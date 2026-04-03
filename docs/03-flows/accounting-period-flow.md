# Accounting Period Flow

> **Module**: Report & Accounting — Period Lifecycle
> Quay về [report-accounting-flow.md](report-accounting-flow.md) (index)

---

## Mục lục

1. [Entity Design](#1-entity-design)
   - [1.1 AccountingPeriods](#11-accountingperiods-kỳ-kế-toán)
   - [1.2 AccountingPeriodAuditLogs](#12-accountingperiodauditlogs-lịch-sử-thay-đổi)
2. [Period Lifecycle](#2-period-lifecycle)
   - [2.1 Create Period](#21-create-period)
   - [2.2 Finalize Period](#22-finalize-period)
   - [2.3 Reopen Period](#23-reopen-period)
3. [Business Rules](#3-business-rules)
4. [API Endpoints](#4-api-endpoints)
5. [Error Codes](#5-error-codes)

---

## 1. Entity Design

### 1.1 AccountingPeriods (Kỳ kế toán)

```sql
-- =============================================
-- ACCOUNTING PERIODS TABLE (Kỳ kế toán)
-- =============================================
CREATE TABLE AccountingPeriods (
    PeriodId BIGINT AUTO_INCREMENT PRIMARY KEY,
    BusinessLocationId INT NOT NULL,
    
    -- Period identity
    PeriodType VARCHAR(10) NOT NULL COMMENT 'quarter | year',
    Year SMALLINT NOT NULL,
    Quarter TINYINT DEFAULT NULL COMMENT '1-4 cho quarterly, NULL cho annual',
    StartDate DATE NOT NULL,
    EndDate DATE NOT NULL,
    
    -- ═══ OPENING BALANCE (số dư đầu kỳ cho S2e) ═══
    OpeningCashBalance DECIMAL(15,2) DEFAULT NULL 
        COMMENT 'Số dư tiền mặt đầu kỳ. Kỳ đầu tiên: Owner nhập. Kỳ sau: auto carry từ closing kỳ trước.',
    OpeningBankBalance DECIMAL(15,2) DEFAULT NULL 
        COMMENT 'Số dư ngân hàng đầu kỳ. Kỳ đầu tiên: Owner nhập. Kỳ sau: auto carry từ closing kỳ trước.',
    
    -- ═══ LIFECYCLE STATUS ═══
    Status VARCHAR(20) NOT NULL DEFAULT 'open',
    -- 'open':       Đang hoạt động, data thay đổi realtime
    -- 'finalized':  Owner đã chốt kỳ, sổ đã xuất chính thức
    -- 'reopened':   Mở lại sau finalize (cần lý do, audit log)
    
    -- ═══ FINALIZATION ═══
    FinalizedAt DATETIME DEFAULT NULL,
    FinalizedByUserId CHAR(36) DEFAULT NULL,
    
    -- Timestamps
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    
    -- Indexes & FKs
    CONSTRAINT fk_period_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    UNIQUE INDEX idx_period_unique (BusinessLocationId, PeriodType, Year, Quarter),
    INDEX idx_period_status (Status),
    INDEX idx_period_year (Year)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class AccountingPeriod
{
    public long PeriodId { get; set; }
    public int BusinessLocationId { get; set; }
    
    // Identity
    public string PeriodType { get; set; } = null!;
    public short Year { get; set; }
    public int? Quarter { get; set; }
    public DateOnly StartDate { get; set; }
    public DateOnly EndDate { get; set; }
    
    // Opening balance (S2e)
    public decimal? OpeningCashBalance { get; set; }
    public decimal? OpeningBankBalance { get; set; }
    
    // Status
    public string Status { get; set; } = "open";
    
    // Finalization
    public DateTime? FinalizedAt { get; set; }
    public Guid? FinalizedByUserId { get; set; }
    
    // Audit
    public DateTime CreatedAt { get; set; }
    public DateTime? UpdatedAt { get; set; }
    
    // Navigation
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual ICollection<AccountingBook> AccountingBooks { get; set; } = new List<AccountingBook>();
    public virtual ICollection<AccountingPeriodAuditLog> AuditLogs { get; set; } = new List<AccountingPeriodAuditLog>();
    public virtual ICollection<AccountingExport> Exports { get; set; } = new List<AccountingExport>();
}

public static class PeriodTypes
{
    public const string Quarter = "quarter";
    public const string Year = "year";
}

public static class PeriodStatuses
{
    public const string Open = "open";
    public const string Finalized = "finalized";
    public const string Reopened = "reopened";
}
```

**Lifecycle giải thích:**

```markdown
OPEN ─────────────────────────────────────────────────► FINALIZED
 │  Kỳ đang hoạt động                                  │  Owner chốt kỳ
 │  → GL entries được tạo tự động                      │  → Không block tạo
 │  → Owner tạo/xem AccountingBooks bất kỳ lúc nào     │     GL entries mới
 │  → Owner preview sổ, so sánh nhóm                   │  → Đánh dấu sổ đã
 │  → Chưa chốt → chưa có gì ràng buộc                 │     chính thức
 │                                                     │
 │◄────────────────────────────────────────────────────┘
                        REOPENED
              Mở lại để sửa (bắt buộc có lý do)
              → Audit log ghi nhận
              → Có thể finalize lại sau
```

> **Lưu ý**: `finalized` không block GL entries mới (vì giao dịch vẫn xảy ra). Nó chỉ đánh dấu rằng Owner đã chốt kỳ này và xuất sổ chính thức. Nếu sau đó có thay đổi → book live tự cập nhật → Owner cần export lại nếu muốn bản mới.

### 1.2 AccountingPeriodAuditLogs (Lịch sử thay đổi)

```sql
-- =============================================
-- ACCOUNTING PERIOD AUDIT LOGS TABLE
-- =============================================
CREATE TABLE AccountingPeriodAuditLogs (
    LogId BIGINT AUTO_INCREMENT PRIMARY KEY,
    PeriodId BIGINT NOT NULL,
    
    -- What changed
    Action VARCHAR(50) NOT NULL,
    -- 'period_created'          Tạo kỳ mới
    -- 'period_finalized'        Chốt kỳ
    -- 'period_reopened'         Mở lại kỳ
    -- 'book_created'            Tạo sổ mới
    -- 'book_exported'           Xuất sổ
    -- 'group_suggestion'        Rule Engine gợi ý (system log)
    
    -- Change details
    OldValue JSON DEFAULT NULL COMMENT 'Giá trị trước thay đổi',
    NewValue JSON DEFAULT NULL COMMENT 'Giá trị sau thay đổi',
    Reason TEXT DEFAULT NULL COMMENT 'Lý do (bắt buộc cho reopen)',
    
    -- Audit
    CreatedByUserId CHAR(36) NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes & FKs
    CONSTRAINT fk_audit_period FOREIGN KEY (PeriodId) 
        REFERENCES AccountingPeriods(PeriodId),
    INDEX idx_audit_period (PeriodId),
    INDEX idx_audit_action (Action),
    INDEX idx_audit_date (CreatedAt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class AccountingPeriodAuditLog
{
    public long LogId { get; set; }
    public long PeriodId { get; set; }
    
    public string Action { get; set; } = null!;
    public string? OldValue { get; set; }
    public string? NewValue { get; set; }
    public string? Reason { get; set; }
    
    public Guid CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    
    // Navigation
    public virtual AccountingPeriod Period { get; set; } = null!;
    public virtual User CreatedByUser { get; set; } = null!;
}
```

**Ví dụ audit entries:**

```json
// Tạo kỳ mới
{
  "action": "period_created",
  "newValue": { "periodType": "quarter", "year": 2026, "quarter": 1 }
}

// Rule Engine gợi ý (auto log)
{
  "action": "group_suggestion",
  "newValue": {
    "suggestedGroup": 2,
    "actualRevenue": 620000000,
    "annualizedRevenue": 820000000,
    "rulesetVersion": "1.0.0"
  }
}

// Owner tạo sổ theo nhóm 2
{
  "action": "book_created",
  "newValue": { "bookId": 15, "groupNumber": 2, "taxMethod": "method_1", "bookType": "S2a" }
}

// Chốt kỳ
{
  "action": "period_finalized",
  "newValue": { "finalizedAt": "2026-04-10T09:00:00Z" }
}

// Mở lại kỳ
{
  "action": "period_reopened",
  "oldValue": { "status": "finalized" },
  "newValue": { "status": "reopened" },
  "reason": "Phát hiện thiếu 3 đơn hàng chưa complete, cần bổ sung trước khi nộp thuế"
}
```

---

## 2. Period Lifecycle

### 2.1 Create Period

Periods có thể được tạo **tự động** (system job đầu quý/năm) hoặc **thủ công** bởi Owner:

```yaml
POST /api/locations/{locationId}/accounting/periods
Authorization: Bearer {token}

Request:
{
  "periodType": "quarter",
  "year": 2026,
  "quarter": 1,
  "openingCashBalance": 50000000,
  "openingBankBalance": 120000000,
  "useSuggestedOpeningBalances": false
}

Response (201 Created):
{
  "periodId": 1,
  "periodType": "quarter",
  "year": 2026,
  "quarter": 1,
  "startDate": "2026-01-01",
  "endDate": "2026-03-31",
  "openingCashBalance": 50000000,
  "openingBankBalance": 120000000,
  "status": "open"
}
```

### 2.1.1 Create Custom Period (Theo khoảng thời gian bất kỳ)

Cho phép Owner tạo kỳ theo bất kỳ khoảng thời gian nào (1 tháng, 2 tháng, 6 tháng, hoặc tùy biến):

```yaml
POST /api/locations/{locationId}/accounting/periods/custom
Authorization: Bearer {token}

Request:
{
  "startDate": "2026-01-01",
  "endDate": "2026-02-28",
  "openingCashBalance": 10000000,
  "openingBankBalance": 25000000,
  "useSuggestedOpeningBalances": false
}

Response (201 Created):
{
  "periodId": 2,
  "periodType": "custom",
  "year": 2026,
  "quarter": null,
  "startDate": "2026-01-01",
  "endDate": "2026-02-28",
  "openingCashBalance": 10000000,
  "openingBankBalance": 25000000,
  "status": "open"
}
```

Rules cho custom period:

- Only Owner.
- `endDate` phải lớn hơn hoặc bằng `startDate`.
- Không check overlap kỳ. Owner có thể tạo kỳ custom bất kỳ.
- `openingCashBalance` + `openingBankBalance` cần user nhập tay, hoặc dùng chế độ gợi ý carry bằng API riêng.

### 2.1.2 API gợi ý Carry Opening Balance

Khi user chưa nhập balance, gọi API này để lấy số dư gợi ý từ kỳ trước. Nếu user đồng ý, gửi `useSuggestedOpeningBalances=true` ở API tạo kỳ.

```yaml
POST /api/locations/{locationId}/accounting/periods/opening-balance-suggestion
Authorization: Bearer {token}

Request (quarter/year):
{
  "periodType": "quarter",
  "year": 2026,
  "quarter": 2
}

Request (custom):
{
  "periodType": "custom",
  "startDate": "2026-07-01"
}

Response:
{
  "hasSuggestion": true,
  "suggestionReasonCode": "PERIOD_SUGGESTION_FROM_PREVIOUS",
  "suggestionReason": "Số dư gợi ý được tính từ opening kỳ trước cộng net GL trong kỳ nguồn.",
  "calculationExplanationCode": "PERIOD_SUGGESTION_FORMULA",
  "calculationExplanation": "Công thức: suggestedOpening = previousOpening + netGL (theo từng kênh cash/bank)",
  "openingCashBalance": 61000000,
  "openingBankBalance": 132000000,
  "sourcePeriodId": 12,
  "sourceStartDate": "2026-04-01",
  "sourceEndDate": "2026-06-30",
  "calculationBreakdown": {
    "previousOpeningCashBalance": 50000000,
    "previousOpeningBankBalance": 120000000,
    "netCashInSourcePeriod": 11000000,
    "netBankInSourcePeriod": 12000000,
    "suggestedOpeningCashBalance": 61000000,
    "suggestedOpeningBankBalance": 132000000
  }
}
```

### 2.2 Finalize Period

```yaml
POST /api/v1/locations/{locationId}/accounting/periods/{periodId}/finalize
Authorization: Bearer {token}

Response:
{
  "periodId": 1,
  "status": "finalized",
  "finalizedAt": "2026-04-10T09:00:00Z",
  "message": "Kỳ Q1/2026 đã được chốt"
}
```

Rules:

- Only Owner
- Phải có ít nhất 1 AccountingBook active trong period
- Ghi audit log

### 2.3 Reopen Period

```yaml
POST /api/v1/locations/{locationId}/accounting/periods/{periodId}/reopen
Authorization: Bearer {token}

Request:
{
  "reason": "Phát hiện thiếu 3 đơn hàng chưa complete"  // Bắt buộc
}

Response:
{
  "periodId": 1,
  "status": "reopened",
  "message": "Kỳ Q1/2026 đã được mở lại"
}
```

Rules:

- Only Owner
- Reason bắt buộc
- Ghi audit log (action = `period_reopened`, oldValue, newValue, reason)

---

## 3. Business Rules

| Rule | Mô tả |
|------|-------|
| **RULE-PERIOD-01** | Unique per location + type + year + quarter |
| **RULE-PERIOD-02** | Finalize bắt buộc có ít nhất 1 book active |
| **RULE-PERIOD-03** | Reopen bắt buộc có reason |
| **RULE-PERIOD-04** | Mọi thay đổi status → audit log |
| **RULE-PERIOD-05** | Khi tạo kỳ, user phải cung cấp cả `openingCashBalance` và `openingBankBalance`, hoặc bật `useSuggestedOpeningBalances=true` |
| **RULE-PERIOD-06** | Hệ thống chỉ carry balance khi user chủ động chọn dùng gợi ý (không auto-carry ngầm) |
| **RULE-PERIOD-07** | Kỳ custom không check overlap, owner có thể tạo theo bất kỳ khoảng thời gian nào |

---

## 4. API Endpoints

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/locations/{id}/accounting/periods` | Tạo kỳ kế toán quarter/year | Owner |
| `POST` | `/api/locations/{id}/accounting/periods/custom` | Tạo kỳ kế toán tùy chỉnh theo startDate/endDate | Owner |
| `POST` | `/api/locations/{id}/accounting/periods/opening-balance-suggestion` | Gợi ý carry opening cash/bank | Owner |
| `GET` | `/api/locations/{id}/accounting/periods` | List kỳ kế toán | Owner |
| `GET` | `/api/locations/{id}/accounting/periods/{periodId}` | Chi tiết kỳ | Owner |
| `POST` | `/api/locations/{id}/accounting/periods/{periodId}/finalize` | Chốt kỳ | Owner |
| `POST` | `/api/locations/{id}/accounting/periods/{periodId}/reopen` | Mở lại kỳ | Owner |
| `GET` | `/api/locations/{id}/accounting/periods/{periodId}/audit-logs` | Lịch sử thay đổi | Owner |

---

## 5. Error Codes

| Code | HTTP | Message |
|------|:----:|---------|
| `PERIOD_NOT_FOUND` | 404 | Kỳ kế toán không tồn tại |
| `PERIOD_ALREADY_EXISTS` | 409 | Kỳ kế toán đã tồn tại (trùng year+quarter) |
| `PERIOD_NOT_OPEN` | 400 | Kỳ kế toán không ở trạng thái open |
| `PERIOD_ALREADY_FINALIZED` | 400 | Kỳ kế toán đã chốt rồi |
| `PERIOD_REOPEN_REASON_REQUIRED` | 400 | Phải nhập lý do khi mở lại kỳ |
| `PERIOD_NO_BOOKS` | 400 | Phải có ít nhất 1 sổ active trước khi chốt kỳ |
| `PERIOD_OPENING_BALANCE_REQUIRED` | 400 | Kỳ đầu tiên bắt buộc nhập số dư đầu kỳ (tiền mặt + ngân hàng) |
| `NO_PERMISSION` | 403 | Không có quyền thực hiện action này |
