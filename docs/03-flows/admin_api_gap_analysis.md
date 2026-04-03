# Phân Tích Gaps Admin API & Kế Hoạch Mở Rộng

> **Vai trò**: Solution Architect + Business Analyst
> **Ngày**: 2026-03-30
> **Scope**: Admin Accounting APIs — quản lý templates, row definitions, metadata registry

---

## 1. Gap Analysis: Admin API Hiện Tại

### 1.1 Những gì ĐÃ CÓ

Dựa trên [AdminAccountingController.cs](file:///d:/Semester-9/bizflow-project/BizFlow-BE-Service/bizflow-platform/BizFlow.Api/Controllers/Accounting/AdminAccountingController.cs):

| # | Endpoint | Chức năng |
|---|----------|-----------|
| 1 | `GET /overview` | Tổng quan templates, rulesets, formulas |
| 2 | `GET /template-versions/{id}` | Chi tiết version (FieldMappings) |
| 3 | `GET /template-versions/{id}/formulas` | Formulas linked to version |
| 4 | `POST /template-versions/{id}/clone` | Clone version → draft |
| 5 | `PATCH /template-versions/{id}` | Update metadata (label, notes) |
| 6 | `POST /template-versions/{id}/activate` | Activate version (Admin only) |
| 7 | `POST /template-versions/{id}/deactivate` | Deactivate version (Admin only) |
| 8 | `DELETE /template-versions/{id}` | Delete draft version (Admin only) |
| 9 | `PATCH /field-mappings/{id}/testing` | Update 1 field mapping |
| 10 | `GET /formulas/{id}` | Get formula detail |
| 11 | `PATCH /formulas/{id}/testing` | Update formula |
| 12 | `POST /formulas/{id}/clone` | Clone formula |
| 13 | `POST /rulesets/{id}/activate` | Activate tax ruleset |
| 14 | `POST /rulesets/{id}/deactivate` | Deactivate tax ruleset |
| 15 | `POST /testing/preview` | Preview template with real data |

### 1.2 Những gì THIẾU

> [!CAUTION]
> Hiện tại admin quản lý template bằng cách "biết trước" cấu trúc code/DB. Không có API nào giúp admin **hiểu** hệ thống cần gì — thiếu hoàn toàn "guide/reference" layer.

| # | Gap | Mức độ | Giải thích |
|---|-----|--------|------------|
| **G1** | **Không có CRUD cho `TemplateRowDefinitions`** | 🔴 Critical | Bảng mới sau refactoring — admin cần tạo/sửa/xóa row definitions cho mỗi template version |
| **G2** | **Không có MappableEntities/Fields API** | 🔴 Critical | [accounting-book-flow-v2.md](file:///d:/Semester-9/bizflow-project/BizFlow-BE-Service/docs/03-flows/accounting-book-flow-v2.md#L736-L758) mô tả CRUD cho metadata registry nhưng chưa implement trong controller |
| **G3** | **FieldMappings chỉ có PATCH** | 🟡 Major | Không có `POST` (tạo mới) và `DELETE` (xóa) — admin chỉ sửa được mapping có sẵn |
| **G4** | **Không có Reference/Guide API** | 🟡 Major | Admin không biết: RowTypes nào hợp lệ? Positions nào có? SectionTypes nào? Phải đọc code |
| **G5** | **Clone version không copy RowDefinitions** | 🟡 Major | [CloneTemplateVersionAsync](file:///d:/Semester-9/bizflow-project/BizFlow-BE-Service/bizflow-platform/BizFlow.Application/Services/AdminAccountingService.cs#L124-L165) chỉ copy FieldMappings, chưa copy RowDefinitions |
| **G6** | **Không có combined view** | 🟢 Nice-to-have | Admin muốn xem full template structure (columns + rows) trong 1 API |
| **G7** | **Không có validation guide cho FE admin** | 🟢 Nice-to-have | FE admin form cần biết constraints: required fields, max lengths, valid enums |

---

## 2. Thiết Kế Giải Pháp

### 2.1 Kiến trúc Admin API — 3 Tầng

```
┌────────────────────────────────────────────────────────────────────┐
│                     ADMIN API LAYERS                                │
│                                                                      │
│  Tầng 1: REFERENCE (Guide)                                          │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ GET /admin/accounting/reference                              │   │
│  │ → Trả tất cả valid values: RowTypes, Positions, SectionTypes │   │
│  │ → FieldTypes, SourceTypes, AggregationTypes, TaxTypes        │   │
│  │ → Admin đọc cái này trước khi tạo/sửa bất kỳ template nào  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Tầng 2: METADATA REGISTRY (Data sources)                           │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ CRUD /admin/accounting/mappable-entities                     │   │
│  │ CRUD /admin/accounting/mappable-entities/{id}/fields          │   │
│  │ → Quản lý whitelist entity + fields cho FieldMappings        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Tầng 3: TEMPLATE MANAGEMENT (Structure)                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ CRUD /admin/accounting/template-versions/{id}/field-mappings │   │
│  │ CRUD /admin/accounting/template-versions/{id}/row-definitions│   │
│  │ GET  /admin/accounting/template-versions/{id}/full-structure │   │
│  │ → Quản lý cột + dòng + xem kết hợp                          │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────┘
```

### 2.2 Reference API (Tầng 1) — "Bảng Hướng Dẫn"

> [!TIP]
> Đây là API mà admin gọi **đầu tiên** khi vào trang quản lý template. Nó trả về tất cả valid values mà admin cần biết — như một cuốn từ điển.

```yaml
GET /api/admin/accounting/reference

Response:
{
  "data": {
    "rowTypes": [
      { "value": "industry_header",  "label": "Tiêu đề ngành nghề",           "description": "Dòng tiêu đề nhóm ngành, xuất hiện đầu mỗi group" },
      { "value": "data_placeholder", "label": "Vị trí data rows",             "description": "Đánh dấu nơi data rows sẽ được chèn vào" },
      { "value": "subtotal",         "label": "Tổng cộng nhóm",               "description": "Dòng tổng per group/section" },
      { "value": "tax_line",         "label": "Dòng thuế",                    "description": "Thuế GTGT/TNCN, kèm TaxType" },
      { "value": "grand_total",      "label": "Tổng cuối sổ",                "description": "Dòng tổng cuối cùng của sổ" },
      { "value": "section_header",   "label": "Tiêu đề section",             "description": "Dùng cho S2c (DT/CP), S2e (Cash/Bank)" },
      { "value": "section_subtotal", "label": "Tổng cộng section",           "description": "Tổng per section (revenue/cost)" },
      { "value": "balance_row",      "label": "Dòng số dư",                  "description": "Tồn đầu kỳ / cuối kỳ (S2d, S2e)" },
      { "value": "monthly_total",    "label": "Cộng tháng",                  "description": "Tổng theo tháng (S1a)" },
      { "value": "quarterly_total",  "label": "Cộng quý",                    "description": "Tổng theo quý" },
      { "value": "profit_row",       "label": "Chênh lệch DT-CP",           "description": "S2c: Doanh thu - Chi phí" }
    ],

    "positions": [
      { "value": "per_group",     "label": "Mỗi nhóm",    "description": "Lặp cho mỗi group (ngành/product/section)" },
      { "value": "per_section",   "label": "Mỗi section",  "description": "Lặp cho mỗi section (revenue/cost, cash/bank)" },
      { "value": "start_of_book", "label": "Đầu sổ",      "description": "Chỉ xuất hiện 1 lần đầu sổ" },
      { "value": "end_of_book",   "label": "Cuối sổ",     "description": "Chỉ xuất hiện 1 lần cuối sổ" }
    ],

    "sectionTypes": [
      { "value": "industry_group", "label": "Nhóm ngành nghề",   "description": "Group by BusinessTypeId (S2a, S2b)" },
      { "value": "revenue_cost",   "label": "Doanh thu & Chi phí","description": "2 sections: revenue, cost (S2c)" },
      { "value": "cash_bank",      "label": "Tiền mặt & Ngân hàng","description": "2 sections: cash, bank (S2e)" },
      { "value": "per_product",    "label": "Theo sản phẩm",     "description": "Group by ProductId (S2d)" }
    ],

    "fieldTypes": [
      { "value": "auto_increment", "label": "STT tự tăng" },
      { "value": "date",           "label": "Ngày tháng" },
      { "value": "text",           "label": "Văn bản" },
      { "value": "decimal",        "label": "Số thập phân" }
    ],

    "sourceTypes": [
      { "value": "query",   "label": "Truy vấn từ DB",  "description": "Lấy data từ MappableEntity/Field" },
      { "value": "formula", "label": "Công thức",        "description": "Tính từ FormulaDefinition" },
      { "value": "static",  "label": "Giá trị tĩnh",    "description": "Giá trị cố định" },
      { "value": "auto",    "label": "Tự động",          "description": "STT, timestamp..." }
    ],

    "taxTypes": [
      { "value": "VAT", "label": "Thuế GTGT" },
      { "value": "PIT", "label": "Thuế TNCN" }
    ],

    "labelPlaceholders": [
      { "placeholder": "{groupIndex}",       "description": "Số thứ tự nhóm (1, 2, 3...)" },
      { "placeholder": "{businessTypeName}", "description": "Tên ngành nghề" },
      { "placeholder": "{monthName}",        "description": "Tên tháng (Tháng 01, Tháng 02...)" },
      { "placeholder": "{quarterName}",      "description": "Tên quý (Quý I, Quý II...)" }
    ]
  }
}
```

### 2.3 Metadata Registry CRUD (Tầng 2)

| # | Method | Endpoint | Mô tả | Auth |
|---|--------|----------|-------|------|
| 1 | `GET` | `/mappable-entities` | List tất cả entities (có filter `?active=true`) | Admin + Consultant |
| 2 | `GET` | `/mappable-entities/{id}` | Chi tiết entity + fields | Admin + Consultant |
| 3 | `POST` | `/mappable-entities` | Tạo entity mới | Admin only |
| 4 | `PATCH` | `/mappable-entities/{id}` | Update entity (displayName, description, deactivate) | Admin only |
| 5 | `GET` | `/mappable-entities/{entityId}/fields` | List fields của entity | Admin + Consultant |
| 6 | `POST` | `/mappable-entities/{entityId}/fields` | Tạo field mới | Admin only |
| 7 | `PATCH` | `/mappable-fields/{fieldId}` | Update field | Admin only |

### 2.4 Template Management CRUD Mở Rộng (Tầng 3)

#### FieldMappings — Bổ sung POST + DELETE

| # | Method | Endpoint hiện tại? | Cần bổ sung |
|---|--------|:------------------:|-------------|
| 1 | `GET` | Có (trong version detail) | ✅ Đã có |
| 2 | `POST` | ❌ Thiếu | `POST /template-versions/{versionId}/field-mappings` — Tạo mapping mới cho draft version |
| 3 | `PATCH` | ✅ Có | `PATCH /field-mappings/{mappingId}/testing` — Đã có |
| 4 | `DELETE` | ❌ Thiếu | `DELETE /field-mappings/{mappingId}` — Xóa mapping (chỉ draft version) |

#### RowDefinitions — CRUD hoàn toàn mới

| # | Method | Endpoint | Mô tả |
|---|--------|----------|-------|
| 1 | `GET` | `/template-versions/{versionId}/row-definitions` | List tất cả row defs cho version |
| 2 | `POST` | `/template-versions/{versionId}/row-definitions` | Tạo row def mới |
| 3 | `PATCH` | `/row-definitions/{rowDefId}` | Update row def |
| 4 | `DELETE` | `/row-definitions/{rowDefId}` | Xóa row def (chỉ draft version) |

#### Combined View — Full Template Structure

| # | Method | Endpoint | Mô tả |
|---|--------|----------|-------|
| 1 | `GET` | `/template-versions/{versionId}/full-structure` | Trả columns (FieldMappings) + row structure (RowDefinitions) kết hợp |

```yaml
GET /api/admin/accounting/template-versions/{versionId}/full-structure

Response:
{
  "data": {
    "templateVersionId": 2,
    "templateCode": "S2a",
    "versionLabel": "v1.0",
    "isActive": true,

    "columns": [
      { "mappingId": 5, "fieldCode": "stt",       "fieldLabel": "STT",        "fieldType": "auto_increment", "sourceType": "auto",  "sortOrder": 1 },
      { "mappingId": 6, "fieldCode": "so_hieu",   "fieldLabel": "Số hiệu",   "fieldType": "text",           "sourceType": "query", "sortOrder": 2, "sourceEntity": "Đơn hàng", "sourceField": "Mã đơn hàng" },
      { "mappingId": 7, "fieldCode": "ngay_thang", "fieldLabel": "Ngày tháng","fieldType": "date",           "sourceType": "query", "sortOrder": 3 },
      { "mappingId": 8, "fieldCode": "dien_giai", "fieldLabel": "Diễn giải",  "fieldType": "text",           "sourceType": "query", "sortOrder": 4 },
      { "mappingId": 9, "fieldCode": "so_tien",   "fieldLabel": "Số tiền",    "fieldType": "decimal",        "sourceType": "query", "sortOrder": 5 }
    ],

    "formulaColumns": [
      { "mappingId": 10, "fieldCode": "cong_quy",  "fieldLabel": "Cộng quý",           "formulaCode": "S2A_QUARTERLY_TOTAL" },
      { "mappingId": 11, "fieldCode": "thue_gtgt", "fieldLabel": "Thuế GTGT phải nộp", "formulaCode": "S2A_VAT" },
      { "mappingId": 12, "fieldCode": "thue_tncn", "fieldLabel": "Thuế TNCN phải nộp", "formulaCode": "S2A_PIT" }
    ],

    "rowStructure": [
      { "rowDefId": 1, "rowType": "industry_header",  "rowLabel": "{groupIndex}. {businessTypeName}", "position": "per_group",   "sortOrder": 1, "sectionType": "industry_group", "groupByField": "BusinessTypeId" },
      { "rowDefId": 2, "rowType": "data_placeholder",  "rowLabel": null,                               "position": "per_group",   "sortOrder": 2, "sectionType": "industry_group" },
      { "rowDefId": 3, "rowType": "subtotal",          "rowLabel": "Tổng cộng ({groupIndex})",         "position": "per_group",   "sortOrder": 3 },
      { "rowDefId": 4, "rowType": "tax_line",          "rowLabel": "Thuế GTGT",                        "position": "per_group",   "sortOrder": 4, "taxType": "VAT" },
      { "rowDefId": 5, "rowType": "tax_line",          "rowLabel": "Thuế TNCN",                        "position": "per_group",   "sortOrder": 5, "taxType": "PIT" },
      { "rowDefId": 6, "rowType": "grand_total",       "rowLabel": "Tổng số thuế GTGT phải nộp",       "position": "end_of_book", "sortOrder": 1, "taxType": "VAT" },
      { "rowDefId": 7, "rowType": "grand_total",       "rowLabel": "Tổng số thuế TNCN phải nộp",       "position": "end_of_book", "sortOrder": 2, "taxType": "PIT" }
    ],

    "renderPreview": "Nhóm ngành → [header → data rows → subtotal → VAT → PIT] × N → grand_total VAT → grand_total PIT"
  }
}
```

> [!TIP]
> **`renderPreview`** là một chuỗi mô tả bằng lời cấu trúc rendering — giúp admin hiểu nhanh sổ sẽ trông như thế nào mà không cần preview với data thật.

---

## 3. Fix Gap G5: Clone phải copy RowDefinitions

Trong [AdminAccountingService.CloneTemplateVersionAsync](file:///d:/Semester-9/bizflow-project/BizFlow-BE-Service/bizflow-platform/BizFlow.Application/Services/AdminAccountingService.cs#L124-L165), cần thêm:

```csharp
// Hiện tại chỉ copy FieldMappings:
FieldMappings = source.FieldMappings.Select(m => new TemplateFieldMapping { ... }).ToList()

// Cần thêm copy RowDefinitions:
RowDefinitions = source.RowDefinitions.Select(r => new TemplateRowDefinition
{
    RowType = r.RowType,
    RowLabel = r.RowLabel,
    Position = r.Position,
    SortOrder = r.SortOrder,
    GroupByField = r.GroupByField,
    SectionType = r.SectionType,
    VisibleFieldCodes = r.VisibleFieldCodes,
    FormulaId = r.FormulaId,
    TaxType = r.TaxType,
    CreatedAt = DateTime.UtcNow
}).ToList()
```

---

## 4. FE Integration Doc — Outline

Sau khi implement xong Phase 1 (sections/rows refactoring), tạo doc cho FE team:

### Cấu trúc FE Integration Doc:

```markdown
# Accounting Book API — FE Integration Guide

## 1. Tổng Quan
- Giải thích 3 API chính cho Owner: /books, /books/{id}/rows, /books/{id}/sections
- Flow: Sections trước → Rows sau → Client assemble

## 2. API: GET /books/{id}/sections
- Purpose: Lấy cấu trúc sổ + formula values
- Response schema + ví dụ S2a
- Giải thích lineType enum
- Giải thích data_placeholder + dataFilter

## 3. API: GET /books/{id}/rows
- Purpose: Lấy data rows paginated
- Response schema + ví dụ
- Cursor-based pagination guide
- businessTypeId trên mỗi row

## 4. Client Assembly Guide
- Pseudocode: sections + rows → final rendered view
- Mapping businessTypeId → đúng section
- Rendering theo lineType

## 5. Styling Guide by lineType
- data → normal row
- industry_header → bold, span full width
- subtotal → bold, border-top
- tax_line → italic, indented
- grand_total → bold, border-top + bottom, background

## 6. Ví Dụ Hoàn Chỉnh
- S2a với 2 ngành, 5 data rows → full JSON + rendered table
```

---

## 5. Kế Hoạch Triển Khai Tổng Thể

### Sprint Map

```
┌─────────────────────────────────────────────────────────────┐
│  SPRINT HIỆN TẠI: Sections/Rows Refactoring (Phase 1)      │
│  ────────────────────────────────────────────────────────── │
│  ✅ Implementation Plan đã có                               │
│  → Migration + Entity + Rendering fix + API /sections       │
│  → Output: GET /rows (fixed) + GET /sections (new)          │
├─────────────────────────────────────────────────────────────┤
│  SPRINT TIẾP: Admin Template Management (Phase 2)          │
│  ────────────────────────────────────────────────────────── │
│  Part A: Reference API + MappableEntities CRUD             │
│  Part B: FieldMappings full CRUD + RowDefinitions CRUD     │
│  Part C: Full-structure view + Clone fix                    │
│  → Output: Admin có thể quản lý hoàn toàn template          │
├─────────────────────────────────────────────────────────────┤
│  SPRINT SAU: FE Integration + Testing                      │
│  ────────────────────────────────────────────────────────── │
│  Part A: FE Integration Doc                                 │
│  Part B: Admin Preview update (dùng RenderSections)         │
│  Part C: E2E testing cho S2a, S2b, S2c                      │
└─────────────────────────────────────────────────────────────┘
```

### Sprint tiếp (Admin Management) — Task Breakdown

#### Part A: Reference + Metadata Registry (4 tasks)

| Task | File/Layer | Mô tả |
|------|-----------|-------|
| A1 | Controller | Thêm `GET /reference` endpoint |
| A2 | Service | Implement reference data (static/config) |
| A3 | Controller + Service | CRUD `/mappable-entities` (4 endpoints) |
| A4 | Controller + Service | CRUD `/mappable-entities/{id}/fields` (3 endpoints) |

#### Part B: Template CRUD Mở Rộng (5 tasks)

| Task | File/Layer | Mô tả |
|------|-----------|-------|
| B1 | Repository | Thêm CRUD methods cho TemplateRowDefinition |
| B2 | Controller + Service | `POST /template-versions/{id}/field-mappings` |
| B3 | Controller + Service | `DELETE /field-mappings/{id}` |
| B4 | Controller + Service | CRUD `/template-versions/{id}/row-definitions` (4 endpoints) |
| B5 | Controller + Service | `GET /template-versions/{id}/full-structure` |

#### Part C: Integration (3 tasks)

| Task | File/Layer | Mô tả |
|------|-----------|-------|
| C1 | Service | Fix Clone — copy RowDefinitions |
| C2 | Service | Update Preview — dùng RenderSectionsAsync |
| C3 | Doc | FE Integration Doc |

---

## 6. Tổng Kết

> [!IMPORTANT]
> **Bạn đúng — thiết kế hiện tại đang thiếu sót.** Cụ thể:
>
> 1. Admin **không có cách** quản lý `TemplateRowDefinitions` (bảng mới) qua API
> 2. Admin **không có reference data** để biết giá trị nào hợp lệ khi tạo/sửa template
> 3. `MappableEntities/Fields` API đã thiết kế trong doc nhưng **chưa implement**
> 4. `FieldMappings` CRUD **chưa hoàn chỉnh** (thiếu POST + DELETE)
> 5. Clone version **không copy** RowDefinitions (sẽ lỗi sau khi thêm bảng mới)

Kế hoạch phân thành 3 sprint rõ ràng. Sprint hiện tại (sections/rows) là nền tảng — sprint tiếp (admin management) xây trên đó to build a complete admin experience.
