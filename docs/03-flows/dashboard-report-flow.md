# Dashboard & Report Flow

> **Module**: Report & Accounting — Dashboard Widgets, Cash Flow & Reports
> Quay về [report-accounting-flow.md](report-accounting-flow.md) (index)

---

## Mục lục

1. [Entity Design](#1-entity-design)
   - [1.1 AccountingSettings](#11-accountingsettings-cấu-hình-kế-toán)
2. [Cash Flow Tracking](#2-cash-flow-tracking)
3. [Dashboard Widgets](#3-dashboard-widgets)
   - [3.1 Tầng 1 — Quick Glance (Summary)](#31-tầng-1--quick-glance-summary)
   - [3.2 Tầng 2 — Charts](#32-tầng-2--charts)
4. [API Endpoints](#4-api-endpoints)

---

## 1. Entity Design

### 1.1 AccountingSettings (Cấu hình kế toán)

Mỗi location có **1 record** cấu hình kế toán duy nhất (1:1 với `BusinessLocations`).

```sql
-- =============================================
-- ACCOUNTING SETTINGS TABLE (Cấu hình per Location)
-- =============================================
CREATE TABLE AccountingSettings (
    AccountingSettingId BIGINT AUTO_INCREMENT PRIMARY KEY,
    BusinessLocationId INT NOT NULL,
    
    -- Năm tài chính
    FiscalYearStart TINYINT NOT NULL DEFAULT 1 
        COMMENT 'Tháng bắt đầu năm tài chính (1-12), mặc định tháng 1',
    
    -- Tiền tệ
    DefaultCurrency VARCHAR(3) NOT NULL DEFAULT 'VND',
    
    -- Timestamps
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    
    -- Indexes & FKs
    CONSTRAINT fk_accsetting_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    UNIQUE INDEX idx_accsetting_location (BusinessLocationId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class AccountingSetting
{
    public long AccountingSettingId { get; set; }
    public int BusinessLocationId { get; set; }
    
    public int FiscalYearStart { get; set; } = 1;
    public string DefaultCurrency { get; set; } = "VND";
    
    public DateTime CreatedAt { get; set; }
    public DateTime? UpdatedAt { get; set; }
    
    // Navigation
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
}
```

> **Ghi chú**: Table này có thể mở rộng sau (thêm logo cho export, tên HKD hiển thị trên sổ, v.v.). Hiện tại giữ minimal.

---

## 2. Cash Flow Tracking

Cash flow **query trực tiếp từ GeneralLedgerEntries** — không cần table riêng.

```sql
-- Tổng hợp dòng tiền trong khoảng thời gian
SELECT
    MoneyChannel,
    SUM(DebitAmount) AS TotalIn,
    SUM(CreditAmount) AS TotalOut,
    SUM(DebitAmount) - SUM(CreditAmount) AS Net
FROM GeneralLedgerEntries
WHERE BusinessLocationId = @locationId
  AND EntryDate BETWEEN @startDate AND @endDate
GROUP BY MoneyChannel;
```

**Kết quả mẫu:**

| Channel | TotalIn     | TotalOut   | Net         |
|---------|-------------|------------|-------------|
| cash    | 450,000,000 | 85,000,000 | 365,000,000 |
| bank    | 120,000,000 | 15,000,000 | 105,000,000 |
| debt    | 50,000,000  | 0          | 50,000,000  |

**Cách đọc:**
- **Tiền THỰC THU** = `cash.Net + bank.Net` = 470,000,000đ
- **Tổng doanh thu** = `cash.In + bank.In + debt.In` = 620,000,000đ (gồm nợ — vì nợ vẫn là doanh thu)
- **Debt tracking**: `debt.TotalIn` = tổng nợ phát sinh, query GL `debt_payment` entries để biết đã thu bao nhiêu

---

## 3. Dashboard Widgets

### 3.1 Tầng 1 — Quick Glance (Summary)

```yaml
GET /api/v1/locations/{locationId}/dashboard/summary?date=2026-03-03
Authorization: Bearer {token}

Response:
{
  "date": "2026-03-03",
  "todayRevenue": 12500000,        # Orders completed today
  "todayOrders": 8,                # Orders count today
  "totalOutstandingDebt": 15000000, # Debtors with negative balance
  "lowStockCount": 5,              # Products below threshold
  "todayCashIn": 8000000,          # GL cash debit today
  "todayBankIn": 3500000,          # GL bank debit today
  "todayCashOut": 2000000,         # GL cash credit today
  "todayBankOut": 0                # GL bank credit today
}
```

**Data sources:**

| Field | Source |
|-------|--------|
| `todayRevenue` | `Orders WHERE Status='completed' AND CompletedAt = @date` |
| `todayOrders` | `COUNT(Orders) same filter` |
| `totalOutstandingDebt` | `Debtors WHERE Balance < 0 (hoặc query GL debt entries)` |
| `lowStockCount` | `Products WHERE CurrentStock < LowStockThreshold` |
| `todayCashIn/BankIn` | `GL WHERE MoneyChannel='cash'/'bank' AND DebitAmount > 0 AND EntryDate = @date` |
| `todayCashOut/BankOut` | `GL WHERE MoneyChannel='cash'/'bank' AND CreditAmount > 0 AND EntryDate = @date` |

### 3.2 Tầng 2 — Charts

#### Revenue Chart (Biểu đồ doanh thu)

```yaml
GET /api/v1/locations/{locationId}/dashboard/revenue-chart?period=7d
Authorization: Bearer {token}

Response:
{
  "period": "7d",
  "data": [
    { "date": "2026-02-25", "revenue": 15000000, "cost": 5000000, "profit": 10000000 },
    { "date": "2026-02-26", "revenue": 12000000, "cost": 3000000, "profit": 9000000 },
    { "date": "2026-02-27", "revenue": 18000000, "cost": 7000000, "profit": 11000000 },
    { "date": "2026-02-28", "revenue": 14000000, "cost": 4000000, "profit": 10000000 },
    { "date": "2026-03-01", "revenue": 20000000, "cost": 6000000, "profit": 14000000 },
    { "date": "2026-03-02", "revenue": 16000000, "cost": 5000000, "profit": 11000000 },
    { "date": "2026-03-03", "revenue": 12500000, "cost": 3500000, "profit": 9000000 }
  ]
}
```

#### Top Products (SP bán chạy)

```yaml
GET /api/v1/locations/{locationId}/dashboard/top-products?period=30d&limit=5
Authorization: Bearer {token}

Response:
{
  "period": "30d",
  "products": [
    { "productId": 10, "productName": "Xi măng Hà Tiên", "totalQuantity": 500, "totalRevenue": 47500000 },
    { "productId": 22, "productName": "Sắt phi 12", "totalQuantity": 200, "totalRevenue": 24000000 },
    { "productId": 5, "productName": "Cát xây dựng", "totalQuantity": 1500, "totalRevenue": 18000000 },
    { "productId": 31, "productName": "Gạch ống", "totalQuantity": 3000, "totalRevenue": 15000000 },
    { "productId": 8, "productName": "Tôn lợp mái", "totalQuantity": 80, "totalRevenue": 12000000 }
  ]
}
```

#### Payment Ratio (Tỷ lệ PTTT)

```yaml
GET /api/v1/locations/{locationId}/dashboard/payment-ratio?period=30d
Authorization: Bearer {token}

Response:
{
  "period": "30d",
  "cash": { "amount": 350000000, "percent": 56.5 },
  "bank": { "amount": 180000000, "percent": 29.0 },
  "debt": { "amount": 90000000, "percent": 14.5 }
}
```

#### Revenue by Business Type (DT theo ngành)

```yaml
GET /api/v1/locations/{locationId}/dashboard/revenue-by-type?period=30d
Authorization: Bearer {token}

Response:
{
  "period": "30d",
  "breakdown": [
    { "businessTypeId": "bt-retail", "name": "Bán lẻ hàng hóa", "revenue": 500000000, "percent": 80.6 },
    { "businessTypeId": "bt-service", "name": "Dịch vụ", "revenue": 120000000, "percent": 19.4 }
  ]
}
```

---

## 4. API Endpoints

### Dashboard

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/v1/locations/{id}/dashboard/summary` | Dashboard tổng quan hôm nay | Owner |
| `GET` | `/api/v1/locations/{id}/dashboard/revenue-chart` | Biểu đồ DT theo ngày | Owner |
| `GET` | `/api/v1/locations/{id}/dashboard/top-products` | Top SP bán chạy | Owner |
| `GET` | `/api/v1/locations/{id}/dashboard/payment-ratio` | Tỷ lệ phương thức thanh toán | Owner |
| `GET` | `/api/v1/locations/{id}/dashboard/revenue-by-type` | DT theo ngành nghề | Owner |

### Reports

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/v1/locations/{id}/reports/cash-flow` | Dòng tiền theo khoảng thời gian | Owner |
| `GET` | `/api/v1/locations/{id}/reports/revenue` | Báo cáo doanh thu theo kỳ | Owner |
| `GET` | `/api/v1/locations/{id}/reports/costs` | Báo cáo chi phí theo kỳ | Owner |

### Accounting Settings

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/v1/locations/{id}/accounting/settings` | Xem cấu hình kế toán | Owner |
| `PUT` | `/api/v1/locations/{id}/accounting/settings` | Cập nhật cấu hình (fiscal year, currency) | Owner |

> **Lưu ý**: Dashboard queries đều read-only, aggregate từ GL/Orders/Costs. Không cần error codes đặc biệt — chỉ sử dụng `NO_PERMISSION` (403) và standard validation errors.
