# Cost & General Ledger Flow

> **Module**: Report & Accounting — Data Layer
> Quay về [report-accounting-flow.md](report-accounting-flow.md) (index)

---

## Mục lục

1. [Entity Design](#1-entity-design)
   - [1.1 Costs](#11-costs-chi-phí)
   - [1.2 GeneralLedgerEntries](#12-generalledgerentries-sổ-cái)
2. [General Ledger Flow](#2-general-ledger-flow)
   - [2.1 Khi nào tạo GL entries?](#21-khi-nào-tạo-gl-entries)
   - [2.2 Entry Generation Rules](#22-entry-generation-rules)
   - [2.3 Tổng hợp quy tắc Debit/Credit](#23-tổng-hợp-quy-tắc-debitcredit)
3. [Manual GL Entry Flow](#3-manual-gl-entry-flow-bút-toán-thủ-công)
   - [3.1 Khi nào dùng?](#31-khi-nào-dùng)
   - [3.2 Create Manual GL Entry](#32-create-manual-gl-entry)
   - [3.3 Update Manual GL Entry](#33-update-manual-gl-entry-reversal--new)
   - [3.4 Delete Manual GL Entry](#34-delete-manual-gl-entry-reversal-only)
   - [3.5 List Manual GL Entries](#35-list-manual-gl-entries)
4. [Cost Flow](#4-cost-flow)
   - [4.1 Auto-generated Costs](#41-auto-generated-costs-từ-import)
   - [4.2 Manual Costs](#42-manual-costs-owner-tự-khai)
   - [4.3 Business Rules](#43-business-rules)
5. [API Endpoints](#5-api-endpoints)
6. [Error Codes](#6-error-codes)

---

## 1. Entity Design

### 1.1 Costs (Chi phí)

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

### 1.2 GeneralLedgerEntries (Sổ cái)

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
    -- Thủ công:     'manual_revenue', 'manual_expense'
    -- Hoàn/Điều chỉnh: (dùng IsReversal = true)
    
    -- ═══ REFERENCE (truy nguồn gốc) ═══
    ReferenceType VARCHAR(30) NOT NULL,
    -- 'order'            → Orders.OrderId
    -- 'import'           → Imports.ImportId
    -- 'cost'             → Costs.CostId
    -- 'debtor_payment'   → DebtorPaymentTransactions.TransactionId
    -- 'tax_payment'      → TaxPayments.TaxPaymentId
    -- 'manual'           → NULL (entry thủ công, không liên kết entity khác)
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
    public const string Sale = "sale";
    public const string ImportCost = "import_cost";
    public const string ManualCost = "manual_cost";
    public const string DebtPayment = "debt_payment";
    public const string TaxPayment = "tax_payment";
    public const string ManualRevenue = "manual_revenue";
    public const string ManualExpense = "manual_expense";
}

public static class GLReferenceTypes
{
    public const string Order = "order";
    public const string Import = "import";
    public const string Cost = "cost";
    public const string DebtorPayment = "debtor_payment";
    public const string TaxPayment = "tax_payment";
    public const string Manual = "manual";
}

public static class MoneyChannels
{
    public const string Cash = "cash";
    public const string Bank = "bank";
    public const string Debt = "debt";
}
```

---

## 2. General Ledger Flow

### 2.1 Khi nào tạo GL entries?

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
| **Manual revenue recorded** | `manual_revenue` | `manual` | `ManualGLService.CreateAsync()` |
| **Manual expense recorded** | `manual_expense` | `manual` | `ManualGLService.CreateAsync()` |
| Manual GL updated | *(reversal + new)* | `manual` | `ManualGLService.UpdateAsync()` |
| Manual GL deleted | *(reversal)* | `manual` | `ManualGLService.DeleteAsync()` |

### 2.2 Entry Generation Rules

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

### 2.3 Tổng hợp quy tắc Debit/Credit

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
| `manual_revenue` | ✅ Amount | — | cash / bank |
| `manual_revenue` (reversal) | — | ✅ Amount | cash / bank |
| `manual_expense` | — | ✅ Amount | cash / bank |
| `manual_expense` (reversal) | ✅ Amount | — | cash / bank |

---

## 3. Manual GL Entry Flow (Bút toán thủ công)

### 3.1 Khi nào dùng?

Manual GL entries dành cho thu/chi **trước khi sử dụng app** (VD: Owner hoạt động 6 tháng trước mới cài BizFlow) hoặc thu/chi **ngoài hệ thống** không liên kết Order/Import/Cost.

- `manual_revenue`: Doanh thu thủ công (ví dụ: doanh thu trước khi dùng app)
- `manual_expense`: Chi phí thủ công (ví dụ: chi phí trước khi dùng app)

> **Lưu ý**: Manual entries tham gia đầy đủ vào tính DT cho Rule Engine + render sổ kế toán (S1a/S2a/S2b/S2c/S2e). Không giới hạn theo ngày — Owner tạo bất kỳ lúc nào.

### 3.2 Create Manual GL Entry

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
    // Validate transactionType
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

### 3.3 Update Manual GL Entry (Reversal + New)

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

### 3.4 Delete Manual GL Entry (Reversal only)

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

### 3.5 List Manual GL Entries

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

## 4. Cost Flow

### 4.1 Auto-generated Costs (từ Import)

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

### 4.2 Manual Costs (Owner tự khai)

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

### 4.3 Business Rules

#### Cost Rules

| Rule | Mô tả |
|------|-------|
| **RULE-COST-01** | Import CONFIRMED → auto tạo Cost (`CostType=import`) + GL entry |
| **RULE-COST-02** | Import CANCELLED → soft delete Cost liên kết + GL reversal |
| **RULE-COST-03** | Owner tự tạo Cost manual → GL entry |
| **RULE-COST-04** | Cost auto từ Import → readonly (sửa/xóa phải qua Import) |
| **RULE-COST-05** | Only Owner CRUD manual costs |
| **RULE-COST-06** | Xóa manual cost → soft delete + GL reversal |

#### General Ledger Rules

| Rule | Mô tả |
|------|-------|
| **RULE-GL-01** | Order completed → GL sale entries (1 per payment channel) |
| **RULE-GL-02** | Order cancelled → GL reversal entries |
| **RULE-GL-03** | Import confirmed → GL import_cost entry |
| **RULE-GL-04** | Debt payment → GL debt_payment entry (Debit, cash/bank) |
| **RULE-GL-05** | Tax payment → GL tax_payment entry (Credit, cash/bank) |
| **RULE-GL-06** | **Không bao giờ sửa/xóa** GL entry — luôn tạo reversal |
| **RULE-GL-07** | GL entries split theo MoneyChannel (1 per channel used) |
| **RULE-GL-08** | Manual GL entries (`manual_revenue`, `manual_expense`) = bút toán thủ công, không liên kết entity Order/Import/Cost |
| **RULE-GL-09** | Update manual GL = reversal + new entry (immutable ledger) |
| **RULE-GL-10** | Delete manual GL = reversal only (entry gốc vẫn tồn tại) |
| **RULE-GL-11** | Manual GL entries tham gia đầy đủ vào tính DT cho Rule Engine + render sổ kế toán |

---

## 5. API Endpoints

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

### Manual GL Entries

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/v1/locations/{id}/gl-entries/manual` | Tạo bút toán thủ công | Owner |
| `GET` | `/api/v1/locations/{id}/gl-entries/manual` | List bút toán thủ công (filter) | Owner |
| `PUT` | `/api/v1/locations/{id}/gl-entries/manual/{entryId}` | Sửa (reversal + new) | Owner |
| `DELETE` | `/api/v1/locations/{id}/gl-entries/manual/{entryId}` | Hủy (reversal) | Owner |

---

## 6. Error Codes

| Code | HTTP | Message |
|------|:----:|---------|
| `COST_NOT_FOUND` | 404 | Chi phí không tồn tại |
| `COST_IS_AUTO_GENERATED` | 400 | Chi phí auto từ Import — không thể sửa/xóa trực tiếp |
| `COST_AMOUNT_INVALID` | 400 | Số tiền phải > 0 |
| `GL_ENTRY_NOT_FOUND` | 404 | GL entry không tồn tại |
| `GL_NOT_MANUAL_ENTRY` | 400 | Chỉ được sửa/xóa manual entries (referenceType = 'manual') |
| `GL_CANNOT_EDIT_REVERSAL` | 400 | Không thể sửa/xóa reversal entry |
| `GL_ALREADY_REVERSED` | 400 | Entry đã bị hủy trước đó |
| `MANUAL_GL_TYPE_INVALID` | 400 | transactionType phải là 'manual_revenue' hoặc 'manual_expense' |
| `MANUAL_GL_AMOUNT_INVALID` | 400 | Số tiền phải > 0 |
