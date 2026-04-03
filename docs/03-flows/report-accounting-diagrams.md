    # Report & Accounting — Diagrams

> **Companion doc** cho [report-accounting-flow.md](report-accounting-flow.md) (index).
> State machines, activity diagrams, và sequence diagrams cho module Report & Accounting.
>
> **Sub-docs**: [cost-gl-flow](cost-gl-flow.md) · [accounting-period-flow](accounting-period-flow.md) · [rule-engine-flow](rule-engine-flow.md) · [accounting-book-flow](accounting-book-flow.md) · [dashboard-report-flow](dashboard-report-flow.md)

---

## Mục lục

1. [State Machine Diagrams](#1-state-machine-diagrams)
   - [1.1 Accounting Period Lifecycle](#11-accounting-period-lifecycle)
   - [1.2 Accounting Book Lifecycle](#12-accounting-book-lifecycle)
   - [1.3 Cost Lifecycle](#13-cost-lifecycle)
   - [1.4 Tax Ruleset Lifecycle](#14-tax-ruleset-lifecycle)
2. [Activity Diagrams](#2-activity-diagrams)
   - [2.1 GL Entry Generation (Order Completed)](#21-gl-entry-generation-order-completed)
   - [2.2 Group Evaluation & Book Creation](#22-group-evaluation--book-creation)
   - [2.3 Book Export](#23-book-export)
   - [2.4 Cost Auto-Generation (Import Confirmed)](#24-cost-auto-generation-import-confirmed)
   - [2.5 Period Finalize](#25-period-finalize)
3. [Sequence Diagrams](#3-sequence-diagrams)
   - [3.1 Order Completed → GL + Side Effects](#31-order-completed--gl--side-effects)
   - [3.2 Owner Views Group Suggestion → Creates Book](#32-owner-views-group-suggestion--creates-book)
   - [3.3 Owner Exports Accounting Book](#33-owner-exports-accounting-book)
   - [3.4 Import Confirmed → Cost + GL](#34-import-confirmed--cost--gl)
   - [3.5 Order Cancelled → GL Reversal](#35-order-cancelled--gl-reversal)
   - [3.6 Debt Payment → GL Entry](#36-debt-payment--gl-entry)
   - [3.7 Period Reopen Flow](#37-period-reopen-flow)

---

## 1. State Machine Diagrams

### 1.1 Accounting Period Lifecycle

```mermaid
stateDiagram-v2
    [*] --> open : POST /periods\n(Owner creates)

    open --> open : GL entries tiếp tục\nđược tạo tự động

    open --> finalized : POST /periods/{id}/finalize\n[has ≥1 active book]

    finalized --> reopened : POST /periods/{id}/reopen\n[reason required]\n→ audit log

    reopened --> finalized : POST /periods/{id}/finalize\n[re-finalize]

    reopened --> reopened : Owner sửa data,\ntạo/archive books

    note right of open
        Trạng thái mặc định.
        - GL entries tạo tự động
        - Owner tạo/xem books
        - Không ràng buộc gì
    end note

    note right of finalized
        Owner đã chốt kỳ.
        - GL entries VẪN tạo được
        (giao dịch vẫn xảy ra)
        - Books vẫn live update
        - Đánh dấu "đã chính thức"
    end note

    note left of reopened
        Mở lại sau finalize.
        - Bắt buộc có lý do
        - Audit log ghi nhận
        - Có thể finalize lại
    end note
```

**Transition rules:**

| From | To | Guard | Side Effect |
|------|----|-------|-------------|
| `[*]` | `open` | — | Audit log: `period_created` |
| `open` | `finalized` | `books.count(active) >= 1` | Set `FinalizedAt`, `FinalizedByUserId`. Audit log: `period_finalized` |
| `finalized` | `reopened` | `reason != null` | Audit log: `period_reopened` (OldValue, NewValue, Reason) |
| `reopened` | `finalized` | `books.count(active) >= 1` | Update `FinalizedAt`. Audit log: `period_finalized` |

---

### 1.2 Accounting Book Lifecycle

```mermaid
stateDiagram-v2
    [*] --> active : POST /books\n(Owner chọn nhóm)

    active --> active : Data tự cập nhật\n(live view from GL)

    active --> active : POST /books/{id}/export\n→ tạo AccountingExport

    active --> archived : PUT /books/{id}/archive\n(Owner đổi nhóm, tạo book mới)

    note right of active
        Book đang sử dụng.
        - Data query realtime
        - Có thể export nhiều lần
        - Mỗi export = 1 snapshot
    end note

    note right of archived
        Không dùng nữa.
        - Vẫn truy cập được (read-only)
        - Export history vẫn giữ
        - Không thể unarchive
    end note
```

**Lưu ý**:
- Không có trạng thái `deleted` — books chỉ archive, không xóa
- Owner có thể tạo nhiều books cho cùng 1 period (so sánh nhóm khác nhau)
- Export không thay đổi trạng thái book — book vẫn `active` sau export

---

### 1.3 Cost Lifecycle

```mermaid
stateDiagram-v2
    [*] --> active_auto : Import CONFIRMED\n→ auto create\n(ImportId = X)

    [*] --> active_manual : POST /costs\n→ Owner tạo\n(ImportId = NULL)

    active_auto --> soft_deleted_auto : Import CANCELLED\n→ auto soft delete\n+ GL reversal

    active_manual --> active_manual : PUT /costs/{id}\n→ Owner sửa

    active_manual --> soft_deleted_manual : DELETE /costs/{id}\n→ soft delete\n+ GL reversal

    note right of active_auto
        READONLY
        Tạo tự động từ Import.
        Không cho sửa/xóa trực tiếp.
        Muốn thay đổi → cancel Import.
    end note

    note right of active_manual
        Owner CRUD
        Owner tạo và quản lý.
        Sửa → GL reversal + entry mới.
        Xóa → soft delete + GL reversal.
    end note
```

**Cost type rules:**

| ImportId | Editable? | Deletable? | How to modify? |
|:--------:|:---------:|:----------:|----------------|
| NOT NULL | ❌ | ❌ | Cancel Import gốc → auto soft delete + reversal |
| NULL | ✅ Owner | ✅ Owner | PUT/DELETE trực tiếp |

---

### 1.4 Tax Ruleset Lifecycle

```mermaid
stateDiagram-v2
    [*] --> inactive : POST /tax-rulesets\n(Admin tạo version mới)

    inactive --> active : PUT /tax-rulesets/{id}/activate\n[deactivate ruleset cũ]

    active --> inactive : Ruleset mới được activate\n→ cái này tự deactivate

    note right of active
        CHỈ 1 ACTIVE
        Rule Engine luôn đọc
        từ active ruleset.
        Khi activate mới
        → cũ tự deactivate.
    end note

    note left of inactive
        Version cũ hoặc draft.
        Vẫn accessible (read).
        Books đã tạo giữ ref
        tới rulesetId cũ.
    end note
```

---

## 2. Activity Diagrams

### 2.1 GL Entry Generation (Order Completed)

```mermaid
flowchart TD
    A[Order.CompleteAsync called] --> B{Order valid?}
    B -->|No| ERR[Throw error]
    B -->|Yes| C[Update Order status = completed]
    C --> D[Stock deduction per OrderDetail]
    D --> E{CashAmount > 0?}
    E -->|Yes| F[Create GL entry:\nDebit CashAmount\nChannel: cash]
    E -->|No| G{BankAmount > 0?}
    F --> G
    G -->|Yes| H[Create GL entry:\nDebit BankAmount\nChannel: bank]
    G -->|No| I{DebtAmount > 0?}
    H --> I
    I -->|Yes| J[Create GL entry:\nDebit DebtAmount\nChannel: debt]
    I -->|No| K{Has Debtor?}
    J --> K
    K -->|Yes| L[Update Debtor balance\nCreate DebtorPaymentTransaction]
    K -->|No| M[SaveChanges]
    L --> M
    M --> N[Return completed Order]

    style F fill:#d4edda
    style H fill:#d4edda
    style J fill:#d4edda
    style L fill:#fff3cd
```

### 2.2 Group Evaluation & Book Creation

```mermaid
flowchart TD
    A[Owner mở trang\nAccounting] --> B[GET /group-suggestion\n?year=2026&quarter=1]
    B --> C[RuleEngineService.\nEvaluateGroupAsync]
    C --> D[Fetch active TaxRuleset]
    D --> E[Query DT lũy kế\ntừ GL entries]
    E --> F{Đủ 12 tháng data?}
    F -->|No| G[Annualize:\nDT × 12/months_elapsed]
    F -->|Yes| H[Dùng DT thực]
    G --> I[Match TaxGroupRules:\nMinRevenue ≤ DT < MaxRevenue]
    H --> I
    I --> J[Lookup IndustryTaxRates\nper BusinessType]
    J --> K[Return GroupEvaluationResult\n+ warnings]
    K --> L[Owner xem kết quả]
    L --> M{Owner chọn\nnhóm + cách?}
    M -->|Nhóm 2 Cách 1| N[POST /books\ngroupNumber=2\ntaxMethod=method_1]
    M -->|Nhóm 2 Cách 2| O[POST /books\ngroupNumber=2\ntaxMethod=method_2]
    M -->|Thử cả 2| P[Tạo cả 2 bộ books\nđể so sánh]
    N --> Q[System xác định\nRequired Books]
    O --> Q
    P --> Q
    Q --> R{Location đa ngành\n+ cần tách?}
    R -->|Yes| S[Tạo 1 book\nper BusinessType]
    R -->|No| T[Tạo 1 book\ntổng]
    S --> U[Audit log:\nbook_created]
    T --> U
    U --> V[Return books]

    style K fill:#d4edda
    style V fill:#d4edda
```

### 2.3 Book Export

```mermaid
flowchart TD
    A[Owner bấm 'Xuất sổ'\nPOST /books/id/export] --> B{Book status\n= active?}
    B -->|No| ERR[Error:\nBOOK_ALREADY_ARCHIVED]
    B -->|Yes| C[Load Book +\nTemplateVersion +\nFieldMappings]
    C --> D[Query data theo\nFieldMappings]
    D --> D1{SourceEntity?}
    D1 -->|orders| E1[Query Orders\nfor period + location\n+ businessType filter]
    D1 -->|gl_entries| E2[Query GL entries\nfor period + location]
    D1 -->|costs| E3[Query Costs\nfor period + location]
    D1 -->|tax_payments| E4[Query TaxPayments\nfor period]
    E1 --> F[Compute formula fields\nVD: revenue × vat_rate]
    E2 --> F
    E3 --> F
    E4 --> F
    F --> G[Build summary:\ntotal DT, CP, VAT, PIT]
    G --> H{Export format?}
    H -->|xlsx| I1[Render data vào\nExcel template]
    H -->|pdf| I2[Render data vào\nPDF template]
    I1 --> J[Upload file\n→ Cloudinary]
    I2 --> J
    J --> K[Create\nAccountingExport record]
    K --> L[Audit log:\nbook_exported]
    L --> M[Return ExportDto\nwith fileUrl]

    style M fill:#d4edda
    style ERR fill:#f8d7da
```

### 2.4 Cost Auto-Generation (Import Confirmed)

```mermaid
flowchart TD
    A[Import.ConfirmAsync called] --> B[Update Import\nstatus = CONFIRMED]
    B --> C[Stock addition\nper ProductImport]
    C --> D[CostPrice update\nweighted average]
    D --> E[Create Cost record:\nCostType=import\nImportId=X\nAmount=TotalAmount]
    E --> F[Create GL entry:\nCreditAmount=TotalAmount\nTransType=import_cost]
    F --> G[SaveChanges]
    G --> H[Return confirmed Import]

    style E fill:#d4edda
    style F fill:#d4edda
```

**Ngược lại — Import Cancelled:**

```mermaid
flowchart TD
    A[Import.CancelAsync called] --> B{Import was\nCONFIRMED?}
    B -->|No — was DRAFT| C[Just set CANCELLED\nNo side effects]
    B -->|Yes — was CONFIRMED| D[Rollback stock\nper ProductImport]
    D --> E[Soft delete linked Cost\nSET DeletedAt = NOW]
    E --> F[Create GL reversal entry:\nDebitAmount=TotalAmount\nIsReversal=true\nReversedEntryId=original]
    F --> G[SaveChanges]
    C --> H[Return cancelled Import]
    G --> H

    style E fill:#fff3cd
    style F fill:#fff3cd
```

### 2.5 Period Finalize

```mermaid
flowchart TD
    A[POST /periods/id/finalize] --> B{Period exists\n& belongs to location?}
    B -->|No| ERR1[Error: PERIOD_NOT_FOUND]
    B -->|Yes| C{Period status\n= open or reopened?}
    C -->|No — already finalized| ERR2[Error: PERIOD_ALREADY_FINALIZED]
    C -->|Yes| D{Has ≥1 active\nAccountingBook?}
    D -->|No| ERR3[Error: PERIOD_NO_BOOKS]
    D -->|Yes| E[Set status = finalized]
    E --> F[Set FinalizedAt = NOW\nFinalizedByUserId = current]
    F --> G[Audit log:\nperiod_finalized]
    G --> H[Return updated Period]

    style H fill:#d4edda
    style ERR1 fill:#f8d7da
    style ERR2 fill:#f8d7da
    style ERR3 fill:#f8d7da
```

---

## 3. Sequence Diagrams

### 3.1 Order Completed → GL + Side Effects

```mermaid
sequenceDiagram
    actor Owner
    participant API as OrderController
    participant OS as OrderService
    participant GL as GLService
    participant Stock as ProductService
    participant Debt as DebtorService
    participant DB as Database

    Owner->>API: POST /orders/{id}/complete
    API->>OS: CompleteAsync(orderId)
    
    OS->>DB: Get Order + OrderDetails
    DB-->>OS: Order data
    
    OS->>OS: Validate (status = pending)
    OS->>DB: Update Order.Status = completed
    
    OS->>Stock: DeductStockAsync(orderDetails)
    Stock->>DB: UPDATE Products SET Stock -= qty

    OS->>GL: RecordOrderCompleted(order)
    
    alt CashAmount > 0
        GL->>DB: INSERT GL entry (Debit, cash)
    end
    alt BankAmount > 0
        GL->>DB: INSERT GL entry (Debit, bank)
    end
    alt DebtAmount > 0
        GL->>DB: INSERT GL entry (Debit, debt)
        OS->>Debt: RecordDebtAsync(order)
        Debt->>DB: UPDATE Debtor balance
        Debt->>DB: INSERT DebtorPaymentTransaction
    end

    OS->>DB: SaveChanges (transaction)
    OS-->>API: CompletedOrder DTO
    API-->>Owner: 200 OK
```

### 3.2 Owner Views Group Suggestion → Creates Book

```mermaid
sequenceDiagram
    actor Owner
    participant API as AccountingController
    participant RE as RuleEngineService
    participant BS as BookService
    participant DB as Database

    Owner->>API: GET /group-suggestion?year=2026&quarter=1
    API->>RE: EvaluateGroupAsync(locationId, 2026, 1)
    
    RE->>DB: Get active TaxRuleset
    DB-->>RE: Ruleset (TT152 v1.0.0)
    
    RE->>DB: Query GL SUM(DebitAmount)\nWHERE sale, Q1/2026
    DB-->>RE: Revenue = 620,000,000đ
    
    RE->>RE: Annualize: 620M × 12/3 = 826M (ước tính)
    
    RE->>DB: Get TaxGroupRules for ruleset
    DB-->>RE: 4 groups with thresholds
    
    RE->>RE: Match: 500M ≤ 826M < 3B → Nhóm 2
    
    RE->>DB: Get IndustryTaxRates
    DB-->>RE: VAT + PIT rates per industry
    
    RE-->>API: GroupEvaluationResult
    API-->>Owner: JSON (suggestedGroup=2,\nmethods=[method_1,method_2],...)

    Note over Owner: Owner xem xét,\nquyết định chọn\nNhóm 2 Cách 1

    Owner->>API: POST /books\n{periodId:1, groupNumber:2,\ntaxMethod:"method_1"}
    API->>BS: CreateBookAsync(...)
    
    BS->>DB: Get TaxGroupRule for group 2
    DB-->>BS: RequiredBooks: method_1 → [S2a]
    
    BS->>DB: Get Template S2a + active version
    DB-->>BS: TemplateVersion v1.0
    
    BS->>DB: Get location BusinessTypes
    DB-->>BS: [bt-retail, bt-service]
    
    Note over BS: Location đa ngành\n→ Tạo 2 books S2a\n(1 per BusinessType)
    
    BS->>DB: INSERT AccountingBook (bt-retail)
    BS->>DB: INSERT AccountingBook (bt-service)
    BS->>DB: INSERT AuditLog (book_created)
    BS->>DB: SaveChanges
    
    BS-->>API: [Book1, Book2]
    API-->>Owner: 201 Created
```

### 3.3 Owner Exports Accounting Book

```mermaid
sequenceDiagram
    actor Owner
    participant API as AccountingController
    participant ES as ExportService
    participant QE as QueryEngine
    participant TE as TemplateEngine
    participant Cloud as Cloudinary
    participant DB as Database

    Owner->>API: POST /books/{bookId}/export\n{format: "xlsx"}
    API->>ES: ExportBookAsync(bookId, "xlsx")
    
    ES->>DB: Get Book + TemplateVersion\n+ FieldMappings
    DB-->>ES: Book data + 6 field mappings
    
    ES->>QE: QueryBookData(book, fieldMappings)
    
    loop Each FieldMapping
        alt SourceEntity = orders
            QE->>DB: SELECT from Orders\nWHERE period + location + businessType
        end
        alt SourceEntity = gl_entries
            QE->>DB: SELECT from GeneralLedgerEntries\nWHERE period + location
        end
        alt SourceType = formula
            QE->>QE: Compute: revenue × vat_rate
        end
    end
    
    DB-->>QE: Query results
    QE-->>ES: DataRows[] (285 rows)
    
    ES->>ES: Build SummaryJson:\ntotalRevenue, totalVat, totalPit
    
    ES->>TE: RenderToExcel(templateFile,\ndataRows, summary)
    TE-->>ES: Excel file bytes
    
    ES->>Cloud: Upload file
    Cloud-->>ES: fileUrl, publicId
    
    ES->>DB: INSERT AccountingExport\n(summaryJson, fileUrl, format)
    ES->>DB: INSERT AuditLog (book_exported)
    ES->>DB: SaveChanges
    
    ES-->>API: ExportDto
    API-->>Owner: 200 OK {fileUrl, summary}
```

### 3.4 Import Confirmed → Cost + GL

```mermaid
sequenceDiagram
    actor Owner
    participant API as ImportController
    participant IS as ImportService
    participant CS as CostService
    participant GL as GLService
    participant PS as ProductService
    participant DB as Database

    Owner->>API: POST /imports/{id}/confirm
    API->>IS: ConfirmAsync(importId)
    
    IS->>DB: Get Import + ProductImports
    DB-->>IS: Import data
    
    IS->>IS: Validate (status = DRAFT)
    IS->>DB: Update Import.Status = CONFIRMED
    
    IS->>PS: AddStockAsync(productImports)
    PS->>DB: UPDATE Products SET Stock += qty
    PS->>PS: Recalculate CostPrice\n(weighted average)
    PS->>DB: UPDATE Products SET CostPrice = new

    IS->>CS: OnImportConfirmed(import)
    CS->>DB: INSERT Cost\n(CostType=import, ImportId=X,\nAmount=TotalAmount)
    
    CS->>GL: RecordImportConfirmed(import)
    GL->>DB: INSERT GL entry\n(CreditAmount=TotalAmount,\nTransType=import_cost)
    
    IS->>DB: SaveChanges (transaction)
    IS-->>API: Confirmed Import
    API-->>Owner: 200 OK
```

### 3.5 Order Cancelled → GL Reversal

```mermaid
sequenceDiagram
    actor Owner
    participant API as OrderController
    participant OS as OrderService
    participant GL as GLService
    participant Stock as ProductService
    participant Debt as DebtorService
    participant DB as Database

    Owner->>API: POST /orders/{id}/cancel
    API->>OS: CancelAsync(orderId)
    
    OS->>DB: Get Order + OrderDetails
    DB-->>OS: Order (status=completed)
    
    OS->>Stock: RestoreStockAsync(orderDetails)
    Stock->>DB: UPDATE Products SET Stock += qty

    alt Order had DebtAmount > 0
        OS->>Debt: ReverseDebtAsync(order)
        Debt->>DB: UPDATE Debtor balance (reverse)
        Debt->>DB: INSERT DebtorPaymentTransaction (reversal)
    end

    OS->>GL: RecordOrderCancelled(order)
    GL->>DB: SELECT GL entries WHERE ref=order/{id}\nAND IsReversal=false
    DB-->>GL: Original entries [E3, E4]

    loop Each original entry
        GL->>DB: INSERT reversal entry\n(swap Debit↔Credit,\nIsReversal=true,\nReversedEntryId=original)
    end

    OS->>DB: Clone to new pending Order
    OS->>DB: Set original Order.Status = cancelled
    OS->>DB: SaveChanges
    
    OS-->>API: New pending Order
    API-->>Owner: 200 OK {newOrder}
```

### 3.6 Debt Payment → GL Entry

```mermaid
sequenceDiagram
    actor Owner
    participant API as DebtorController
    participant DS as DebtorService
    participant GL as GLService
    participant DB as Database

    Owner->>API: POST /debtors/{id}/payments\n{amount: 1000000,\npaymentMethod: "cash"}
    API->>DS: RecordPaymentAsync(debtorId, amount, method)
    
    DS->>DB: Get Debtor
    DB-->>DS: Debtor (CurrentBalance = -1,950,000)
    
    DS->>DS: Calculate new balance:\n-1,950,000 + 1,000,000 = -950,000
    
    DS->>DB: INSERT DebtorPaymentTransaction\n(Amount=1,000,000,\nBalanceBefore=-1,950,000,\nBalanceAfter=-950,000)
    
    DS->>DB: UPDATE Debtor\nSET CurrentBalance = -950,000
    
    DS->>GL: RecordDebtPayment(payment, debtor)
    GL->>DB: INSERT GL entry\n(DebitAmount=1,000,000,\nChannel=cash,\nTransType=debt_payment,\nRef=debtor_payment/{txId})
    
    Note over GL: Thu nợ = tiền VÀO\n→ Debit (không phải DT mới,\nDT đã ghi lúc bán hàng)
    
    DS->>DB: SaveChanges
    DS-->>API: PaymentTransaction DTO
    API-->>Owner: 200 OK
```

### 3.7 Period Reopen Flow

```mermaid
sequenceDiagram
    actor Owner
    participant API as AccountingController
    participant PS as PeriodService
    participant AS as AuditService
    participant DB as Database

    Owner->>API: POST /periods/{id}/reopen\n{reason: "Thiếu 3 đơn hàng\nchưa complete"}
    API->>PS: ReopenAsync(periodId, reason)
    
    PS->>DB: Get Period
    DB-->>PS: Period (status=finalized)
    
    PS->>PS: Validate:\n1. Status = finalized ✓\n2. Reason not empty ✓
    
    PS->>DB: UPDATE Period\nSET Status = reopened
    
    PS->>AS: LogAsync(periodId, "period_reopened")
    AS->>DB: INSERT AuditLog\n(Action=period_reopened,\nOldValue={status:finalized},\nNewValue={status:reopened},\nReason="Thiếu 3 đơn hàng...")
    
    PS->>DB: SaveChanges
    PS-->>API: Updated Period
    API-->>Owner: 200 OK

    Note over Owner: Owner complete 3 đơn thiếu\n→ GL entries auto created\n→ Books auto updated

    Owner->>API: POST /periods/{id}/finalize
    API->>PS: FinalizeAsync(periodId)
    PS->>DB: UPDATE Period SET Status = finalized
    PS->>AS: LogAsync(periodId, "period_finalized")
    AS->>DB: INSERT AuditLog
    PS->>DB: SaveChanges
    PS-->>API: Finalized Period
    API-->>Owner: 200 OK
```

---

## Appendix: Diagram Summary

| Diagram | Type | Mô tả | Section |
|---------|------|-------|---------|
| Accounting Period | State Machine | open → finalized → reopened | [1.1](#11-accounting-period-lifecycle) |
| Accounting Book | State Machine | active → archived | [1.2](#12-accounting-book-lifecycle) |
| Cost | State Machine | auto vs manual lifecycle | [1.3](#13-cost-lifecycle) |
| Tax Ruleset | State Machine | inactive ↔ active (chỉ 1) | [1.4](#14-tax-ruleset-lifecycle) |
| GL Generation (Order) | Activity | Order complete → split GL entries | [2.1](#21-gl-entry-generation-order-completed) |
| Group Eval + Book | Activity | Rule Engine → Owner chọn → tạo books | [2.2](#22-group-evaluation--book-creation) |
| Export Book | Activity | Query data → render → upload → snapshot | [2.3](#23-book-export) |
| Cost Auto-Gen | Activity | Import confirmed → Cost + GL | [2.4](#24-cost-auto-generation-import-confirmed) |
| Period Finalize | Activity | Validate → finalize → audit | [2.5](#25-period-finalize) |
| Order → GL | Sequence | Full side effects on complete | [3.1](#31-order-completed--gl--side-effects) |
| Group → Books | Sequence | Evaluation → suggestion → create books | [3.2](#32-owner-views-group-suggestion--creates-book) |
| Export | Sequence | Query → render → Cloudinary → snapshot | [3.3](#33-owner-exports-accounting-book) |
| Import → Cost + GL | Sequence | Confirm → stock + cost + GL | [3.4](#34-import-confirmed--cost--gl) |
| Order Cancel → Reversal | Sequence | Cancel → reverse stock, debt, GL | [3.5](#35-order-cancelled--gl-reversal) |
| Debt Payment → GL | Sequence | Pay debt → update balance → GL | [3.6](#36-debt-payment--gl-entry) |
| Period Reopen | Sequence | Reopen → fix → re-finalize | [3.7](#37-period-reopen-flow) |
