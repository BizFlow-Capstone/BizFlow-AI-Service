# Export Engine — Merge Field

> **Module**: Report & Accounting — Export Engine
> **Vị trí**: Bước cuối cùng trong Rendering Pipeline — nhận data đã tính toán, merge vào file template, xuất file xlsx/docx
> Quay về [report-accounting-flow.md](../03-flows/report-accounting-flow.md) (index)
>
> **Mục đích**: Nhận dữ liệu sổ kế toán (data rows + formula results) và merge vào file template (.xlsx hoặc .docx) sử dụng cơ chế **merge field** `{{placeholder}}`. Output là file hoàn chỉnh upload lên Cloudinary.

---

## Mục lục

1. [Vị trí trong kiến trúc](#1-vị-trí-trong-kiến-trúc)
2. [Quyết định thiết kế](#2-quyết-định-thiết-kế)
3. [Merge Field Specification](#3-merge-field-specification)
4. [Template Design — Từng sổ TT152](#4-template-design--từng-sổ-tt152)
5. [Export Pipeline](#5-export-pipeline)
6. [C# Architecture](#6-c-architecture)
7. [Integration — Data Collector & Formula Engine](#7-integration--data-collector--formula-engine)
8. [Template File Management](#8-template-file-management)
9. [Business Rules](#9-business-rules)
10. [API Contract (cập nhật)](#10-api-contract-cập-nhật)
11. [Error Codes](#11-error-codes)

---

## 1. Vị trí trong kiến trúc

```
┌────────────────────────────── EXPORT PIPELINE ──────────────────────────────┐
│                                                                             │
│  Owner bấm "Xuất sổ"                                                       │
│        │                                                                    │
│        ▼                                                                    │
│  ┌──────────────────┐                                                       │
│  │  ExportService    │                                                       │
│  │  (orchestrator)   │                                                       │
│  └──────┬───────────┘                                                       │
│         │                                                                    │
│    ┌────┴──────────────────────────────────────────────┐                     │
│    │                                                   │                     │
│    ▼                                                   ▼                     │
│  ┌──────────────────┐    ┌──────────────┐    ┌──────────────────┐           │
│  │  DataCollector    │───►│ FormulaEngine │    │ TemplateResolver │           │
│  │                   │    │              │    │                  │           │
│  │ Query:            │    │ Evaluate     │    │ Load template    │           │
│  │ - Revenues        │    │ formulas     │    │ .xlsx / .docx    │           │
│  │ - Costs           │    │ → Dict<>     │    │ from storage     │           │
│  │ - GL Entries      │    └──────────────┘    └────────┬─────────┘           │
│  │ - StockMovements  │                                 │                     │
│  └──────────────────┘                                  │                     │
│         │                                              │                     │
│         ▼                                              ▼                     │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │                    MergeProcessor                             │           │
│  │                                                               │           │
│  │  Input:                                                       │           │
│  │   - ExportContext (scalars, rows, formulas, sections)         │           │
│  │   - Template file stream (.xlsx or .docx)                     │           │
│  │                                                               │           │
│  │  Process:                                                     │           │
│  │   1. Parse merge fields {{...}} trong template                │           │
│  │   2. Replace scalar fields                                    │           │
│  │   3. Expand table rows ({{#rows}} ... {{/rows}})              │           │
│  │   4. Fill formula results ({{formula:CODE}})                  │           │
│  │   5. Handle sections / sheet duplication                      │           │
│  │                                                               │           │
│  │  Output: MemoryStream (completed file)                        │           │
│  └──────────────────────────────────┬────────────────────────────┘           │
│                                     │                                        │
│                                     ▼                                        │
│  ┌──────────────────────────────────────────────────────────────┐           │
│  │  FileUploader                                                 │           │
│  │  - Upload → Cloudinary                                        │           │
│  │  - Ghi AccountingExport record (snapshot)                     │           │
│  │  - Return file URL                                            │           │
│  └──────────────────────────────────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Quyết định thiết kế

### DD-EX-01: Dual format — xlsx + docx

Hệ thống hỗ trợ **2 định dạng** template và output:

| Format | Template file | Output file | Use case chính |
|--------|--------------|-------------|---------------|
| **xlsx** | `.xlsx` với merge fields trong cells | `.xlsx` | Sổ kế toán — kế toán quen Excel, dễ in, dễ chỉnh |
| **docx** | `.docx` với merge fields trong paragraphs/tables | `.docx` | Báo cáo, văn bản hành chính, cần trình bày đẹp hơn |

**Lý do dual format**: Sổ kế toán TT152 chủ yếu dạng bảng → xlsx phù hợp nhất. Nhưng một số mẫu báo cáo cần trình bày paragraph, header/footer phức tạp → docx bổ sung.

`AccountingTemplateVersions.TemplateFileUrl` lưu URL file template. Engine detect format qua file extension.

### DD-EX-02: Library — ClosedXML (xlsx) + Open XML SDK (docx)

| Library | Format | License | NuGet | Lý do chọn |
|---------|--------|---------|-------|-----------|
| **ClosedXML** | xlsx | MIT (free) | `ClosedXML` | API clean, mature (10K+ stars), active development. Xử lý cell formatting, row insertion, sheet copy tốt |
| **Open XML SDK** | docx | MIT (free) | `DocumentFormat.OpenXml` | Microsoft official, zero dependency, full control. Xử lý paragraph/table/merge field replacement |

**Alternatives bị loại:**

| Library | Lý do loại |
|---------|-----------|
| EPPlus v5+ | License thương mại từ v5, LGPL v4 nhưng cũ |
| NPOI | API verbose, documentation kém, lỗi memory leak với file lớn |
| Xceed DocX | Free chỉ cho non-commercial |
| Aspose | Thương mại, đắt |

### DD-EX-03: Merge field syntax — Mustache-inspired

Sử dụng cú pháp `{{...}}` (Mustache-style) vì:
- Quen thuộc với developer
- Không conflict với Excel formula syntax (`=SUM(...)`)
- Không conflict với Word mail merge syntax (`«field»`)
- Dễ regex parse: `\{\{(.+?)\}\}`

**3 loại merge field:**

| Loại | Pattern | Engine action |
|------|---------|--------------|
| **Scalar** | `{{field_name}}` | Replace text bằng giá trị đơn |
| **Row** | `{{row.field_code}}` (trong vùng `{{#rows}}...{{/rows}}`) | Duplicate row template, fill mỗi data row |
| **Formula** | `{{formula:CODE}}` | Lookup FormulaEngine result bằng Code |

### DD-EX-04: S2d — Duplicate sheet per product

Sổ S2d theo dõi XNT **per product**. Thay vì gộp tất cả sản phẩm vào 1 sheet dài:

- Template xlsx có 1 sheet mẫu (template sheet) chứa merge fields
- Engine duplicate sheet cho **mỗi sản phẩm**, rename sheet = tên sản phẩm
- Xóa sheet template gốc sau khi duplicate xong

**Lợi ích**: Giống sổ giấy thực tế (mỗi sản phẩm 1 trang sổ riêng), dễ in, dễ tra cứu.

### DD-EX-05: No PDF — chỉ xlsx/docx output

Không hỗ trợ convert sang PDF vì:
- Thêm dependency nặng (Puppeteer, LibreOffice headless...)
- Accountant cần file editable
- User có thể tự "Print to PDF" từ Excel/Word nếu cần

---

## 3. Merge Field Specification

### 3.1 Scalar Fields — `{{field_name}}`

Giá trị đơn lẻ, thường dùng cho header/footer/metadata.

**Available scalar fields:**

| Field name | Kiểu | Mô tả | Ví dụ |
|-----------|------|-------|-------|
| `book_name` | text | Tên sổ kế toán | "Sổ doanh thu bán hàng hóa, dịch vụ" |
| `template_code` | text | Mã template | "S2a" |
| `period_label` | text | Nhãn kỳ kế toán | "Quý I/2026" |
| `period_start` | date | Ngày bắt đầu kỳ | "01/01/2026" |
| `period_end` | date | Ngày kết thúc kỳ | "31/03/2026" |
| `location_name` | text | Tên địa điểm kinh doanh | "Cửa hàng VLXD Phú Thịnh" |
| `location_address` | text | Địa chỉ | "123 Nguyễn Trãi, Q.5, TP.HCM" |
| `owner_name` | text | Tên chủ hộ | "Nguyễn Văn A" |
| `business_type_name` | text | Tên ngành nghề (nếu tách ngành) | "Bán lẻ vật liệu xây dựng" |
| `tax_id` | text | Mã số thuế | "0312345678" |
| `group_number` | integer | Nhóm HKD | "2" |
| `tax_method` | text | Cách tính thuế | "Cách 1" |
| `export_date` | date | Ngày xuất sổ | "10/04/2026" |
| `product_name` | text | Tên sản phẩm (S2d, per sheet) | "Xi măng Hà Tiên PCB40" |
| `product_unit` | text | ĐVT sản phẩm (S2d, per sheet) | "Bao" |

**Xử lý trong xlsx:**

```csharp
// Cell chứa "Kỳ: {{period_label}}" → replace thành "Kỳ: Quý I/2026"
// Cell chứa "{{owner_name}}" → replace thành "Nguyễn Văn A"
// Giữ nguyên formatting (font, size, bold, border) của cell gốc
```

**Xử lý trong docx:**

```csharp
// Paragraph chứa "Kỳ kế toán: {{period_label}}" → replace text run
// Giữ nguyên formatting (font, size, bold) của run gốc
```

### 3.2 Table Row Fields — `{{#rows}}` / `{{row.field_code}}` / `{{/rows}}`

Vùng lặp — engine duplicate dòng template cho mỗi data row.

**Cú pháp trong xlsx:**

```
Row N  : Cell A chứa "{{#rows}}"                ← START marker (dòng này bị xóa)
Row N+1: {{row.stt}} | {{row.date}} | {{row.description}} | {{row.revenue}}
                                                  ← TEMPLATE ROW (được duplicate × N)
Row N+2: Cell A chứa "{{/rows}}"                ← END marker (dòng này bị xóa)
```

Engine xử lý:
1. Tìm dòng chứa `{{#rows}}` và `{{/rows}}`
2. Lấy các dòng **giữa** làm template rows
3. Xóa marker rows (`{{#rows}}` và `{{/rows}}`)
4. Với mỗi data row → clone template row, replace `{{row.xxx}}` bằng giá trị
5. Insert cloned rows vào vị trí, **đẩy các dòng bên dưới xuống** (shift down)
6. Giữ nguyên cell formatting từ template row (font, border, number format, alignment...)

**Cú pháp trong docx:**

```
Paragraph: {{#rows}}
Table Row: | {{row.stt}} | {{row.date}} | {{row.description}} | {{row.revenue}} |
Paragraph: {{/rows}}
```

Engine duplicate table row trong docx table.

**Row fields mapping** — lấy từ `TemplateFieldMappings`:

```
{{row.stt}}         → FieldCode="stt",         SourceType="auto"
{{row.date}}        → FieldCode="date",        SourceType="query"  → MappableField
{{row.description}} → FieldCode="description", SourceType="query"  → MappableField
{{row.revenue}}     → FieldCode="revenue",     SourceType="query"  → MappableField
```

### 3.3 Section Fields — `{{#section:name}}` / `{{/section:name}}`

Cho templates có **nhiều section** (S2c: DT + CP, S2e: cash + bank).

```
{{#section:revenue}}
{{#rows}}
{{row.stt}} | {{row.date}} | {{row.description}} | {{row.amount}}
{{/rows}}
{{formula:S2C_TOTAL_REVENUE}}
{{/section:revenue}}

{{#section:cost}}
{{#rows}}
{{row.stt}} | {{row.date}} | {{row.description}} | {{row.amount}}
{{/rows}}
{{formula:S2C_TOTAL_COST}}
{{/section:cost}}
```

Mỗi section có **data rows riêng** và **formula results riêng**.

### 3.4 Formula Fields — `{{formula:CODE}}`

Tham chiếu kết quả từ FormulaEngine bằng `FormulaDefinitions.Code`.

```
{{formula:S2A_QUARTERLY_TOTAL}}    → 500,000,000
{{formula:S2A_VAT}}                → 5,000,000
{{formula:S2A_PIT}}                → 0
```

Engine xử lý:
1. Parse CODE từ `{{formula:CODE}}`
2. Lookup trong `Dictionary<string, decimal>` trả về bởi `FormulaEngine.EvaluateAllAsync()`
3. Replace bằng giá trị, format theo number format của cell (xlsx) hoặc run format (docx)
4. Nếu CODE không tồn tại → để trống + log warning

### 3.5 Sheet Duplication — `{{#sheets:source}}`

Dùng cho S2d (1 sheet per product). Chỉ áp dụng xlsx.

Template xlsx có **1 sheet tên `_template_`** (hoặc bất kỳ tên chứa `{{#sheets:products}}`):

```
Sheet tab name: "{{#sheets:products}}"

Cell A1: Sổ chi tiết: {{product_name}}
Cell B1: ĐVT: {{product_unit}}
...
{{#rows}}
{{row.document_code}} | {{row.date}} | {{row.description}} | ...
{{/rows}}
{{formula:S2D_OPENING_QTY}}
{{formula:S2D_WEIGHTED_AVG}}
...
```

Engine xử lý:
1. Detect sheet có tab name chứa `{{#sheets:products}}`
2. Lấy danh sách products → với mỗi product:
   a. Copy sheet template → rename = product name (truncate 31 chars — Excel limit)
   b. Set `context.ProductId` → evaluate formulas cho product này
   c. Merge data rows + scalars + formulas vào sheet mới
3. Xóa sheet template gốc

### 3.6 Monthly Group — `{{#monthly_groups}}`

Dùng cho S1a (cần tổng tháng + tổng quý).

```
{{#monthly_groups}}
  Tháng {{month_label}}:
  {{#rows}}
  {{row.stt}} | {{row.date}} | {{row.description}} | {{row.revenue}}
  {{/rows}}
  Cộng tháng {{month_label}}: {{month_total}}
{{/monthly_groups}}
Cộng quý: {{formula:S1A_QUARTERLY_TOTAL}}
```

Engine xử lý:
1. Group data rows theo tháng (`RevenueDate.Month`)
2. Với mỗi tháng → expand rows + insert subtotal row
3. Cuối cùng insert dòng tổng quý (formula)

### 3.7 Merge Field Resolution Order

```
1. Scalar fields          → {{field_name}}
2. Sheet duplication      → {{#sheets:products}}     (xlsx only)
3. Section expansion      → {{#section:name}}
4. Monthly groups         → {{#monthly_groups}}       (S1a)
5. Row expansion          → {{#rows}} ... {{/rows}}
6. Formula fields         → {{formula:CODE}}
7. Cleanup                → remove unfilled {{...}} markers
```

Resolve theo thứ tự này để đảm bảo:
- Sheet đã duplicate trước khi fill data
- Section đã xác định trước khi expand rows
- Row đã expand xong trước khi fill formula (vì formula row ở cuối bảng, position bị đẩy xuống khi rows expand)

---

## 4. Template Design — Từng sổ TT152

### 4.1 S1a — Sổ chi tiết bán hàng

**Format chính**: xlsx

```
┌─────────────────────────────────────────────────────────┐
│ A1: SỔ CHI TIẾT BÁN HÀNG                               │
│ A2: Kỳ: {{period_label}}                                │
│ A3: Địa điểm: {{location_name}}                         │
│ A4: Chủ hộ: {{owner_name}}                              │
│ ────────────────────────────────────────────────────────│
│      A         B            C                D          │
│ ┌────────┬──────────┬─────────────────┬──────────────┐  │
│ │  STT   │ Ngày     │ Nội dung        │ Doanh thu    │  │
│ │        │ tháng    │ (Diễn giải)     │ bán hàng     │  │
│ ├────────┼──────────┼─────────────────┼──────────────┤  │
│ │{{#monthly_groups}}                                 │  │
│ │{{#rows}}                                           │  │
│ │{{row.stt}} │{{row.date}}│{{row.description}}│{{row.revenue}}│
│ │{{/rows}}                                           │  │
│ │        │          │ Cộng tháng      │{{month_total}}│  │
│ │        │          │ {{month_label}} │              │  │
│ │{{/monthly_groups}}                                 │  │
│ ├────────┼──────────┼─────────────────┼──────────────┤  │
│ │        │          │  Cộng quý       │{{formula:S1A_QUARTERLY_TOTAL}}│
│ └────────┴──────────┴─────────────────┴──────────────┘  │
│                                                         │
│ Ngày xuất: {{export_date}}                              │
└─────────────────────────────────────────────────────────┘
```

**Merge context:**

| Key | Source |
|-----|--------|
| Scalars | Book metadata + Period + Location |
| Rows | Revenues (sale + manual) + GL manual_revenue, grouped by month |
| Formulas | `S1A_MONTHLY_TOTAL`, `S1A_QUARTERLY_TOTAL` |

### 4.2 S2a — Sổ doanh thu (Cách 1)

**Format chính**: xlsx

```
┌──────────────────────────────────────────────────────────────┐
│ A1: SỔ DOANH THU BÁN HÀNG HÓA, DỊCH VỤ                     │
│ A2: (Dùng cho hộ kinh doanh nộp thuế theo phương pháp        │
│      khoán — Cách 1)                                          │
│ A3: Kỳ: {{period_label}}    Ngành: {{business_type_name}}    │
│ A4: Địa điểm: {{location_name}}                              │
│ ─────────────────────────────────────────────────────────────│
│       A              B              C             D          │
│ ┌───────────┬──────────────┬──────────────┬──────────────┐   │
│ │ Chứng từ  │ Chứng từ     │ Diễn giải    │ Số tiền      │   │
│ │ Số hiệu   │ Ngày tháng   │    (C)       │    (1)       │   │
│ │   (A)      │    (B)       │              │              │   │
│ ├───────────┼──────────────┼──────────────┼──────────────┤   │
│ │{{#rows}}                                               │   │
│ │{{row.so_hieu}}│{{row.ngay_thang}}│{{row.dien_giai}}│{{row.so_tien}}│
│ │{{/rows}}                                               │   │
│ ├───────────┼──────────────┼──────────────┼──────────────┤   │
│ │           │              │ Cộng quý     │{{formula:S2A_QUARTERLY_TOTAL}}│
│ │           │              │ Thuế GTGT    │{{formula:S2A_VAT}}│
│ │           │              │ Thuế TNCN    │{{formula:S2A_PIT}}│
│ └───────────┴──────────────┴──────────────┴──────────────┘   │
│                                                               │
│ Ngày xuất: {{export_date}}        Chủ hộ: {{owner_name}}    │
└──────────────────────────────────────────────────────────────┘
```

### 4.3 S2b — Sổ doanh thu (Cách 2+)

Giống S2a nhưng **không có dòng thuế TNCN** (TNCN tính ở S2c).

```
│ │           │              │ Cộng quý     │{{formula:S2B_QUARTERLY_TOTAL}}│
│ │           │              │ Thuế GTGT    │{{formula:S2B_VAT}}│
```

### 4.4 S2c — Sổ DT, CP (2 section)

```
┌────────────────────────────────────────────────────────────────┐
│ A1: SỔ CHI TIẾT DOANH THU, CHI PHÍ                            │
│ A2: Kỳ: {{period_label}}                                      │
│ ──────────────────────────────────────────────────────────────│
│       A              B              C             D           │
│ ┌───────────┬──────────────┬──────────────┬──────────────┐    │
│ │ Số hiệu   │ Ngày tháng   │ Diễn giải    │ Số tiền      │    │
│ ├───────────┼──────────────┼──────────────┼──────────────┤    │
│ │           │              │ I. DOANH THU │              │    │
│ │{{#section:revenue}}                                    │    │
│ │{{#rows}}                                               │    │
│ │{{row.so_hieu}}│{{row.ngay_thang}}│{{row.dien_giai}}│{{row.so_tien}}│
│ │{{/rows}}                                               │    │
│ │           │              │ Tổng DT      │{{formula:S2C_TOTAL_REVENUE}}│
│ │{{/section:revenue}}                                    │    │
│ │           │              │ II. CHI PHÍ  │              │    │
│ │{{#section:cost}}                                       │    │
│ │{{#rows}}                                               │    │
│ │{{row.so_hieu}}│{{row.ngay_thang}}│{{row.dien_giai}}│{{row.so_tien}}│
│ │{{/rows}}                                               │    │
│ │           │              │ Tổng CP      │{{formula:S2C_TOTAL_COST}}│
│ │{{/section:cost}}                                       │    │
│ ├───────────┼──────────────┼──────────────┼──────────────┤    │
│ │           │              │ III. Chênh   │{{formula:S2C_PROFIT}}│
│ │           │              │ lệch (DT-CP) │              │    │
│ │           │              │ Thuế TNCN    │{{formula:S2C_PIT}}│
│ └───────────┴──────────────┴──────────────┴──────────────┘    │
└────────────────────────────────────────────────────────────────┘
```

### 4.5 S2d — Sổ kho XNT (multi-sheet per product)

**Sheet tab name**: `{{#sheets:products}}`

```
┌──────────────────────────────────────────────────────────────────────────┐
│ A1: SỔ CHI TIẾT VẬT LIỆU, DỤNG CỤ, SẢN PHẨM, HÀNG HÓA              │
│ A2: Tên hàng: {{product_name}}   ĐVT: {{product_unit}}                │
│ A3: Kỳ: {{period_label}}                                               │
│ ────────────────────────────────────────────────────────────────────────│
│    A       B      C      D     E      F       G      H       I     J  │
│ ┌──────┬──────┬──────┬────┬─────┬──────┬───────┬──────┬───────┬─────┬──────┐│
│ │Số    │Ngày  │Diễn  │ĐVT │Đơn  │ NHẬP        │ XUẤT        │ TỒN       ││
│ │hiệu │      │giải  │    │giá  │SL    │Tiền   │SL    │Tiền   │SL   │Tiền  ││
│ │(A)   │(B)   │(C)   │(D) │(1)  │(2)   │(3)    │(4)   │(5)    │(6)  │(7)   ││
│ ├──────┼──────┼──────┼────┼─────┼──────┼───────┼──────┼───────┼─────┼──────┤│
│ │      │      │Tồn   │    │     │      │       │      │       │{{formula:S2D_OPENING_QTY}}│{{formula:S2D_OPENING_VALUE}}││
│ │      │      │ĐK    │    │     │      │       │      │       │     │      ││
│ │{{#rows}}                                                              ││
│ │{{row.doc_code}}│{{row.date}}│{{row.desc}}│{{row.unit}}│{{row.unit_price}}│{{row.import_qty}}│{{row.import_value}}│{{row.export_qty}}│{{row.export_value}}│{{row.stock_qty}}│{{row.stock_value}}││
│ │{{/rows}}                                                              ││
│ ├──────┼──────┼──────┼────┼─────┼──────┼───────┼──────┼───────┼─────┼──────┤│
│ │      │      │Tồn   │    │ĐG BQ│{{formula:S2D_IMPORT_QTY}}│{{formula:S2D_IMPORT_VALUE}}│{{formula:S2D_EXPORT_QTY}}│{{formula:S2D_EXPORT_VALUE}}│{{formula:S2D_CLOSING_QTY}}│{{formula:S2D_CLOSING_VALUE}}││
│ │      │      │CK    │    │{{formula:S2D_WEIGHTED_AVG}}│   │       │      │       │     │      ││
│ └──────┴──────┴──────┴────┴─────┴──────┴───────┴──────┴───────┴─────┴──────┘│
└──────────────────────────────────────────────────────────────────────────┘
```

**Engine behavior:**
1. Load danh sách products từ `StockMovements` (distinct ProductId cho location + period)
2. Với mỗi product:
   - Copy sheet template
   - Rename sheet → `product.ProductName` (max 31 chars)
   - Set `context.ProductId = product.ProductId`
   - Evaluate formulas S2D_* cho product này
   - Query StockMovements rows cho product này
   - Merge all fields
3. Xóa sheet template gốc

### 4.6 S2e — Sổ chi tiết tiền (2 section)

```
┌──────────────────────────────────────────────────────────────┐
│ A1: SỔ CHI TIẾT TIỀN                                        │
│ A2: Kỳ: {{period_label}}                                    │
│ ─────────────────────────────────────────────────────────── │
│       A              B              C          D         E  │
│ ┌───────────┬──────────────┬────────────┬──────────┬────────┐│
│ │ Số hiệu   │ Ngày tháng   │ Diễn giải  │ Thu/Gửi  │ Chi/  ││
│ │   (A)      │    (B)       │    (C)     │ vào (1)  │Rút (2)││
│ ├───────────┼──────────────┼────────────┼──────────┼────────┤│
│ │           │              │ TIỀN MẶT   │          │        ││
│ │           │              │ Đầu kỳ     │{{formula:S2E_CASH_OPENING}}│ ││
│ │{{#section:cash}}                                          ││
│ │{{#rows}}                                                  ││
│ │{{row.so_hieu}}│{{row.ngay_thang}}│{{row.dien_giai}}│{{row.thu_vao}}│{{row.chi_ra}}││
│ │{{/rows}}                                                  ││
│ │           │              │Tổng thu    │{{formula:S2E_CASH_IN}}│ ││
│ │           │              │Tổng chi    │          │{{formula:S2E_CASH_OUT}}││
│ │           │              │Tồn CK     │{{formula:S2E_CASH_CLOSING}}│ ││
│ │{{/section:cash}}                                          ││
│ ├───────────┼──────────────┼────────────┼──────────┼────────┤│
│ │           │              │ TIỀN GỬI   │          │        ││
│ │           │              │ Đầu kỳ     │{{formula:S2E_BANK_OPENING}}│ ││
│ │{{#section:bank}}                                          ││
│ │{{#rows}}                                                  ││
│ │{{row.so_hieu}}│{{row.ngay_thang}}│{{row.dien_giai}}│{{row.gui_vao}}│{{row.rut_ra}}││
│ │{{/rows}}                                                  ││
│ │           │              │Tổng gửi    │{{formula:S2E_BANK_IN}}│ ││
│ │           │              │Tổng rút    │          │{{formula:S2E_BANK_OUT}}││
│ │           │              │Dư CK       │{{formula:S2E_BANK_CLOSING}}│ ││
│ │{{/section:bank}}                                          ││
│ └───────────┴──────────────┴────────────┴──────────┴────────┘│
└──────────────────────────────────────────────────────────────┘
```

---

## 5. Export Pipeline

### 5.1 Flow tổng quan

```
ExportBook(bookId, format, userId):
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  1. Load Book → lấy TemplateVersionId, PeriodId, BusinessTypeId     │
│                                                                     │
│  2. TemplateResolver:                                               │
│     Load template file (.xlsx / .docx) từ storage                   │
│     → Validate format khớp với request                              │
│     → Return MemoryStream                                           │
│                                                                     │
│  3. DataCollector:                                                  │
│     3a. Build FormulaContext                                        │
│     3b. FormulaEngine.EvaluateAllAsync(bookId, ctx)                 │
│         → Dict<string, decimal> formulaResults                      │
│     3c. Query data rows theo TemplateFieldMappings (SourceType=query)│
│     3d. Query scalar values (location, period, owner metadata)      │
│     3e. Assemble ExportContext                                      │
│                                                                     │
│  4. MergeProcessor:                                                 │
│     4a. Detect format (xlsx vs docx) → delegate to processor        │
│     4b. XlsxMergeProcessor hoặc DocxMergeProcessor                  │
│     4c. Execute merge theo Resolution Order (Section 3.7)           │
│     4d. Return MemoryStream (completed file)                        │
│                                                                     │
│  5. FileUploader:                                                   │
│     5a. Upload MemoryStream → Cloudinary                            │
│     5b. Get FileUrl + PublicId                                      │
│                                                                     │
│  6. Snapshot:                                                       │
│     6a. Build SummaryJson (tổng DT, CP, thuế, row count...)        │
│     6b. INSERT AccountingExport record                              │
│     6c. Audit log                                                   │
│                                                                     │
│  7. RETURN ExportResult (exportId, fileUrl, summary)                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 ExportContext — Data model cho merge

```csharp
/// <summary>
/// Tất cả data cần thiết để merge vào 1 template file.
/// Được assemble bởi DataCollector, consume bởi MergeProcessor.
/// </summary>
public class ExportContext
{
    // ═══ SCALAR VALUES ═══
    public Dictionary<string, string> Scalars { get; set; } = new();
    
    // ═══ FORMULA RESULTS ═══
    public Dictionary<string, decimal> FormulaResults { get; set; } = new();
    
    // ═══ DATA ROWS (flat — cho template không có section) ═══
    public List<Dictionary<string, object?>> Rows { get; set; } = new();
    
    // ═══ SECTIONS (cho S2c, S2e) ═══
    public Dictionary<string, SectionData> Sections { get; set; } = new();
    
    // ═══ MONTHLY GROUPS (cho S1a) ═══
    public List<MonthlyGroup>? MonthlyGroups { get; set; }
    
    // ═══ PRODUCTS (cho S2d — multi-sheet) ═══
    public List<ProductSheetData>? ProductSheets { get; set; }
    
    // ═══ METADATA ═══
    public string TemplateCode { get; set; } = null!;
    public string ExportFormat { get; set; } = null!;  // "xlsx" | "docx"
}

public class SectionData
{
    public string SectionName { get; set; } = null!;
    public List<Dictionary<string, object?>> Rows { get; set; } = new();
}

public class MonthlyGroup
{
    public string MonthLabel { get; set; } = null!;   // "Tháng 01", "Tháng 02"...
    public decimal MonthTotal { get; set; }
    public List<Dictionary<string, object?>> Rows { get; set; } = new();
}

public class ProductSheetData
{
    public string ProductId { get; set; } = null!;
    public string ProductName { get; set; } = null!;
    public string ProductUnit { get; set; } = null!;
    
    // Scalars riêng cho sheet này
    public Dictionary<string, string> Scalars { get; set; } = new();
    
    // Formula results riêng cho product này
    public Dictionary<string, decimal> FormulaResults { get; set; } = new();
    
    // Data rows riêng
    public List<Dictionary<string, object?>> Rows { get; set; } = new();
}
```

### 5.3 Merge Processor — xlsx (ClosedXML)

```csharp
public class XlsxMergeProcessor
{
    public MemoryStream Process(Stream templateStream, ExportContext context)
    {
        using var workbook = new XLWorkbook(templateStream);
        
        // 1. Sheet duplication (S2d)
        if (context.ProductSheets is { Count: > 0 })
        {
            ProcessSheetDuplication(workbook, context.ProductSheets);
        }
        else
        {
            // Process single sheet
            var sheet = workbook.Worksheets.First();
            ProcessSheet(sheet, context);
        }
        
        var output = new MemoryStream();
        workbook.SaveAs(output);
        output.Position = 0;
        return output;
    }
    
    private void ProcessSheet(IXLWorksheet sheet, ExportContext context, 
        ProductSheetData? productData = null)
    {
        var scalars = productData?.Scalars ?? context.Scalars;
        var formulas = productData?.FormulaResults ?? context.FormulaResults;
        
        // Step 1: Replace scalar fields
        ReplaceScalars(sheet, scalars);
        
        // Step 2: Process sections (nếu có)
        if (context.Sections.Count > 0)
        {
            foreach (var (sectionName, sectionData) in context.Sections)
                ProcessSection(sheet, sectionName, sectionData);
        }
        
        // Step 3: Process monthly groups (S1a)
        if (context.MonthlyGroups is { Count: > 0 })
            ProcessMonthlyGroups(sheet, context.MonthlyGroups);
        
        // Step 4: Expand rows (simple — non-sectioned)
        if (context.Rows.Count > 0 && context.Sections.Count == 0)
            ExpandRows(sheet, context.Rows);
        
        // Step 5: Replace formula fields
        ReplaceFormulas(sheet, formulas);
        
        // Step 6: Cleanup unfilled merge fields
        CleanupUnfilledFields(sheet);
    }
    
    private void ReplaceScalars(IXLWorksheet sheet, Dictionary<string, string> scalars)
    {
        foreach (var cell in sheet.CellsUsed())
        {
            if (cell.Value.IsText)
            {
                var text = cell.GetText();
                foreach (var (key, value) in scalars)
                {
                    text = text.Replace($"{{{{{key}}}}}", value);
                }
                if (text != cell.GetText())
                    cell.Value = text;
            }
        }
    }
    
    private void ExpandRows(IXLWorksheet sheet, 
        List<Dictionary<string, object?>> rows)
    {
        // Find {{#rows}} and {{/rows}} markers
        int startRow = -1, endRow = -1;
        foreach (var cell in sheet.CellsUsed())
        {
            var text = cell.GetText();
            if (text.Contains("{{#rows}}")) startRow = cell.Address.RowNumber;
            if (text.Contains("{{/rows}}")) endRow = cell.Address.RowNumber;
        }
        
        if (startRow < 0 || endRow < 0) return;
        
        // Template rows = rows between markers (exclusive)
        int templateRowStart = startRow + 1;
        int templateRowEnd = endRow - 1;
        int templateRowCount = templateRowEnd - templateRowStart + 1;
        
        // Collect template row formats + merge field patterns
        var templateInfo = CaptureTemplateRows(sheet, templateRowStart, templateRowEnd);
        
        // Delete marker rows + template rows
        // Insert data rows at position
        sheet.Row(endRow).Delete();                    // delete {{/rows}} first (bottom up)
        for (int r = templateRowEnd; r >= templateRowStart; r--)
            sheet.Row(r).Delete();
        sheet.Row(startRow).Delete();                  // delete {{#rows}}
        
        int insertAt = startRow;
        foreach (var dataRow in rows)
        {
            var newRow = sheet.Row(insertAt);
            // Apply template formatting
            ApplyTemplateFormat(newRow, templateInfo);
            // Fill values
            foreach (var (fieldCode, value) in dataRow)
            {
                var colIndex = templateInfo.GetColumnFor($"{{{{row.{fieldCode}}}}}");
                if (colIndex > 0)
                    SetCellValue(sheet.Cell(insertAt, colIndex), value);
            }
            insertAt++;
        }
    }
    
    private void ReplaceFormulas(IXLWorksheet sheet, 
        Dictionary<string, decimal> formulas)
    {
        foreach (var cell in sheet.CellsUsed())
        {
            if (!cell.Value.IsText) continue;
            var text = cell.GetText();
            
            var match = Regex.Match(text, @"\{\{formula:(\w+)\}\}");
            if (match.Success)
            {
                var code = match.Groups[1].Value;
                if (formulas.TryGetValue(code, out var value))
                {
                    cell.Value = value;
                    // Keep number format from template cell
                }
            }
        }
    }
}
```

### 5.4 Merge Processor — docx (Open XML SDK)

```csharp
public class DocxMergeProcessor
{
    public MemoryStream Process(Stream templateStream, ExportContext context)
    {
        var output = new MemoryStream();
        templateStream.CopyTo(output);
        output.Position = 0;
        
        using var doc = WordprocessingDocument.Open(output, isEditable: true);
        var body = doc.MainDocumentPart!.Document.Body!;
        
        // Step 1: Replace scalar fields in all paragraphs
        ReplaceScalarsInBody(body, context.Scalars);
        
        // Step 2: Expand table rows
        ExpandTableRows(body, context);
        
        // Step 3: Replace formula fields
        ReplaceFormulasInBody(body, context.FormulaResults);
        
        // Step 4: Cleanup
        CleanupUnfilledFields(body);
        
        doc.Save();
        output.Position = 0;
        return output;
    }
    
    private void ReplaceScalarsInBody(Body body, Dictionary<string, string> scalars)
    {
        foreach (var paragraph in body.Descendants<Paragraph>())
        {
            var fullText = paragraph.InnerText;
            foreach (var (key, value) in scalars)
            {
                var placeholder = $"{{{{{key}}}}}";
                if (fullText.Contains(placeholder))
                {
                    ReplacePlaceholderInParagraph(paragraph, placeholder, value);
                }
            }
        }
    }
    
    private void ExpandTableRows(Body body, ExportContext context)
    {
        // Find table containing {{#rows}} marker
        foreach (var table in body.Descendants<Table>())
        {
            var rows = table.Elements<TableRow>().ToList();
            TableRow? startMarkerRow = null;
            TableRow? templateRow = null;
            TableRow? endMarkerRow = null;
            
            for (int i = 0; i < rows.Count; i++)
            {
                var text = rows[i].InnerText;
                if (text.Contains("{{#rows}}")) startMarkerRow = rows[i];
                if (text.Contains("{{/rows}}")) endMarkerRow = rows[i];
                if (startMarkerRow != null && endMarkerRow == null 
                    && rows[i] != startMarkerRow)
                    templateRow = rows[i];
            }
            
            if (startMarkerRow == null || templateRow == null 
                || endMarkerRow == null) continue;
            
            // Clone template row for each data row
            var dataRows = context.Rows;
            var insertBefore = endMarkerRow;
            
            foreach (var dataRow in dataRows)
            {
                var newRow = (TableRow)templateRow.CloneNode(true);
                foreach (var (fieldCode, value) in dataRow)
                {
                    var placeholder = $"{{{{row.{fieldCode}}}}}";
                    ReplacePlaceholderInRow(newRow, placeholder, 
                        value?.ToString() ?? "");
                }
                table.InsertBefore(newRow, insertBefore);
            }
            
            // Remove marker rows + template row
            startMarkerRow.Remove();
            templateRow.Remove();
            endMarkerRow.Remove();
        }
    }
}
```

---

## 6. C# Architecture

### 6.1 Project structure

```
BizFlow.Application/
├── Interfaces/
│   ├── IExportService.cs             -- Orchestrator interface
│   ├── ITemplateResolver.cs          -- Load template file
│   └── IMergeProcessor.cs            -- Merge data into template
│
├── DTOs/
│   ├── ExportBookRequest.cs          -- { format: "xlsx"|"docx", notes?: string }
│   └── ExportBookResponse.cs         -- { exportId, fileUrl, summary }
│
BizFlow.Infrastructure/
├── Services/
│   └── Export/
│       ├── ExportService.cs           -- Main orchestrator
│       ├── DataCollector.cs           -- Query data + formula → ExportContext
│       ├── TemplateResolver.cs        -- Download template file from URL/storage
│       ├── MergeProcessor/
│       │   ├── IMergeProcessor.cs     -- Interface
│       │   ├── XlsxMergeProcessor.cs  -- ClosedXML-based
│       │   ├── DocxMergeProcessor.cs  -- OpenXML SDK-based
│       │   └── MergeProcessorFactory.cs -- Chọn processor theo format
│       └── FileUploader.cs            -- Upload to Cloudinary
```

### 6.2 Interfaces

```csharp
public interface IExportService
{
    Task<ExportBookResponse> ExportBookAsync(
        int locationId, long bookId, ExportBookRequest request, 
        Guid userId, CancellationToken ct = default);
}

public interface ITemplateResolver
{
    /// <summary>
    /// Load template file stream từ TemplateVersion.TemplateFileUrl.
    /// Support: local file, Cloudinary URL, embedded resource.
    /// </summary>
    Task<Stream> ResolveAsync(
        int templateVersionId, CancellationToken ct = default);
}

public interface IMergeProcessor
{
    /// <summary>
    /// Merge ExportContext vào template stream, trả về completed file stream.
    /// </summary>
    MemoryStream Process(Stream templateStream, ExportContext context);
    
    /// <summary>
    /// Format hỗ trợ: "xlsx" hoặc "docx"
    /// </summary>
    string SupportedFormat { get; }
}
```

### 6.3 ExportService — Orchestrator

```csharp
public class ExportService : IExportService
{
    private readonly IUnitOfWork _unitOfWork;
    private readonly IFormulaEngine _formulaEngine;
    private readonly ITemplateResolver _templateResolver;
    private readonly MergeProcessorFactory _mergeFactory;
    private readonly IFileUploader _fileUploader;
    private readonly IAuditService _auditService;
    
    public async Task<ExportBookResponse> ExportBookAsync(
        int locationId, long bookId, ExportBookRequest request,
        Guid userId, CancellationToken ct = default)
    {
        // 1. Load book + validate ownership
        var book = await _unitOfWork.AccountingBooks.GetByIdAsync(bookId, ct);
        if (book == null || book.BusinessLocationId != locationId)
            throw new NotFoundException("Book not found");
        
        // 2. Resolve template file
        var templateStream = await _templateResolver.ResolveAsync(
            book.TemplateVersionId, ct);
        
        // 3. Collect data → ExportContext
        var context = await CollectDataAsync(book, request.Format, ct);
        
        // 4. Merge
        var processor = _mergeFactory.GetProcessor(request.Format);
        var outputStream = processor.Process(templateStream, context);
        
        // 5. Upload
        var fileName = BuildFileName(book, request.Format);
        var uploadResult = await _fileUploader.UploadAsync(
            outputStream, fileName, ct);
        
        // 6. Save export record
        var export = new AccountingExport
        {
            BookId = bookId,
            GroupNumber = book.GroupNumber,
            TaxMethod = book.TaxMethod,
            RulesetVersion = book.Ruleset.VersionLabel,
            SummaryJson = BuildSummaryJson(context),
            DataRowCount = CountTotalRows(context),
            ExportFormat = request.Format,
            FileUrl = uploadResult.FileUrl,
            FilePublicId = uploadResult.PublicId,
            ExportedByUserId = userId,
            ExportedAt = DateTime.UtcNow,
            Notes = request.Notes,
        };
        
        await _unitOfWork.AccountingExports.AddAsync(export, ct);
        await _unitOfWork.SaveChangesAsync(ct);
        
        // 7. Audit log
        await _auditService.LogAsync(book.PeriodId, "book_exported", userId, new
        {
            bookId,
            format = request.Format,
            exportId = export.ExportId,
        }, ct);
        
        return new ExportBookResponse
        {
            ExportId = export.ExportId,
            BookId = bookId,
            GroupNumber = book.GroupNumber,
            RulesetVersion = export.RulesetVersion,
            Format = request.Format,
            FileUrl = uploadResult.FileUrl,
            Summary = BuildSummaryDto(context),
            DataRowCount = export.DataRowCount,
            ExportedAt = export.ExportedAt,
            Notes = request.Notes,
        };
    }
    
    private string BuildFileName(AccountingBook book, string format)
    {
        var template = book.TemplateVersion.Template;
        var period = book.Period;
        // e.g. "S2a_Q1_2026_retail.xlsx"
        var suffix = book.BusinessTypeId != null 
            ? $"_{book.BusinessTypeId}" : "";
        return $"{template.TemplateCode}_{period.PeriodLabel}{suffix}.{format}";
    }
}
```

### 6.4 DataCollector

```csharp
public class DataCollector
{
    private readonly IUnitOfWork _unitOfWork;
    private readonly IFormulaEngine _formulaEngine;
    
    public async Task<ExportContext> CollectAsync(
        AccountingBook book, string format, CancellationToken ct)
    {
        var period = book.Period;
        var location = book.BusinessLocation;
        var templateCode = book.TemplateVersion.Template.TemplateCode;
        
        var context = new ExportContext
        {
            TemplateCode = templateCode,
            ExportFormat = format,
        };
        
        // ═══ SCALARS (common) ═══
        context.Scalars["book_name"] = book.TemplateVersion.Template.Name;
        context.Scalars["template_code"] = templateCode;
        context.Scalars["period_label"] = period.PeriodLabel;
        context.Scalars["period_start"] = period.StartDate.ToString("dd/MM/yyyy");
        context.Scalars["period_end"] = period.EndDate.ToString("dd/MM/yyyy");
        context.Scalars["location_name"] = location.LocationName;
        context.Scalars["location_address"] = location.Address ?? "";
        context.Scalars["owner_name"] = location.Owner?.FullName ?? "";
        context.Scalars["tax_id"] = location.TaxId ?? "";
        context.Scalars["group_number"] = book.GroupNumber.ToString();
        context.Scalars["tax_method"] = FormatTaxMethod(book.TaxMethod);
        context.Scalars["export_date"] = DateTime.Now.ToString("dd/MM/yyyy");
        
        if (book.BusinessTypeId != null)
        {
            var bt = await _unitOfWork.BusinessTypes
                .GetByIdAsync(book.BusinessTypeId.Value, ct);
            context.Scalars["business_type_name"] = bt?.Name ?? "";
        }
        
        // ═══ TEMPLATE-SPECIFIC DATA ═══
        switch (templateCode)
        {
            case "S1a":
                await CollectS1aAsync(book, context, ct);
                break;
            case "S2a":
                await CollectS2aAsync(book, context, ct);
                break;
            case "S2b":
                await CollectS2bAsync(book, context, ct);
                break;
            case "S2c":
                await CollectS2cAsync(book, context, ct);
                break;
            case "S2d":
                await CollectS2dAsync(book, context, ct);
                break;
            case "S2e":
                await CollectS2eAsync(book, context, ct);
                break;
        }
        
        return context;
    }
    
    private async Task CollectS1aAsync(
        AccountingBook book, ExportContext context, CancellationToken ct)
    {
        // Query revenue rows
        var rows = await _unitOfWork.Revenues
            .GetForBookExportAsync(book, ct);
        
        // Group by month
        var grouped = rows
            .GroupBy(r => ((DateTime)r["date"]).Month)
            .OrderBy(g => g.Key)
            .ToList();
        
        context.MonthlyGroups = new List<MonthlyGroup>();
        foreach (var group in grouped)
        {
            var monthRows = group.Select((r, i) =>
            {
                r["stt"] = i + 1;
                return r;
            }).ToList();
            
            context.MonthlyGroups.Add(new MonthlyGroup
            {
                MonthLabel = $"Tháng {group.Key:D2}",
                MonthTotal = monthRows.Sum(r => (decimal)r["revenue"]),
                Rows = monthRows,
            });
        }
        
        // Formula results
        var formulaCtx = BuildFormulaContext(book);
        context.FormulaResults = await _formulaEngine
            .EvaluateAllAsync(book.BookId, formulaCtx, ct);
    }
    
    private async Task CollectS2dAsync(
        AccountingBook book, ExportContext context, CancellationToken ct)
    {
        // Get distinct products
        var products = await _unitOfWork.StockMovements
            .GetDistinctProductsAsync(book.BusinessLocationId, 
                book.Period.StartDate, book.Period.EndDate, ct);
        
        context.ProductSheets = new List<ProductSheetData>();
        
        foreach (var product in products)
        {
            var formulaCtx = BuildFormulaContext(book);
            formulaCtx.ProductId = product.ProductId;
            
            // Evaluate formulas per product
            var formulaResults = await _formulaEngine
                .EvaluateAllAsync(book.BookId, formulaCtx, ct);
            
            // Query stock movement rows per product
            var rows = await _unitOfWork.StockMovements
                .GetRowsForExportAsync(book, product.ProductId, ct);
            
            context.ProductSheets.Add(new ProductSheetData
            {
                ProductId = product.ProductId,
                ProductName = product.ProductName,
                ProductUnit = product.Unit,
                Scalars = new Dictionary<string, string>
                {
                    ["product_name"] = product.ProductName,
                    ["product_unit"] = product.Unit,
                    // Inherit common scalars
                }.MergeWith(context.Scalars),
                FormulaResults = formulaResults,
                Rows = rows,
            });
        }
    }
    
    private async Task CollectS2cAsync(
        AccountingBook book, ExportContext context, CancellationToken ct)
    {
        // Section: revenue
        var revenueRows = await _unitOfWork.Revenues
            .GetForBookExportAsync(book, ct);
        context.Sections["revenue"] = new SectionData
        {
            SectionName = "revenue",
            Rows = revenueRows,
        };
        
        // Section: cost
        var costRows = await _unitOfWork.Costs
            .GetForBookExportAsync(book, ct);
        context.Sections["cost"] = new SectionData
        {
            SectionName = "cost",
            Rows = costRows,
        };
        
        // Formulas
        var formulaCtx = BuildFormulaContext(book);
        context.FormulaResults = await _formulaEngine
            .EvaluateAllAsync(book.BookId, formulaCtx, ct);
    }
    
    private async Task CollectS2eAsync(
        AccountingBook book, ExportContext context, CancellationToken ct)
    {
        // Section: cash
        var cashRows = await _unitOfWork.GeneralLedgerEntries
            .GetCashTransactionsAsync(book, ct);
        context.Sections["cash"] = new SectionData
        {
            SectionName = "cash",
            Rows = cashRows,
        };
        
        // Section: bank
        var bankRows = await _unitOfWork.GeneralLedgerEntries
            .GetBankTransactionsAsync(book, ct);
        context.Sections["bank"] = new SectionData
        {
            SectionName = "bank",
            Rows = bankRows,
        };
        
        // Formulas
        var formulaCtx = BuildFormulaContext(book);
        context.FormulaResults = await _formulaEngine
            .EvaluateAllAsync(book.BookId, formulaCtx, ct);
    }
}
```

### 6.5 MergeProcessorFactory

```csharp
public class MergeProcessorFactory
{
    private readonly IEnumerable<IMergeProcessor> _processors;
    
    public MergeProcessorFactory(IEnumerable<IMergeProcessor> processors)
    {
        _processors = processors;
    }
    
    public IMergeProcessor GetProcessor(string format)
    {
        var processor = _processors.FirstOrDefault(
            p => p.SupportedFormat.Equals(format, StringComparison.OrdinalIgnoreCase));
        
        if (processor == null)
            throw new ExportFormatException(
                $"Unsupported export format: {format}. Supported: xlsx, docx");
        
        return processor;
    }
}
```

### 6.6 DI Registration

```csharp
// InfrastructureModule.cs
services.AddScoped<IExportService, ExportService>();
services.AddScoped<ITemplateResolver, TemplateResolver>();
services.AddScoped<IMergeProcessor, XlsxMergeProcessor>();
services.AddScoped<IMergeProcessor, DocxMergeProcessor>();
services.AddSingleton<MergeProcessorFactory>();
services.AddScoped<DataCollector>();
services.AddScoped<IFileUploader, CloudinaryFileUploader>();
```

---

## 7. Integration — Data Collector & Formula Engine

### Sequence Diagram — Export Book

```
Owner              ExportService         DataCollector      FormulaEngine      TemplateResolver     MergeProcessor      FileUploader       DB
  │                     │                     │                  │                   │                    │                  │              │
  │  POST /export       │                     │                  │                   │                    │                  │              │
  │  {format:"xlsx"}    │                     │                  │                   │                    │                  │              │
  │────────────────────►│                     │                  │                   │                    │                  │              │
  │                     │                     │                  │                   │                    │                  │              │
  │                     │  Load Book          │                  │                   │                    │                  │              │
  │                     │─────────────────────┼──────────────────┼───────────────────┼────────────────────┼──────────────────┼─────────────►│
  │                     │◄────────────────────┼──────────────────┼───────────────────┼────────────────────┼──────────────────┼──────────────│
  │                     │                     │                  │                   │                    │                  │              │
  │                     │  Resolve template   │                  │                   │                    │                  │              │
  │                     │──────────────────────────────────────────────────────────►│                    │                  │              │
  │                     │◄──────────────────────────────────────────────────────────│ Stream              │                  │              │
  │                     │                     │                  │                   │                    │                  │              │
  │                     │  Collect data       │                  │                   │                    │                  │              │
  │                     │────────────────────►│                  │                   │                    │                  │              │
  │                     │                     │  EvaluateAll     │                   │                    │                  │              │
  │                     │                     │─────────────────►│                   │                    │                  │              │
  │                     │                     │◄─────────────────│ Dict<Code,Value>  │                    │                  │              │
  │                     │                     │  Query rows      │                   │                    │                  │              │
  │                     │                     │──────────────────┼───────────────────┼────────────────────┼──────────────────┼─────────────►│
  │                     │                     │◄─────────────────┼───────────────────┼────────────────────┼──────────────────┼──────────────│
  │                     │◄────────────────────│ ExportContext     │                   │                    │                  │              │
  │                     │                     │                  │                   │                    │                  │              │
  │                     │  Merge              │                  │                   │                    │                  │              │
  │                     │───────────────────────────────────────────────────────────────────────────────►│                  │              │
  │                     │◄──────────────────────────────────────────────────────────────────────────────│ MemoryStream      │              │
  │                     │                     │                  │                   │                    │                  │              │
  │                     │  Upload             │                  │                   │                    │                  │              │
  │                     │──────────────────────────────────────────────────────────────────────────────────────────────────►│              │
  │                     │◄─────────────────────────────────────────────────────────────────────────────────────────────────│ URL           │
  │                     │                     │                  │                   │                    │                  │              │
  │                     │  INSERT Export      │                  │                   │                    │                  │              │
  │                     │─────────────────────┼──────────────────┼───────────────────┼────────────────────┼──────────────────┼─────────────►│
  │                     │                     │                  │                   │                    │                  │              │
  │  ExportResponse     │                     │                  │                   │                    │                  │              │
  │◄────────────────────│                     │                  │                   │                    │                  │              │
```

### Data flow per template

| Template | DataCollector method | Sections | MonthlyGroups | ProductSheets | Key formulas |
|----------|---------------------|----------|---------------|---------------|-------------|
| S1a | `CollectS1aAsync` | — | Yes (by month) | — | `S1A_QUARTERLY_TOTAL` |
| S2a | `CollectS2aAsync` | — | — | — | `S2A_QUARTERLY_TOTAL`, `S2A_VAT`, `S2A_PIT` |
| S2b | `CollectS2bAsync` | — | — | — | `S2B_QUARTERLY_TOTAL`, `S2B_VAT` |
| S2c | `CollectS2cAsync` | `revenue`, `cost` | — | — | `S2C_TOTAL_REVENUE`, `S2C_TOTAL_COST`, `S2C_PROFIT`, `S2C_PIT` |
| S2d | `CollectS2dAsync` | — | — | Yes (per product) | `S2D_OPENING_QTY` ... `S2D_CLOSING_VALUE` (×N products) |
| S2e | `CollectS2eAsync` | `cash`, `bank` | — | — | `S2E_CASH_*`, `S2E_BANK_*` |

---

## 8. Template File Management

### 8.1 Storage

Template files (.xlsx, .docx) lưu trong `AccountingTemplateVersions.TemplateFileUrl`.

**Storage options (chọn 1):**

| Option | URL pattern | Pros | Cons |
|--------|------------|------|------|
| **Cloudinary** | `https://res.cloudinary.com/.../s2a_v1.xlsx` | Đã có infra, CDN | Cloudinary không optimized cho office files |
| **Local/Volume** | `/templates/s2a_v1.xlsx` | Simple, fast | Không scale multi-instance |
| **Embedded resource** | `embedded://BizFlow.Api/Templates/s2a_v1.xlsx` | Zero external dependency, version cùng code | Phải deploy để update template |

**Recommend**: Giai đoạn đầu dùng **embedded resource** (template TT152 ít thay đổi). Sau upgrade lên Cloudinary nếu cần Admin upload template mới qua UI.

### 8.2 Template versioning

```
Mỗi AccountingTemplateVersion có thể có TemplateFileUrl riêng:

Template S2a:
├── v1.0 (active)  → TemplateFileUrl = ".../s2a_v1.0.xlsx"
├── v1.0 docx      → TemplateFileUrl = ".../s2a_v1.0.docx"  (?)
└── v2.0 (draft)   → TemplateFileUrl = ".../s2a_v2.0.xlsx"
```

**Quan trọng**: Hiện tại `TemplateFileUrl` chỉ lưu **1 URL**. Để support dual format, có 2 cách:

**Cách A — Thêm column:**

```sql
ALTER TABLE AccountingTemplateVersions
    ADD COLUMN TemplateFileUrlDocx VARCHAR(500) DEFAULT NULL
        COMMENT 'URL file template docx (nếu có)';
-- TemplateFileUrl giữ nguyên cho xlsx (primary format)
```

**Cách B — JSON map:**

```sql
ALTER TABLE AccountingTemplateVersions
    MODIFY COLUMN TemplateFileUrl JSON DEFAULT NULL
        COMMENT '{"xlsx": "url...", "docx": "url..."}';
```

**Recommend**: Cách A — đơn giản, backward compatible, column name rõ ràng.

### 8.3 Entity update

```csharp
public class AccountingTemplateVersion
{
    // ... existing fields ...
    
    public string? TemplateFileUrl { get; set; }      // xlsx template
    public string? TemplateFileUrlDocx { get; set; }  // docx template (optional)
}
```

---

## 9. Business Rules

| Rule | Mô tả |
|------|-------|
| **RULE-EX-01** | Export format phải là `xlsx` hoặc `docx` |
| **RULE-EX-02** | Template file phải tồn tại cho format được yêu cầu — nếu không → error `TEMPLATE_FILE_NOT_FOUND` |
| **RULE-EX-03** | Merge field không tìm thấy value → để trống cell, KHÔNG throw error (graceful) |
| **RULE-EX-04** | Formula field (`{{formula:CODE}}`) không tìm thấy → để trống + log warning |
| **RULE-EX-05** | S2d: Sheet name max 31 chars (Excel limit) — truncate product name nếu dài hơn |
| **RULE-EX-06** | S2d: Nếu không có product nào trong period → export file với 1 sheet trống + thông báo |
| **RULE-EX-07** | Export tạo snapshot (AccountingExport) — file và SummaryJson frozen, không thay đổi |
| **RULE-EX-08** | Mỗi lần export tạo 1 record riêng — không overwrite export cũ |
| **RULE-EX-09** | Export chỉ Owner có quyền (kiểm tra qua locationId ownership) |
| **RULE-EX-10** | Cell formatting (font, border, number format, alignment) từ template file được **giữ nguyên** khi merge |
| **RULE-EX-11** | Row expansion phải **shift down** các dòng bên dưới (không overwrite) |
| **RULE-EX-12** | Scalar field có thể nằm cùng dòng với text tĩnh: `"Kỳ: {{period_label}}"` → replace inline |
| **RULE-EX-13** | Date values format theo `dd/MM/yyyy` (chuẩn VN) trừ khi cell có custom number format |
| **RULE-EX-14** | Decimal values giữ nguyên precision, rely on cell number format để hiển thị |

---

## 10. API Contract (cập nhật)

### Export Book

```yaml
POST /api/v1/locations/{locationId}/accounting/books/{bookId}/export
Authorization: Bearer {owner_token}

Request:
{
  "format": "xlsx",                    # "xlsx" | "docx"
  "notes": "Xuất bổ sung lần 2"       # optional
}

Response (201 Created):
{
  "exportId": 8,
  "bookId": 15,
  "groupNumber": 2,
  "rulesetVersion": "1.0.0",
  "format": "xlsx",
  "fileUrl": "https://res.cloudinary.com/.../S2a_Q1_2026_retail.xlsx",
  "summary": {
    "totalRevenue": 625000000,
    "totalCost": 85000000,
    "totalVat": 6250000,
    "totalPit": 0,
    "rowCount": 345
  },
  "dataRowCount": 345,
  "exportedAt": "2026-04-10T09:30:00Z",
  "notes": "Xuất bổ sung lần 2"
}
```

### List Exports

```yaml
GET /api/v1/locations/{locationId}/accounting/books/{bookId}/exports
Authorization: Bearer {owner_token}

Response:
{
  "items": [
    {
      "exportId": 8,
      "format": "xlsx",
      "fileUrl": "https://...",
      "dataRowCount": 345,
      "exportedAt": "2026-04-10T09:30:00Z",
      "notes": "Xuất bổ sung lần 2"
    },
    {
      "exportId": 5,
      "format": "xlsx",
      "fileUrl": "https://...",
      "dataRowCount": 342,
      "exportedAt": "2026-04-05T14:00:00Z",
      "notes": null
    }
  ]
}
```

---

## 11. Error Codes

| Code | HTTP | Message |
|------|:----:|---------|
| `EXPORT_FORMAT_INVALID` | 400 | Format không hợp lệ. Chỉ hỗ trợ: xlsx, docx |
| `TEMPLATE_FILE_NOT_FOUND` | 400 | Không tìm thấy file template cho format yêu cầu |
| `TEMPLATE_FILE_CORRUPTED` | 500 | File template bị hỏng, không thể đọc |
| `MERGE_FIELD_PARSE_ERROR` | 500 | Không thể parse merge field trong template |
| `SHEET_DUPLICATION_FAILED` | 500 | Không thể duplicate sheet (S2d) |
| `DATA_COLLECT_FAILED` | 500 | Lỗi khi query data cho export |
| `FORMULA_EVALUATION_FAILED` | 500 | FormulaEngine trả lỗi khi tính toán |
| `FILE_UPLOAD_FAILED` | 500 | Upload file lên storage thất bại |
| `BOOK_NOT_FOUND` | 404 | Sổ kế toán không tồn tại |
| `BOOK_NO_PERMISSION` | 403 | Không có quyền export sổ này |
