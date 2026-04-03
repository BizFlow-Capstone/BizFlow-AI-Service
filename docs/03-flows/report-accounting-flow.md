# Report & Accounting Flow Documentation

> **Mục đích**: Document chi tiết flow báo cáo, kế toán, và tuân thủ Thông tư 152/2025/TT-BTC cho BizFlow Platform.
> Tài liệu này là **index** — chi tiết từng tính năng nằm trong các file con bên dưới.

---

## Mục lục

1. [Tổng quan](#1-tổng-quan)
2. [Quyết định thiết kế](#2-quyết-định-thiết-kế)
3. [Tables Overview](#3-tables-overview)
4. [Sub-documents](#4-sub-documents)

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
│  │  Orders ──► Revenues (doanh thu) ──┐                            │  │
│  │  Imports ──► Costs (chi phí)    ───┼──► GeneralLedgerEntries    │  │
│  │  Manual GL (bút toán tự do)    ────┘    (sổ cái)               │  │
│  │                                                                 │  │
│  │  Orders/Imports ──► StockMovements (nhật ký kho + giá trị)     │  │
│  │                   + TaxPayments (thuế đã nộp)                   │  │
│  └─────────────────────────┬───────────────────────────────────────┘  │
│                            │                                          │
│  ┌─────────────────────────▼───────────────────────────────────────┐  │
│  │  RULE ENGINE (independent module, versioned)                    │  │
│  │                                                                 │  │
│  │  TaxRulesets ── TaxGroupRules ── IndustryTaxRates               │  │
│  │  → Input: DT lũy kế    → Output: Nhóm + Thuế suất + Mẫu sổ   │  │
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
│  └─────────────────────────┬───────────────────────────────────────┘  │
│                            │                                          │
│  ┌─────────────────────────▼───────────────────────────────────────┐  │
│  │  FORMULA ENGINE (computed cells)                                │  │
│  │                                                                 │  │
│  │  FormulaDefinitions (ExpressionJson AST) ──► FormulaResults     │  │
│  │  → Evaluate: AGGREGATE, CELL_REF, TAX_RATE, WEIGHTED_AVG       │  │
│  │  → Cache: IsStale invalidation, lazy re-compute                 │  │
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
    │          "ORD-100: Bán hàng (ghi nợ Anh Ba)"            │
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

## 3. Tables Overview

| # | Table | Mục đích | Managed by | Chi tiết tại |
|---|-------|----------|------------|-------------|
| 1 | `Costs` | Chi phí (auto từ Import + Owner tự khai) | System + Owner | [cost-gl-flow-v2.md](cost-gl-flow-v2.md) |
| 2 | `Revenues` | Doanh thu (auto từ Order + Owner tự khai) | System + Owner | [cost-gl-flow-v2.md](cost-gl-flow-v2.md) |
| 3 | `StockMovements` | Nhật ký biến động kho (nhập/xuất/giá trị) | System (auto) | [cost-gl-flow-v2.md](cost-gl-flow-v2.md) |
| 4 | `GeneralLedgerEntries` | Sổ cái — mọi giao dịch tài chính | System (auto) | [cost-gl-flow-v2.md](cost-gl-flow-v2.md) |
| 5 | `AccountingSettings` | Cấu hình kế toán per location | Owner | [dashboard-report-flow.md](dashboard-report-flow.md) |
| 6 | `AccountingPeriods` | Kỳ kế toán (quý/năm) | System + Owner | [accounting-period-flow.md](accounting-period-flow.md) |
| 7 | `AccountingPeriodAuditLogs` | Lịch sử thay đổi kỳ kế toán | System (auto) | [accounting-period-flow.md](accounting-period-flow.md) |
| 8 | `TaxRulesets` | Version container cho Rule Engine | Admin/Consultant | [rule-engine-flow.md](rule-engine-flow.md) |
| 9 | `TaxGroupRules` | Phân nhóm HKD theo doanh thu | Admin/Consultant | [rule-engine-flow.md](rule-engine-flow.md) |
| 10 | `IndustryTaxRates` | Thuế suất VAT/TNCN theo ngành | Admin/Consultant | [rule-engine-flow.md](rule-engine-flow.md) |
| 11 | `AccountingTemplates` | Định nghĩa mẫu sổ (S1a, S2a…) | Admin/Consultant | [accounting-book-flow-v2.md](accounting-book-flow-v2.md) |
| 12 | `AccountingTemplateVersions` | Phiên bản nội dung mẫu sổ | Admin/Consultant | [accounting-book-flow-v2.md](accounting-book-flow-v2.md) |
| 13 | `MappableEntities` | Whitelist entity cho field mapping (Metadata Registry) | Admin | [accounting-book-flow-v2.md](accounting-book-flow-v2.md) |
| 14 | `MappableFields` | Whitelist field cho từng entity (Metadata Registry) | Admin | [accounting-book-flow-v2.md](accounting-book-flow-v2.md) |
| 15 | `TemplateFieldMappings` | Mapping dữ liệu DB → field trong mẫu (FK → Metadata Registry) | Admin/Consultant | [accounting-book-flow-v2.md](accounting-book-flow-v2.md) |
| 16 | `AccountingBooks` | Sổ kế toán đã tạo (live view) | Owner | [accounting-book-flow-v2.md](accounting-book-flow-v2.md) |
| 17 | `AccountingExports` | Snapshot mỗi lần xuất sổ | System (auto) | [accounting-book-flow-v2.md](accounting-book-flow-v2.md) |
| 18 | `TaxPayments` | Ghi nhận thuế đã nộp (cho S3a khi triển khai) | Owner | [accounting-book-flow-v2.md](accounting-book-flow-v2.md) |
| 19 | `FormulaDefinitions` | Định nghĩa công thức tính toán (JSON AST), reusable pool | Admin/Consultant | [tax-formular-engine.md](../04-engine/tax-formular-engine.md) |
| 20 | `FormulaResults` | Cache kết quả tính toán per Book + Formula + Context | System (auto) | [tax-formular-engine.md](../04-engine/tax-formular-engine.md) |

---

## 4. Sub-documents

### Feature Docs (Entity + Flow + Rules + API + Errors)

| # | File | Nội dung chính |
|---|------|---------------|
| 1 | [cost-gl-flow-v2.md](cost-gl-flow-v2.md) | Costs + Revenues + StockMovements + GL — Revenue/Cost symmetry, StockMovement v2, Manual GL, reversal logic |
| 2 | [accounting-period-flow.md](accounting-period-flow.md) | AccountingPeriods + AuditLogs — lifecycle (open → finalized → reopened) |
| 3 | [rule-engine-flow.md](rule-engine-flow.md) | TaxRulesets + TaxGroupRules + IndustryTaxRates — group evaluation, data-driven |
| 4 | [accounting-book-flow-v2.md](accounting-book-flow-v2.md) | Templates + Metadata Registry + Books + Exports + TaxPayments + TT152 Specs (S1a, S2a–S2e) |
| 5 | [dashboard-report-flow.md](dashboard-report-flow.md) | AccountingSettings + Cash Flow + Dashboard Widgets + Reports |
| 6 | [tax-formular-engine.md](../04-engine/tax-formular-engine.md) | FormulaDefinitions + FormulaResults — Formula Engine cho computed cells (AGGREGATE, CELL_REF, TAX_RATE, WEIGHTED_AVG, EXTERNAL_LOOKUP) |
| 7 | [accounting-book-revenue-centric-plan.md](accounting-book-revenue-centric-plan.md) | Plan chot theo huong Revenue-centric: bo lien ket book-business type, override VAT/PIT theo book, bulk reclassify cho FE |

### Companion Docs

| File | Nội dung |
|------|---------|
| [report-accounting-entities.md](report-accounting-entities.md) | Entity reference — sample data cho tất cả 14 tables |
| [report-accounting-diagrams.md](report-accounting-diagrams.md) | State machines, Activity diagrams, Sequence diagrams |
