# Report & Accounting Flow Documentation

> **Mục đích**: Document chi tiết flow báo cáo, kế toán, và tuân thủ Thông tư 152/2025/TT-BTC cho BizFlow Platform.

---

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Quyết định thiết kế](#2-quyết-định-thiết-kế)
3. [Entity Design](#3-entity-design)
4. [General Ledger Flow](#4-general-ledger-flow)
5. [Cost Flow](#5-cost-flow)
6. [Accounting Period Flow](#6-accounting-period-flow)
7. [Rule Engine Module](#7-rule-engine-module)
8. [Accounting Book Generation Flow](#8-accounting-book-generation-flow)
9. [TT152 Book Specifications (S1a, S2a–S2e)](#9-tt152-book-specifications-s1a-s2as2e)
10. [Cash Flow & Dashboard](#10-cash-flow--dashboard)
11. [API Endpoints Summary](#11-api-endpoints-summary)
12. [Error Codes](#12-error-codes)
13. [Business Rules Summary](#13-business-rules-summary)

---

## 1. Tổng quan

### Context

Hộ kinh doanh Việt Nam (HKD) từ 01/01/2026 phải tự ghi chép sổ sách kế toán theo Thông tư 152/2025/TT-BTC. BizFlow Platform hỗ trợ:

- **Tự động ghi sổ cái** (General Ledger) từ các hoạt động kinh doanh (bán hàng, nhập hàng, chi phí)
- **Quản lý kỳ kế toán** (quý/năm)
- **Phân loại nhóm HKD** qua Rule Engine (data-driven, versioned, không hardcode)
- **Tạo sổ kế toán** theo mẫu TT152 (S1a, S2a–S2e), fill data tự động từ GL
- **Xuất báo cáo** PDF/Excel cho khai thuế
- **Theo dõi dòng tiền** (cash/bank) và dashboard cho Owner

### Module Map

```markdown
┌──────────────────────── REPORT & ACCOUNTING ──────────────────────────┐
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  DATA LAYER (auto-generated, realtime)                          │  │
│  │                                                                 │  │
│  │  Orders ──┐                                                     │  │
│  │  Imports ─┼──► GeneralLedgerEntries (sổ cái)                    │  │
│  │  Costs ───┘    + Costs (chi phí)                                │  │
│  │                + TaxPayments (thuế đã nộp)                      │  │
│  └─────────────────────────┬───────────────────────────────────────┘  │
│                            │                                          │
│  ┌─────────────────────────▼───────────────────────────────────────┐  │
│  │  RULE ENGINE (independent module, versioned)                    │  │
│  │                                                                 │  │
│  │  TaxRulesets ── TaxGroupRules ── IndustryTaxRates               │  │
│  │  → Input: DT lũy kế    → Output: Nhóm + Thuế suất + Mẫu sổ      │  │
│  └─────────────────────────┬───────────────────────────────────────┘  │
│                            │                                          │
│  ┌─────────────────────────▼───────────────────────────────────────┐  │
│  │  TEMPLATE & BOOK GENERATION                                     │  │
│  │                                                                 │  │
│  │  AccountingTemplates ── TemplateVersions ── FieldMappings       │  │
│  │                                   │                             │  │
│  │  Owner chọn nhóm ──► AccountingBooks (live view from GL)        │  │
│  │                                   │                             │  │
│  │                           AccountingExports (snapshot khi xuất) │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐  │
│  │  REPORTING LAYER                                                │  │
│  │                                                                 │  │
│  │  Dashboard (widgets) ── Cash Flow ── Revenue by BusinessType    │  │
│  └─────────────────────────────────────────────────────────────────┘  │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

### Tables Overview

| # | Table | Mục đích | Managed by |
|---|-------|----------|------------|
| 1 | `Costs` | Chi phí (auto từ Import + Owner tự khai) | System + Owner |
| 2 | `GeneralLedgerEntries` | Sổ cái — mọi giao dịch tài chính | System (auto) |
| 3 | `AccountingSettings` | Cấu hình kế toán per location | Owner |
| 4 | `AccountingPeriods` | Kỳ kế toán (quý/năm) | System + Owner |
| 5 | `AccountingPeriodAuditLogs` | Lịch sử thay đổi kỳ kế toán | System (auto) |
| 6 | `TaxRulesets` | Version container cho Rule Engine | Admin/Consultant |
| 7 | `TaxGroupRules` | Phân nhóm HKD theo doanh thu | Admin/Consultant |
| 8 | `IndustryTaxRates` | Thuế suất VAT/TNCN theo ngành | Admin/Consultant |
| 9 | `AccountingTemplates` | Định nghĩa mẫu sổ (S1a, S2a…) | Admin/Consultant |
| 10 | `AccountingTemplateVersions` | Phiên bản nội dung mẫu sổ | Admin/Consultant |
| 11 | `TemplateFieldMappings` | Mapping dữ liệu DB → field trong mẫu | Admin/Consultant |
| 12 | `AccountingBooks` | Sổ kế toán đã tạo (live view) | Owner |
| 13 | `AccountingExports` | Snapshot mỗi lần xuất sổ | System (auto) |
| 14 | `TaxPayments` | Ghi nhận thuế đã nộp (cho S2d) | Owner |

---

## 2. Quyết định thiết kế

### DD-01: Mỗi Location một sổ riêng

Mỗi `BusinessLocation` có bộ sổ kế toán riêng biệt. GL, Costs, Periods, Books đều scoped theo `BusinessLocationId`.

Khi một location kinh doanh **đa ngành** (nhiều `BusinessType` với các mức thuế khác nhau), hệ thống **tự động tách** file báo cáo theo từng ngành. Owner không cần tự phân loại — hệ thống query dựa trên `Product.BusinessTypeId` trong `OrderDetails`.

```markdown
Location: "Cửa hàng Minh Phát"
├── Bán hàng hóa (BusinessType: Retail, VAT 1%)
├── Dịch vụ cắt sắt (BusinessType: Service, VAT 5%)
│
└── Khi xuất sổ S2a:
    ├── File 1: S2a — Phân phối hàng hóa (VAT 1%, TNCN 0.5%)
    └── File 2: S2a — Dịch vụ (VAT 5%, TNCN 2%)
    
    GL vẫn gộp chung → hệ thống tách khi render/export
```

### DD-02: General Ledger là sổ cái giao dịch đơn giản

GL cho HKD **không phải** double-entry accounting chuẩn (chart of accounts, T-accounts). Đây là **sổ ghi chép giao dịch tài chính đơn giản** phù hợp TT152:

- Mỗi event tài chính → 1+ GL entry
- Mỗi entry ghi nhận: ngày, mô tả, số tiền vào/ra, kênh tiền (cash/bank/debt)
- Khi data thay đổi (cancel order, sửa cost) → tạo **reversal entry** (không sửa/xóa entry cũ)

### DD-03: Owner chủ động chọn nhóm, hệ thống gợi ý

```markdown
┌────────────────────────────────────────────────────────────────┐
│                   FLOW CHỌN NHÓM HKD                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. Không bắt buộc chọn nhóm khi tạo kỳ kế toán mới            │
│                                                                │
│  2. Hệ thống thu thập dữ liệu (GL ghi nhận tất cả)             │
│                                                                │
│  3. Rule Engine gợi ý nhóm dựa trên DT lũy kế                  │
│     → Hiển thị trên Dashboard: "DT hiện tại: 620tr             │
│       → Gợi ý: Nhóm 2, Cách 1"                                 │
│                                                                │
│  4. Owner dựa vào gợi ý + kinh nghiệm kỳ trước                 │
│     → Chọn nhóm + cách tính thuế                               │
│     → HỆ THỐNG TẠO AccountingBook theo mẫu tương ứng           │
│     → Data từ GL được fill vào book                            │
│                                                                │
│  5. Owner có thể chọn nhóm khác bất kỳ lúc nào                 │
│     → Tạo thêm book mới (book cũ vẫn giữ)                      │
│     → So sánh giữa các nhóm trước khi quyết định               │
│                                                                │
│  6. Khi sẵn sàng → Export sổ (snapshot lưu lại)                │
│     → Nếu data thay đổi → book live tự cập nhật                │
│     → Export mới sẽ khác → có lịch sử so sánh                  │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### DD-04: Rule Engine là module độc lập, data-driven

- Toàn bộ logic phân nhóm + thuế suất nằm trong **data** (tables), không hardcode if/else
- Mỗi lần TT152 thay đổi → Admin/Consultant tạo **version mới** của Ruleset
- Code Rule Engine **không đổi** — chỉ data thay đổi
- Mọi lần đánh giá đều ghi log (version nào, input gì, output gì)

### DD-05: Live data + Snapshot exports

| Khái niệm | Mô tả | Editable? |
|-----------|-------|:---------:|
| **AccountingBook** (live view) | Config: kỳ nào + nhóm nào + mẫu nào. Data luôn query realtime từ GL/Orders/Costs. Tự cập nhật khi data gốc thay đổi. | N/A (auto) |
| **AccountingExport** (snapshot) | Bản chụp tại thời điểm xuất. Lưu summary + file output. Không thay đổi. | ❌ Frozen |

Owner có thể export nhiều lần → so sánh giữa các snapshot → thấy được lịch sử thay đổi.

### DD-06: GL entry splitting — Tách entry theo kênh thanh toán

> **Giải thích**: Khi một đơn hàng được thanh toán bằng nhiều hình thức (tiền mặt + chuyển khoản + ghi nợ), hệ thống tạo **nhiều GL entry** — mỗi entry cho 1 kênh tiền. Mục đích: khi query dòng tiền (cash flow), có thể lọc chính xác "tiền mặt thực nhận" vs "ghi nợ chưa thu".

**Ví dụ cụ thể:**

```markdown
Order #100: Tổng 1,000,000đ
├── Thanh toán: 600k tiền mặt + 200k chuyển khoản + 200k ghi nợ
│
└── GL tạo ra 3 entries:
    ┌─────────────────────────────────────────────────────────┐
    │ Entry 1: Debit 600,000 | Channel: cash                  │
    │          "ORD-100: Bán hàng (tiền mặt)"                 │
    │                                                         │
    │ Entry 2: Debit 200,000 | Channel: bank                  │
    │          "ORD-100: Bán hàng (chuyển khoản)"             │
    │                                                         │
    │ Entry 3: Debit 200,000 | Channel: debt                  │
    │          "ORD-100: Bán hàng (ghi nợ Anh Ba)"  tổng 1000k │
        entry 4: trả nợ 100k        │   tổng 900
    └─────────────────────────────────────────────────────────┘

Query cash flow thực tế:
  SELECT SUM(DebitAmount) WHERE MoneyChannel IN ('cash','bank')
  → 800,000đ (tiền thực nhận)

Query tổng doanh thu:
  SELECT SUM(DebitAmount) WHERE TransactionType = 'sale'
  → 1,000,000đ (gồm cả ghi nợ, vì nợ vẫn là DT)
```

**Trường hợp phổ biến (80%+ orders):** Thanh toán 1 hình thức duy nhất → chỉ **1 GL entry per order**. Splitting chỉ xảy ra khi mixed payment.

---

## 3. Entity Design

### 3.1 Costs (Chi phí)

```sql
-- =============================================
-- COSTS TABLE (Chi phí kinh doanh)
-- =============================================
CREATE TABLE Costs (
    CostId BIGINT AUTO_INCREMENT PRIMARY KEY,
    BusinessLocationId INT NOT NULL,
    
    -- Phân loại
    CostType VARCHAR(30) NOT NULL 
        COMMENT 'import, salary, rent, utilities, transport, marketing, maintenance, other',
    
    -- Liên kết auto (nếu từ Import)
    ImportId BIGINT DEFAULT NULL 
        COMMENT 'NULL = Owner tự khai báo, NOT NULL = auto tạo từ Import CONFIRMED',
    
    -- Chi tiết
    Description VARCHAR(500) NOT NULL,
    Amount DECIMAL(15,2) NOT NULL,
    CostDate DATE NOT NULL COMMENT 'Ngày phát sinh chi phí',
    
    -- Thanh toán
    PaymentMethod VARCHAR(20) DEFAULT NULL COMMENT 'cash | bank | NULL=chưa xác định',
    
    -- Chứng từ
    DocumentUrl VARCHAR(500) DEFAULT NULL COMMENT 'Ảnh hóa đơn/biên lai (Cloudinary)',
    DocumentPublicId VARCHAR(255) DEFAULT NULL COMMENT 'Cloudinary public ID',
    
    -- Audit
    CreatedByUserId CHAR(36) NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    DeletedAt DATETIME DEFAULT NULL COMMENT 'Soft delete',
    
    -- Indexes & FKs
    CONSTRAINT fk_cost_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    CONSTRAINT fk_cost_import FOREIGN KEY (ImportId) 
        REFERENCES Imports(ImportId),
    INDEX idx_cost_location (BusinessLocationId),
    INDEX idx_cost_type (CostType),
    INDEX idx_cost_date (CostDate),
    INDEX idx_cost_import (ImportId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class Cost
{
    public long CostId { get; set; }
    public int BusinessLocationId { get; set; }
    
    // Classification
    public string CostType { get; set; } = null!;
    public long? ImportId { get; set; }
    
    // Details
    public string Description { get; set; } = null!;
    public decimal Amount { get; set; }
    public DateOnly CostDate { get; set; }
    public string? PaymentMethod { get; set; }
    
    // Document
    public string? DocumentUrl { get; set; }
    public string? DocumentPublicId { get; set; }
    
    // Audit
    public Guid CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? UpdatedAt { get; set; }
    public DateTime? DeletedAt { get; set; }
    
    // Navigation
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual Import? Import { get; set; }
    public virtual User CreatedByUser { get; set; } = null!;
}

public static class CostTypes
{
    public const string Import = "import";
    public const string Salary = "salary";
    public const string Rent = "rent";
    public const string Utilities = "utilities";
    public const string Transport = "transport";
    public const string Marketing = "marketing";
    public const string Maintenance = "maintenance";
    public const string Other = "other";
}
```

### 3.2 GeneralLedgerEntries (Sổ cái)

```sql
-- =============================================
-- GENERAL LEDGER ENTRIES TABLE (Sổ cái giao dịch)
-- =============================================
CREATE TABLE GeneralLedgerEntries (
    EntryId BIGINT AUTO_INCREMENT PRIMARY KEY,
    BusinessLocationId INT NOT NULL,
    
    -- ═══ PHÂN LOẠI GIAO DỊCH ═══
    TransactionType VARCHAR(30) NOT NULL,
    -- Doanh thu:    'sale'
    -- Chi phí:      'import_cost', 'manual_cost'
    -- Công nợ:      'debt_payment'
    -- Thuế:         'tax_payment'
    -- Hoàn/Điều chỉnh: (dùng IsReversal = true)
    
    -- ═══ REFERENCE (truy nguồn gốc) ═══
    ReferenceType VARCHAR(30) NOT NULL,
    -- 'order'            → Orders.OrderId
    -- 'import'           → Imports.ImportId
    -- 'cost'             → Costs.CostId
    -- 'debtor_payment'   → DebtorPaymentTransactions.TransactionId
    -- 'tax_payment'      → TaxPayments.TaxPaymentId
    ReferenceId BIGINT NOT NULL,
    
    -- ═══ NỘI DUNG ═══
    EntryDate DATE NOT NULL COMMENT 'Ngày giao dịch',
    Description VARCHAR(500) NOT NULL COMMENT 'Diễn giải giao dịch',
    
    -- ═══ SỐ TIỀN ═══
    -- Convention: Chỉ 1 trong 2 có giá trị > 0 trên mỗi entry
    DebitAmount DECIMAL(15,2) NOT NULL DEFAULT 0 
        COMMENT 'Tiền VÀO business: doanh thu bán hàng, thu nợ',
    CreditAmount DECIMAL(15,2) NOT NULL DEFAULT 0 
        COMMENT 'Tiền RA business: nhập hàng, chi phí, nộp thuế',
    
    -- ═══ KÊNH TIỀN (cho cash flow tracking) ═══
    MoneyChannel VARCHAR(10) DEFAULT NULL,
    -- 'cash'  = Tiền mặt thực tế
    -- 'bank'  = Chuyển khoản thực tế
    -- 'debt'  = Ghi nợ (chưa thu/trả tiền thực tế)
    -- NULL    = Không liên quan dòng tiền (hiếm)
    
    -- ═══ REVERSAL TRACKING ═══
    IsReversal BOOLEAN NOT NULL DEFAULT FALSE 
        COMMENT 'TRUE = entry hoàn/hủy (cancel order, cancel import)',
    ReversedEntryId BIGINT DEFAULT NULL 
        COMMENT 'Trỏ về EntryId bị reverse',
    
    -- ═══ AUDIT ═══
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes & FKs
    CONSTRAINT fk_gl_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    INDEX idx_gl_location_date (BusinessLocationId, EntryDate),
    INDEX idx_gl_type (TransactionType),
    INDEX idx_gl_ref (ReferenceType, ReferenceId),
    INDEX idx_gl_channel (MoneyChannel),
    INDEX idx_gl_reversal (ReversedEntryId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class GeneralLedgerEntry
{
    public long EntryId { get; set; }
    public int BusinessLocationId { get; set; }
    
    // Classification
    public string TransactionType { get; set; } = null!;
    public string ReferenceType { get; set; } = null!;
    public long ReferenceId { get; set; }
    
    // Content
    public DateOnly EntryDate { get; set; }
    public string Description { get; set; } = null!;
    
    // Amount
    public decimal DebitAmount { get; set; }
    public decimal CreditAmount { get; set; }
    
    // Money channel
    public string? MoneyChannel { get; set; }
    
    // Reversal
    public bool IsReversal { get; set; }
    public long? ReversedEntryId { get; set; }
    
    // Audit
    public DateTime CreatedAt { get; set; }
    
    // Navigation
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
}

public static class GLTransactionTypes
{
    public const string Sale = "sale";
    public const string ImportCost = "import_cost";
    public const string ManualCost = "manual_cost";
    public const string DebtPayment = "debt_payment";
    public const string TaxPayment = "tax_payment";
}

public static class GLReferenceTypes
{
    public const string Order = "order";
    public const string Import = "import";
    public const string Cost = "cost";
    public const string DebtorPayment = "debtor_payment";
    public const string TaxPayment = "tax_payment";
}

public static class MoneyChannels
{
    public const string Cash = "cash";
    public const string Bank = "bank";
    public const string Debt = "debt";
}
```

### 3.3 AccountingSettings (Cấu hình kế toán)

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

### 3.4 AccountingPeriods (Kỳ kế toán)

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

### 3.5 AccountingPeriodAuditLogs (Lịch sử thay đổi)

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

### 3.6 Rule Engine: TaxRulesets, TaxGroupRules, IndustryTaxRates

#### TaxRulesets (Version container)

```sql
-- =============================================
-- TAX RULESETS TABLE (Version container cho Rule Engine)
-- =============================================
CREATE TABLE TaxRulesets (
    RulesetId INT AUTO_INCREMENT PRIMARY KEY,
    
    -- Identity
    Code VARCHAR(50) NOT NULL COMMENT 'Unique code: TT152_2025',
    Name VARCHAR(200) NOT NULL COMMENT 'Thông tư 152/2025/TT-BTC',
    Description TEXT DEFAULT NULL,
    Version VARCHAR(20) NOT NULL COMMENT 'Semantic versioning: 1.0.0',
    
    -- Lifecycle
    EffectiveFrom DATE NOT NULL COMMENT 'Ngày bắt đầu hiệu lực',
    EffectiveTo DATE DEFAULT NULL COMMENT 'NULL = vô thời hạn',
    IsActive BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Chỉ 1 active tại 1 thời điểm',
    
    -- Audit
    CreatedByUserId CHAR(36) DEFAULT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE INDEX idx_ruleset_code_version (Code, Version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class TaxRuleset
{
    public int RulesetId { get; set; }
    
    public string Code { get; set; } = null!;
    public string Name { get; set; } = null!;
    public string? Description { get; set; }
    public string Version { get; set; } = null!;
    
    public DateOnly EffectiveFrom { get; set; }
    public DateOnly? EffectiveTo { get; set; }
    public bool IsActive { get; set; }
    
    public Guid? CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    
    // Navigation
    public virtual ICollection<TaxGroupRule> GroupRules { get; set; } = new List<TaxGroupRule>();
    public virtual ICollection<IndustryTaxRate> IndustryTaxRates { get; set; } = new List<IndustryTaxRate>();
}
```

#### TaxGroupRules (Phân nhóm HKD)

```sql
-- =============================================
-- TAX GROUP RULES TABLE (Logic phân nhóm HKD)
-- =============================================
CREATE TABLE TaxGroupRules (
    RuleId INT AUTO_INCREMENT PRIMARY KEY,
    RulesetId INT NOT NULL,
    
    -- Group identity
    GroupNumber TINYINT NOT NULL COMMENT '1, 2, 3, 4',
    GroupName VARCHAR(100) NOT NULL COMMENT 'Nhóm 1, Nhóm 2...',
    GroupDescription TEXT DEFAULT NULL,
    
    -- ═══ REVENUE THRESHOLDS ═══
    MinRevenue DECIMAL(18,2) NOT NULL DEFAULT 0 
        COMMENT 'Ngưỡng DT tối thiểu (inclusive)',
    MaxRevenue DECIMAL(18,2) DEFAULT NULL 
        COMMENT 'Ngưỡng DT tối đa (exclusive), NULL = unlimited',
    
    -- ═══ TAX EXEMPTIONS ═══
    VatExempt BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Miễn thuế GTGT (Nhóm 1)?',
    PitExempt BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Miễn thuế TNCN (Nhóm 1)?',
    
    -- ═══ TAX METHODS ═══
    AllowedTaxMethods JSON NOT NULL 
        COMMENT '["method_1","method_2"] cho N2, ["method_2"] cho N3-4, ["exempt"] cho N1',
    DefaultTaxMethod VARCHAR(20) DEFAULT NULL 
        COMMENT 'Gợi ý mặc định khi owner chưa chọn',
    
    -- ═══ PIT RATE (Cách 2 — thuế suất cố định theo nhóm) ═══
    PitRateMethod2 DECIMAL(5,4) DEFAULT NULL 
        COMMENT '0.1500=15% (N2), 0.1700=17% (N3), 0.2000=20% (N4)',
    
    -- ═══ DEDUCTION (Cách 1 — mức trừ DT) ═══
    RevenueDeduction DECIMAL(18,2) DEFAULT NULL 
        COMMENT '500,000,000đ cho Nhóm 2 Cách 1',
    
    -- ═══ REQUIRED BOOKS ═══
    RequiredBooksJson JSON NOT NULL,
    -- Ví dụ:
    -- Nhóm 1: {"default": ["S1a"]}
    -- Nhóm 2: {"method_1": ["S2a"], "method_2": ["S2b","S2c","S2d","S2e"]}
    -- Nhóm 3-4: {"method_2": ["S2b","S2c","S2d","S2e"]}
    
    -- ═══ REPORTING OBLIGATIONS ═══
    VatReportFrequency VARCHAR(20) NOT NULL DEFAULT 'quarterly' 
        COMMENT 'quarterly | monthly | exempt',
    PitReportFrequency VARCHAR(20) DEFAULT NULL 
        COMMENT 'quarterly | exempt',
    AnnualSettlement BOOLEAN NOT NULL DEFAULT FALSE 
        COMMENT 'Quyết toán năm? (Nhóm 2: true)',
    
    -- ═══ E-INVOICE ═══
    EInvoiceRequired BOOLEAN NOT NULL DEFAULT FALSE,
    EInvoiceRevenueThreshold DECIMAL(18,2) DEFAULT NULL 
        COMMENT '1,000,000,000 (1 tỷ) cho Nhóm 2',
    
    -- Ordering
    SortOrder INT NOT NULL DEFAULT 0,
    
    -- Indexes & FKs
    CONSTRAINT fk_tgr_ruleset FOREIGN KEY (RulesetId) 
        REFERENCES TaxRulesets(RulesetId),
    INDEX idx_tgr_ruleset (RulesetId),
    UNIQUE INDEX idx_tgr_ruleset_group (RulesetId, GroupNumber)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class TaxGroupRule
{
    public int RuleId { get; set; }
    public int RulesetId { get; set; }
    
    // Group
    public int GroupNumber { get; set; }
    public string GroupName { get; set; } = null!;
    public string? GroupDescription { get; set; }
    
    // Thresholds
    public decimal MinRevenue { get; set; }
    public decimal? MaxRevenue { get; set; }
    
    // Tax
    public bool VatExempt { get; set; }
    public bool PitExempt { get; set; }
    public string AllowedTaxMethods { get; set; } = null!; // JSON
    public string? DefaultTaxMethod { get; set; }
    public decimal? PitRateMethod2 { get; set; }
    public decimal? RevenueDeduction { get; set; }
    
    // Books & Reporting
    public string RequiredBooksJson { get; set; } = null!; // JSON
    public string VatReportFrequency { get; set; } = "quarterly";
    public string? PitReportFrequency { get; set; }
    public bool AnnualSettlement { get; set; }
    
    // E-Invoice
    public bool EInvoiceRequired { get; set; }
    public decimal? EInvoiceRevenueThreshold { get; set; }
    
    public int SortOrder { get; set; }
    
    // Navigation
    public virtual TaxRuleset Ruleset { get; set; } = null!;
}
```

**Sample data (TT152/2025 v1.0):**

```sql
INSERT INTO TaxRulesets (Code, Name, Version, EffectiveFrom, IsActive) VALUES
('TT152_2025', 'Thông tư 152/2025/TT-BTC', '1.0.0', '2026-01-01', TRUE);

-- RulesetId = 1
INSERT INTO TaxGroupRules 
(RulesetId, GroupNumber, GroupName, MinRevenue, MaxRevenue, VatExempt, PitExempt,
 AllowedTaxMethods, DefaultTaxMethod, PitRateMethod2, RevenueDeduction,
 RequiredBooksJson, VatReportFrequency, PitReportFrequency, 
 AnnualSettlement, EInvoiceRequired, EInvoiceRevenueThreshold, SortOrder) VALUES

-- Nhóm 1: DT < 500 triệu
(1, 1, 'Nhóm 1', 0, 500000000,
 TRUE, TRUE,
 '["exempt"]', 'exempt', NULL, NULL,
 '{"default":["S1a"]}', 'quarterly', 'exempt',
 FALSE, FALSE, NULL, 1),

-- Nhóm 2: 500 triệu ≤ DT < 3 tỷ
(1, 2, 'Nhóm 2', 500000000, 3000000000,
 FALSE, FALSE,
 '["method_1","method_2"]', 'method_1', 0.1500, 500000000,
 '{"method_1":["S2a"],"method_2":["S2b","S2c","S2d","S2e"]}', 'quarterly', 'quarterly',
 TRUE, FALSE, 1000000000, 2),

-- Nhóm 3: 3 tỷ ≤ DT < 50 tỷ
(1, 3, 'Nhóm 3', 3000000000, 50000000000,
 FALSE, FALSE,
 '["method_2"]', 'method_2', 0.1700, NULL,
 '{"method_2":["S2b","S2c","S2d","S2e"]}', 'quarterly', NULL,
 FALSE, TRUE, NULL, 3),

-- Nhóm 4: DT ≥ 50 tỷ
(1, 4, 'Nhóm 4', 50000000000, NULL,
 FALSE, FALSE,
 '["method_2"]', 'method_2', 0.2000, NULL,
 '{"method_2":["S2b","S2c","S2d","S2e"]}', 'monthly', NULL,
 FALSE, TRUE, NULL, 4);
```

#### IndustryTaxRates (Thuế suất theo ngành)

```sql
-- =============================================
-- INDUSTRY TAX RATES TABLE (Thuế suất theo ngành nghề)
-- =============================================
CREATE TABLE IndustryTaxRates (
    RateId INT AUTO_INCREMENT PRIMARY KEY,
    RulesetId INT NOT NULL,
    BusinessTypeId CHAR(36) NOT NULL,
    
    -- Tax type
    TaxType VARCHAR(20) NOT NULL,
    -- 'VAT'            Thuế GTGT (% trên DT, tất cả nhóm chịu thuế)
    -- 'PIT_METHOD_1'   Thuế TNCN Cách 1 (% trên DT vượt 500tr, chỉ Nhóm 2)
    
    -- Rate
    TaxRate DECIMAL(5,4) NOT NULL COMMENT 'VD: 0.0100 = 1%, 0.0050 = 0.5%',
    
    -- Description
    Description VARCHAR(200) DEFAULT NULL,
    
    -- Indexes & FKs
    CONSTRAINT fk_itr_ruleset FOREIGN KEY (RulesetId) 
        REFERENCES TaxRulesets(RulesetId),
    CONSTRAINT fk_itr_business_type FOREIGN KEY (BusinessTypeId) 
        REFERENCES BusinessTypes(BusinessTypeId),
    INDEX idx_itr_ruleset (RulesetId),
    UNIQUE INDEX idx_itr_unique (RulesetId, BusinessTypeId, TaxType)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class IndustryTaxRate
{
    public int RateId { get; set; }
    public int RulesetId { get; set; }
    public Guid BusinessTypeId { get; set; }
    
    public string TaxType { get; set; } = null!;
    public decimal TaxRate { get; set; }
    public string? Description { get; set; }
    
    // Navigation
    public virtual TaxRuleset Ruleset { get; set; } = null!;
    public virtual BusinessType BusinessType { get; set; } = null!;
}
```

**Sample data:**

```sql
-- Giả sử: bt-retail, bt-service, bt-fnb, bt-transport là BusinessTypeId
INSERT INTO IndustryTaxRates (RulesetId, BusinessTypeId, TaxType, TaxRate, Description) VALUES
-- VAT (Thuế GTGT % trên doanh thu)
(1, 'bt-retail',    'VAT', 0.0100, 'Phân phối, cung cấp hàng hóa: GTGT 1%'),
(1, 'bt-service',   'VAT', 0.0500, 'Dịch vụ: GTGT 5%'),
(1, 'bt-fnb',       'VAT', 0.0300, 'Sản xuất, dịch vụ gắn hàng hóa: GTGT 3%'),
(1, 'bt-transport', 'VAT', 0.0300, 'Vận tải: GTGT 3%'),

-- PIT Method 1 (Thuế TNCN Cách 1: % trên DT vượt 500tr, chỉ Nhóm 2)
(1, 'bt-retail',    'PIT_METHOD_1', 0.0050, 'Phân phối hàng hóa: TNCN 0.5%'),
(1, 'bt-service',   'PIT_METHOD_1', 0.0200, 'Dịch vụ: TNCN 2%'),
(1, 'bt-fnb',       'PIT_METHOD_1', 0.0150, 'Sản xuất, DV gắn hàng hóa: TNCN 1.5%'),
(1, 'bt-transport', 'PIT_METHOD_1', 0.0150, 'Vận tải: TNCN 1.5%');
```

**Note: Relationship với `BusinessTypeTaxes` hiện tại**

| Aspect | `BusinessTypeTaxes` (hiện tại) | `IndustryTaxRates` (mới) |
|--------|-------------------------------|-------------------------|
| Versioning | `EffectiveFrom/To` (date-based) | `RulesetId` (version-based) |
| Tax types | `VAT`, `PIT` | `VAT`, `PIT_METHOD_1` (rõ ràng hơn) |
| Group context | Không có | Linked qua Ruleset → TaxGroupRules |

Giữ `BusinessTypeTaxes` cho backward compat, đánh dấu deprecated. Rule Engine chỉ đọc từ `IndustryTaxRates`.

### 3.7 Template: AccountingTemplates, AccountingTemplateVersions, TemplateFieldMappings

#### AccountingTemplates (Mẫu sổ kế toán)

```sql
-- =============================================
-- ACCOUNTING TEMPLATES TABLE (Định nghĩa mẫu sổ TT152)
-- =============================================
CREATE TABLE AccountingTemplates (
    TemplateId INT AUTO_INCREMENT PRIMARY KEY,
    
    -- Identity
    TemplateCode VARCHAR(20) NOT NULL COMMENT 'S1a | S2a | S2b | S2c | S2d | S2e',
    Name VARCHAR(200) NOT NULL COMMENT 'Sổ chi tiết bán hàng (Nhóm 1)',
    Description TEXT DEFAULT NULL,
    
    -- Classification
    ApplicableGroups JSON NOT NULL 
        COMMENT 'Nhóm áp dụng: [1] hoặc [2] hoặc [2,3,4]',
    ApplicableMethods JSON DEFAULT NULL 
        COMMENT 'Cách tính: ["method_1"] hoặc ["method_2"] hoặc NULL=tất cả',
    
    -- Status
    IsActive BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Audit
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE INDEX idx_template_code (TemplateCode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Sample data:**

```sql
INSERT INTO AccountingTemplates (TemplateCode, Name, ApplicableGroups, ApplicableMethods) VALUES
('S1a', 'Sổ chi tiết bán hàng (đơn giản)',       '[1]',      NULL),
('S2a', 'Sổ chi tiết bán hàng (theo ngành)',      '[2]',      '["method_1"]'),
('S2b', 'Sổ chi tiết bán hàng (chi tiết)',        '[2,3,4]',  '["method_2"]'),
('S2c', 'Sổ chi tiết chi phí',                     '[2,3,4]',  '["method_2"]'),
('S2d', 'Sổ theo dõi nghĩa vụ thuế',              '[2,3,4]',  '["method_2"]'),
('S2e', 'Sổ theo dõi tình hình thanh toán',        '[2,3,4]',  '["method_2"]');
```

#### AccountingTemplateVersions

```sql
-- =============================================
-- ACCOUNTING TEMPLATE VERSIONS TABLE
-- =============================================
CREATE TABLE AccountingTemplateVersions (
    TemplateVersionId INT AUTO_INCREMENT PRIMARY KEY,
    TemplateId INT NOT NULL,
    
    -- Version
    VersionLabel VARCHAR(20) NOT NULL COMMENT 'v1.0, v2.0...',
    IsActive BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Chỉ 1 active version per template',
    EffectiveFrom DATE DEFAULT NULL,
    
    -- Template file cho export
    TemplateFileUrl VARCHAR(500) DEFAULT NULL COMMENT 'URL file template (xlsx/docx)',
    
    -- Metadata
    ChangeNotes TEXT DEFAULT NULL COMMENT 'Ghi chú thay đổi so với version trước',
    
    -- Audit
    CreatedByUserId CHAR(36) DEFAULT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes & FKs
    CONSTRAINT fk_tv_template FOREIGN KEY (TemplateId) 
        REFERENCES AccountingTemplates(TemplateId),
    INDEX idx_tv_template (TemplateId),
    INDEX idx_tv_active (IsActive)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

#### TemplateFieldMappings

```sql
-- =============================================
-- TEMPLATE FIELD MAPPINGS TABLE
-- Mapping logic: DB data → template fields
-- =============================================
CREATE TABLE TemplateFieldMappings (
    MappingId INT AUTO_INCREMENT PRIMARY KEY,
    TemplateVersionId INT NOT NULL,
    
    -- ═══ FIELD IDENTITY ═══
    FieldCode VARCHAR(50) NOT NULL 
        COMMENT 'Code: stt, date, description, revenue, vat_amount...',
    FieldLabel VARCHAR(200) NOT NULL 
        COMMENT 'Nhãn hiển thị: STT, Ngày tháng, Diễn giải...',
    FieldType VARCHAR(20) NOT NULL 
        COMMENT 'auto_increment | date | text | decimal | computed',
    
    -- ═══ DATA SOURCE ═══
    SourceType VARCHAR(30) DEFAULT NULL 
        COMMENT 'query | formula | static | auto',
    SourceEntity VARCHAR(50) DEFAULT NULL 
        COMMENT 'Entity nguồn: orders, order_details, gl_entries, costs, tax_payments',
    SourceField VARCHAR(100) DEFAULT NULL 
        COMMENT 'Field cụ thể: TotalAmount, CompletedAt, CostDate...',
    FilterJson JSON DEFAULT NULL 
        COMMENT 'Filter khi query: {"transactionType":"sale","moneyChannel":"cash"}',
    AggregationType VARCHAR(20) DEFAULT NULL 
        COMMENT 'sum | count | avg | none (none = render per row)',
    
    -- ═══ COMPUTED FIELDS ═══
    FormulaExpression VARCHAR(500) DEFAULT NULL 
        COMMENT 'Công thức: revenue * vat_rate, revenue - cost',
    DependsOn JSON DEFAULT NULL 
        COMMENT 'Danh sách fields phụ thuộc: ["revenue","vat_rate"]',
    
    -- ═══ EXPORT POSITIONING ═══
    ExportColumn VARCHAR(10) DEFAULT NULL COMMENT 'Excel column: A, B, C...',
    SortOrder INT NOT NULL DEFAULT 0,
    IsRequired BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- Indexes & FKs
    CONSTRAINT fk_tfm_version FOREIGN KEY (TemplateVersionId) 
        REFERENCES AccountingTemplateVersions(TemplateVersionId),
    INDEX idx_tfm_version (TemplateVersionId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class AccountingTemplate
{
    public int TemplateId { get; set; }
    public string TemplateCode { get; set; } = null!;
    public string Name { get; set; } = null!;
    public string? Description { get; set; }
    public string ApplicableGroups { get; set; } = null!; // JSON
    public string? ApplicableMethods { get; set; }        // JSON
    public bool IsActive { get; set; }
    public DateTime CreatedAt { get; set; }
    
    public virtual ICollection<AccountingTemplateVersion> Versions { get; set; } = new List<AccountingTemplateVersion>();
}

public class AccountingTemplateVersion
{
    public int TemplateVersionId { get; set; }
    public int TemplateId { get; set; }
    
    public string VersionLabel { get; set; } = null!;
    public bool IsActive { get; set; }
    public DateOnly? EffectiveFrom { get; set; }
    public string? TemplateFileUrl { get; set; }
    public string? ChangeNotes { get; set; }
    
    public Guid? CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    
    public virtual AccountingTemplate Template { get; set; } = null!;
    public virtual ICollection<TemplateFieldMapping> FieldMappings { get; set; } = new List<TemplateFieldMapping>();
}

public class TemplateFieldMapping
{
    public int MappingId { get; set; }
    public int TemplateVersionId { get; set; }
    
    // Field identity
    public string FieldCode { get; set; } = null!;
    public string FieldLabel { get; set; } = null!;
    public string FieldType { get; set; } = null!;
    
    // Data source
    public string? SourceType { get; set; }
    public string? SourceEntity { get; set; }
    public string? SourceField { get; set; }
    public string? FilterJson { get; set; }
    public string? AggregationType { get; set; }
    
    // Computed
    public string? FormulaExpression { get; set; }
    public string? DependsOn { get; set; }
    
    // Export
    public string? ExportColumn { get; set; }
    public int SortOrder { get; set; }
    public bool IsRequired { get; set; }
    
    public virtual AccountingTemplateVersion TemplateVersion { get; set; } = null!;
}
```

**Ví dụ FieldMapping cho S1a (Sổ chi tiết bán hàng — Nhóm 1):**

```sql
-- S1a chỉ cần 4 cột đơn giản
INSERT INTO TemplateFieldMappings 
(TemplateVersionId, FieldCode, FieldLabel, FieldType, SourceType, SourceEntity, SourceField, AggregationType, ExportColumn, SortOrder, IsRequired) VALUES
(1, 'stt',         'STT',         'auto_increment', 'auto',  NULL,     NULL,          NULL,   'A', 1, TRUE),
(1, 'date',        'Ngày tháng',  'date',           'query', 'orders', 'CompletedAt', 'none', 'B', 2, TRUE),
(1, 'description', 'Nội dung',    'text',           'query', 'orders', 'OrderCode',   'none', 'C', 3, TRUE),
(1, 'revenue',     'Doanh thu',   'decimal',        'query', 'orders', 'TotalAmount', 'none', 'D', 4, TRUE);
```

### 3.8 AccountingBooks (Sổ kế toán đã tạo)

```sql
-- =============================================
-- ACCOUNTING BOOKS TABLE (Sổ kế toán — live view instances)
-- =============================================
CREATE TABLE AccountingBooks (
    BookId BIGINT AUTO_INCREMENT PRIMARY KEY,
    BusinessLocationId INT NOT NULL,
    PeriodId BIGINT NOT NULL,
    TemplateVersionId INT NOT NULL,
    
    -- ═══ CONTEXT (nhóm + cách tính Owner đã chọn) ═══
    GroupNumber TINYINT NOT NULL COMMENT 'Nhóm HKD: 1, 2, 3, 4',
    TaxMethod VARCHAR(20) DEFAULT NULL COMMENT 'method_1 | method_2 | exempt',
    RulesetId INT NOT NULL COMMENT 'Ruleset version dùng lúc tạo',
    
    -- ═══ BUSINESS TYPE FILTER ═══
    BusinessTypeId CHAR(36) DEFAULT NULL 
        COMMENT 'NULL = tất cả ngành trong location, NOT NULL = ngành cụ thể',
    
    -- ═══ STATUS ═══
    Status VARCHAR(20) NOT NULL DEFAULT 'active',
    -- 'active':    Đang sử dụng, data cập nhật realtime
    -- 'archived':  Không dùng nữa (owner đổi nhóm, tạo book mới)
    
    -- Timestamps
    CreatedByUserId CHAR(36) NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ArchivedAt DATETIME DEFAULT NULL,
    
    -- Indexes & FKs
    CONSTRAINT fk_book_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    CONSTRAINT fk_book_period FOREIGN KEY (PeriodId) 
        REFERENCES AccountingPeriods(PeriodId),
    CONSTRAINT fk_book_template_version FOREIGN KEY (TemplateVersionId) 
        REFERENCES AccountingTemplateVersions(TemplateVersionId),
    CONSTRAINT fk_book_ruleset FOREIGN KEY (RulesetId) 
        REFERENCES TaxRulesets(RulesetId),
    INDEX idx_book_location_period (BusinessLocationId, PeriodId),
    INDEX idx_book_status (Status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class AccountingBook
{
    public long BookId { get; set; }
    public int BusinessLocationId { get; set; }
    public long PeriodId { get; set; }
    public int TemplateVersionId { get; set; }
    
    // Context
    public int GroupNumber { get; set; }
    public string? TaxMethod { get; set; }
    public int RulesetId { get; set; }
    public Guid? BusinessTypeId { get; set; }
    
    // Status
    public string Status { get; set; } = "active";
    
    // Audit
    public Guid CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? ArchivedAt { get; set; }
    
    // Navigation
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual AccountingPeriod Period { get; set; } = null!;
    public virtual AccountingTemplateVersion TemplateVersion { get; set; } = null!;
    public virtual TaxRuleset Ruleset { get; set; } = null!;
    public virtual User CreatedByUser { get; set; } = null!;
}
```

> **Quan trọng**: `AccountingBooks` **không lưu data**. Nó là một "saved configuration" — khi Owner xem sổ, hệ thống query data realtime từ GL/Orders/Costs/TaxPayments rồi render theo `TemplateFieldMappings`. Data luôn cập nhật theo giao dịch mới nhất.

### 3.9 AccountingExports (Snapshot xuất sổ)

```sql
-- =============================================
-- ACCOUNTING EXPORTS TABLE (Lịch sử xuất sổ)
-- =============================================
CREATE TABLE AccountingExports (
    ExportId BIGINT AUTO_INCREMENT PRIMARY KEY,
    BookId BIGINT NOT NULL,
    
    -- Snapshot context (ghi lại tại thời điểm xuất)
    GroupNumber TINYINT NOT NULL,
    TaxMethod VARCHAR(20) DEFAULT NULL,
    RulesetVersion VARCHAR(20) NOT NULL,
    
    -- Data snapshot
    SummaryJson LONGTEXT NOT NULL 
        COMMENT 'Tóm tắt: tổng DT, tổng CP, thuế phải nộp, số dòng...',
    DataRowCount INT NOT NULL DEFAULT 0 COMMENT 'Số dòng dữ liệu',
    
    -- File output
    ExportFormat VARCHAR(10) NOT NULL COMMENT 'pdf | xlsx',
    FileUrl VARCHAR(500) DEFAULT NULL COMMENT 'URL file đã export',
    FilePublicId VARCHAR(255) DEFAULT NULL COMMENT 'Cloudinary public ID',
    
    -- Audit
    ExportedByUserId CHAR(36) NOT NULL,
    ExportedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    Notes TEXT DEFAULT NULL,
    
    -- Indexes & FKs
    CONSTRAINT fk_export_book FOREIGN KEY (BookId) 
        REFERENCES AccountingBooks(BookId),
    INDEX idx_export_book (BookId),
    INDEX idx_export_date (ExportedAt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class AccountingExport
{
    public long ExportId { get; set; }
    public long BookId { get; set; }
    
    // Snapshot context
    public int GroupNumber { get; set; }
    public string? TaxMethod { get; set; }
    public string RulesetVersion { get; set; } = null!;
    
    // Data snapshot
    public string SummaryJson { get; set; } = null!;
    public int DataRowCount { get; set; }
    
    // File
    public string ExportFormat { get; set; } = null!;
    public string? FileUrl { get; set; }
    public string? FilePublicId { get; set; }
    
    // Audit
    public Guid ExportedByUserId { get; set; }
    public DateTime ExportedAt { get; set; }
    public string? Notes { get; set; }
    
    // Navigation
    public virtual AccountingBook Book { get; set; } = null!;
    public virtual User ExportedByUser { get; set; } = null!;
}
```

### 3.10 TaxPayments (Thuế đã nộp)

```sql
-- =============================================
-- TAX PAYMENTS TABLE (Ghi nhận thuế đã nộp — cho S2d)
-- =============================================
CREATE TABLE TaxPayments (
    TaxPaymentId BIGINT AUTO_INCREMENT PRIMARY KEY,
    BusinessLocationId INT NOT NULL,
    PeriodId BIGINT DEFAULT NULL COMMENT 'Thuộc kỳ kế toán nào (optional)',
    
    -- Tax info
    TaxType VARCHAR(10) NOT NULL COMMENT 'VAT | PIT',
    Amount DECIMAL(15,2) NOT NULL COMMENT 'Số tiền đã nộp',
    PaidAt DATE NOT NULL COMMENT 'Ngày nộp',
    
    -- Payment details
    PaymentMethod VARCHAR(20) DEFAULT NULL COMMENT 'cash | bank',
    ReferenceNumber VARCHAR(100) DEFAULT NULL COMMENT 'Số biên lai / mã giao dịch',
    Notes TEXT DEFAULT NULL,
    
    -- Audit
    CreatedByUserId CHAR(36) NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    DeletedAt DATETIME DEFAULT NULL COMMENT 'Soft delete',
    
    -- Indexes & FKs
    CONSTRAINT fk_taxpay_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    CONSTRAINT fk_taxpay_period FOREIGN KEY (PeriodId) 
        REFERENCES AccountingPeriods(PeriodId),
    INDEX idx_taxpay_location (BusinessLocationId),
    INDEX idx_taxpay_type (TaxType),
    INDEX idx_taxpay_period (PeriodId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class TaxPayment
{
    public long TaxPaymentId { get; set; }
    public int BusinessLocationId { get; set; }
    public long? PeriodId { get; set; }
    
    public string TaxType { get; set; } = null!;
    public decimal Amount { get; set; }
    public DateOnly PaidAt { get; set; }
    public string? PaymentMethod { get; set; }
    public string? ReferenceNumber { get; set; }
    public string? Notes { get; set; }
    
    public Guid CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? DeletedAt { get; set; }
    
    // Navigation
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual AccountingPeriod? Period { get; set; }
    public virtual User CreatedByUser { get; set; } = null!;
}
```

---

## 4. General Ledger Flow

### 4.1 Khi nào tạo GL entries?

GL entries được tạo **tự động** bởi hệ thống khi xảy ra các event tài chính:

| Event | TransactionType | ReferenceType | Trigger |
|-------|----------------|---------------|---------|
| Order completed | `sale` | `order` | `OrderService.CompleteAsync()` |
| Order cancelled (was completed) | `sale` (reversal) | `order` | `OrderService.CancelAsync()` |
| Import confirmed | `import_cost` | `import` | `ImportService.ConfirmAsync()` |
| Import cancelled (was confirmed) | `import_cost` (reversal) | `import` | `ImportService.CancelAsync()` |
| Manual cost created | `manual_cost` | `cost` | `CostService.CreateAsync()` |
| Manual cost deleted | `manual_cost` (reversal) | `cost` | `CostService.DeleteAsync()` |
| Debt payment recorded | `debt_payment` | `debtor_payment` | `DebtorService.RecordPaymentAsync()` |
| Tax payment recorded | `tax_payment` | `tax_payment` | `TaxPaymentService.CreateAsync()` |

### 4.2 Entry Generation Rules

#### RULE-GL-01: Order Completed → Sale Entries

Khi order chuyển sang `completed`, tạo GL entries theo từng kênh thanh toán:

```csharp
public async Task RecordOrderCompleted(Order order)
{
    var entries = new List<GeneralLedgerEntry>();
    
    // 1 entry per payment channel (chỉ tạo nếu amount > 0)
    if (order.CashAmount > 0)
    {
        entries.Add(new GeneralLedgerEntry
        {
            BusinessLocationId = order.BusinessLocationId,
            TransactionType = GLTransactionTypes.Sale,
            ReferenceType = GLReferenceTypes.Order,
            ReferenceId = order.OrderId,
            EntryDate = DateOnly.FromDateTime(order.CompletedAt!.Value),
            Description = $"{order.OrderCode}: Bán hàng (tiền mặt)",
            DebitAmount = order.CashAmount,
            CreditAmount = 0,
            MoneyChannel = MoneyChannels.Cash,
            IsReversal = false
        });
    }
    
    if (order.BankAmount > 0)
    {
        entries.Add(new GeneralLedgerEntry
        {
            // ... tương tự, MoneyChannel = MoneyChannels.Bank
            DebitAmount = order.BankAmount,
            Description = $"{order.OrderCode}: Bán hàng (chuyển khoản)",
            MoneyChannel = MoneyChannels.Bank
        });
    }
    
    if (order.DebtAmount > 0)
    {
        entries.Add(new GeneralLedgerEntry
        {
            // ... tương tự, MoneyChannel = MoneyChannels.Debt
            DebitAmount = order.DebtAmount,
            Description = $"{order.OrderCode}: Bán hàng (ghi nợ {order.Debtor?.Name})",
            MoneyChannel = MoneyChannels.Debt
        });
    }
    
    await _unitOfWork.GeneralLedgerEntries.AddRangeAsync(entries);
}
```

#### RULE-GL-02: Order Cancelled → Reversal Entries

Khi cancel order đã completed, tạo **reversal entries** — ngược chiều entry gốc:

```csharp
public async Task RecordOrderCancelled(Order order)
{
    // Tìm tất cả GL entries gốc của order này
    var originalEntries = await _unitOfWork.GeneralLedgerEntries
        .FindAllAsync(e => e.ReferenceType == GLReferenceTypes.Order 
                        && e.ReferenceId == order.OrderId
                        && !e.IsReversal);
    
    var reversals = originalEntries.Select(original => new GeneralLedgerEntry
    {
        BusinessLocationId = original.BusinessLocationId,
        TransactionType = original.TransactionType,
        ReferenceType = original.ReferenceType,
        ReferenceId = original.ReferenceId,
        EntryDate = DateOnly.FromDateTime(DateTime.UtcNow),
        Description = $"[HỦY] {original.Description}",
        // Đảo ngược: Debit ↔ Credit
        DebitAmount = original.CreditAmount,
        CreditAmount = original.DebitAmount,
        MoneyChannel = original.MoneyChannel,
        IsReversal = true,
        ReversedEntryId = original.EntryId
    }).ToList();
    
    await _unitOfWork.GeneralLedgerEntries.AddRangeAsync(reversals);
}
```

> **Nguyên tắc**: Không bao giờ sửa hoặc xóa GL entry đã tạo. Luôn tạo reversal entry để hủy. Điều này đảm bảo audit trail đầy đủ.

#### RULE-GL-03: Import Confirmed → Cost Entry

```csharp
public async Task RecordImportConfirmed(Import import)
{
    if (import.TotalAmount <= 0) return;
    
    var entry = new GeneralLedgerEntry
    {
        BusinessLocationId = import.BusinessLocationId,
        TransactionType = GLTransactionTypes.ImportCost,
        ReferenceType = GLReferenceTypes.Import,
        ReferenceId = import.ImportId,
        EntryDate = DateOnly.FromDateTime(import.ConfirmedAt!.Value),
        Description = $"{import.ImportCode}: Nhập hàng" + 
            (import.Supplier != null ? $" từ {import.Supplier}" : ""),
        DebitAmount = 0,
        CreditAmount = import.TotalAmount,
        MoneyChannel = null, // Owner update sau qua Cost.PaymentMethod
        IsReversal = false
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddAsync(entry);
}
```

#### RULE-GL-04: Debt Payment → Cash-in Entry

```csharp
public async Task RecordDebtPayment(DebtorPaymentTransaction payment, Debtor debtor)
{
    var entry = new GeneralLedgerEntry
    {
        BusinessLocationId = debtor.BusinessLocationId,
        TransactionType = GLTransactionTypes.DebtPayment,
        ReferenceType = GLReferenceTypes.DebtorPayment,
        ReferenceId = payment.TransactionId,
        EntryDate = DateOnly.FromDateTime(payment.PaidAt),
        Description = $"Thu nợ {debtor.Name}: {payment.Amount:N0}đ ({payment.PaymentMethod})",
        DebitAmount = payment.Amount,   // Tiền VÀO
        CreditAmount = 0,
        MoneyChannel = payment.PaymentMethod, // 'cash' hoặc 'bank'
        IsReversal = false
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddAsync(entry);
}
```

> **Lưu ý**: Thu nợ **không phải doanh thu** — doanh thu đã ghi nhận lúc Order completed (với channel = debt). Thu nợ là tiền mặt/bank thực nhận, entry Debit để ghi nhận cash-in.

#### RULE-GL-05: Tax Payment → Cash-out Entry

```csharp
public async Task RecordTaxPayment(TaxPayment taxPayment)
{
    var entry = new GeneralLedgerEntry
    {
        BusinessLocationId = taxPayment.BusinessLocationId,
        TransactionType = GLTransactionTypes.TaxPayment,
        ReferenceType = GLReferenceTypes.TaxPayment,
        ReferenceId = taxPayment.TaxPaymentId,
        EntryDate = taxPayment.PaidAt,
        Description = $"Nộp thuế {taxPayment.TaxType} " +
            (taxPayment.ReferenceNumber != null ? $"(#{taxPayment.ReferenceNumber})" : ""),
        DebitAmount = 0,
        CreditAmount = taxPayment.Amount, // Tiền RA
        MoneyChannel = taxPayment.PaymentMethod,
        IsReversal = false
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddAsync(entry);
}
```

### 4.3 Tổng hợp quy tắc Debit/Credit

| TransactionType | DebitAmount (tiền VÀO) | CreditAmount (tiền RA) | MoneyChannel |
|:----------------|:----------------------:|:----------------------:|:------------:|
| `sale` | ✅ TotalAmount | — | cash / bank / debt |
| `sale` (reversal) | — | ✅ TotalAmount | cash / bank / debt |
| `import_cost` | — | ✅ TotalAmount | cash / bank / NULL |
| `import_cost` (reversal) | ✅ TotalAmount | — | cash / bank / NULL |
| `manual_cost` | — | ✅ Amount | cash / bank |
| `manual_cost` (reversal) | ✅ Amount | — | cash / bank |
| `debt_payment` | ✅ PaymentAmount | — | cash / bank |
| `tax_payment` | — | ✅ Amount | cash / bank |

---

## 5. Cost Flow

### 5.1 Auto-generated Costs (từ Import)

Khi Import chuyển sang `CONFIRMED`, hệ thống **tự động tạo** Cost record:

```csharp
// RULE-COST-01: Auto tạo Cost khi Import CONFIRMED
public async Task OnImportConfirmed(Import import)
{
    var cost = new Cost
    {
        BusinessLocationId = import.BusinessLocationId,
        CostType = CostTypes.Import,
        ImportId = import.ImportId,
        Description = $"Nhập hàng {import.ImportCode}" +
            (import.Supplier != null ? $" từ {import.Supplier}" : ""),
        Amount = import.TotalAmount,
        CostDate = DateOnly.FromDateTime(import.ConfirmedAt ?? import.CreatedAt),
        PaymentMethod = null, // Owner update sau nếu muốn
        CreatedByUserId = import.ConfirmedByUserId!.Value,
    };
    
    await _unitOfWork.Costs.AddAsync(cost);
    
    // Đồng thời tạo GL entry (RULE-GL-03)
    await _glService.RecordImportConfirmed(import);
}
```

### 5.2 Manual Costs (Owner tự khai)

```yaml
POST /api/v1/locations/{locationId}/costs
Authorization: Bearer {token}

Request:
{
  "costType": "rent",
  "description": "Thuê mặt bằng tháng 3/2026",
  "amount": 5000000,
  "costDate": "2026-03-01",
  "paymentMethod": "bank",
  "documentUrl": null
}

Response (201 Created):
{
  "costId": 15,
  "costType": "rent",
  "description": "Thuê mặt bằng tháng 3/2026",
  "amount": 5000000,
  "costDate": "2026-03-01",
  "paymentMethod": "bank",
  "importId": null,
  "createdAt": "2026-03-01T08:00:00Z"
}
```

### 5.3 Business Rules

| Rule | Mô tả |
|------|-------|
| **RULE-COST-01** | Import CONFIRMED → auto tạo Cost (`CostType=import`, `ImportId=X`) + GL entry |
| **RULE-COST-02** | Import CANCELLED → soft delete Cost liên kết + GL reversal entry |
| **RULE-COST-03** | Owner tự tạo Cost cho chi phí khác (tiền thuê, điện nước, lương…) → tạo GL entry |
| **RULE-COST-04** | Cost auto từ Import → **readonly** (sửa/xóa phải thông qua Import cancel) |
| **RULE-COST-05** | Only Owner tạo/sửa/xóa manual costs |
| **RULE-COST-06** | Xóa manual cost → soft delete Cost + GL reversal entry |

---

## 6. Accounting Period Flow

### 6.1 Create Period

Periods có thể được tạo **tự động** (system job đầu quý/năm) hoặc **thủ công** bởi Owner:

```yaml
POST /api/v1/locations/{locationId}/accounting/periods
Authorization: Bearer {token}

Request:
{
  "periodType": "quarter",
  "year": 2026,
  "quarter": 1
}

Response (201 Created):
{
  "periodId": 1,
  "periodType": "quarter",
  "year": 2026,
  "quarter": 1,
  "startDate": "2026-01-01",
  "endDate": "2026-03-31",
  "status": "open"
}
```

### 6.2 Finalize Period

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

### 6.3 Reopen Period

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

## 7. Rule Engine Module

### 7.1 Architecture

```markdown
┌───────── RULE ENGINE SERVICE ─────────┐
│                                        │
│  Input:                                │
│  ├── ownerUserId (or locationId)       │
│  ├── year                              │
│  └── quarter (optional)               │
│                                        │
│  Process:                              │
│  ├── 1. Fetch active TaxRuleset        │
│  ├── 2. Query DT lũy kế từ GL/Orders  │
│  ├── 3. Match TaxGroupRules            │
│  │      (MinRevenue ≤ DT < MaxRevenue) │
│  ├── 4. Lookup IndustryTaxRates        │
│  └── 5. Build result                   │
│                                        │
│  Output:                               │
│  ├── suggestedGroup (1-4)              │
│  ├── allowedTaxMethods                 │
│  ├── requiredBooks (S1a/S2a/...)       │
│  ├── taxRates per businessType         │
│  ├── warnings (nếu gần ngưỡng nhóm)   │
│  └── rulesetVersion (audit)            │
│                                        │
└────────────────────────────────────────┘
```

### 7.2 Evaluation Logic

```csharp
public class RuleEngineService : IRuleEngineService
{
    /// <summary>
    /// Gợi ý nhóm HKD dựa trên DT lũy kế.
    /// Không hardcode nhóm/ngưỡng — tất cả từ data.
    /// </summary>
    public async Task<GroupEvaluationResult> EvaluateGroupAsync(
        int businessLocationId, int year, int? quarter = null)
    {
        // 1. Lấy active ruleset
        var ruleset = await _rulesetRepo.GetActiveAsync();
        if (ruleset == null) throw new InvalidOperationException("No active tax ruleset");
        
        // 2. Tính DT lũy kế của location trong khoảng thời gian
        DateOnly startDate, endDate;
        if (quarter.HasValue)
        {
            startDate = new DateOnly(year, (quarter.Value - 1) * 3 + 1, 1);
            endDate = startDate.AddMonths(3).AddDays(-1);
        }
        else
        {
            startDate = new DateOnly(year, 1, 1);
            endDate = new DateOnly(year, 12, 31);
        }
        
        var revenue = await _glRepo.CalculateRevenueAsync(
            businessLocationId, startDate, endDate);
        // revenue = { totalRevenue, revenueByBusinessType: [{btId, amount}] }
        
        // 3. Annualize nếu chưa hết năm (ước tính cho gợi ý)
        var monthsElapsed = CalculateMonthsElapsed(startDate, DateOnly.FromDateTime(DateTime.UtcNow));
        decimal annualizedRevenue = monthsElapsed > 0 && monthsElapsed < 12
            ? revenue.TotalRevenue * (12.0m / monthsElapsed)
            : revenue.TotalRevenue;
        
        // 4. Match group (NO if/else hardcode)
        var groups = await _groupRuleRepo.GetByRulesetAsync(ruleset.RulesetId);
        var matchedGroup = groups
            .OrderBy(g => g.SortOrder)
            .FirstOrDefault(g =>
                annualizedRevenue >= g.MinRevenue &&
                (g.MaxRevenue == null || annualizedRevenue < g.MaxRevenue));
        
        // 5. Lookup industry tax rates
        var industryRates = await _taxRateRepo
            .GetByRulesetAsync(ruleset.RulesetId);
        
        var breakdown = revenue.RevenueByBusinessType.Select(r =>
        {
            var vatRate = industryRates
                .FirstOrDefault(ir => ir.BusinessTypeId == r.BusinessTypeId 
                    && ir.TaxType == "VAT")?.TaxRate ?? 0;
            var pitM1Rate = industryRates
                .FirstOrDefault(ir => ir.BusinessTypeId == r.BusinessTypeId 
                    && ir.TaxType == "PIT_METHOD_1")?.TaxRate ?? 0;
            
            return new IndustryBreakdown
            {
                BusinessTypeId = r.BusinessTypeId,
                Revenue = r.Amount,
                VatRate = vatRate,
                PitMethod1Rate = pitM1Rate,
                VatAmount = matchedGroup.VatExempt ? 0 : r.Amount * vatRate,
                PitMethod1Amount = matchedGroup.PitExempt ? 0 
                    : Math.Max(0, r.Amount - (matchedGroup.RevenueDeduction ?? 0)) * pitM1Rate
            };
        }).ToList();
        
        // 6. Build warnings
        var warnings = new List<string>();
        if (matchedGroup.MaxRevenue.HasValue)
        {
            var headroom = matchedGroup.MaxRevenue.Value - annualizedRevenue;
            if (headroom < matchedGroup.MaxRevenue.Value * 0.1m)
                warnings.Add($"DT dự kiến gần ngưỡng Nhóm {matchedGroup.GroupNumber + 1}");
        }
        
        return new GroupEvaluationResult
        {
            RulesetId = ruleset.RulesetId,
            RulesetVersion = ruleset.Version,
            ActualRevenue = revenue.TotalRevenue,
            AnnualizedRevenue = annualizedRevenue,
            IsAnnualized = monthsElapsed < 12,
            SuggestedGroup = matchedGroup.GroupNumber,
            SuggestedGroupName = matchedGroup.GroupName,
            AllowedTaxMethods = JsonSerializer.Deserialize<List<string>>(matchedGroup.AllowedTaxMethods),
            DefaultTaxMethod = matchedGroup.DefaultTaxMethod,
            RequiredBooks = JsonSerializer.Deserialize<Dictionary<string, List<string>>>(matchedGroup.RequiredBooksJson),
            VatExempt = matchedGroup.VatExempt,
            PitExempt = matchedGroup.PitExempt,
            PitRateMethod2 = matchedGroup.PitRateMethod2,
            RevenueDeduction = matchedGroup.RevenueDeduction,
            IndustryBreakdown = breakdown,
            Warnings = warnings
        };
    }
}
```

### 7.3 API: Get Group Suggestion

```yaml
GET /api/v1/locations/{locationId}/accounting/group-suggestion?year=2026&quarter=1
Authorization: Bearer {token}

Response:
{
  "rulesetVersion": "1.0.0",
  "actualRevenue": 620000000,
  "annualizedRevenue": 826666667,
  "isAnnualized": true,
  "suggestedGroup": 2,
  "suggestedGroupName": "Nhóm 2",
  "allowedTaxMethods": ["method_1", "method_2"],
  "defaultTaxMethod": "method_1",
  "requiredBooks": {
    "method_1": ["S2a"],
    "method_2": ["S2b", "S2c", "S2d", "S2e"]
  },
  "vatExempt": false,
  "pitExempt": false,
  "revenueDeduction": 500000000,
  "industryBreakdown": [
    {
      "businessTypeId": "bt-retail",
      "businessTypeName": "Bán lẻ hàng hóa",
      "revenue": 500000000,
      "vatRate": 0.01,
      "vatAmount": 5000000,
      "pitMethod1Rate": 0.005,
      "pitMethod1Amount": 600000
    },
    {
      "businessTypeId": "bt-service",
      "businessTypeName": "Dịch vụ",
      "revenue": 120000000,
      "vatRate": 0.05,
      "vatAmount": 6000000,
      "pitMethod1Rate": 0.02,
      "pitMethod1Amount": 2400000
    }
  ],
  "warnings": []
}
```

> **Lưu ý**: API này chỉ **gợi ý** — không tạo gì cả. Owner xem kết quả rồi quyết định tạo AccountingBook với nhóm + cách tính mong muốn.

---

## 8. Accounting Book Generation Flow

### 8.1 Flow tổng quan

```markdown
Owner xem gợi ý Rule Engine
        │
        ▼
Owner chọn nhóm + cách tính thuế
(có thể khác gợi ý, tùy Owner)
        │
        ▼
┌───────────────────────────────────┐
│ HỆ THỐNG TẠO AccountingBook      │
│                                   │
│ - Xác định TemplateVersion active │
│   cho mẫu sổ tương ứng           │
│ - Location đa ngành?             │
│   → Tạo 1 book per BusinessType  │
│   → Hoặc 1 book tổng (option)    │
│ - Lưu context: group, method,    │
│   ruleset version, businessType   │
└───────────┬───────────────────────┘
            │
            ▼
┌───────────────────────────────────┐
│ BOOK LIVE VIEW                    │
│                                   │
│ Data query realtime:              │
│ - S1a/S2a/S2b → từ Orders        │
│ - S2c → từ Costs                  │
│ - S2d → từ calculated tax +      │
│         TaxPayments               │
│ - S2e → từ GL entries             │
│                                   │
│ → Fill vào template theo          │
│   TemplateFieldMappings           │
│ → Data tự cập nhật khi có        │
│   giao dịch mới                   │
└───────────┬───────────────────────┘
            │
     Owner xem / review
            │
       Sẵn sàng?
        │       │
       Yes     No → Tiếp tục kinh doanh, 
        │           data tự cập nhật
        ▼
┌───────────────────────────────────┐
│ EXPORT (Snapshot)                 │
│                                   │
│ - Render data vào template file   │
│ - Tạo file PDF/Excel             │
│ - Lưu SummaryJson (snapshot)      │
│ - Upload file → Cloudinary        │
│ - Ghi AccountingExport record     │
│ - Ghi audit log                   │
└───────────────────────────────────┘
```

### 8.2 Create Book API

```yaml
POST /api/v1/locations/{locationId}/accounting/books
Authorization: Bearer {token}

Request:
{
  "periodId": 1,
  "groupNumber": 2,
  "taxMethod": "method_1",
  "businessTypeId": null          # NULL = tất cả ngành, hệ thống tự tách
}

Response (201 Created):
{
  "bookId": 15,
  "periodId": 1,
  "templateCode": "S2a",
  "templateVersionLabel": "v1.0",
  "groupNumber": 2,
  "taxMethod": "method_1",
  "rulesetVersion": "1.0.0",
  "status": "active",
  "createdAt": "2026-04-01T10:00:00Z"
}
```

```csharp
public async Task<AccountingBookDto> CreateBookAsync(
    int locationId, Guid userId, CreateBookRequest request)
{
    // 1. Validate period exists and is open/reopened
    var period = await _unitOfWork.AccountingPeriods.GetByIdAsync(request.PeriodId);
    if (period == null || period.BusinessLocationId != locationId)
        throw new NotFoundException("Period not found");
    
    // 2. Get active ruleset
    var ruleset = await _unitOfWork.TaxRulesets.GetActiveAsync();
    
    // 3. Get group rule to determine required books
    var groupRule = await _unitOfWork.TaxGroupRules
        .GetByGroupAsync(ruleset.RulesetId, request.GroupNumber);
    
    var requiredBooks = JsonSerializer.Deserialize<Dictionary<string, List<string>>>(
        groupRule.RequiredBooksJson);
    var methodKey = request.TaxMethod ?? "default";
    var bookCodes = requiredBooks.ContainsKey(methodKey) 
        ? requiredBooks[methodKey] 
        : requiredBooks["default"];
    
    // 4. Create book for each required template
    var books = new List<AccountingBook>();
    foreach (var bookCode in bookCodes)
    {
        var template = await _unitOfWork.AccountingTemplates
            .GetByCodeAsync(bookCode);
        var activeVersion = template.Versions.First(v => v.IsActive);
        
        // Nếu location đa ngành + book cần tách (S2a) → tạo per BusinessType
        if (request.BusinessTypeId == null && NeedsSplitByBusinessType(bookCode))
        {
            var businessTypes = await GetLocationBusinessTypesAsync(locationId);
            foreach (var bt in businessTypes)
            {
                books.Add(CreateBookEntity(locationId, request, activeVersion, ruleset, bt.BusinessTypeId, userId));
            }
        }
        else
        {
            books.Add(CreateBookEntity(locationId, request, activeVersion, ruleset, request.BusinessTypeId, userId));
        }
    }
    
    await _unitOfWork.AccountingBooks.AddRangeAsync(books);
    
    // 5. Audit log
    await _auditService.LogAsync(request.PeriodId, "book_created", userId, new
    {
        groupNumber = request.GroupNumber,
        taxMethod = request.TaxMethod,
        bookCodes = bookCodes
    });
    
    await _unitOfWork.SaveChangesAsync();
    return _mapper.Map<AccountingBookDto>(books.First());
}
```

### 8.3 View Book Data (Live)

```yaml
GET /api/v1/locations/{locationId}/accounting/books/{bookId}/data
Authorization: Bearer {token}

Response:
{
  "bookId": 15,
  "templateCode": "S2a",
  "periodLabel": "Q1/2026",
  "groupNumber": 2,
  "taxMethod": "method_1",
  "lastUpdated": "2026-03-28T14:30:00Z",
  
  "columns": [
    { "fieldCode": "stt", "label": "STT" },
    { "fieldCode": "date", "label": "Ngày" },
    { "fieldCode": "description", "label": "Nội dung" },
    { "fieldCode": "revenue", "label": "Doanh thu" },
    { "fieldCode": "vat_rate", "label": "Tỷ lệ GTGT" },
    { "fieldCode": "vat_amount", "label": "Thuế GTGT" }
  ],
  
  "rows": [
    { "stt": 1, "date": "2026-01-15", "description": "ORD-20260115-001", "revenue": 950000, "vat_rate": "1%", "vat_amount": 9500 },
    { "stt": 2, "date": "2026-01-15", "description": "ORD-20260115-002", "revenue": 2100000, "vat_rate": "1%", "vat_amount": 21000 }
  ],
  
  "summary": {
    "totalRevenue": 620000000,
    "totalVat": 6200000,
    "totalPit": 600000,
    "rowCount": 342
  }
}
```

### 8.4 Export Book

```yaml
POST /api/v1/locations/{locationId}/accounting/books/{bookId}/export
Authorization: Bearer {token}

Request:
{
  "format": "xlsx",      # 'xlsx' | 'pdf'
  "notes": "Xuất bổ sung lần 2 — sau khi cập nhật 3 đơn thiếu"
}

Response:
{
  "exportId": 8,
  "bookId": 15,
  "groupNumber": 2,
  "rulesetVersion": "1.0.0",
  "format": "xlsx",
  "fileUrl": "https://res.cloudinary.com/.../s2a_q1_2026_v2.xlsx",
  "summary": {
    "totalRevenue": 625000000,
    "totalVat": 6250000,
    "rowCount": 345
  },
  "dataRowCount": 345,
  "exportedAt": "2026-04-10T09:30:00Z",
  "notes": "Xuất bổ sung lần 2 — sau khi cập nhật 3 đơn thiếu"
}
```

---

## 9. TT152 Book Specifications (S1a, S2a–S2e)

### 9.1 S1a-HKD — Sổ chi tiết bán hàng (Nhóm 1)

**Áp dụng**: Nhóm 1 (DT < 500 triệu/năm) — miễn thuế GTGT & TNCN.

| STT | Ngày tháng | Nội dung (Diễn giải) | Doanh thu bán hàng |
|:---:|:----------:|---------------------|-------------------:|
| 1 | 15/01/2026 | ORD-20260115-001: Bán Xi măng HT 50 bao | 4,750,000 |
| 2 | 15/01/2026 | ORD-20260115-003: Bán Cát xây dựng 200 kg | 600,000 |
| ... | ... | ... | ... |
| | | **Cộng tháng 01** | **45,200,000** |
| ... | ... | ... | ... |
| | | **Cộng quý I** | **120,500,000** |

**Data source**: `Orders WHERE Status = 'completed' AND CompletedAt BETWEEN startDate AND endDate`

**Rendering logic**:

```sql
SELECT 
    ROW_NUMBER() OVER (ORDER BY o.CompletedAt) AS STT,
    DATE(o.CompletedAt) AS NgayThang,
    CONCAT(o.OrderCode, ': ', GROUP_CONCAT(od.ProductName SEPARATOR ', ')) AS NoiDung,
    o.TotalAmount AS DoanhThu
FROM Orders o
JOIN OrderDetails od ON o.OrderId = od.OrderId
WHERE o.BusinessLocationId = @locationId
  AND o.Status = 'completed'
  AND o.CompletedAt BETWEEN @startDate AND @endDate
GROUP BY o.OrderId
ORDER BY o.CompletedAt;
```

### 9.2 S2a-HKD — Sổ chi tiết bán hàng theo ngành (Nhóm 2, Cách 1)

**Áp dụng**: Nhóm 2 (500 triệu – 3 tỷ), Cách 1 tính thuế (% DT theo ngành).

**Lưu ý**: Khi location có nhiều ngành → hệ thống tạo **mỗi ngành 1 file S2a riêng** (theo DD-01).

| STT | Ngày | Nội dung | Doanh thu | Thuế GTGT (1%) | Thuế TNCN (0.5%) |
|:---:|:----:|---------|----------:|:--------------:|:----------------:|
| 1 | 15/01 | ORD-001: Xi măng HT 50 bao | 4,750,000 | 47,500 | 23,750 |
| 2 | 16/01 | ORD-005: Sắt thép 100 kg | 3,200,000 | 32,000 | 16,000 |
| ... | ... | ... | ... | ... | ... |
| | | **Cộng quý I** | **500,000,000** | **5,000,000** | **0** |

> **Thuế TNCN Cách 1**: `(DT ngành - 500 triệu) × tỷ lệ %`. Phần DT ≤ 500 triệu → TNCN = 0. Lưu ý: mức trừ 500 triệu chỉ áp dụng **1 lần** cho toàn HKD, không phải mỗi ngành.

**Data source**: `Orders → OrderDetails → Product.BusinessTypeId + IndustryTaxRates`

**Rendering logic**:

```sql
SELECT 
    ROW_NUMBER() OVER (ORDER BY o.CompletedAt) AS STT,
    DATE(o.CompletedAt) AS Ngay,
    CONCAT(o.OrderCode, ': ', od.ProductName, ' ', od.Quantity, ' ', od.Unit) AS NoiDung,
    od.Amount AS DoanhThu,
    od.Amount * itr_vat.TaxRate AS ThueGTGT,
    -- TNCN tính trên tổng DT ngành vượt 500tr, không tính per row
    -- → Computed ở summary, không hiện per row
    NULL AS ThueTNCN
FROM Orders o
JOIN OrderDetails od ON o.OrderId = od.OrderId
JOIN Products p ON od.ProductId = p.ProductId
JOIN IndustryTaxRates itr_vat ON itr_vat.BusinessTypeId = p.BusinessTypeId 
    AND itr_vat.TaxType = 'VAT' AND itr_vat.RulesetId = @rulesetId
WHERE o.BusinessLocationId = @locationId
  AND o.Status = 'completed'
  AND o.CompletedAt BETWEEN @startDate AND @endDate
  AND p.BusinessTypeId = @businessTypeId  -- Filter theo ngành
ORDER BY o.CompletedAt;
```

### 9.3 S2b-HKD — Sổ chi tiết bán hàng (Nhóm 2 Cách 2, Nhóm 3-4)

**Áp dụng**: Nhóm 2 (Cách 2) + Nhóm 3 + Nhóm 4

| STT | Ngày | Mã đơn | Khách hàng | Sản phẩm | ĐVT | SL | Đơn giá | Thành tiền | PTTT |
|:---:|:----:|:------:|-----------|---------|:---:|---:|--------:|-----------:|:----:|
| 1 | 15/01 | ORD-001 | Anh Ba | Xi măng HT | Bao | 50 | 95,000 | 4,750,000 | TM |
| 2 | 15/01 | ORD-001 | Anh Ba | Cát xây dựng | Kg | 200 | 3,000 | 600,000 | TM |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| | | | | | | | **Cộng quý I** | **620,000,000** | |

**PTTT**: TM = Tiền mặt, CK = Chuyển khoản, NỢ = Ghi nợ, HH = Hỗn hợp

**Data source**: `Orders → OrderDetails → SaleItems → Products`

### 9.4 S2c-HKD — Sổ chi tiết chi phí (Nhóm 2 Cách 2, Nhóm 3-4)

| STT | Ngày | Nội dung | Loại chi phí | Số tiền | Chứng từ |
|:---:|:----:|---------|:------------:|--------:|:--------:|
| 1 | 10/01 | PNK-001: Nhập Xi măng từ Công ty ABC | Nhập hàng | 8,500,000 | Có HĐ |
| 2 | 15/01 | Thuê mặt bằng T1/2026 | Thuê | 5,000,000 | Có HĐ |
| 3 | 20/01 | Tiền điện T1/2026 | Điện nước | 1,200,000 | Có HĐ |
| ... | ... | ... | ... | ... | ... |
| | | | **Cộng quý I** | **85,000,000** | |

**Data source**: `Costs WHERE DeletedAt IS NULL AND CostDate BETWEEN startDate AND endDate`

### 9.5 S2d-HKD — Sổ theo dõi nghĩa vụ thuế (Nhóm 2 Cách 2, Nhóm 3-4)

| Kỳ thuế | Loại thuế | DT chịu thuế | Chi phí | Thu nhập tính thuế | Thuế suất | Phải nộp | Đã nộp | Còn nợ |
|:-------:|:---------:|------------:|--------:|------------------:|:---------:|---------:|-------:|-------:|
| Q1/2026 | GTGT | 620,000,000 | — | — | 1% | 6,200,000 | 6,200,000 | 0 |
| Q1/2026 | TNCN | 620,000,000 | 85,000,000 | 535,000,000 | 15% | 80,250,000 | 50,000,000 | 30,250,000 |

**Data sources**:
- DT chịu thuế: `Orders (completed), aggregated`
- Chi phí: `Costs, aggregated`
- Phải nộp: `Computed by Rule Engine` (DT × VatRate, hoặc (DT - CP) × PitRateMethod2)
- Đã nộp: `TaxPayments`
- Còn nợ: `Phải nộp - Đã nộp`

### 9.6 S2e-HKD — Sổ theo dõi tình hình thanh toán (Nhóm 2 Cách 2, Nhóm 3-4)

| STT | Ngày | Nội dung | Thu TM | Thu CK | Chi TM | Chi CK | Ghi nợ | Thu nợ |
|:---:|:----:|---------|-------:|-------:|-------:|-------:|-------:|-------:|
| 1 | 15/01 | ORD-001: Bán hàng | 600,000 | — | — | — | 200,000 | — |
| 2 | 16/01 | PNK-002: Nhập hàng | — | — | 8,500,000 | — | — | — |
| 3 | 20/01 | Thu nợ Anh Ba | 300,000 | — | — | — | — | 300,000 |
| 4 | 25/01 | Thuê mặt bằng | — | — | — | 5,000,000 | — | — |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |
| | | **Cộng quý I** | **xx** | **xx** | **xx** | **xx** | **xx** | **xx** |

**Data source**: `GeneralLedgerEntries` — render trực tiếp từ GL:

```sql
SELECT 
    ROW_NUMBER() OVER (ORDER BY gle.EntryDate, gle.EntryId) AS STT,
    gle.EntryDate AS Ngay,
    gle.Description AS NoiDung,
    
    -- Thu tiền mặt
    CASE WHEN gle.MoneyChannel = 'cash' AND gle.DebitAmount > 0 
              AND gle.TransactionType != 'debt_payment'
         THEN gle.DebitAmount ELSE NULL END AS ThuTM,
    
    -- Thu chuyển khoản
    CASE WHEN gle.MoneyChannel = 'bank' AND gle.DebitAmount > 0 
              AND gle.TransactionType != 'debt_payment'
         THEN gle.DebitAmount ELSE NULL END AS ThuCK,
    
    -- Chi tiền mặt
    CASE WHEN gle.MoneyChannel = 'cash' AND gle.CreditAmount > 0 
         THEN gle.CreditAmount ELSE NULL END AS ChiTM,
    
    -- Chi chuyển khoản
    CASE WHEN gle.MoneyChannel = 'bank' AND gle.CreditAmount > 0 
         THEN gle.CreditAmount ELSE NULL END AS ChiCK,
    
    -- Ghi nợ (bán hàng ghi nợ)
    CASE WHEN gle.MoneyChannel = 'debt' AND gle.TransactionType = 'sale'
         THEN gle.DebitAmount ELSE NULL END AS GhiNo,
    
    -- Thu nợ (khách trả nợ)
    CASE WHEN gle.TransactionType = 'debt_payment'
         THEN gle.DebitAmount ELSE NULL END AS ThuNo

FROM GeneralLedgerEntries gle
WHERE gle.BusinessLocationId = @locationId
  AND gle.EntryDate BETWEEN @startDate AND @endDate
ORDER BY gle.EntryDate, gle.EntryId;
```

---

## 10. Cash Flow & Dashboard

### 10.1 Cash Flow Tracking

Cash flow **query trực tiếp từ GL** — không cần table riêng:

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

-- Kết quả:
-- | Channel | TotalIn     | TotalOut   | Net         |
-- |---------|-------------|------------|-------------|
-- | cash    | 450,000,000 | 85,000,000 | 365,000,000 |
-- | bank    | 120,000,000 | 15,000,000 | 105,000,000 |
-- | debt    | 50,000,000  | 0          | 50,000,000  |
--
-- Tiền THỰC THU = cash.Net + bank.Net = 470,000,000đ
-- Doanh thu = cash.In + bank.In + debt.In = 620,000,000đ (gồm ghi nợ)
```

### 10.2 Dashboard Widgets

#### Tầng 1 — Quick Glance

```yaml
GET /api/v1/locations/{locationId}/dashboard/summary?date=2026-03-03

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

#### Tầng 2 — Charts

```yaml
GET /api/v1/locations/{locationId}/dashboard/revenue-chart?period=7d

Response:
{
  "period": "7d",
  "data": [
    { "date": "2026-02-25", "revenue": 15000000, "cost": 5000000, "profit": 10000000 },
    { "date": "2026-02-26", "revenue": 12000000, "cost": 3000000, "profit": 9000000 },
    ...
  ]
}
```

```yaml
GET /api/v1/locations/{locationId}/dashboard/top-products?period=30d&limit=5

Response:
{
  "period": "30d",
  "products": [
    { "productId": 10, "productName": "Xi măng Hà Tiên", "totalQuantity": 500, "totalRevenue": 47500000 },
    { "productId": 22, "productName": "Sắt phi 12", "totalQuantity": 200, "totalRevenue": 24000000 }
  ]
}
```

```yaml
GET /api/v1/locations/{locationId}/dashboard/payment-ratio?period=30d

Response:
{
  "period": "30d",
  "cash": { "amount": 350000000, "percent": 56.5 },
  "bank": { "amount": 180000000, "percent": 29.0 },
  "debt": { "amount": 90000000, "percent": 14.5 }
}
```

```yaml
GET /api/v1/locations/{locationId}/dashboard/revenue-by-type?period=30d

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

## 11. API Endpoints Summary

### Costs

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/v1/locations/{id}/costs` | Tạo chi phí thủ công | Owner |
| `GET` | `/api/v1/locations/{id}/costs` | List chi phí (filter, pagination) | Owner |
| `GET` | `/api/v1/locations/{id}/costs/{costId}` | Chi tiết chi phí | Owner |
| `PUT` | `/api/v1/locations/{id}/costs/{costId}` | Cập nhật chi phí (chỉ manual) | Owner |
| `DELETE` | `/api/v1/locations/{id}/costs/{costId}` | Soft delete (chỉ manual) | Owner |

### General Ledger

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/v1/locations/{id}/gl-entries` | List GL entries (filter, pagination) | Owner |

### Accounting Periods

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/v1/locations/{id}/accounting/periods` | Tạo kỳ kế toán | Owner |
| `GET` | `/api/v1/locations/{id}/accounting/periods` | List kỳ kế toán | Owner |
| `GET` | `/api/v1/locations/{id}/accounting/periods/{periodId}` | Chi tiết kỳ | Owner |
| `POST` | `/api/v1/locations/{id}/accounting/periods/{periodId}/finalize` | Chốt kỳ | Owner |
| `POST` | `/api/v1/locations/{id}/accounting/periods/{periodId}/reopen` | Mở lại kỳ | Owner |
| `GET` | `/api/v1/locations/{id}/accounting/periods/{periodId}/audit-logs` | Lịch sử thay đổi | Owner |

### Rule Engine

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/v1/locations/{id}/accounting/group-suggestion` | Gợi ý nhóm HKD | Owner |
| `GET` | `/api/v1/tax-rulesets` | List rulesets | Admin, Consultant |
| `POST` | `/api/v1/tax-rulesets` | Tạo ruleset version mới | Admin, Consultant |
| `PUT` | `/api/v1/tax-rulesets/{rulesetId}/activate` | Activate ruleset | Admin, Consultant |
| `GET` | `/api/v1/tax-rulesets/{rulesetId}/group-rules` | List group rules | Admin, Consultant |
| `GET` | `/api/v1/tax-rulesets/{rulesetId}/industry-rates` | List industry rates | Admin, Consultant |

### Accounting Books

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/v1/locations/{id}/accounting/books` | Tạo sổ kế toán | Owner |
| `GET` | `/api/v1/locations/{id}/accounting/books` | List sổ kế toán | Owner |
| `GET` | `/api/v1/locations/{id}/accounting/books/{bookId}` | Meta sổ kế toán | Owner |
| `GET` | `/api/v1/locations/{id}/accounting/books/{bookId}/data` | Data sổ (live) | Owner |
| `POST` | `/api/v1/locations/{id}/accounting/books/{bookId}/export` | Xuất sổ PDF/Excel | Owner |
| `PUT` | `/api/v1/locations/{id}/accounting/books/{bookId}/archive` | Archive sổ cũ | Owner |

### Accounting Templates (Admin/Consultant)

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/v1/accounting-templates` | List templates | Admin, Consultant |
| `POST` | `/api/v1/accounting-templates/{id}/versions` | Tạo version mới | Admin, Consultant |
| `PUT` | `/api/v1/accounting-templates/versions/{versionId}/activate` | Activate version | Admin, Consultant |

### Tax Payments

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/v1/locations/{id}/tax-payments` | Ghi nhận nộp thuế | Owner |
| `GET` | `/api/v1/locations/{id}/tax-payments` | List thuế đã nộp | Owner |
| `DELETE` | `/api/v1/locations/{id}/tax-payments/{paymentId}` | Soft delete | Owner |

### Dashboard & Reports

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/v1/locations/{id}/dashboard/summary` | Dashboard tổng quan | Owner |
| `GET` | `/api/v1/locations/{id}/dashboard/revenue-chart` | Biểu đồ DT | Owner |
| `GET` | `/api/v1/locations/{id}/dashboard/top-products` | Top SP bán chạy | Owner |
| `GET` | `/api/v1/locations/{id}/dashboard/payment-ratio` | Tỷ lệ PTTT | Owner |
| `GET` | `/api/v1/locations/{id}/dashboard/revenue-by-type` | DT theo ngành | Owner |
| `GET` | `/api/v1/locations/{id}/reports/cash-flow` | Dòng tiền | Owner |
| `GET` | `/api/v1/locations/{id}/reports/revenue` | Báo cáo DT theo kỳ | Owner |
| `GET` | `/api/v1/locations/{id}/reports/costs` | Báo cáo chi phí | Owner |

### Accounting Settings

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/v1/locations/{id}/accounting/settings` | Xem cấu hình | Owner |
| `PUT` | `/api/v1/locations/{id}/accounting/settings` | Cập nhật cấu hình | Owner |

---

## 12. Error Codes

| Code | HTTP | Message |
|------|:----:|---------|
| `COST_NOT_FOUND` | 404 | Chi phí không tồn tại |
| `COST_IS_AUTO_GENERATED` | 400 | Chi phí auto từ Import — không thể sửa/xóa trực tiếp |
| `COST_AMOUNT_INVALID` | 400 | Số tiền phải > 0 |
| `PERIOD_NOT_FOUND` | 404 | Kỳ kế toán không tồn tại |
| `PERIOD_ALREADY_EXISTS` | 409 | Kỳ kế toán đã tồn tại (trùng year+quarter) |
| `PERIOD_NOT_OPEN` | 400 | Kỳ kế toán không ở trạng thái open |
| `PERIOD_REOPEN_REASON_REQUIRED` | 400 | Phải nhập lý do khi mở lại kỳ |
| `PERIOD_NO_BOOKS` | 400 | Phải có ít nhất 1 sổ active trước khi chốt kỳ |
| `RULESET_NOT_FOUND` | 404 | Không tìm thấy Tax Ruleset |
| `RULESET_NO_ACTIVE` | 500 | Không có ruleset active trong hệ thống |
| `GROUP_INVALID` | 400 | Nhóm HKD không hợp lệ (1-4) |
| `TAX_METHOD_NOT_ALLOWED` | 400 | Cách tính thuế không áp dụng cho nhóm này |
| `TEMPLATE_NOT_FOUND` | 404 | Mẫu sổ kế toán không tồn tại |
| `TEMPLATE_NO_ACTIVE_VERSION` | 400 | Không có version active cho mẫu sổ |
| `BOOK_NOT_FOUND` | 404 | Sổ kế toán không tồn tại |
| `BOOK_ALREADY_ARCHIVED` | 400 | Sổ đã được archive |
| `EXPORT_FORMAT_INVALID` | 400 | Định dạng xuất không hợp lệ (chỉ pdf hoặc xlsx) |
| `TAX_PAYMENT_NOT_FOUND` | 404 | Ghi nhận nộp thuế không tồn tại |
| `TAX_TYPE_INVALID` | 400 | Loại thuế không hợp lệ (chỉ VAT hoặc PIT) |
| `NO_PERMISSION` | 403 | Không có quyền thực hiện action này |

---

## 13. Business Rules Summary

### Cost Rules

| Rule | Mô tả |
|------|-------|
| **RULE-COST-01** | Import CONFIRMED → auto tạo Cost (`CostType=import`) + GL entry |
| **RULE-COST-02** | Import CANCELLED → soft delete Cost liên kết + GL reversal |
| **RULE-COST-03** | Owner tự tạo Cost manual → GL entry |
| **RULE-COST-04** | Cost auto từ Import → readonly (sửa/xóa phải qua Import) |
| **RULE-COST-05** | Only Owner CRUD manual costs |
| **RULE-COST-06** | Xóa manual cost → soft delete + GL reversal |

### General Ledger Rules

| Rule | Mô tả |
|------|-------|
| **RULE-GL-01** | Order completed → GL sale entries (1 per payment channel) |
| **RULE-GL-02** | Order cancelled → GL reversal entries |
| **RULE-GL-03** | Import confirmed → GL import_cost entry |
| **RULE-GL-04** | Debt payment → GL debt_payment entry (Debit, cash/bank) |
| **RULE-GL-05** | Tax payment → GL tax_payment entry (Credit, cash/bank) |
| **RULE-GL-06** | **Không bao giờ sửa/xóa** GL entry — luôn tạo reversal |
| **RULE-GL-07** | GL entries split theo MoneyChannel (1 per channel used) |

### Accounting Period Rules

| Rule | Mô tả |
|------|-------|
| **RULE-PERIOD-01** | Unique per location + type + year + quarter |
| **RULE-PERIOD-02** | Finalize bắt buộc có ít nhất 1 book active |
| **RULE-PERIOD-03** | Reopen bắt buộc có reason |
| **RULE-PERIOD-04** | Mọi thay đổi status → audit log |

### Rule Engine Rules

| Rule | Mô tả |
|------|-------|
| **RULE-ENGINE-01** | Chỉ 1 TaxRuleset active tại 1 thời điểm |
| **RULE-ENGINE-02** | Phân nhóm dựa trên data (TaxGroupRules), không hardcode |
| **RULE-ENGINE-03** | DT annualized cho gợi ý giữa năm |
| **RULE-ENGINE-04** | Gợi ý chỉ gợi ý — Owner chủ động chọn nhóm để tạo book |
| **RULE-ENGINE-05** | Khi TT thay đổi → tạo version mới, code không đổi |

### Book & Export Rules

| Rule | Mô tả |
|------|-------|
| **RULE-BOOK-01** | Owner chọn nhóm → hệ thống tạo book theo template tương ứng |
| **RULE-BOOK-02** | Book = live view, data luôn query realtime từ GL/Orders/Costs |
| **RULE-BOOK-03** | Location đa ngành → hệ thống tự tách book per BusinessType khi cần |
| **RULE-BOOK-04** | Owner có thể tạo nhiều books (khác nhóm) cho cùng 1 period để so sánh |
| **RULE-BOOK-05** | Export = snapshot frozen, không thay đổi sau khi xuất |
| **RULE-BOOK-06** | Export lưu: SummaryJson + file URL + ruleset version (audit) |
