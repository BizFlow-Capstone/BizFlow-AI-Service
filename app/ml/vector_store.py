"""
ml/vector_store.py — ChromaDB client for product catalog RAG

Each business location's product catalog is stored in a separate ChromaDB
**collection** named `location_{location_id}`. This provides natural
data isolation — a query for location A can never return results from location B.

Embedding model: intfloat/multilingual-e5-large
  - 560-dim, supports Vietnamese, English, and 100+ languages natively.
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

from app.core.config import settings

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

    logger.info("Loading embedding model: intfloat/multilingual-e5-large …")
    _embedding_fn = SentenceTransformerEmbeddingFunction(
        model_name="intfloat/multilingual-e5-large",
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

    # Embed the product as a rich text string for better semantic matching
    document = f"{product['name']} ({product.get('unit', '')}) [{product.get('category', '')}]"

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
    logger.info("Synced product %s to location %s collection.", product["product_id"], location_id)


async def delete_product(location_id: str, product_id: str) -> None:
    """Remove a product from the location's ChromaDB collection."""
    collection = _get_collection(location_id)
    collection.delete(ids=[product_id])
    logger.info("Deleted product %s from location %s collection.", product_id, location_id)


async def query_products(
    location_id: str,
    query_text: str,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """
    Semantic search for products matching the query text.

    Args:
        location_id: UUID of the business location.
        query_text:  Extracted product phrase from STT (e.g., "xi măng").
        top_k:       Number of results to return. 3 is sufficient for LLM context injection.

    Returns:
        List of product metadata dicts ordered by similarity (most similar first).
    """
    collection = _get_collection(location_id)

    results = collection.query(
        query_texts=[query_text],
        n_results=min(top_k, collection.count() or 1),
        include=["metadatas", "distances"],
    )

    products: list[dict[str, Any]] = []
    if results["metadatas"]:
        for meta in results["metadatas"][0]:
            products.append(dict(meta))

    logger.debug("RAG query '%s' → %d results for location %s", query_text, len(products), location_id)
    return products
