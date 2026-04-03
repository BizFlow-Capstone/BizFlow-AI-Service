# Tax Formula Engine

> **Module**: Report & Accounting — Formula Engine
> **Vị trí**: Middleware giữa Data Layer và Rendering Service
> Quay về [report-accounting-flow.md](../03-flows/report-accounting-flow.md) (index)
>
> **Mục đích**: Tính toán tất cả ô computed trong template TT152 — tổng hợp (SUM), tham chiếu ô khác, công thức thuế, bình quân gia quyền, lookup giá trị ngoài. Công thức lưu dạng structured JSON trong DB, không hardcode.
>
> **Đọc thêm (chi tiết toán tử và cách evaluate)**: [formula-operator-guide.md](formula-operator-guide.md)

---

## Mục lục

1. [Vị trí trong kiến trúc](#1-vị-trí-trong-kiến-trúc)
2. [Quyết định thiết kế](#2-quyết-định-thiết-kế)
3. [Entity Design](#3-entity-design)
   - [3.1 FormulaDefinitions](#31-formuladefinitions)
   - [3.2 FormulaResults (cache)](#32-formularesults-cache)
   - [3.3 TemplateFieldMappings (cập nhật)](#33-templatefieldmappings-cập-nhật)
4. [ExpressionJson Specification](#4-expressionjson-specification)
5. [Formula Catalog — TT152](#5-formula-catalog--tt152)
6. [Evaluation Engine](#6-evaluation-engine)
7. [Cache Strategy](#7-cache-strategy)
8. [C# Architecture](#8-c-architecture)
9. [Integration — Rendering Service](#9-integration--rendering-service)
10. [Business Rules](#10-business-rules)
11. [API Endpoints](#11-api-endpoints)
12. [Error Codes](#12-error-codes)

---

## 1. Vị trí trong kiến trúc

```
┌─────────────────────── RENDERING PIPELINE ───────────────────────────┐
│                                                                      │
│  ┌────────────┐                                                      │
│  │ Owner xem  │                                                      │
│  │ Book Data  │                                                      │
│  └─────┬──────┘                                                      │
│        │                                                             │
│        ▼                                                             │
│  ┌─────────────────┐    ┌──────────────────┐    ┌────────────────┐   │
│  │ Rendering       │───►│ FORMULA ENGINE   │───►│ FormulaResults │   │
│  │ Service         │    │                  │    │ (cache, SQL)   │   │
│  │                 │    │ Evaluate(context)│    └────────────────┘   │
│  │ 1. Query data   │    │                  │                         │
│  │ 2. Call Engine  │    │ Input:           │    ┌────────────────┐   │
│  │ 3. Compose rows │    │  - BookId        │───►│ Data Tables    │   │
│  │ 4. Return JSON  │    │  - PeriodId      │    │ Revenues       │   │
│  └─────────────────┘    │  - Context       │    │ Costs          │   │
│                         │                  │    │ GL Entries     │   │
│                         │ Output:          │    │ StockMovements │   │
│                         │  - Dict<Code,Val>│    │ IndustryRates  │   │
│                         └──────────────────┘    │ Periods        │   │
│                                │                └────────────────┘   │
│                                │                                     │
│                         ┌──────▼──────────┐                          │
│                         │ Formula         │                          │
│                         │ Definitions     │                          │
│                         │ (ExpressionJson)│                          │
│                         └─────────────────┘                          │
└──────────────────────────────────────────────────────────────────────┘
```

**Rendering Service** chỉ lo:

1. Query data rows (Revenues, Costs, GL...)
2. Gọi `FormulaEngine.EvaluateAll(bookId, context)` → nhận được `Dictionary<string, decimal>`
3. Gắn kết quả vào các dòng tổng hợp / dòng thuế

**Formula Engine** chỉ lo:

1. Đọc `FormulaDefinitions` (ExpressionJson)
2. Tính toán (query data nếu cần, tham chiếu ô khác, apply công thức)
3. Trả kết quả + cache vào `FormulaResults`

---

## 2. Quyết định thiết kế

### DD-FE-01: Formula Engine xử lý TẤT CẢ ô computed

Engine xử lý **5 loại tính toán**, không chỉ thuế:

| Loại | FormulaType | Ví dụ | Template |
|------|-------------|-------|----------|
| Gộp dữ liệu | `AGGREGATE` | SUM(doanh thu), SUM(chi phí) | S1a–S2e |
| Tham chiếu ô khác | `CELL_REF` | DT - CP = chênh lệch | S2c, S2e |
| Công thức thuế | `TAX_RATE` | DT × VAT rate | S2a, S2b, S2c |
| Bình quân gia quyền | `WEIGHTED_AVG` | (tồn + nhập) / (SL tồn + SL nhập) | S2d |
| Tra cứu bên ngoài | `EXTERNAL_LOOKUP` | OpeningCashBalance | S2e |

**Lý do**: Single responsibility cho computation. Rendering Service không cần biết logic tính — chỉ cần gọi `Evaluate()` và nhận kết quả.

### DD-FE-02: Structured JSON, không raw SQL

Công thức lưu dạng **JSON AST** (cây biểu thức), **KHÔNG phải** raw SQL hay stored procedure.

| | Raw SQL / Procedure | Structured JSON |
|---|---|---|
| **Bảo mật** | ❌ SQL injection khi admin sửa | ✅ Chỉ cho phép các node hợp lệ |
| **Testable** | ❌ Phải chạy DB để test | ✅ Unit test với mock data |
| **Portable** | ❌ Vendor lock (MySQL syntax) | ✅ Engine parse JSON → generate query |
| **Version control** | ❌ Procedure trong DB, ngoài Git | ✅ JSON = data, seed/migrate được |
| **Validation** | ❌ Chỉ biết sai khi chạy | ✅ Validate schema trước khi lưu |

### DD-FE-03: Cache kết quả trong SQL

Kết quả tính toán lưu trong `FormulaResults` (table SQL thường) — **không phải NoSQL**.

```
Mỗi row = 1 kết quả:
┌────────┬───────────┬───────────┬──────────────┬─────────────┐
│ BookId │ FormulaId │ ProductId │ BusinessType │ ResultValue │
├────────┼───────────┼───────────┼──────────────┼─────────────┤
│ 1      │ 3 (DT)    │ ''        │ 'bt-retail'  │ 500,000,000 │
│ 1      │ 4 (VAT)   │ ''        │ 'bt-retail'  │ 5,000,000   │
│ 1      │ 12 (W.Avg)│ 'prod-01' │ ''           │ 85,500      │
└────────┴───────────┴───────────┴──────────────┴─────────────┘
Thêm công thức mới → INSERT row, không ALTER TABLE.
```

**Invalidation**: Khi data gốc thay đổi (Revenue/Cost/GL/SM mới, sửa, reversal) → đánh dấu `IsStale = TRUE` cho các FormulaResults liên quan → lần view tiếp theo sẽ tính lại.

### DD-FE-04: CalculationOrder — đảm bảo dependency

Công thức có **dependency chain**: phải tính `total_revenue` trước rồi mới tính `vat = total_revenue × rate`. `CalculationOrder` (từ ý tưởng ban đầu) đặt trong `TemplateFieldMappings` — vì cùng 1 formula có thể ở order khác nhau tùy template.

Engine validate: không cho phép formula ở order N tham chiếu formula ở order > N.

---

## 3. Entity Design

### 3.1 FormulaDefinitions

> **Tương ứng**: `FomulatiresTax` trong ý tưởng ban đầu — giữ nguyên tinh thần Code/Name/Description/DataType, đổi `fomulation` text → `ExpressionJson` structured, bỏ `caculation_order` (chuyển sang TemplateFieldMappings).

```sql
-- =============================================
-- FORMULA DEFINITIONS TABLE
-- Pool công thức tính toán, reusable across templates
-- =============================================
CREATE TABLE FormulaDefinitions (
    FormulaId BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- ═══ IDENTITY ═══
    Code VARCHAR(50) NOT NULL
        COMMENT 'Mã công thức: S2A_QUARTERLY_TOTAL, S2C_PROFIT, S2D_WEIGHTED_AVG...',
    Name VARCHAR(255) NOT NULL
        COMMENT 'Tên: "Tổng doanh thu quý", "Chênh lệch DT-CP", "Đơn giá xuất kho BQ"',
    Description TEXT DEFAULT NULL
        COMMENT 'Giải thích công thức và cách áp dụng',
    
    -- ═══ TYPE ═══
    FormulaType ENUM('AGGREGATE', 'CELL_REF', 'TAX_RATE', 'WEIGHTED_AVG', 'EXTERNAL_LOOKUP') NOT NULL
        COMMENT 'Loại công thức — quyết định cách engine evaluate',
    
    -- ═══ EXPRESSION (structured JSON AST) ═══
    ExpressionJson JSON NOT NULL
        COMMENT 'Cây biểu thức JSON — xem Section 4 cho spec chi tiết',
    
    -- ═══ RESULT ═══
    ResultDataType ENUM('decimal', 'integer') NOT NULL DEFAULT 'decimal'
        COMMENT 'Kiểu dữ liệu kết quả',
    RoundingMode VARCHAR(20) DEFAULT NULL
        COMMENT 'floor | ceil | round_half_up | null = không làm tròn',
    RoundingPrecision TINYINT DEFAULT 0
        COMMENT 'Số chữ số thập phân (0 = làm tròn đến đơn vị)',
    
    -- ═══ STATUS ═══
    IsActive BOOLEAN NOT NULL DEFAULT TRUE,
    
    -- ═══ AUDIT ═══
    CreatedByUserId CHAR(36) DEFAULT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UpdatedAt DATETIME DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,
    
    UNIQUE INDEX idx_fd_code (Code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**C# Entity:**

```csharp
public class FormulaDefinition
{
    public long FormulaId { get; set; }
    
    public string Code { get; set; } = null!;
    public string Name { get; set; } = null!;
    public string? Description { get; set; }
    
    public FormulaType FormulaType { get; set; }
    public string ExpressionJson { get; set; } = null!;  // JSON string
    
    public ResultDataType ResultDataType { get; set; }
    public string? RoundingMode { get; set; }
    public int RoundingPrecision { get; set; }
    
    public bool IsActive { get; set; }
    public Guid? CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    public DateTime? UpdatedAt { get; set; }
}

public enum FormulaType
{
    AGGREGATE,        // SUM, COUNT, AVG over data rows
    CELL_REF,         // Reference other formula results
    TAX_RATE,         // Multiply by tax rate from IndustryTaxRates
    WEIGHTED_AVG,     // Bình quân gia quyền
    EXTERNAL_LOOKUP   // Fetch value from another table
}

public enum ResultDataType
{
    Decimal,
    Integer
}
```

### 3.2 FormulaResults (cache)

> **Tương ứng**: Bảng `tax` trong ý tưởng ban đầu — nhưng **dọc** (1 row = 1 kết quả) thay vì **ngang** (1 row = tất cả). Vẫn là SQL thuần, không phải NoSQL.

```sql
-- =============================================
-- FORMULA RESULTS TABLE (cache computation results)
-- Mỗi row = 1 kết quả của 1 công thức cho 1 book + context
-- =============================================
CREATE TABLE FormulaResults (
    ResultId BIGINT AUTO_INCREMENT PRIMARY KEY,
    
    -- ═══ KEYS ═══
    BookId BIGINT NOT NULL
        COMMENT 'FK → AccountingBooks — sổ nào',
    FormulaId BIGINT NOT NULL
        COMMENT 'FK → FormulaDefinitions — công thức nào',
    
    -- ═══ CONTEXT (scope cho kết quả) ═══
    -- Dùng '' (empty string) thay vì NULL để UNIQUE INDEX hoạt động đúng
    ProductId CHAR(36) NOT NULL DEFAULT ''
        COMMENT 'Scope theo sản phẩm (S2d). Empty = không scope',
    BusinessTypeId CHAR(36) NOT NULL DEFAULT ''
        COMMENT 'Scope theo ngành (S2a/S2b). Empty = không scope',
    SectionCode VARCHAR(50) NOT NULL DEFAULT ''
        COMMENT 'Scope theo phần: cash | bank (S2e), revenue | cost (S2c). Empty = không scope',
    
    -- ═══ RESULT ═══
    ResultValue DECIMAL(18,4) NOT NULL
        COMMENT 'Giá trị kết quả sau tính toán',
    
    -- ═══ CACHE MANAGEMENT ═══
    ComputedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        COMMENT 'Thời điểm tính gần nhất',
    IsStale BOOLEAN NOT NULL DEFAULT FALSE
        COMMENT 'TRUE = data gốc đã thay đổi, cần tính lại',
    
    -- ═══ FKs & INDEXES ═══
    CONSTRAINT fk_fr_book FOREIGN KEY (BookId) 
        REFERENCES AccountingBooks(BookId),
    CONSTRAINT fk_fr_formula FOREIGN KEY (FormulaId) 
        REFERENCES FormulaDefinitions(FormulaId),
    
    UNIQUE INDEX idx_fr_composite (BookId, FormulaId, ProductId, BusinessTypeId, SectionCode),
    INDEX idx_fr_stale (BookId, IsStale)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**C# Entity:**

```csharp
public class FormulaResult
{
    public long ResultId { get; set; }
    
    public long BookId { get; set; }
    public long FormulaId { get; set; }
    
    // Context scope
    public string ProductId { get; set; } = "";
    public string BusinessTypeId { get; set; } = "";
    public string SectionCode { get; set; } = "";
    
    // Result
    public decimal ResultValue { get; set; }
    
    // Cache
    public DateTime ComputedAt { get; set; }
    public bool IsStale { get; set; }
    
    // Navigation
    public virtual AccountingBook Book { get; set; } = null!;
    public virtual FormulaDefinition Formula { get; set; } = null!;
}
```

**So sánh bảng `tax` ban đầu → `FormulaResults`:**

| `tax` (ban đầu) | `FormulaResults` (hiện tại) | Lý do đổi |
|---|---|---|
| `doanh_thu` (fixed column) | Row: FormulaId → `QUARTERLY_TOTAL`, ResultValue = 500M | Không ALTER TABLE khi thêm chỉ tiêu |
| `thue_gtgt` (fixed column) | Row: FormulaId → `VAT`, ResultValue = 5M | Dynamic — INSERT thêm formula mới |
| `don_gia_xuat_kho` (1 giá trị) | N rows: FormulaId → `WEIGHTED_AVG`, ProductId = 'sp-01' / 'sp-02'... | 1 giá trị per sản phẩm |
| `period_tax` FK | BookId → Book.PeriodId → `AccountingPeriods` | Không duplicate table Period |

### 3.3 TemplateFieldMappings (cập nhật)

Thêm `FormulaId` FK và `CalculationOrder` vào table hiện có:

```sql
-- ═══ MIGRATION: Thêm FormulaId + CalculationOrder ═══
ALTER TABLE TemplateFieldMappings
    ADD COLUMN FormulaId BIGINT DEFAULT NULL
        COMMENT 'FK → FormulaDefinitions. Set khi SourceType = formula',
    ADD COLUMN CalculationOrder INT DEFAULT NULL
        COMMENT 'Thứ tự tính. Formula ở order thấp phải tính trước',
    ADD CONSTRAINT fk_tfm_formula FOREIGN KEY (FormulaId)
        REFERENCES FormulaDefinitions(FormulaId),
    ADD INDEX idx_tfm_formula (FormulaId);
```

**Quan hệ:**

```
TemplateFieldMappings (1 ô trong sổ)
├── SourceType = 'query'   → SourceEntityId + SourceFieldId (data row)
├── SourceType = 'formula' → FormulaId FK (computed value)
├── SourceType = 'auto'    → Auto-increment (STT)
└── SourceType = 'static'  → Fixed label/value
```

**Ví dụ FieldMappings cho S2a (có cả query + formula):**

```sql
-- Data rows (SourceType = 'query'):
INSERT INTO TemplateFieldMappings 
(TemplateVersionId, FieldCode, FieldLabel, FieldType, SourceType, SourceEntityId, SourceFieldId, ExportColumn, SortOrder) VALUES
(2, 'so_hieu',    'Số hiệu (A)',   'text',    'query', 4, 3, 'A', 1),  -- orders.OrderCode
(2, 'ngay_thang', 'Ngày tháng (B)','date',    'query', 1, 2, 'B', 2),  -- revenues.RevenueDate
(2, 'dien_giai',  'Diễn giải (C)', 'text',    'query', 1, 3, 'C', 3),  -- revenues.Description
(2, 'so_tien',    'Số tiền (1)',   'decimal', 'query', 1, 1, 'D', 4);  -- revenues.Amount

-- Computed rows (SourceType = 'formula'):
INSERT INTO TemplateFieldMappings 
(TemplateVersionId, FieldCode, FieldLabel, FieldType, SourceType, FormulaId, CalculationOrder, ExportColumn, SortOrder) VALUES
(2, 'cong_quy',    'Cộng quý',             'decimal', 'formula', 1, 1, 'D', 10), -- FormulaId→S2A_QUARTERLY_TOTAL
(2, 'thue_gtgt',   'Thuế GTGT phải nộp',   'decimal', 'formula', 2, 2, 'D', 11), -- FormulaId→S2A_VAT
(2, 'thue_tncn',   'Thuế TNCN phải nộp',   'decimal', 'formula', 3, 3, 'D', 12); -- FormulaId→S2A_PIT
```

---

## 4. ExpressionJson Specification

### Node Types

Mỗi `ExpressionJson` là một **cây biểu thức** (AST). Các loại node:

#### 4.1 Literal — Giá trị cố định

```json
{ "literal": 500000000 }
```

Dùng cho: ngưỡng miễn thuế 500 triệu, giá trị mặc định 0, v.v.

#### 4.2 Ref — Tham chiếu kết quả formula khác

```json
{ "ref": "S2A_QUARTERLY_TOTAL" }
```

Tham chiếu bằng `FormulaDefinitions.Code`. Kết quả phải đã được tính trước (CalculationOrder thấp hơn).

#### 4.3 Aggregate — Gộp dữ liệu từ data table

```json
{
  "aggregate": "SUM",
  "source": "revenues",
  "field": "Amount",
  "scope": "book",
  "filter": {
    "RevenueType": ["sale", "manual"]
  }
}
```

| Property | Type | Mô tả |
|----------|------|-------|
| `aggregate` | `SUM` \| `COUNT` \| `AVG` | Phép gộp |
| `source` | string | Entity code (từ MappableEntities): `revenues`, `costs`, `gl_entries`, `stock_movements` |
| `field` | string | Field code (từ MappableFields): `Amount`, `DebitAmount`, `QuantityDelta`... |
| `scope` | `book` \| `location` | `book` = filter theo Book.BusinessTypeId. `location` = toàn location |
| `filter` | object? | Điều kiện bổ sung. Key = field, Value = giá trị hoặc array giá trị |
| `periodFilter` | `current` \| `before` \| `none` | `current` = trong kỳ (default). `before` = trước kỳ (tồn đầu kỳ). `none` = tất cả |
| `sign` | `positive` \| `negative` \| `all` | Lọc theo dấu: `positive` (nhập), `negative` (xuất). Default = `all` |

#### 4.4 Lookup — Lấy giá trị từ table khác

```json
{
  "lookup": {
    "entity": "IndustryTaxRates",
    "field": "TaxRate",
    "filter": { "TaxType": "VAT" }
  }
}
```

```json
{
  "lookup": {
    "entity": "AccountingPeriods",
    "field": "OpeningCashBalance"
  }
}
```

Engine tự biết cần filter theo `BusinessLocationId` / `PeriodId` / `BusinessTypeId` từ context.

#### 4.5 Op — Phép toán 2 ngôi

```json
{
  "op": "MULTIPLY",
  "left": { "ref": "S2A_QUARTERLY_TOTAL" },
  "right": { "lookup": { "entity": "IndustryTaxRates", "field": "TaxRate", "filter": { "TaxType": "VAT" } } }
}
```

| Op | Ý nghĩa |
|---|---|
| `ADD` | Cộng |
| `SUBTRACT` | Trừ |
| `MULTIPLY` | Nhân |
| `DIVIDE` | Chia (chia 0 → trả 0, không throw) |

#### 4.6 Fn — Hàm

```json
{
  "fn": "MAX",
  "args": [
    { "literal": 0 },
    { "op": "SUBTRACT", "left": { "ref": "TOTAL_REVENUE_ALL" }, "right": { "literal": 500000000 } }
  ]
}
```

| Fn | Ý nghĩa | Args |
|---|---|---|
| `MAX` | Lớn nhất | 2+ |
| `MIN` | Nhỏ nhất | 2+ |
| `ABS` | Trị tuyệt đối | 1 |
| `ROUND` | Làm tròn | 2 (value, precision) |

#### 4.7 Context — Giá trị runtime

```json
{ "context": "period_start" }
```

| Context key | Giá trị | Ghi chú |
|---|---|---|
| `period_start` | DateTime | Ngày bắt đầu kỳ |
| `period_end` | DateTime | Ngày kết thúc kỳ |
| `business_type_id` | string | Ngành nghề của book hiện tại |
| `product_id` | string | Sản phẩm (S2d scope) |

### Ví dụ Full ExpressionJson

**Thuế GTGT S2a** — `total × vat_rate`:

```json
{
  "op": "MULTIPLY",
  "left": { "ref": "S2A_QUARTERLY_TOTAL" },
  "right": {
    "lookup": {
      "entity": "IndustryTaxRates",
      "field": "TaxRate",
      "filter": { "TaxType": "VAT" }
    }
  }
}
```

**Thuế TNCN S2a** — `MAX(0, DT_total - 500M) × pit_rate`:

```json
{
  "op": "MULTIPLY",
  "left": {
    "fn": "MAX",
    "args": [
      { "literal": 0 },
      {
        "op": "SUBTRACT",
        "left": { "ref": "S2A_TOTAL_REVENUE_ALL" },
        "right": { "literal": 500000000 }
      }
    ]
  },
  "right": {
    "lookup": {
      "entity": "IndustryTaxRates",
      "field": "TaxRate",
      "filter": { "TaxType": "PIT_M1" }
    }
  }
}
```

**Bình quân gia quyền S2d** — `(tồn_value + nhập_value) / (tồn_qty + nhập_qty)`:

```json
{
  "op": "DIVIDE",
  "left": {
    "op": "ADD",
    "left": { "ref": "S2D_OPENING_VALUE" },
    "right": { "ref": "S2D_IMPORT_VALUE" }
  },
  "right": {
    "op": "ADD",
    "left": { "ref": "S2D_OPENING_QTY" },
    "right": { "ref": "S2D_IMPORT_QTY" }
  }
}
```

---

## 5. Formula Catalog — TT152

### Toàn bộ công thức cần thiết cho 6 template

#### S1a — Sổ chi tiết bán hàng (2 formulas)

| # | Code | Type | Mô tả | CalculationOrder |
|---|------|------|-------|:----------------:|
| 1 | `S1A_MONTHLY_TOTAL` | AGGREGATE | SUM doanh thu theo tháng | 1 |
| 2 | `S1A_QUARTERLY_TOTAL` | AGGREGATE | SUM doanh thu cả quý | 2 |

```sql
-- S1A_QUARTERLY_TOTAL
INSERT INTO FormulaDefinitions (Code, Name, FormulaType, ExpressionJson, ResultDataType, RoundingPrecision) VALUES
('S1A_QUARTERLY_TOTAL', 'Cộng quý — S1a', 'AGGREGATE',
 '{"aggregate":"SUM","source":"revenues","field":"Amount","scope":"location","filter":{"RevenueType":["sale","manual"]}}',
 'decimal', 0);
```

#### S2a — Sổ doanh thu Cách 1 (4 formulas)

| # | Code | Type | Mô tả | Order |
|---|------|------|-------|:-----:|
| 3 | `S2A_QUARTERLY_TOTAL` | AGGREGATE | SUM DT theo ngành (scope: book) | 1 |
| 4 | `S2A_TOTAL_REVENUE_ALL` | AGGREGATE | SUM DT toàn location (scope: location) — dùng cho PIT threshold | 2 |
| 5 | `S2A_VAT` | TAX_RATE | Tổng DT ngành × VAT rate | 3 |
| 6 | `S2A_PIT` | TAX_RATE | MAX(0, DT toàn bộ - 500M) × PIT rate | 4 |

```sql
INSERT INTO FormulaDefinitions (Code, Name, FormulaType, ExpressionJson, ResultDataType, RoundingPrecision) VALUES
('S2A_QUARTERLY_TOTAL', 'Cộng quý DT — S2a', 'AGGREGATE',
 '{"aggregate":"SUM","source":"revenues","field":"Amount","scope":"book","filter":{"RevenueType":["sale","manual"]}}',
 'decimal', 0),

('S2A_TOTAL_REVENUE_ALL', 'Tổng DT toàn location — S2a', 'AGGREGATE',
 '{"aggregate":"SUM","source":"revenues","field":"Amount","scope":"location","filter":{"RevenueType":["sale","manual"]}}',
 'decimal', 0),

('S2A_VAT', 'Thuế GTGT — S2a', 'TAX_RATE',
 '{"op":"MULTIPLY","left":{"ref":"S2A_QUARTERLY_TOTAL"},"right":{"lookup":{"entity":"IndustryTaxRates","field":"TaxRate","filter":{"TaxType":"VAT"}}}}',
 'decimal', 0),

('S2A_PIT', 'Thuế TNCN — S2a', 'TAX_RATE',
 '{"op":"MULTIPLY","left":{"fn":"MAX","args":[{"literal":0},{"op":"SUBTRACT","left":{"ref":"S2A_TOTAL_REVENUE_ALL"},"right":{"literal":500000000}}]},"right":{"lookup":{"entity":"IndustryTaxRates","field":"TaxRate","filter":{"TaxType":"PIT_M1"}}}}',
 'decimal', 0);
```

#### S2b — Sổ doanh thu Cách 2 (2 formulas)

| # | Code | Type | Mô tả | Order |
|---|------|------|-------|:-----:|
| 7 | `S2B_QUARTERLY_TOTAL` | AGGREGATE | SUM DT theo ngành | 1 |
| 8 | `S2B_VAT` | TAX_RATE | DT ngành × VAT rate (không có PIT — tính ở S2c) | 2 |

Cùng structure với S2A_QUARTERLY_TOTAL và S2A_VAT. Có thể **reuse** cùng FormulaId nếu ExpressionJson giống nhau, hoặc tạo riêng để rõ ràng.

#### S2c — Sổ DT, CP (4 formulas)

| # | Code | Type | Mô tả | Order |
|---|------|------|-------|:-----:|
| 9 | `S2C_TOTAL_REVENUE` | AGGREGATE | SUM DT toàn location | 1 |
| 10 | `S2C_TOTAL_COST` | AGGREGATE | SUM CP toàn location | 2 |
| 11 | `S2C_PROFIT` | CELL_REF | DT - CP = chênh lệch | 3 |
| 12 | `S2C_PIT` | TAX_RATE | Chênh lệch × PIT rate (Cách 2) | 4 |

```sql
INSERT INTO FormulaDefinitions (Code, Name, FormulaType, ExpressionJson, ResultDataType, RoundingPrecision) VALUES
('S2C_TOTAL_REVENUE', 'Tổng doanh thu — S2c', 'AGGREGATE',
 '{"aggregate":"SUM","source":"revenues","field":"Amount","scope":"location","filter":{"RevenueType":["sale","manual"]}}',
 'decimal', 0),

('S2C_TOTAL_COST', 'Tổng chi phí hợp lý — S2c', 'AGGREGATE',
 '{"aggregate":"SUM","source":"costs","field":"Amount","scope":"location"}',
 'decimal', 0),

('S2C_PROFIT', 'Chênh lệch DT - CP — S2c', 'CELL_REF',
 '{"op":"SUBTRACT","left":{"ref":"S2C_TOTAL_REVENUE"},"right":{"ref":"S2C_TOTAL_COST"}}',
 'decimal', 0),

('S2C_PIT', 'Thuế TNCN Cách 2 — S2c', 'TAX_RATE',
 '{"op":"MULTIPLY","left":{"fn":"MAX","args":[{"literal":0},{"ref":"S2C_PROFIT"}]},"right":{"lookup":{"entity":"IndustryTaxRates","field":"TaxRate","filter":{"TaxType":"PIT_M1"}}}}',
 'decimal', 0);
```

#### S2d — Sổ kho XNT (8 formulas, per product)

| # | Code | Type | Mô tả | Order |
|---|------|------|-------|:-----:|
| 13 | `S2D_OPENING_QTY` | AGGREGATE | SL tồn đầu kỳ (SUM delta trước kỳ) | 1 |
| 14 | `S2D_OPENING_VALUE` | AGGREGATE | Giá trị tồn đầu kỳ | 2 |
| 15 | `S2D_IMPORT_QTY` | AGGREGATE | SUM SL nhập trong kỳ | 3 |
| 16 | `S2D_IMPORT_VALUE` | AGGREGATE | SUM giá trị nhập trong kỳ | 4 |
| 17 | `S2D_WEIGHTED_AVG` | WEIGHTED_AVG | Đơn giá xuất BQ gia quyền | 5 |
| 18 | `S2D_EXPORT_QTY` | AGGREGATE | SUM SL xuất trong kỳ | 6 |
| 19 | `S2D_EXPORT_VALUE` | CELL_REF | SL xuất × đơn giá BQ | 7 |
| 20 | `S2D_CLOSING_QTY` | CELL_REF | Tồn ĐK + Nhập - Xuất | 8 |
| 21 | `S2D_CLOSING_VALUE` | CELL_REF | SL tồn CK × đơn giá BQ | 9 |

```sql
INSERT INTO FormulaDefinitions (Code, Name, FormulaType, ExpressionJson, ResultDataType, RoundingPrecision) VALUES
('S2D_OPENING_QTY', 'SL tồn đầu kỳ — S2d', 'AGGREGATE',
 '{"aggregate":"SUM","source":"stock_movements","field":"QuantityDelta","scope":"book","periodFilter":"before"}',
 'decimal', 2),

('S2D_OPENING_VALUE', 'Giá trị tồn đầu kỳ — S2d', 'AGGREGATE',
 '{"aggregate":"SUM","source":"stock_movements","field":"TotalValue","scope":"book","periodFilter":"before","sign":"positive"}',
 'decimal', 0),

('S2D_IMPORT_QTY', 'SL nhập trong kỳ — S2d', 'AGGREGATE',
 '{"aggregate":"SUM","source":"stock_movements","field":"QuantityDelta","scope":"book","periodFilter":"current","sign":"positive"}',
 'decimal', 2),

('S2D_IMPORT_VALUE', 'Giá trị nhập trong kỳ — S2d', 'AGGREGATE',
 '{"aggregate":"SUM","source":"stock_movements","field":"TotalValue","scope":"book","periodFilter":"current","sign":"positive"}',
 'decimal', 0),

('S2D_WEIGHTED_AVG', 'Đơn giá xuất kho BQ gia quyền — S2d', 'WEIGHTED_AVG',
 '{"op":"DIVIDE","left":{"op":"ADD","left":{"ref":"S2D_OPENING_VALUE"},"right":{"ref":"S2D_IMPORT_VALUE"}},"right":{"op":"ADD","left":{"ref":"S2D_OPENING_QTY"},"right":{"ref":"S2D_IMPORT_QTY"}}}',
 'decimal', 0),

('S2D_EXPORT_QTY', 'SL xuất trong kỳ — S2d', 'AGGREGATE',
 '{"fn":"ABS","args":[{"aggregate":"SUM","source":"stock_movements","field":"QuantityDelta","scope":"book","periodFilter":"current","sign":"negative"}]}',
 'decimal', 2),

('S2D_EXPORT_VALUE', 'Giá trị xuất trong kỳ — S2d', 'CELL_REF',
 '{"op":"MULTIPLY","left":{"ref":"S2D_EXPORT_QTY"},"right":{"ref":"S2D_WEIGHTED_AVG"}}',
 'decimal', 0),

('S2D_CLOSING_QTY', 'SL tồn cuối kỳ — S2d', 'CELL_REF',
 '{"op":"SUBTRACT","left":{"op":"ADD","left":{"ref":"S2D_OPENING_QTY"},"right":{"ref":"S2D_IMPORT_QTY"}},"right":{"ref":"S2D_EXPORT_QTY"}}',
 'decimal', 2),

('S2D_CLOSING_VALUE', 'Giá trị tồn cuối kỳ — S2d', 'CELL_REF',
 '{"op":"MULTIPLY","left":{"ref":"S2D_CLOSING_QTY"},"right":{"ref":"S2D_WEIGHTED_AVG"}}',
 'decimal', 0);
```

> **Lưu ý S2d**: Tất cả formulas S2d evaluate **per Product** — engine chạy vòng lặp cho mỗi sản phẩm, truyền `context.ProductId`, lưu kết quả với `FormulaResults.ProductId != ''`.

#### S2e — Sổ chi tiết tiền (8 formulas, per section)

| # | Code | Type | Mô tả | Order |
|---|------|------|-------|:-----:|
| 22 | `S2E_CASH_OPENING` | EXTERNAL_LOOKUP | Tiền mặt đầu kỳ | 1 |
| 23 | `S2E_CASH_IN` | AGGREGATE | SUM GL Debit WHERE cash | 2 |
| 24 | `S2E_CASH_OUT` | AGGREGATE | SUM GL Credit WHERE cash | 3 |
| 25 | `S2E_CASH_CLOSING` | CELL_REF | Opening + In - Out | 4 |
| 26 | `S2E_BANK_OPENING` | EXTERNAL_LOOKUP | Tiền gửi đầu kỳ | 5 |
| 27 | `S2E_BANK_IN` | AGGREGATE | SUM GL Debit WHERE bank | 6 |
| 28 | `S2E_BANK_OUT` | AGGREGATE | SUM GL Credit WHERE bank | 7 |
| 29 | `S2E_BANK_CLOSING` | CELL_REF | Opening + In - Out | 8 |

```sql
INSERT INTO FormulaDefinitions (Code, Name, FormulaType, ExpressionJson, ResultDataType, RoundingPrecision) VALUES
('S2E_CASH_OPENING', 'Tiền mặt đầu kỳ — S2e', 'EXTERNAL_LOOKUP',
 '{"lookup":{"entity":"AccountingPeriods","field":"OpeningCashBalance"}}',
 'decimal', 0),

('S2E_CASH_IN', 'Tổng thu tiền mặt — S2e', 'AGGREGATE',
 '{"aggregate":"SUM","source":"gl_entries","field":"DebitAmount","scope":"location","filter":{"MoneyChannel":"cash"}}',
 'decimal', 0),

('S2E_CASH_OUT', 'Tổng chi tiền mặt — S2e', 'AGGREGATE',
 '{"aggregate":"SUM","source":"gl_entries","field":"CreditAmount","scope":"location","filter":{"MoneyChannel":"cash"}}',
 'decimal', 0),

('S2E_CASH_CLOSING', 'Tiền mặt tồn cuối kỳ — S2e', 'CELL_REF',
 '{"op":"SUBTRACT","left":{"op":"ADD","left":{"ref":"S2E_CASH_OPENING"},"right":{"ref":"S2E_CASH_IN"}},"right":{"ref":"S2E_CASH_OUT"}}',
 'decimal', 0),

('S2E_BANK_OPENING', 'Tiền gửi đầu kỳ — S2e', 'EXTERNAL_LOOKUP',
 '{"lookup":{"entity":"AccountingPeriods","field":"OpeningBankBalance"}}',
 'decimal', 0),

('S2E_BANK_IN', 'Tổng gửi vào — S2e', 'AGGREGATE',
 '{"aggregate":"SUM","source":"gl_entries","field":"DebitAmount","scope":"location","filter":{"MoneyChannel":"bank"}}',
 'decimal', 0),

('S2E_BANK_OUT', 'Tổng rút ra — S2e', 'AGGREGATE',
 '{"aggregate":"SUM","source":"gl_entries","field":"CreditAmount","scope":"location","filter":{"MoneyChannel":"bank"}}',
 'decimal', 0),

('S2E_BANK_CLOSING', 'Dư tiền gửi cuối kỳ — S2e', 'CELL_REF',
 '{"op":"SUBTRACT","left":{"op":"ADD","left":{"ref":"S2E_BANK_OPENING"},"right":{"ref":"S2E_BANK_IN"}},"right":{"ref":"S2E_BANK_OUT"}}',
 'decimal', 0);
```

### Tổng hợp Formula Catalog

```
Tổng: 29 formulas
├── S1a: 2  (AGGREGATE × 2)
├── S2a: 4  (AGGREGATE × 2, TAX_RATE × 2)
├── S2b: 2  (AGGREGATE × 1, TAX_RATE × 1)
├── S2c: 4  (AGGREGATE × 2, CELL_REF × 1, TAX_RATE × 1)
├── S2d: 9  (AGGREGATE × 4, WEIGHTED_AVG × 1, CELL_REF × 4) — per product
└── S2e: 8  (EXTERNAL_LOOKUP × 2, AGGREGATE × 4, CELL_REF × 2) — per section
```

---

## 6. Evaluation Engine

### Algorithm

```
EvaluateAllFormulas(bookId, context):
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  1. Load Book → lấy TemplateVersionId, PeriodId, BusinessTypeId     │
│                                                                     │
│  2. Load all TemplateFieldMappings WHERE SourceType = 'formula'     │
│     ORDER BY CalculationOrder ASC                                    │
│                                                                     │
│  3. Load FormulaDefinitions for each FormulaId                      │
│                                                                     │
│  4. Khởi tạo resolvedValues = Dictionary<string, decimal>           │
│                                                                     │
│  5. FOR EACH formula (theo CalculationOrder):                       │
│     │                                                               │
│     ├── 5a. Check cache: FormulaResults                             │
│     │   WHERE BookId = @bookId AND FormulaId = @fId                 │
│     │     AND ProductId = @ctx.ProductId                            │
│     │     AND IsStale = FALSE                                       │
│     │                                                               │
│     ├── 5b. HIT (cache valid) → result = cached value              │
│     │                                                               │
│     ├── 5c. MISS (stale / không có) → Evaluate ExpressionJson:     │
│     │   │                                                           │
│     │   ├── Node = literal → return value                          │
│     │   ├── Node = ref     → return resolvedValues[refCode]        │
│     │   ├── Node = aggregate → BUILD + EXECUTE SQL query           │
│     │   ├── Node = lookup  → QUERY lookup table                    │
│     │   ├── Node = op      → evaluate(left) OP evaluate(right)     │
│     │   └── Node = fn      → evaluate args, apply function         │
│     │                                                               │
│     ├── 5d. Apply rounding (nếu có)                                │
│     │                                                               │
│     ├── 5e. UPSERT FormulaResults (cache result)                   │
│     │                                                               │
│     └── 5f. resolvedValues[formula.Code] = result                  │
│                                                                     │
│  6. RETURN resolvedValues                                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Aggregate SQL Generation

Khi engine gặp node `aggregate`, nó **build SQL dynamically** (prepared statement, parameterized — không injection):

```csharp
// Ví dụ: {"aggregate":"SUM","source":"revenues","field":"Amount","scope":"book"}

// Engine generates:
var sql = @"
    SELECT COALESCE(SUM(r.Amount), 0)
    FROM Revenues r
    WHERE r.BusinessLocationId = @locationId
      AND r.DeletedAt IS NULL
      AND r.RevenueDate BETWEEN @startDate AND @endDate";

// scope = "book" → thêm filter BusinessType
if (scope == "book" && !string.IsNullOrEmpty(context.BusinessTypeId))
{
    sql += " AND EXISTS (SELECT 1 FROM Orders o JOIN OrderDetails od ON ... " +
           "WHERE o.OrderId = r.OrderId AND od.BusinessTypeId = @businessTypeId)";
}

// Luôn dùng parameterized query — KHÔNG string concat giá trị
```

### Sequence Diagram — Xem Book Data

```
Owner              RenderingService           FormulaEngine          DB
  │                      │                         │                  │
  │  GET /books/1/data   │                         │                  │
  │─────────────────────►│                         │                  │
  │                      │                         │                  │
  │                      │  1. Query data rows     │                  │
  │                      │  (Revenues, GL...)      │                  │
  │                      │────────────────────────────────────────────►│
  │                      │◄────────────────────────────────────────────│
  │                      │  rows[]                 │                  │
  │                      │                         │                  │
  │                      │  2. EvaluateAll(bookId)  │                  │
  │                      │────────────────────────►│                  │
  │                      │                         │  Check cache     │
  │                      │                         │─────────────────►│
  │                      │                         │  (IsStale=false) │
  │                      │                         │◄─────────────────│
  │                      │                         │  cached results  │
  │                      │                         │                  │
  │                      │                         │  (hoặc nếu stale)│
  │                      │                         │  Evaluate JSON   │
  │                      │                         │  → query DB      │
  │                      │                         │─────────────────►│
  │                      │                         │◄─────────────────│
  │                      │                         │  UPSERT cache    │
  │                      │                         │─────────────────►│
  │                      │                         │                  │
  │                      │◄────────────────────────│                  │
  │                      │  Dict<code, value>      │                  │
  │                      │                         │                  │
  │                      │  3. Compose response    │                  │
  │                      │  (data rows + computed) │                  │
  │◄─────────────────────│                         │                  │
  │  JSON response       │                         │                  │
```

---

## 7. Cache Strategy

### Invalidation Events

| Event | Ảnh hưởng | Action |
|-------|----------|--------|
| Revenue created/reversed | S1a, S2a, S2b, S2c totals + tax | Mark stale WHERE BookId IN (affected books) |
| Cost created/reversed | S2c totals + profit + PIT | Mark stale WHERE FormulaId IN (cost-related) |
| GL entry created/reversed | S2e cash/bank totals | Mark stale WHERE FormulaId IN (GL-related) |
| StockMovement created | S2d all (qty, value, avg) | Mark stale WHERE FormulaId IN (SM-related) AND ProductId = @pid |
| Period opening balance changed | S2e opening + closing | Mark stale WHERE FormulaId IN (S2E_*_OPENING, S2E_*_CLOSING) |

### Implementation — Domain Events

```csharp
// Khi Revenue mới được tạo:
public class RevenueCreatedHandler : INotificationHandler<RevenueCreatedEvent>
{
    private readonly IFormulaResultRepository _cache;
    
    public async Task Handle(RevenueCreatedEvent e, CancellationToken ct)
    {
        // Tìm tất cả books cho location + period chứa revenue date
        var affectedBookIds = await _cache.FindAffectedBooks(
            e.BusinessLocationId, e.RevenueDate);
        
        // Mark stale
        await _cache.MarkStale(affectedBookIds, 
            formulaCodes: new[] { 
                "S1A_%", "S2A_%", "S2B_%", 
                "S2C_TOTAL_REVENUE", "S2C_PROFIT", "S2C_PIT" 
            });
    }
}
```

### Cache Flow

```
                 ┌──────────────────────────────┐
                 │  Data thay đổi               │
                 │  (Revenue/Cost/GL/SM event)  │
                 └──────────────┬───────────────┘
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │  InvalidationHandler         │
                 │  → UPDATE FormulaResults     │
                 │    SET IsStale = TRUE        │
                 │    WHERE BookId IN (...)     │
                 └──────────────┬───────────────┘
                                │
          (Lần tiếp theo Owner mở book)
                                │
                                ▼
                 ┌──────────────────────────────┐
                 │  FormulaEngine.EvaluateAll() │
                 │                              │
                 │  Stale? → Re-evaluate        │
                 │  Fresh? → Return cached      │
                 │                              │
                 │  → UPSERT FormulaResults     │
                 │    SET IsStale = FALSE,      │
                 │    ResultValue = @newValue,  │
                 │    ComputedAt = NOW()        │
                 └──────────────────────────────┘
```

---

## 8. C# Architecture

### Interfaces

```csharp
public interface IFormulaEngine
{
    /// Evaluate tất cả formulas cho 1 book, trả về Dict<Code, Value>
    Task<Dictionary<string, decimal>> EvaluateAllAsync(
        long bookId, FormulaContext context, CancellationToken ct = default);
    
    /// Evaluate 1 formula cụ thể
    Task<decimal> EvaluateAsync(
        long formulaId, FormulaContext context, CancellationToken ct = default);
    
    /// Invalidate cache khi data thay đổi
    Task InvalidateAsync(
        int businessLocationId, DateTime affectedDate, 
        string[] formulaCodePatterns, CancellationToken ct = default);
}

public class FormulaContext
{
    public long BookId { get; set; }
    public int BusinessLocationId { get; set; }
    public long PeriodId { get; set; }
    public DateTime PeriodStart { get; set; }
    public DateTime PeriodEnd { get; set; }
    
    // Scope (optional)
    public string? ProductId { get; set; }
    public string? BusinessTypeId { get; set; }
    public string? SectionCode { get; set; }
    
    // Pre-loaded (từ AccountingPeriods)
    public decimal OpeningCashBalance { get; set; }
    public decimal OpeningBankBalance { get; set; }
    
    // Internal — filled during evaluation
    internal Dictionary<string, decimal> ResolvedValues { get; } = new();
}
```

### Service structure

```
BizFlow.Application/
├── Interfaces/
│   └── IFormulaEngine.cs
│
BizFlow.Infrastructure/
├── Services/
│   └── FormulaEngine/
│       ├── FormulaEngine.cs            -- Main evaluator
│       ├── ExpressionEvaluator.cs      -- Recursive JSON AST walker
│       ├── AggregateQueryBuilder.cs    -- Build parameterized SQL from aggregate nodes
│       ├── LookupResolver.cs           -- Resolve EXTERNAL_LOOKUP nodes
│       └── FormulaResultCache.cs       -- UPSERT + invalidation logic
```

### ExpressionEvaluator — Core Logic

```csharp
public class ExpressionEvaluator
{
    public async Task<decimal> EvaluateNode(
        JsonElement node, FormulaContext ctx, CancellationToken ct)
    {
        if (node.TryGetProperty("literal", out var lit))
            return lit.GetDecimal();
        
        if (node.TryGetProperty("ref", out var refCode))
        {
            var code = refCode.GetString()!;
            if (!ctx.ResolvedValues.TryGetValue(code, out var val))
                throw new FormulaDependencyException(code);
            return val;
        }
        
        if (node.TryGetProperty("aggregate", out _))
            return await _aggregateBuilder.ExecuteAsync(node, ctx, ct);
        
        if (node.TryGetProperty("lookup", out _))
            return await _lookupResolver.ResolveAsync(node, ctx, ct);
        
        if (node.TryGetProperty("op", out var op))
        {
            var left = await EvaluateNode(node.GetProperty("left"), ctx, ct);
            var right = await EvaluateNode(node.GetProperty("right"), ctx, ct);
            return op.GetString() switch
            {
                "ADD"      => left + right,
                "SUBTRACT" => left - right,
                "MULTIPLY" => left * right,
                "DIVIDE"   => right == 0 ? 0 : left / right,
                _ => throw new InvalidFormulaException($"Unknown op: {op}")
            };
        }
        
        if (node.TryGetProperty("fn", out var fn))
        {
            var args = new List<decimal>();
            foreach (var arg in node.GetProperty("args").EnumerateArray())
                args.Add(await EvaluateNode(arg, ctx, ct));
            
            return fn.GetString() switch
            {
                "MAX"   => args.Max(),
                "MIN"   => args.Min(),
                "ABS"   => Math.Abs(args[0]),
                "ROUND" => Math.Round(args[0], (int)args[1]),
                _ => throw new InvalidFormulaException($"Unknown fn: {fn}")
            };
        }
        
        if (node.TryGetProperty("context", out var ctxKey))
        {
            return ctxKey.GetString() switch
            {
                "opening_cash" => ctx.OpeningCashBalance,
                "opening_bank" => ctx.OpeningBankBalance,
                _ => throw new InvalidFormulaException($"Unknown context: {ctxKey}")
            };
        }
        
        throw new InvalidFormulaException("Unknown node type");
    }
}
```

---

## 9. Integration — Rendering Service

### Rendering Service gọi FormulaEngine

```csharp
public class BookRenderingService
{
    private readonly IFormulaEngine _formulaEngine;
    
    public async Task<BookDataResponse> RenderBookAsync(long bookId, CancellationToken ct)
    {
        // 1. Load book + period + template
        var book = await _bookRepo.GetWithDetailsAsync(bookId, ct);
        var period = await _periodRepo.GetAsync(book.PeriodId, ct);
        
        // 2. Query data rows (Revenues, Costs, GL, SM...)
        var dataRows = await _dataQueryService.QueryRowsAsync(book, period, ct);
        
        // 3. Evaluate ALL formulas cho book này
        var ctx = new FormulaContext
        {
            BookId = bookId,
            BusinessLocationId = book.BusinessLocationId,
            PeriodId = period.PeriodId,
            PeriodStart = period.StartDate,
            PeriodEnd = period.EndDate,
            BusinessTypeId = book.BusinessTypeId,
            OpeningCashBalance = period.OpeningCashBalance,
            OpeningBankBalance = period.OpeningBankBalance
        };
        
        var computedValues = await _formulaEngine.EvaluateAllAsync(bookId, ctx, ct);
        // computedValues = { "S2A_QUARTERLY_TOTAL": 500000000, "S2A_VAT": 5000000, ... }
        
        // 4. Compose response: data rows + summary rows
        var response = new BookDataResponse
        {
            DataRows = dataRows,
            SummaryRows = BuildSummaryRows(book, computedValues)
        };
        
        return response;
    }
}
```

### S2d — Per-product evaluation

```csharp
// S2d: Cần evaluate formulas cho TỪNG sản phẩm
if (book.Template.TemplateCode == "S2d")
{
    var products = await _smRepo.GetDistinctProducts(book.BusinessLocationId, period, ct);
    
    foreach (var product in products)
    {
        var productCtx = ctx with { ProductId = product.ProductId };
        var productValues = await _formulaEngine.EvaluateAllAsync(bookId, productCtx, ct);
        // productValues cho sản phẩm này: S2D_OPENING_QTY, S2D_WEIGHTED_AVG, ...
    }
}
```

---

## 10. Business Rules

| Rule | Mô tả |
|------|-------|
| **RULE-FE-01** | Mỗi ô computed trong template phải có FormulaId FK → FormulaDefinitions |
| **RULE-FE-02** | CalculationOrder phải tăng dần, formula có `ref` phải trỏ tới formula có order nhỏ hơn |
| **RULE-FE-03** | Circular dependency (A ref B, B ref A) → reject khi lưu TemplateFieldMappings |
| **RULE-FE-04** | `DIVIDE` chia cho 0 → trả về 0 (không throw exception) |
| **RULE-FE-05** | Cache invalidation là **lazy** — chỉ mark stale, không tính lại ngay |
| **RULE-FE-06** | Khi export book → luôn tính lại tất cả formula (ignore cache) để đảm bảo snapshot chính xác |
| **RULE-FE-07** | FormulaDefinitions có IsActive — formula inactive không được gán cho FieldMapping mới, mapping cũ vẫn hoạt động |
| **RULE-FE-08** | ExpressionJson phải pass schema validation trước khi INSERT/UPDATE |
| **RULE-FE-09** | `aggregate` node chỉ được query entity trong MappableEntities (whitelist) |
| **RULE-FE-10** | `lookup` node chỉ được truy cập các table cho phép: IndustryTaxRates, AccountingPeriods |

---

## 11. API Endpoints

### Admin — Quản lý Formula

| # | Method | Endpoint | Mục đích |
|:-:|--------|----------|----------|
| 1 | `GET` | `/api/admin/formulas` | List tất cả formula definitions |
| 2 | `GET` | `/api/admin/formulas/{id}` | Chi tiết 1 formula |
| 3 | `POST` | `/api/admin/formulas` | Tạo formula mới |
| 4 | `PUT` | `/api/admin/formulas/{id}` | Sửa formula (ExpressionJson, Name...) |
| 5 | `POST` | `/api/admin/formulas/{id}/validate` | Validate ExpressionJson (check refs, schema) |
| 6 | `POST` | `/api/admin/formulas/{id}/dry-run` | Test formula với data thật (không lưu cache) |

### Internal — Cache Management

| # | Method | Endpoint | Mục đích |
|:-:|--------|----------|----------|
| 7 | `POST` | `/api/internal/formula-cache/invalidate` | Force invalidate (dùng khi debug) |
| 8 | `GET` | `/api/internal/formula-cache/stats` | Cache hit/miss stats |

---

## 12. Error Codes

| Code | HTTP | Mô tả |
|------|:----:|-------|
| `FORMULA_NOT_FOUND` | 404 | FormulaId không tồn tại |
| `FORMULA_INACTIVE` | 400 | Formula đã bị deactivate |
| `FORMULA_INVALID_EXPRESSION` | 400 | ExpressionJson không pass schema validation |
| `FORMULA_CIRCULAR_DEP` | 400 | Circular dependency detected |
| `FORMULA_MISSING_REF` | 400 | `ref` tham chiếu formula code không tồn tại |
| `FORMULA_ORDER_VIOLATION` | 400 | CalculationOrder vi phạm dependency (ref tới order cao hơn) |
| `FORMULA_EVAL_ERROR` | 500 | Lỗi runtime khi evaluate (unexpected) |
| `FORMULA_AGGREGATE_INVALID_SOURCE` | 400 | `source` không nằm trong MappableEntities whitelist |
| `FORMULA_LOOKUP_DENIED` | 400 | `lookup.entity` không nằm trong danh sách cho phép |