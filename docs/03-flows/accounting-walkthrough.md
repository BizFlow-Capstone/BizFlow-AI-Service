# Accounting Module — Walkthrough & Data Flow

> **Mục đích**: Tài liệu dạng walkthrough — chạy từ đầu đến cuối module kế toán với **data mẫu cụ thể**, giải thích **ai làm gì, data đi đâu, entity nào tham gia**. Dùng để onboard member mới.
>
> Tham chiếu chi tiết: [report-accounting-flow.md](report-accounting-flow.md) (index)

---

## Mục lục

- [Tổng quan Entity](#tổng-quan-entity)
- [Phase 0 — Setup (Admin)](#phase-0--setup-admin)
- [Phase 1 — Cấu hình Template (Admin)](#phase-1--cấu-hình-template-admin)
- [Phase 2 — Hoạt động kinh doanh (Owner)](#phase-2--hoạt-động-kinh-doanh-hàng-ngày-owner)
- [Phase 3 — Tạo kỳ kế toán (Owner)](#phase-3--tạo-kỳ-kế-toán-owner)
- [Phase 4 — Rule Engine gợi ý (System)](#phase-4--rule-engine-gợi-ý-nhóm-system)
- [Phase 5 — Tạo sổ & xem dữ liệu (Owner)](#phase-5--tạo-sổ--xem-dữ-liệu-live-owner)
- [Phase 6 — Xuất sổ (Owner)](#phase-6--xuất-sổ-owner)
- [Phase 7 — Chốt kỳ (Owner)](#phase-7--chốt-kỳ-owner)
- [Phụ lục A — Full Entity Map](#phụ-lục-a--full-entity-map)
- [Phụ lục B — API Summary](#phụ-lục-b--api-summary)

---

## Tổng quan Entity

### Toàn bộ 18 tables, chia theo vai trò

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        ENTITY MAP — ACCOUNTING MODULE                       │
│                                                                             │
│  ╔═══════ ADMIN SETUP (một lần, ít thay đổi) ════════════════════════════╗  │
│  ║                                                                       ║  │
│  ║  TaxRulesets ─────┬── TaxGroupRules        (Bộ quy tắc phân nhóm)     ║  │
│  ║                   └── IndustryTaxRates      (Thuế suất theo ngành)    ║  │
│  ║                                                                       ║  │
│  ║  MappableEntities ─── MappableFields        (Metadata Registry)       ║  │
│  ║                                                                       ║  │
│  ║  AccountingTemplates ── AccountingTemplateVersions                    ║  │
│  ║                              └── TemplateFieldMappings                ║  │
│  ║                                  (map DB field → cột sổ kế toán)      ║  │
│  ╚═══════════════════════════════════════════════════════════════════════╝  │
│                                                                             │
│  ╔═══════ DATA LAYER (tự động từ bán/mua/thủ công) ══════════════════════╗  │
│  ║                                                                       ║  │
│  ║  Orders ──────► Revenues ────┐                                        ║  │
│  ║  Imports ─────► Costs ───────┼──► GeneralLedgerEntries (sổ cái)       ║  │
│  ║  Manual GL ──────────────────┘                                        ║  │
│  ║                                                                       ║  │
│  ║  Orders/Imports ──► StockMovements (nhật ký kho)                      ║  │
│  ║                                                                       ║  │
│  ╚═══════════════════════════════════════════════════════════════════════╝  │
│                                                                             │
│  ╔═══════ OWNER ACCOUNTING (khi chốt sổ) ════════════════════════════════╗  │
│  ║                                                                       ║  │
│  ║  AccountingPeriods ──────┬── AccountingBooks (live view)              ║  │
│  ║  AccountingPeriodAuditLogs│       └── AccountingExports (snapshot)    ║  │
│  ║                          └── TaxPayments (thuế đã nộp)                ║  │
│  ║                                                                       ║  │
│  ║  AccountingSettings (cấu hình kế toán per location)                   ║  │
│  ╚═══════════════════════════════════════════════════════════════════════╝  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Entity Relationship

```markdown
                         ┌─────────────────┐
                         │  TaxRulesets    │
                         │  (version 1.0)  │
                         └──┬───────────┬──┘
                            │           │
                  ┌─────────▼──┐   ┌────▼─────────────┐
                  │TaxGroupRules│  │IndustryTaxRates  │
                  │(Nhóm 1-4)  │   │(VAT/PIT per ngành│
                  └────────────┘   └──────────────────┘

┌───────────────────┐   ┌──────────────────────┐   ┌──────────────────┐
│MappableEntities   │──►│MappableFields        │   │AccountingTemplates│
│(orders, costs...) │   │(TotalAmount, Date..) │   │(S1a, S2a-S2e)    │
└───────────────────┘   └──────────┬───────────┘   └───────┬──────────┘
                                   │                       │
                                   │    ┌──────────────────▼──────────┐
                                   │    │AccountingTemplateVersions   │
                                   │    │(v1.0, v2.0...)              │
                                   │    └──────────────┬──────────────┘
                                   │                   │
                                   │    ┌──────────────▼──────────────┐
                                   └───►│TemplateFieldMappings        │
                                        │(EntityId + FieldId → Cột sổ)│
                                        └─────────────────────────────┘

┌─────────┐    ┌──────────┐                      ┌───────────────────┐
│ Orders  │───►│ Revenues │───┐                  │ GeneralLedger     │
└─────────┘    └──────────┘   ├─────────────────►│ Entries (GL)      │
┌─────────┐    ┌──────────┐   │                  │ (sổ cái tổng)     │
│ Imports │───►│ Costs    │───┘                  └───────────────────┘
└────┬────┘    └──────────┘                               │
     │                                                     │
     └──────────────────────┐                              │
┌─────────┐                 │                              │
│ Orders  │──► StockMovements (nhật ký kho)                │
└─────────┘                                                │
                                                           │
                   ┌───────────────────┐                   │
                   │AccountingPeriods  │◄──────────────────┘
                   │(Q1/2026, Q2..)    │         (data query realtime)
                   └───────┬───────────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
    ┌─────────▼──┐  ┌──────▼────┐  ┌───▼──────────┐
    │Accounting  │  │Accounting │  │TaxPayments   │
    │Books       │  │PeriodAudit│  │(thuế đã nộp) │
    │(live view) │  │Logs       │  └──────────────┘
    └─────┬──────┘  └───────────┘
          │
    ┌─────▼──────────┐
    │Accounting      │
    │Exports         │
    │(snapshot file) │
    └────────────────┘
```

---

## Phase 0 — Setup (Admin)

> **Ai**: Admin hệ thống
> **Khi nào**: Một lần khi deploy, hoặc khi TT152 thay đổi
> **Mục đích**: Cấu hình Tax Rule Engine + Metadata Registry

### Bước 0.1 — Tạo Tax Ruleset

Admin tạo bộ quy tắc phân nhóm HKD theo TT152/2025:

```
POST /api/v1/tax-rulesets
{
    "code": "TT152_2025",
    "name": "Thông tư 152/2025/TT-BTC",
    "version": "1.0.0",
    "effectiveFrom": "2026-01-01"
}
```

**Entities tham gia**: `TaxRulesets`

**Data sau bước này:**

| RulesetId | Code | Version | IsActive | EffectiveFrom |
|:---------:|------|:-------:|:--------:|:-------------:|
| 1 | TT152_2025 | 1.0.0 | ✅ | 2026-01-01 |

### Bước 0.2 — Tạo Group Rules (4 nhóm)

```
TaxGroupRules (bên trong RulesetId = 1):

┌────────┬──────────┬──────────────────────────────┬─────────────────────────┐
│ Nhóm   │ DT/năm   │ Thuế                         │ Sổ bắt buộc             │
├────────┼──────────┼──────────────────────────────┼─────────────────────────┤
│ Nhóm 1 │ < 500tr  │ Miễn VAT + PIT               │ S1a                     │
│ Nhóm 2 │ 500tr-3tỷ│ Cách 1: %DT. Cách 2: DT-CP   │ C1: S2a. C2: S2b-S2e    │
│ Nhóm 3 │ 3tỷ-50tỷ │ Cách 2: DT-CP                │ S2b, S2c, S2d, S2e      │
│ Nhóm 4 │ ≥ 50tỷ   │ Cách 2: DT-CP                │ S2b, S2c, S2d, S2e      │
└────────┴──────────┴──────────────────────────────┴─────────────────────────┘
```

**Entities tham gia**: `TaxGroupRules`

### Bước 0.3 — Tạo Industry Tax Rates

```
IndustryTaxRates (bên trong RulesetId = 1):

┌──────────────────┬─────────┬──────────┬────────────────────────┐
│ Ngành            │ TaxType │ TaxRate  │ Mô tả                  │
├──────────────────┼─────────┼──────────┼────────────────────────┤
│ Bán lẻ hàng hóa  │ VAT     │ 1.00%    │ GTGT phân phối hàng    │
│ Bán lẻ hàng hóa  │ PIT_M1  │ 0.50%    │ TNCN Cách 1            │
│ Dịch vụ          │ VAT     │ 5.00%    │ GTGT dịch vụ           │
│ Dịch vụ          │ PIT_M1  │ 2.00%    │ TNCN Cách 1            │
│ SX, DV gắn hàng  │ VAT     │ 3.00%    │ GTGT SX/FnB            │
│ SX, DV gắn hàng  │ PIT_M1  │ 1.50%    │ TNCN Cách 1            │
└──────────────────┴─────────┴──────────┴────────────────────────┘
```

**Entities tham gia**: `IndustryTaxRates`

### Bước 0.4 — Tạo Metadata Registry

Admin đăng ký các entity + field mà template được phép tham chiếu:

```
POST /api/admin/mappable-entities
→ { "entityCode": "revenues",      "displayName": "Doanh thu",   "category": "revenue" }
→ { "entityCode": "costs",         "displayName": "Chi phí",     "category": "cost" }
→ { "entityCode": "gl_entries",    "displayName": "Sổ cái (GL)", "category": "general" }
→ { "entityCode": "orders",        "displayName": "Đơn hàng",    "category": "revenue" }
→ { "entityCode": "order_details", "displayName": "Chi tiết đơn", "category": "revenue" }
→ { "entityCode": "products",      "displayName": "Sản phẩm",    "category": "revenue" }
→ { "entityCode": "stock_movements","displayName": "Biến động kho","category": "inventory" }
→ { "entityCode": "tax_payments",  "displayName": "Thuế đã nộp", "category": "tax" }
```

```
POST /api/admin/mappable-entities/{entityId}/fields
→ revenues:   Amount, RevenueDate, Description, RevenueType, ...
→ costs:      Amount, CostDate, Description, CostType, ...
→ gl_entries: DebitAmount, CreditAmount, EntryDate, MoneyChannel, ...
→ ...
```

**Entities tham gia**: `MappableEntities`, `MappableFields`

**Data sau bước này:**

```
MappableEntities:
┌────┬──────────────────┬───────────────┬───────────┐
│ ID │ EntityCode       │ DisplayName   │ Category  │
├────┼──────────────────┼───────────────┼───────────┤
│ 1  │ revenues         │ Doanh thu     │ revenue   │
│ 2  │ costs            │ Chi phí       │ cost      │
│ 3  │ gl_entries       │ Sổ cái (GL)   │ general   │
│ 4  │ orders           │ Đơn hàng      │ revenue   │
│ 5  │ order_details    │ Chi tiết đơn  │ revenue   │
│ 6  │ products         │ Sản phẩm      │ revenue   │
│ 7  │ stock_movements  │ Biến động kho │ inventory │
│ 8  │ tax_payments     │ Thuế đã nộp   │ tax       │
└────┴──────────────────┴───────────────┴───────────┘

MappableFields (ví dụ cho revenues, EntityId=1):
┌────┬────────────┬──────────────┬─────────┬───────────────────┐
│ ID │ FieldCode  │ DisplayName  │ DataType│AllowedAggregations│
├────┼────────────┼──────────────┼─────────┼───────────────────┤
│ 1  │ Amount     │ Số tiền DT   │ decimal │ ["sum","avg"]     │
│ 2  │ RevenueDate│ Ngày DT      │ date    │ ["none"]          │
│ 3  │ Description│ Diễn giải    │ text    │ ["none"]          │
└────┴────────────┴──────────────┴─────────┴───────────────────┘
```

---

## Phase 1 — Cấu hình Template (Admin)

> **Ai**: Admin (hoặc Consultant cho bước edit)
> **Khi nào**: Một lần sau Phase 0, hoặc khi cần sửa cấu trúc sổ
> **Mục đích**: Tạo + cấu hình mẫu sổ kế toán TT152

### Step-by-step

```
                    TEMPLATE MANAGEMENT FLOW
                    ════════════════════════

  ┌──────────────────────────────────────────────────────────────┐
  │  Bước 1.1: Templates đã có sẵn (seeded lúc deploy)           │
  │                                                              │
  │    AccountingTemplates:                                      │
  │    ┌──────┬──────────────────────────────┬──────────┬──────┐ │
  │    │ Code │ Name                         │ Groups   │Method│ │
  │    ├──────┼──────────────────────────────┼──────────┼──────┤ │
  │    │ S1a  │ Sổ chi tiết bán hàng         │ [1]      │ all  │ │
  │    │ S2a  │ Sổ doanh thu BH, DV          │ [2]      │ C1   │ │
  │    │ S2b  │ Sổ doanh thu BH, DV          │ [2,3,4]  │ C2   │ │
  │    │ S2c  │ Sổ chi tiết doanh thu, CP    │ [2,3,4]  │ C2   │ │
  │    │ S2d  │ Sổ chi tiết VL, DC, SP, HH   │ [2,3,4]  │ C2   │ │
  │    │ S2e  │ Sổ chi tiết tiền             │ [2,3,4]  │ C2   │ │
  │    └──────┴──────────────────────────────┴──────────┴──────┘ │
  └────────────────────────────┬─────────────────────────────────┘
                               │
                               ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Bước 1.2: Admin clone version → Draft                       │
  │                                                              │
  │    POST /api/admin/accounting-templates/1/versions/clone     │
  │    → Tạo AccountingTemplateVersions (v1.0, IsActive=false)   │
  │    → Copy FieldMappings từ version trước (nếu có)            │
  │                                                              │
  │    AccountingTemplateVersions:                               │
  │    ┌────┬──────────┬──────┬────────┬──────────┐              │
  │    │ TV │ Template │ Ver  │ Active │ Status   │              │
  │    ├────┼──────────┼──────┼────────┼──────────┤              │
  │    │ 1  │ S1a (1)  │ v1.0 │ false  │ draft    │              │
  │    │ 2  │ S2a (2)  │ v1.0 │ false  │ draft    │              │
  │    │ ...│ ...      │ ...  │ ...    │ ...      │              │
  │    └────┴──────────┴──────┴────────┴──────────┘              │
  └────────────────────────────┬─────────────────────────────────┘
                               │
                               ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Bước 1.3: Admin cấu hình FieldMappings (dropdown-based)    │
  │                                                              │
  │  UI hiện dropdown Entity → chọn → dropdown Field hiện       │
  │                                                              │
  │  Ví dụ: FieldMappings cho S1a (TemplateVersionId = 1):      │
  │                                                              │
  │  ┌─────────┬───────────┬───────────┬──────────┬─────┬──────┐│
  │  │FieldCode│ Label     │ Source    │ Field    │ Agg │ Col  ││
  │  │         │           │ Entity   │          │     │      ││
  │  ├─────────┼───────────┼───────────┼──────────┼─────┼──────┤│
  │  │ stt     │ STT       │ (auto)    │ —        │ —   │ A    ││
  │  │ date    │ Ngày tháng│ revenues  │ Revenue  │ none│ B    ││
  │  │         │           │ (Id=1)    │ Date(2)  │     │      ││
  │  │ content │ Nội dung  │ revenues  │ Descript │ none│ C    ││
  │  │         │           │ (Id=1)    │ ion (3)  │     │      ││
  │  │ revenue │ Doanh thu │ revenues  │ Amount   │ none│ D    ││
  │  │         │           │ (Id=1)    │ (1)      │     │      ││
  │  └─────────┴───────────┴───────────┴──────────┴─────┴──────┘│
  │                                                              │
  │  TemplateFieldMappings lưu:                                  │
  │  - SourceEntityId = FK → MappableEntities (Id=1, revenues)  │
  │  - SourceFieldId  = FK → MappableFields   (Id=2, RevenueDate)│
  │  (Chống injection — chỉ chọn từ dropdown, DB constraint)     │
  └────────────────────────────┬─────────────────────────────────┘
                               │
                               ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Bước 1.4: Preview / Dry-run                                │
  │                                                              │
  │  POST /api/admin/template-versions/1/preview                 │
  │  { "locationId": 1, "periodStart": "2026-01-01",             │
  │    "periodEnd": "2026-03-31", "maxRows": 10 }               │
  │                                                              │
  │  → System query Revenues + GL data thật cho Location 1       │
  │  → Render theo FieldMappings draft → trả về JSON             │
  │  → Admin xem: "Đúng rồi, data hiển thị đúng cột"           │
  │                                                              │
  │  Validate:                                                   │
  │  ✓ SourceEntityId/SourceFieldId tồn tại + active             │
  │  ✓ AggregationType hợp lệ (vd: không sum trên text)         │
  │  ✓ ExportColumn unique trong version                         │
  └────────────────────────────┬─────────────────────────────────┘
                               │
                               ▼
  ┌──────────────────────────────────────────────────────────────┐
  │  Bước 1.5: Activate (Admin only)                             │
  │                                                              │
  │  PUT /api/admin/accounting-templates/versions/1/activate     │
  │  → v1.0 IsActive = true                                      │
  │  → Tất cả AccountingBooks dùng template S1a sẽ dùng v1.0    │
  │                                                              │
  │  AccountingTemplateVersions SAU activate:                    │
  │  ┌────┬──────────┬──────┬────────┐                           │
  │  │ TV │ Template │ Ver  │ Active │                           │
  │  ├────┼──────────┼──────┼────────┤                           │
  │  │ 1  │ S1a (1)  │ v1.0 │ ✅ true │ ←── active              │
  │  │ 2  │ S2a (2)  │ v1.0 │ ✅ true │ ←── active              │
  │  │ ...│ ...      │ ...  │ ...    │                           │
  │  └────┴──────────┴──────┴────────┘                           │
  └──────────────────────────────────────────────────────────────┘
```

**Entities tham gia Phase 1:**
- `AccountingTemplates` — mẫu sổ
- `AccountingTemplateVersions` — phiên bản
- `TemplateFieldMappings` — mapping cột
- `MappableEntities` + `MappableFields` — nguồn dropdown

---

## Phase 2 — Hoạt động kinh doanh hàng ngày (Owner)

> **Ai**: Owner (qua app BizFlow)
> **Khi nào**: Mỗi ngày — bán hàng, nhập hàng, ghi chi phí
> **Mục đích**: Data tự động tạo ra Revenues, Costs, GL entries, StockMovements

### Scenario mẫu — Q1/2026, Location "Cửa hàng Minh Phát"

```
═══════════════════════════════════════════════════════════════
  THÁNG 1/2026 — HOẠT ĐỘNG KINH DOANH
═══════════════════════════════════════════════════════════════

  📦 10/01: NHẬP HÀNG (Import CONFIRMED)
  ─────────────────────────────────────────
  PNK-20260110-001: Nhập Xi măng HT 200 bao × 85,000đ = 17,000,000đ

  Trigger: ImportService.ConfirmAsync()
  ┌─────────────────────────────────────────────────────────┐
  │ 1. Costs ← auto tạo Cost (RULE-COST-01)                │
  │    CostId=1, CostType='import', ImportId=1              │
  │    Amount=17,000,000, CostDate=2026-01-10               │
  │                                                         │
  │ 2. GL ← auto tạo entry (RULE-GL-03)                    │
  │    EntryId=1, TransactionType='import_cost'             │
  │    ReferenceType='cost', ReferenceId=1 (CostId)         │
  │    DebitAmount=0, CreditAmount=17,000,000               │
  │    MoneyChannel='cash'                                   │
  │                                                         │
  │ 3. StockMovements ← auto log (RULE-SM-01)              │
  │    ProductId=Xi_Mang, QuantityDelta=+200                │
  │    StockBefore=0, StockAfter=200                        │
  │    UnitCostPrice=85,000, TotalValue=17,000,000          │
  │    ReferenceType='IMPORT', DocumentCode='PNK-001'       │
  └─────────────────────────────────────────────────────────┘

  🛒 15/01: BÁN HÀNG (Order COMPLETED)
  ─────────────────────────────────────────
  ORD-20260115-001: Bán Xi măng 50 bao × 95,000đ = 4,750,000đ
  Thanh toán: 4,000,000đ tiền mặt + 750,000đ chuyển khoản

  Trigger: OrderService.CompleteAsync()
  ┌─────────────────────────────────────────────────────────┐
  │ 1. Revenues ← auto tạo Revenue (RULE-REV-01)           │
  │    RevenueId=1, RevenueType='sale', OrderId=1           │
  │    Amount=4,750,000, RevenueDate=2026-01-15             │
  │    PaymentMethod='mixed'                                 │
  │                                                         │
  │ 2. GL ← auto tạo 2 entries (RULE-GL-01, DD-06 split)   │
  │    EntryId=2: DebitAmount=4,000,000, Channel=cash       │
  │    EntryId=3: DebitAmount=750,000, Channel=bank         │
  │    Cả 2: TransactionType='sale', RefType='revenue'      │
  │    ReferenceId=1 (RevenueId)                            │
  │                                                         │
  │ 3. StockMovements ← auto log (RULE-SM-01)              │
  │    ProductId=Xi_Mang, QuantityDelta=-50                 │
  │    StockBefore=200, StockAfter=150                      │
  │    UnitCostPrice=85,000, TotalValue=4,250,000           │
  │    ReferenceType='ORDER', DocumentCode='ORD-001'        │
  └─────────────────────────────────────────────────────────┘

  🛒 20/01: BÁN HÀNG (Order COMPLETED, có ghi nợ)
  ─────────────────────────────────────────────────
  ORD-20260120-002: Bán Xi măng 100 bao × 95,000đ = 9,500,000đ
  Thanh toán: 7,000,000đ tiền mặt + 2,500,000đ ghi nợ Anh Ba

  ┌─────────────────────────────────────────────────────────┐
  │ Revenues: RevenueId=2, Amount=9,500,000, mixed          │
  │                                                         │
  │ GL: 2 entries (DD-06 split by channel)                  │
  │   EntryId=4: Debit 7,000,000 | cash                    │
  │   EntryId=5: Debit 2,500,000 | debt                    │
  │                                                         │
  │ StockMovement: Xi_Mang -100, Before=150, After=50      │
  └─────────────────────────────────────────────────────────┘

  💰 25/01: THU NỢ (Debt Payment)
  ─────────────────────────────────
  Anh Ba trả 1,000,000đ tiền mặt

  ┌─────────────────────────────────────────────────────────┐
  │ GL ← auto entry (RULE-GL-04)                           │
  │   EntryId=6: TransactionType='debt_payment'            │
  │   DebitAmount=1,000,000 | MoneyChannel='cash'           │
  │   (Thu nợ ≠ doanh thu — DT đã ghi khi bán hàng)       │
  └─────────────────────────────────────────────────────────┘

  ✏️ 28/01: CHI PHÍ THỦ CÔNG (Owner tự khai)
  ─────────────────────────────────────────────
  Owner ghi: Thuê mặt bằng T1/2026 = 5,000,000đ
  
  POST /api/v1/locations/1/costs
  { "costType": "rent", "amount": 5000000, "costDate": "2026-01-28", 
    "paymentMethod": "bank", "description": "Thuê mặt bằng T1/2026" }

  ┌─────────────────────────────────────────────────────────┐
  │ Costs ← manual (RULE-COST-03)                          │
  │   CostId=2, CostType='rent', ImportId=NULL              │
  │   Amount=5,000,000                                       │
  │                                                         │
  │ GL ← auto entry (RULE-GL-03)                           │
  │   EntryId=7: TransactionType='manual_cost'              │
  │   CreditAmount=5,000,000 | MoneyChannel='bank'          │
  └─────────────────────────────────────────────────────────┘

  ✏️ 30/01: DOANH THU THỦ CÔNG — Manual GL (đường tự do)
  ────────────────────────────────────────────────────────
  Owner ghi DT trước khi dùng app (T12/2025) = 15,000,000đ
  
  POST /api/v1/locations/1/gl-entries/manual
  { "transactionType": "manual_revenue", "amount": 15000000,
    "entryDate": "2025-12-15", "moneyChannel": "cash",
    "description": "Bán hàng T12/2025 (trước khi dùng app)" }

  ┌─────────────────────────────────────────────────────────┐
  │ GL ← manual entry trực tiếp (RULE-GL-08)               │
  │   EntryId=8: TransactionType='manual_revenue'           │
  │   ReferenceType='manual', ReferenceId=NULL              │
  │   DebitAmount=15,000,000 | MoneyChannel='cash'           │
  │   EntryDate=2025-12-15 (trước khi dùng app)             │
  │                                                         │
  │   (Không tạo Revenue record — đường tự do vào GL)       │
  └─────────────────────────────────────────────────────────┘
```

### Tổng hợp data sau Phase 2 (Q1/2026)

**Revenues table:**

| RevenueId | Type | OrderId | Amount | Date | PaymentMethod |
|:---------:|:----:|:-------:|-------:|:----:|:-------------:|
| 1 | sale | 1 | 4,750,000 | 15/01 | mixed |
| 2 | sale | 2 | 9,500,000 | 20/01 | mixed |
| *(+ thêm các đơn T2, T3...)* | | | | | |

**Costs table:**

| CostId | Type | ImportId | Amount | Date |
|:------:|:----:|:--------:|-------:|:----:|
| 1 | import | 1 | 17,000,000 | 10/01 |
| 2 | rent | NULL | 5,000,000 | 28/01 |
| *(+ thêm chi phí T2, T3...)* | | | | |

**GeneralLedgerEntries (GL):**

| EntryId | TransactionType | RefType | Debit | Credit | Channel | Date |
|:-------:|:---------------:|:-------:|------:|-------:|:-------:|:----:|
| 1 | import_cost | cost | 0 | 17,000,000 | cash | 10/01 |
| 2 | sale | revenue | 4,000,000 | 0 | cash | 15/01 |
| 3 | sale | revenue | 750,000 | 0 | bank | 15/01 |
| 4 | sale | revenue | 7,000,000 | 0 | cash | 20/01 |
| 5 | sale | revenue | 2,500,000 | 0 | debt | 20/01 |
| 6 | debt_payment | debtor | 1,000,000 | 0 | cash | 25/01 |
| 7 | manual_cost | cost | 0 | 5,000,000 | bank | 28/01 |
| 8 | manual_revenue | manual | 15,000,000 | 0 | cash | 15/12/25 |

**StockMovements:**

| SmId | Product | Delta | Before | After | UnitPrice | TotalValue | Ref |
|:----:|:-------:|:-----:|:------:|:-----:|----------:|-----------:|:---:|
| 1 | Xi Măng | +200 | 0 | 200 | 85,000 | 17,000,000 | IMPORT |
| 2 | Xi Măng | -50 | 200 | 150 | 85,000 | 4,250,000 | ORDER |
| 3 | Xi Măng | -100 | 150 | 50 | 85,000 | 8,500,000 | ORDER |

---

## Phase 3 — Tạo kỳ kế toán (Owner)

> **Ai**: Owner
> **Khi nào**: Đầu kỳ hoặc khi sẵn sàng chốt sổ
> **Mục đích**: Tạo kỳ Q1/2026 + nhập số dư đầu kỳ

```
POST /api/v1/locations/1/accounting/periods
{
    "periodType": "quarter",
    "year": 2026,
    "quarter": 1,
    "openingCashBalance": 10000000,     ← Kỳ đầu tiên: Owner nhập
    "openingBankBalance": 50000000      ← (RULE-PERIOD-05)
}
```

**Entities tham gia**: `AccountingPeriods`, `AccountingPeriodAuditLogs`

**Data sau bước này:**

```
AccountingPeriods:
┌──────────┬──────────┬──────┬─────┬────────────┬────────────┬──────────┬──────────┬────────┐
│ PeriodId │ Location │ Type │ Yr  │ Quarter    │ StartDate  │ EndDate  │ Cash     │ Bank   │
│          │          │      │     │            │            │          │ Opening  │Opening │
├──────────┼──────────┼──────┼─────┼────────────┼────────────┼──────────┼──────────┼────────┤
│ 1        │ 1        │ qtr  │ 2026│ 1          │ 2026-01-01 │2026-03-31│10,000,000│50M     │
└──────────┴──────────┴──────┴─────┴────────────┴────────────┴──────────┴──────────┴────────┘
Status: "open"

AccountingPeriodAuditLogs:
┌───────┬──────────┬─────────────────┬─────────────────────────────┐
│ LogId │ PeriodId │ Action          │ CreatedAt                   │
├───────┼──────────┼─────────────────┼─────────────────────────────┤
│ 1     │ 1        │ period_created  │ 2026-03-31T10:00:00Z        │
└───────┴──────────┴─────────────────┴─────────────────────────────┘
```

> **Kỳ thứ 2 trở đi** (RULE-PERIOD-06): Nếu Owner không truyền `openingCashBalance`, hệ thống auto tính = `10,000,000 + SUM(GL cash debit) - SUM(GL cash credit)` từ Q1.

---

## Phase 4 — Rule Engine gợi ý nhóm (System)

> **Ai**: System (tự động), Owner xem
> **Khi nào**: Khi Owner mở trang kế toán, hoặc call API
> **Mục đích**: Gợi ý nhóm HKD dựa trên doanh thu thực tế

```
GET /api/v1/locations/1/accounting/group-suggestion?periodId=1
```

```
System thực hiện:
┌─────────────────────────────────────────────────────────────────┐
│  1. SUM doanh thu Q1:                                           │
│     Revenues (sale+manual) + GL (manual_revenue)                │
│     = 4,750,000 + 9,500,000 + ... (giả sử tổng Q1 = 620tr)   │
│                                                                 │
│  2. Annualize: 620tr × (12/3) = ~2,480tr/năm                  │
│                                                                 │
│  3. Match TaxGroupRules:                                        │
│     Nhóm 1: 0 - 500tr     → SKIP (2,480tr > 500tr)            │
│     Nhóm 2: 500tr - 3tỷ   → ✅ MATCH                          │
│     Nhóm 3: 3tỷ - 50tỷ    → SKIP                              │
│                                                                 │
│  4. Trả về:                                                     │
│     suggestedGroup: 2                                           │
│     allowedTaxMethods: ["method_1", "method_2"]                │
│     requiredBooks:                                              │
│       method_1: ["S2a"]                                         │
│       method_2: ["S2b", "S2c", "S2d", "S2e"]                  │
│     industryBreakdown: [                                        │
│       { business: "Bán lẻ", revenue: 500tr, vatRate: 1% }     │
│       { business: "Dịch vụ", revenue: 120tr, vatRate: 5% }    │
│     ]                                                           │
└─────────────────────────────────────────────────────────────────┘
```

**Entities tham gia**: `TaxRulesets`, `TaxGroupRules`, `IndustryTaxRates`, `Revenues`, `GeneralLedgerEntries`

**Đây chỉ là GỢI Ý — Owner tự quyết định** (DD-03):

```
UI Dashboard hiển thị:

  ╔════════════════════════════════════════════════════════════╗
  ║  📊 GỢI Ý NHÓM HKD — Q1/2026                             ║
  ║                                                            ║
  ║  DT thực tế Q1:       620,000,000đ                        ║
  ║  DT dự kiến cả năm:   ~2,480,000,000đ                     ║
  ║                                                            ║
  ║  → Gợi ý: NHÓM 2                                          ║
  ║                                                            ║
  ║  ┌──────────────────────────────────────────────────────┐  ║
  ║  │  Cách 1: Thuế = % trên doanh thu                    │  ║
  ║  │  → Sổ cần: S2a (Sổ doanh thu)                       │  ║
  ║  │  [  CHỌN CÁCH 1  ]                                   │  ║
  ║  └──────────────────────────────────────────────────────┘  ║
  ║  ┌──────────────────────────────────────────────────────┐  ║
  ║  │  Cách 2: Thuế TNCN = % trên (DT - Chi phí)          │  ║
  ║  │  → Sổ cần: S2b, S2c, S2d, S2e                       │  ║
  ║  │  [  CHỌN CÁCH 2  ]                                   │  ║
  ║  └──────────────────────────────────────────────────────┘  ║
  ╚════════════════════════════════════════════════════════════╝

  Owner click "CHỌN CÁCH 1" → Hệ thống tạo AccountingBook
```

---

## Phase 5 — Tạo sổ & xem dữ liệu live (Owner)

> **Ai**: Owner
> **Khi nào**: Sau khi chọn nhóm/cách tính
> **Mục đích**: Tạo AccountingBook + xem data live

### Bước 5.1 — Tạo Book

Owner chọn Nhóm 2, Cách 1 → System tạo sổ S2a:

```
POST /api/v1/locations/1/accounting/books
{
    "periodId": 1,
    "groupNumber": 2,
    "taxMethod": "method_1",
    "businessTypeId": null    ← null = tạo cho tất cả ngành
}
```

```
System thực hiện:
┌─────────────────────────────────────────────────────────────┐
│  1. Xác định requiredBooks cho Nhóm 2 + method_1: ["S2a"]  │
│                                                             │
│  2. Location có 2 ngành (Bán lẻ + Dịch vụ)?                │
│     → DD-01: Tạo 1 book per BusinessType → 2 books         │
│     (Hoặc Owner chọn businessTypeId cụ thể → 1 book)       │
│                                                             │
│  3. Lookup active TemplateVersion cho S2a → VersionId=2     │
│                                                             │
│  4. Tạo AccountingBooks:                                    │
│     BookId=1: S2a, Bán lẻ hàng hóa (VAT 1%)               │
│     BookId=2: S2a, Dịch vụ (VAT 5%)                        │
└─────────────────────────────────────────────────────────────┘
```

**Entities tham gia**: `AccountingBooks`, `AccountingTemplateVersions`, `TaxGroupRules`

**Data:**

```
AccountingBooks:
┌────────┬──────────┬──────────┬─────┬────────┬────────────────┬────────┐
│ BookId │ Location │ PeriodId │ TV  │ Group  │ BusinessType   │ Status │
├────────┼──────────┼──────────┼─────┼────────┼────────────────┼────────┤
│ 1      │ 1        │ 1        │ 2   │ 2      │ bt-retail      │ active │
│ 2      │ 1        │ 1        │ 2   │ 2      │ bt-service     │ active │
└────────┴──────────┴──────────┴─────┴────────┴────────────────┴────────┘
TaxMethod = 'method_1', RulesetId = 1
```

### Bước 5.2 — Xem dữ liệu Live

```
GET /api/v1/locations/1/accounting/books/1/data
```

```
System thực hiện (DD-05 — Live data, không lưu):
┌───────────────────────────────────────────────────────────────────────┐
│                                                                       │
│  1. Lookup TemplateFieldMappings cho TemplateVersionId=2 (S2a v1.0)  │
│                                                                       │
│  2. Theo FieldMappings → query data:                                  │
│     SourceEntityId=1 (revenues) → query Revenues table                │
│     WHERE BusinessLocationId=1                                        │
│       AND DeletedAt IS NULL                                           │
│       AND RevenueDate BETWEEN '2026-01-01' AND '2026-03-31'          │
│     UNION ALL manual GL revenue entries                               │
│     Filter by BusinessTypeId = 'bt-retail' (Book.BusinessType)        │
│                                                                       │
│  3. Render theo cấu trúc S2a (A, B, C, 1):                          │
│                                                                       │
│  ┌──────────────────┬────────────┬──────────────────────┬────────────┐│
│  │ Số hiệu (A)      │ Ngày (B)   │ Diễn giải (C)        │ Số tiền(1)││
│  ├──────────────────┼────────────┼──────────────────────┼────────────┤│
│  │ ORD-20260115-001 │ 15/01/2026 │ Bán Xi măng 50 bao   │ 4,750,000 ││
│  │ ORD-20260120-002 │ 20/01/2026 │ Bán Xi măng 100 bao  │ 9,500,000 ││
│  │ ...              │ ...        │ ...                  │ ...        ││
│  │                  │            │ Cộng quý I           │500,000,000 ││
│  │                  │            │ Thuế GTGT (1%)       │  5,000,000 ││
│  │                  │            │ Thuế TNCN (0.5%)     │          0 ││
│  └──────────────────┴────────────┴──────────────────────┴────────────┘│
│                                                                       │
│  4. Dòng cuối: Apply TaxFormulas từ DB:                              │
│     GTGT = 500,000,000 × 0.01 = 5,000,000                           │
│     TNCN = MAX(0, 500,000,000 - 500,000,000) × 0.005 = 0            │
│     (DT bán lẻ chưa vượt 500tr miễn → TNCN = 0)                    │
│                                                                       │
└───────────────────────────────────────────────────────────────────────┘
```

**Data flow tổng hợp Phase 5:**

```
                    TemplateFieldMappings
                    (cột A → SoHieu,
                     cột B → RevenueDate,
                     cột C → Description,          
                     cột 1 → Amount)
                           │
                           ▼
  ┌────────────┐     ┌─────────────┐     ┌──────────────┐
  │ Revenues   │────►│  RENDERING  │────►│ JSON / Table │
  │ (sale data)│     │   ENGINE    │     │  Response    │
  └────────────┘     │             │     └──────────────┘
  ┌────────────┐     │  Resolve FK │
  │ GL entries │────►│  → Entity   │
  │ (manual DT)│     │  → Field    │
  └────────────┘     │  → Aggregate│
  ┌────────────┐     │  → Formula  │
  │ TaxFormulas│────►│  → Tax calc │
  │ (from DB)  │     └─────────────┘
  └────────────┘
```

> **Quan trọng** (DD-05): `AccountingBooks` **KHÔNG LƯU DATA**. Nó là "saved configuration" — khi Owner mở sổ, system query Revenues/Costs/GL **realtime**. Data luôn cập nhật theo giao dịch mới nhất.

---

## Phase 6 — Xuất sổ (Owner)

> **Ai**: Owner
> **Khi nào**: Khi sẵn sàng nộp thuế hoặc lưu trữ
> **Mục đích**: Tạo snapshot + export file Excel/PDF

```
POST /api/v1/locations/1/accounting/books/1/export
{
    "format": "xlsx",
    "notes": "Xuất lần 1 — Q1/2026"
}
```

```
System thực hiện:
┌─────────────────────────────────────────────────────────────┐
│  1. Query live data (giống Phase 5)                         │
│                                                             │
│  2. Render data vào template file (xlsx layout)             │
│                                                             │
│  3. Upload file → Cloudinary                                │
│     → FileUrl: https://res.cloudinary.com/.../S2a_Q1.xlsx  │
│                                                             │
│  4. Tạo AccountingExports (snapshot):                       │
│     ExportId=1                                              │
│     BookId=1                                                │
│     SummaryJson='{"totalRevenue":500000000,"totalVat":..}'  │
│     DataRowCount=142                                        │
│     ExportFormat='xlsx'                                     │
│     FileUrl='https://...'                                   │
│     ExportedAt=2026-04-01T10:00:00Z                        │
│                                                             │
│  5. Audit log → AccountingPeriodAuditLogs                   │
│     Action='book_exported', PeriodId=1                      │
└─────────────────────────────────────────────────────────────┘
```

**Entities tham gia**: `AccountingExports`, `AccountingPeriodAuditLogs`

**Data:**

```
AccountingExports:
┌──────────┬────────┬────────────────────────────┬──────┬──────────────────────┐
│ ExportId │ BookId │ SummaryJson (snapshot)      │ Rows │ ExportedAt           │
├──────────┼────────┼────────────────────────────┼──────┼──────────────────────┤
│ 1        │ 1      │ {"totalRevenue":500000000, │ 142  │ 2026-04-01T10:00:00Z │
│          │        │  "totalVat":5000000,        │      │                      │
│          │        │  "totalPit":0}              │      │                      │
└──────────┴────────┴────────────────────────────┴──────┴──────────────────────┘
Format: xlsx, FileUrl: https://res.cloudinary.com/.../S2a_Q1.xlsx
```

> **DD-05**: Export = **snapshot frozen**. Nếu sau đó có thêm đơn hàng → book live cập nhật → export mới sẽ khác. Owner có lịch sử so sánh giữa các lần export.

---

## Phase 7 — Chốt kỳ (Owner)

> **Ai**: Owner
> **Khi nào**: Sau khi đã export + nộp thuế xong
> **Mục đích**: Đánh dấu kỳ hoàn tất, lock sổ

```
POST /api/v1/locations/1/accounting/periods/1/finalize
```

```
System thực hiện:
┌─────────────────────────────────────────────────────────────┐
│  1. Validate: có ít nhất 1 book active? → ✅ (RULE-PERIOD-02)│
│                                                             │
│  2. Update AccountingPeriods:                               │
│     Status: 'open' → 'finalized'                            │
│     FinalizedAt = now()                                     │
│     FinalizedByUserId = currentUser                         │
│                                                             │
│  3. Audit log:                                              │
│     Action='period_finalized'                               │
│     NewValue='{"status":"finalized"}'                       │
│                                                             │
│  4. Prepare opening balance cho kỳ tiếp:                   │
│     Closing cash = 10,000,000 (opening)                     │
│                   + SUM(GL DebitAmount WHERE cash) = 12M    │
│                   - SUM(GL CreditAmount WHERE cash) = 17M   │
│                   = 5,000,000đ                              │
│                                                             │
│     Closing bank = 50,000,000 (opening)                     │
│                   + 750,000 (GL bank debit)                 │
│                   - 5,000,000 (GL bank credit)              │
│                   = 45,750,000đ                             │
│                                                             │
│  5. Khi Owner tạo Q2/2026 → auto carry (RULE-PERIOD-06):  │
│     Q2.openingCashBalance = 5,000,000                       │
│     Q2.openingBankBalance = 45,750,000                      │
└─────────────────────────────────────────────────────────────┘
```

**Lifecycle:**
```
  OPEN ──────────► FINALIZED ──────────► (Q2 mới, OPEN)
                       │
                       │ (Nếu cần sửa)
                       ▼
                   REOPENED ───► sửa data ───► FINALIZED lại
                   (bắt buộc ghi lý do — RULE-PERIOD-03)
```

---

## Phụ lục A — Full Entity Map

### All 18 tables theo thứ tự data flow

```
PHASE 0 — ADMIN SETUP
 │
 ├── TaxRulesets                    Bộ quy tắc (TT152 v1.0)
 │    ├── TaxGroupRules             4 nhóm HKD (JSON conditions + outcomes)
 │    └── IndustryTaxRates          Thuế suất VAT/PIT per ngành
 │
 ├── MappableEntities               Whitelist entity (orders, revenues...)
 │    └── MappableFields            Whitelist field per entity (Amount, Date...)
 │
 └── AccountingTemplates            Mẫu sổ (S1a, S2a-S2e)
      └── AccountingTemplateVersions    Phiên bản (v1.0, v2.0...)
           └── TemplateFieldMappings    Map DB→cột sổ (FK → Metadata Registry)

PHASE 2 — DATA LAYER (auto + manual)
 │
 ├── Revenues                       DT auto (Order→sale) + manual
 ├── Costs                          CP auto (Import→import) + manual
 ├── GeneralLedgerEntries           Sổ cái — every event → GL entry
 └── StockMovements                 Nhật ký kho — stock delta + giá trị

PHASE 3-7 — OWNER ACCOUNTING
 │
 ├── AccountingSettings             Cấu hình kế toán per location
 ├── AccountingPeriods              Kỳ kế toán (Q1/2026, Q2...)
 │    └── AccountingPeriodAuditLogs Lịch sử thao tác kỳ
 ├── AccountingBooks                Sổ đã tạo (live view, không lưu data)
 │    └── AccountingExports         Snapshot mỗi lần xuất (frozen)
 └── TaxPayments                    Ghi nhận thuế đã nộp
```

### Key fields per entity

| Entity | PK | Main FK | Key Fields |
|--------|:--:|---------|------------|
| **TaxRulesets** | RulesetId | — | Code, Version, IsActive, EffectiveFrom |
| **TaxGroupRules** | RuleId | RulesetId | GroupNumber, ConditionsJson, OutcomesJson |
| **IndustryTaxRates** | RateId | RulesetId, BusinessTypeId | TaxType, TaxRate |
| **MappableEntities** | EntityId | — | EntityCode, DisplayName, Category, IsActive |
| **MappableFields** | FieldId | EntityId | FieldCode, DataType, AllowedAggregations |
| **AccountingTemplates** | TemplateId | — | TemplateCode, ApplicableGroups, ApplicableMethods |
| **AccountingTemplateVersions** | TemplateVersionId | TemplateId | VersionLabel, IsActive |
| **TemplateFieldMappings** | MappingId | TemplateVersionId, SourceEntityId, SourceFieldId | FieldCode, FieldType, AggregationType, ExportColumn |
| **Revenues** | RevenueId | BusinessLocationId, OrderId | RevenueType, Amount, RevenueDate, PaymentMethod |
| **Costs** | CostId | BusinessLocationId, ImportId | CostType, Amount, CostDate, PaymentMethod |
| **GeneralLedgerEntries** | EntryId | BusinessLocationId | TransactionType, ReferenceType, ReferenceId, DebitAmount, CreditAmount, MoneyChannel, IsReversal |
| **StockMovements** | StockMovementId | ProductId, BusinessLocationId | QuantityDelta, StockBefore, StockAfter, UnitCostPrice, TotalValue, ReferenceType, DocumentCode |
| **AccountingSettings** | SettingId | BusinessLocationId | *(cấu hình kế toán)* |
| **AccountingPeriods** | PeriodId | BusinessLocationId | PeriodType, Year, Quarter, OpeningCashBalance, OpeningBankBalance, Status |
| **AccountingPeriodAuditLogs** | LogId | PeriodId | Action, OldValue, NewValue, Reason |
| **AccountingBooks** | BookId | BusinessLocationId, PeriodId, TemplateVersionId | GroupNumber, TaxMethod, BusinessTypeId, Status |
| **AccountingExports** | ExportId | BookId | SummaryJson, DataRowCount, ExportFormat, FileUrl |
| **TaxPayments** | TaxPaymentId | BusinessLocationId, PeriodId | TaxType, Amount, PaidAt, PaymentMethod |

---

## Phụ lục B — API Summary

### Admin APIs

| # | Method | Endpoint | Mục đích |
|:-:|--------|----------|----------|
| 1 | `POST` | `/api/v1/tax-rulesets` | Tạo bộ quy tắc thuế |
| 2 | `PUT` | `/api/v1/tax-rulesets/{id}/activate` | Activate ruleset |
| 3 | `GET` | `/api/v1/tax-rulesets/{id}/group-rules` | Xem group rules |
| 4 | `GET` | `/api/v1/tax-rulesets/{id}/industry-rates` | Xem thuế suất |
| 5 | `POST` | `/api/admin/mappable-entities` | Thêm entity vào whitelist |
| 6 | `POST` | `/api/admin/mappable-entities/{id}/fields` | Thêm field |
| 7 | `GET` | `/api/admin/mappable-entities` | List entities (dropdown) |
| 8 | `GET` | `/api/admin/mappable-entities/{id}/fields` | List fields (dropdown) |
| 9 | `GET` | `/api/admin/accounting-templates` | List mẫu sổ |
| 10 | `POST` | `/api/admin/accounting-templates/{id}/versions/clone` | Clone version draft |
| 11 | `POST` | `/api/admin/template-versions/{id}/field-mappings` | Thêm mapping |
| 12 | `PUT` | `/api/admin/template-versions/{id}/field-mappings/{mid}` | Sửa mapping |
| 13 | `POST` | `/api/admin/template-versions/{id}/preview` | Preview dry-run |
| 14 | `PUT` | `/api/admin/accounting-templates/versions/{id}/activate` | Activate version |

### Owner APIs

| # | Method | Endpoint | Mục đích |
|:-:|--------|----------|----------|
| 15 | `POST` | `/locations/{id}/costs` | Tạo chi phí thủ công |
| 16 | `POST` | `/locations/{id}/revenues` | Tạo doanh thu thủ công |
| 17 | `POST` | `/locations/{id}/gl-entries/manual` | Bút toán GL tự do |
| 18 | `GET` | `/locations/{id}/gl-entries` | Xem sổ cái |
| 19 | `GET` | `/locations/{id}/stock-movements` | Xem biến động kho |
| 20 | `GET` | `/locations/{id}/stock-movements/summary` | Tổng kết XNT |
| 21 | `POST` | `/locations/{id}/accounting/periods` | Tạo kỳ kế toán |
| 22 | `GET` | `/locations/{id}/accounting/group-suggestion` | Gợi ý nhóm HKD |
| 23 | `POST` | `/locations/{id}/accounting/books` | Tạo sổ kế toán |
| 24 | `GET` | `/locations/{id}/accounting/books/{bid}/data` | Xem data live |
| 25 | `POST` | `/locations/{id}/accounting/books/{bid}/export` | Xuất sổ (snapshot) |
| 26 | `POST` | `/locations/{id}/accounting/periods/{pid}/finalize` | Chốt kỳ |
| 27 | `POST` | `/locations/{id}/accounting/periods/{pid}/reopen` | Mở lại kỳ |
| 28 | `POST` | `/locations/{id}/tax-payments` | Ghi nhận thuế đã nộp |

> Tất cả Owner APIs prefix: `/api/v1/locations/{locationId}/...`
