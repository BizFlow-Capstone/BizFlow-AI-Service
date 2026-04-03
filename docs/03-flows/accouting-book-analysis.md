# Phân Tích Lỗi Thiết Kế API GetBookRows — Mẫu S2a (v2)

> **Vai trò**: Solution Architect + Business Analyst
> **Ngày**: 2026-03-30
> **Scope**: API `GET {bookId}/rows` và cách nó thể hiện dữ liệu theo template S2a
> **Trạng thái**: v2 — đã cập nhật sau discussion

---

## 1. Tóm Tắt Vấn Đề

API `GET {bookId}/rows` cho mẫu **S2a** đang trả về `thue_gtgt`, `thue_tncn` **lặp lại trên MỌI dòng revenue**, trong khi theo mẫu S2a chính thức (TT152), các dòng thuế này **chỉ xuất hiện 1 lần ở cuối sổ** (hoặc cuối mỗi nhóm ngành).

> [!IMPORTANT]
> **Root cause**: Lỗi nằm ở **rendering pipeline** ([BookRenderingService.cs](file:///d:/Semester-9/bizflow-project/BizFlow-BE-Service/bizflow-platform/BizFlow.Infrastructure/Services/BookRendering/BookRenderingService.cs#L58-L75)), KHÔNG phải data seed (migration). Code duyệt ALL FieldMappings (bao gồm formula) cho MỖI source row — gán formula values vào mỗi data row thay vì tạo separate summary rows.

---

## 2. Root Cause — Rendering Pipeline

### Code lỗi

```csharp
// BookRenderingService.cs L58-75
foreach (var sourceRow in sourceRows.Items)
{
    var row = new Dictionary<string, object?>();
    foreach (var mapping in version.FieldMappings.OrderBy(m => m.SortOrder))
    {
        row[mapping.FieldCode] = mapping.SourceType switch
        {
            "auto"    => sttOffset + (++rowIndex),
            "query"   => ExtractFieldValue(sourceRow, mapping),
            "static"  => null,
            "formula" => formulaValuesByFieldCode.GetValueOrDefault(mapping.FieldCode),
            //          ⚠️ Formula values được gán cho MỌI row — SAI
            _ => null
        };
    }
    rows.Add(row);
}
```

### Tại sao seed data KHÔNG sai

[061_seed_template_field_mappings.sql](file:///d:/Semester-9/bizflow-project/BizFlow-BE-Service/database/migrations/061_seed_template_field_mappings.sql#L17-L31) đã phân biệt đúng:
- `SourceType = "query"` + `SortOrder 1-5` → dòng data
- `SourceType = "formula"` + `SortOrder 10-12` → dòng tổng hợp/thuế

**Nhưng rendering code không phân biệt chúng.**

---

## 3. Gaps Kiến Trúc

| # | Gap | Mô tả |
|---|-----|-------|
| 1 | **Không có `lineType`** | Không phân biệt data row vs summary row vs tax row |
| 2 | **Không có Row Schema** | Hệ thống chỉ biết template có **CỘT** gì, không biết **DÒNG** gì |
| 3 | **Không có grouping logic** | S2a cần group theo ngành, pipeline render "flat" |
| 4 | **Không có section concept** | S2c cần Revenue/Cost sections, S2e cần Cash/Bank sections |

### Row types cần cho từng template:

| Template | Các loại dòng cần thiết |
|----------|------------------------|
| **S1a** | `data`, `monthly_total`, `quarterly_total` |
| **S2a** | `industry_header`, `data`, `subtotal`, `tax_line` (VAT+PIT), `grand_total` |
| **S2b** | `industry_header`, `data`, `subtotal`, `tax_line` (chỉ VAT), `grand_total` |
| **S2c** | `section_header` (DT/CP), `data`, `section_subtotal`, `profit_row`, `tax_line` |
| **S2d** | `balance_opening`, `data`, `balance_closing` (per product) |
| **S2e** | `section_header` (cash/bank), `data`, `balance_opening`, `balance_closing` |

---

## 4. Quyết Định Đã Chốt (Discussion Outcomes)

Sau khi discuss, chốt các điểm sau:

| Quyết định | Kết luận |
|-----------|----------|
| **1 book S2a chứa TẤT CẢ ngành?** | ✅ Đúng — 1 book chứa tất cả ngành, grouping xảy ra trong rendering |
| **Pagination + grouping** | Tách thành **2 API riêng** để tránh phức tạp pagination |
| **Align revenue-centric plan** | ✅ Đúng — dùng `lineType` giống plan, mở rộng thêm |

---

## 5. Giải Pháp: Tách 2 API + TemplateRowDefinitions

### 5.1 Thiết kế tổng quan

```
┌────────────────────────────────────────────────────────────┐
│                    CLIENT RENDERING FLOW                    │
│                                                              │
│  1. GET /sections  ──→  Cấu trúc sổ + formula values       │
│     (1 call, nhẹ)       [headers, subtotals, tax, totals]   │
│                                                              │
│  2. GET /rows      ──→  Data rows thuần (paginated)         │
│     (cursor-based)      [flat revenue/cost/GL rows]         │
│                                                              │
│  3. Client tự ASSEMBLE:                                      │
│     sections structure + data rows → render đúng mẫu TT152  │
│                                                              │
│  Ví dụ S2a:                                                  │
│  ┌─ industry_header "1. Bán lẻ"  ← từ /sections            │
│  │   data row 1                   ← từ /rows                │
│  │   data row 2                   ← từ /rows                │
│  │   subtotal                     ← từ /sections            │
│  │   tax_line (VAT)               ← từ /sections            │
│  │   tax_line (PIT)               ← từ /sections            │
│  ├─ industry_header "2. Dịch vụ"  ← từ /sections            │
│  │   data row 3                   ← từ /rows                │
│  │   subtotal                     ← từ /sections            │
│  │   tax_line (VAT)               ← từ /sections            │
│  │   tax_line (PIT)               ← từ /sections            │
│  ├─ grand_total (VAT)             ← từ /sections            │
│  └─ grand_total (PIT)             ← từ /sections            │
└────────────────────────────────────────────────────────────┘
```

### 5.2 API 1: `GET /rows` — Data Rows (paginated)

```yaml
GET /api/locations/{locationId}/accounting/books/{bookId}/rows?cursor={cursor}&batchSize=200

Response:
{
  "data": {
    "rows": [
      {
        "lineType": "data",
        "businessTypeId": "bt-001",
        "stt": 1,
        "so_hieu": "ORD-20260115-001",
        "ngay_thang": "2026-01-15",
        "dien_giai": "Bán Xi măng 50 bao",
        "so_tien": 4750000
      },
      {
        "lineType": "data",
        "businessTypeId": "bt-001",
        "stt": 2,
        "so_hieu": "ORD-20260120-003",
        "ngay_thang": "2026-01-20",
        "dien_giai": "Bán Cát 200kg",
        "so_tien": 600000
      },
      {
        "lineType": "data",
        "businessTypeId": "bt-002",
        "stt": 3,
        "so_hieu": "ORD-20260125-005",
        "ngay_thang": "2026-01-25",
        "dien_giai": "Dịch vụ sửa chữa",
        "so_tien": 2000000
      }
    ],
    "hasMore": false,
    "nextCursor": null,
    "loadedCount": 3,
    "totalEstimated": 3
  }
}
```

**Đặc điểm:**
- Chỉ trả **flat data rows** (revenue/cost/GL...)
- Mỗi row có `businessTypeId` để client biết thuộc nhóm ngành nào
- Cursor-based pagination hoạt động bình thường — không cần lo group context
- `lineType` luôn là `"data"`

### 5.3 API 2: `GET /sections` — Cấu trúc sổ + Formula Values

```yaml
GET /api/locations/{locationId}/accounting/books/{bookId}/sections

Response:
{
  "data": {
    "templateCode": "S2a",
    "templateName": "Sổ doanh thu bán hàng hóa, dịch vụ (Cách 1)",
    
    "columns": [
      { "fieldCode": "stt",       "label": "STT",                  "fieldType": "auto_increment" },
      { "fieldCode": "so_hieu",   "label": "Chứng từ - Số hiệu",  "fieldType": "text" },
      { "fieldCode": "ngay_thang","label": "Chứng từ - Ngày tháng","fieldType": "date" },
      { "fieldCode": "dien_giai", "label": "Diễn giải",            "fieldType": "text" },
      { "fieldCode": "so_tien",   "label": "Số tiền (1)",          "fieldType": "decimal" }
    ],

    "sections": [
      {
        "sectionType": "industry_group",
        "businessTypeId": "bt-001",
        "businessTypeName": "Bán lẻ vật liệu xây dựng",
        "groupIndex": 1,
        "rows": [
          {
            "lineType": "industry_header",
            "dien_giai": "1. Bán lẻ vật liệu xây dựng"
          },
          {
            "lineType": "data_placeholder",
            "dataFilter": { "businessTypeId": "bt-001" },
            "description": "Client insert /rows data where businessTypeId = bt-001 here"
          },
          {
            "lineType": "subtotal",
            "dien_giai": "Tổng cộng (1)",
            "so_tien": 500000000
          },
          {
            "lineType": "tax_line",
            "dien_giai": "Thuế GTGT phải nộp (1%)",
            "so_tien": 5000000,
            "metadata": { "taxType": "VAT", "rate": 0.01, "source": "DEFAULT" }
          },
          {
            "lineType": "tax_line",
            "dien_giai": "Thuế TNCN phải nộp (0.5%)",
            "so_tien": 0,
            "metadata": { "taxType": "PIT", "rate": 0.005, "source": "DEFAULT" }
          }
        ]
      },
      {
        "sectionType": "industry_group",
        "businessTypeId": "bt-002",
        "businessTypeName": "Dịch vụ",
        "groupIndex": 2,
        "rows": [
          {
            "lineType": "industry_header",
            "dien_giai": "2. Dịch vụ"
          },
          {
            "lineType": "data_placeholder",
            "dataFilter": { "businessTypeId": "bt-002" }
          },
          {
            "lineType": "subtotal",
            "dien_giai": "Tổng cộng (2)",
            "so_tien": 350000000
          },
          {
            "lineType": "tax_line",
            "dien_giai": "Thuế GTGT phải nộp (3%)",
            "so_tien": 10500000,
            "metadata": { "taxType": "VAT", "rate": 0.03, "source": "OVERRIDE" }
          },
          {
            "lineType": "tax_line",
            "dien_giai": "Thuế TNCN phải nộp (2%)",
            "so_tien": 7000000,
            "metadata": { "taxType": "PIT", "rate": 0.02, "source": "OVERRIDE" }
          }
        ]
      }
    ],

    "footerRows": [
      {
        "lineType": "grand_total",
        "dien_giai": "Tổng số thuế GTGT phải nộp",
        "so_tien": 15500000
      },
      {
        "lineType": "grand_total",
        "dien_giai": "Tổng số thuế TNCN phải nộp",
        "so_tien": 7000000
      }
    ]
  }
}
```

**Đặc điểm:**
- Trả **cấu trúc hoàn chỉnh** của sổ: columns, sections, footers
- Mỗi section chứa: header + `data_placeholder` (chỉ cho client biết filter data ở đâu) + subtotal + tax
- Formula values đã tính sẵn
- **Không pagination** — lightweight, 1 call
- `data_placeholder` chứa `dataFilter` để client biết insert data rows nào vào vị trí đó

### 5.4 Client Assembly Pseudocode

```javascript
// 1. Fetch sections (structure + formulas)
const sections = await fetch(`/books/${bookId}/sections`);

// 2. Fetch all data rows (paginated)
let allRows = [];
let cursor = null;
do {
  const batch = await fetch(`/books/${bookId}/rows?cursor=${cursor}`);
  allRows.push(...batch.rows);
  cursor = batch.nextCursor;
} while (batch.hasMore);

// 3. Assemble into final view
const finalRows = [];
for (const section of sections.sections) {
  for (const sectionRow of section.rows) {
    if (sectionRow.lineType === 'data_placeholder') {
      // Insert matching data rows here
      const matchingRows = allRows.filter(r => 
        r.businessTypeId === sectionRow.dataFilter.businessTypeId
      );
      finalRows.push(...matchingRows);
    } else {
      finalRows.push(sectionRow);
    }
  }
}
// Append footer
finalRows.push(...sections.footerRows);
```

---

## 6. Schema: TemplateRowDefinitions

Bảng mới (data-driven, tuân thủ DD-04) — mỗi template version tự định nghĩa row types:

```sql
CREATE TABLE TemplateRowDefinitions (
    RowDefId INT AUTO_INCREMENT PRIMARY KEY,
    TemplateVersionId INT NOT NULL,
    
    -- Row identity
    RowType VARCHAR(30) NOT NULL 
        COMMENT 'industry_header | data | data_placeholder | subtotal | tax_line | grand_total | section_header | balance_opening | balance_closing | monthly_total | quarterly_total | profit_row',
    RowLabel VARCHAR(200) DEFAULT NULL 
        COMMENT 'Label template, hỗ trợ placeholder: "{businessTypeName}", "Tổng cộng ({groupIndex})"',
    
    -- Positioning
    Position VARCHAR(20) NOT NULL DEFAULT 'per_group'
        COMMENT 'per_group | per_section | end_of_book | start_of_book',
    SortOrder INT NOT NULL DEFAULT 0,
    
    -- Grouping/Section
    GroupByField VARCHAR(50) DEFAULT NULL
        COMMENT 'Field để group: BusinessTypeId (S2a/S2b), Section (S2c/S2e), ProductId (S2d)',
    SectionType VARCHAR(30) DEFAULT NULL
        COMMENT 'Phân loại section: industry_group | revenue_cost | cash_bank | per_product',
    
    -- Data binding
    VisibleFieldCodes JSON DEFAULT NULL
        COMMENT 'Cột hiển thị cho row này: ["dien_giai","so_tien"]',
    FormulaId BIGINT DEFAULT NULL,
    
    -- Tax metadata (cho tax_line rows)
    TaxType VARCHAR(10) DEFAULT NULL COMMENT 'VAT | PIT',
    
    CONSTRAINT fk_rowdef_version FOREIGN KEY (TemplateVersionId) 
        REFERENCES AccountingTemplateVersions(TemplateVersionId),
    INDEX idx_rowdef_version (TemplateVersionId)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

### Seed cho S2a:

```sql
INSERT INTO TemplateRowDefinitions 
(TemplateVersionId, RowType, RowLabel, Position, SortOrder, GroupByField, SectionType, TaxType) VALUES
-- Per industry group
(2, 'industry_header',  '{groupIndex}. {businessTypeName}', 'per_group',   1, 'BusinessTypeId', 'industry_group', NULL),
(2, 'data_placeholder', NULL,                                'per_group',   2, 'BusinessTypeId', 'industry_group', NULL),
(2, 'subtotal',         'Tổng cộng ({groupIndex})',          'per_group',   3, 'BusinessTypeId', 'industry_group', NULL),
(2, 'tax_line',         'Thuế GTGT phải nộp',               'per_group',   4, 'BusinessTypeId', 'industry_group', 'VAT'),
(2, 'tax_line',         'Thuế TNCN phải nộp',               'per_group',   5, 'BusinessTypeId', 'industry_group', 'PIT'),
-- End of book
(2, 'grand_total',      'Tổng số thuế GTGT phải nộp',       'end_of_book', 1, NULL, NULL, 'VAT'),
(2, 'grand_total',      'Tổng số thuế TNCN phải nộp',       'end_of_book', 2, NULL, NULL, 'PIT');
```

### Seed cho S2c (ví dụ khác — different structure):

```sql
INSERT INTO TemplateRowDefinitions 
(TemplateVersionId, RowType, RowLabel, Position, SortOrder, GroupByField, SectionType) VALUES
-- Revenue section
(4, 'section_header',   'I. DOANH THU',           'per_section', 1, 'Section', 'revenue_cost'),
(4, 'data_placeholder', NULL,                       'per_section', 2, 'Section', 'revenue_cost'),
(4, 'section_subtotal', 'Tổng doanh thu',          'per_section', 3, 'Section', 'revenue_cost'),
-- Cost section  
(4, 'section_header',   'II. CHI PHÍ HỢP LÝ',    'per_section', 4, 'Section', 'revenue_cost'),
(4, 'data_placeholder', NULL,                       'per_section', 5, 'Section', 'revenue_cost'),
(4, 'section_subtotal', 'Tổng chi phí hợp lý',    'per_section', 6, 'Section', 'revenue_cost'),
-- Footer
(4, 'profit_row',       'III. CHÊNH LỆCH (DT-CP)','end_of_book', 1, NULL, NULL),
(4, 'tax_line',         'Thuế TNCN phải nộp',      'end_of_book', 2, NULL, NULL);
```

> [!TIP]
> **Cùng 1 bảng, khác data** → mỗi template define row structure riêng mà không cần sửa code. Khi thêm template mới, chỉ cần INSERT rows mới vào `TemplateRowDefinitions`.

---

## 7. Tác Động Lên Code Hiện Tại

### 7.1 Cần thay đổi

| Component | Thay đổi |
|-----------|----------|
| **AccountingBookController** | Thêm endpoint `GET /sections` |
| **IAccountingBookService** | Thêm method `GetBookSectionsAsync()` |
| **AccountingBookService** | Implement `GetBookSectionsAsync()` — tổ hợp sections + formulas |
| **BookRenderingService** | Sửa `RenderRowsAsync()` — chỉ trả data rows, thêm `businessTypeId` |
| **BookRenderingService** | Thêm `RenderSectionsAsync()` — tính formula values, build sections |
| **Migration mới** | Tạo bảng `TemplateRowDefinitions`, seed data cho 6 templates |
| **DTO mới** | `BookSectionsResponse`, `SectionDto`, `SectionRowDto` |

### 7.2 Không cần thay đổi

| Component | Lý do |
|-----------|-------|
| Migration 059-062 | Data đúng, giữ nguyên |
| `TemplateFieldMappings` | Vẫn dùng cho column definitions |
| `FormulaDefinitions` | Vẫn dùng cho formula evaluation |
| `GET /summary` | Vẫn hoạt động — KPI summary |
| `GET /rows` (signature) | Giữ nguyên signature, chỉ sửa nội dung response |

---

## 8. Tổng Kết

```
TRƯỚC (lỗi):
  GET /rows → [{ stt, so_hieu, ngay_thang, dien_giai, so_tien, 
                  cong_quy: 500M, thue_gtgt: 5M, thue_tncn: 0  ← LẶP MỌI DÒNG
               }, ...]

SAU (fix):
  GET /sections → { sections: [{header, placeholder, subtotal, tax}], footerRows: [...] }
  GET /rows     → [{ lineType: "data", businessTypeId, stt, so_hieu, ... }]   ← CHỈ DATA
  
  Client assemble → Render đúng mẫu TT152
```

> [!IMPORTANT]
> Hướng đi này giải quyết triệt để cả 4 gaps kiến trúc, hỗ trợ tất cả 6 templates với cùng 1 kiến trúc data-driven, và tận dụng được toàn bộ infrastructure hiện có (formulas, mappings, metadata registry).
