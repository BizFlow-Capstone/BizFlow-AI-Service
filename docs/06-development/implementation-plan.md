# BizFlow AI Service — Implementation Plan

> **Tác giả:** BA & Solution Architecture Review  
> **Ngày:** 2026-04-04  
> **Trạng thái:** Draft — chờ review và approve trước khi làm

---

## Tổng quan

Plan này được xây dựng sau khi phân tích cross-service giữa `BizFlow-AI-Service` (Python/FastAPI) và `BizFlow-BE-Service` (.NET/ASP.NET Core). Có **3 critical bug chặn toàn bộ AI features**, **1 integration layer hoàn toàn chưa được build**, và một số design issues cần điều chỉnh.

Chia thành **3 sprint**, thực hiện tuần tự:

| Sprint | Tên | Nội dung chính | Repo |
|--------|-----|----------------|------|
| Sprint 1 | Fix Critical Bugs | status string, schema migration, UNIQUE constraints | AI Service |
| Sprint 2 | BE Integration Layer | AI HTTP client, proxy endpoints, vector store hooks | BE Service |
| Sprint 3 | Nightly Jobs + Dashboard | Hangfire jobs, read endpoints, minor fixes | BE + AI |

---

## Sprint 1 — Fix Critical Bugs (AI Service)

**Mục tiêu:** Đảm bảo AI Service có thể chạy đúng với dữ liệu thực trước khi build integration.

---

### Task 1.1 — Sửa `status = 'CONFIRMED'` → `'completed'`

**Vấn đề:** Tất cả SQL query trong 4 service files dùng `status = 'CONFIRMED'`, trong khi BE lưu vào DB giá trị `'completed'` (xem `OrderStatus.cs`). Kết quả: mọi query trả 0 row → mọi AI feature bị skip với lý do "không đủ dữ liệu".

**Files cần sửa:**

| File | Dòng | Sửa |
|------|------|-----|
| `app/services/forecast_service.py` | ~57 | `'CONFIRMED'` → `'completed'` |
| `app/services/reorder_service.py` | ~63 | `'CONFIRMED'` → `'completed'` |
| `app/services/anomaly_service.py` | ~75, ~179 | `'CONFIRMED'` → `'completed'` (2 chỗ) |
| `app/services/product_insights_service.py` | ~54 | `'CONFIRMED'` → `'completed'` |

**Effort:** 30 phút  
**Risk:** Không có — chỉ đổi string literal.

---

### Task 1.2 — Viết lại Alembic migration

**Vấn đề:** Migration hiện tại (`278c5207c508_create_ai_tables.py`) tạo ra schema không khớp với SQL mà service code thực tế dùng.

| Bảng | Migration tạo | Service SQL cần |
|------|---------------|-----------------|
| `ai_revenue_forecasts` | `forecast_revenue` | `predicted_revenue` |
| `ai_anomaly_alerts` | `entity_type, entity_id, message, tier INT, created_at` | `alert_type, severity, tier VARCHAR, reference_date, description, reference_id, is_acknowledged, generated_at` |
| `ai_reorder_suggestions` | `reorder_point, suggested_reorder_qty` | `days_until_stockout, suggested_quantity, avg_daily_sales, urgency` |
| `ai_product_insights` | ✅ Đúng | ✅ Không cần sửa |

**Cách làm:**
1. Nếu DB dev chưa có data quan trọng: drop toàn bộ 4 bảng AI, sửa migration file hiện tại cho đúng, chạy lại.
2. Nếu DB đã có data: tạo migration mới `alembic revision -m "fix_ai_tables_schema"` với `op.drop_table` + `op.create_table` đúng schema.

**Schema đúng cho `ai_revenue_forecasts`:**
```sql
CREATE TABLE ai_revenue_forecasts (
    id VARCHAR(36) PRIMARY KEY,
    location_id VARCHAR(36) NOT NULL,
    forecast_date VARCHAR(10) NOT NULL,       -- 'YYYY-MM-DD'
    predicted_revenue FLOAT NOT NULL,
    lower_bound FLOAT NOT NULL,
    upper_bound FLOAT NOT NULL,
    trend_note TEXT,
    generated_at DATETIME NOT NULL,
    UNIQUE KEY uq_forecast_location_date (location_id, forecast_date),
    INDEX ix_location_id (location_id)
);
```

**Schema đúng cho `ai_anomaly_alerts`:**
```sql
CREATE TABLE ai_anomaly_alerts (
    id VARCHAR(36) PRIMARY KEY,
    location_id VARCHAR(36) NOT NULL,
    alert_type VARCHAR(100) NOT NULL,         -- e.g. 'DATA_QUALITY', 'REVENUE_ANOMALY'
    severity VARCHAR(20) NOT NULL,            -- 'CRITICAL', 'WARNING'
    tier VARCHAR(20) NOT NULL,                -- 'RULE_BASED', 'LLM_PATTERN'
    reference_date DATE NOT NULL,
    description TEXT NOT NULL,
    reference_id VARCHAR(36),                 -- orderId or importId
    is_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    generated_at DATETIME NOT NULL,
    INDEX ix_location_id (location_id),
    INDEX ix_reference_date (reference_date)
);
```

**Schema đúng cho `ai_reorder_suggestions`:**
```sql
CREATE TABLE ai_reorder_suggestions (
    id VARCHAR(36) PRIMARY KEY,
    location_id VARCHAR(36) NOT NULL,
    product_id VARCHAR(36) NOT NULL,
    current_stock FLOAT NOT NULL,
    days_until_stockout INT NOT NULL,
    suggested_quantity FLOAT NOT NULL,
    avg_daily_sales FLOAT NOT NULL,
    urgency VARCHAR(10) NOT NULL,             -- 'HIGH', 'MEDIUM', 'LOW'
    generated_at DATETIME NOT NULL,
    UNIQUE KEY uq_reorder_location_product (location_id, product_id),
    INDEX ix_location_id (location_id)
);
```

**Effort:** 2–3 giờ  
**Risk:** Cần backup DB dev trước khi chạy.

---

### Task 1.3 — Thêm UNIQUE constraints (nếu chưa có từ Task 1.2)

**Vấn đề:** Service dùng `INSERT ... ON DUPLICATE KEY UPDATE` cho `ai_revenue_forecasts` và `ai_reorder_suggestions`, nhưng nếu không có UNIQUE INDEX trên `(location_id, forecast_date)` và `(location_id, product_id)` thì mỗi lần chạy nightly job sẽ INSERT thêm row mới thay vì UPDATE.

Đã được handle trong Task 1.2 schema trên. Nếu làm migration riêng thì cần thêm:

```sql
ALTER TABLE ai_revenue_forecasts
    ADD UNIQUE KEY uq_forecast_location_date (location_id, forecast_date);

ALTER TABLE ai_reorder_suggestions
    ADD UNIQUE KEY uq_reorder_location_product (location_id, product_id);
```

**Effort:** 30 phút (nếu tách riêng khỏi Task 1.2)

---

### Task 1.4 — Giảm temperature trong forecast (minor)

**File:** `app/services/forecast_service.py`

```python
# Trước
answer = await llm.chat(system=..., user=csv_data, temperature=0.7)

# Sau — analytical text generation không cần sáng tạo cao
answer = await llm.chat(system=..., user=csv_data, temperature=0.2)
```

**Effort:** 5 phút  
**Lý do:** `temperature=0.7` phù hợp cho creative writing, không phù hợp cho "đọc số liệu và mô tả xu hướng" — có thể sinh text không phản ánh đúng data.

---

### Checklist Sprint 1

- [ ] Task 1.1 — Sửa `status='CONFIRMED'` (4 files)
- [ ] Task 1.2 — Viết lại migration (backup DB trước)
- [ ] Task 1.3 — Verify UNIQUE constraints tồn tại
- [ ] Task 1.4 — Giảm temperature forecast
- [ ] Test thủ công: gọi `POST /forecast`, `POST /reorder`, `POST /product-insights` với data thực
- [ ] Verify rows được INSERT đúng vào DB

---

## Sprint 2 — BE Integration Layer (BE Service)

**Mục tiêu:** Kết nối BE .NET với AI Service — các luồng user-facing (sync) và vector store sync.

---

### Task 2.1 — Tạo `IAiServiceClient` + `AiServiceHttpClient`

**Vị trí:** `BizFlow.Infrastructure/Services/AiServiceHttpClient.cs`

**Interface (Application layer):**
```csharp
// BizFlow.Application/Interfaces/Services/IAiServiceClient.cs
public interface IAiServiceClient
{
    Task<DraftOrderResultDto> ParseDraftOrderAsync(Stream audioStream, string mimeType, int locationId, CancellationToken ct = default);
    Task<OcrInvoiceResultDto> OcrInvoiceAsync(Stream imageStream, string mimeType, int locationId, CancellationToken ct = default);
    Task<OcrDeliveryNoteResultDto> OcrDeliveryNoteAsync(Stream imageStream, string mimeType, int locationId, CancellationToken ct = default);
    Task CheckAnomalyAsync(int locationId, string recordType, long recordId, CancellationToken ct = default);
    Task TriggerVectorStoreSyncAsync(int locationId, object productData, CancellationToken ct = default);
    Task TriggerVectorStoreDeleteAsync(int locationId, long productId, CancellationToken ct = default);
}
```

**Cấu hình (Settings):**
```json
// appsettings.json
"AiService": {
  "BaseUrl": "http://ai-service:8001",
  "InternalSecret": "dev_internal_secret_change_in_prod",
  "TimeoutSeconds": 30
}
```

**Lưu ý triển khai:**
- Dùng `IHttpClientFactory` — không tạo `HttpClient` mới mỗi request.
- Header `X-Internal-Secret` được add vào mọi request.
- `CheckAnomalyAsync` fire-and-forget — không `await` trong request path (xem Task 2.3).
- Timeout 30s chỉ cho Draft Order/OCR; Anomaly check nên có timeout riêng 5s.

**Effort:** 4–6 giờ

---

### Task 2.2 — Proxy endpoints cho Draft Order & OCR

**Vị trí:** `BizFlow.Api/Controllers/Ai/AiController.cs`

```csharp
[Route("api/my-business/ai")]
public class AiController : ApiController
{
    [HttpPost("draft-order")]
    public async Task<IActionResult> ParseDraftOrder([FromForm] DraftOrderRequest request) { ... }

    [HttpPost("ocr/invoice")]
    public async Task<IActionResult> OcrInvoice([FromForm] OcrRequest request) { ... }

    [HttpPost("ocr/delivery-note")]
    public async Task<IActionResult> OcrDeliveryNote([FromForm] OcrRequest request) { ... }
}
```

**Auth:** Dùng JWT auth chuẩn của BE — controller có `[Authorize]`, sau đó forward có `X-Internal-Secret` khi gọi AI Service (user không thấy secret này).

**Validate location access** trước khi forward — tương tự pattern trong `OrderController`.

**Effort:** 3–4 giờ

---

### Task 2.3 — Hook Anomaly Tier 1 vào `OrderService.CompleteAsync`

**Vấn đề thiết kế quan trọng:** Anomaly check KHÔNG được đặt trong synchronous request path. Nếu AI Service down thì user không tạo được đơn hàng — không chấp nhận được.

**Cách làm đúng — fire-and-forget qua Hangfire:**

```csharp
// OrderService.CompleteAsync — sau SaveChanges()
await _uow.SaveChangesAsync();

// Fire-and-forget: không block, không throw nếu AI Service down
BackgroundJob.Enqueue<IAiBackgroundJobService>(x =>
    x.CheckOrderAnomalyAsync(locationId, order.OrderId));
```

```csharp
// BizFlow.Infrastructure/Jobs/AiAnomalyCheckJob.cs
public class AiBackgroundJobService : IAiBackgroundJobService
{
    public async Task CheckOrderAnomalyAsync(int locationId, long orderId)
    {
        // Nếu AI Service không available → log warning, không throw
        // Nếu có CRITICAL alert → gọi IFirebaseNotificationService để push FCM
    }
}
```

**Tương tự cho Import:** Hook vào `ImportService.ConfirmImportAsync`.

**Effort:** 3–4 giờ

---

### Task 2.4 — Vector Store Sync trong `ProductService`

Cần thêm 3 call sau mỗi `SaveChanges()` tương ứng:

```csharp
// ProductService.CreateAsync — sau SaveChanges()
_ = _aiServiceClient.TriggerVectorStoreSyncAsync(locationId, productData);  // fire-and-forget

// ProductService.UpdateAsync — sau SaveChanges()
_ = _aiServiceClient.TriggerVectorStoreSyncAsync(locationId, productData);

// ProductService.DeleteAsync — sau SaveChanges()
_ = _aiServiceClient.TriggerVectorStoreDeleteAsync(locationId, product.ProductId);
```

**Lưu ý:** Fire-and-forget (không `await`) — vector store sync delay vài giây là chấp nhận được. Product vẫn có thể tìm bằng tên, chỉ semantic search chưa cập nhật.

**Effort:** 2 giờ

---

### Checklist Sprint 2

- [ ] Task 2.1 — `IAiServiceClient` + implementation
- [ ] Task 2.2 — `AiController` proxy endpoints (Draft Order + OCR)
- [ ] Task 2.3 — Hook Anomaly Tier 1 vào CompleteAsync + ConfirmImportAsync
- [ ] Task 2.4 — Vector store sync trong ProductService
- [ ] Test: tạo product → query `/draft-order` xem có tìm thấy product không
- [ ] Test: complete order → verify anomaly alert được tạo trong DB

---

## Sprint 3 — Nightly Jobs + Dashboard Read Endpoints

**Mục tiêu:** Hoàn thiện scheduled batch jobs và các endpoint để FE đọc kết quả AI.

---

### Task 3.1 — Hangfire Nightly Jobs

**Vị trí:** `BizFlow.Infrastructure/Jobs/`

Cần tạo 4 job class:

| Job | Cron | AI Endpoint | Ghi chú |
|-----|------|-------------|---------|
| `AiForecastJob` | `0 1 * * *` (01:00) | `POST /forecast` | Fetch all active location IDs trước |
| `AiAnomalyPatternJob` | `0 2 * * *` (02:00) | `POST /anomaly` | |
| `AiReorderJob` | `0 3 * * *` (03:00) | `POST /reorder` | Push FCM nếu có HIGH urgency |
| `AiProductInsightsJob` | `30 3 * * *` (03:30) | `POST /product-insights` | |

**Pattern chung:**
```csharp
public class AiForecastJob
{
    public async Task RunAsync()
    {
        var locationIds = await _uow.BusinessLocations.GetAllActiveIdsAsync();
        await _aiServiceClient.TriggerForecastAsync(locationIds);
    }
}
```

**Đăng ký trong `HangfireBackgroundJobScheduler.cs`** (pattern tương tự các job hiện có như `SubscriptionExpiryCheckJob`).

**Effort:** 4–5 giờ

---

### Task 3.2 — Read Endpoints cho Dashboard

**Vị trí:** Thêm vào `AiController.cs` (tạo từ Task 2.2)

```
GET  /api/my-business/ai/forecast?locationId={id}
GET  /api/my-business/ai/reorder?locationId={id}
GET  /api/my-business/ai/insights?locationId={id}
GET  /api/my-business/ai/anomalies?locationId={id}&acknowledged=false
POST /api/my-business/ai/anomalies/{id}/acknowledge
```

**Implement:** Query trực tiếp từ MySQL (bảng `ai_*`) qua `IUnitOfWork` — không cần gọi AI Service, chỉ đọc data đã pre-computed.

**Effort:** 4–5 giờ

---

### Task 3.3 — FCM Push cho CRITICAL Alerts và HIGH Reorder

Hiện tại `IFirebaseNotificationService` đã tồn tại trong BE (`FirebaseNotificationService.cs`). Cần wire vào 2 chỗ:

1. Khi `AiBackgroundJobService.CheckOrderAnomalyAsync` nhận về CRITICAL alert (từ Task 2.3).
2. Khi `AiReorderJob` hoàn thành và có sản phẩm với urgency = HIGH (từ Task 3.1).

**Effort:** 2 giờ

---

### Task 3.4 — Minor AI Service Fixes (từ analysis)

| Fix | File | Chi tiết |
|-----|------|---------|
| Thêm `matched: bool` vào `DraftOrderItem` | `services/draft_order_service.py` | `matched = product_id is not None` — no LLM call |
| Xóa Anomaly Rule #4 (redundant) | `services/anomaly_service.py` | Rule này không bao giờ fire vì BE đã block trước |

**Effort:** 1 giờ

---

### Checklist Sprint 3

- [ ] Task 3.1 — 4 Hangfire nightly jobs
- [ ] Task 3.2 — Dashboard read endpoints
- [ ] Task 3.3 — FCM push cho CRITICAL + HIGH urgency
- [ ] Task 3.4 — Minor AI Service fixes
- [ ] End-to-end test: chạy nightly jobs thủ công, verify data trong DB, verify FE có thể đọc

---

## Dependency & Thứ Tự Thực Hiện

```
Sprint 1 (AI bugs)
    └── PHẢI xong trước Sprint 2 và Sprint 3
        (nếu không, scheduled jobs chạy cũng không có data)

Sprint 2 (BE integration)
    ├── Task 2.1 (AI client) — PHẢI xong trước 2.2, 2.3, 2.4
    ├── Task 2.2 (proxy) — độc lập sau 2.1
    ├── Task 2.3 (anomaly hook) — độc lập sau 2.1
    └── Task 2.4 (vector sync) — độc lập sau 2.1

Sprint 3 (jobs + dashboard)
    ├── Task 3.1 (Hangfire) — cần Sprint 1 + 2.1 xong
    ├── Task 3.2 (read endpoints) — cần Sprint 1 xong (để có data)
    ├── Task 3.3 (FCM) — cần 2.3 và 3.1 xong
    └── Task 3.4 (AI fixes) — độc lập
```

---

## Các Quyết Định Giữ Nguyên (Không Thay Đổi)

Những design này đã đúng, không cần can thiệp:

| Design | Lý do giữ |
|--------|-----------|
| EMA thay vì Prophet | Đủ cho HKD, nhẹ, explainable |
| Pre-computed batch results | Dashboard instant response, đúng UX |
| Two-tier anomaly | Tier 1 zero-latency, Tier 2 LLM không block user |
| OCR never auto-saves | Safety UX cho HKD |
| ChromaDB per-location isolation | Multi-tenant data safety |
| `gpt-4o-mini` cho extraction/explanation | Cost-effective, đủ chất lượng |

---

## Rủi Ro & Giảm Thiểu

| Rủi ro | Khả năng xảy ra | Giảm thiểu |
|--------|-----------------|------------|
| AI Service down → user không tạo được đơn | Cao nếu dùng sync | Dùng fire-and-forget (Task 2.3) |
| LLM API rate limit vào giờ nightly | Thấp (1 location = 4 call/ngày) | Stagger job times (01:00, 02:00, 03:00, 03:30) — đã có |
| ChromaDB corrupt sau restart container | Thấp | `CHROMA_PERSIST_DIR` mount ra volume Docker |
| Schema migration fail trên production | Trung bình | Backup DB trước, test trên dev env trước |
| Reorder formula overfit với HKD mới (< 14 ngày data) | Cao ban đầu | Skip + ghi `not_enough_data` sentinel — đã xử lý |

---

*Kết thúc plan. Xem lại và điều chỉnh effort estimate trước khi assign task.*
