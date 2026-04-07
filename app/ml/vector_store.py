"""
ml/vector_store.py — ChromaDB client for product catalog RAG

Each business location's product catalog is stored in a separate ChromaDB
**collection** named `location_{location_id}`. This provides natural
data isolation — a query for location A can never return results from location B.

Embedding model: configurable via settings.embedding_model_name
  - 384-dim, supports Vietnamese, English, and 100+ languages natively.
  - Chosen over multilingual-e5-large (1024-dim, ~2.24 GB) because HKD product
    catalogs are small (< 500 items) and queries are short product name phrases
    — the quality difference is negligible for this task while resource savings
    on VPS (RAM, startup time, storage) are significant (~4-5x lighter).
  - Downloaded once on first run and cached via HuggingFace cache dir.
  - Loaded into memory once at startup via init_vector_store().

Usage in draft_order_service:
    products = await query_products(location_id="abc-123", query_text="xi măng", top_k=3)
    # → [{"product_id": "...", "name": "Xi măng Hà Tiên", "unit": "bao", ...}, ...]
"""

import logging
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from rapidfuzz import process as fuzz_process, fuzz

from app.core.config import settings
from app.db.mysql_client import fetch_all

logger = logging.getLogger(__name__)

_client: chromadb.ClientAPI | None = None
_embedding_fn: SentenceTransformerEmbeddingFunction | None = None


# ---------------------------------------------------------------------------
# Initialisation (called once at app startup via lifespan)
# ---------------------------------------------------------------------------

async def init_vector_store() -> None:
    """
    Initialise the ChromaDB persistent client and pre-load the embedding model.
    Called from main.py lifespan so the model is warm before the first request.
    """
    global _client, _embedding_fn

    logger.info("Initialising ChromaDB at %s …", settings.chroma_persist_dir)
    _client = chromadb.PersistentClient(path=settings.chroma_persist_dir)

    logger.info("Loading embedding model: %s…", settings.embedding_model_name)
    _embedding_fn = SentenceTransformerEmbeddingFunction(
        model_name=settings.embedding_model_name,
        normalize_embeddings=True,
    )
    logger.info("Vector store ready.")


def _get_collection(location_id: str) -> chromadb.Collection:
    """Return (or create) the ChromaDB collection for a given location."""
    if _client is None or _embedding_fn is None:
        raise RuntimeError("Vector store not initialised. Call init_vector_store() first.")
    return _client.get_or_create_collection(
        name=f"location_{location_id}",
        embedding_function=_embedding_fn,  # type: ignore[arg-type]
        metadata={"hnsw:space": "cosine"},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def sync_product(location_id: str, product: dict[str, Any]) -> None:
    """
    Upsert a single product into the location's ChromaDB collection.

    Args:
        location_id: UUID of the business location.
        product: dict with keys: product_id (str), name (str), unit (str),
                 category (str | None).

    Called by: POST /vector-store/sync  (triggered by BizFlow API on product change)
    """
    collection = _get_collection(location_id)

    # Fetch all SaleItem units for this product to enrich the document text.
    # This ensures semantic search can match any unit the customer says
    # (e.g. "thùng", "gói") even if the product's default unit is "kg".
    sale_item_units = _fetch_sale_item_units(product["product_id"])

    # Build rich document text: include name, default unit, category, + all sale units
    all_units = list(dict.fromkeys(
        [u for u in [product.get("unit", "")] + sale_item_units if u]
    ))
    units_str = ", ".join(all_units)
    document = (
        f"{product['name']} ({units_str}) [{product.get('category', '')}]"
    )

    collection.upsert(
        ids=[product["product_id"]],
        documents=[document],
        metadatas=[{
            "product_id": product["product_id"],
            "name":       product["name"],
            "unit":       product.get("unit", ""),
            "category":   product.get("category", ""),
        }],
    )
    logger.info(
        "Synced product %s to location %s collection (units: %s).",
        product["product_id"], location_id, units_str,
    )


def _fetch_sale_item_units(product_id: str) -> list[str]:
    """Return distinct non-null units from SaleItems for a product (sync DB call)."""
    try:
        rows = fetch_all(
            "SELECT DISTINCT Unit FROM SaleItems WHERE ProductId = :pid AND DeletedAt IS NULL AND Unit IS NOT NULL",
            {"pid": product_id},
        )
        return [r["Unit"] for r in rows if r.get("Unit")]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch SaleItem units for product %s: %s", product_id, exc)
        return []


async def delete_product(location_id: str, product_id: str) -> None:
    """Remove a product from the location's ChromaDB collection."""
    collection = _get_collection(location_id)
    collection.delete(ids=[product_id])
    logger.info("Deleted product %s from location %s collection.", product_id, location_id)


def list_products(location_id: str, limit: int = 200) -> dict[str, Any]:
    """
    Return all products stored in a location's ChromaDB collection.

    Args:
        location_id: The business location id.
        limit:       Max number of documents to return (default 200).

    Returns:
        dict with keys: location_id, total (int), items (list of metadata dicts).
    """
    collection = _get_collection(location_id)
    total = collection.count()
    if total == 0:
        return {"location_id": location_id, "total": 0, "items": []}

    result = collection.get(
        limit=limit,
        include=["metadatas", "documents"],
    )
    items = [
        {
            "product_id": meta.get("product_id", ids),
            "name":       meta.get("name", ""),
            "unit":       meta.get("unit", ""),
            "category":   meta.get("category", ""),
            "document":   doc,
        }
        for meta, doc, ids in zip(
            result["metadatas"] or [],
            result["documents"] or [],
            result["ids"] or [],
        )
    ]
    return {"location_id": location_id, "total": total, "items": items}


async def backfill_location(location_id: str) -> dict[str, Any]:
    """
    Bulk-sync all active, non-deleted products of a location from MySQL into ChromaDB.

    Queries the Products table joined with BusinessTypes to get the category name,
    then upserts every product via sync_product(). Safe to re-run — ChromaDB's
    upsert is idempotent so already-synced products just get refreshed.

    Args:
        location_id: The business location id (integer stored as string).

    Returns:
        dict with keys: location_id, synced (count), skipped (error count).
    """
    _SQL = """
        SELECT
            p.ProductId  AS product_id,
            p.ProductName AS name,
            p.Unit        AS unit,
            bt.Name       AS category
        FROM Products p
        JOIN BusinessTypes bt ON p.BusinessTypeId = bt.BusinessTypeId
        WHERE p.BusinessLocationId = :loc_id
          AND p.DeletedAt IS NULL
          AND p.Status   = 'Active'
    """
    rows = fetch_all(_SQL, {"loc_id": int(location_id)})
    synced = 0
    skipped = 0
    for row in rows:
        try:
            await sync_product(
                location_id=location_id,
                product={
                    "product_id": str(row["product_id"]),
                    "name":       row["name"],
                    "unit":       row["unit"] or "",
                    "category":   row["category"] or "",
                },
            )
            synced += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Backfill skipped product %s for location %s: %s",
                row["product_id"], location_id, exc,
            )
            skipped += 1

    logger.info(
        "Backfill complete for location %s: synced=%d, skipped=%d.",
        location_id, synced, skipped,
    )
    return {"location_id": location_id, "synced": synced, "skipped": skipped}


async def query_products(
    location_id: str,
    query_text: str,
    top_k: int = 3,
    fuzzy_threshold: float | None = None,
) -> list[dict[str, Any]]:
    """
    Semantic search for products matching the query text, with a fuzzy-string
    fallback to handle STT tonal/diacritic errors in Vietnamese
    (e.g. "Bạt sỉu" from STT → should match "Bạc xỉu" in catalog).

    Strategy:
      1. Run semantic (dense) search via ChromaDB.
      2. If the best cosine distance > fuzzy_threshold (weak match), also run
         rapidfuzz token_set_ratio across all product names in the collection.
      3. Merge: products confirmed by both paths first, then semantic-only,
         then fuzzy-only. Deduplicated by product_id.

    Args:
        location_id:     UUID of the business location.
        query_text:      Extracted product phrase from STT (e.g., "xi măng").
        top_k:           Number of results to return.
        fuzzy_threshold: Cosine distance above which fuzzy fallback is triggered.
                 If omitted, uses settings.vector_fuzzy_threshold.
                 (0 = perfect, 1 = no similarity; 0.35 is a practical
                         boundary between "confident" and "uncertain" matches).

    Returns:
        List of product metadata dicts ordered by combined confidence (best first).
    """
    collection = _get_collection(location_id)
    count = collection.count()
    if count == 0:
        return []
    threshold = settings.vector_fuzzy_threshold if fuzzy_threshold is None else fuzzy_threshold

    # --- Step 1: Semantic search ---
    semantic_results = collection.query(
        query_texts=[query_text],
        n_results=min(top_k, count),
        include=["metadatas", "distances"],
    )

    semantic_products: list[dict[str, Any]] = []
    best_distance = 1.0
    if semantic_results["metadatas"] and semantic_results["distances"]:
        for meta, dist in zip(
            semantic_results["metadatas"][0],
            semantic_results["distances"][0],
        ):
            semantic_products.append(dict(meta))
            if dist < best_distance:
                best_distance = dist

    # --- Step 2: Fuzzy fallback (only when semantic confidence is low) ---
    fuzzy_products: list[dict[str, Any]] = []
    if best_distance > threshold:
        logger.debug(
            "Semantic match weak (distance=%.3f > %.2f) for query '%s' — running fuzzy fallback.",
            best_distance, threshold, query_text,
        )
        all_items = collection.get(include=["metadatas"])
        all_metas: list[dict[str, Any]] = all_items.get("metadatas") or []

        # Build name→meta map, run fuzzy match on product names
        name_to_meta = {m["name"]: m for m in all_metas}
        matches = fuzz_process.extract(
            query_text,
            name_to_meta.keys(),
            scorer=fuzz.token_set_ratio,
            limit=top_k,
            # minimum fuzzy score (0–100) to consider a hit
            score_cutoff=settings.vector_fuzzy_score_cutoff,
        )
        fuzzy_products = [dict(name_to_meta[name]) for name, _score, _idx in matches]

    # --- Step 3: Merge (confirmed-by-both first, dedup by product_id) ---
    if not fuzzy_products:
        logger.debug(
            "RAG query '%s' → %d semantic results (distance=%.3f) for location %s",
            query_text, len(semantic_products), best_distance, location_id,
        )
        return semantic_products

    semantic_ids = {p["product_id"] for p in semantic_products}
    fuzzy_ids    = {p["product_id"] for p in fuzzy_products}
    confirmed    = [p for p in semantic_products if p["product_id"] in fuzzy_ids]
    sem_only     = [p for p in semantic_products if p["product_id"] not in fuzzy_ids]
    fuzz_only    = [p for p in fuzzy_products    if p["product_id"] not in semantic_ids]

    merged = (confirmed + sem_only + fuzz_only)[:top_k]
    logger.debug(
        "RAG query '%s' → %d merged results (semantic=%d, fuzzy=%d, confirmed=%d) for location %s",
        query_text, len(merged), len(semantic_products), len(fuzzy_products),
        len(confirmed), location_id,
    )
    return merged
