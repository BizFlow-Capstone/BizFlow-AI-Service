# Cost, Revenue & General Ledger Flow (v2)

> **Module**: Report & Accounting — Data Layer
> Quay về [report-accounting-flow.md](report-accounting-flow.md) (index)
>
> **v2 Changes**:
> - **+Revenues table** — Quản lý doanh thu (auto từ Order + manual), mirror Costs
> - **+RevenueType** — Phân loại doanh thu: `sale`, `manual`
> - **StockMovements nâng cấp** — Thêm `UnitCostPrice`, `TotalValue`, `DocumentCode` để phục vụ sổ kho + báo cáo giá trị tồn kho
> - **GL thêm ReferenceType `revenue`** — GL entries từ doanh thu trỏ về Revenues table
> - **Giữ nguyên Manual GL Flow** — Người dùng vẫn có thể ghi trực tiếp vào sổ cái mà không bắt buộc phải đi qua Revenue/Cost
> - **Giữ nguyên Costs table** — Không thay đổi

---

## Mục lục

1. [Entity Design](#1-entity-design)
   - [1.1 Costs (giữ nguyên v1)](#11-costs-chi-phí--giữ-nguyên-v1)
   - [1.2 Revenues (NEW v2)](#12-revenues-doanh-thu--new-v2)
   - [1.3 StockMovements (UPDATED v2)](#13-stockmovements-nhật-ký-biến-động-kho--updated-v2)
   - [1.4 GeneralLedgerEntries (UPDATED v2)](#14-generalledgerentries-sổ-cái--updated-v2)
2. [Kiến trúc Data Flow](#2-kiến-trúc-data-flow)
3. [General Ledger Flow](#3-general-ledger-flow)
   - [3.1 Khi nào tạo GL entries?](#31-khi-nào-tạo-gl-entries)
   - [3.2 Entry Generation Rules](#32-entry-generation-rules)
   - [3.3 Tổng hợp quy tắc Debit/Credit](#33-tổng-hợp-quy-tắc-debitcredit)
4. [Manual GL Entry Flow (giữ nguyên v1)](#4-manual-gl-entry-flow-bút-toán-thủ-công)
   - [4.1 Khi nào dùng?](#41-khi-nào-dùng)
   - [4.2 Create Manual GL Entry](#42-create-manual-gl-entry)
   - [4.3 Update Manual GL Entry](#43-update-manual-gl-entry-reversal--new)
   - [4.4 Delete Manual GL Entry](#44-delete-manual-gl-entry-reversal-only)
   - [4.5 List Manual GL Entries](#45-list-manual-gl-entries)
5. [Revenue Flow (NEW v2)](#5-revenue-flow-new-v2)
   - [5.1 Auto-generated Revenues (từ Order)](#51-auto-generated-revenues-từ-order)
   - [5.2 Manual Revenues (Owner tự khai)](#52-manual-revenues-owner-tự-khai)
   - [5.3 Business Rules — Revenue](#53-business-rules--revenue)
6. [Cost Flow (giữ nguyên v1)](#6-cost-flow-giữ-nguyên-v1)
   - [6.1 Auto-generated Costs (từ Import)](#61-auto-generated-costs-từ-import)
   - [6.2 Manual Costs (Owner tự khai)](#62-manual-costs-owner-tự-khai)
   - [6.3 Business Rules — Cost](#63-business-rules--cost)
7. [StockMovement Flow (NEW v2)](#7-stockmovement-flow-new-v2)
   - [7.1 Khi nào ghi StockMovement?](#71-khi-nào-ghi-stockmovement)
   - [7.2 Nguồn dữ liệu UnitCostPrice](#72-nguồn-dữ-liệu-unitcostprice)
   - [7.3 Tổng kết kỳ kế toán (computed query)](#73-tổng-kết-kỳ-kế-toán-computed-query)
   - [7.4 Ví dụ nhật ký biến động v2](#74-ví-dụ-nhật-ký-biến-động-v2)
   - [7.5 Reconciliation](#75-reconciliation)
8. [Business Rules Summary](#8-business-rules-summary)
9. [API Endpoints](#9-api-endpoints)
10. [Error Codes](#10-error-codes)

---

## 1. Entity Design

### 1.1 Costs (Chi phí — giữ nguyên v1)

```sql
-- =============================================
-- COSTS TABLE (Chi phí kinh doanh) — KHÔNG THAY ĐỔI
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

### 1.2 Revenues (Doanh thu — NEW v2)

> **Thiết kế đối xứng với Costs**: Cost quản lý chi phí (auto từ Import + manual), Revenue quản lý doanh thu (auto từ Order + manual). Cả hai đều tạo GL entries.

```sql
-- =============================================
-- REVENUES TABLE (Doanh thu kinh doanh) — NEW v2
-- =============================================
CREATE TABLE Revenues (
    RevenueId BIGINT AUTO_INCREMENT PRIMARY KEY,
    BusinessLocationId INT NOT NULL,
    
    -- Phân loại
    RevenueType VARCHAR(30) NOT NULL 
        COMMENT 'sale = auto từ Order, manual = Owner tự khai',
    
    -- Liên kết auto (nếu từ Order)
    OrderId BIGINT DEFAULT NULL 
        COMMENT 'NULL = Owner tự khai, NOT NULL = auto từ Order COMPLETED',
    
    -- Chi tiết
    Description VARCHAR(500) NOT NULL,
    Amount DECIMAL(15,2) NOT NULL COMMENT 'Tổng doanh thu',
    RevenueDate DATE NOT NULL COMMENT 'Ngày ghi nhận doanh thu',
    
    -- Thanh toán
    PaymentMethod VARCHAR(20) DEFAULT NULL 
        COMMENT 'cash | bank | debt | mixed (khi Order thanh toán nhiều hình thức)',
    
    -- Chứng từ
    DocumentUrl VARCHAR(500) DEFAULT NULL COMMENT 'Ảnh hóa đơn/chứng từ (Cloudinary)',
    DocumentPublicId VARCHAR(255) DEFAULT NULL COMMENT 'Cloudinary public ID',
    
    -- Audit
    CreatedByUserId CHAR(36) NOT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    DeletedAt DATETIME DEFAULT NULL COMMENT 'Soft delete',
    
    -- Indexes & FKs
    CONSTRAINT fk_rev_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    CONSTRAINT fk_rev_order FOREIGN KEY (OrderId) 
        REFERENCES Orders(OrderId),
    INDEX idx_rev_location (BusinessLocationId),
    INDEX idx_rev_type (RevenueType),
    INDEX idx_rev_date (RevenueDate),
    INDEX idx_rev_order (OrderId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class Revenue
{
    public long RevenueId { get; set; }
    public int BusinessLocationId { get; set; }
    
    // Classification
    public string RevenueType { get; set; } = null!;
    public long? OrderId { get; set; }
    
    // Details
    public string Description { get; set; } = null!;
    public decimal Amount { get; set; }
    public DateOnly RevenueDate { get; set; }
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
    public virtual Order? Order { get; set; }
    public virtual User CreatedByUser { get; set; } = null!;
}

public static class RevenueTypes
{
    public const string Sale = "sale";       // Auto từ Order COMPLETED
    public const string Manual = "manual";   // Owner tự khai
}
```

**So sánh Symmetry Cost ↔ Revenue:**

| Aspect | `Costs` | `Revenues` |
|--------|---------|------------|
| Auto source | Import CONFIRMED | Order COMPLETED |
| Auto FK | `ImportId` | `OrderId` |
| Auto type | `CostType = 'import'` | `RevenueType = 'sale'` |
| Manual types | `salary`, `rent`, `utilities`... | `manual` |
| GL direction | CreditAmount (tiền ra) | DebitAmount (tiền vào) |
| Soft delete | `DeletedAt` | `DeletedAt` |

### 1.3 StockMovements (Nhật ký biến động kho — UPDATED v2)

> **v2 Changes**: Thêm `UnitCostPrice`, `TotalValue`, `DocumentCode` để phục vụ sổ kho + báo cáo giá trị tồn kho theo kỳ kế toán.
> StockMovement vẫn là **immutable log** — không sửa/xóa, correction = tạo entry mới.

```sql
-- =============================================
-- STOCK_MOVEMENTS TABLE (Nhật ký biến động kho) — UPDATED v2
-- =============================================
CREATE TABLE StockMovements (
    StockMovementId BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    ProductId BIGINT NOT NULL,
    BusinessLocationId INT NOT NULL,
    
    -- Biến động số lượng
    QuantityDelta INT NOT NULL COMMENT 'Biến động: +N (nhập) hoặc -N (xuất)',
    StockBefore INT NOT NULL COMMENT 'Tồn trước biến động',
    StockAfter INT NOT NULL COMMENT 'Tồn sau biến động',
    
    -- Giá trị (NEW v2)
    UnitCostPrice DECIMAL(15,2) NOT NULL DEFAULT 0 
        COMMENT 'Đơn giá tại thời điểm biến động (lấy từ ProductImport.CostPrice hoặc Product.CostPrice)',
    TotalValue DECIMAL(15,2) NOT NULL DEFAULT 0 
        COMMENT 'ABS(QuantityDelta) × UnitCostPrice — giá trị biến động',
    
    -- Truy nguồn (polymorphic)
    ReferenceType VARCHAR(30) NOT NULL 
        COMMENT 'ORDER | IMPORT | CANCEL_ORDER | CANCEL_IMPORT | ADJUSTMENT',
    ReferenceId BIGINT DEFAULT NULL COMMENT 'OrderId hoặc ImportId',
    DocumentCode VARCHAR(50) DEFAULT NULL 
        COMMENT 'Số hiệu chứng từ: ImportCode hoặc OrderCode (NEW v2)',
    
    -- Metadata
    Note VARCHAR(500) DEFAULT NULL COMMENT 'Ghi chú (manual adjustment reason)',
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CreatedBy CHAR(36) NOT NULL COMMENT 'UserId thực hiện',
    
    CONSTRAINT fk_stockmov_product FOREIGN KEY (ProductId) 
        REFERENCES Products(ProductId),
    CONSTRAINT fk_stockmov_location FOREIGN KEY (BusinessLocationId) 
        REFERENCES BusinessLocations(BusinessLocationId),
    INDEX idx_stockmov_product (ProductId),
    INDEX idx_stockmov_location_date (BusinessLocationId, CreatedAt),
    INDEX idx_stockmov_reference (ReferenceType, ReferenceId),
    INDEX idx_stockmov_created (CreatedAt)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class StockMovement
{
    public long StockMovementId { get; set; }
    public long ProductId { get; set; }
    public int BusinessLocationId { get; set; }
    
    // Quantity
    public int QuantityDelta { get; set; }      // +N or -N
    public int StockBefore { get; set; }
    public int StockAfter { get; set; }
    
    // Value (NEW v2)
    public decimal UnitCostPrice { get; set; }   // Đơn giá tại thời điểm biến động
    public decimal TotalValue { get; set; }      // ABS(QuantityDelta) × UnitCostPrice
    
    // Reference
    public string ReferenceType { get; set; } = null!;
    public long? ReferenceId { get; set; }
    public string? DocumentCode { get; set; }    // Số hiệu chứng từ (NEW v2)
    
    // Metadata
    public string? Note { get; set; }
    public DateTime CreatedAt { get; set; }
    public Guid CreatedBy { get; set; }
    
    // Navigation
    public virtual Product Product { get; set; } = null!;
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
}

public static class StockMovementType
{
    public const string Order = "ORDER";
    public const string Import = "IMPORT";
    public const string CancelOrder = "CANCEL_ORDER";
    public const string CancelImport = "CANCEL_IMPORT";
    public const string Adjustment = "ADJUSTMENT";
}
```

**v1 → v2 diff:**

| Column | v1 | v2 |
|--------|:--:|:--:|
| `QuantityDelta` | ✅ | ✅ |
| `StockBefore` / `StockAfter` | ✅ | ✅ |
| `UnitCostPrice` | ❌ | ✅ NEW |
| `TotalValue` | ❌ | ✅ NEW |
| `DocumentCode` | ❌ | ✅ NEW |
| `ReferenceType` / `ReferenceId` | ✅ | ✅ |
| INDEX `idx_stockmov_location` | by location only | ✅ **composite** `(BusinessLocationId, CreatedAt)` for period queries |

### 1.4 GeneralLedgerEntries (Sổ cái — UPDATED v2)

> **v2 Changes**: Thêm `ReferenceType = 'revenue'` cho GL entries từ Revenue table. Giữ nguyên `'manual'` cho manual GL entries.

```sql
-- =============================================
-- GENERAL LEDGER ENTRIES TABLE (Sổ cái giao dịch) — UPDATED v2
-- =============================================
CREATE TABLE GeneralLedgerEntries (
    EntryId BIGINT AUTO_INCREMENT PRIMARY KEY,
    BusinessLocationId INT NOT NULL,
    
    -- ═══ PHÂN LOẠI GIAO DỊCH ═══
    TransactionType VARCHAR(30) NOT NULL,
    -- Doanh thu (qua Revenue):  'sale', 'manual_revenue_cost'
    -- Chi phí (qua Cost):       'import_cost', 'manual_cost'
    -- Công nợ:                  'debt_payment'
    -- Thuế:                     'tax_payment'
    -- Thủ công (trực tiếp GL):  'manual_revenue', 'manual_expense'
    -- Hoàn/Điều chỉnh:         (dùng IsReversal = true)
    
    -- ═══ REFERENCE (truy nguồn gốc) ═══
    ReferenceType VARCHAR(30) NOT NULL,
    -- 'revenue'          → Revenues.RevenueId               (NEW v2)
    -- 'cost'             → Costs.CostId
    -- 'debtor_payment'   → DebtorPaymentTransactions.TransactionId
    -- 'tax_payment'      → TaxPayments.TaxPaymentId
    -- 'manual'           → NULL (entry thủ công trực tiếp, không liên kết entity)
    ReferenceId BIGINT DEFAULT NULL COMMENT 'NULL cho manual entries',
    
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
    public long? ReferenceId { get; set; }
    
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
    // Doanh thu (qua Revenue table)
    public const string Sale = "sale";
    public const string ManualRevenueCost = "manual_revenue_cost";  // Manual revenue đi qua Revenues table
    
    // Chi phí (qua Cost table)
    public const string ImportCost = "import_cost";
    public const string ManualCost = "manual_cost";
    
    // Công nợ & Thuế
    public const string DebtPayment = "debt_payment";
    public const string TaxPayment = "tax_payment";
    
    // Thủ công (trực tiếp vào GL, không qua Revenue/Cost)
    public const string ManualRevenue = "manual_revenue";
    public const string ManualExpense = "manual_expense";
}

public static class GLReferenceTypes
{
    public const string Revenue = "revenue";            // NEW v2
    public const string Cost = "cost";
    public const string DebtorPayment = "debtor_payment";
    public const string TaxPayment = "tax_payment";
    public const string Manual = "manual";              // Bút toán thủ công trực tiếp
}

public static class MoneyChannels
{
    public const string Cash = "cash";
    public const string Bank = "bank";
    public const string Debt = "debt";
}
```

**v1 → v2 GL diff:**

| Aspect | v1 | v2 |
|--------|:--:|:--:|
| `ReferenceType = 'order'` | ✅ GL ghi trực tiếp Order | ❌ **Bỏ** — đi qua Revenue |
| `ReferenceType = 'import'` | ✅ GL ghi trực tiếp Import | ❌ **Bỏ** — đi qua Cost (đã có từ v1) |
| `ReferenceType = 'revenue'` | ❌ | ✅ **NEW** — GL trỏ về Revenues |
| `ReferenceType = 'manual'` | ✅ | ✅ **Giữ nguyên** |
| `TransactionType = 'manual_revenue_cost'` | ❌ | ✅ **NEW** — phân biệt manual revenue qua Revenues table vs manual GL |

> **Lưu ý phân biệt 2 loại manual revenue:**
> - `manual_revenue` + `ReferenceType = 'manual'` → Bút toán thủ công trực tiếp vào GL (Section 4)
> - `manual_revenue_cost` + `ReferenceType = 'revenue'` → Manual revenue qua Revenues table (Section 5.2)
>
> Cả hai đều tham gia đầy đủ vào tính DT + render sổ kế toán.

---

## 2. Kiến trúc Data Flow

> **Nguyên tắc**: Mọi nghiệp vụ tài chính đều có thể đi qua **2 đường**:
> - **Đường có cấu trúc**: Business event → Revenue/Cost → GL entries (truy vết đầy đủ)
> - **Đường tự do**: Owner ghi trực tiếp vào GL (cho dữ liệu ngoài hệ thống)

```markdown
┌─────────────────────────── DATA FLOW v2 ──────────────────────────────┐
│                                                                       │
│  ╔═══ ĐƯỜNG CÓ CẤU TRÚC (auto + manual có entity) ═══════════════╗  │
│  ║                                                                 ║  │
│  ║  Order COMPLETED ──► Revenue (auto, sale) ──┐                   ║  │
│  ║  Owner tạo DT     ──► Revenue (manual)    ──┤                   ║  │
│  ║                                              ├──► GL entries    ║  │
│  ║  Import CONFIRMED ──► Cost (auto, import) ──┤    (sổ cái)      ║  │
│  ║  Owner tạo CP     ──► Cost (manual)       ──┘                   ║  │
│  ║                                                                 ║  │
│  ║  Debt Payment ──────────────────────────────────► GL entries    ║  │
│  ║  Tax Payment  ──────────────────────────────────► GL entries    ║  │
│  ║                                                                 ║  │
│  ╚═════════════════════════════════════════════════════════════════╝  │
│                                                                       │
│  ╔═══ ĐƯỜNG TỰ DO (manual GL — trực tiếp vào sổ cái) ════════════╗  │
│  ║                                                                 ║  │
│  ║  Owner ghi bút toán ──────────────────────────► GL entries     ║  │
│  ║  (manual_revenue / manual_expense)                              ║  │
│  ║                                                                 ║  │
│  ║  Dùng cho: dữ liệu trước khi dùng app, thu/chi ngoài hệ      ║  │
│  ║  thống, hoặc khi Owner không muốn phân loại DT/CP cụ thể      ║  │
│  ║                                                                 ║  │
│  ╚═════════════════════════════════════════════════════════════════╝  │
│                                                                       │
│  ╔═══ STOCK FLOW ════════════════════════════════════════════════╗   │
│  ║                                                                ║   │
│  ║  Import CONFIRMED ──► StockMovement (+N, đơn giá từ PI)       ║   │
│  ║  Import CANCELLED ──► StockMovement (-N, rollback)            ║   │
│  ║  Order COMPLETED  ──► StockMovement (-N, đơn giá từ Product)  ║   │
│  ║  Order CANCELLED  ──► StockMovement (+N, rollback)            ║   │
│  ║  Manual Adjustment──► StockMovement (+/-N)                    ║   │
│  ║                                                                ║   │
│  ╚════════════════════════════════════════════════════════════════╝   │
│                                                                       │
│  ╔═══ BÁO CÁO TT152 ═══════════════════════════════════════════╗   │
│  ║                                                                ║   │
│  ║  S1a (Sổ bán hàng)        ◄── Revenues + GL (manual_revenue) ║   │
│  ║  S2a (DT theo ngành C1)   ◄── Revenues (join Product) + Tax  ║   │
│  ║  S2b (DT theo ngành C2+)  ◄── Revenues (join Product) + Tax  ║   │
│  ║  S2c (DT + Chi phí)       ◄── Revenues + Costs + GL manual   ║   │
│  ║  S2d (Sổ kho XNT)        ◄── StockMovements (bình quân GQ)  ║   │
│  ║  S2e (Sổ chi tiết tiền)   ◄── GL entries (cash + bank)       ║   │
│  ║                                                                ║   │
│  ╚════════════════════════════════════════════════════════════════╝   │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 3. General Ledger Flow

### 3.1 Khi nào tạo GL entries?

GL entries được tạo **tự động** bởi hệ thống khi xảy ra các event tài chính:

| Event | TransactionType | ReferenceType | ReferenceId | Trigger |
|-------|----------------|---------------|-------------|---------|
| Revenue auto (sale) created | `sale` | `revenue` | RevenueId | `RevenueService.OnOrderCompleted()` |
| Revenue auto (sale) cancelled | `sale` (reversal) | `revenue` | RevenueId | `RevenueService.OnOrderCancelled()` |
| Revenue manual created | `manual_revenue_cost` | `revenue` | RevenueId | `RevenueService.CreateManualAsync()` |
| Revenue manual deleted | `manual_revenue_cost` (reversal) | `revenue` | RevenueId | `RevenueService.DeleteAsync()` |
| Cost auto (import) created | `import_cost` | `cost` | CostId | `CostService.OnImportConfirmed()` |
| Cost auto (import) cancelled | `import_cost` (reversal) | `cost` | CostId | `CostService.OnImportCancelled()` |
| Cost manual created | `manual_cost` | `cost` | CostId | `CostService.CreateManualAsync()` |
| Cost manual deleted | `manual_cost` (reversal) | `cost` | CostId | `CostService.DeleteAsync()` |
| Debt payment recorded | `debt_payment` | `debtor_payment` | TransactionId | `DebtorService.RecordPaymentAsync()` |
| Tax payment recorded | `tax_payment` | `tax_payment` | TaxPaymentId | `TaxPaymentService.CreateAsync()` |
| **Manual GL revenue** | `manual_revenue` | `manual` | NULL | `ManualGLService.CreateAsync()` |
| **Manual GL expense** | `manual_expense` | `manual` | NULL | `ManualGLService.CreateAsync()` |
| Manual GL updated | *(reversal + new)* | `manual` | NULL | `ManualGLService.UpdateAsync()` |
| Manual GL deleted | *(reversal)* | `manual` | NULL | `ManualGLService.DeleteAsync()` |

### 3.2 Entry Generation Rules

#### RULE-GL-01: Revenue Created → Sale / Revenue Entries (UPDATED v2)

Khi Revenue được tạo (auto hoặc manual), tạo GL entries. Với auto revenue từ Order, split theo kênh thanh toán:

```csharp
// Auto revenue (từ Order) — split theo payment channels
public async Task RecordRevenueFromOrder(Revenue revenue, Order order)
{
    var entries = new List<GeneralLedgerEntry>();
    
    if (order.CashAmount > 0)
    {
        entries.Add(new GeneralLedgerEntry
        {
            BusinessLocationId = revenue.BusinessLocationId,
            TransactionType = GLTransactionTypes.Sale,
            ReferenceType = GLReferenceTypes.Revenue,
            ReferenceId = revenue.RevenueId,
            EntryDate = revenue.RevenueDate,
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
            BusinessLocationId = revenue.BusinessLocationId,
            TransactionType = GLTransactionTypes.Sale,
            ReferenceType = GLReferenceTypes.Revenue,
            ReferenceId = revenue.RevenueId,
            EntryDate = revenue.RevenueDate,
            Description = $"{order.OrderCode}: Bán hàng (chuyển khoản)",
            DebitAmount = order.BankAmount,
            CreditAmount = 0,
            MoneyChannel = MoneyChannels.Bank,
            IsReversal = false
        });
    }
    
    if (order.DebtAmount > 0)
    {
        entries.Add(new GeneralLedgerEntry
        {
            BusinessLocationId = revenue.BusinessLocationId,
            TransactionType = GLTransactionTypes.Sale,
            ReferenceType = GLReferenceTypes.Revenue,
            ReferenceId = revenue.RevenueId,
            EntryDate = revenue.RevenueDate,
            Description = $"{order.OrderCode}: Bán hàng (ghi nợ {order.Debtor?.Name})",
            DebitAmount = order.DebtAmount,
            CreditAmount = 0,
            MoneyChannel = MoneyChannels.Debt,
            IsReversal = false
        });
    }
    
    await _unitOfWork.GeneralLedgerEntries.AddRangeAsync(entries);
}

// Manual revenue — 1 GL entry
public async Task RecordManualRevenue(Revenue revenue)
{
    var entry = new GeneralLedgerEntry
    {
        BusinessLocationId = revenue.BusinessLocationId,
        TransactionType = GLTransactionTypes.ManualRevenueCost,
        ReferenceType = GLReferenceTypes.Revenue,
        ReferenceId = revenue.RevenueId,
        EntryDate = revenue.RevenueDate,
        Description = revenue.Description,
        DebitAmount = revenue.Amount,
        CreditAmount = 0,
        MoneyChannel = revenue.PaymentMethod,
        IsReversal = false
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddAsync(entry);
}
```

#### RULE-GL-02: Revenue Cancelled → Reversal Entries

Khi cancel Revenue (soft delete), tạo reversal entries:

```csharp
public async Task RecordRevenueCancelled(Revenue revenue)
{
    var originalEntries = await _unitOfWork.GeneralLedgerEntries
        .FindAllAsync(e => e.ReferenceType == GLReferenceTypes.Revenue 
                        && e.ReferenceId == revenue.RevenueId
                        && !e.IsReversal);
    
    var reversals = originalEntries.Select(original => new GeneralLedgerEntry
    {
        BusinessLocationId = original.BusinessLocationId,
        TransactionType = original.TransactionType,
        ReferenceType = original.ReferenceType,
        ReferenceId = original.ReferenceId,
        EntryDate = DateOnly.FromDateTime(DateTime.UtcNow),
        Description = $"[HỦY] {original.Description}",
        DebitAmount = original.CreditAmount,
        CreditAmount = original.DebitAmount,
        MoneyChannel = original.MoneyChannel,
        IsReversal = true,
        ReversedEntryId = original.EntryId
    }).ToList();
    
    await _unitOfWork.GeneralLedgerEntries.AddRangeAsync(reversals);
}
```

#### RULE-GL-03: Cost Created → Cost Entry (giữ nguyên v1)

```csharp
// Auto cost (từ Import)
public async Task RecordCostFromImport(Cost cost, Import import)
{
    if (import.TotalAmount <= 0) return;
    
    var entry = new GeneralLedgerEntry
    {
        BusinessLocationId = cost.BusinessLocationId,
        TransactionType = GLTransactionTypes.ImportCost,
        ReferenceType = GLReferenceTypes.Cost,
        ReferenceId = cost.CostId,
        EntryDate = cost.CostDate,
        Description = $"{import.ImportCode}: Nhập hàng" + 
            (import.Supplier != null ? $" từ {import.Supplier}" : ""),
        DebitAmount = 0,
        CreditAmount = import.TotalAmount,
        MoneyChannel = cost.PaymentMethod,
        IsReversal = false
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddAsync(entry);
}

// Manual cost
public async Task RecordManualCost(Cost cost)
{
    var entry = new GeneralLedgerEntry
    {
        BusinessLocationId = cost.BusinessLocationId,
        TransactionType = GLTransactionTypes.ManualCost,
        ReferenceType = GLReferenceTypes.Cost,
        ReferenceId = cost.CostId,
        EntryDate = cost.CostDate,
        Description = cost.Description,
        DebitAmount = 0,
        CreditAmount = cost.Amount,
        MoneyChannel = cost.PaymentMethod,
        IsReversal = false
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddAsync(entry);
}
```

#### RULE-GL-04: Debt Payment → Cash-in Entry (giữ nguyên v1)

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
        DebitAmount = payment.Amount,
        CreditAmount = 0,
        MoneyChannel = payment.PaymentMethod,
        IsReversal = false
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddAsync(entry);
}
```

> **Lưu ý**: Thu nợ **không phải doanh thu** — doanh thu đã ghi nhận lúc Order completed (với channel = debt). Thu nợ là tiền mặt/bank thực nhận, entry Debit để ghi nhận cash-in.

#### RULE-GL-05: Tax Payment → Cash-out Entry (giữ nguyên v1)

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
        CreditAmount = taxPayment.Amount,
        MoneyChannel = taxPayment.PaymentMethod,
        IsReversal = false
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddAsync(entry);
}
```

### 3.3 Tổng hợp quy tắc Debit/Credit

| TransactionType | ReferenceType | DebitAmount (tiền VÀO) | CreditAmount (tiền RA) | MoneyChannel |
|:----------------|:--------------|:----------------------:|:----------------------:|:------------:|
| `sale` | `revenue` | ✅ Amount | — | cash / bank / debt |
| `sale` (reversal) | `revenue` | — | ✅ Amount | cash / bank / debt |
| `manual_revenue_cost` | `revenue` | ✅ Amount | — | cash / bank |
| `manual_revenue_cost` (reversal) | `revenue` | — | ✅ Amount | cash / bank |
| `import_cost` | `cost` | — | ✅ Amount | cash / bank / NULL |
| `import_cost` (reversal) | `cost` | ✅ Amount | — | cash / bank / NULL |
| `manual_cost` | `cost` | — | ✅ Amount | cash / bank |
| `manual_cost` (reversal) | `cost` | ✅ Amount | — | cash / bank |
| `debt_payment` | `debtor_payment` | ✅ Amount | — | cash / bank |
| `tax_payment` | `tax_payment` | — | ✅ Amount | cash / bank |
| `manual_revenue` | `manual` | ✅ Amount | — | cash / bank |
| `manual_revenue` (reversal) | `manual` | — | ✅ Amount | cash / bank |
| `manual_expense` | `manual` | — | ✅ Amount | cash / bank |
| `manual_expense` (reversal) | `manual` | ✅ Amount | — | cash / bank |

---

## 4. Manual GL Entry Flow (Bút toán thủ công)

> **Giữ nguyên v1**. Hệ thống không bó buộc người dùng phải dùng đúng mục doanh thu/chi phí cho mọi nghiệp vụ. Owner vẫn có thể ghi bút toán trực tiếp vào sổ cái.

### 4.1 Khi nào dùng?

Manual GL entries dành cho thu/chi **trước khi sử dụng app** (VD: Owner hoạt động 6 tháng trước mới cài BizFlow) hoặc thu/chi **ngoài hệ thống** không cần/muốn phân loại qua Revenue/Cost.

- `manual_revenue`: Doanh thu ghi trực tiếp vào GL
- `manual_expense`: Chi phí ghi trực tiếp vào GL

> **Lưu ý**: Manual entries tham gia đầy đủ vào tính DT cho Rule Engine + render sổ kế toán (S1a/S2a/S2b/S2c/S2e). Không giới hạn theo ngày — Owner tạo bất kỳ lúc nào.

> **So sánh với Revenue/Cost manual**:
> | | Manual Revenue (Revenues table) | Manual GL Revenue (GL trực tiếp) |
> |---|---|---|
> | Có entity riêng | ✅ Revenue record | ❌ Chỉ có GL entry |
> | Sửa/xóa | CRUD bình thường | Reversal + new |
> | Metadata | RevenueType, DocumentUrl | Chỉ Description |
> | Khi nào dùng | Owner muốn quản lý doanh thu có cấu trúc | Ghi nhanh, không cần phân loại |

### 4.2 Create Manual GL Entry

```yaml
POST /api/v1/locations/{locationId}/gl-entries/manual
Authorization: Bearer {token}

Request:
{
  "transactionType": "manual_revenue",     # 'manual_revenue' | 'manual_expense'
  "entryDate": "2025-12-15",
  "description": "Bán hàng tháng 12/2025 (trước khi dùng app)",
  "amount": 15000000,
  "moneyChannel": "cash"                   # 'cash' | 'bank'
}

Response (201 Created):
{
  "entryId": 501,
  "transactionType": "manual_revenue",
  "referenceType": "manual",
  "referenceId": null,
  "entryDate": "2025-12-15",
  "description": "Bán hàng tháng 12/2025 (trước khi dùng app)",
  "debitAmount": 15000000,
  "creditAmount": 0,
  "moneyChannel": "cash",
  "isReversal": false,
  "createdAt": "2026-04-01T10:00:00Z"
}
```

```csharp
public async Task<GeneralLedgerEntry> CreateManualEntryAsync(
    int locationId, Guid userId, CreateManualGLRequest request)
{
    if (request.TransactionType != GLTransactionTypes.ManualRevenue 
        && request.TransactionType != GLTransactionTypes.ManualExpense)
        throw new BadRequestException("MANUAL_GL_TYPE_INVALID");
    
    var isRevenue = request.TransactionType == GLTransactionTypes.ManualRevenue;
    
    var entry = new GeneralLedgerEntry
    {
        BusinessLocationId = locationId,
        TransactionType = request.TransactionType,
        ReferenceType = GLReferenceTypes.Manual,
        ReferenceId = null,
        EntryDate = request.EntryDate,
        Description = request.Description,
        DebitAmount = isRevenue ? request.Amount : 0,
        CreditAmount = isRevenue ? 0 : request.Amount,
        MoneyChannel = request.MoneyChannel,
        IsReversal = false
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddAsync(entry);
    await _unitOfWork.SaveChangesAsync();
    return entry;
}
```

### 4.3 Update Manual GL Entry (Reversal + New)

Update = tạo reversal entry hủy entry cũ + tạo entry mới với data đã sửa. **Không bao giờ UPDATE trực tiếp row GL.**

```yaml
PUT /api/v1/locations/{locationId}/gl-entries/manual/{entryId}
Authorization: Bearer {token}

Request:
{
  "entryDate": "2025-12-15",
  "description": "Bán hàng tháng 12/2025 (đã chỉnh sửa)",
  "amount": 18000000,
  "moneyChannel": "cash"
}

Response:
{
  "reversedEntryId": 501,
  "newEntry": {
    "entryId": 502,
    "transactionType": "manual_revenue",
    "entryDate": "2025-12-15",
    "description": "Bán hàng tháng 12/2025 (đã chỉnh sửa)",
    "debitAmount": 18000000,
    "creditAmount": 0,
    "moneyChannel": "cash",
    "isReversal": false
  },
  "reversalEntry": {
    "entryId": 503,
    "isReversal": true,
    "reversedEntryId": 501
  }
}
```

```csharp
public async Task<ManualGLUpdateResult> UpdateManualEntryAsync(
    int locationId, long entryId, Guid userId, UpdateManualGLRequest request)
{
    var original = await _unitOfWork.GeneralLedgerEntries.GetByIdAsync(entryId);
    if (original == null || original.BusinessLocationId != locationId)
        throw new NotFoundException("GL_ENTRY_NOT_FOUND");
    if (original.ReferenceType != GLReferenceTypes.Manual)
        throw new BadRequestException("GL_NOT_MANUAL_ENTRY");
    if (original.IsReversal)
        throw new BadRequestException("GL_CANNOT_EDIT_REVERSAL");
    
    var isRevenue = original.TransactionType == GLTransactionTypes.ManualRevenue;
    
    // 1. Create reversal (đảo ngược entry cũ)
    var reversal = new GeneralLedgerEntry
    {
        BusinessLocationId = original.BusinessLocationId,
        TransactionType = original.TransactionType,
        ReferenceType = original.ReferenceType,
        ReferenceId = null,
        EntryDate = DateOnly.FromDateTime(DateTime.UtcNow),
        Description = $"[SỬA] {original.Description}",
        DebitAmount = original.CreditAmount,
        CreditAmount = original.DebitAmount,
        MoneyChannel = original.MoneyChannel,
        IsReversal = true,
        ReversedEntryId = original.EntryId
    };
    
    // 2. Create new entry (data đã sửa)
    var newEntry = new GeneralLedgerEntry
    {
        BusinessLocationId = locationId,
        TransactionType = original.TransactionType,
        ReferenceType = GLReferenceTypes.Manual,
        ReferenceId = null,
        EntryDate = request.EntryDate,
        Description = request.Description,
        DebitAmount = isRevenue ? request.Amount : 0,
        CreditAmount = isRevenue ? 0 : request.Amount,
        MoneyChannel = request.MoneyChannel,
        IsReversal = false
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddRangeAsync(new[] { reversal, newEntry });
    await _unitOfWork.SaveChangesAsync();
    
    return new ManualGLUpdateResult { ReversedEntryId = entryId, NewEntry = newEntry, ReversalEntry = reversal };
}
```

### 4.4 Delete Manual GL Entry (Reversal only)

Delete = tạo reversal entry. Row gốc vẫn tồn tại, nhưng bị counter-balanced bởi reversal.

```yaml
DELETE /api/v1/locations/{locationId}/gl-entries/manual/{entryId}
Authorization: Bearer {token}

Response:
{
  "message": "Manual GL entry đã được hủy (reversal created)",
  "reversalEntry": {
    "entryId": 504,
    "isReversal": true,
    "reversedEntryId": 501,
    "description": "[HỦY] Bán hàng tháng 12/2025 (trước khi dùng app)"
  }
}
```

```csharp
public async Task<GeneralLedgerEntry> DeleteManualEntryAsync(
    int locationId, long entryId, Guid userId)
{
    var original = await _unitOfWork.GeneralLedgerEntries.GetByIdAsync(entryId);
    if (original == null || original.BusinessLocationId != locationId)
        throw new NotFoundException("GL_ENTRY_NOT_FOUND");
    if (original.ReferenceType != GLReferenceTypes.Manual)
        throw new BadRequestException("GL_NOT_MANUAL_ENTRY");
    if (original.IsReversal)
        throw new BadRequestException("GL_CANNOT_DELETE_REVERSAL");
    
    // Check chưa bị reverse trước đó
    var alreadyReversed = await _unitOfWork.GeneralLedgerEntries
        .AnyAsync(e => e.ReversedEntryId == entryId);
    if (alreadyReversed)
        throw new BadRequestException("GL_ALREADY_REVERSED");
    
    var reversal = new GeneralLedgerEntry
    {
        BusinessLocationId = original.BusinessLocationId,
        TransactionType = original.TransactionType,
        ReferenceType = original.ReferenceType,
        ReferenceId = null,
        EntryDate = DateOnly.FromDateTime(DateTime.UtcNow),
        Description = $"[HỦY] {original.Description}",
        DebitAmount = original.CreditAmount,
        CreditAmount = original.DebitAmount,
        MoneyChannel = original.MoneyChannel,
        IsReversal = true,
        ReversedEntryId = original.EntryId
    };
    
    await _unitOfWork.GeneralLedgerEntries.AddAsync(reversal);
    await _unitOfWork.SaveChangesAsync();
    return reversal;
}
```

### 4.5 List Manual GL Entries

```yaml
GET /api/v1/locations/{locationId}/gl-entries/manual?startDate=2025-10-01&endDate=2026-03-31&type=manual_revenue
Authorization: Bearer {token}

Response:
{
  "items": [
    {
      "entryId": 501,
      "transactionType": "manual_revenue",
      "entryDate": "2025-12-15",
      "description": "Bán hàng tháng 12/2025",
      "debitAmount": 15000000,
      "creditAmount": 0,
      "moneyChannel": "cash",
      "isReversal": false,
      "isReversed": true,
      "createdAt": "2026-04-01T10:00:00Z"
    }
  ],
  "pagination": { "page": 1, "pageSize": 20, "totalCount": 5 }
}
```

> **`isReversed`**: Computed field — `true` nếu tồn tại entry khác có `ReversedEntryId = this.EntryId`. Frontend dùng để hiển thị trạng thái (gạch ngang, badge "Đã hủy").

---

## 5. Revenue Flow (NEW v2)

### 5.1 Auto-generated Revenues (từ Order)

Khi Order chuyển sang `COMPLETED`, hệ thống **tự động tạo** Revenue record + GL entries:

```csharp
// RULE-REV-01: Auto tạo Revenue khi Order COMPLETED
public async Task OnOrderCompleted(Order order)
{
    var revenue = new Revenue
    {
        BusinessLocationId = order.BusinessLocationId,
        RevenueType = RevenueTypes.Sale,
        OrderId = order.OrderId,
        Description = $"Bán hàng {order.OrderCode}",
        Amount = order.TotalAmount,
        RevenueDate = DateOnly.FromDateTime(order.CompletedAt!.Value),
        PaymentMethod = DeterminePaymentMethod(order), // cash | bank | debt | mixed
        CreatedByUserId = order.CompletedByUserId!.Value,
    };
    
    await _unitOfWork.Revenues.AddAsync(revenue);
    await _unitOfWork.SaveChangesAsync();
    
    // Tạo GL entries (RULE-GL-01) — split theo payment channel
    await _glService.RecordRevenueFromOrder(revenue, order);
    await _unitOfWork.SaveChangesAsync();
}

private string DeterminePaymentMethod(Order order)
{
    var channels = new List<string>();
    if (order.CashAmount > 0) channels.Add("cash");
    if (order.BankAmount > 0) channels.Add("bank");
    if (order.DebtAmount > 0) channels.Add("debt");
    return channels.Count > 1 ? "mixed" : channels.FirstOrDefault() ?? "cash";
}
```

### 5.2 Manual Revenues (Owner tự khai)

```yaml
POST /api/v1/locations/{locationId}/revenues
Authorization: Bearer {token}

Request:
{
  "description": "Doanh thu dịch vụ tháng 2/2026",
  "amount": 8000000,
  "revenueDate": "2026-02-28",
  "paymentMethod": "bank",
  "documentUrl": null
}

Response (201 Created):
{
  "revenueId": 25,
  "revenueType": "manual",
  "description": "Doanh thu dịch vụ tháng 2/2026",
  "amount": 8000000,
  "revenueDate": "2026-02-28",
  "paymentMethod": "bank",
  "orderId": null,
  "createdAt": "2026-02-28T08:00:00Z"
}
```

```csharp
// RULE-REV-03: Owner tạo Manual Revenue → tạo GL entry
public async Task<Revenue> CreateManualRevenueAsync(
    int locationId, Guid userId, CreateManualRevenueRequest request)
{
    var revenue = new Revenue
    {
        BusinessLocationId = locationId,
        RevenueType = RevenueTypes.Manual,
        OrderId = null,
        Description = request.Description,
        Amount = request.Amount,
        RevenueDate = request.RevenueDate,
        PaymentMethod = request.PaymentMethod,
        DocumentUrl = request.DocumentUrl,
        DocumentPublicId = request.DocumentPublicId,
        CreatedByUserId = userId,
    };
    
    await _unitOfWork.Revenues.AddAsync(revenue);
    await _unitOfWork.SaveChangesAsync();
    
    // Tạo GL entry
    await _glService.RecordManualRevenue(revenue);
    await _unitOfWork.SaveChangesAsync();
    
    return revenue;
}
```

### 5.3 Business Rules — Revenue

| Rule | Mô tả |
|------|-------|
| **RULE-REV-01** | Order COMPLETED → auto tạo Revenue (`RevenueType=sale`) + GL entries (split by payment channel) |
| **RULE-REV-02** | Order CANCELLED (từ completed) → soft delete Revenue liên kết + GL reversal entries |
| **RULE-REV-03** | Owner tạo Revenue manual → GL entry (`manual_revenue_cost`, `ReferenceType=revenue`) |
| **RULE-REV-04** | Revenue auto từ Order → readonly (sửa/xóa phải qua Order) |
| **RULE-REV-05** | Only Owner CRUD manual revenues |
| **RULE-REV-06** | Xóa manual revenue → soft delete + GL reversal |

---

## 6. Cost Flow (giữ nguyên v1)

### 6.1 Auto-generated Costs (từ Import)

Khi Import chuyển sang `CONFIRMED`, hệ thống **tự động tạo** Cost record + GL entry:

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
    await _unitOfWork.SaveChangesAsync();
    
    // Tạo GL entry (RULE-GL-03)
    await _glService.RecordCostFromImport(cost, import);
    await _unitOfWork.SaveChangesAsync();
}
```

### 6.2 Manual Costs (Owner tự khai)

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

### 6.3 Business Rules — Cost

| Rule | Mô tả |
|------|-------|
| **RULE-COST-01** | Import CONFIRMED → auto tạo Cost (`CostType=import`) + GL entry |
| **RULE-COST-02** | Import CANCELLED → soft delete Cost liên kết + GL reversal |
| **RULE-COST-03** | Owner tạo Cost manual → GL entry (`manual_cost`, `ReferenceType=cost`) |
| **RULE-COST-04** | Cost auto từ Import → readonly (sửa/xóa phải qua Import) |
| **RULE-COST-05** | Only Owner CRUD manual costs |
| **RULE-COST-06** | Xóa manual cost → soft delete + GL reversal |

---

## 7. StockMovement Flow (NEW v2)

> **Context**: StockMovements v2 vừa là audit log vừa là **nguồn dữ liệu cho sổ kho** (báo cáo nhập-xuất-tồn theo kỳ kế toán). Thêm đơn giá + tổng tiền để tính giá trị tồn kho.

### 7.1 Khi nào ghi StockMovement?

Mọi thay đổi stock **phải** ghi StockMovement trong **cùng transaction** với update `Product.Stock`:

| Event | ReferenceType | QuantityDelta | UnitCostPrice source | Điều kiện |
|-------|--------------|:-------------:|---------------------|-----------|
| Import confirmed | `IMPORT` | `+N` | `ProductImport.CostPrice` | `TrackInventory = true` |
| Import cancelled | `CANCEL_IMPORT` | `-N` (rollback) | `ProductImport.CostPrice` | `TrackInventory = true` |
| Order completed | `ORDER` | `-N` | `Product.CostPrice` (giá vốn hiện tại) | `TrackInventory = true` |
| Order cancelled | `CANCEL_ORDER` | `+N` (rollback) | Giá trị entry gốc | `TrackInventory = true` |
| Manual adjustment | `ADJUSTMENT` | `+/-N` | Owner nhập hoặc `Product.CostPrice` | Owner only |

**Pattern code:**

```csharp
// Ví dụ: Confirm Import (v2 — thêm giá trị)
public async Task ConfirmImportAsync(...)
{
    // ... validate ...
    
    foreach (var productImport in import.ProductImports)
    {
        var product = productImport.Product;
        if (product.TrackInventory == true)
        {
            var stockBefore = product.Stock;
            product.Stock += productImport.Quantity;
            
            var movement = new StockMovement
            {
                ProductId = product.ProductId,
                BusinessLocationId = product.BusinessLocationId,
                QuantityDelta = +productImport.Quantity,
                StockBefore = stockBefore,
                StockAfter = product.Stock,
                // NEW v2: giá trị
                UnitCostPrice = productImport.CostPrice,
                TotalValue = Math.Abs(productImport.Quantity) * productImport.CostPrice,
                // NEW v2: số hiệu chứng từ
                DocumentCode = import.ImportCode,
                ReferenceType = StockMovementType.Import,
                ReferenceId = import.ImportId,
                CreatedAt = DateTime.UtcNow,
                CreatedBy = userId
            };
            
            await _unitOfWork.StockMovements.AddAsync(movement);
        }
        
        // Auto-update cached CostPrice
        product.CostPrice = productImport.CostPrice;
    }
    
    await _unitOfWork.SaveChangesAsync(); // Atomic
}

// Ví dụ: Complete Order (v2)
public async Task CompleteOrderAsync(...)
{
    // ... validate ...
    
    foreach (var detail in order.OrderDetails)
    {
        var product = detail.SaleItem.Product;
        if (product.TrackInventory == true)
        {
            var qty = detail.Quantity * detail.SaleItem.Quantity; // order qty × sale item base unit qty
            var stockBefore = product.Stock;
            product.Stock -= qty;
            
            var movement = new StockMovement
            {
                ProductId = product.ProductId,
                BusinessLocationId = product.BusinessLocationId,
                QuantityDelta = -qty,
                StockBefore = stockBefore,
                StockAfter = product.Stock,
                // NEW v2
                UnitCostPrice = product.CostPrice,
                TotalValue = Math.Abs(qty) * product.CostPrice,
                DocumentCode = order.OrderCode,
                ReferenceType = StockMovementType.Order,
                ReferenceId = order.OrderId,
                CreatedAt = DateTime.UtcNow,
                CreatedBy = userId
            };
            
            await _unitOfWork.StockMovements.AddAsync(movement);
        }
    }
    
    await _unitOfWork.SaveChangesAsync();
}
```

### 7.2 Nguồn dữ liệu UnitCostPrice

| ReferenceType | UnitCostPrice lấy từ | Giải thích |
|---|---|---|
| `IMPORT` | `ProductImport.CostPrice` | Giá vốn nhập hàng ghi trên phiếu nhập |
| `ORDER` | `Product.CostPrice` | Giá vốn cached hiện tại tại thời điểm bán (giá vốn xuất kho) |
| `CANCEL_ORDER` | UnitCostPrice của movement gốc | Rollback đúng giá tại thời điểm bán |
| `CANCEL_IMPORT` | `ProductImport.CostPrice` | Rollback đúng giá tại thời điểm nhập |
| `ADJUSTMENT` | Owner nhập hoặc `Product.CostPrice` | Giá trị tính theo giá vốn hiện tại nếu không nhập |

### 7.3 Tổng kết kỳ kế toán (computed query)

Theo DD-05 (live data), tổng kết kỳ là **query realtime**, không lưu snapshot riêng:

```sql
-- ═══ TỒN ĐẦU KỲ (per product) ═══
SELECT 
    sm.ProductId,
    p.ProductName,
    p.Unit,
    COALESCE(SUM(sm.QuantityDelta), 0) AS OpeningQty,
    COALESCE(SUM(
        CASE WHEN sm.QuantityDelta > 0 THEN sm.TotalValue
             ELSE -sm.TotalValue END
    ), 0) AS OpeningValue
FROM StockMovements sm
JOIN Products p ON p.ProductId = sm.ProductId
WHERE sm.BusinessLocationId = @locId 
  AND sm.CreatedAt < @periodStart
GROUP BY sm.ProductId, p.ProductName, p.Unit;

-- ═══ NHẬP TRONG KỲ ═══
SELECT 
    sm.ProductId,
    SUM(sm.QuantityDelta) AS ImportQty,
    SUM(sm.TotalValue) AS ImportValue
FROM StockMovements sm
WHERE sm.BusinessLocationId = @locId 
  AND sm.CreatedAt BETWEEN @periodStart AND @periodEnd
  AND sm.QuantityDelta > 0
GROUP BY sm.ProductId;

-- ═══ XUẤT TRONG KỲ ═══
SELECT 
    sm.ProductId,
    SUM(ABS(sm.QuantityDelta)) AS ExportQty,
    SUM(sm.TotalValue) AS ExportValue
FROM StockMovements sm
WHERE sm.BusinessLocationId = @locId 
  AND sm.CreatedAt BETWEEN @periodStart AND @periodEnd
  AND sm.QuantityDelta < 0
GROUP BY sm.ProductId;

-- ═══ TỒN CUỐI KỲ = Tồn đầu kỳ + Nhập - Xuất ═══
-- (Computed from above queries or single query:)
SELECT 
    sm.ProductId,
    COALESCE(SUM(sm.QuantityDelta), 0) AS ClosingQty,
    COALESCE(SUM(
        CASE WHEN sm.QuantityDelta > 0 THEN sm.TotalValue
             ELSE -sm.TotalValue END
    ), 0) AS ClosingValue
FROM StockMovements sm
WHERE sm.BusinessLocationId = @locId 
  AND sm.CreatedAt <= @periodEnd
GROUP BY sm.ProductId;
```

### 7.4 Ví dụ nhật ký biến động v2

```markdown
Product: Xi măng Hà Tiên (Base unit: bao)

┌────┬────────────┬──────────────────┬────────┬──────────┬──────────────┬────────┬────────┬──────────────┐
│ #  │ Ngày       │ Số hiệu          │ Delta  │ Đơn giá  │ Tổng tiền    │ Before │ After  │ Loại         │
├────┼────────────┼──────────────────┼────────┼──────────┼──────────────┼────────┼────────┼──────────────┤
│ 1  │ 2026-01-15 │ PNK-001          │ +200   │ 85,000   │ 17,000,000   │ 0      │ 200    │ IMPORT       │
│ 2  │ 2026-01-20 │ ORD-005          │ -24    │ 85,000   │  2,040,000   │ 200    │ 176    │ ORDER        │
│ 3  │ 2026-01-22 │ ORD-008          │ -48    │ 85,000   │  4,080,000   │ 176    │ 128    │ ORDER        │
│ 4  │ 2026-01-25 │ ORD-008          │ +48    │ 85,000   │  4,080,000   │ 128    │ 176    │ CANCEL_ORDER │
│ 5  │ 2026-02-01 │ PNK-012          │ +100   │ 87,000   │  8,700,000   │ 176    │ 276    │ IMPORT       │
│ 6  │ 2026-02-10 │ ORD-015          │ -126   │ 85,933   │ 10,827,558   │ 276    │ 150    │ ORDER        │
└────┴────────────┴──────────────────┴────────┴──────────┴──────────────┴────────┴────────┴──────────────┘

Tồn kho hiện tại: 150 bao
Giá trị tồn kho:  SUM(signed TotalValue) = 17,000,000 - 2,040,000 - 4,080,000 + 4,080,000 + 8,700,000 - 10,827,558 = 12,832,442đ
Kiểm tra qty:     SUM(Delta) = +200 -24 -48 +48 +100 -126 = +150 ✅ = Product.Stock
```

### 7.5 Reconciliation

```csharp
// Job chạy định kỳ (hàng đêm) kiểm tra sai lệch
public async Task ReconcileStockAsync()
{
    var mismatches = await _dbContext.Products
        .Where(p => p.TrackInventory == true && p.DeletedAt == null)
        .Select(p => new {
            p.ProductId,
            p.ProductName,
            CurrentStock = p.Stock,
            CalculatedStock = p.StockMovements.Sum(m => m.QuantityDelta)
        })
        .Where(x => x.CurrentStock != x.CalculatedStock)
        .ToListAsync();
    
    // Alert / log mismatches
}
```

---

## 8. Business Rules Summary

### Revenue Rules (NEW v2)

| Rule | Mô tả |
|------|-------|
| **RULE-REV-01** | Order COMPLETED → auto tạo Revenue (`RevenueType=sale`) + GL entries |
| **RULE-REV-02** | Order CANCELLED (từ completed) → soft delete Revenue + GL reversal |
| **RULE-REV-03** | Owner tạo Revenue manual → GL entry |
| **RULE-REV-04** | Revenue auto từ Order → readonly |
| **RULE-REV-05** | Only Owner CRUD manual revenues |
| **RULE-REV-06** | Xóa manual revenue → soft delete + GL reversal |

### Cost Rules (giữ nguyên v1)

| Rule | Mô tả |
|------|-------|
| **RULE-COST-01** | Import CONFIRMED → auto tạo Cost (`CostType=import`) + GL entry |
| **RULE-COST-02** | Import CANCELLED → soft delete Cost liên kết + GL reversal |
| **RULE-COST-03** | Owner tạo Cost manual → GL entry |
| **RULE-COST-04** | Cost auto từ Import → readonly |
| **RULE-COST-05** | Only Owner CRUD manual costs |
| **RULE-COST-06** | Xóa manual cost → soft delete + GL reversal |

### General Ledger Rules

| Rule | Mô tả |
|------|-------|
| **RULE-GL-01** | Revenue created → GL entries (split by payment channel for auto sale) |
| **RULE-GL-02** | Revenue cancelled → GL reversal entries |
| **RULE-GL-03** | Cost created → GL entry (import_cost hoặc manual_cost) |
| **RULE-GL-04** | Debt payment → GL debt_payment entry (Debit, cash/bank) |
| **RULE-GL-05** | Tax payment → GL tax_payment entry (Credit, cash/bank) |
| **RULE-GL-06** | **Không bao giờ sửa/xóa** GL entry — luôn tạo reversal |
| **RULE-GL-07** | GL entries split theo MoneyChannel (1 per channel used) |
| **RULE-GL-08** | Manual GL entries (`manual_revenue`, `manual_expense`) = bút toán thủ công trực tiếp, không liên kết Revenue/Cost |
| **RULE-GL-09** | Update manual GL = reversal + new entry (immutable ledger) |
| **RULE-GL-10** | Delete manual GL = reversal only |
| **RULE-GL-11** | Manual GL entries tham gia đầy đủ vào tính DT cho Rule Engine + render sổ kế toán |

### Stock Movement Rules (UPDATED v2)

| Rule | Mô tả |
|------|-------|
| **RULE-SM-01** | Mọi thay đổi stock phải ghi StockMovement trong cùng transaction |
| **RULE-SM-02** | StockMovement là immutable — không sửa/xóa, correction = tạo entry mới |
| **RULE-SM-03** | `UnitCostPrice` lấy từ `ProductImport.CostPrice` (nhập) hoặc `Product.CostPrice` (xuất) |
| **RULE-SM-04** | `TotalValue = ABS(QuantityDelta) × UnitCostPrice` |
| **RULE-SM-05** | `DocumentCode` copy từ `ImportCode` hoặc `OrderCode` |
| **RULE-SM-06** | Chỉ ghi khi `Product.TrackInventory = true` |

---

## 9. API Endpoints

### Revenues (NEW v2)

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/v1/locations/{id}/revenues` | Tạo doanh thu thủ công | Owner |
| `GET` | `/api/v1/locations/{id}/revenues` | List doanh thu (filter, pagination) | Owner |
| `GET` | `/api/v1/locations/{id}/revenues/{revenueId}` | Chi tiết doanh thu | Owner |
| `PUT` | `/api/v1/locations/{id}/revenues/{revenueId}` | Cập nhật doanh thu (chỉ manual) | Owner |
| `DELETE` | `/api/v1/locations/{id}/revenues/{revenueId}` | Soft delete (chỉ manual) | Owner |

### Costs (giữ nguyên v1)

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

### Manual GL Entries (giữ nguyên v1)

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/v1/locations/{id}/gl-entries/manual` | Tạo bút toán thủ công | Owner |
| `GET` | `/api/v1/locations/{id}/gl-entries/manual` | List bút toán thủ công (filter) | Owner |
| `PUT` | `/api/v1/locations/{id}/gl-entries/manual/{entryId}` | Sửa (reversal + new) | Owner |
| `DELETE` | `/api/v1/locations/{id}/gl-entries/manual/{entryId}` | Hủy (reversal) | Owner |

### Stock Movements (NEW v2)

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/v1/locations/{id}/stock-movements` | List biến động kho (filter by product, date range) | Owner |
| `GET` | `/api/v1/locations/{id}/stock-movements/summary` | Tổng kết XNT theo kỳ (tồn đầu/cuối kỳ, nhập/xuất) | Owner |

---

## 10. Error Codes

### Cost Errors (giữ nguyên v1)

| Code | HTTP | Message |
|------|:----:|---------|
| `COST_NOT_FOUND` | 404 | Chi phí không tồn tại |
| `COST_IS_AUTO_GENERATED` | 400 | Chi phí auto từ Import — không thể sửa/xóa trực tiếp |
| `COST_AMOUNT_INVALID` | 400 | Số tiền phải > 0 |

### Revenue Errors (NEW v2)

| Code | HTTP | Message |
|------|:----:|---------|
| `REVENUE_NOT_FOUND` | 404 | Doanh thu không tồn tại |
| `REVENUE_IS_AUTO_GENERATED` | 400 | Doanh thu auto từ Order — không thể sửa/xóa trực tiếp |
| `REVENUE_AMOUNT_INVALID` | 400 | Số tiền phải > 0 |

### GL Errors (giữ nguyên v1)

| Code | HTTP | Message |
|------|:----:|---------|
| `GL_ENTRY_NOT_FOUND` | 404 | GL entry không tồn tại |
| `GL_NOT_MANUAL_ENTRY` | 400 | Chỉ được sửa/xóa manual entries (referenceType = 'manual') |
| `GL_CANNOT_EDIT_REVERSAL` | 400 | Không thể sửa/xóa reversal entry |
| `GL_ALREADY_REVERSED` | 400 | Entry đã bị hủy trước đó |
| `MANUAL_GL_TYPE_INVALID` | 400 | transactionType phải là 'manual_revenue' hoặc 'manual_expense' |
| `MANUAL_GL_AMOUNT_INVALID` | 400 | Số tiền phải > 0 |
