# AI Service Architecture

## 1. Overview

The BizFlow AI Service is an independent Python microservice deployed alongside the .NET Core API on the VPS (Docker Compose). It provides six AI-powered capabilities that help household business owners understand and manage their business without requiring any data science expertise.

| Capability | User-facing description |
|---|---|
| **Voice-to-Draft-Order** | Owner speaks an order naturally; system creates a draft for review |
| **Revenue Forecasting** | Predicts next 7 days of revenue with a Vietnamese trend explanation |
| **Anomaly Detection** | Alerts when revenue or accounting figures appear abnormal or contain data-entry errors |
| **Reorder Suggestions** | Recommends which products to import, when, and how much |
| **OCR Document Scanning** | Owner photographs an invoice or delivery slip; system auto-fills the Import/Order form |
| **Product Performance Insights** | Highlights top-selling products, growth trends, and high-margin items worth promoting |

---

## 2. Technology Stack

| Component | Technology | Reason |
|---|---|---|
| API Framework | **FastAPI** (Python) | Async, fast, auto-generates OpenAPI docs |
| Speech-to-Text | **Google Cloud STT** (`vi-VN`, Synchronous Recognition) — primary; **Whisper** (`whisper-1`) — fallback | Google STT: free tier 60 min/month, dedicated Vietnamese model; Whisper: reliable fallback if quota exceeded |
| LLM | **OpenAI GPT-4o-mini** (extraction / explanation) + **GPT-4o Vision** (OCR) | gpt-4o-mini is 15× cheaper than gpt-4o and sufficient for structured JSON extraction; Vision API handles document OCR with Vietnamese text |
| Vector Store | **ChromaDB** + **multilingual-e5-large** | In-process vector DB, no separate service needed; stores product catalog embeddings for RAG |
| Revenue Forecasting | **Pandas** (EMA/SMA computation) + **GPT-4o-mini** (Vietnamese explanation) | No Prophet dependency (~200 MB); works with as little as 14 days of data; LLM explains trends naturally in Vietnamese |
| Anomaly Detection | **Rule-based checks** (realtime) + **GPT-4o-mini** (nightly pattern summary) | Rule-based catches 80 % of data-entry errors instantly with zero cold-start; LLM provides natural Vietnamese explanation for subtler patterns |
| Reorder Suggestions | **Pandas** + statistical reorder-point formula | Sales velocity + safety stock model; explainable and verifiable by non-technical users |
| Product Insights | **Pandas** + SQL aggregations | Pure data aggregation — no ML needed; results are derived entirely from the business's own data |
| DB Access | **SQLAlchemy** + **PyMySQL** | Reads historical sales/import data from the same Aiven MySQL |
| Scheduler trigger | **Hangfire** (in .NET API) | Scheduled jobs (nightly) call AI Service HTTP endpoints to re-run forecasts, anomaly checks, and reorder calculations |

---

## 3. Service Architecture

### 3.1 Package Structure

```
bizflow-ai/
├── main.py                         FastAPI application entry point, router registration
│
├── routers/
│   ├── draft_order.py              POST /draft-order              (sync — user waits)
│   ├── forecast.py                 POST /forecast                 (called by Hangfire scheduler)
│   ├── anomaly.py                  POST /anomaly                  (called by Hangfire scheduler)
│   │                               POST /anomaly/check-record     (sync — called on each order/import save)
│   ├── reorder.py                  POST /reorder                  (called by Hangfire scheduler)
│   ├── ocr.py                      POST /ocr/invoice              (sync — user waits)
│   │                               POST /ocr/delivery-note        (sync — user waits)
│   └── product_insights.py         POST /product-insights         (called by Hangfire scheduler)
│
├── services/
│   ├── draft_order_service.py      Orchestrates STT → RAG → LLM → structured order
│   ├── forecast_service.py         Loads sales data → EMA/SMA computation → GPT explanation → writes to DB
│   ├── anomaly_service.py          Tier-1: rule-based checks per record; Tier-2: LLM nightly pattern summary
│   ├── reorder_service.py          Calculates reorder points → writes suggestions to DB
│   ├── ocr_service.py              GPT-4o Vision: extract structured data from invoice/delivery images
│   └── product_insights_service.py Pandas aggregations: top sellers, growth trends, high-margin items
│
├── ml/
│   ├── stt.py                      Google STT primary (vi-VN) + Whisper fallback, returns transcript text
│   ├── llm.py                      Wrapper: OpenAI client, prompt templates (chat + vision)
│   └── vector_store.py             ChromaDB client: sync product catalog, query similar products
│
├── db/
│   └── mysql_client.py             SQLAlchemy engine, query helpers for reading/writing MySQL
│
├── Dockerfile
└── requirements.txt
```

### 3.2 Communication Pattern with BizFlow API

The AI Service is **not exposed to the internet**. Only the BizFlow API (container-to-container via Docker internal network) can call it.

Two communication patterns are used:

```
Pattern A — Synchronous (used by: Draft Order, OCR)
─────────────────────────────────────────────────────
Client (Flutter/Web)
  → POST /api/orders/draft-order          (sends audio file)
  → BizFlow API                           (forwards to AI Service)
  → AI Service: STT + RAG + LLM          (processes ~5–8 s)
  ← Returns draft order JSON
  ← BizFlow API returns to client
  ← Client displays draft for user review

Pattern B — Asynchronous / Scheduled (used by: Forecast, Anomaly, Reorder)
────────────────────────────────────────────────────────────────────────────
Hangfire Job (runs nightly, e.g., 01:00 AM)
  → POST http://bizflow-ai:5000/forecast  (trigger, no user waiting)
  → AI Service: pulls data from MySQL, runs model, writes results back to MySQL
Client (next morning, opens dashboard)
  → GET /api/analytics/forecast
  → BizFlow API reads pre-computed results from MySQL
  ← Returns instantly (no model inference at read time)
```

> **Why async for forecast/anomaly/reorder?**
> These models process weeks or months of historical data. Running them synchronously on a user request would result in 5–60 second loading times. By pre-computing nightly and storing results, the dashboard responds in < 200 ms.

---

## 4. Feature 1: Voice-to-Draft-Order

### 4.1 Description

The owner speaks a natural Vietnamese command — e.g., *"Bán cho anh Ba 5 bao xi măng, ghi nợ"* — and the system creates a structured draft order that the owner reviews and confirms before saving.

### 4.2 Technology

| Step | Technology |
|---|---|
| Audio capture | Flutter microphone package (on device) |
| Speech-to-Text | **Google Cloud STT** (`vi-VN`, Synchronous Recognition) — primary; **Whisper** (`whisper-1`) — fallback |
| Product matching | **RAG**: ChromaDB vector search over the location's product catalog |
| Order extraction | **LLM** (GPT-4o-mini): structured extraction with product context injected into prompt |
| Output | JSON draft order (productId, quantity, unit, customerId, isDebt) |

> **STT strategy**: Google Cloud STT is the primary engine — it has a free tier of 60 minutes/month, a dedicated `vi-VN` model, and lower per-minute cost than Whisper when billed. Whisper (`whisper-1`) is the automatic fallback if the Google STT quota is exceeded or the service is unavailable. Both operate in **file-based synchronous mode** (record audio → upload → get transcript). The switch between providers requires changing only one function in `ml/stt.py`.

### 4.3 RAG Detail

The product catalog of each business location is embedded and stored in ChromaDB:

```
Sync trigger: when owner creates/edits/deletes a product
  → BizFlow API calls POST /ai/vector-store/sync
  → AI Service: re-embeds changed product (name + unit + category)
  → Stores in ChromaDB collection keyed by locationId
```

When extracting an order:
```
User says: "5 bao xi măng cho anh Ba"
  1. STT → "5 bao xi măng cho anh Ba"
  2. ChromaDB query: top-3 similar products to "xi măng" (from location's catalog)
     → returns: [{"id": 42, "name": "Xi măng Hà Tiên bao 50kg", "unit": "bao", ...}]
  3. LLM prompt (with product context injected):
     → "Given products: [list]... extract order from: '5 bao xi măng cho anh Ba'"
     → returns: {"productId": 42, "quantity": 5, "unit": "bao", "customerName": "Anh Ba", "isDebt": true}
```

### 4.4 Data Flow Diagram

```
[Flutter] ─── audio (multipart) ──► [BizFlow API]
                                          │
                                          │ HTTP POST /draft-order (audio file)
                                          ▼
                                    [AI Service]
                                          │
                          ┌───────────────┼───────────────┐
                          ▼               ▼               ▼
                       [STT]          [ChromaDB]       [LLM]
                    (transcript)   (product context)  (extraction)
                          └───────────────┼───────────────┘
                                          ▼
                                   Draft Order JSON
                                          │
                          ◄───────────────┘
                    [BizFlow API]
                          │
                ◄─────────┘
           [Flutter] displays draft → user confirms → saved to MySQL
```

### 4.5 Fallback

If the AI Service is unavailable (timeout / error), the client falls back to manual order entry. The BizFlow API returns `503 AI Service Unavailable` with a user-friendly message.

If Google STT quota is exceeded mid-request, `ml/stt.py` transparently retries the same audio with Whisper `whisper-1` before returning an error to the caller.

---

## 5. Feature 2: Revenue Forecasting

### 5.1 Description

Predicts the business location's revenue for the next **7 days**, displayed as a chart on the dashboard, along with a short Vietnamese explanation of the current trend. Helps owners anticipate slow/busy periods and plan inventory accordingly.

### 5.2 Technology: Pandas EMA/SMA + GPT-4o-mini Explanation

**Why not Facebook Prophet?**
Prophet requires ~200 MB of additional dependencies (`pystan`, `cmdstanpy`) that significantly inflate the Docker image, and a minimum of 60 days of data before it produces meaningful forecasts. For a household business that may have only 2–4 weeks of history, this is a hard blocker at demo time.

**Chosen approach — two-component design:**

| Component | Technology | Responsibility |
|---|---|---|
| Forecast computation | **Pandas** — Exponential Moving Average (EMA) + ±1σ confidence band | Numeric forecast values; works with as few as 14 days of history |
| Trend explanation | **GPT-4o-mini** | Generates a 2–3 sentence Vietnamese summary of the trend, weekly pattern, and any notable days |

**EMA computation:**
- Span of 7 days (recent data weighted more heavily than older data)
- Confidence band: point forecast ± 1 standard deviation of the residuals from the last 14 days
- Missing days (holidays, closures) are forward-filled with 0 before smoothing

### 5.3 Input Data

Pulled from MySQL on each scheduled run:

```sql
SELECT DATE(created_at) AS ds, SUM(total_amount) AS y
FROM orders
WHERE location_id = :location_id
  AND status = 'CONFIRMED'
  AND created_at >= DATE_SUB(NOW(), INTERVAL 3 MONTH)
GROUP BY DATE(created_at)
ORDER BY ds
```

> Minimum viable history: **14 days** of confirmed sales. If a location has less data, the forecast is skipped and a `"not_enough_data"` flag is stored. This is much lower than Prophet's 60-day requirement.

### 5.4 Output

Stored in MySQL table `ai_revenue_forecasts`:

| Column | Type | Description |
|---|---|---|
| `location_id` | UUID | The business location |
| `forecast_date` | DATE | Predicted date |
| `predicted_revenue` | DECIMAL | EMA point forecast |
| `lower_bound` | DECIMAL | Point forecast − 1σ |
| `upper_bound` | DECIMAL | Point forecast + 1σ |
| `trend_note` | TEXT | 2–3 sentence Vietnamese explanation generated by GPT-4o-mini |
| `generated_at` | DATETIME | Timestamp of forecast run |

### 5.5 Schedule

```
Hangfire RecurringJob: "forecast-all-locations"
  Cron: "0 1 * * *"   (01:00 AM daily)
  → POST http://bizflow-ai:5000/forecast
     body: { "location_ids": [...all active locations...] }
  → AI Service computes EMA forecast per location, generates Vietnamese explanation,
    writes to ai_revenue_forecasts
```

### 5.6 Data Flow Diagram

```
[Hangfire Job @ 01:00 AM]
       │ POST /forecast (locationIds[])
       ▼
 [AI Service]
       │
       ├─── SELECT sales data ──► [Aiven MySQL]
       │         ◄── returns historical daily revenue (last 3 months)
       │
       ├─── Pandas: compute 7-day EMA forecast + ±1σ confidence band
       │
       ├─── GPT-4o-mini: generate Vietnamese trend explanation
       │         (sends last 30 days as CSV in prompt)
       │
       └─── UPSERT forecast results ──► [Aiven MySQL ai_revenue_forecasts]

[Next morning: User opens dashboard]
       │ GET /api/analytics/forecast?locationId=...
       ▼
 [BizFlow API]
       │ SELECT FROM ai_revenue_forecasts ──► [Aiven MySQL]
       ◄── returns pre-computed results instantly
       ▼
 [Client renders forecast chart + trend explanation]
```

---

## 6. Feature 3: Anomaly Detection

### 6.1 Description

Monitors the business's financial data and raises alerts when something looks abnormal. Targets two types of anomalies:

| Type | Examples |
|---|---|
| **Revenue anomaly** | A day with near-zero revenue despite multiple orders (entry error), a spike 3× the normal average (data entry mistake), sudden drop in a usually profitable week |
| **Accounting / data quality anomaly** | Product sold at ₫0, an import with total cost far below unit price × quantity, a debt recorded for an unknown customer |

### 6.2 Technology: 2-Tier Detection

**Why not Isolation Forest (scikit-learn)?**
Household businesses process a few dozen orders per day. Isolation Forest needs enough data to learn a "normal" pattern — with sparse data it produces a high false-positive rate, which causes owners to distrust and ignore all alerts.

The chosen 2-tier approach is simpler, more reliable, and produces natural Vietnamese explanations without scikit-learn:

| Tier | Trigger | Method | Catches |
|---|---|---|---|
| **Tier 1 — Rule-based** | Realtime, on every order/import save | Hard-coded business rules | Data-entry errors (price = 0, negative qty, cost > revenue × 3, etc.) |
| **Tier 2 — LLM pattern summary** | Nightly (02:00 AM) | GPT-4o-mini reviews last 7 days | Subtle pattern anomalies (unusually quiet week, consistent pricing drift) |

### 6.3 Tier 1: Rule-Based Checks

Triggered synchronously by the BizFlow API immediately after saving an order or import record. Endpoint: `POST /anomaly/check-record`.

**Rules evaluated per record:**

| Rule | Condition | Severity |
|---|---|---|
| Zero-price sale | `unit_price == 0` for a confirmed order item | `CRITICAL` |
| Negative quantity | `quantity <= 0` | `CRITICAL` |
| Cost exceeds revenue | `import_total_cost > order_total_revenue × 3` for same product in same day | `WARNING` |
| Unknown customer debt | `is_debt == true AND customer_id IS NULL` | `WARNING` |
| Price far from history | `unit_price < avg_historical_price × 0.3` OR `> avg_historical_price × 3` | `WARNING` |

### 6.4 Tier 2: LLM Nightly Pattern Summary

Triggered by Hangfire at 02:00 AM. Sends a 7-day aggregated summary per location to GPT-4o-mini:

```
Prompt:
  "Đây là dữ liệu kinh doanh 7 ngày qua của một hộ kinh doanh nhỏ:
   [daily_revenue, order_count, avg_order_value for last 7 days as CSV]
   Hãy chỉ ra các điểm bất thường (nếu có) và giải thích ngắn gọn bằng tiếng Việt
   dành cho chủ hộ kinh doanh."

→ "Ngày 04/03 có 5 đơn hàng nhưng doanh thu chỉ 50.000đ — thấp bất thường so
   với trung bình 2.500.000đ/ngày. Vui lòng kiểm tra lại các đơn hàng trong ngày này."
```

### 6.5 Output

Stored in MySQL table `ai_anomaly_alerts`:

| Column | Type | Description |
|---|---|---|
| `location_id` | UUID | |
| `alert_type` | ENUM | `REVENUE_ANOMALY`, `DATA_QUALITY` |
| `severity` | ENUM | `WARNING`, `CRITICAL` |
| `tier` | ENUM | `RULE_BASED`, `LLM_PATTERN` |
| `reference_date` | DATE | The date of the anomalous record |
| `description` | TEXT | Human-readable Vietnamese explanation |
| `reference_id` | UUID | FK to the specific order/import (Tier 1 only) |
| `is_acknowledged` | BOOLEAN | Owner has seen/dismissed the alert |
| `generated_at` | DATETIME | |

### 6.6 Schedule

```
Tier 1 — Realtime:
  BizFlow API (on order/import save)
  → POST http://bizflow-ai:5000/anomaly/check-record
     body: { "location_id": "...", "record_type": "order|import", "record_id": "..." }
  → AI Service runs rule checks, writes any alerts immediately
  → BizFlow API: if CRITICAL alert written → send FCM push notification right away

Tier 2 — Nightly:
  Hangfire RecurringJob: "anomaly-pattern-check-all-locations"
    Cron: "0 2 * * *"   (02:00 AM daily)
    → POST http://bizflow-ai:5000/anomaly
       body: { "location_ids": [...] }
    → AI Service builds 7-day summary per location, calls GPT-4o-mini,
      writes pattern alerts to ai_anomaly_alerts
```

### 6.7 Data Flow Diagram

```
── Tier 1: Realtime rule-based ─────────────────────────────────────────────
[BizFlow API — on order/import save]
       │ POST /anomaly/check-record (record details)
       ▼
 [AI Service]
       ├─── Evaluate hard business rules against record
       ├─── If violation found → INSERT alert (CRITICAL/WARNING)
       │
       └─── [Aiven MySQL ai_anomaly_alerts]
                    │
       [BizFlow API: if CRITICAL → FCM push]
                    ▼
       [Flutter/ReactJS: "⚠️ Phát hiện lỗi nhập liệu"]

── Tier 2: Nightly LLM pattern summary ─────────────────────────────────────
[Hangfire Job @ 02:00 AM]
       │ POST /anomaly (locationIds[])
       ▼
 [AI Service]
       ├─── SELECT 7-day aggregated data ──► [Aiven MySQL]
       ├─── Build plain-text summary per location
       ├─── GPT-4o-mini: identify pattern anomalies + Vietnamese explanation
       └─── INSERT pattern alerts ──► [Aiven MySQL ai_anomaly_alerts]
```

---

## 7. Feature 4: Reorder / Import Suggestions

### 7.1 Description

Tells the business owner which products are running low and how much to order, based on:
- **Current stock level** (quantity on hand)
- **Sales velocity** (average units sold per day, calculated from historical orders)
- **Lead time** (fixed assumption: 3 days, configurable per product in future)

Example output: *"Xi măng Hà Tiên: còn 10 bao, dự kiến hết sau 2 ngày dựa trên doanh số. Đề xuất nhập thêm 50 bao."*

### 7.2 Technology

| Component | Technology |
|---|---|
| Sales velocity | **Pandas**: rolling 14-day average of units sold per product per day |
| Stock level | Read from `products.stock_quantity` in MySQL |
| Reorder logic | Statistical **reorder-point formula** (see below) |

**Reorder-point formula:**

$$\text{Reorder Point} = \text{Avg Daily Sales} \times \text{Lead Time} + \text{Safety Stock}$$

$$\text{Safety Stock} = Z \times \sigma_{\text{daily sales}} \times \sqrt{\text{Lead Time}}$$

Where:
- $Z = 1.65$ (95% service level — reasonable for household business)
- $\sigma$ = standard deviation of daily sales over past 30 days
- Lead time = 3 days (default)

**Suggested order quantity:**

$$\text{Order Qty} = \text{Max Stock Level} - \text{Current Stock}$$

Max Stock Level = 30-day supply at average sales velocity (configurable).

### 7.3 Output

Stored in MySQL table `ai_reorder_suggestions`:

| Column | Type | Description |
|---|---|---|
| `location_id` | UUID | |
| `product_id` | UUID | |
| `current_stock` | DECIMAL | Stock at time of calculation |
| `days_until_stockout` | INT | Estimated days before stock hits zero |
| `suggested_quantity` | DECIMAL | Units to reorder |
| `avg_daily_sales` | DECIMAL | 14-day rolling average |
| `urgency` | ENUM | `LOW` (>7 days), `MEDIUM` (3–7 days), `HIGH` (<3 days) |
| `generated_at` | DATETIME | |

### 7.4 Schedule

```
Hangfire RecurringJob: "reorder-suggestions-all-locations"
  Cron: "0 3 * * *"   (03:00 AM daily)
  → POST http://bizflow-ai:5000/reorder
  → AI Service calculates for all products at all active locations
  → Writes to ai_reorder_suggestions
  → BizFlow API checks for HIGH urgency items → FCM push to owner if any found
```

### 7.5 Data Flow Diagram

```
[Hangfire Job @ 03:00 AM]
       │ POST /reorder (locationIds[])
       ▼
 [AI Service]
       ├─── SELECT current stock per product ──► [Aiven MySQL]
       ├─── SELECT order line items (last 30 days) ──► [Aiven MySQL]
       │
       ├─── Calculate avg daily sales per product (pandas rolling mean)
       ├─── Calculate reorder point + suggested quantity
       │
       └─── UPSERT suggestions ──► [Aiven MySQL ai_reorder_suggestions]
                    │
       [BizFlow API checks HIGH urgency items]
                    │ if found: FCM push notification
                    ▼
       [Flutter/ReactJS: "📦 3 sản phẩm sắp hết hàng"]
```

---

## 8. Feature 5: OCR Document Scanning

### 8.1 Description

The owner photographs an import invoice or delivery slip using the Flutter app. The AI Service reads the document image using GPT-4o Vision and returns a structured pre-filled form that the owner reviews and confirms before saving.

**Use cases:**
- **Import invoice** from a supplier → auto-fill Import form (product names, quantities, unit prices, total)
- **Delivery slip** → auto-fill bulk Order form (product names, quantities)

### 8.2 Technology

| Step | Technology |
|---|---|
| Image capture | Flutter camera / file-picker |
| OCR & extraction | **GPT-4o Vision** (handles Vietnamese text, table layouts, handwritten notes) |
| Output | Structured JSON with pre-filled form fields |

**Why GPT-4o Vision instead of Tesseract/dedicated OCR?**
- Single API call handles both OCR and semantic extraction (no separate NLP step)
- Vietnamese text support is native
- Handles poor lighting, skewed angles, printed and handwritten content better than Tesseract at this scale
- Cost: ~$0.01–$0.03 per image — acceptable for household business usage

**Image pre-processing (client-side before upload):**
- Resize to max 1280 px on longest side
- JPEG compress to ≤ 1 MB
- This reduces API cost and improves recognition accuracy on blurry photos

### 8.3 Endpoints

**`POST /ocr/invoice`** — extracts import invoice data

```json
// Request (multipart/form-data)
{ "image": <file>, "location_id": "uuid" }

// Response
{
  "supplier_name": "Công ty TNHH ABC",
  "invoice_date": "2026-04-03",
  "items": [
    { "product_name": "Xi măng Hà Tiên", "quantity": 50, "unit": "bao", "unit_price": 95000 },
    { "product_name": "Cát xây dựng",    "quantity": 10, "unit": "m3",  "unit_price": 250000 }
  ],
  "total_amount": 7250000,
  "confidence": "high"   // "high" | "medium" | "low" — based on image quality heuristics
}
```

**`POST /ocr/delivery-note`** — extracts delivery slip data

```json
// Request (multipart/form-data)
{ "image": <file>, "location_id": "uuid" }

// Response
{
  "items": [
    { "product_name": "Gạch bông 30x30", "quantity": 200, "unit": "viên" }
  ],
  "confidence": "medium"
}
```

### 8.4 Data Flow Diagram

```
[Flutter] ─── image (multipart, ≤1 MB) ──► [BizFlow API]
                                                  │
                                                  │ HTTP POST /ocr/invoice
                                                  ▼
                                           [AI Service]
                                                  │
                                       [GPT-4o Vision API]
                                       (image + prompt → JSON)
                                                  │
                                           Structured JSON
                                                  │
                              ◄───────────────────┘
                        [BizFlow API]
                              │
                    ◄─────────┘
          [Flutter] displays pre-filled form → user reviews/edits → confirms → saved to MySQL
```

### 8.5 Fallback

If the OCR confidence is `"low"` or GPT returns an unparseable response, the client is notified and the form remains empty for manual entry. The owner is never silently given wrong data.

---

## 9. Feature 6: Product Performance Insights

### 9.1 Description

Gives the business owner a clear view of how their products are performing, based entirely on their own sales data. **No cross-business data, no LLM hallucination risk.** Three insight types are computed nightly:

| Insight | Description |
|---|---|
| **Top sellers** | Products ranked by revenue and units sold over the last 7 / 30 days |
| **Growth trend** | Products whose 7-day sales velocity is significantly higher than their 30-day average (rising stars) |
| **Promote candidates** | High-margin products with above-average stock levels — suggesting the owner has room to push sales |

### 9.2 Technology

| Component | Technology |
|---|---|
| Top sellers | **SQL** aggregation: `SUM(quantity)`, `SUM(revenue)` grouped by product |
| Growth trend | **Pandas**: compare 7-day rolling mean vs 30-day rolling mean; flag if ratio > 1.5 |
| Promote candidates | **Pandas**: join margin data (from `products` table) with stock levels; filter high-margin + high-stock |

No ML model needed — all computations are deterministic aggregations over the location's own data.

### 9.3 Output

Stored in MySQL table `ai_product_insights`:

| Column | Type | Description |
|---|---|---|
| `location_id` | UUID | |
| `product_id` | UUID | |
| `insight_type` | ENUM | `TOP_SELLER`, `GROWTH_TREND`, `PROMOTE_CANDIDATE` |
| `rank` | INT | Rank within insight type (1 = best) |
| `metric_value` | DECIMAL | The underlying metric (revenue, growth ratio, margin %) |
| `period_days` | INT | Lookback period used (7 or 30) |
| `generated_at` | DATETIME | |

### 9.4 Schedule

```
Hangfire RecurringJob: "product-insights-all-locations"
  Cron: "30 3 * * *"   (03:30 AM daily)
  → POST http://bizflow-ai:5000/product-insights
     body: { "location_ids": [...all active locations...] }
  → AI Service computes all 3 insight types, writes to ai_product_insights
```

### 9.5 Data Flow Diagram

```
[Hangfire Job @ 03:30 AM]
       │ POST /product-insights (locationIds[])
       ▼
 [AI Service]
       ├─── SELECT order line items (last 30 days) ──► [Aiven MySQL]
       ├─── SELECT products (stock_quantity, margin) ──► [Aiven MySQL]
       │
       ├─── SQL/Pandas: compute top sellers (7-day + 30-day)
       ├─── Pandas: compute 7d/30d velocity ratio → flag growth trends
       ├─── Pandas: join margin × stock → flag promote candidates
       │
       └─── UPSERT insights ──► [Aiven MySQL ai_product_insights]

[User opens dashboard]
       │ GET /api/analytics/product-insights?locationId=...
       ▼
 [BizFlow API reads pre-computed results instantly]
       ▼
 [Client renders: "Top sellers / Đang tăng trưởng / Nên đẩy mạnh" cards]
```

---

## 10. Nightly Job Schedule Summary

All scheduled jobs are triggered from **Hangfire** (running inside the .NET API process). They call the AI Service over the Docker internal network.

| Time | Job | AI Service Endpoint |
|---|---|---|
| 01:00 AM | Revenue forecast update | `POST /forecast` |
| 02:00 AM | Anomaly pattern check (Tier 2 — LLM nightly) | `POST /anomaly` |
| 03:00 AM | Reorder suggestions | `POST /reorder` |
| 03:30 AM | Product performance insights | `POST /product-insights` |

> **Anomaly Tier 1** (rule-based) is triggered synchronously in real-time by the BizFlow API on every order/import save — it is not a scheduled job.

ChromaDB (product vector store) is updated in real-time — synced whenever a product is created, updated, or deleted via `POST /vector-store/sync`.

---

## 11. AI Service Endpoints Summary

| Method | Path | Pattern | Triggered by |
|---|---|---|---|
| `POST` | `/draft-order` | Sync | Client (via BizFlow API proxy) |
| `POST` | `/vector-store/sync` | Sync | BizFlow API (on product change) |
| `POST` | `/forecast` | Async (no wait) | Hangfire job |
| `POST` | `/anomaly` | Async (no wait) | Hangfire job (Tier 2 — nightly) |
| `POST` | `/anomaly/check-record` | Sync | BizFlow API (on each order/import save — Tier 1) |
| `POST` | `/reorder` | Async (no wait) | Hangfire job |
| `POST` | `/ocr/invoice` | Sync | Client (via BizFlow API proxy) |
| `POST` | `/ocr/delivery-note` | Sync | Client (via BizFlow API proxy) |
| `POST` | `/product-insights` | Async (no wait) | Hangfire job |

---

## 12. Database Tables Added by AI Features

```sql
-- Pre-computed revenue forecasts (EMA/SMA + GPT explanation)
CREATE TABLE ai_revenue_forecasts (
    id                CHAR(36)       PRIMARY KEY,
    location_id       CHAR(36)       NOT NULL,
    forecast_date     DATE           NOT NULL,
    predicted_revenue DECIMAL(15,2),
    lower_bound       DECIMAL(15,2),
    upper_bound       DECIMAL(15,2),
    trend_note        TEXT,                        -- Vietnamese explanation from GPT-4o-mini
    generated_at      DATETIME       NOT NULL,
    INDEX idx_location_date (location_id, forecast_date)
);

-- Anomaly alerts (Tier 1 rule-based + Tier 2 LLM pattern)
CREATE TABLE ai_anomaly_alerts (
    id              CHAR(36)   PRIMARY KEY,
    location_id     CHAR(36)   NOT NULL,
    alert_type      ENUM('REVENUE_ANOMALY','DATA_QUALITY') NOT NULL,
    severity        ENUM('WARNING','CRITICAL') NOT NULL,
    tier            ENUM('RULE_BASED','LLM_PATTERN') NOT NULL,
    reference_date  DATE,
    description     TEXT       NOT NULL,
    reference_id    CHAR(36),                      -- FK to order/import (Tier 1 only)
    is_acknowledged BOOLEAN    DEFAULT FALSE,
    generated_at    DATETIME   NOT NULL,
    INDEX idx_location_severity (location_id, severity, is_acknowledged)
);

-- Reorder suggestions per product
CREATE TABLE ai_reorder_suggestions (
    id                 CHAR(36)   PRIMARY KEY,
    location_id        CHAR(36)   NOT NULL,
    product_id         CHAR(36)   NOT NULL,
    current_stock      DECIMAL(15,3),
    days_until_stockout INT,
    suggested_quantity DECIMAL(15,3),
    avg_daily_sales    DECIMAL(15,3),
    urgency            ENUM('LOW','MEDIUM','HIGH') NOT NULL,
    generated_at       DATETIME   NOT NULL,
    INDEX idx_location_urgency (location_id, urgency)
);

-- Product performance insights (top sellers / growth trends / promote candidates)
CREATE TABLE ai_product_insights (
    id             CHAR(36)   PRIMARY KEY,
    location_id    CHAR(36)   NOT NULL,
    product_id     CHAR(36)   NOT NULL,
    insight_type   ENUM('TOP_SELLER','GROWTH_TREND','PROMOTE_CANDIDATE') NOT NULL,
    rank           INT        NOT NULL,
    metric_value   DECIMAL(15,4),                  -- revenue / growth ratio / margin %
    period_days    INT        NOT NULL,             -- 7 or 30
    generated_at   DATETIME   NOT NULL,
    INDEX idx_location_insight (location_id, insight_type, rank)
);

-- OCR: no persistent table — result is returned synchronously to the client for review
```

---

## 13. Non-Functional Considerations

| Concern | Approach |
|---|---|
| **Draft order latency** | Target < 8 s end-to-end. Google STT (primary) processes audio in ~1–2 s; if quota exceeded, Whisper fallback adds ~2–3 s. |
| **Forecasting cold start** | Minimum 14 days of data required. Below threshold, stores `not_enough_data` flag; client shows a friendly message instead of an empty chart. |
| **Anomaly Tier 1 latency** | Rule-based checks run in < 100 ms synchronously on every save. No ML model, no network call, no cold start. |
| **Anomaly Tier 2 cold start** | Requires minimum 7 days of data to produce a meaningful LLM summary. Locations with less data skip the nightly LLM call. |
| **Reorder cold start** | Requires minimum 14 days of sales history. Locations with less data skip reorder suggestions. |
| **OCR latency** | Target < 8 s. GPT-4o Vision processes a 1 MB JPEG in ~3–5 s. Client pre-compresses image before upload to stay within this budget. |
| **OCR accuracy & safety** | OCR results are **always shown as a draft for user review**. Auto-save is never performed. Low-confidence responses include a `confidence: "low"` flag with a review prompt. |
| **AI Service outage** | All 6 features degrade gracefully: scheduled jobs retry on next run; draft order and OCR fall back to manual entry (BizFlow API returns `503` with user-friendly message). |
| **ChromaDB data isolation** | Each location's products stored in a separate ChromaDB **collection** (`location_{uuid}`), preventing cross-location data leakage. |
| **Forecast confidence transparency** | Forecast charts display the ±1σ confidence band (not just a single line) so owners understand predictions are estimates. |
| **Product insights data trust** | All insights are derived exclusively from the location's own historical data — no cross-location data, no LLM knowledge injection, no hallucination risk. |
