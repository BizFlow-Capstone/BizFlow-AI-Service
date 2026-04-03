# Accounting Book & Export Flow

> **Module**: Report & Accounting — Template, Book Generation & Export
> Quay về [report-accounting-flow.md](report-accounting-flow.md) (index)

---

## Mục lục

1. [Entity Design](#1-entity-design)
   - [1.1 AccountingTemplates](#11-accountingtemplates-mẫu-sổ-kế-toán)
   - [1.2 AccountingTemplateVersions](#12-accountingtemplateversions)
   - [1.3 TemplateFieldMappings](#13-templatefieldmappings)
   - [1.4 AccountingBooks](#14-accountingbooks-sổ-kế-toán-đã-tạo)
   - [1.5 AccountingExports](#15-accountingexports-snapshot-xuất-sổ)
   - [1.6 TaxPayments](#16-taxpayments-thuế-đã-nộp)
2. [Accounting Book Generation Flow](#2-accounting-book-generation-flow)
   - [2.1 Flow tổng quan](#21-flow-tổng-quan)
   - [2.2 Create Book API](#22-create-book-api)
   - [2.3 View Book Data (Live)](#23-view-book-data-live)
   - [2.4 Export Book](#24-export-book)
3. [TT152 Book Specifications (S1a, S2a–S2e)](#3-tt152-book-specifications-s1a-s2as2e)
   - [3.1 S1a — Sổ chi tiết bán hàng (Nhóm 1)](#31-s1a--sổ-chi-tiết-bán-hàng-nhóm-1)
   - [3.2 S2a — Sổ bán hàng theo ngành (Nhóm 2 Cách 1)](#32-s2a--sổ-bán-hàng-theo-ngành-nhóm-2-cách-1)
   - [3.3 S2b — Sổ bán hàng chi tiết (Nhóm 2 Cách 2, Nhóm 3-4)](#33-s2b--sổ-bán-hàng-chi-tiết-nhóm-2-cách-2-nhóm-3-4)
   - [3.4 S2c — Sổ chi tiết chi phí](#34-s2c--sổ-chi-tiết-chi-phí)
   - [3.5 S2d — Sổ theo dõi nghĩa vụ thuế](#35-s2d--sổ-theo-dõi-nghĩa-vụ-thuế)
   - [3.6 S2e — Sổ theo dõi tình hình thanh toán](#36-s2e--sổ-theo-dõi-tình-hình-thanh-toán)
4. [Business Rules](#4-business-rules)
5. [API Endpoints](#5-api-endpoints)
6. [Error Codes](#6-error-codes)

---

## 1. Entity Design

### 1.1 AccountingTemplates (Mẫu sổ kế toán)

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

### 1.2 AccountingTemplateVersions

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

### 1.3 TemplateFieldMappings

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

### 1.4 AccountingBooks (Sổ kế toán đã tạo)

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

### 1.5 AccountingExports (Snapshot xuất sổ)

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

### 1.6 TaxPayments (Thuế đã nộp)

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

## 2. Accounting Book Generation Flow

### 2.1 Flow tổng quan

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
│   + manual_revenue GL entries     │
│ - S2c → từ Costs                  │
│   + manual_expense GL entries     │
│ - S2d → từ calculated tax +      │
│         TaxPayments               │
│ - S2e → từ GL entries             │
│   + opening/closing balance       │
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

### 2.2 Create Book API

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

### 2.3 View Book Data (Live)

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

### 2.4 Export Book

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

## 3. TT152 Book Specifications (S1a, S2a–S2e)

### 3.1 S1a — Sổ chi tiết bán hàng (Nhóm 1)

**Áp dụng**: Nhóm 1 (DT < 500 triệu/năm) — miễn thuế GTGT & TNCN.

| STT | Ngày tháng | Nội dung (Diễn giải) | Doanh thu bán hàng |
|:---:|:----------:|---------------------|-------------------:|
| 1 | 15/01/2026 | ORD-20260115-001: Bán Xi măng HT 50 bao | 4,750,000 |
| 2 | 15/01/2026 | ORD-20260115-003: Bán Cát xây dựng 200 kg | 600,000 |
| ... | ... | ... | ... |
| | | **Cộng tháng 01** | **45,200,000** |
| ... | ... | ... | ... |
| | | **Cộng quý I** | **120,500,000** |

**Data source**: `Orders WHERE Status = 'completed'` + `GL WHERE TransactionType = 'manual_revenue'`

**Rendering logic**:

```sql
-- Orders (doanh thu từ app)
SELECT 
    DATE(o.CompletedAt) AS NgayThang,
    CONCAT(o.OrderCode, ': ', GROUP_CONCAT(od.ProductName SEPARATOR ', ')) AS NoiDung,
    o.TotalAmount AS DoanhThu
FROM Orders o
JOIN OrderDetails od ON o.OrderId = od.OrderId
WHERE o.BusinessLocationId = @locationId
  AND o.Status = 'completed'
  AND o.CompletedAt BETWEEN @startDate AND @endDate
GROUP BY o.OrderId

UNION ALL

-- Manual revenue GL entries (doanh thu thủ công)
SELECT 
    gle.EntryDate AS NgayThang,
    CONCAT('[THỦ CÔNG] ', gle.Description) AS NoiDung,
    gle.DebitAmount AS DoanhThu
FROM GeneralLedgerEntries gle
WHERE gle.BusinessLocationId = @locationId
  AND gle.TransactionType = 'manual_revenue'
  AND gle.IsReversal = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM GeneralLedgerEntries r 
      WHERE r.ReversedEntryId = gle.EntryId
  )
  AND gle.EntryDate BETWEEN @startDate AND @endDate

ORDER BY NgayThang;
```

### 3.2 S2a — Sổ bán hàng theo ngành (Nhóm 2 Cách 1)

**Áp dụng**: Nhóm 2 (500 triệu – 3 tỷ), Cách 1 tính thuế (% DT theo ngành).

**Lưu ý**: Khi location có nhiều ngành → hệ thống tạo **mỗi ngành 1 file S2a riêng** (theo DD-01 trong [report-accounting-flow.md](report-accounting-flow.md)).

| STT | Ngày | Nội dung | Doanh thu | Thuế GTGT (1%) | Thuế TNCN (0.5%) |
|:---:|:----:|---------|----------:|:--------------:|:----------------:|
| 1 | 15/01 | ORD-001: Xi măng HT 50 bao | 4,750,000 | 47,500 | 23,750 |
| 2 | 16/01 | ORD-005: Sắt thép 100 kg | 3,200,000 | 32,000 | 16,000 |
| ... | ... | ... | ... | ... | ... |
| | | **Cộng quý I** | **500,000,000** | **5,000,000** | **0** |

> **Thuế TNCN Cách 1**: `(DT ngành - 500 triệu) × tỷ lệ %`. Phần DT ≤ 500 triệu → TNCN = 0. Lưu ý: mức trừ 500 triệu chỉ áp dụng **1 lần** cho toàn HKD, không phải mỗi ngành.

**Data source**: `Orders → OrderDetails → Product.BusinessTypeId + IndustryTaxRates` + `GL WHERE TransactionType = 'manual_revenue'`

**Rendering logic**:

```sql
-- Orders (doanh thu từ app, tách theo ngành)
SELECT 
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

UNION ALL

-- Manual revenue GL entries (doanh thu thủ công, không tách ngành)
SELECT 
    gle.EntryDate AS Ngay,
    CONCAT('[THỦ CÔNG] ', gle.Description) AS NoiDung,
    gle.DebitAmount AS DoanhThu,
    NULL AS ThueGTGT,
    NULL AS ThueTNCN
FROM GeneralLedgerEntries gle
WHERE gle.BusinessLocationId = @locationId
  AND gle.TransactionType = 'manual_revenue'
  AND gle.IsReversal = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM GeneralLedgerEntries r 
      WHERE r.ReversedEntryId = gle.EntryId
  )
  AND gle.EntryDate BETWEEN @startDate AND @endDate

ORDER BY Ngay;
```

> **Lưu ý**: Manual revenue entries không có BusinessTypeId → hiển thị riêng cuối sổ hoặc Owner tự phân loại khi nhập. Thuế GTGT/TNCN per-row = NULL cho manual entries — tính ở tổng.

### 3.3 S2b — Sổ bán hàng chi tiết (Nhóm 2 Cách 2, Nhóm 3-4)

**Áp dụng**: Nhóm 2 (Cách 2) + Nhóm 3 + Nhóm 4

| STT | Ngày | Mã đơn | Khách hàng | Sản phẩm | ĐVT | SL | Đơn giá | Thành tiền | PTTT |
|:---:|:----:|:------:|-----------|---------|:---:|---:|--------:|-----------:|:----:|
| 1 | 15/01 | ORD-001 | Anh Ba | Xi măng HT | Bao | 50 | 95,000 | 4,750,000 | TM |
| 2 | 15/01 | ORD-001 | Anh Ba | Cát xây dựng | Kg | 200 | 3,000 | 600,000 | TM |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |
| | | | | | | | **Cộng quý I** | **620,000,000** | |

**PTTT**: TM = Tiền mặt, CK = Chuyển khoản, NỢ = Ghi nợ, HH = Hỗn hợp

**Data source**: `Orders → OrderDetails → SaleItems → Products` + `GL WHERE TransactionType = 'manual_revenue'`

> **Manual revenue**: Hiển thị thêm dòng cuối từ `GL WHERE manual_revenue`, tương tự S1a UNION ALL. Cột PTTT = TM/CK theo `MoneyChannel`.

### 3.4 S2c — Sổ chi tiết chi phí

| STT | Ngày | Nội dung | Loại chi phí | Số tiền | Chứng từ |
|:---:|:----:|---------|:------------:|--------:|:--------:|
| 1 | 10/01 | PNK-001: Nhập Xi măng từ Công ty ABC | Nhập hàng | 8,500,000 | Có HĐ |
| 2 | 15/01 | Thuê mặt bằng T1/2026 | Thuê | 5,000,000 | Có HĐ |
| 3 | 20/01 | Tiền điện T1/2026 | Điện nước | 1,200,000 | Có HĐ |
| ... | ... | ... | ... | ... | ... |
| | | | **Cộng quý I** | **85,000,000** | |

**Data source**: `Costs WHERE DeletedAt IS NULL` + `GL WHERE TransactionType = 'manual_expense'`

> **Manual expense**: Ngoài Costs (manual_cost, import), sổ S2c cũng hiển thị `manual_expense` GL entries. UNION ALL tương tự S1a. Cột Loại chi phí = "Thủ công".

### 3.5 S2d — Sổ theo dõi nghĩa vụ thuế

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

### 3.6 S2e — Sổ theo dõi tình hình thanh toán

| STT | Ngày | Nội dung | Thu TM | Thu CK | Chi TM | Chi CK | Ghi nợ | Thu nợ |
|:---:|:----:|---------|-------:|-------:|-------:|-------:|-------:|-------:|
| 1 | 15/01 | ORD-001: Bán hàng | 600,000 | — | — | — | 200,000 | — |
| 2 | 16/01 | PNK-002: Nhập hàng | — | — | 8,500,000 | — | — | — |
| 3 | 20/01 | Thu nợ Anh Ba | 300,000 | — | — | — | — | 300,000 |
| 4 | 25/01 | Thuê mặt bằng | — | — | — | 5,000,000 | — | — |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |
| | | **Cộng quý I** | **xx** | **xx** | **xx** | **xx** | **xx** | **xx** |

**Data source**: `GeneralLedgerEntries` — render trực tiếp từ GL + opening/closing balance từ `AccountingPeriods`:

```sql
-- ═══ DÒNG ĐẦU: SỐ DƯ ĐẦU KỲ ═══
SELECT 
    0 AS STT,
    @startDate AS Ngay,
    'Số dư đầu kỳ' AS NoiDung,
    ap.OpeningCashBalance AS ThuTM,
    ap.OpeningBankBalance AS ThuCK,
    NULL AS ChiTM, NULL AS ChiCK, NULL AS GhiNo, NULL AS ThuNo
FROM AccountingPeriods ap
WHERE ap.PeriodId = @periodId

UNION ALL

-- ═══ CÁC DÒNG GIAO DỊCH TRONG KỲ ═══
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

ORDER BY STT;
```

**Closing balance (Số dư cuối kỳ)** — computed, hiển thị dòng cuối sổ:

```
Số dư cuối kỳ (tiền mặt) = OpeningCashBalance + SUM(ThuTM) - SUM(ChiTM)
Số dư cuối kỳ (ngân hàng) = OpeningBankBalance + SUM(ThuCK) - SUM(ChiCK)
```

> **Lưu ý**: Opening balance lấy từ `AccountingPeriods.OpeningCashBalance / OpeningBankBalance`. Closing balance = opening + net trong kỳ. Khi tạo kỳ mới, closing kỳ trước tự become opening kỳ sau (xem [accounting-period-flow.md](accounting-period-flow.md) RULE-PERIOD-06).

---

## 4. Business Rules

| Rule | Mô tả |
|------|-------|
| **RULE-BOOK-01** | Owner chọn nhóm → hệ thống tạo book theo template tương ứng |
| **RULE-BOOK-02** | Book = live view, data luôn query realtime từ GL/Orders/Costs |
| **RULE-BOOK-03** | Location đa ngành → hệ thống tự tách book per BusinessType khi cần |
| **RULE-BOOK-04** | Owner có thể tạo nhiều books (khác nhóm) cho cùng 1 period để so sánh |
| **RULE-BOOK-05** | Export = snapshot frozen, không thay đổi sau khi xuất |
| **RULE-BOOK-06** | Export lưu: SummaryJson + file URL + ruleset version (audit) |
| **RULE-BOOK-07** | Manual GL entries (`manual_revenue`) tham gia vào S1a, S2a, S2b (UNION ALL với Orders) |
| **RULE-BOOK-08** | Manual GL entries (`manual_expense`) tham gia vào S2c (UNION ALL với Costs) |
| **RULE-BOOK-09** | S2e hiển thị số dư đầu kỳ (dòng đầu) + số dư cuối kỳ (dòng cuối), lấy từ `AccountingPeriods.OpeningCashBalance/OpeningBankBalance` |
| **RULE-BOOK-10** | Manual entries trong sổ được đánh dấu `[THỦ CÔNG]` ở cột Nội dung để Owner phân biệt |

---

## 5. API Endpoints

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

---

## 6. Error Codes

| Code | HTTP | Message |
|------|:----:|---------|
| `TEMPLATE_NOT_FOUND` | 404 | Mẫu sổ kế toán không tồn tại |
| `TEMPLATE_NO_ACTIVE_VERSION` | 400 | Không có version active cho mẫu sổ |
| `BOOK_NOT_FOUND` | 404 | Sổ kế toán không tồn tại |
| `BOOK_ALREADY_ARCHIVED` | 400 | Sổ đã được archive |
| `EXPORT_FORMAT_INVALID` | 400 | Định dạng xuất không hợp lệ (chỉ pdf hoặc xlsx) |
| `TAX_PAYMENT_NOT_FOUND` | 404 | Ghi nhận nộp thuế không tồn tại |
| `TAX_TYPE_INVALID` | 400 | Loại thuế không hợp lệ (chỉ VAT hoặc PIT) |
| `NO_PERMISSION` | 403 | Không có quyền thực hiện action này |
