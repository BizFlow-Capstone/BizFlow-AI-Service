# Accounting Book & Export Flow (v2)

> **Module**: Report & Accounting — Template, Book Generation & Export
> Quay về [report-accounting-flow.md](report-accounting-flow.md) (index)
>
> **v2 Changes**: Thêm Metadata Registry (`MappableEntities` + `MappableFields`) để quản lý whitelist entity/field cho TemplateFieldMappings. Tách quyền Admin vs Consultant. Thêm Preview/Dry-run flow.

---

## Mục lục

1. [Entity Design](#1-entity-design)
   - [1.1 AccountingTemplates](#11-accountingtemplates-mẫu-sổ-kế-toán)
   - [1.2 AccountingTemplateVersions](#12-accountingtemplateversions)
   - [1.3 MappableEntities (NEW v2)](#13-mappableentities-new-v2)
   - [1.4 MappableFields (NEW v2)](#14-mappablefields-new-v2)
   - [1.5 TemplateFieldMappings (UPDATED v2)](#15-templatefieldmappings-updated-v2)
   - [1.6 AccountingBooks](#16-accountingbooks-sổ-kế-toán-đã-tạo)
   - [1.7 AccountingExports](#17-accountingexports-snapshot-xuất-sổ)
   - [1.8 TaxPayments](#18-taxpayments-thuế-đã-nộp)
2. [Template Management Flow (NEW v2)](#2-template-management-flow-new-v2)
   - [2.1 Quyết định thiết kế — Metadata Registry](#21-quyết-định-thiết-kế--metadata-registry)
   - [2.2 Admin Flow: Quản lý Metadata Registry](#22-admin-flow-quản-lý-metadata-registry)
   - [2.3 Admin Flow: Quản lý Template + FieldMappings](#23-admin-flow-quản-lý-template--fieldmappings)
   - [2.4 Preview / Dry-run trước khi activate](#24-preview--dry-run-trước-khi-activate)
   - [2.5 Phân quyền Admin vs Consultant](#25-phân-quyền-admin-vs-consultant)
3. [Accounting Book Generation Flow](#3-accounting-book-generation-flow)
   - [3.1 Flow tổng quan](#31-flow-tổng-quan)
   - [3.2 Create Book API](#32-create-book-api)
   - [3.3 View Book Data (Live)](#33-view-book-data-live)
   - [3.4 Export Book](#34-export-book)
4. [TT152 Book Specifications (S1a, S2a–S2e)](#4-tt152-book-specifications-s1a-s2as2e)
   - [4.1 S1a — Sổ chi tiết bán hàng (Nhóm 1)](#41-s1a--sổ-chi-tiết-bán-hàng-nhóm-1)
   - [4.2 S2a — Sổ doanh thu bán hàng hóa, dịch vụ (Nhóm 2 Cách 1)](#42-s2a--sổ-doanh-thu-bán-hàng-hóa-dịch-vụ-nhóm-2-cách-1)
   - [4.3 S2b — Sổ doanh thu bán hàng hóa, dịch vụ (Nhóm 2 Cách 2, Nhóm 3-4)](#43-s2b--sổ-doanh-thu-bán-hàng-hóa-dịch-vụ-nhóm-2-cách-2-nhóm-3-4)
   - [4.4 S2c — Sổ chi tiết doanh thu, chi phí](#44-s2c--sổ-chi-tiết-doanh-thu-chi-phí)
   - [4.5 S2d — Sổ chi tiết vật liệu, dụng cụ, sản phẩm, hàng hóa](#45-s2d--sổ-chi-tiết-vật-liệu-dụng-cụ-sản-phẩm-hàng-hóa)
   - [4.6 S2e — Sổ chi tiết tiền](#46-s2e--sổ-chi-tiết-tiền)
5. [Business Rules](#5-business-rules)
6. [API Endpoints](#6-api-endpoints)
7. [Error Codes](#7-error-codes)

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
('S1a', 'Sổ chi tiết bán hàng',                           '[1]',      NULL),
('S2a', 'Sổ doanh thu bán hàng hóa, dịch vụ',             '[2]',      '["method_1"]'),
('S2b', 'Sổ doanh thu bán hàng hóa, dịch vụ',             '[2,3,4]',  '["method_2"]'),
('S2c', 'Sổ chi tiết doanh thu, chi phí',                  '[2,3,4]',  '["method_2"]'),
('S2d', 'Sổ chi tiết vật liệu, dụng cụ, sản phẩm, hàng hóa', '[2,3,4]', '["method_2"]'),
('S2e', 'Sổ chi tiết tiền',                                '[2,3,4]',  '["method_2"]');
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

### 1.3 MappableEntities (NEW v2)

> **Mục đích**: Whitelist các data source entities mà TemplateFieldMappings được phép tham chiếu. Admin quản lý qua CRUD — không hardcode trong code.

```sql
-- =============================================
-- MAPPABLE ENTITIES TABLE — Metadata Registry (v2)
-- Whitelist nguồn dữ liệu cho field mapping
-- =============================================
CREATE TABLE MappableEntities (
    EntityId INT AUTO_INCREMENT PRIMARY KEY,
    
    -- ═══ IDENTITY ═══
    EntityCode VARCHAR(50) NOT NULL
        COMMENT 'Mã kỹ thuật: orders, order_details, gl_entries, costs, tax_payments',
    DisplayName VARCHAR(200) NOT NULL
        COMMENT 'Tên hiển thị trên UI: "Đơn hàng", "Chi tiết đơn hàng"',
    Description TEXT DEFAULT NULL
        COMMENT 'Mô tả tóm tắt entity này chứa data gì',
    
    -- ═══ CONTEXT ═══
    Category VARCHAR(50) NOT NULL DEFAULT 'revenue'
        COMMENT 'Phân loại: revenue | cost | tax | cashflow | general',
    
    -- ═══ STATUS ═══
    IsActive BOOLEAN NOT NULL DEFAULT TRUE
        COMMENT 'FALSE = ẩn khỏi dropdown, mapping cũ tham chiếu entity này vẫn giữ nguyên',
    
    -- ═══ AUDIT ═══
    CreatedByUserId CHAR(36) DEFAULT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    
    UNIQUE INDEX idx_me_code (EntityCode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Sample data:**

```sql
INSERT INTO MappableEntities (EntityCode, DisplayName, Description, Category) VALUES
('orders',         'Đơn hàng',              'Đơn hàng đã hoàn tất (completed)',     'revenue'),
('order_details',  'Chi tiết đơn hàng',     'Dòng sản phẩm trong đơn hàng',        'revenue'),
('gl_entries',     'Sổ cái (GL)',           'Bút toán sổ cái tài chính',            'general'),
('costs',          'Chi phí',               'Chi phí (nhập hàng + thủ công)',        'cost'),
('tax_payments',   'Thuế đã nộp',          'Ghi nhận nộp thuế VAT/TNCN',           'tax'),
('products',       'Sản phẩm',             'Thông tin sản phẩm',                    'revenue');
```

### 1.4 MappableFields (NEW v2)

> **Mục đích**: Whitelist các field cụ thể thuộc mỗi entity. Mỗi field kèm metadata: datatype, aggregation cho phép, mô tả. UI hiển thị dropdown field phụ thuộc entity đã chọn.

```sql
-- =============================================
-- MAPPABLE FIELDS TABLE — Metadata Registry (v2)
-- Whitelist field cho từng entity
-- =============================================
CREATE TABLE MappableFields (
    FieldId INT AUTO_INCREMENT PRIMARY KEY,
    EntityId INT NOT NULL,
    
    -- ═══ FIELD IDENTITY ═══
    FieldCode VARCHAR(100) NOT NULL
        COMMENT 'Tên field kỹ thuật (mapping sang DB column/computed): TotalAmount, CompletedAt',
    DisplayName VARCHAR(200) NOT NULL
        COMMENT 'Tên hiển thị trên UI: "Tổng tiền", "Ngày hoàn tất"',
    Description TEXT DEFAULT NULL
        COMMENT 'Giải thích: "Tổng tiền đơn hàng sau giảm giá"',
    
    -- ═══ DATA TYPE ═══
    DataType VARCHAR(20) NOT NULL
        COMMENT 'decimal | date | text | integer | boolean',
    
    -- ═══ ALLOWED OPERATIONS ═══
    AllowedAggregations JSON NOT NULL DEFAULT '["none"]'
        COMMENT 'Aggregation cho phép: ["sum","avg","count","none"]',
    
    -- ═══ STATUS ═══
    IsActive BOOLEAN NOT NULL DEFAULT TRUE
        COMMENT 'FALSE = ẩn khỏi dropdown, không ảnh hưởng mapping cũ',
    
    -- ═══ AUDIT ═══
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    
    -- ═══ FKs & INDEXES ═══
    CONSTRAINT fk_mf_entity FOREIGN KEY (EntityId)
        REFERENCES MappableEntities(EntityId),
    INDEX idx_mf_entity (EntityId),
    UNIQUE INDEX idx_mf_entity_field (EntityId, FieldCode)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Sample data:**

```sql
-- Entity: orders (EntityId = 1)
INSERT INTO MappableFields (EntityId, FieldCode, DisplayName, Description, DataType, AllowedAggregations) VALUES
(1, 'TotalAmount',   'Tổng tiền',        'Tổng tiền đơn hàng (sau giảm giá)',         'decimal',  '["sum","avg","none"]'),
(1, 'CompletedAt',   'Ngày hoàn tất',    'Thời điểm đơn hàng được hoàn tất',          'date',     '["none"]'),
(1, 'OrderCode',     'Mã đơn hàng',      'Mã đơn hàng tự sinh',                        'text',     '["none","count"]'),
(1, 'Status',        'Trạng thái',       'completed | cancelled | ...',                 'text',     '["none"]'),
(1, 'CustomerName',  'Tên khách hàng',   'Tên khách hàng (nếu có)',                     'text',     '["none"]');

-- Entity: order_details (EntityId = 2)
INSERT INTO MappableFields (EntityId, FieldCode, DisplayName, Description, DataType, AllowedAggregations) VALUES
(2, 'ProductName',   'Tên sản phẩm',     'Tên sản phẩm trong đơn',                    'text',     '["none"]'),
(2, 'Quantity',      'Số lượng',         'Số lượng mua',                                'decimal',  '["sum","none"]'),
(2, 'Unit',          'Đơn vị tính',      'Bao, Kg, Cây...',                             'text',     '["none"]'),
(2, 'UnitPrice',     'Đơn giá',          'Giá bán 1 đơn vị',                            'decimal',  '["avg","none"]'),
(2, 'Amount',        'Thành tiền',       'Quantity × UnitPrice',                         'decimal',  '["sum","none"]');

-- Entity: gl_entries (EntityId = 3)
INSERT INTO MappableFields (EntityId, FieldCode, DisplayName, Description, DataType, AllowedAggregations) VALUES
(3, 'EntryDate',       'Ngày bút toán',     'Ngày ghi sổ',                               'date',     '["none"]'),
(3, 'Description',     'Diễn giải',        'Mô tả nội dung giao dịch',                   'text',     '["none"]'),
(3, 'DebitAmount',     'Số tiền ghi nợ',   'Tiền vào (thu)',                              'decimal',  '["sum","avg","none"]'),
(3, 'CreditAmount',   'Số tiền ghi có',   'Tiền ra (chi)',                               'decimal',  '["sum","avg","none"]'),
(3, 'TransactionType', 'Loại giao dịch',   'sale | import_cost | manual_cost | ...',      'text',     '["none"]'),
(3, 'MoneyChannel',    'Kênh tiền',        'cash | bank | debt',                          'text',     '["none"]');

-- Entity: costs (EntityId = 4)
INSERT INTO MappableFields (EntityId, FieldCode, DisplayName, Description, DataType, AllowedAggregations) VALUES
(4, 'CostDate',       'Ngày chi phí',     'Ngày phát sinh chi phí',                     'date',     '["none"]'),
(4, 'CostAmount',     'Số tiền',          'Giá trị chi phí',                             'decimal',  '["sum","avg","none"]'),
(4, 'CostCategory',   'Loại chi phí',     'rent | utilities | import | other',           'text',     '["none"]'),
(4, 'CostDescription','Mô tả',            'Nội dung chi phí',                            'text',     '["none"]'),
(4, 'HasInvoice',     'Có hóa đơn',       'Có chứng từ hay không',                       'boolean',  '["none"]');

-- Entity: tax_payments (EntityId = 5)
INSERT INTO MappableFields (EntityId, FieldCode, DisplayName, Description, DataType, AllowedAggregations) VALUES
(5, 'TaxType',         'Loại thuế',         'VAT | PIT',                                 'text',     '["none"]'),
(5, 'Amount',          'Số tiền nộp',       'Số tiền thuế đã nộp',                       'decimal',  '["sum","none"]'),
(5, 'PaidAt',          'Ngày nộp',          'Ngày nộp thuế',                              'date',     '["none"]'),
(5, 'PaymentMethod',   'Hình thức nộp',     'cash | bank',                               'text',     '["none"]'),
(5, 'ReferenceNumber', 'Số biên lai',       'Mã giao dịch / số biên lai',                'text',     '["none"]');

-- Entity: products (EntityId = 6)
INSERT INTO MappableFields (EntityId, FieldCode, DisplayName, Description, DataType, AllowedAggregations) VALUES
(6, 'ProductName',     'Tên sản phẩm',     'Tên sản phẩm trong danh mục',               'text',     '["none"]'),
(6, 'Unit',            'ĐVT',              'Đơn vị tính',                                'text',     '["none"]'),
(6, 'BusinessTypeId',  'Ngành nghề',       'ID ngành nghề (để tách sổ theo ngành)',       'text',     '["none"]');
```

### 1.5 TemplateFieldMappings (UPDATED v2)

> **v2 Changes**: `SourceEntity` và `SourceField` giờ là **FK tham chiếu** MappableEntities/MappableFields, không còn là free text. Đảm bảo data integrity qua foreign key constraint.

```sql
-- =============================================
-- TEMPLATE FIELD MAPPINGS TABLE (v2)
-- Mapping logic: DB data → template fields
-- Tham chiếu Metadata Registry thay vì free text
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
    
    -- ═══ DATA SOURCE (v2: FK → Metadata Registry) ═══
    SourceType VARCHAR(30) DEFAULT NULL 
        COMMENT 'query | formula | static | auto',
    SourceEntityId INT DEFAULT NULL
        COMMENT 'FK → MappableEntities. NULL khi SourceType = auto | formula | static',
    SourceFieldId INT DEFAULT NULL
        COMMENT 'FK → MappableFields. NULL khi SourceType = auto | formula | static',
    FilterJson JSON DEFAULT NULL 
        COMMENT 'Filter khi query: {"transactionType":"sale","moneyChannel":"cash"}',
    AggregationType VARCHAR(20) DEFAULT NULL 
        COMMENT 'sum | count | avg | none — phải nằm trong AllowedAggregations của MappableField',
    
    -- ═══ COMPUTED FIELDS ═══
    FormulaExpression VARCHAR(500) DEFAULT NULL 
        COMMENT 'Công thức tham chiếu FieldCode khác: revenue * vat_rate',
    DependsOn JSON DEFAULT NULL 
        COMMENT 'Danh sách FieldCode phụ thuộc: ["revenue","vat_rate"]',
    
    -- ═══ EXPORT POSITIONING ═══
    ExportColumn VARCHAR(10) DEFAULT NULL COMMENT 'Excel column: A, B, C...',
    SortOrder INT NOT NULL DEFAULT 0,
    IsRequired BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- ═══ FKs & INDEXES ═══
    CONSTRAINT fk_tfm_version FOREIGN KEY (TemplateVersionId) 
        REFERENCES AccountingTemplateVersions(TemplateVersionId),
    CONSTRAINT fk_tfm_source_entity FOREIGN KEY (SourceEntityId)
        REFERENCES MappableEntities(EntityId),
    CONSTRAINT fk_tfm_source_field FOREIGN KEY (SourceFieldId)
        REFERENCES MappableFields(FieldId),
    INDEX idx_tfm_version (TemplateVersionId),
    INDEX idx_tfm_source (SourceEntityId, SourceFieldId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**So sánh v1 → v2:**

| Field | v1 | v2 | Lý do |
|-------|----|----|-------|
| `SourceEntity` | `VARCHAR(50)` free text | **Removed** → `SourceEntityId INT FK` | Chống injection, type-safe |
| `SourceField` | `VARCHAR(100)` free text | **Removed** → `SourceFieldId INT FK` | Chống injection, type-safe |
| `AggregationType` | Free text | Validate against `MappableFields.AllowedAggregations` | Ngăn aggregation không hợp lệ (vd: `sum` trên field `text`) |

**Ví dụ FieldMapping cho S1a (v2):**

```sql
-- Giả sử: orders EntityId=1, gl_entries EntityId=3
-- CompletedAt FieldId=2, OrderCode FieldId=3, TotalAmount FieldId=1

INSERT INTO TemplateFieldMappings 
(TemplateVersionId, FieldCode, FieldLabel, FieldType, SourceType, SourceEntityId, SourceFieldId, AggregationType, ExportColumn, SortOrder, IsRequired) VALUES
(1, 'stt',         'STT',         'auto_increment', 'auto',    NULL,  NULL,  NULL,   'A', 1, TRUE),
(1, 'date',        'Ngày tháng',  'date',           'query',   1,     2,     'none', 'B', 2, TRUE),
(1, 'description', 'Nội dung',    'text',           'query',   1,     3,     'none', 'C', 3, TRUE),
(1, 'revenue',     'Doanh thu',   'decimal',        'query',   1,     1,     'none', 'D', 4, TRUE);
```

### C# Entity classes

```csharp
public class MappableEntity
{
    public int EntityId { get; set; }
    public string EntityCode { get; set; } = null!;
    public string DisplayName { get; set; } = null!;
    public string? Description { get; set; }
    public string Category { get; set; } = "revenue";
    public bool IsActive { get; set; }
    public Guid? CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? UpdatedAt { get; set; }
    
    public virtual ICollection<MappableField> Fields { get; set; } = new List<MappableField>();
}

public class MappableField
{
    public int FieldId { get; set; }
    public int EntityId { get; set; }
    public string FieldCode { get; set; } = null!;
    public string DisplayName { get; set; } = null!;
    public string? Description { get; set; }
    public string DataType { get; set; } = null!;           // decimal | date | text | integer | boolean
    public string AllowedAggregations { get; set; } = null!; // JSON: ["sum","none"]
    public bool IsActive { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? UpdatedAt { get; set; }
    
    public virtual MappableEntity Entity { get; set; } = null!;
}

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
    
    // Data source (v2: FK references)
    public string? SourceType { get; set; }
    public int? SourceEntityId { get; set; }   // FK → MappableEntities
    public int? SourceFieldId { get; set; }    // FK → MappableFields
    public string? FilterJson { get; set; }
    public string? AggregationType { get; set; }
    
    // Computed
    public string? FormulaExpression { get; set; }
    public string? DependsOn { get; set; }
    
    // Export
    public string? ExportColumn { get; set; }
    public int SortOrder { get; set; }
    public bool IsRequired { get; set; }
    
    // Navigation
    public virtual AccountingTemplateVersion TemplateVersion { get; set; } = null!;
    public virtual MappableEntity? SourceEntity { get; set; }
    public virtual MappableField? SourceField { get; set; }
}
```

### 1.6 AccountingBooks (Sổ kế toán đã tạo)

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
    
    public int GroupNumber { get; set; }
    public string? TaxMethod { get; set; }
    public int RulesetId { get; set; }
    public Guid? BusinessTypeId { get; set; }
    
    public string Status { get; set; } = "active";
    
    public Guid CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? ArchivedAt { get; set; }
    
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual AccountingPeriod Period { get; set; } = null!;
    public virtual AccountingTemplateVersion TemplateVersion { get; set; } = null!;
    public virtual TaxRuleset Ruleset { get; set; } = null!;
    public virtual User CreatedByUser { get; set; } = null!;
}
```

> **Quan trọng**: `AccountingBooks` **không lưu data**. Nó là một "saved configuration" — khi Owner xem sổ, hệ thống query data realtime từ GL/Orders/Costs/TaxPayments rồi render theo `TemplateFieldMappings`. Data luôn cập nhật theo giao dịch mới nhất.

### 1.7 AccountingExports (Snapshot xuất sổ)

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
    
    public int GroupNumber { get; set; }
    public string? TaxMethod { get; set; }
    public string RulesetVersion { get; set; } = null!;
    
    public string SummaryJson { get; set; } = null!;
    public int DataRowCount { get; set; }
    
    public string ExportFormat { get; set; } = null!;
    public string? FileUrl { get; set; }
    public string? FilePublicId { get; set; }
    
    public Guid ExportedByUserId { get; set; }
    public DateTime ExportedAt { get; set; }
    public string? Notes { get; set; }
    
    public virtual AccountingBook Book { get; set; } = null!;
    public virtual User ExportedByUser { get; set; } = null!;
}
```

### 1.8 TaxPayments (Thuế đã nộp)

```sql
-- =============================================
-- TAX PAYMENTS TABLE (Ghi nhận thuế đã nộp — cho S3a)
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
    
    public virtual BusinessLocation BusinessLocation { get; set; } = null!;
    public virtual AccountingPeriod? Period { get; set; }
    public virtual User CreatedByUser { get; set; } = null!;
}
```

---

## 2. Template Management Flow (NEW v2)

### 2.1 Quyết định thiết kế — Metadata Registry

#### DD-TEMPLATE-01: Metadata Registry thay vì hardcode whitelist

**Vấn đề v1**: TemplateFieldMappings cho phép Admin nhập `SourceEntity` và `SourceField` dạng free text. Hai lựa chọn bảo vệ đều có vấn đề:

| Cách bảo vệ v1 | Vấn đề |
|----------------|--------|
| Free text + regex validation | SQL injection risk, Admin gõ sai tên column → sổ kế toán sai |
| Hardcode whitelist (enum/regex) | Vi phạm DD-04 (data-driven), phải deploy code mỗi lần thêm entity/field |

**Giải pháp v2**: Thêm 2 bảng `MappableEntities` + `MappableFields` làm **Metadata Registry**:

```
┌──────────────────────────────────────────────────────────────────┐
│                    METADATA REGISTRY (v2)                        │
│                                                                  │
│  Admin CRUD ──► MappableEntities ──► MappableFields              │
│                 "orders"              "TotalAmount" (decimal)     │
│                 "gl_entries"          "DebitAmount" (decimal)     │
│                 ...                   ...                         │
│                                                                  │
│  ── khi cần thêm entity/field mới ──                             │
│  Admin INSERT vào MappableEntities/Fields → UI dropdown tự có   │
│  Không deploy code. Tuân thủ DD-04 (data-driven).                │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TemplateFieldMappings.SourceEntityId ──FK──► MappableEntities   │
│  TemplateFieldMappings.SourceFieldId  ──FK──► MappableFields     │
│                                                                  │
│  → DB constraint đảm bảo không thể nhập entity/field ngoài      │
│    whitelist                                                     │
│  → UI Frontend hiện dropdown từ GET /mappable-entities           │
│  → Không cần regex/enum trong backend code                       │
└──────────────────────────────────────────────────────────────────┘
```

**Lợi ích:**

| Tiêu chí | v1 (free text) | v2 (Metadata Registry) |
|----------|----------------|----------------------|
| Tuân thủ DD-04 (data-driven) | ❌ nếu hardcode whitelist | ✅ |
| Chống injection | ❌ | ✅ FK constraint |
| Mở rộng entity/field | Deploy code | INSERT vào DB |
| UI thân thiện | Admin gõ tay tên cột | Dropdown có DisplayName tiếng Việt |
| Validate aggregation | Không | ✅ `AllowedAggregations` per field |

#### DD-TEMPLATE-02: Version lifecycle — Draft → Preview → Active

```
┌──────────────────────────────────────────────────────────────────┐
│              TEMPLATE VERSION LIFECYCLE (v2)                     │
│                                                                  │
│  ┌─────────┐    Clone     ┌─────────┐   Preview    ┌──────────┐ │
│  │ Active  │ ──────────►  │  Draft  │ ───────────► │ Previewed│ │
│  │ Version │              │ (edit)  │  (dry-run    │          │ │
│  │ (v1.0)  │              │         │   with real  │          │ │
│  └─────────┘              └─────────┘   data)      └────┬─────┘ │
│       ▲                                                  │      │
│       │                              Activate            │      │
│       │              ┌──────────────────────────────────┘      │
│       │              ▼                                          │
│       │         ┌──────────┐                                    │
│       └─ deact ─┤  Active  │  (v2.0)                           │
│                 │ Version  │                                    │
│                 └──────────┘                                    │
│                                                                  │
│  Rollback: Reactivate old version bất kỳ lúc nào               │
│  History: Tất cả versions được giữ lại, không xóa              │
└──────────────────────────────────────────────────────────────────┘
```

- **Draft**: Version mới tạo, đang edit FieldMappings. Chưa ảnh hưởng production.
- **Previewed**: Admin đã chạy preview → xem data render thử với location thật.
- **Active**: Version đang phục vụ. Chỉ **1 active version per template**.

> **Lưu ý**: Không tạo thêm cột Status cho version. Dùng `IsActive = true/false` như v1. Trạng thái "draft" ngầm hiểu = version có `IsActive = false` và chưa từng active.

#### DD-TEMPLATE-03: Phân quyền Admin vs Consultant

| Action | Admin | Consultant | Lý do |
|--------|:-----:|:----------:|-------|
| CRUD MappableEntities/Fields | ✅ | ❌ | Thay đổi schema whitelist → ảnh hưởng toàn hệ thống |
| View MappableEntities/Fields | ✅ | ✅ | Cần xem để hiểu mapping |
| Clone version (tạo draft) | ✅ | ✅ | Cả hai cần tạo mapping mới |
| Edit FieldMappings (draft) | ✅ | ✅ | Cả hai cần config sổ |
| Preview version (dry-run) | ✅ | ✅ | Cả hai cần kiểm tra |
| **Activate version** | ✅ | ❌ | **Chỉ Admin** — ảnh hưởng tất cả Owner |
| Rollback (reactivate old) | ✅ | ❌ | Tương đương activate |

### 2.2 Admin Flow: Quản lý Metadata Registry

```
Admin muốn hệ thống nhận diện thêm entity/field mới
(ví dụ: bảng Expenses mới, hoặc cột DiscountAmount mới trong Orders)
│
├── 1. POST /api/admin/mappable-entities
│       { "entityCode": "expenses", "displayName": "Chi phí khác", "category": "cost" }
│
├── 2. POST /api/admin/mappable-entities/{entityId}/fields
│       { "fieldCode": "ExpenseAmount", "displayName": "Số tiền", "dataType": "decimal",
│         "allowedAggregations": ["sum","avg","none"] }
│
├── 3. Ngay lập tức:
│       → UI Admin khi tạo FieldMapping sẽ thấy "Chi phí khác" trong dropdown Entity
│       → Chọn "Chi phí khác" → dropdown Field hiện "Số tiền"
│       → Không deploy code
│
└── 4. Deactivate entity/field cũ nếu không dùng nữa
        → PATCH /api/admin/mappable-entities/{id}/deactivate
        → Mapping cũ tham chiếu entity này vẫn hoạt động bình thường
        → Dropdown chỉ ẩn entity/field cho mapping MỚI
```

### 2.3 Admin Flow: Quản lý Template + FieldMappings

```
Admin/Consultant muốn sửa mapping cho template S2a
│
├── 1. GET /api/admin/accounting-templates
│       → Xem list templates, chọn S2a (TemplateId=2)
│
├── 2. GET /api/admin/accounting-templates/2/versions
│       → Xem versions, thấy v1.0 đang Active
│
├── 3. POST /api/admin/accounting-templates/2/versions/clone
│       → Clone v1.0 → tạo v2.0 (draft, IsActive=false)
│       → v2.0 kế thừa tất cả FieldMappings từ v1.0
│
├── 4. Edit FieldMappings trên v2.0 (draft):
│       │
│       ├── GET /api/admin/mappable-entities?active=true
│       │       → Dropdown Entity: ["Đơn hàng", "Chi tiết đơn hàng", "Sổ cái"...]
│       │
│       ├── GET /api/admin/mappable-entities/{entityId}/fields?active=true
│       │       → Dropdown Field (phụ thuộc entity đã chọn):
│       │         ["Tổng tiền", "Ngày hoàn tất", "Mã đơn hàng"...]
│       │
│       ├── POST /api/admin/template-versions/{versionId}/field-mappings
│       │       → Thêm mapping mới (chọn entity+field từ dropdown)
│       │
│       ├── PUT /api/admin/template-versions/{versionId}/field-mappings/{mappingId}
│       │       → Sửa mapping
│       │
│       └── DELETE /api/admin/template-versions/{versionId}/field-mappings/{mappingId}
│               → Xóa mapping (chỉ draft version)
│
├── 5. Preview (xem Section 2.4)
│
├── 6. Activate (Admin only):
│       PUT /api/admin/accounting-templates/versions/{versionId}/activate
│       → v1.0 deactivate, v2.0 activate
│       → Tất cả AccountingBooks đang dùng template S2a sẽ dùng v2.0
│
└── 7. Rollback nếu cần:
        PUT /api/admin/accounting-templates/versions/{v1VersionId}/activate
        → Reactivate v1.0, deactivate v2.0
```

### 2.4 Preview / Dry-run trước khi activate

> **Mục đích**: Admin xem dữ liệu render thực tế với mapping draft, trước khi ảnh hưởng production.

```yaml
POST /api/admin/template-versions/{versionId}/preview
Authorization: Bearer {admin_or_consultant_token}

Request:
{
  "locationId": 1,                    # Location thật để lấy data thử
  "periodId": 1,                      # Kỳ kế toán thử
  "businessTypeId": "bt-retail",      # Optional, cho template tách ngành
  "maxRows": 20                       # Giới hạn rows trả về (tránh data lớn)
}

Response:
{
  "templateCode": "S2a",
  "versionLabel": "v2.0 (draft)",
  "previewStatus": "success",         # success | warning | error
  
  "columns": [
    { "fieldCode": "stt",  "label": "STT",  "sourceEntity": "—", "sourceField": "—" },
    { "fieldCode": "date", "label": "Ngày", "sourceEntity": "Đơn hàng", "sourceField": "Ngày hoàn tất" },
    { "fieldCode": "desc", "label": "Nội dung", "sourceEntity": "Đơn hàng", "sourceField": "Mã đơn hàng" },
    { "fieldCode": "revenue", "label": "Doanh thu", "sourceEntity": "Đơn hàng", "sourceField": "Tổng tiền" }
  ],
  
  "rows": [
    { "stt": 1, "date": "2026-01-15", "desc": "ORD-001", "revenue": 4750000 },
    { "stt": 2, "date": "2026-01-20", "desc": "ORD-002", "revenue": 9500000 }
  ],
  
  "summary": {
    "totalRows": 342,
    "previewedRows": 20,
    "totalRevenue": 620000000
  },
  
  "warnings": [
    "Field 'vat_amount' có FormulaExpression nhưng DependsOn chứa 'vat_rate' — field 'vat_rate' chưa tồn tại trong version này"
  ],
  
  "errors": []
}
```

**Validation trong Preview:**

| Check | Loại | Mô tả |
|-------|------|-------|
| SourceEntityId/SourceFieldId tồn tại và active | Error | FK bị deactivate → mapping sẽ fail |
| AggregationType nằm trong AllowedAggregations | Error | Vd: `sum` trên field `text` |
| FormulaExpression tham chiếu FieldCode tồn tại | Warning | DependsOn field chưa khai báo |
| Có data thực để render | Warning | Location không có order nào trong period |
| ExportColumn unique trong version | Error | 2 fields cùng map vào cột A |

### 2.5 Phân quyền Admin vs Consultant

Tóm tắt phân quyền cho tất cả API trong section 2:

| API Group | Endpoint Pattern | Admin | Consultant | Owner |
|-----------|-----------------|:-----:|:----------:|:-----:|
| Metadata Registry | `/api/admin/mappable-entities/**` (CRUD) | ✅ | ❌ | ❌ |
| Metadata Registry | `/api/admin/mappable-entities/**` (GET) | ✅ | ✅ | ❌ |
| Templates | `/api/admin/accounting-templates` (GET) | ✅ | ✅ | ❌ |
| Template Versions | Clone, Edit FieldMappings, Preview | ✅ | ✅ | ❌ |
| Template Versions | **Activate / Rollback** | ✅ | ❌ | ❌ |
| Accounting Books | `/api/v1/locations/{id}/accounting/**` | ❌ | ❌ | ✅ |

---

## 3. Accounting Book Generation Flow

### 3.1 Flow tổng quan

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
│   (v2: resolve qua Metadata      │
│    Registry FK)                   │
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

### 3.2 Create Book API

```yaml
POST /api/v1/locations/{locationId}/accounting/books
Authorization: Bearer {token}

Request:
{
  "periodId": 1,
  "groupNumber": 2,
  "taxMethod": "method_1",
  "businessTypeId": null
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

### 3.3 View Book Data (Live)

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

### 3.4 Export Book

```yaml
POST /api/v1/locations/{locationId}/accounting/books/{bookId}/export
Authorization: Bearer {token}

Request:
{
  "format": "xlsx",
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

## 4. TT152 Book Specifications (S1a, S2a–S2e)

### 4.1 S1a — Sổ chi tiết bán hàng (Nhóm 1)

**Áp dụng**: Nhóm 1 (DT < 500 triệu/năm) — miễn thuế GTGT & TNCN.

| STT | Ngày tháng | Nội dung (Diễn giải) | Doanh thu bán hàng |
|:---:|:----------:|---------------------|-------------------:|
| 1 | 15/01/2026 | ORD-20260115-001: Bán Xi măng HT 50 bao | 4,750,000 |
| 2 | 15/01/2026 | ORD-20260115-003: Bán Cát xây dựng 200 kg | 600,000 |
| ... | ... | ... | ... |
| | | **Cộng tháng 01** | **45,200,000** |
| ... | ... | ... | ... |
| | | **Cộng quý I** | **120,500,000** |

**Data source**: `Revenues` (sale + manual) + `GL WHERE TransactionType = 'manual_revenue'`

**Rendering logic**:

```sql
-- Revenues (auto + manual)
SELECT 
    COALESCE(o.OrderCode, CONCAT('MAN-', r.RevenueId)) AS SoHieu,
    r.RevenueDate AS NgayThang,
    r.Description AS NoiDung,
    r.Amount AS DoanhThu
FROM Revenues r
LEFT JOIN Orders o ON o.OrderId = r.OrderId
WHERE r.BusinessLocationId = @locationId
  AND r.DeletedAt IS NULL
  AND r.RevenueDate BETWEEN @startDate AND @endDate

UNION ALL

-- Manual GL revenue entries (đường tự do)
SELECT 
    CONCAT('GL-', gle.EntryId) AS SoHieu,
    gle.EntryDate AS NgayThang,
    CONCAT('[GL] ', gle.Description) AS NoiDung,
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

ORDER BY NgayThang, SoHieu;
```

### 4.2 S2a — Sổ doanh thu bán hàng hóa, dịch vụ (Nhóm 2 Cách 1)

**Áp dụng**: Nhóm 2 (500 triệu – 3 tỷ), Cách 1 tính thuế (% DT theo ngành).

> **Mục đích**: Ghi doanh thu theo **từng nhóm ngành nghề** có cùng tỷ lệ % thuế GTGT hoặc cùng thuế suất TNCN. Cuối kỳ tính ra thuế GTGT + TNCN phải nộp dựa theo công thức lưu trong DB.

**Mở sổ**: Khi location có nhiều nhóm ngành → **mỗi nhóm ngành 1 sổ S2a riêng** (theo DD-01 trong [report-accounting-flow.md](report-accounting-flow.md)). Nếu HKD chỉ có 1 ngành → 1 sổ duy nhất.

**Cấu trúc sổ:**

| Chứng từ — Số hiệu (A) | Chứng từ — Ngày tháng (B) | Diễn giải (C) | Số tiền (1) |
|:-----------------------:|:-------------------------:|--------------|------------:|
| ORD-20260115-001 | 15/01/2026 | Bán Xi măng HT 50 bao | 4,750,000 |
| ORD-20260115-003 | 15/01/2026 | Bán Cát xây dựng 200 kg | 600,000 |
| ... | ... | ... | ... |
| | | **Cộng quý I** | **500,000,000** |
| | | **Thuế GTGT phải nộp (1%)** | **5,000,000** |
| | | **Thuế TNCN phải nộp (0.5%)** | **0** |

> **Cách tính thuế (Cách 1):**
> - Thuế GTGT = Tổng DT × tỷ lệ % GTGT theo ngành (từ `IndustryTaxRates`)
> - Thuế TNCN = (Tổng DT - mức miễn 500 triệu) × tỷ lệ % TNCN theo ngành
> - Mức trừ 500 triệu áp dụng **1 lần** cho toàn HKD, không phải mỗi ngành
> - **Công thức lưu trong DB** (xem DD-TAX-FORMULA bên dưới) → khi quy định thay đổi, update công thức trong DB, không deploy code

> **Đối chiếu thuế**: Nếu cơ quan thuế cung cấp dữ liệu nộp thuế GTGT/TNCN → Owner sử dụng sổ này để theo dõi, đối chiếu.

**Data source**: `Revenues (join OrderDetails → Product.BusinessTypeId)` + `GL WHERE TransactionType = 'manual_revenue'` + `IndustryTaxRates` + `TaxFormulas`

**Rendering logic**:

```sql
-- ═══ CÁC DÒNG DOANH THU ═══
-- Revenues auto (từ Order, tách theo ngành)
SELECT 
    o.OrderCode AS SoHieu,
    r.RevenueDate AS NgayThang,
    CONCAT(o.OrderCode, ': ', GROUP_CONCAT(DISTINCT od.ProductName SEPARATOR ', ')) AS DienGiai,
    r.Amount AS SoTien
FROM Revenues r
JOIN Orders o ON o.OrderId = r.OrderId
JOIN OrderDetails od ON od.OrderId = o.OrderId
JOIN Products p ON od.ProductId = p.ProductId
WHERE r.BusinessLocationId = @locationId
  AND r.RevenueType = 'sale'
  AND r.DeletedAt IS NULL
  AND p.BusinessTypeId = @businessTypeId
  AND r.RevenueDate BETWEEN @startDate AND @endDate
GROUP BY r.RevenueId

UNION ALL

-- Revenues manual (Owner tự khai, nếu có gán BusinessTypeId)
SELECT 
    CONCAT('MAN-', r.RevenueId) AS SoHieu,
    r.RevenueDate AS NgayThang,
    CONCAT('[THỦ CÔNG] ', r.Description) AS DienGiai,
    r.Amount AS SoTien
FROM Revenues r
WHERE r.BusinessLocationId = @locationId
  AND r.RevenueType = 'manual'
  AND r.DeletedAt IS NULL
  AND r.RevenueDate BETWEEN @startDate AND @endDate

UNION ALL

-- Manual GL revenue entries (đường tự do)
SELECT 
    CONCAT('GL-', gle.EntryId) AS SoHieu,
    gle.EntryDate AS NgayThang,
    CONCAT('[GL] ', gle.Description) AS DienGiai,
    gle.DebitAmount AS SoTien
FROM GeneralLedgerEntries gle
WHERE gle.BusinessLocationId = @locationId
  AND gle.TransactionType = 'manual_revenue'
  AND gle.IsReversal = FALSE
  AND NOT EXISTS (
      SELECT 1 FROM GeneralLedgerEntries r 
      WHERE r.ReversedEntryId = gle.EntryId
  )
  AND gle.EntryDate BETWEEN @startDate AND @endDate

ORDER BY NgayThang, SoHieu;

-- ═══ DÒNG CUỐI: TÍNH THUẾ (dùng công thức từ DB) ═══
-- Sau khi có Tổng DT (@totalRevenue), apply TaxFormulas:
--   GTGT = @totalRevenue × IndustryTaxRates.VatRate (WHERE BusinessTypeId = @btId)
--   TNCN = TaxFormulas.Calculate(@totalRevenue, @pitRate, @threshold)
```

> **Lưu ý**: Manual revenue entries + manual GL entries không có `BusinessTypeId` → hiển thị cuối sổ hoặc Owner chọn ngành khi nhập.

#### DD-TAX-FORMULA: Công thức thuế lưu động trong DB

Công thức tính thuế GTGT/TNCN ở dòng cuối S2a/S2b **không hardcode** — lưu trong DB để có thể update khi quy định thay đổi:

```sql
-- Ví dụ cấu trúc (nằm trong TaxRulesets hoặc table riêng TaxFormulas)
-- Chi tiết table design sẽ bổ sung trong rule-engine-flow.md
--
-- Cách 1 (S2a):
--   GTGT: DT_ngành × tỷ_lệ_GTGT_ngành
--   TNCN: MAX(0, DT_tổng - mức_miễn) × tỷ_lệ_TNCN_ngành
--
-- Cách 2 (S2b):
--   GTGT: DT_ngành × tỷ_lệ_GTGT_ngành
--   TNCN: Không tính ở S2b — tính ở S2c (DT - CP)
```

> **Workflow**: Điền dữ liệu doanh thu vào sổ → tính tổng DT → apply công thức từ DB → điền kết quả vào dòng cuối.

### 4.3 S2b — Sổ doanh thu bán hàng hóa, dịch vụ (Nhóm 2 Cách 2, Nhóm 3-4)

**Áp dụng**: Nhóm 2 (Cách 2: tính thuế trên DT - CP) + Nhóm 3 + Nhóm 4

> **Mục đích**: Giống S2a — ghi DT theo ngành có cùng tỷ lệ % thuế GTGT. Khác S2a ở chỗ: chỉ tính **thuế GTGT** ở dòng cuối (thuế TNCN tính qua S2c dựa trên chênh lệch DT - CP).

**Mở sổ**: Tương tự S2a — mỗi nhóm ngành 1 sổ riêng.

**Cấu trúc sổ:**

| Chứng từ — Số hiệu (A) | Chứng từ — Ngày tháng (B) | Diễn giải (C) | Số tiền (1) |
|:-----------------------:|:-------------------------:|--------------|------------:|
| ORD-20260115-001 | 15/01/2026 | Bán Xi măng HT 50 bao | 4,750,000 |
| ORD-20260116-005 | 16/01/2026 | Bán Sắt thép 100 kg | 3,200,000 |
| ... | ... | ... | ... |
| | | **Cộng quý I** | **620,000,000** |
| | | **Thuế GTGT phải nộp (1%)** | **6,200,000** |

> **Khác biệt S2a vs S2b:**
>
> | | S2a (Cách 1) | S2b (Cách 2+) |
> |---|---|---|
> | Tính GTGT ở dòng cuối | ✅ DT × tỷ lệ % GTGT | ✅ DT × tỷ lệ % GTGT |
> | Tính TNCN ở dòng cuối | ✅ DT × tỷ lệ % TNCN (trực tiếp) | ❌ Không — TNCN tính ở S2c |
> | Lý do | Cách 1: thuế = % trên DT | Cách 2: thuế TNCN = % trên (DT - CP) |

**Data source**: Giống S2a — `Revenues` + `GL manual_revenue` + `IndustryTaxRates` + `TaxFormulas`

**Rendering logic**: Giống S2a. Dòng cuối chỉ có thuế GTGT, không có TNCN.

```sql
-- Query data giống S2a (xem section 4.2)
-- Dòng cuối:
--   GTGT = @totalRevenue × IndustryTaxRates.VatRate
--   (Không tính TNCN — tính ở S2c)
```

### 4.4 S2c — Sổ chi tiết doanh thu, chi phí

**Áp dụng**: Nhóm 2 (Cách 2) + Nhóm 3 + Nhóm 4

> **Mục đích**: Ghi **cả doanh thu VÀ chi phí**, tính chênh lệch = thu nhập chịu thuế TNCN. Đây là căn cứ tính thuế TNCN cho Cách 2 (thay vì tính % trực tiếp trên DT như Cách 1).

**Cấu trúc sổ:**

| Chứng từ — Số hiệu (A) | Chứng từ — Ngày tháng (B) | Diễn giải (C) | Số tiền (1) |
|:-----------------------:|:-------------------------:|--------------|------------:|
| | | **I. DOANH THU** | |
| ORD-20260115-001 | 15/01/2026 | Bán Xi măng HT 50 bao | 4,750,000 |
| ORD-20260115-003 | 15/01/2026 | Bán Cát xây dựng 200 kg | 600,000 |
| ... | ... | ... | ... |
| | | **Tổng doanh thu** | **620,000,000** |
| | | **II. CHI PHÍ HỢP LÝ** | |
| PNK-20260110-001 | 10/01/2026 | Nhập Xi măng từ Công ty ABC | 8,500,000 |
| | 15/01/2026 | Thuê mặt bằng T1/2026 | 5,000,000 |
| | 20/01/2026 | Tiền điện T1/2026 | 1,200,000 |
| ... | ... | ... | ... |
| | | **Tổng chi phí hợp lý** | **85,000,000** |
| | | **III. CHÊNH LỆCH (DT - CP)** | **535,000,000** |
| | | **Thuế TNCN phải nộp** | **...** |

> **Cách ghi sổ (theo TT152):**
> - **Dòng I**: Tổng DT bán hàng hóa, dịch vụ — có thể ghi tổng hoặc chi tiết từng nghiệp vụ tùy nhu cầu
> - **Dòng II**: Tổng chi phí hợp lý — các chi phí thực tế phát sinh, có thể ghi tổng hoặc chi tiết
> - **Chênh lệch** = Tổng DT - Tổng CP → căn cứ tính thuế TNCN
> - **Thuế TNCN** = Apply công thức từ DB (TaxFormulas) lên chênh lệch

**Data sources**:
- Doanh thu: `Revenues` (sale + manual) + `GL WHERE TransactionType = 'manual_revenue'`
- Chi phí: `Costs` (import + manual) + `GL WHERE TransactionType = 'manual_expense'`

**Rendering logic**:

```sql
-- ═══ PHẦN I: DOANH THU ═══
-- (Giống S2a/S2b query nhưng không tách theo ngành)
SELECT 
    COALESCE(o.OrderCode, CONCAT('MAN-', r.RevenueId)) AS SoHieu,
    r.RevenueDate AS NgayThang,
    r.Description AS DienGiai,
    r.Amount AS SoTien,
    'revenue' AS Section
FROM Revenues r
LEFT JOIN Orders o ON o.OrderId = r.OrderId
WHERE r.BusinessLocationId = @locationId
  AND r.DeletedAt IS NULL
  AND r.RevenueDate BETWEEN @startDate AND @endDate

UNION ALL

-- Manual GL revenue
SELECT 
    CONCAT('GL-', gle.EntryId) AS SoHieu,
    gle.EntryDate AS NgayThang,
    CONCAT('[GL] ', gle.Description) AS DienGiai,
    gle.DebitAmount AS SoTien,
    'revenue' AS Section
FROM GeneralLedgerEntries gle
WHERE gle.BusinessLocationId = @locationId
  AND gle.TransactionType = 'manual_revenue'
  AND gle.IsReversal = FALSE
  AND NOT EXISTS (SELECT 1 FROM GeneralLedgerEntries r WHERE r.ReversedEntryId = gle.EntryId)
  AND gle.EntryDate BETWEEN @startDate AND @endDate

UNION ALL

-- ═══ PHẦN II: CHI PHÍ HỢP LÝ ═══
SELECT 
    COALESCE(i.ImportCode, CONCAT('COST-', c.CostId)) AS SoHieu,
    c.CostDate AS NgayThang,
    c.Description AS DienGiai,
    c.Amount AS SoTien,
    'cost' AS Section
FROM Costs c
LEFT JOIN Imports i ON i.ImportId = c.ImportId
WHERE c.BusinessLocationId = @locationId
  AND c.DeletedAt IS NULL
  AND c.CostDate BETWEEN @startDate AND @endDate

UNION ALL

-- Manual GL expense
SELECT 
    CONCAT('GL-', gle.EntryId) AS SoHieu,
    gle.EntryDate AS NgayThang,
    CONCAT('[GL] ', gle.Description) AS DienGiai,
    gle.CreditAmount AS SoTien,
    'cost' AS Section
FROM GeneralLedgerEntries gle
WHERE gle.BusinessLocationId = @locationId
  AND gle.TransactionType = 'manual_expense'
  AND gle.IsReversal = FALSE
  AND NOT EXISTS (SELECT 1 FROM GeneralLedgerEntries r WHERE r.ReversedEntryId = gle.EntryId)
  AND gle.EntryDate BETWEEN @startDate AND @endDate

ORDER BY Section, NgayThang, SoHieu;

-- ═══ DÒNG CUỐI: THUẾ TNCN ═══
-- Chênh lệch = SUM(revenue) - SUM(cost)
-- TNCN = TaxFormulas.Calculate(@chenhLech, @pitRateMethod2)
```

### 4.5 S2d — Sổ chi tiết vật liệu, dụng cụ, sản phẩm, hàng hóa

**Áp dụng**: Nhóm 2 (Cách 2) + Nhóm 3 + Nhóm 4

> **Mục đích**: Sổ kho XNT (nhập/xuất/tồn) — theo dõi số lượng và giá trị vật liệu, dụng cụ, sản phẩm, hàng hóa. Mỗi sản phẩm 1 trang sổ riêng.

**Cấu trúc sổ (mỗi sản phẩm 1 trang):**

| Chứng từ | | Diễn giải | ĐVT | Đơn giá | Nhập | | Xuất | | Tồn | |
|:--------:|:-:|----------|:---:|--------:|-----:|------:|-----:|------:|----:|------:|
| Số hiệu (A) | Ngày (B) | (C) | (D) | (1) | SL (2) | Tiền (3) | SL (4) | Tiền (5) | SL (6) | Tiền (7) |
| | | **Tồn đầu kỳ** | Bao | 85,000 | | | | | 200 | 17,000,000 |
| PNK-001 | 15/01 | Nhập từ NCC ABC | Bao | 85,000 | 100 | 8,500,000 | | | 300 | 25,500,000 |
| ORD-005 | 20/01 | Bán hàng | Bao | 85,000 | | | 24 | 2,040,000 | 276 | 23,460,000 |
| PNK-012 | 01/02 | Nhập từ NCC XYZ | Bao | 87,000 | 100 | 8,700,000 | | | 376 | 32,160,000 |
| ORD-015 | 10/02 | Bán hàng | Bao | **85,532** | | | 126 | 10,777,032 | 250 | 21,382,968 |
| | | **Tồn cuối kỳ** | Bao | | | | | | 250 | 21,382,968 |

> **Đơn giá xuất kho — Bình quân gia quyền cuối kỳ (TT152):**
>
> $$\text{Đơn giá xuất kho} = \frac{\text{Giá trị tồn đầu kỳ} + \text{Giá trị nhập trong kỳ}}{\text{SL tồn đầu kỳ} + \text{SL nhập trong kỳ}}$$
>
> **Ví dụ**: $(17{,}000{,}000 + 8{,}500{,}000 + 8{,}700{,}000) ÷ (200 + 100 + 100) = 85{,}500đ$ → đơn giá xuất cho tất cả dòng xuất trong kỳ.
>
> **Cách A (đã xác nhận)**: StockMovements v2 ghi giá thực tế (`UnitCostPrice` từ `Product.CostPrice`). Khi render sổ S2d, **tính lại** đơn giá xuất kho theo bình quân gia quyền cuối kỳ.

**Data source**: `StockMovements` (xem [cost-gl-flow-v2.md](cost-gl-flow-v2.md) Section 7)

**Rendering logic**:

```sql
-- ═══ BƯỚC 1: Tồn đầu kỳ ═══
SELECT 
    sm.ProductId,
    p.ProductName,
    p.Unit,
    COALESCE(SUM(sm.QuantityDelta), 0) AS OpeningQty
FROM StockMovements sm
JOIN Products p ON p.ProductId = sm.ProductId
WHERE sm.BusinessLocationId = @locationId
  AND sm.ProductId = @productId
  AND sm.CreatedAt < @periodStart
GROUP BY sm.ProductId;

-- Giá trị tồn đầu kỳ = SUM(signed TotalValue) before period
SELECT 
    COALESCE(SUM(
        CASE WHEN sm.QuantityDelta > 0 THEN sm.TotalValue
             ELSE -sm.TotalValue END
    ), 0) AS OpeningValue
FROM StockMovements sm
WHERE sm.BusinessLocationId = @locationId
  AND sm.ProductId = @productId
  AND sm.CreatedAt < @periodStart;

-- ═══ BƯỚC 2: Nhập trong kỳ ═══
SELECT 
    SUM(sm.QuantityDelta) AS ImportQty,
    SUM(sm.TotalValue) AS ImportValue
FROM StockMovements sm
WHERE sm.BusinessLocationId = @locationId
  AND sm.ProductId = @productId
  AND sm.CreatedAt BETWEEN @periodStart AND @periodEnd
  AND sm.QuantityDelta > 0;

-- ═══ BƯỚC 3: Tính đơn giá xuất kho (bình quân gia quyền) ═══
-- @avgExportPrice = (@openingValue + @importValue) / (@openingQty + @importQty)

-- ═══ BƯỚC 4: Các dòng chi tiết trong kỳ ═══
SELECT 
    sm.DocumentCode AS SoHieu,
    DATE(sm.CreatedAt) AS Ngay,
    CASE 
        WHEN sm.QuantityDelta > 0 THEN CONCAT('Nhập: ', sm.Note)
        ELSE CONCAT('Xuất: ', sm.Note)
    END AS DienGiai,
    -- Nhập
    CASE WHEN sm.QuantityDelta > 0 THEN sm.UnitCostPrice END AS DonGiaNhap,
    CASE WHEN sm.QuantityDelta > 0 THEN sm.QuantityDelta END AS SLNhap,
    CASE WHEN sm.QuantityDelta > 0 THEN sm.TotalValue END AS TienNhap,
    -- Xuất (dùng đơn giá bình quân)
    CASE WHEN sm.QuantityDelta < 0 THEN @avgExportPrice END AS DonGiaXuat,
    CASE WHEN sm.QuantityDelta < 0 THEN ABS(sm.QuantityDelta) END AS SLXuat,
    CASE WHEN sm.QuantityDelta < 0 THEN ABS(sm.QuantityDelta) * @avgExportPrice END AS TienXuat,
    -- Running tồn
    sm.StockAfter AS SLTon
FROM StockMovements sm
WHERE sm.BusinessLocationId = @locationId
  AND sm.ProductId = @productId
  AND sm.CreatedAt BETWEEN @periodStart AND @periodEnd
ORDER BY sm.CreatedAt, sm.StockMovementId;

-- Giá trị tồn = SLTon × @avgExportPrice (hoặc tính từ OpeningValue + ImportValue - ExportValue)
```

### 4.6 S2e — Sổ chi tiết tiền

**Áp dụng**: Nhóm 2 (Cách 2) + Nhóm 3 + Nhóm 4

> **Mục đích**: Theo dõi tiền mặt thu/chi và tiền gửi không kỳ hạn gửi vào/rút ra. Cuối kỳ tính tồn quỹ tiền mặt + dư tiền gửi cuối kỳ. **1 sổ gộp** gồm 2 phần: Tiền mặt + Tiền gửi không kỳ hạn.

**Cấu trúc sổ:**

| Chứng từ — Số hiệu (A) | Chứng từ — Ngày tháng (B) | Diễn giải (C) | Thu/Gửi vào (1) | Chi/Rút ra (2) |
|:-----------------------:|:-------------------------:|--------------|----------------:|---------------:|
| | | **TIỀN MẶT** | | |
| | | Tiền mặt đầu kỳ | 10,000,000 | |
| ORD-001 | 15/01/2026 | Bán hàng (tiền mặt) | 600,000 | |
| PNK-002 | 16/01/2026 | Nhập hàng (tiền mặt) | | 8,500,000 |
| | 20/01/2026 | Thu nợ Anh Ba (tiền mặt) | 300,000 | |
| | 25/01/2026 | Thuê mặt bằng | | 5,000,000 |
| ... | ... | ... | ... | ... |
| | | **Tổng tiền thu vào trong kỳ** | **xx** | |
| | | **Tổng tiền chi ra trong kỳ** | | **xx** |
| | | **Tiền mặt tồn cuối kỳ** | **xx** | |
| | | **TIỀN GỬI KHÔNG KỲ HẠN** | | |
| | | *Ngân hàng ABC...* | | |
| | | Tiền gửi đầu kỳ | 50,000,000 | |
| ORD-005 | 16/01/2026 | Bán hàng (chuyển khoản) | 3,200,000 | |
| ... | ... | ... | ... | ... |
| | | **Tổng gửi vào trong kỳ** | **xx** | |
| | | **Tổng rút ra trong kỳ** | | **xx** |
| | | **Dư cuối kỳ** | **xx** | |

**Data source**: `GeneralLedgerEntries` filter by `MoneyChannel` + opening/closing balance từ `AccountingPeriods`

**Rendering logic**:

```sql
-- ═══ PHẦN 1: TIỀN MẶT ═══
-- Opening balance
SELECT ap.OpeningCashBalance FROM AccountingPeriods ap WHERE ap.PeriodId = @periodId;

-- Transactions (tiền mặt)
SELECT 
    CASE 
        WHEN gle.ReferenceType = 'revenue' THEN (SELECT o.OrderCode FROM Revenues rv JOIN Orders o ON o.OrderId = rv.OrderId WHERE rv.RevenueId = gle.ReferenceId)
        WHEN gle.ReferenceType = 'cost' THEN (SELECT i.ImportCode FROM Costs c JOIN Imports i ON i.ImportId = c.ImportId WHERE c.CostId = gle.ReferenceId)
        ELSE CONCAT('GL-', gle.EntryId)
    END AS SoHieu,
    gle.EntryDate AS NgayThang,
    gle.Description AS DienGiai,
    CASE WHEN gle.DebitAmount > 0 THEN gle.DebitAmount ELSE NULL END AS ThuVao,
    CASE WHEN gle.CreditAmount > 0 THEN gle.CreditAmount ELSE NULL END AS ChiRa
FROM GeneralLedgerEntries gle
WHERE gle.BusinessLocationId = @locationId
  AND gle.MoneyChannel = 'cash'
  AND gle.EntryDate BETWEEN @startDate AND @endDate
ORDER BY gle.EntryDate, gle.EntryId;

-- Closing: OpeningCash + SUM(ThuVao) - SUM(ChiRa)

-- ═══ PHẦN 2: TIỀN GỬI KHÔNG KỲ HẠN ═══
-- Opening balance
SELECT ap.OpeningBankBalance FROM AccountingPeriods ap WHERE ap.PeriodId = @periodId;

-- Transactions (chuyển khoản)
SELECT 
    CASE 
        WHEN gle.ReferenceType = 'revenue' THEN (SELECT o.OrderCode FROM Revenues rv JOIN Orders o ON o.OrderId = rv.OrderId WHERE rv.RevenueId = gle.ReferenceId)
        WHEN gle.ReferenceType = 'cost' THEN (SELECT i.ImportCode FROM Costs c JOIN Imports i ON i.ImportId = c.ImportId WHERE c.CostId = gle.ReferenceId)
        ELSE CONCAT('GL-', gle.EntryId)
    END AS SoHieu,
    gle.EntryDate AS NgayThang,
    gle.Description AS DienGiai,
    CASE WHEN gle.DebitAmount > 0 THEN gle.DebitAmount ELSE NULL END AS GuiVao,
    CASE WHEN gle.CreditAmount > 0 THEN gle.CreditAmount ELSE NULL END AS RutRa
FROM GeneralLedgerEntries gle
WHERE gle.BusinessLocationId = @locationId
  AND gle.MoneyChannel = 'bank'
  AND gle.EntryDate BETWEEN @startDate AND @endDate
ORDER BY gle.EntryDate, gle.EntryId;

-- Closing: OpeningBank + SUM(GuiVao) - SUM(RutRa)
```

> **Lưu ý**: 
> - GL entries với `MoneyChannel = 'debt'` **không xuất hiện** trong S2e (ghi nợ không phải dòng tiền thực tế)
> - Opening balance lấy từ `AccountingPeriods.OpeningCashBalance / OpeningBankBalance`
> - Closing = opening + net trong kỳ
> - Khi tạo kỳ mới, closing kỳ trước tự become opening kỳ sau (xem [accounting-period-flow.md](accounting-period-flow.md) RULE-PERIOD-06)

---

## 5. Business Rules

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
| **RULE-META-01** | (v2) TemplateFieldMappings.SourceEntityId/SourceFieldId PHẢI tham chiếu MappableEntities/MappableFields active |
| **RULE-META-02** | (v2) AggregationType phải nằm trong AllowedAggregations của MappableField tương ứng |
| **RULE-META-03** | (v2) Deactivate MappableEntity/Field không ảnh hưởng mapping cũ, chỉ ẩn khỏi dropdown tạo mapping mới |
| **RULE-META-04** | (v2) Khi tạo FieldMapping mới, nếu SourceType = 'query' thì SourceEntityId và SourceFieldId bắt buộc |
| **RULE-META-05** | (v2) Khi tạo FieldMapping mới, nếu SourceType = 'formula' thì FormulaExpression bắt buộc, DependsOn phải chứa FieldCode tồn tại trong cùng version |
| **RULE-VER-01** | (v2) Chỉ sửa/xóa FieldMappings trên version chưa active (draft). Version đã active → frozen. |
| **RULE-VER-02** | (v2) Clone version active → tạo draft mới kế thừa tất cả FieldMappings |
| **RULE-VER-03** | (v2) Activate version mới → deactivate version cũ. Chỉ 1 active per template. |
| **RULE-VER-04** | (v2) Trước khi activate, khuyến nghị chạy Preview để kiểm tra data render đúng |
| **RULE-VER-05** | (v2) Chỉ Admin được activate/rollback. Consultant được clone, edit, preview. |

---

## 6. API Endpoints

### Metadata Registry (NEW v2) — Admin only

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/admin/mappable-entities` | List entities (filter: active/all) | Admin, Consultant |
| `GET` | `/api/admin/mappable-entities/{id}` | Get entity + fields | Admin, Consultant |
| `POST` | `/api/admin/mappable-entities` | Tạo entity mới | Admin |
| `PUT` | `/api/admin/mappable-entities/{id}` | Cập nhật entity | Admin |
| `PATCH` | `/api/admin/mappable-entities/{id}/deactivate` | Deactivate entity | Admin |
| `GET` | `/api/admin/mappable-entities/{id}/fields` | List fields (filter: active/all) | Admin, Consultant |
| `POST` | `/api/admin/mappable-entities/{id}/fields` | Thêm field mới | Admin |
| `PUT` | `/api/admin/mappable-fields/{fieldId}` | Cập nhật field | Admin |
| `PATCH` | `/api/admin/mappable-fields/{fieldId}/deactivate` | Deactivate field | Admin |

### Accounting Templates — Admin/Consultant

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/admin/accounting-templates` | List templates | Admin, Consultant |
| `GET` | `/api/admin/accounting-templates/{id}/versions` | List versions | Admin, Consultant |
| `POST` | `/api/admin/accounting-templates/{id}/versions/clone` | Clone active → draft | Admin, Consultant |
| `PUT` | `/api/admin/accounting-templates/versions/{versionId}/activate` | Activate version | **Admin only** |

### Template Field Mappings — Admin/Consultant (draft version only)

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/admin/template-versions/{versionId}/field-mappings` | List field mappings | Admin, Consultant |
| `POST` | `/api/admin/template-versions/{versionId}/field-mappings` | Thêm mapping (dropdown-based) | Admin, Consultant |
| `PUT` | `/api/admin/template-versions/{versionId}/field-mappings/{mappingId}` | Sửa mapping | Admin, Consultant |
| `DELETE` | `/api/admin/template-versions/{versionId}/field-mappings/{mappingId}` | Xóa mapping | Admin, Consultant |

### Template Preview — Admin/Consultant

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/admin/template-versions/{versionId}/preview` | Dry-run với data thật | Admin, Consultant |

### Accounting Books — Owner

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/v1/locations/{id}/accounting/books` | Tạo sổ kế toán | Owner |
| `GET` | `/api/v1/locations/{id}/accounting/books` | List sổ kế toán | Owner |
| `GET` | `/api/v1/locations/{id}/accounting/books/{bookId}` | Meta sổ kế toán | Owner |
| `GET` | `/api/v1/locations/{id}/accounting/books/{bookId}/data` | Data sổ (live) | Owner |
| `POST` | `/api/v1/locations/{id}/accounting/books/{bookId}/export` | Xuất sổ PDF/Excel | Owner |
| `PUT` | `/api/v1/locations/{id}/accounting/books/{bookId}/archive` | Archive sổ cũ | Owner |

### Tax Payments — Owner

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `POST` | `/api/v1/locations/{id}/tax-payments` | Ghi nhận nộp thuế | Owner |
| `GET` | `/api/v1/locations/{id}/tax-payments` | List thuế đã nộp | Owner |
| `DELETE` | `/api/v1/locations/{id}/tax-payments/{paymentId}` | Soft delete | Owner |

---

## 7. Error Codes

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
| `MAPPABLE_ENTITY_NOT_FOUND` | 404 | (v2) Entity không tồn tại trong Metadata Registry |
| `MAPPABLE_FIELD_NOT_FOUND` | 404 | (v2) Field không tồn tại trong Metadata Registry |
| `MAPPABLE_ENTITY_CODE_CONFLICT` | 400 | (v2) EntityCode đã tồn tại |
| `MAPPABLE_FIELD_CODE_CONFLICT` | 400 | (v2) FieldCode đã tồn tại trong entity này |
| `AGGREGATION_NOT_ALLOWED` | 400 | (v2) AggregationType không nằm trong AllowedAggregations của field |
| `CANNOT_MODIFY_ACTIVE_VERSION` | 400 | (v2) Không thể sửa/xóa mapping trên version đã active |
| `DUPLICATE_FIELD_CODE` | 400 | (v2) FieldCode đã tồn tại trong version này |
| `DUPLICATE_EXPORT_COLUMN` | 400 | (v2) ExportColumn đã được dùng bởi field khác trong version |
| `SOURCE_ENTITY_FIELD_REQUIRED` | 400 | (v2) SourceType=query yêu cầu SourceEntityId + SourceFieldId |
| `FORMULA_REQUIRED` | 400 | (v2) SourceType=formula yêu cầu FormulaExpression |
| `DEPENDS_ON_FIELD_NOT_FOUND` | 400 | (v2) DependsOn tham chiếu FieldCode không tồn tại trong version |
| `SOURCE_ENTITY_INACTIVE` | 400 | (v2) Entity đã bị deactivate, không dùng cho mapping mới |
| `SOURCE_FIELD_INACTIVE` | 400 | (v2) Field đã bị deactivate, không dùng cho mapping mới |
| `PREVIEW_LOCATION_REQUIRED` | 400 | (v2) Preview yêu cầu locationId |
