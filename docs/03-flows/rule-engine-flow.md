# Rule Engine Flow

> **Module**: Report & Accounting — Rule Engine (Independent, Versioned)
> Quay về [report-accounting-flow.md](report-accounting-flow.md) (index)

---

## Mục lục

1. [Entity Design](#1-entity-design)
   - [1.1 TaxRulesets](#11-taxrulesets-version-container)
   - [1.2 TaxGroupRules](#12-taxgrouprules-phân-nhóm-hkd--sql--json-hybrid) — SQL + JSON Hybrid
   - [1.3 IndustryTaxRates](#13-industrytaxrates-thuế-suất-theo-ngành)
2. [Architecture](#2-architecture)
   - [2.1 Design: SQL + JSON Hybrid](#21-design-sql--json-hybrid)
   - [2.2 Service Flow](#22-service-flow)
3. [Evaluation Logic](#3-evaluation-logic)
4. [API: Get Group Suggestion](#4-api-get-group-suggestion)
5. [Business Rules](#5-business-rules)
6. [API Endpoints](#6-api-endpoints)
7. [Error Codes](#7-error-codes)

---

## 1. Entity Design

### 1.1 TaxRulesets (Version container)

```sql
-- =============================================
-- TAX RULESETS TABLE (Version container cho Rule Engine)
-- =============================================
CREATE TABLE TaxRulesets (
    RulesetId INT AUTO_INCREMENT PRIMARY KEY,
    
    -- Identity
    Code VARCHAR(50) NOT NULL COMMENT 'Unique code: TT152_2025',
    Name VARCHAR(200) NOT NULL COMMENT 'Thông tư 152/2025/TT-BTC',
    Description TEXT DEFAULT NULL,
    Version VARCHAR(20) NOT NULL COMMENT 'Semantic versioning: 1.0.0',
    
    -- Lifecycle
    EffectiveFrom DATE NOT NULL COMMENT 'Ngày bắt đầu hiệu lực',
    EffectiveTo DATE DEFAULT NULL COMMENT 'NULL = vô thời hạn',
    IsActive BOOLEAN NOT NULL DEFAULT FALSE COMMENT 'Chỉ 1 active tại 1 thời điểm',
    
    -- Audit
    CreatedByUserId CHAR(36) DEFAULT NULL,
    CreatedAt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE INDEX idx_ruleset_code_version (Code, Version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class TaxRuleset
{
    public int RulesetId { get; set; }
    
    public string Code { get; set; } = null!;
    public string Name { get; set; } = null!;
    public string? Description { get; set; }
    public string Version { get; set; } = null!;
    
    public DateOnly EffectiveFrom { get; set; }
    public DateOnly? EffectiveTo { get; set; }
    public bool IsActive { get; set; }
    
    public Guid? CreatedByUserId { get; set; }
    public DateTime CreatedAt { get; set; }
    
    // Navigation
    public virtual ICollection<TaxGroupRule> GroupRules { get; set; } = new List<TaxGroupRule>();
    public virtual ICollection<IndustryTaxRate> IndustryTaxRates { get; set; } = new List<IndustryTaxRate>();
}
```

### 1.2 TaxGroupRules (Phân nhóm HKD — SQL + JSON Hybrid)

> **Design Decision**: Dùng SQL + JSON hybrid thay vì hard-coded columns.
> Lý do: Luật thuế thay đổi thường xuyên (số nhóm, ngưỡng DT, tiêu chí mới như số nhân viên, vốn đầu tư...).
> Với JSON hybrid, khi luật đổi chỉ cần tạo ruleset version mới với JSON structure khác — **không cần ALTER TABLE, không cần deploy code mới**.
>
> Đã cân nhắc và loại bỏ:
> - **Full NoSQL (MongoDB)**: Overkill cho data nhỏ (~4-5 rules/ruleset), thêm infrastructure + cross-DB FK pain
> - **EAV pattern** (key-value rows): Khó query, khó debug, khó maintain
> - **Hard-coded columns** (v1 cũ): Mỗi lần luật đổi phải ALTER TABLE + sửa C# entity

```sql
-- =============================================
-- TAX GROUP RULES TABLE (SQL + JSON Hybrid)
-- Structured columns: identity + ordering (ít thay đổi)
-- JSON columns: conditions + outcomes (linh hoạt theo luật)
-- =============================================
CREATE TABLE TaxGroupRules (
    RuleId INT AUTO_INCREMENT PRIMARY KEY,
    RulesetId INT NOT NULL,
    
    -- ═══ GROUP IDENTITY (structured — ít thay đổi) ═══
    GroupNumber TINYINT NOT NULL COMMENT '1, 2, 3, 4 (hoặc nhiều hơn nếu luật mới)',
    GroupName VARCHAR(100) NOT NULL COMMENT 'Nhóm 1, Nhóm 2...',
    GroupDescription TEXT DEFAULT NULL,
    
    -- ═══ MATCHING CONDITIONS (JSON — linh hoạt) ═══
    ConditionsJson JSON NOT NULL COMMENT 'Tiêu chí phân nhóm: revenue, employees, capital...',
    -- VD hiện tại (TT152): {"minRevenue":500000000, "maxRevenue":3000000000}
    -- VD tương lai:        {"minRevenue":..., "maxRevenue":..., "minEmployees":1, "maxEmployees":10}
    
    -- ═══ OUTCOMES (JSON — linh hoạt) ═══
    OutcomesJson JSON NOT NULL COMMENT 'Kết quả khi match: tax methods, rates, books, reporting...',
    -- Chứa toàn bộ: vatExempt, pitExempt, allowedTaxMethods, requiredBooks,
    -- reportFrequency, eInvoice, deduction... Thêm field mới KHÔNG cần ALTER TABLE.
    
    -- Ordering
    SortOrder INT NOT NULL DEFAULT 0,
    
    -- Indexes & FKs
    CONSTRAINT fk_tgr_ruleset FOREIGN KEY (RulesetId) 
        REFERENCES TaxRulesets(RulesetId),
    INDEX idx_tgr_ruleset (RulesetId),
    UNIQUE INDEX idx_tgr_ruleset_group (RulesetId, GroupNumber)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**JSON Schema definitions:**

```jsonc
// ConditionsJson — tiêu chí matching
{
  "minRevenue": 500000000,        // decimal, inclusive (≥)
  "maxRevenue": 3000000000,       // decimal | null, exclusive (<), null = unlimited
  // Future fields (thêm khi luật đổi, KHÔNG cần ALTER TABLE):
  // "minEmployees": 1,
  // "maxEmployees": 10,
  // "minCapital": 0,
  // "businessCategories": ["retail", "service"]
}

// OutcomesJson — kết quả khi match
{
  // Tax exemptions
  "vatExempt": false,
  "pitExempt": false,
  
  // Tax methods
  "allowedTaxMethods": ["method_1", "method_2"],
  "defaultTaxMethod": "method_1",
  
  // PIT rates
  "pitRateMethod2": 0.15,           // Cách 2: thuế suất cố định theo nhóm
  "revenueDeduction": 500000000,    // Cách 1: mức trừ DT (Nhóm 2)
  
  // Required books
  "requiredBooks": {
    "method_1": ["S2a"],
    "method_2": ["S2b", "S2c", "S2d", "S2e"]
  },
  
  // Reporting obligations
  "vatReportFrequency": "quarterly",   // quarterly | monthly | exempt
  "pitReportFrequency": "quarterly",   // quarterly | exempt
  "annualSettlement": true,             // Quyết toán năm?
  
  // E-Invoice
  "eInvoiceRequired": false,
  "eInvoiceRevenueThreshold": 1000000000
  
  // Future: thêm bất kỳ field mới mà không cần schema change
}
```

```csharp
// ═══ Entity (slim — chỉ structured columns) ═══
public class TaxGroupRule
{
    public int RuleId { get; set; }
    public int RulesetId { get; set; }
    
    public int GroupNumber { get; set; }
    public string GroupName { get; set; } = null!;
    public string? GroupDescription { get; set; }
    
    public string ConditionsJson { get; set; } = null!;   // JSON
    public string OutcomesJson { get; set; } = null!;     // JSON
    
    public int SortOrder { get; set; }
    
    // Navigation
    public virtual TaxRuleset Ruleset { get; set; } = null!;
}

// ═══ DTOs for JSON deserialization (type-safe in C#) ═══
public class GroupConditions
{
    public decimal MinRevenue { get; set; }
    public decimal? MaxRevenue { get; set; }
    
    // Future: thêm properties mới khi luật đổi
    // public int? MinEmployees { get; set; }
    // public int? MaxEmployees { get; set; }
    // public decimal? MinCapital { get; set; }
}

public class GroupOutcomes
{
    // Tax exemptions
    public bool VatExempt { get; set; }
    public bool PitExempt { get; set; }
    
    // Tax methods
    public List<string> AllowedTaxMethods { get; set; } = new();
    public string? DefaultTaxMethod { get; set; }
    public decimal? PitRateMethod2 { get; set; }
    public decimal? RevenueDeduction { get; set; }
    
    // Required books
    public Dictionary<string, List<string>> RequiredBooks { get; set; } = new();
    
    // Reporting
    public string VatReportFrequency { get; set; } = "quarterly";
    public string? PitReportFrequency { get; set; }
    public bool AnnualSettlement { get; set; }
    
    // E-Invoice
    public bool EInvoiceRequired { get; set; }
    public decimal? EInvoiceRevenueThreshold { get; set; }
    
    // JsonExtensionData: capture bất kỳ field mới nào chưa có property
    [JsonExtensionData]
    public Dictionary<string, JsonElement>? ExtensionData { get; set; }
}
```

> **Lưu ý `[JsonExtensionData]`**: Khi Admin thêm field mới vào `OutcomesJson` (VD: `"newTaxCredit": 100000`),
> C# tự capture vào `ExtensionData` mà không cần deploy code mới. Frontend đọc từ API response và hiển thị.

**Sample data (TT152/2025 v1.0):**

```sql
INSERT INTO TaxRulesets (Code, Name, Version, EffectiveFrom, IsActive) VALUES
('TT152_2025', 'Thông tư 152/2025/TT-BTC', '1.0.0', '2026-01-01', TRUE);

-- RulesetId = 1
INSERT INTO TaxGroupRules 
(RulesetId, GroupNumber, GroupName, ConditionsJson, OutcomesJson, SortOrder) VALUES

-- Nhóm 1: DT < 500 triệu → miễn VAT + PIT
(1, 1, 'Nhóm 1',
 '{"minRevenue":0,"maxRevenue":500000000}',
 '{"vatExempt":true,"pitExempt":true,"allowedTaxMethods":["exempt"],"defaultTaxMethod":"exempt","requiredBooks":{"default":["S1a"]},"vatReportFrequency":"quarterly","pitReportFrequency":"exempt","annualSettlement":false,"eInvoiceRequired":false}',
 1),

-- Nhóm 2: 500 triệu ≤ DT < 3 tỷ → Cách 1 hoặc Cách 2
(1, 2, 'Nhóm 2',
 '{"minRevenue":500000000,"maxRevenue":3000000000}',
 '{"vatExempt":false,"pitExempt":false,"allowedTaxMethods":["method_1","method_2"],"defaultTaxMethod":"method_1","pitRateMethod2":0.15,"revenueDeduction":500000000,"requiredBooks":{"method_1":["S2a"],"method_2":["S2b","S2c","S2d","S2e"]},"vatReportFrequency":"quarterly","pitReportFrequency":"quarterly","annualSettlement":true,"eInvoiceRequired":false,"eInvoiceRevenueThreshold":1000000000}',
 2),

-- Nhóm 3: 3 tỷ ≤ DT < 50 tỷ → chỉ Cách 2
(1, 3, 'Nhóm 3',
 '{"minRevenue":3000000000,"maxRevenue":50000000000}',
 '{"vatExempt":false,"pitExempt":false,"allowedTaxMethods":["method_2"],"defaultTaxMethod":"method_2","pitRateMethod2":0.17,"requiredBooks":{"method_2":["S2b","S2c","S2d","S2e"]},"vatReportFrequency":"quarterly","annualSettlement":false,"eInvoiceRequired":true}',
 3),

-- Nhóm 4: DT ≥ 50 tỷ → chỉ Cách 2, báo cáo monthly
(1, 4, 'Nhóm 4',
 '{"minRevenue":50000000000,"maxRevenue":null}',
 '{"vatExempt":false,"pitExempt":false,"allowedTaxMethods":["method_2"],"defaultTaxMethod":"method_2","pitRateMethod2":0.20,"requiredBooks":{"method_2":["S2b","S2c","S2d","S2e"]},"vatReportFrequency":"monthly","annualSettlement":false,"eInvoiceRequired":true}',
 4);
```

### 1.3 IndustryTaxRates (Thuế suất theo ngành)

```sql
-- =============================================
-- INDUSTRY TAX RATES TABLE (Thuế suất theo ngành nghề)
-- =============================================
CREATE TABLE IndustryTaxRates (
    RateId INT AUTO_INCREMENT PRIMARY KEY,
    RulesetId INT NOT NULL,
    BusinessTypeId CHAR(36) NOT NULL,
    
    -- Tax type
    TaxType VARCHAR(20) NOT NULL,
    -- 'VAT'            Thuế GTGT (% trên DT, tất cả nhóm chịu thuế)
    -- 'PIT_METHOD_1'   Thuế TNCN Cách 1 (% trên DT vượt 500tr, chỉ Nhóm 2)
    
    -- Rate
    TaxRate DECIMAL(5,4) NOT NULL COMMENT 'VD: 0.0100 = 1%, 0.0050 = 0.5%',
    
    -- Description
    Description VARCHAR(200) DEFAULT NULL,
    
    -- Indexes & FKs
    CONSTRAINT fk_itr_ruleset FOREIGN KEY (RulesetId) 
        REFERENCES TaxRulesets(RulesetId),
    CONSTRAINT fk_itr_business_type FOREIGN KEY (BusinessTypeId) 
        REFERENCES BusinessTypes(BusinessTypeId),
    INDEX idx_itr_ruleset (RulesetId),
    UNIQUE INDEX idx_itr_unique (RulesetId, BusinessTypeId, TaxType)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

```csharp
public class IndustryTaxRate
{
    public int RateId { get; set; }
    public int RulesetId { get; set; }
    public Guid BusinessTypeId { get; set; }
    
    public string TaxType { get; set; } = null!;
    public decimal TaxRate { get; set; }
    public string? Description { get; set; }
    
    // Navigation
    public virtual TaxRuleset Ruleset { get; set; } = null!;
    public virtual BusinessType BusinessType { get; set; } = null!;
}
```

**Sample data:**

```sql
-- Giả sử: bt-retail, bt-service, bt-fnb, bt-transport là BusinessTypeId
INSERT INTO IndustryTaxRates (RulesetId, BusinessTypeId, TaxType, TaxRate, Description) VALUES
-- VAT (Thuế GTGT % trên doanh thu)
(1, 'bt-retail',    'VAT', 0.0100, 'Phân phối, cung cấp hàng hóa: GTGT 1%'),
(1, 'bt-service',   'VAT', 0.0500, 'Dịch vụ: GTGT 5%'),
(1, 'bt-fnb',       'VAT', 0.0300, 'Sản xuất, dịch vụ gắn hàng hóa: GTGT 3%'),
(1, 'bt-transport', 'VAT', 0.0300, 'Vận tải: GTGT 3%'),

-- PIT Method 1 (Thuế TNCN Cách 1: % trên DT vượt 500tr, chỉ Nhóm 2)
(1, 'bt-retail',    'PIT_METHOD_1', 0.0050, 'Phân phối hàng hóa: TNCN 0.5%'),
(1, 'bt-service',   'PIT_METHOD_1', 0.0200, 'Dịch vụ: TNCN 2%'),
(1, 'bt-fnb',       'PIT_METHOD_1', 0.0150, 'Sản xuất, DV gắn hàng hóa: TNCN 1.5%'),
(1, 'bt-transport', 'PIT_METHOD_1', 0.0150, 'Vận tải: TNCN 1.5%');
```

**Note: Relationship với `BusinessTypeTaxes` hiện tại**

| Aspect | `BusinessTypeTaxes` (hiện tại) | `IndustryTaxRates` (mới) |
|--------|-------------------------------|-------------------------|
| Versioning | `EffectiveFrom/To` (date-based) | `RulesetId` (version-based) |
| Tax types | `VAT`, `PIT` | `VAT`, `PIT_METHOD_1` (rõ ràng hơn) |
| Group context | Không có | Linked qua Ruleset → TaxGroupRules |

Giữ `BusinessTypeTaxes` cho backward compat, đánh dấu deprecated. Rule Engine chỉ đọc từ `IndustryTaxRates`.

---

## 2. Architecture

### 2.1 Design: SQL + JSON Hybrid

```
┌─── TaxGroupRules TABLE ───────────────────────────────────────┐
│                                                                │
│  Structured columns (SQL)     │  Flexible columns (JSON)       │
│  ─────────────────────────    │  ──────────────────────────     │
│  RuleId (PK)                  │  ConditionsJson:               │
│  RulesetId (FK)               │    {minRevenue, maxRevenue,    │
│  GroupNumber                  │     ...future criteria}        │
│  GroupName                    │                                │
│  SortOrder                    │  OutcomesJson:                 │
│                               │    {vatExempt, allowedMethods, │
│  → Query/join/FK bình thường  │     requiredBooks, ...}        │
│  → Không bao giờ đổi schema   │  → Thêm field mới = thêm key  │
│                               │  → KHÔNG cần ALTER TABLE       │
└───────────────────────────────┴────────────────────────────────┘
```

**Tại sao không dùng NoSQL/MongoDB?**
- Chỉ ~4-5 rules/ruleset — data rất nhỏ, không cần horizontal scale
- TaxRuleset cần FK đến `BusinessTypes` (MySQL) — cross-DB FK = tự quản lý consistency
- Thêm MongoDB = thêm container, backup, monitoring — overhead lớn cho team 4 người
- MySQL 8 JSON support (`JSON_EXTRACT`, generated columns) đủ mạnh cho use case này

**Tại sao rule matching giữ ở Backend (.NET), không chuyển sang AI Service?**
- Phân nhóm HKD là **100% deterministic** (math comparison) — không cần ML/LLM
- Audit-friendly: input X → rule Y → output Z, có thể giải trình với cơ quan thuế
- Self-contained: không phụ thuộc AI Service availability
- AI Service (Python) phù hợp hơn cho **enrichment layer** (Phase 2): revenue forecast, tax optimization suggestion, anomaly detection

### 2.2 Service Flow

```markdown
┌───────── RULE ENGINE SERVICE ─────────┐
│                                        │
│  Input:                                │
│  ├── ownerUserId (or locationId)       │
│  └── periodId (kỳ kế toán cụ thể)     │
│                                        │
│  Process:                              │
│  ├── 1. Fetch active TaxRuleset        │
│  ├── 2. Lookup Period → startDate,     │
│  │      endDate                        │
│  ├── 3. Query DT lũy kế từ GL/Orders  │
│  │      + manual_revenue entries       │
│  ├── 4. Deserialize ConditionsJson     │
│  │      → Match (MinRevenue ≤ DT      │
│  │         < MaxRevenue)               │
│  ├── 5. Deserialize OutcomesJson       │
│  ├── 5. Deserialize OutcomesJson       │
│  ├── 6. Lookup IndustryTaxRates        │
│  ├── 7. Lookup previousPeriod          │
│  │      (nhóm kỳ trước, nếu có)       │
│  └── 8. Build result + recommendation  │
│                                        │
│  Output:                               │
│  ├── suggestedGroup (1-N)              │
│  ├── allowedTaxMethods                 │
│  ├── requiredBooks (S1a/S2a/...)       │
│  ├── taxRates per businessType         │
│  ├── warnings (nếu gần ngưỡng nhóm)   │
│  └── rulesetVersion (audit)            │
│                                        │
└────────────────────────────────────────┘

┌─── Phase 2: AI Enrichment (optional) ──┐
│                                         │
│  Backend (deterministic result)         │
│       │                                 │
│       ▼                                 │
│  AI Service (Python):                   │
│  ├── Revenue Forecast (ML)              │
│  ├── Tax Optimization Suggestion        │
│  └── Group Change Warning               │
│       │                                 │
│       ▼                                 │
│  Frontend (show cả 2: actual + forecast)│
└─────────────────────────────────────────┘
```

---

## 3. Evaluation Logic

```csharp
public class RuleEngineService : IRuleEngineService
{
    /// <summary>
    /// Gợi ý nhóm HKD dựa trên DT lũy kế.
    /// Không hardcode nhóm/ngưỡng — tất cả từ JSON data.
    /// Input: periodId → lookup period dates, tính DT (bao gồm manual_revenue GL entries).
    /// </summary>
    public async Task<GroupEvaluationResult> EvaluateGroupAsync(
        int businessLocationId, long periodId)
    {
        // 1. Lấy active ruleset
        var ruleset = await _rulesetRepo.GetActiveAsync();
        if (ruleset == null) throw new InvalidOperationException("No active tax ruleset");
        
        // 2. Lookup period → lấy startDate, endDate
        var period = await _periodRepo.GetByIdAsync(periodId);
        if (period == null) throw new NotFoundException("Period not found");
        
        DateOnly startDate = period.StartDate;
        DateOnly endDate = period.EndDate;
        
        // 3. Tính DT lũy kế (bao gồm manual_revenue GL entries)
        var revenue = await _glRepo.CalculateRevenueAsync(
            businessLocationId, startDate, endDate);
        // revenue = { totalRevenue, revenueByBusinessType: [{btId, amount}] }
        // CalculateRevenueAsync tổng hợp từ:
        //   - Orders completed (sale GL entries)
        //   - Manual revenue GL entries (manual_revenue, DebitAmount)
        //   - Trừ reversals (IsReversal = true)
        
        // 4. Annualize nếu chưa hết năm (ước tính cho gợi ý)
        var monthsElapsed = CalculateMonthsElapsed(startDate, DateOnly.FromDateTime(DateTime.UtcNow));
        decimal annualizedRevenue = monthsElapsed > 0 && monthsElapsed < 12
            ? revenue.TotalRevenue * (12.0m / monthsElapsed)
            : revenue.TotalRevenue;
        
        // 5. Parse JSON + Match group
        var groups = await _groupRuleRepo.GetByRulesetAsync(ruleset.RulesetId);
        var parsed = groups.Select(g => new
        {
            Rule = g,
            Conditions = JsonSerializer.Deserialize<GroupConditions>(g.ConditionsJson)!,
            Outcomes = JsonSerializer.Deserialize<GroupOutcomes>(g.OutcomesJson)!
        }).ToList();
        
        var matched = parsed
            .OrderBy(x => x.Rule.SortOrder)
            .FirstOrDefault(x =>
                annualizedRevenue >= x.Conditions.MinRevenue &&
                (x.Conditions.MaxRevenue == null || annualizedRevenue < x.Conditions.MaxRevenue));
        
        if (matched == null) throw new InvalidOperationException("No matching group rule");
        
        var outcomes = matched.Outcomes;
        var conditions = matched.Conditions;
        
        // 6. Lookup industry tax rates
        var industryRates = await _taxRateRepo
            .GetByRulesetAsync(ruleset.RulesetId);
        
        // 7. Tính PIT Method 1: trừ RevenueDeduction trên TỔNG DT trước, rồi phân bổ
        decimal deductibleRevenue = Math.Max(0, 
            revenue.TotalRevenue - (outcomes.RevenueDeduction ?? 0));
        decimal totalRevenue = revenue.TotalRevenue;
        
        var breakdown = revenue.RevenueByBusinessType.Select(r =>
        {
            var vatRate = industryRates
                .FirstOrDefault(ir => ir.BusinessTypeId == r.BusinessTypeId 
                    && ir.TaxType == "VAT")?.TaxRate ?? 0;
            var pitM1Rate = industryRates
                .FirstOrDefault(ir => ir.BusinessTypeId == r.BusinessTypeId 
                    && ir.TaxType == "PIT_METHOD_1")?.TaxRate ?? 0;
            
            // Phân bổ phần DT sau trừ deduction theo tỷ lệ DT từng ngành
            decimal allocatedRevenue = totalRevenue > 0
                ? deductibleRevenue * (r.Amount / totalRevenue)
                : 0;
            
            return new IndustryBreakdown
            {
                BusinessTypeId = r.BusinessTypeId,
                Revenue = r.Amount,
                VatRate = vatRate,
                PitMethod1Rate = pitM1Rate,
                VatAmount = outcomes.VatExempt ? 0 : r.Amount * vatRate,
                PitMethod1Amount = outcomes.PitExempt ? 0 : allocatedRevenue * pitM1Rate
            };
        }).ToList();
        
        // 8. Build warnings
        var warnings = new List<string>();
        if (conditions.MaxRevenue.HasValue)
        {
            var headroom = conditions.MaxRevenue.Value - annualizedRevenue;
            if (headroom < conditions.MaxRevenue.Value * 0.1m)
                warnings.Add($"DT dự kiến gần ngưỡng Nhóm {matched.Rule.GroupNumber + 1}");
        }
        
        return new GroupEvaluationResult
        {
            RulesetId = ruleset.RulesetId,
            RulesetVersion = ruleset.Version,
            ActualRevenue = revenue.TotalRevenue,
            AnnualizedRevenue = annualizedRevenue,
            IsAnnualized = monthsElapsed < 12,
            SuggestedGroup = matched.Rule.GroupNumber,
            SuggestedGroupName = matched.Rule.GroupName,
            // Outcomes đã là typed object — không cần deserialize lại
            AllowedTaxMethods = outcomes.AllowedTaxMethods,
            DefaultTaxMethod = outcomes.DefaultTaxMethod,
            RequiredBooks = outcomes.RequiredBooks,
            VatExempt = outcomes.VatExempt,
            PitExempt = outcomes.PitExempt,
            PitRateMethod2 = outcomes.PitRateMethod2,
            RevenueDeduction = outcomes.RevenueDeduction,
            IndustryBreakdown = breakdown,
            Warnings = warnings
        };
        
        // 9. Lookup previous period (carry-over context)
        var previousPeriod = await _periodRepo.GetPreviousPeriodAsync(
            businessLocationId, period.PeriodType, period.Year, period.Quarter);
        
        PreviousPeriodContext? prevContext = null;
        string? recommendation = null;
        
        if (previousPeriod != null)
        {
            var prevBooks = await _bookRepo.GetByPeriodAsync(previousPeriod.PeriodId);
            var prevGroup = prevBooks.FirstOrDefault()?.GroupNumber;
            var prevMethod = prevBooks.FirstOrDefault()?.TaxMethod;
            
            prevContext = new PreviousPeriodContext
            {
                PeriodId = previousPeriod.PeriodId,
                PeriodLabel = $"Q{previousPeriod.Quarter}/{previousPeriod.Year}",
                GroupNumber = prevGroup,
                TaxMethod = prevMethod,
                Status = previousPeriod.Status
            };
            
            // Recommendation: so sánh nhóm kỳ trước vs gợi ý kỳ này
            if (prevGroup.HasValue && prevGroup.Value == result.SuggestedGroup)
                recommendation = "Giữ nguyên nhóm và cách tính thuế kỳ trước";
            else if (prevGroup.HasValue)
                recommendation = $"DT thay đổi → chuyển từ Nhóm {prevGroup} sang Nhóm {result.SuggestedGroup}. Vui lòng xem xét lại cách tính thuế.";
        }
        else
        {
            recommendation = "Kỳ đầu tiên — chưa có dữ liệu kỳ trước để so sánh";
        }
        
        result.PreviousPeriod = prevContext;
        result.Recommendation = recommendation;
        
        return result;
    }
}
```

> **Fix PIT Method 1 (so với v1 cũ)**: `RevenueDeduction` (500tr) bây giờ trừ trên **tổng DT** trước,
> rồi phân bổ theo tỷ lệ DT từng ngành. V1 cũ trừ per-BusinessType → sai khi có multi-BusinessType.

---

## 4. API: Get Group Suggestion

```yaml
GET /api/v1/locations/{locationId}/accounting/group-suggestion?periodId=1
Authorization: Bearer {token}

Response:
{
  "rulesetVersion": "1.0.0",
  "periodId": 1,
  "periodLabel": "Q1/2026",
  "actualRevenue": 620000000,
  "annualizedRevenue": 826666667,
  "isAnnualized": true,
  "suggestedGroup": 2,
  "suggestedGroupName": "Nhóm 2",
  "allowedTaxMethods": ["method_1", "method_2"],
  "defaultTaxMethod": "method_1",
  "requiredBooks": {
    "method_1": ["S2a"],
    "method_2": ["S2b", "S2c", "S2d", "S2e"]
  },
  "vatExempt": false,
  "pitExempt": false,
  "revenueDeduction": 500000000,
  "industryBreakdown": [
    {
      "businessTypeId": "bt-retail",
      "businessTypeName": "Bán lẻ hàng hóa",
      "revenue": 500000000,
      "vatRate": 0.01,
      "vatAmount": 5000000,
      "pitMethod1Rate": 0.005,
      "pitMethod1Amount": 483871
    },
    {
      "businessTypeId": "bt-service",
      "businessTypeName": "Dịch vụ",
      "revenue": 120000000,
      "vatRate": 0.05,
      "vatAmount": 6000000,
      "pitMethod1Rate": 0.02,
      "pitMethod1Amount": 464516
    }
  ],
  "warnings": [],
  
  "previousPeriod": {
    "periodId": null,
    "periodLabel": null,
    "groupNumber": null,
    "taxMethod": null,
    "status": null
  },
  "recommendation": "Kỳ đầu tiên — chưa có dữ liệu kỳ trước để so sánh"
}
```

> **Lưu ý**: `previousPeriod` chứa context nhóm + cách tính thuế kỳ trước (nếu có). `recommendation` gợi ý carry-over hoặc thay đổi so với kỳ trước. API này chỉ **gợi ý** — Owner xem kết quả rồi quyết định tạo AccountingBook.

---

## 5. Business Rules

| Rule | Mô tả |
|------|-------|
| **RULE-ENGINE-01** | Chỉ 1 TaxRuleset active tại 1 thời điểm |
| **RULE-ENGINE-02** | Phân nhóm dựa trên data (TaxGroupRules JSON), không hardcode |
| **RULE-ENGINE-03** | DT annualized cho gợi ý giữa năm |
| **RULE-ENGINE-04** | Gợi ý chỉ gợi ý — Owner chủ động chọn nhóm để tạo book |
| **RULE-ENGINE-05** | Khi TT thay đổi → tạo version mới, code không đổi |
| **RULE-ENGINE-06** | Schema linh hoạt: ConditionsJson + OutcomesJson, thêm tiêu chí/kết quả mới mà KHÔNG cần ALTER TABLE hay deploy code |
| **RULE-ENGINE-07** | RevenueDeduction trừ trên tổng DT trước, rồi phân bổ theo tỷ lệ DT từng ngành |
| **RULE-ENGINE-08** | Manual GL entries (`manual_revenue`) tham gia vào tính DT lũy kế cho phân nhóm |
| **RULE-ENGINE-09** | Input = `periodId` (thay vì year/quarter) — gắn gợi ý vào kỳ kế toán cụ thể |
| **RULE-ENGINE-10** | API trả về `previousPeriod` + `recommendation` để Owner có context carry-over |

---

## 6. API Endpoints

| Method | Endpoint | Description | Who |
|--------|----------|-------------|-----|
| `GET` | `/api/v1/locations/{id}/accounting/group-suggestion?periodId={periodId}` | Gợi ý nhóm HKD | Owner |
| `GET` | `/api/v1/tax-rulesets` | List rulesets | Admin, Consultant |
| `POST` | `/api/v1/tax-rulesets` | Tạo ruleset version mới | Admin, Consultant |
| `PUT` | `/api/v1/tax-rulesets/{rulesetId}/activate` | Activate ruleset | Admin, Consultant |
| `GET` | `/api/v1/tax-rulesets/{rulesetId}/group-rules` | List group rules | Admin, Consultant |
| `GET` | `/api/v1/tax-rulesets/{rulesetId}/industry-rates` | List industry rates | Admin, Consultant |

---

## 7. Error Codes

| Code | HTTP | Message |
|------|:----:|---------|
| `RULESET_NOT_FOUND` | 404 | Không tìm thấy Tax Ruleset |
| `RULESET_NO_ACTIVE` | 500 | Không có ruleset active trong hệ thống |
| `GROUP_INVALID` | 400 | Nhóm HKD không hợp lệ (1-4) |
| `TAX_METHOD_NOT_ALLOWED` | 400 | Cách tính thuế không áp dụng cho nhóm này |
| `TAX_TYPE_INVALID` | 400 | Loại thuế không hợp lệ (chỉ VAT hoặc PIT) |
