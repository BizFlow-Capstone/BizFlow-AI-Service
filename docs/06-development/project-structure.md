# BizFlow AI Service — Cấu Trúc Dự Án

> **Đối tượng:** Developer muốn hiểu, bảo trì, hoặc mở rộng service này.  
> **Cập nhật lần cuối:** xem git log

---

## 1. Tổng Quan

**BizFlow AI Service** là một internal Python microservice phục vụ các tính năng AI cho nền tảng BizFlow. Service giao tiếp với backend .NET qua HTTP (container-to-container), bảo vệ bởi header bí mật `X-Internal-Secret`. Service **không** expose ra internet.

```
BizFlow Backend (.NET)  ──HTTP──►  BizFlow AI Service (FastAPI)
                                        │
                         ┌──────────────┼────────────────┐
                         ▼              ▼                 ▼
                    MySQL DB       OpenAI API      Google Cloud STT
                    (SQLAlchemy)   (GPT-4o/mini,   (vi-VN, sync)
                                    Whisper-1)
                                        │
                                   ChromaDB (local)
                                   multilingual-e5-large
```

---

## 2. Sơ Đồ Thư Mục

```
BizFlow-AI-Service/
│
├── main.py                   # FastAPI app, lifespan, router mount
├── requirements.txt          # Python dependencies (pinned versions)
├── Dockerfile                # Multi-stage build (builder + runtime)
├── .env.dev                  # Dev environment variables
│
├── core/                     # Framework-level concerns
│   ├── config.py             #   pydantic Settings — đọc toàn bộ env vars
│   ├── dependencies.py       #   FastAPI dependency: xác thực internal secret
│   └── exceptions.py         #   Domain exceptions + HTTP helpers
│
├── db/                       # Database access
│   └── mysql_client.py       #   SQLAlchemy engine, fetch_all(), execute_write()
│
├── ml/                       # AI/ML primitives (không phụ thuộc lẫn nhau)
│   ├── stt.py                #   Speech-to-Text (Google STT primary, Whisper fallback)
│   ├── llm.py                #   LLM wrappers (chat / vision)
│   └── vector_store.py       #   ChromaDB + sentence-transformer embedding
│
├── routers/                  # HTTP layer — nhận request, gọi service, trả response
│   ├── draft_order.py        #   POST /draft-order
│   ├── forecast.py           #   POST /forecast
│   ├── anomaly.py            #   POST /anomaly/check-record, POST /anomaly
│   ├── reorder.py            #   POST /reorder
│   ├── ocr.py                #   POST /ocr/invoice, POST /ocr/delivery-note
│   ├── product_insights.py   #   POST /product-insights
│   └── vector_store.py       #   POST /vector-store/sync, POST /vector-store/delete
│
├── services/                 # Business logic — mọi tính toán xảy ra ở đây
│   ├── draft_order_service.py
│   ├── forecast_service.py
│   ├── anomaly_service.py
│   ├── reorder_service.py
│   ├── ocr_service.py
│   └── product_insights_service.py
│
└── docs/                     # Tài liệu (bạn đang đọc ở đây)
    └── 06-development/
        └── project-structure.md
```

---

## 3. Chi Tiết Từng Thành Phần

### 3.1 `main.py` — Entry Point

| Thành phần | Mục đích |
|---|---|
| `lifespan(app)` | Gọi `init_vector_store()` lúc startup để warm-up sentence-transformer |
| `app.include_router(...)` | Gắn 7 router với prefix và tag tương ứng |
| `GET /health` | Health check không có auth — dùng cho Docker healthcheck |

**Quy tắc mở rộng:** Thêm tính năng mới = tạo `routers/new_feature.py` + `services/new_feature_service.py`, sau đó `include_router` tại đây.

---

### 3.2 `core/config.py` — Cấu Hình

Sử dụng `pydantic-settings` để đọc toàn bộ biến môi trường có type-safety.

```python
from core.config import settings
settings.openai_api_key   # str
settings.ai_db_url        # str (SQLAlchemy URL)
settings.internal_api_secret  # str
settings.chroma_persist_dir   # str
```

`extra="ignore"` cho phép file `.env.dev` chứa các biến .NET không liên quan mà không gây lỗi.

---

### 3.3 `core/dependencies.py` — Xác Thực

```python
# Áp dụng cho router:
router = APIRouter(dependencies=[Depends(verify_internal_secret)])
```

Dependency `verify_internal_secret` đọc header `X-Internal-Secret` từ request, so sánh với `settings.internal_api_secret`. Trả 401 nếu sai.

---

### 3.4 `core/exceptions.py` — Domain Exceptions

| Exception | Khi nào dùng |
|---|---|
| `AIServiceError` | Base class cho mọi lỗi AI |
| `InsufficientDataError` | Không đủ lịch sử để tính toán (< 14 ngày) |
| `STTError` | Cả Google STT lẫn Whisper đều thất bại |
| `LLMError` | OpenAI API trả lỗi hoặc JSON parse fail |
| `OCRParseError` | GPT-4o Vision không trả JSON hợp lệ |
| `VectorStoreError` | ChromaDB hoặc embedding thất bại |
| `raise_503(msg)` | Helper — ném HTTPException 503 |
| `raise_422(msg)` | Helper — ném HTTPException 422 |

---

### 3.5 `db/mysql_client.py` — Database

Dùng SQLAlchemy Core (không dùng ORM). Kết nối pool tái sử dụng giữa các request.

```python
rows: list[dict] = fetch_all("SELECT ... WHERE id = :id", {"id": 123})
affected: int    = execute_write("UPDATE ...", {...})
```

`fetch_all` trả `list[dict]` (column name là key) — phù hợp để đưa thẳng vào `pd.DataFrame(rows)`.

---

### 3.6 `ml/stt.py` — Speech-to-Text

```
audio bytes ──► _transcribe_google()  ──[OK]──► transcript (str)
                        │
                     [FAIL]
                        ▼
               _transcribe_whisper()  ──[OK]──► transcript (str)
                        │
                     [FAIL]
                        ▼
                  raise STTError
```

- **Google STT** (`vi-VN`, sync) — miễn phí 60 phút/tháng, độ trễ thấp
- **Whisper-1** — fallback, tốn token cost nhưng chất lượng cao hơn trên noise
- Input: raw audio bytes + MIME type (`audio/wav`, `audio/webm`, …)

---

### 3.7 `ml/llm.py` — LLM Wrappers

```python
# Text chat (GPT-4o-mini)
answer: str = await chat(system="...", user="...", temperature=0.2)

# Vision / OCR (GPT-4o)
answer: str = await vision(system="...", user_text="...", image_bytes=b"...", image_mime="image/jpeg")
```

- `chat()` hỗ trợ `response_format={"type": "json_object"}` cho JSON mode
- `vision()` encode ảnh sang base64, dùng `detail="high"` để đọc văn bản nhỏ

---

### 3.8 `ml/vector_store.py` — Semantic Search

| Hàm | Mục đích |
|---|---|
| `init_vector_store()` | Load ChromaDB PersistentClient + sentence-transformer (gọi 1 lần lúc startup) |
| `sync_product(location_id, product_dict)` | Upsert sản phẩm vào collection của location |
| `delete_product(location_id, product_id)` | Xóa sản phẩm khỏi collection |
| `query_products(location_id, query_text, top_k=3)` | Semantic search, trả top-k sản phẩm |

**Data isolation:** Mỗi `location_id` có một ChromaDB collection riêng (`location_{uuid}`). Không có nguy cơ dữ liệu chéo giữa các cửa hàng.

**Embedding model:** `intfloat/multilingual-e5-large` — hỗ trợ tiếng Việt, 560 MB, cache tại `TRANSFORMERS_CACHE`.

---

## 4. Tính Năng Chi Tiết

### 4.1 Draft Order (Đặt Hàng Bằng Giọng Nói)

**Endpoint:** `POST /draft-order`  
**Input:** multipart form — `audio` file + `location_id`

**Pipeline:**
```
Audio ──► STT (Google/Whisper)
       ──► transcript (tiếng Việt)
       ──► query_products(top_k=5) — RAG từ ChromaDB
       ──► GPT-4o-mini với context sản phẩm
       ──► JSON parse ──► DraftOrderResult
```

**Service:** `services/draft_order_service.py`  
**Model trả về:** `DraftOrderResult` chứa list `DraftOrderItem` + `confidence_score`

---

### 4.2 Revenue Forecast (Dự Báo Doanh Thu)

**Endpoint:** `POST /forecast`  
**Input:** `{ "location_ids": ["uuid1", "uuid2"] }`

**Thuật toán:**
- SELECT doanh thu thực tế 90 ngày từ MySQL
- Pandas EMA với `span=7` để làm mượt chuỗi
- Dự báo 7 ngày tới = EMA kéo dài
- Confidence band = ±1σ (sigma từ 14 ngày residuals gần nhất)
- GPT-4o-mini sinh `trend_note` 1 câu bằng tiếng Việt

**Ghi vào DB:** `ai_revenue_forecasts` (UPSERT theo `location_id + forecast_date`)  
**Điều kiện tối thiểu:** Cần ≥ 14 ngày dữ liệu; nếu thiếu → ghi sentinel `not_enough_data`

---

### 4.3 Anomaly Detection (Phát Hiện Bất Thường)

**Hai tầng (two-tier):**

| Tầng | Endpoint | Khi nào gọi | Phương pháp |
|---|---|---|---|
| Tier 1 | `POST /anomaly/check-record` | Realtime khi tạo đơn hàng | 5 luật cứng (hard rules) |
| Tier 2 | `POST /anomaly` | Nightly batch (cron job) | LLM phân tích pattern 7 ngày |

**Tier 1 rules (đồng bộ, < 5ms):**
- Đơn hàng có sản phẩm giá = 0
- Số lượng âm
- Đơn giá lệch quá 70% hoặc gấp 3× so với giá catalog
- Đơn có công nợ nhưng không có `DebtorId` (table `Debtors`)

**Ghi vào DB:** `ai_anomaly_alerts` với `tier` = 1 hoặc 2

---

### 4.4 Reorder Suggestion (Gợi Ý Nhập Hàng)

**Endpoint:** `POST /reorder`  
**Input:** `{ "location_ids": ["uuid1"] }`

**Công thức:**
$$\text{Reorder Point} = \bar{d} \times L + Z \times \sigma_d \times \sqrt{L}$$

- $\bar{d}$ = trung bình bán hàng 14 ngày (Pandas rolling mean)
- $\sigma_d$ = độ lệch chuẩn 14 ngày (Pandas rolling std)
- $L$ = lead time = 3 ngày (default)
- $Z$ = 1.65 (service level 95%)

Vì sao lại là công thức này, chi tiết liên hệ **Thienlm30**

**Ghi vào DB:** `ai_reorder_suggestions` (UPSERT)  
**Điều kiện tối thiểu:** Sản phẩm cần ≥ 14 ngày bán hàng

---

### 4.5 OCR Hóa Đơn

**Endpoints:**
- `POST /ocr/invoice` — Hóa đơn bán hàng
- `POST /ocr/delivery-note` — Phiếu nhập hàng

**Input:** multipart form — `image` file + `location_id`  
**Công nghệ:** GPT-4o Vision (`detail="high"`)

**Output mẫu (`InvoiceResult`):**
```json
{
  "e-invoice_id": "01ABC2345"
  "supplier": "Công ty TNHH ABC",
  "invoice_date": "2025-01-15",
  "items": [
    { "name": "Nước ngọt Pepsi 1.5L", "qty": 24, "unit_price": 15000 }
  ],
  "total_amount": 360000,
  "confidence": "high"
}
```

Confidence = `"low"` khi JSON parse fail (trả partial data thay vì throw lỗi).

---

### 4.6 Product Insights (Phân Tích Sản Phẩm)

**Endpoint:** `POST /product-insights`  
**Input:** `{ "location_ids": ["1"] }`

**Ba loại insight:**

| Loại | Ý nghĩa | Thuật toán |
|---|---|---|
| `TOP_SELLER` | Sản phẩm bán chạy nhất 7 ngày và 30 ngày | SQL SUM, GROUP BY, TOP 10 |
| `GROWTH_TREND` | Sản phẩm đang tăng tốc bán | Velocity_7d / Velocity_30d ≥ 1.5 |
| `PROMOTE_CANDIDATE` | Sản phẩm nên khuyến mãi để giải phóng tồn kho | Margin ≥ avg AND Stock ≥ avg |

**Ghi vào DB:** `ai_product_insights` (DELETE rồi INSERT toàn bộ theo location)

---

### 4.7 Vector Store Sync

**Endpoints:**
- `POST /vector-store/sync` — Đồng bộ thông tin 1 sản phẩm vào ChromaDB
- `POST /vector-store/delete` — Xóa sản phẩm khỏi ChromaDB

Backend .NET gọi 2 endpoint này mỗi khi sản phẩm được tạo/sửa/xóa, đảm bảo vector store luôn đồng bộ với DB.

---

## 5. Biến Môi Trường

File: `.env.dev` (dev) / cấu hình container trong production

| Biến | Ý nghĩa | Ví dụ |
|---|---|---|
| `AI_DB_URL` | SQLAlchemy URL kết nối MySQL | `mysql+pymysql://admin:admin@localhost:3307/bizflow_db` |
| `OPENAI_API_KEY` | OpenAI API key | `sk-...` |
| `GOOGLE_APPLICATION_CREDENTIALS` | Đường dẫn tới Service Account JSON của Google Cloud | `/app/gcp-key.json` |
| `INTERNAL_API_SECRET` | Secret chia sẻ với backend .NET (header `X-Internal-Secret`) | `dev_internal_secret_change_in_prod` |
| `CHROMA_PERSIST_DIR` | Thư mục lưu ChromaDB persistent data | `./chroma_data` |

---

## 6. Cách Chạy Cục Bộ

```bash
# 1. Kích hoạt virtual environment
.venv\Scripts\activate           # Windows
source .venv/bin/activate        # Linux/macOS

# 2. Cài dependencies
pip install -r requirements.txt

# 3. Chạy dev server (hot-reload)
uvicorn main:app --reload --env-file .env.dev --port 8001

# 4. Kiểm tra
curl http://localhost:8001/health
# → {"status": "ok", "service": "bizflow-ai"}
```

**Lưu ý:** Lần chạy đầu tiên sẽ download model `multilingual-e5-large` (~560 MB) vào `TRANSFORMERS_CACHE`.

---

## 7. Cách Chạy Bằng Docker

```bash
# Build
docker build -t bizflow-ai-service .

# Run
docker run -p 8001:8001 \
  -e AI_DB_URL="mysql+pymysql://admin:admin@host.docker.internal:3307/bizflow_db" \
  -e OPENAI_API_KEY="sk-..." \
  -e GOOGLE_APPLICATION_CREDENTIALS="/app/gcp-key.json" \
  -e INTERNAL_API_SECRET="your_secret" \
  -e CHROMA_PERSIST_DIR="/app/chroma_data" \
  -v $(pwd)/gcp-key.json:/app/gcp-key.json \
  -v $(pwd)/chroma_data:/app/chroma_data \
  bizflow-ai-service
```

---

## 8. Thêm Tính Năng Mới

Ví dụ thêm tính năng **Customer Churn Prediction**:

1. **Tạo service:** `services/churn_service.py`
   - Nhận `location_id`, query data từ `fetch_all()`
   - Tính toán bằng Pandas
   - Ghi kết quả vào DB bằng `execute_write()`
   - Trả Pydantic model

2. **Tạo router:** `routers/churn.py`
   ```python
   router = APIRouter(dependencies=[Depends(verify_internal_secret)])
   
   @router.post("", response_model=ChurnResponse)
   async def run_churn(req: ChurnRequest):
       return await churn_service.run(req.location_id)
   ```

3. **Đăng ký trong `main.py`:**
   ```python
   from routers import churn
   app.include_router(churn.router, prefix="/churn", tags=["Churn"])
   ```

4. **Thêm exception type** vào `core/exceptions.py` nếu cần lỗi đặc thù.

---

## 9. Bảng DB Được Ghi Bởi Service

| Bảng | Ghi bởi service | Mục đích |
|---|---|---|
| ai_revenue_forecasts | forecast_service | Dự báo doanh thu 7 ngày |
| ai_anomaly_alerts | anomaly_service | Cảnh báo bất thường Tier 1 + 2 |
| ai_reorder_suggestions | reorder_service | Gợi ý điểm đặt hàng lại |
| ai_product_insights | product_insights_service | TOP_SELLER, GROWTH_TREND, PROMOTE_CANDIDATE |

Các bảng AI được quản lý migration bởi chính AI Service (Alembic), không đi qua cơ chế migration của backend .NET.

---

## 10. Migration Policy (Tách Riêng Backend và AI)

### 10.1 Ownership Rõ Ràng

- Backend .NET sở hữu toàn bộ schema nghiệp vụ chính và migration SQL theo cơ chế __MigrationHistory.
- AI Service chỉ sở hữu schema các bảng có prefix ai_ và migration bằng Alembic.
- Không migration chéo ownership:
- Backend không tạo/sửa/xóa bảng ai_.
- AI không tạo/sửa/xóa bảng nghiệp vụ của backend.

### 10.2 Quy Trình Migration Cho AI Service

1. Thay đổi schema ở model của AI.
2. Tạo revision Alembic mới.
3. Review migration file, đảm bảo chỉ có thay đổi trên bảng ai_.
4. Chạy upgrade trên môi trường dev/staging.
5. Smoke test các endpoint AI liên quan.
6. Triển khai production: chạy migration trước khi bật traffic đầy đủ cho AI version mới.

Các lệnh thường dùng:

- Tạo revision:
  alembic revision -m "20260404_add_field_x_to_ai_table"

- Nâng schema lên mới nhất:
  alembic upgrade head

- Xem revision hiện tại:
  alembic current

- Rollback 1 bước:
  alembic downgrade -1

### 10.3 Quy Tắc Đặt Tên

- Bảng AI luôn bắt đầu bằng ai_.
- Tên revision message nên theo dạng:
  yyyymmdd_action_object
  Ví dụ: 20260404_add_urgency_to_reorder_suggestions
- Tên database:
- Nếu BE và AI cùng dùng chung schema vật lý: dùng chung bizflow_db là hợp lý.
- Nếu nhiều môi trường cùng một MySQL instance: tách tên theo môi trường (bizflow_db_dev, bizflow_db_stg, bizflow_db_prod).
- Nếu mỗi môi trường là một DB instance riêng: có thể giữ cùng tên bizflow_db.

### 10.4 Biến Môi Trường Bắt Buộc Cho AI Migration

- AI Service đọc kết nối DB từ AI_DB_URL.
- AI migration không đọc DB_CONNECTION_STRING.
- Trước khi chạy Alembic trong CI/CD, bắt buộc set AI_DB_URL đúng môi trường mục tiêu.

---

## 11. Checklist CI/CD Cho Migration BE + AI

### 11.1 Pre-flight Chung (Bắt Buộc Trước Mọi Release Có Đụng Schema)

1. Xác nhận có backup/snapshot DB trước migration.
2. Xác nhận biến môi trường đúng môi trường deploy:
- Backend dùng DB_CONNECTION_STRING.
- AI dùng AI_DB_URL.
3. Xác nhận ownership:
- Migration backend không chứa thay đổi bảng ai_.
- Migration AI không chứa thay đổi bảng backend.
4. Thông báo lịch triển khai và phương án rollback.

### 11.2 Scenario A: Chỉ Backend Đổi Schema

Khi dùng:
- Có thay đổi migration SQL của backend.
- Không có thay đổi migration Alembic của AI.

Thứ tự chạy:
1. Backup DB.
2. Apply migration backend.
3. Deploy backend.
4. Smoke test endpoint backend.
5. Không chạy migration AI.

### 11.3 Scenario B: Chỉ AI Đổi Schema

Khi dùng:
- Có thay đổi model/migration Alembic của AI.
- Không có migration mới của backend.

Thứ tự chạy:
1. Backup DB.
2. Set AI_DB_URL của môi trường đích.
3. Chạy alembic upgrade head.
4. Deploy AI Service.
5. Smoke test health và các endpoint AI chính.

### 11.4 Scenario C: Cả Backend và AI Cùng Đổi Schema

Khi dùng:
- Release có cả migration backend và migration AI.

Thứ tự chuẩn:
1. Backup DB.
2. Apply migration backend trước.
3. Apply migration AI sau.
4. Deploy backend.
5. Deploy AI.
6. Chạy smoke test end-to-end:
- Backend gọi được AI.
- Các job forecast/anomaly/reorder/product-insights chạy bình thường.

### 11.5 Rollback Checklist

1. Nếu lỗi ở migration backend:
- Dừng rollout.
- Rollback theo runbook backend hoặc restore snapshot.
2. Nếu lỗi ở migration AI:
- Chạy alembic downgrade về revision trước đó hoặc restore snapshot.
3. Sau rollback:
- Chạy lại smoke test backend + AI trước khi mở traffic đầy đủ.

### 11.6 Release Gate (Pass/Fail)

- PASS khi:
- Migration chạy thành công.
- App khởi động ổn định.
- Smoke test chính đều pass.
- FAIL khi:
- Migration fail hoặc partial apply.
- App lỗi kết nối DB sau deploy.
- Endpoint trọng yếu lỗi sau migration.