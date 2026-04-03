# Report & Accounting — Entity Reference & Sample Data

> **Companion doc** cho [report-accounting-flow.md](report-accounting-flow.md) (index).
> Giải thích chi tiết từng entity, quan hệ giữa các table, và dữ liệu mẫu xuyên suốt một kịch bản kinh doanh thực tế.
>
> **Sub-docs**: [cost-gl-flow](cost-gl-flow.md) · [accounting-period-flow](accounting-period-flow.md) · [rule-engine-flow](rule-engine-flow.md) · [accounting-book-flow](accounting-book-flow.md) · [dashboard-report-flow](dashboard-report-flow.md)

---

## Mục lục

1. [Kịch bản mẫu (Scenario)](#1-kịch-bản-mẫu-scenario)
2. [ERD — Entity Relationship Diagram](#2-erd--entity-relationship-diagram)
3. [Entity Details & Sample Data](#3-entity-details--sample-data)
   - [3.1 Costs](#31-costs)
   - [3.2 GeneralLedgerEntries](#32-generalledgerentries)
   - [3.3 AccountingSettings](#33-accountingsettings)
   - [3.4 AccountingPeriods](#34-accountingperiods)
   - [3.5 AccountingPeriodAuditLogs](#35-accountingperiodauditlogs)
   - [3.6 TaxRulesets](#36-taxrulesets)
   - [3.7 TaxGroupRules](#37-taxgrouprules)
   - [3.8 IndustryTaxRates](#38-industrytaxrates)
   - [3.9 AccountingTemplates](#39-accountingtemplates)
   - [3.10 AccountingTemplateVersions](#310-accountingtemplateversions)
   - [3.11 TemplateFieldMappings](#311-templatefieldmappings)
   - [3.12 AccountingBooks](#312-accountingbooks)
   - [3.13 AccountingExports](#313-accountingexports)
   - [3.14 TaxPayments](#314-taxpayments)
4. [Data Flow Walkthrough](#4-data-flow-walkthrough)
5. [Cross-Entity Queries](#5-cross-entity-queries)

---

## 1. Kịch bản mẫu (Scenario)

Toàn bộ sample data trong doc này xoay quanh **một kịch bản xuyên suốt** để thấy cách các entity liên kết:

### Nhân vật & Location

| Entity | Value | Ghi chú |
|--------|-------|---------|
| **Owner** | Anh Minh (`UserId: u-owner-001`) | Chủ cửa hàng |
| **Location** | Cửa hàng Minh Phát (`BusinessLocationId: 1`) | VLXD + Dịch vụ cắt sắt |
| **BusinessType 1** | Bán lẻ hàng hóa (`bt-retail`) | VAT 1%, TNCN 0.5% |
| **BusinessType 2** | Dịch vụ (`bt-service`) | VAT 5%, TNCN 2% |
| **Khách hàng** | Anh Ba (Debtor, `DebtorId: 5`) | Thường mua ghi nợ |
| **Nhà cung cấp** | Công ty ABC | Xi măng, sắt thép |

### Timeline Q1/2026

```markdown
Tháng 1/2026:
├── 05/01: Import IMP-001 (Xi măng 500 bao × 85,000đ = 42,500,000đ) → CONFIRMED
├── 10/01: Chi tiền thuê mặt bằng T1: 5,000,000đ (manual cost)
├── 15/01: Order ORD-001 (Xi măng 50 bao + cắt sắt) = 5,950,000đ
│          → 4,000,000đ tiền mặt + 1,950,000đ ghi nợ Anh Ba
├── 20/01: Order ORD-002 (Xi măng 100 bao) = 9,500,000đ → full tiền mặt
├── 25/01: Anh Ba trả nợ 1,000,000đ (tiền mặt)
├── 28/01: Chi tiền điện T1: 1,200,000đ (manual cost)

Tháng 2/2026:
├── 05/02: Import IMP-002 (Sắt thép 200 cây × 120,000đ = 24,000,000đ) → CONFIRMED
├── 10/02: Order ORD-003 (Sắt 50 cây) = 7,500,000đ → chuyển khoản
├── 15/02: Order ORD-004 (Xi măng 200 bao + DV cắt sắt) = 20,100,000đ
│          → 15,000,000đ TM + 5,100,000đ CK
├── 20/02: Nộp thuế GTGT tạm tính Q4/2025: 3,500,000đ
├── 28/02: Chi thuê mặt bằng T2 + điện: 6,200,000đ

Tháng 3/2026:
├── ...Orders tiếp tục...
├── 15/03: Owner xem Rule Engine gợi ý → Nhóm 2
├── 20/03: Owner tạo AccountingBook (Nhóm 2, Cách 1, S2a)
├── 25/03: Owner cancel ORD-005 (đã completed trước đó)
├── 31/03: Owner export sổ Q1/2026

Tổng Q1/2026:
├── Doanh thu bán lẻ:     480,000,000đ
├── Doanh thu dịch vụ:    140,000,000đ
├── Tổng doanh thu:        620,000,000đ
├── Tổng chi phí:           85,000,000đ
```

---

## 2. ERD — Entity Relationship Diagram

```mermaid
┌──────────────────┐      ┌──────────────────┐     ┌──────────────────┐
│ BusinessLocations│      │   TaxRulesets    │     │  BusinessTypes   │
│──────────────────│      │──────────────────│     │──────────────────│
│BusinessLocationId│◄──── │ (independent)    │────►│ BusinessTypeId   │
│Name              │      │ RulesetId        │     │ Code             │
│...               │      │ Code, Version    │     │ Name             │
└───────┬──────────┘      │ IsActive         │     └─────────┬────────┘
        │                 └───────┬──────────┘               │
        │                         │                          │
   ┌────┴─────────────────────────┼──────────────────────────┤
   │                              │                          │
   │    ┌─────────────────┐       │    ┌─────────────────┐   │
   │    │    Costs        │       │    │ TaxGroupRules   │   │
   │    │─────────────────│       │    │─────────────────│   │
   ├───►│ BusinessLocId   │       ├───►│ RulesetId (FK)  │   │
   │    │ CostType        │       │    │ GroupNumber 1-4 │   │
   │    │ ImportId (FK?)  │       │    │ Min/MaxRevenue  │   │
   │    │ Amount, Date    │       │    │ AllowedMethods  │   │
   │    └─────────────────┘       │    │ RequiredBooks   │   │
   │                              │    └─────────────────┘   │
   │    ┌─────────────────┐       │                          │
   │    │ GeneralLedger   │       │    ┌─────────────────┐   │
   │    │    Entries      │       │    │IndustryTaxRates │   │
   │    │─────────────────│       │    │─────────────────│   │
   ├───►│ BusinessLocId   │       └───►│ RulesetId (FK)  │   │
   │    │ TransactionType │            │ BusinessTypeId◄─┼───┘
   │    │ Debit/Credit    │            │ TaxType, Rate   │
   │    │ MoneyChannel    │            └─────────────────┘
   │    │ IsReversal      │
   │    └─────────────────┘       ┌─────────────────────┐
   │                              │AccountingTemplates  │
   │    ┌─────────────────┐       │─────────────────────│
   │    │AccountingSettings│      │ TemplateCode (S1a…) │
   │    │─────────────────│       │ ApplicableGroups    │
   ├───►│ BusinessLocId   │       └──────────┬──────────┘
   │    │ FiscalYearStart │                  │
   │    └─────────────────┘       ┌──────────▼──────────┐
   │                              │TemplateVersions     │
   │    ┌─────────────────┐       │─────────────────────│
   │    │AccountingPeriods│       │ TemplateId (FK)     │
   │    │─────────────────│       │ VersionLabel, Schema│
   ├───►│ BusinessLocId   │       └──────────┬──────────┘
   │    │ Year, Quarter   │                  │
   │    │ Status          │       ┌──────────▼──────────┐
   │    └──┬───────┬──────┘       │TemplateFieldMappings│
   │       │       │              │─────────────────────│
   │       │       │              │ TemplateVersionId   │
   │       │       │              │ FieldCode, Source   │
   │       │       │              │ FormulaExpression   │
   │       │       │              └─────────────────────┘
   │       │       │
   │  ┌────▼────┐ ┌▼───────────────┐
   │  │AuditLogs│ │AccountingBooks │
   │  │─────────│ │────────────────│
   │  │PeriodId │ │ PeriodId (FK)  │
   │  │Action   │ │ TemplateVerId  │
   │  │Old/New  │ │ GroupNumber    │
   │  └─────────┘ │ TaxMethod      │
   │              │ BusinessTypeId │
   │              │ Status         │
   │              └───────┬────────┘
   │                      │
   │              ┌───────▼─────────┐
   │              │AccountingExports│
   │              │─────────────────│
   │              │ BookId (FK)     │
   │              │ SummaryJson     │
   │              │ FileUrl         │
   │              └─────────────────┘
   │
   │    ┌─────────────────┐
   │    │  TaxPayments    │
   │    │─────────────────│
   └───►│ BusinessLocId   │
        │ PeriodId (FK?)  │
        │ TaxType, Amount │
        │ PaidAt          │
        └─────────────────┘
```

### Quan hệ tóm tắt

| Parent → Child | Cardinality | FK column |
|---------------|:-----------:|-----------|
| BusinessLocations → Costs | 1:N | `BusinessLocationId` |
| BusinessLocations → GeneralLedgerEntries | 1:N | `BusinessLocationId` |
| BusinessLocations → AccountingSettings | 1:1 | `BusinessLocationId` (UNIQUE) |
| BusinessLocations → AccountingPeriods | 1:N | `BusinessLocationId` |
| BusinessLocations → TaxPayments | 1:N | `BusinessLocationId` |
| BusinessLocations → AccountingBooks | 1:N | `BusinessLocationId` |
| Imports → Costs | 1:0..1 | `ImportId` (nullable) |
| AccountingPeriods → AccountingPeriodAuditLogs | 1:N | `PeriodId` |
| AccountingPeriods → AccountingBooks | 1:N | `PeriodId` |
| AccountingPeriods → TaxPayments | 1:N | `PeriodId` (nullable) |
| TaxRulesets → TaxGroupRules | 1:N | `RulesetId` |
| TaxRulesets → IndustryTaxRates | 1:N | `RulesetId` |
| BusinessTypes → IndustryTaxRates | 1:N | `BusinessTypeId` |
| AccountingTemplates → AccountingTemplateVersions | 1:N | `TemplateId` |
| AccountingTemplateVersions → TemplateFieldMappings | 1:N | `TemplateVersionId` |
| AccountingTemplateVersions → AccountingBooks | 1:N | `TemplateVersionId` |
| TaxRulesets → AccountingBooks | 1:N | `RulesetId` |
| AccountingBooks → AccountingExports | 1:N | `BookId` |

---

## 3. Entity Details & Sample Data

### 3.1 Costs

**Mô tả**: Ghi nhận mọi chi phí kinh doanh — bao gồm cả chi phí tự động (từ Import) và chi phí Owner nhập tay.

**Columns giải thích:**

| Column | Type | Ý nghĩa | Ví dụ |
|--------|------|---------|-------|
| `CostType` | VARCHAR(30) | Phân loại chi phí | `import`, `salary`, `rent`, `utilities`, `transport`, `marketing`, `maintenance`, `other` |
| `ImportId` | BIGINT? | Nếu NOT NULL → chi phí tự động từ Import. Nếu NULL → Owner tự khai | `NULL` = manual, `101` = auto từ Import 101 |
| `Amount` | DECIMAL(15,2) | Số tiền chi phí (luôn dương) | `5000000.00` |
| `PaymentMethod` | VARCHAR(20)? | Hình thức thanh toán | `cash`, `bank`, `NULL` = chưa xác định |
| `DocumentUrl` | VARCHAR(500)? | Ảnh chụp hóa đơn/biên lai (Cloudinary) | `https://res.cloudinary.com/.../invoice.jpg` |

**Quy tắc đặc biệt:**
- `ImportId IS NOT NULL` → **readonly**. Muốn sửa/xóa phải cancel Import gốc.
- `ImportId IS NULL` → Owner tự CRUD.
- Soft delete (`DeletedAt`) → GL reversal entry tạo đồng thời.

**Sample data:**

| CostId | BizLocId | CostType | ImportId | Description | Amount | CostDate | PaymentMethod | CreatedBy |
|:------:|:--------:|:--------:|:--------:|-------------|-------:|:--------:|:-------------:|:---------:|
| 1 | 1 | `import` | 101 | Nhập Xi măng IMP-001 từ Cty ABC | 42,500,000 | 2026-01-05 | `bank` | u-owner-001 |
| 2 | 1 | `rent` | NULL | Thuê mặt bằng T1/2026 | 5,000,000 | 2026-01-10 | `bank` | u-owner-001 |
| 3 | 1 | `utilities` | NULL | Tiền điện T1/2026 | 1,200,000 | 2026-01-28 | `cash` | u-owner-001 |
| 4 | 1 | `import` | 102 | Nhập Sắt thép IMP-002 từ Cty ABC | 24,000,000 | 2026-02-05 | `bank` | u-owner-001 |
| 5 | 1 | `rent` | NULL | Thuê mặt bằng T2/2026 | 5,000,000 | 2026-02-28 | `bank` | u-owner-001 |
| 6 | 1 | `utilities` | NULL | Tiền điện T2/2026 | 1,200,000 | 2026-02-28 | `cash` | u-owner-001 |
| 7 | 1 | `salary` | NULL | Lương nhân viên T1+T2/2026 | 6,000,000 | 2026-02-28 | `cash` | u-owner-001 |

**Tổng chi phí Q1 (tính thêm T3):** ~85,000,000đ

---

### 3.2 GeneralLedgerEntries

**Mô tả**: Sổ cái ghi chép mọi giao dịch tài chính. Hệ thống tự động tạo — không có UI để user tạo trực tiếp.

**Columns giải thích:**

| Column | Type | Ý nghĩa | Giá trị hợp lệ |
|--------|------|---------|----------------|
| `TransactionType` | VARCHAR(30) | Loại giao dịch | `sale`, `import_cost`, `manual_cost`, `debt_payment`, `tax_payment` |
| `ReferenceType` | VARCHAR(30) | Entity nguồn | `order`, `import`, `cost`, `debtor_payment`, `tax_payment` |
| `ReferenceId` | BIGINT | ID của entity nguồn | FK logic (không enforce FK constraint) |
| `DebitAmount` | DECIMAL(15,2) | Tiền VÀO business | Doanh thu bán hàng, thu nợ |
| `CreditAmount` | DECIMAL(15,2) | Tiền RA business | Chi phí, nhập hàng, nộp thuế |
| `MoneyChannel` | VARCHAR(10)? | Kênh tiền thực tế | `cash`, `bank`, `debt`, `NULL` |
| `IsReversal` | BOOLEAN | Entry hoàn/hủy? | `true` khi cancel order/import |
| `ReversedEntryId` | BIGINT? | Trỏ về entry bị reverse | EntryId của entry gốc |

**Convention tiền:**
- Mỗi entry chỉ có **1 trong 2** (Debit hoặc Credit) > 0, cái còn lại = 0
- **DebitAmount > 0**: Tiền chảy VÀO business (bán hàng, thu nợ)
- **CreditAmount > 0**: Tiền chảy RA business (nhập hàng, chi phí, nộp thuế)
- **Reversal**: Đảo ngược direction (Debit gốc → Credit reversal, và ngược lại)

**Sample data — Các giao dịch tháng 1/2026:**

| EntryId | BizLocId | TransType | RefType | RefId | Date | Description | Debit | Credit | Channel | IsRev | RevId |
|:-------:|:--------:|:---------:|:-------:|:-----:|:----:|-------------|------:|-------:|:-------:|:-----:|:-----:|
| 1 | 1 | `import_cost` | `import` | 101 | 01-05 | IMP-001: Nhập Xi măng từ Cty ABC | 0 | 42,500,000 | `bank` | ❌ | — |
| 2 | 1 | `manual_cost` | `cost` | 2 | 01-10 | Thuê mặt bằng T1/2026 | 0 | 5,000,000 | `bank` | ❌ | — |
| 3 | 1 | `sale` | `order` | 201 | 01-15 | ORD-001: Bán hàng (tiền mặt) | 4,000,000 | 0 | `cash` | ❌ | — |
| 4 | 1 | `sale` | `order` | 201 | 01-15 | ORD-001: Bán hàng (ghi nợ Anh Ba) | 1,950,000 | 0 | `debt` | ❌ | — |
| 5 | 1 | `sale` | `order` | 202 | 01-20 | ORD-002: Bán hàng (tiền mặt) | 9,500,000 | 0 | `cash` | ❌ | — |
| 6 | 1 | `debt_payment` | `debtor_payment` | 301 | 01-25 | Thu nợ Anh Ba: 1,000,000đ (TM) | 1,000,000 | 0 | `cash` | ❌ | — |
| 7 | 1 | `manual_cost` | `cost` | 3 | 01-28 | Tiền điện T1/2026 | 0 | 1,200,000 | `cash` | ❌ | — |

**Sample data — Tháng 2/2026 (continued):**

| EntryId | BizLocId | TransType | RefType | RefId | Date | Description | Debit | Credit | Channel | IsRev | RevId |
|:-------:|:--------:|:---------:|:-------:|:-----:|:----:|-------------|------:|-------:|:-------:|:-----:|:-----:|
| 8 | 1 | `import_cost` | `import` | 102 | 02-05 | IMP-002: Nhập Sắt thép từ Cty ABC | 0 | 24,000,000 | `bank` | ❌ | — |
| 9 | 1 | `sale` | `order` | 203 | 02-10 | ORD-003: Bán sắt (chuyển khoản) | 7,500,000 | 0 | `bank` | ❌ | — |
| 10 | 1 | `sale` | `order` | 204 | 02-15 | ORD-004: Bán hàng (tiền mặt) | 15,000,000 | 0 | `cash` | ❌ | — |
| 11 | 1 | `sale` | `order` | 204 | 02-15 | ORD-004: Bán hàng (chuyển khoản) | 5,100,000 | 0 | `bank` | ❌ | — |
| 12 | 1 | `tax_payment` | `tax_payment` | 1 | 02-20 | Nộp thuế GTGT Q4/2025 | 0 | 3,500,000 | `bank` | ❌ | — |
| 13 | 1 | `manual_cost` | `cost` | 5 | 02-28 | Thuê mặt bằng T2/2026 | 0 | 5,000,000 | `bank` | ❌ | — |
| 14 | 1 | `manual_cost` | `cost` | 6 | 02-28 | Tiền điện T2/2026 | 0 | 1,200,000 | `cash` | ❌ | — |
| 15 | 1 | `manual_cost` | `cost` | 7 | 02-28 | Lương nhân viên T1+T2 | 0 | 6,000,000 | `cash` | ❌ | — |

**Sample data — Reversal (Order ORD-005 cancelled 25/03):**

| EntryId | BizLocId | TransType | RefType | RefId | Date | Description | Debit | Credit | Channel | IsRev | RevId |
|:-------:|:--------:|:---------:|:-------:|:-----:|:----:|-------------|------:|-------:|:-------:|:-----:|:-----:|
| 50 | 1 | `sale` | `order` | 205 | 03-10 | ORD-005: Bán hàng (tiền mặt) | 3,200,000 | 0 | `cash` | ❌ | — |
| 51 | 1 | `sale` | `order` | 205 | 03-25 | [HỦY] ORD-005: Bán hàng (tiền mặt) | 0 | 3,200,000 | `cash` | ✅ | 50 |

> **Đọc reversal**: Entry 51 reverse entry 50. Tổng net = 3,200,000 - 3,200,000 = 0. ORD-005 không còn ảnh hưởng đến DT.

---

### 3.3 AccountingSettings

**Mô tả**: Cấu hình kế toán cho mỗi location. Quan hệ 1:1 với BusinessLocation (UNIQUE constraint).

**Note**: Table đơn giản, dự phòng cho mở rộng sau (multiple currencies, fiscal year khác lịch dương, etc.).

| Column | Type | Ý nghĩa |
|--------|------|---------|
| `FiscalYearStart` | TINYINT (1-12) | Tháng bắt đầu năm tài chính. Mặc định = 1 (tháng 1). HKD Việt Nam thường dùng năm dương lịch. |
| `DefaultCurrency` | VARCHAR(3) | Đơn vị tiền tệ. Mặc định = `VND`. |

**Sample data:**

| AccountingSettingId | BusinessLocationId | FiscalYearStart | DefaultCurrency | CreatedAt |
|:-------------------:|:------------------:|:---------------:|:---------------:|:---------:|
| 1 | 1 | 1 | VND | 2026-01-01 08:00:00 |
| 2 | 2 | 1 | VND | 2026-01-15 10:00:00 |

---

### 3.4 AccountingPeriods

**Mô tả**: Kỳ kế toán — đơn vị thời gian để tổng hợp báo cáo. Có 2 loại: `quarter` (quý) và `year` (năm).

**Columns giải thích:**

| Column | Type | Ý nghĩa |
|--------|------|---------|
| `PeriodType` | VARCHAR(10) | `quarter` = kỳ quý, `year` = kỳ năm |
| `Quarter` | TINYINT? | 1-4 cho quarterly, `NULL` cho annual |
| `Status` | VARCHAR(20) | `open` → `finalized` → `reopened` (xem State Machine ở diagrams doc) |
| `FinalizedAt` | DATETIME? | Thời điểm Owner chốt kỳ |

**Unique constraint**: `(BusinessLocationId, PeriodType, Year, Quarter)` — không cho phép tạo trùng.

**Sample data:**

| PeriodId | BizLocId | Type | Year | Quarter | StartDate | EndDate | Status | FinalizedAt |
|:--------:|:--------:|:----:|:----:|:-------:|:---------:|:-------:|:------:|:-----------:|
| 1 | 1 | `quarter` | 2026 | 1 | 2026-01-01 | 2026-03-31 | `open` | NULL |
| 2 | 1 | `quarter` | 2026 | 2 | 2026-04-01 | 2026-06-30 | `open` | NULL |
| 3 | 1 | `year` | 2026 | NULL | 2026-01-01 | 2026-12-31 | `open` | NULL |

**Ví dụ sau khi finalize Q1:**

| PeriodId | Status | FinalizedAt | FinalizedByUserId |
|:--------:|:------:|:-----------:|:-----------------:|
| 1 | `finalized` | 2026-04-10 09:00:00 | u-owner-001 |

---

### 3.5 AccountingPeriodAuditLogs

**Mô tả**: Ghi lại mọi thay đổi quan trọng của kỳ kế toán. Đảm bảo audit trail cho compliance.

**Columns giải thích:**

| Column | Type | Ý nghĩa |
|--------|------|---------|
| `Action` | VARCHAR(50) | Loại sự kiện: `period_created`, `period_finalized`, `period_reopened`, `book_created`, `book_exported`, `group_suggestion` |
| `OldValue` | JSON? | Trạng thái trước thay đổi |
| `NewValue` | JSON? | Trạng thái sau thay đổi |
| `Reason` | TEXT? | Lý do — **bắt buộc** cho `period_reopened` |

**Sample data — Timeline Q1/2026:**

| LogId | PeriodId | Action | OldValue | NewValue | Reason | CreatedBy | CreatedAt |
|:-----:|:--------:|--------|----------|----------|--------|:---------:|:---------:|
| 1 | 1 | `period_created` | — | `{"periodType":"quarter","year":2026,"quarter":1}` | — | u-owner-001 | 2026-01-01 08:00 |
| 2 | 1 | `group_suggestion` | — | `{"suggestedGroup":1,"revenue":0,"rulesetVersion":"1.0.0"}` | — | system | 2026-01-01 08:01 |
| 3 | 1 | `group_suggestion` | — | `{"suggestedGroup":2,"revenue":620000000,"annualized":826666667,"rulesetVersion":"1.0.0"}` | — | system | 2026-03-15 10:00 |
| 4 | 1 | `book_created` | — | `{"bookId":1,"groupNumber":2,"taxMethod":"method_1","templateCode":"S2a"}` | — | u-owner-001 | 2026-03-20 14:00 |
| 5 | 1 | `book_exported` | — | `{"exportId":1,"bookId":1,"format":"xlsx","rowCount":342}` | — | u-owner-001 | 2026-03-31 16:00 |
| 6 | 1 | `period_finalized` | `{"status":"open"}` | `{"status":"finalized"}` | — | u-owner-001 | 2026-04-10 09:00 |
| 7 | 1 | `period_reopened` | `{"status":"finalized"}` | `{"status":"reopened"}` | Phát hiện thiếu 3 đơn hàng chưa complete | u-owner-001 | 2026-04-12 11:00 |
| 8 | 1 | `period_finalized` | `{"status":"reopened"}` | `{"status":"finalized"}` | — | u-owner-001 | 2026-04-12 15:00 |

---

### 3.6 TaxRulesets

**Mô tả**: Container version cho toàn bộ Rule Engine. Mỗi lần TT152 thay đổi → tạo version mới, data cũ vẫn giữ.

**Columns giải thích:**

| Column | Type | Ý nghĩa |
|--------|------|---------|
| `Code` | VARCHAR(50) | Mã thông tư: `TT152_2025` |
| `Version` | VARCHAR(20) | Semantic version: `1.0.0`, `1.1.0`, `2.0.0` |
| `IsActive` | BOOLEAN | Chỉ **1 ruleset active** tại 1 thời điểm. Khi activate mới → deactivate cũ. |
| `EffectiveFrom/To` | DATE | Khoảng thời gian hiệu lực pháp lý |

**Sample data:**

| RulesetId | Code | Name | Version | EffectiveFrom | EffectiveTo | IsActive |
|:---------:|:----:|------|:-------:|:-------------:|:-----------:|:--------:|
| 1 | TT152_2025 | Thông tư 152/2025/TT-BTC | 1.0.0 | 2026-01-01 | NULL | ✅ TRUE |
| 2 | TT152_2025 | TT152 — Cập nhật mức trừ DT | 1.1.0 | 2027-01-01 | NULL | ❌ FALSE |

> **Scenario version mới**: Năm 2027 Bộ Tài chính điều chỉnh mức trừ DT từ 500tr → 600tr. Admin tạo Ruleset v1.1.0, cập nhật TaxGroupRules tương ứng, rồi activate. Code Rule Engine **không đổi** — chỉ data thay đổi.

---

### 3.7 TaxGroupRules

**Mô tả**: Quy tắc phân nhóm HKD theo doanh thu. Mỗi Ruleset có đúng 4 rows (4 nhóm).

**Columns giải thích chi tiết:**

| Column | Ý nghĩa | Nhóm 1 | Nhóm 2 | Nhóm 3 | Nhóm 4 |
|--------|---------|:------:|:------:|:------:|:------:|
| `MinRevenue` | Ngưỡng dưới (≥) | 0 | 500,000,000 | 3,000,000,000 | 50,000,000,000 |
| `MaxRevenue` | Ngưỡng trên (<) | 500,000,000 | 3,000,000,000 | 50,000,000,000 | NULL (∞) |
| `VatExempt` | Miễn GTGT? | ✅ | ❌ | ❌ | ❌ |
| `PitExempt` | Miễn TNCN? | ✅ | ❌ | ❌ | ❌ |
| `AllowedTaxMethods` | Cách tính thuế | `["exempt"]` | `["method_1","method_2"]` | `["method_2"]` | `["method_2"]` |
| `PitRateMethod2` | Thuế suất TNCN Cách 2 | — | 15% | 17% | 20% |
| `RevenueDeduction` | Mức trừ DT (Cách 1) | — | 500,000,000 | — | — |
| `RequiredBooksJson` | Mẫu sổ bắt buộc | `S1a` | `S2a` hoặc `S2b-e` | `S2b-e` | `S2b-e` |
| `AnnualSettlement` | Quyết toán năm? | ❌ | ✅ | ❌ | ❌ |
| `EInvoiceRequired` | Bắt buộc hóa đơn điện tử? | ❌ | ❌ | ✅ | ✅ |

**Sample data (full row — Nhóm 2 chi tiết):**

```json
{
  "ruleId": 2,
  "rulesetId": 1,
  "groupNumber": 2,
  "groupName": "Nhóm 2",
  "groupDescription": "HKD có doanh thu từ 500 triệu đến dưới 3 tỷ/năm",
  "minRevenue": 500000000,
  "maxRevenue": 3000000000,
  "vatExempt": false,
  "pitExempt": false,
  "allowedTaxMethods": ["method_1", "method_2"],
  "defaultTaxMethod": "method_1",
  "pitRateMethod2": 0.15,
  "revenueDeduction": 500000000,
  "requiredBooksJson": {
    "method_1": ["S2a"],
    "method_2": ["S2b", "S2c", "S2d", "S2e"]
  },
  "vatReportFrequency": "quarterly",
  "pitReportFrequency": "quarterly",
  "annualSettlement": true,
  "eInvoiceRequired": false,
  "eInvoiceRevenueThreshold": 1000000000,
  "sortOrder": 2
}
```

**Giải thích `RequiredBooksJson`:**
- Nhóm 2, Cách 1: Owner chỉ cần **1 sổ S2a** (ghi DT bán hàng theo ngành, thuế tính trên DT)
- Nhóm 2, Cách 2: Owner cần **4 sổ S2b + S2c + S2d + S2e** (ghi chi tiết DT, chi phí, thuế, thanh toán → thuế tính trên lợi nhuận)

---

### 3.8 IndustryTaxRates

**Mô tả**: Thuế suất cụ thể cho từng ngành nghề. Rule Engine dùng table này để tính thuế GTGT và TNCN theo ngành.

**Columns giải thích:**

| Column | Ý nghĩa |
|--------|---------|
| `TaxType = 'VAT'` | Thuế GTGT — áp dụng cho tất cả nhóm chịu thuế (2, 3, 4). Tính trên **tổng doanh thu**. |
| `TaxType = 'PIT_METHOD_1'` | Thuế TNCN Cách 1 — chỉ áp dụng Nhóm 2. Tính trên **phần DT vượt 500 triệu**. |

> **PIT Method 2** (Cách 2): Thuế suất cố định **theo nhóm** (15%/17%/20% trên lợi nhuận), **không theo ngành** → lưu ở `TaxGroupRules.PitRateMethod2`, không cần row ở đây.

**Sample data:**

| RateId | RulesetId | BusinessTypeId | BusinessType Name | TaxType | TaxRate | Giải thích |
|:------:|:---------:|:--------------:|:------------------:|:-------:|:-------:|------------|
| 1 | 1 | bt-retail | Phân phối hàng hóa | VAT | 0.0100 | GTGT 1% trên DT |
| 2 | 1 | bt-retail | Phân phối hàng hóa | PIT_METHOD_1 | 0.0050 | TNCN 0.5% trên DT vượt 500tr |
| 3 | 1 | bt-service | Dịch vụ | VAT | 0.0500 | GTGT 5% trên DT |
| 4 | 1 | bt-service | Dịch vụ | PIT_METHOD_1 | 0.0200 | TNCN 2% trên DT vượt 500tr |
| 5 | 1 | bt-fnb | SX, DV gắn hàng hóa | VAT | 0.0300 | GTGT 3% trên DT |
| 6 | 1 | bt-fnb | SX, DV gắn hàng hóa | PIT_METHOD_1 | 0.0150 | TNCN 1.5% trên DT vượt 500tr |
| 7 | 1 | bt-transport | Vận tải | VAT | 0.0300 | GTGT 3% trên DT |
| 8 | 1 | bt-transport | Vận tải | PIT_METHOD_1 | 0.0150 | TNCN 1.5% trên DT vượt 500tr |

**Ví dụ tính thuế cho cửa hàng Minh Phát (DT Q1 = 620tr):**

```
Bán lẻ hàng hóa (bt-retail):   DT = 480,000,000đ
  → GTGT = 480,000,000 × 1%    = 4,800,000đ
  → TNCN Cách 1 = (480,000,000 - 500,000,000) × 0.5% = 0đ  (chưa vượt 500tr riêng ngành này)

Dịch vụ (bt-service):          DT = 140,000,000đ
  → GTGT = 140,000,000 × 5%    = 7,000,000đ
  → TNCN Cách 1 = 0đ           (DT ngành < 500tr)

NHƯNG! Mức trừ 500tr chỉ tính 1 lần cho TOÀN BỘ HKD:
  → Tổng DT = 620,000,000đ
  → Phần vượt 500tr = 120,000,000đ
  → Phân bổ theo tỷ trọng:
    - Retail: 120,000,000 × (480/620) = 92,903,226đ → TNCN = 92,903,226 × 0.5% = 464,516đ
    - Service: 120,000,000 × (140/620) = 27,096,774đ → TNCN = 27,096,774 × 2% = 541,935đ
  → Tổng TNCN Cách 1 = 1,006,451đ
```

---

### 3.9 AccountingTemplates

**Mô tả**: Định nghĩa các mẫu sổ kế toán theo TT152. Mỗi mẫu gắn với nhóm HKD cụ thể.

**Sample data:**

| TemplateId | TemplateCode | Name | ApplicableGroups | ApplicableMethods | IsActive |
|:----------:|:------------:|------|:----------------:|:-----------------:|:--------:|
| 1 | S1a | Sổ chi tiết bán hàng (đơn giản) | `[1]` | `null` | ✅ |
| 2 | S2a | Sổ chi tiết bán hàng (theo ngành) | `[2]` | `["method_1"]` | ✅ |
| 3 | S2b | Sổ chi tiết bán hàng (chi tiết) | `[2,3,4]` | `["method_2"]` | ✅ |
| 4 | S2c | Sổ chi tiết chi phí | `[2,3,4]` | `["method_2"]` | ✅ |
| 5 | S2d | Sổ theo dõi nghĩa vụ thuế | `[2,3,4]` | `["method_2"]` | ✅ |
| 6 | S2e | Sổ theo dõi tình hình thanh toán | `[2,3,4]` | `["method_2"]` | ✅ |

**Ma trận nhóm × sổ:**

| | S1a | S2a | S2b | S2c | S2d | S2e |
|:-:|:---:|:---:|:---:|:---:|:---:|:---:|
| **Nhóm 1** | ✅ | — | — | — | — | — |
| **Nhóm 2 Cách 1** | — | ✅ | — | — | — | — |
| **Nhóm 2 Cách 2** | — | — | ✅ | ✅ | ✅ | ✅ |
| **Nhóm 3** | — | — | ✅ | ✅ | ✅ | ✅ |
| **Nhóm 4** | — | — | ✅ | ✅ | ✅ | ✅ |

---

### 3.10 AccountingTemplateVersions

**Mô tả**: Phiên bản cụ thể của mỗi mẫu sổ. Cho phép cập nhật format/cột mà không mất dữ liệu cũ.

**Sample data:**

| TVId | TemplateId | TemplateCode | VersionLabel | IsActive | EffectiveFrom | TemplateFileUrl | ChangeNotes |
|:----:|:----------:|:------------:|:------------:|:--------:|:-------------:|:---------------:|-------------|
| 1 | 1 | S1a | v1.0 | ✅ | 2026-01-01 | `.../templates/s1a_v1.xlsx` | Initial version |
| 2 | 2 | S2a | v1.0 | ✅ | 2026-01-01 | `.../templates/s2a_v1.xlsx` | Initial version |
| 3 | 3 | S2b | v1.0 | ✅ | 2026-01-01 | `.../templates/s2b_v1.xlsx` | Initial version |
| 4 | 4 | S2c | v1.0 | ✅ | 2026-01-01 | `.../templates/s2c_v1.xlsx` | Initial version |
| 5 | 5 | S2d | v1.0 | ✅ | 2026-01-01 | `.../templates/s2d_v1.xlsx` | Initial version |
| 6 | 6 | S2e | v1.0 | ✅ | 2026-01-01 | `.../templates/s2e_v1.xlsx` | Initial version |

---

### 3.11 TemplateFieldMappings

**Mô tả**: Mapping logic — bảng này nói cho hệ thống biết cách lấy data từ DB để render vào từng cột của sổ kế toán.

**Columns giải thích chi tiết:**

| Column | Ý nghĩa | Ví dụ |
|--------|---------|-------|
| `FieldCode` | Code cột duy nhất | `stt`, `date`, `revenue`, `vat_amount` |
| `FieldLabel` | Nhãn hiển thị | "STT", "Ngày tháng", "Doanh thu" |
| `FieldType` | Kiểu dữ liệu | `auto_increment`, `date`, `text`, `decimal`, `computed` |
| `SourceType` | Cách lấy data | `query` (từ DB), `formula` (tính toán), `static` (giá trị cố định), `auto` (hệ thống tự tạo) |
| `SourceEntity` | Table nguồn | `orders`, `order_details`, `gl_entries`, `costs`, `tax_payments` |
| `SourceField` | Column cụ thể | `TotalAmount`, `CompletedAt`, `CostDate` |
| `FilterJson` | Điều kiện lọc | `{"transactionType":"sale","moneyChannel":"cash"}` |
| `AggregationType` | Cách tập hợp | `sum` (cộng dồn), `count`, `avg`, `none` (render per row) |
| `FormulaExpression` | Công thức tính | `revenue * vat_rate` |
| `DependsOn` | Cột phụ thuộc | `["revenue","vat_rate"]` |
| `ExportColumn` | Cột Excel | `A`, `B`, `C`... |

**Sample data — S1a (4 cột đơn giản):**

| MId | TVId | FieldCode | FieldLabel | FieldType | SourceType | SourceEntity | SourceField | Filter | Agg | Formula | ExportCol | Sort |
|:---:|:----:|:---------:|:----------:|:---------:|:----------:|:------------:|:-----------:|:------:|:---:|:-------:|:---------:|:----:|
| 1 | 1 | `stt` | STT | auto_increment | auto | — | — | — | — | — | A | 1 |
| 2 | 1 | `date` | Ngày tháng | date | query | orders | CompletedAt | — | none | — | B | 2 |
| 3 | 1 | `description` | Nội dung | text | query | orders | OrderCode | — | none | — | C | 3 |
| 4 | 1 | `revenue` | Doanh thu | decimal | query | orders | TotalAmount | — | none | — | D | 4 |

**Sample data — S2a (6 cột — thêm thuế suất):**

| MId | TVId | FieldCode | FieldLabel | FieldType | SourceType | SourceEntity | SourceField | Formula | ExportCol | Sort |
|:---:|:----:|:---------:|:----------:|:---------:|:----------:|:------------:|:-----------:|:-------:|:---------:|:----:|
| 5 | 2 | `stt` | STT | auto_increment | auto | — | — | — | A | 1 |
| 6 | 2 | `date` | Ngày | date | query | orders | CompletedAt | — | B | 2 |
| 7 | 2 | `description` | Nội dung | text | query | orders | OrderCode | — | C | 3 |
| 8 | 2 | `revenue` | Doanh thu | decimal | query | order_details | Amount | — | D | 4 |
| 9 | 2 | `vat_rate` | Tỷ lệ GTGT | decimal | query | industry_tax_rates | TaxRate | — | E | 5 |
| 10 | 2 | `vat_amount` | Thuế GTGT | computed | formula | — | — | `revenue * vat_rate` | F | 6 |

**Sample data — S2e (8 cột — from GL entries):**

| MId | TVId | FieldCode | FieldLabel | FieldType | SourceType | SourceEntity | SourceField | Filter | ExportCol | Sort |
|:---:|:----:|:---------:|:----------:|:---------:|:----------:|:------------:|:-----------:|:------:|:---------:|:----:|
| 30 | 6 | `stt` | STT | auto_increment | auto | — | — | — | A | 1 |
| 31 | 6 | `date` | Ngày | date | query | gl_entries | EntryDate | — | B | 2 |
| 32 | 6 | `description` | Nội dung | text | query | gl_entries | Description | — | C | 3 |
| 33 | 6 | `cash_in` | Thu TM | decimal | query | gl_entries | DebitAmount | `{"moneyChannel":"cash","transactionType":["sale"]}` | D | 4 |
| 34 | 6 | `bank_in` | Thu CK | decimal | query | gl_entries | DebitAmount | `{"moneyChannel":"bank","transactionType":["sale"]}` | E | 5 |
| 35 | 6 | `cash_out` | Chi TM | decimal | query | gl_entries | CreditAmount | `{"moneyChannel":"cash"}` | F | 6 |
| 36 | 6 | `bank_out` | Chi CK | decimal | query | gl_entries | CreditAmount | `{"moneyChannel":"bank"}` | G | 7 |
| 37 | 6 | `debt_out` | Ghi nợ | decimal | query | gl_entries | DebitAmount | `{"moneyChannel":"debt","transactionType":"sale"}` | H | 8 |
| 38 | 6 | `debt_in` | Thu nợ | decimal | query | gl_entries | DebitAmount | `{"transactionType":"debt_payment"}` | I | 9 |

---

### 3.12 AccountingBooks

**Mô tả**: Sổ kế toán đã tạo — là "saved configuration" cho live view. **Không lưu data** — data luôn query realtime từ GL/Orders/Costs.

**Columns giải thích:**

| Column | Ý nghĩa |
|--------|---------|
| `PeriodId` | Thuộc kỳ kế toán nào |
| `TemplateVersionId` | Dùng version nào của template để render |
| `GroupNumber` | Owner đã chọn nhóm nào (1-4) |
| `TaxMethod` | Cách tính thuế: `method_1`, `method_2`, `exempt` |
| `RulesetId` | Version Rule Engine lúc tạo (audit trail) |
| `BusinessTypeId` | Lọc theo ngành — `NULL` = tất cả, NOT NULL = 1 ngành cụ thể |
| `Status` | `active` = đang dùng, `archived` = không dùng nữa |

**Sample data — Cửa hàng Minh Phát Q1/2026:**

| BookId | BizLocId | PeriodId | TVId | Group | Method | RulesetId | BusinessTypeId | Status | CreatedBy | CreatedAt |
|:------:|:--------:|:--------:|:----:|:-----:|:------:|:---------:|:--------------:|:------:|:---------:|:---------:|
| 1 | 1 | 1 | 2 | 2 | method_1 | 1 | bt-retail | active | u-owner-001 | 2026-03-20 14:00 |
| 2 | 1 | 1 | 2 | 2 | method_1 | 1 | bt-service | active | u-owner-001 | 2026-03-20 14:00 |

> **Giải thích**: Owner chọn Nhóm 2 Cách 1 → hệ thống cần sổ S2a. Vì location có 2 ngành (retail + service), hệ thống tự tạo **2 books** — mỗi ngành 1 sổ S2a riêng.

**Ví dụ Owner thử tạo sổ Nhóm 2 Cách 2 (so sánh):**

| BookId | PeriodId | TVId | Group | Method | BusinessTypeId | Status | Ghi chú |
|:------:|:--------:|:----:|:-----:|:------:|:--------------:|:------:|---------|
| 3 | 1 | 3 | 2 | method_2 | NULL | active | S2b — bán hàng chi tiết (tất cả ngành) |
| 4 | 1 | 4 | 2 | method_2 | NULL | active | S2c — chi phí |
| 5 | 1 | 5 | 2 | method_2 | NULL | active | S2d — nghĩa vụ thuế |
| 6 | 1 | 6 | 2 | method_2 | NULL | active | S2e — thanh toán |

> Owner giờ có **6 books** trong Q1 — 2 sổ Cách 1 + 4 sổ Cách 2. Xem cả 2 bộ, so sánh thuế phải nộp, rồi chọn cách có lợi hơn để export nộp thuế.

---

### 3.13 AccountingExports

**Mô tả**: Snapshot mỗi lần xuất sổ. Bản chụp tại thời điểm — không thay đổi sau khi tạo.

**Columns giải thích:**

| Column | Ý nghĩa |
|--------|---------|
| `SummaryJson` | Snapshot số liệu tổng hợp lúc xuất |
| `DataRowCount` | Số dòng dữ liệu trong file |
| `ExportFormat` | `pdf` hoặc `xlsx` |
| `FileUrl` | URL file trên Cloudinary |
| `RulesetVersion` | Version Rule Engine lúc xuất (audit) |

**Sample data:**

| ExportId | BookId | Group | Method | RulesetVer | DataRows | Format | ExportedAt | Notes |
|:--------:|:------:|:-----:|:------:|:----------:|:--------:|:------:|:----------:|-------|
| 1 | 1 | 2 | method_1 | 1.0.0 | 285 | xlsx | 2026-03-31 16:00 | Xuất lần 1 |
| 2 | 2 | 2 | method_1 | 1.0.0 | 57 | xlsx | 2026-03-31 16:05 | Xuất lần 1 — DV |
| 3 | 1 | 2 | method_1 | 1.0.0 | 288 | xlsx | 2026-04-12 15:30 | Xuất lần 2 — sau bổ sung 3 đơn |

**SummaryJson mẫu (Export 1 — S2a Bán lẻ hàng hóa):**

```json
{
  "bookId": 1,
  "templateCode": "S2a",
  "periodLabel": "Q1/2026",
  "businessTypeName": "Phân phối hàng hóa",
  "groupNumber": 2,
  "taxMethod": "method_1",
  "dataRowCount": 285,
  "totalRevenue": 480000000,
  "totalVat": 4800000,
  "totalPit": 464516,
  "vatRate": 0.01,
  "pitRate": 0.005,
  "revenueDeduction": 500000000,
  "revenueExcess": 92903226,
  "generatedAt": "2026-03-31T16:00:00Z",
  "rulesetVersion": "1.0.0"
}
```

**So sánh Export 1 vs Export 3 (cùng BookId = 1, sau bổ sung 3 đơn):**

| Metric | Export 1 (31/03) | Export 3 (12/04) | Chênh lệch |
|--------|:----------------:|:----------------:|:-----------:|
| Số dòng | 285 | 288 | +3 |
| Doanh thu | 480,000,000 | 486,000,000 | +6,000,000 |
| GTGT | 4,800,000 | 4,860,000 | +60,000 |

---

### 3.14 TaxPayments

**Mô tả**: Owner ghi nhận thuế đã nộp cho cơ quan thuế. Dùng cho sổ S2d (theo dõi nghĩa vụ thuế) — cột "Đã nộp".

**Columns giải thích:**

| Column | Ý nghĩa |
|--------|---------|
| `TaxType` | `VAT` = Thuế GTGT, `PIT` = Thuế TNCN |
| `PeriodId` | Thuế nộp cho kỳ nào (optional — có thể nộp trước khi tạo period) |
| `ReferenceNumber` | Số biên lai hoặc mã giao dịch ngân hàng |

**Sample data:**

| TaxPaymentId | BizLocId | PeriodId | TaxType | Amount | PaidAt | PaymentMethod | RefNumber | Notes |
|:------------:|:--------:|:--------:|:-------:|-------:|:------:|:-------------:|:---------:|-------|
| 1 | 1 | NULL | VAT | 3,500,000 | 2026-02-20 | bank | BL-202602-001 | Nộp GTGT Q4/2025 |
| 2 | 1 | 1 | VAT | 11,800,000 | 2026-04-20 | bank | BL-202604-001 | Nộp GTGT Q1/2026 |
| 3 | 1 | 1 | PIT | 1,006,451 | 2026-04-20 | bank | BL-202604-002 | Nộp TNCN Q1/2026 (Cách 1) |

> **TaxPayment #1**: `PeriodId = NULL` vì nộp thuế Q4/2025 trước khi tạo period Q1/2026. Hệ thống vẫn ghi nhận, vẫn tạo GL entry. Khi nhìn sổ S2d, entry này nằm ngoài kỳ Q1.

---

## 4. Data Flow Walkthrough

Theo dõi **một đơn hàng ORD-001** xuyên suốt hệ thống:

### Step 1: Order Created (Pending)

```
Order ORD-001 (pending)
├── Xi măng HT × 50 bao × 95,000đ = 4,750,000đ (bt-retail)
├── DV cắt sắt = 1,200,000đ (bt-service)
├── Total = 5,950,000đ
└── Chưa có GL entry, chưa có ảnh hưởng kế toán
```

**Affected tables**: Chỉ `Orders + OrderDetails`

### Step 2: Order Completed

```
Order ORD-001 → completed
├── CashAmount = 4,000,000đ
├── DebtAmount = 1,950,000đ (Anh Ba)
│
├── GL entries tạo:
│   ├── Entry 3: Debit 4,000,000 | cash | sale | ref: order/201
│   └── Entry 4: Debit 1,950,000 | debt | sale | ref: order/201
│
├── Stock giảm: Xi măng -50 bao (xem order-flow.md)
└── Debtor Anh Ba: CurrentBalance thêm -1,950,000đ
```

**Affected tables**: `Orders` (status), `GeneralLedgerEntries` (+2 rows), `Products` (stock), `Debtors` (balance), `DebtorPaymentTransactions` (+1 row)

### Step 3: Data hiển thị trong sổ

```
Sổ S2a (Book ID 1, bt-retail):
  → Row: 15/01 | ORD-001: Xi măng HT 50 bao | 4,750,000 | VAT 1% | 47,500đ
  
Sổ S2a (Book ID 2, bt-service):
  → Row: 15/01 | ORD-001: DV cắt sắt | 1,200,000 | VAT 5% | 60,000đ

Sổ S2e (thanh toán):
  → Row: 15/01 | ORD-001 | Thu TM: 4,000,000 | Ghi nợ: 1,950,000

Dashboard:
  → todayRevenue += 5,950,000đ
  → todayCashIn += 4,000,000đ
```

### Step 4: Anh Ba trả nợ (25/01)

```
DebtorPaymentTransaction: Anh Ba trả 1,000,000đ (tiền mặt)
│
├── GL entry:
│   └── Entry 6: Debit 1,000,000 | cash | debt_payment | ref: debtor_payment/301
│
├── Debtor Anh Ba: CurrentBalance += 1,000,000đ (giảm nợ)
│
└── Sổ S2e thêm row:
    → 25/01 | Thu nợ Anh Ba | Thu TM: — | Thu nợ: 1,000,000
    (Lưu ý: Thu nợ KHÔNG phải doanh thu — DT đã ghi ở step 2)
```

### Step 5: Export sổ Q1/2026

```
Owner bấm Export cho Book ID 1 (S2a, bt-retail):
│
├── Hệ thống query Orders + OrderDetails WHERE bt-retail, Q1/2026
│   → 285 rows
│
├── Tính summary:
│   → totalRevenue = 480,000,000đ
│   → totalVat = 4,800,000đ
│   → totalPit = 464,516đ
│
├── Render vào template s2a_v1.xlsx
│   → Upload Cloudinary
│   → fileUrl = "https://res.cloudinary.com/.../s2a_q1_retail.xlsx"
│
└── Tạo AccountingExport record (ExportId = 1)
    → SummaryJson = {...snapshot...}
    → Frozen — không bao giờ thay đổi
```

---

## 5. Cross-Entity Queries

### Query 1: Tổng doanh thu Q1 theo ngành (from GL)

```sql
SELECT 
    p.BusinessTypeId,
    bt.Name AS BusinessTypeName,
    SUM(CASE WHEN gle.IsReversal = FALSE THEN gle.DebitAmount ELSE 0 END) 
    - SUM(CASE WHEN gle.IsReversal = TRUE THEN gle.CreditAmount ELSE 0 END) AS NetRevenue
FROM GeneralLedgerEntries gle
JOIN Orders o ON gle.ReferenceId = o.OrderId AND gle.ReferenceType = 'order'
JOIN OrderDetails od ON o.OrderId = od.OrderId
JOIN Products p ON od.ProductId = p.ProductId
JOIN BusinessTypes bt ON p.BusinessTypeId = bt.BusinessTypeId
WHERE gle.BusinessLocationId = 1
  AND gle.TransactionType = 'sale'
  AND gle.EntryDate BETWEEN '2026-01-01' AND '2026-03-31'
GROUP BY p.BusinessTypeId, bt.Name;

-- Kết quả:
-- | BusinessType      | NetRevenue    |
-- |-------------------|---------------|
-- | Bán lẻ hàng hóa   | 480,000,000   |
-- | Dịch vụ           | 140,000,000   |
```

### Query 2: Cash flow thực tế Q1 (from GL)

```sql
SELECT 
    MoneyChannel,
    SUM(DebitAmount) AS TotalIn,
    SUM(CreditAmount) AS TotalOut,
    SUM(DebitAmount) - SUM(CreditAmount) AS NetFlow
FROM GeneralLedgerEntries
WHERE BusinessLocationId = 1
  AND EntryDate BETWEEN '2026-01-01' AND '2026-03-31'
  AND MoneyChannel IN ('cash', 'bank')  -- Chỉ tiền thực tế
GROUP BY MoneyChannel;

-- Kết quả:
-- | Channel | TotalIn     | TotalOut    | NetFlow     |
-- |---------|-------------|------------|-------------|
-- | cash    | 450,000,000 | 20,600,000 | 429,400,000 |
-- | bank    | 120,000,000 | 75,000,000 | 45,000,000  |
```

### Query 3: Lịch sử export của 1 book

```sql
SELECT 
    ae.ExportId,
    ae.ExportedAt,
    ae.DataRowCount,
    ae.ExportFormat,
    JSON_EXTRACT(ae.SummaryJson, '$.totalRevenue') AS Revenue,
    JSON_EXTRACT(ae.SummaryJson, '$.totalVat') AS VAT,
    ae.Notes
FROM AccountingExports ae
WHERE ae.BookId = 1
ORDER BY ae.ExportedAt;

-- Kết quả:
-- | ExportId | ExportedAt       | Rows | Revenue     | VAT       | Notes                           |
-- |----------|------------------|------|-------------|-----------|----------------------------------|
-- | 1        | 2026-03-31 16:00 | 285  | 480,000,000 | 4,800,000 | Xuất lần 1                       |
-- | 3        | 2026-04-12 15:30 | 288  | 486,000,000 | 4,860,000 | Xuất lần 2 — sau bổ sung 3 đơn  |
```

### Query 4: Kiểm tra nghĩa vụ thuế (S2d data)

```sql
-- Tính thuế phải nộp (Rule Engine tính):
-- VAT: tổng DT × VAT rate per ngành
-- PIT: (tổng DT - mức trừ) × PIT rate per ngành (Cách 1) hoặc (DT - CP) × PitRateMethod2 (Cách 2)

-- Thuế đã nộp:
SELECT 
    tp.TaxType,
    SUM(tp.Amount) AS TotalPaid
FROM TaxPayments tp
WHERE tp.BusinessLocationId = 1
  AND tp.PaidAt BETWEEN '2026-01-01' AND '2026-03-31'
  AND tp.DeletedAt IS NULL
GROUP BY tp.TaxType;

-- Kết quả:
-- | TaxType | TotalPaid  |
-- |---------|------------|
-- | VAT     | 3,500,000  |  (Q4/2025, nộp trong Q1)

-- Còn nợ: Phải nộp Q1 - Đã nộp Q1
-- VAT: 11,800,000 - 0 = 11,800,000đ (chưa nộp Q1)
-- PIT: 1,006,451 - 0 = 1,006,451đ (chưa nộp Q1)
```
