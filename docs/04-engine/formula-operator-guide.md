# Formula Operator Guide

> Module: Report & Accounting - Formula Engine
> Scope: Giai thich chi tiet cac toan tu va cach engine evaluate ExpressionJson
> Lien quan:

> - [tax-formular-engine.md](tax-formular-engine.md)
> - [accounting-book-flow-v2.md](../03-flows/accounting-book-flow-v2.md)

---

## 1. Muc tieu tai lieu

Tai lieu nay tap trung vao 3 cau hoi:

1. Engine doc `ExpressionJson` nhu the nao?
2. Moi toan tu/node hoat dong ra sao?
3. Khi sua formula thi ket qua thay doi theo quy tac gi?

Khac voi tai lieu tong quan, file nay di sau vao logic evaluate va edge-cases.

---

## 2. Mental model ngan gon

Engine coi `ExpressionJson` nhu mot cay AST (Abstract Syntax Tree):

- Node la 1 phep tinh hoac 1 nguon du lieu.
- Engine evaluate de quy tu node la len node goc.
- Ket qua cuoi cung la mot so (`decimal` hoac `integer`).

Vi du:

```json
{
  "op": "SUBTRACT",
  "left": { "ref": "S2C_TOTAL_REVENUE" },
  "right": { "ref": "S2C_TOTAL_COST" }
}
```

Cay nay nghia la: lay ket qua formula `S2C_TOTAL_REVENUE` tru `S2C_TOTAL_COST`.

---

## 3. Thu tu evaluate (runtime)

## 3.1 Theo `CalculationOrder`

Engine evaluate theo thu tu tang dan `CalculationOrder` trong `TemplateFieldMappings`.

- Formula o order nho hon duoc tinh truoc.
- Formula dung `ref` chi nen tham chieu formula co order thap hon.

## 3.2 Theo node trong moi formula

Voi 1 formula cu the, engine evaluate theo de quy:

1. Gap `literal` -> tra ve gia tri.
2. Gap `ref` -> lay tu `resolvedValues`.
3. Gap `aggregate` -> build query + query DB.
4. Gap `lookup` -> query bang lookup.
5. Gap `op` -> evaluate `left`, evaluate `right`, roi ap phep toan.
6. Gap `fn` -> evaluate danh sach `args`, roi ap ham.

## 3.3 Round va cast

Sau khi co ket qua thuan:

1. Ap `RoundingMode` neu co.
2. Ap `RoundingPrecision`.
3. Cast theo `ResultDataType`.

---

## 4. Node va toan tu chi tiet

## 4.1 `literal`

Cau truc:

```json
{ "literal": 500000000 }
```

Y nghia:

- Gia tri co dinh.
- Khong phu thuoc DB hay context.

Dung cho:

- Nguong mien thue (500M)
- He so co dinh
- Gia tri fallback

---

## 4.2 `ref`

Cau truc:

```json
{ "ref": "S2A_QUARTERLY_TOTAL" }
```

Y nghia:

- Tham chieu ket qua formula da tinh truoc do.
- Key tham chieu la `FormulaDefinitions.Code`.

Luu y:

- Neu `ref` khong ton tai -> loi `FORMULA_MISSING_REF`.
- Neu ref tao vong phu thuoc -> `FORMULA_CIRCULAR_DEP`.

---

## 4.3 `aggregate`

Cau truc tong quat:

```json
{
  "aggregate": "SUM",
  "source": "revenues",
  "field": "Amount",
  "scope": "book",
  "filter": { "RevenueType": ["sale", "manual"] },
  "periodFilter": "current",
  "sign": "all"
}
```

### Truong quan trong

- `aggregate`: `SUM | COUNT | AVG`
- `source`: entity whitelist (tu metadata)
- `field`: field whitelist trong entity
- `scope`:
  - `book`: loc theo context cua so
  - `location`: toan location
- `periodFilter`:
  - `current`: trong ky
  - `before`: truoc ky
  - `none`: khong loc theo ky
- `sign`:
  - `positive`: > 0
  - `negative`: < 0
  - `all`: khong loc dau

### Quy tac ket qua

- Khong co du lieu -> tra ve `0` (khong null).
- AVG khong co du lieu -> quy ve `0`.

### Vi du 1: Tong doanh thu

```json
{
  "aggregate": "SUM",
  "source": "revenues",
  "field": "Amount",
  "scope": "location",
  "filter": { "RevenueType": ["sale", "manual"] }
}
```

### Vi du 2: So luong xuat kho (dau am)

```json
{
  "aggregate": "SUM",
  "source": "stock_movements",
  "field": "QuantityDelta",
  "scope": "book",
  "periodFilter": "current",
  "sign": "negative"
}
```

---

## 4.4 `lookup`

Cau truc:

```json
{
  "lookup": {
    "entity": "AccountingPeriods",
    "field": "OpeningCashBalance"
  }
}
```

Y nghia:

- Lay 1 gia tri don tu bang lookup duoc cho phep.
- Thuong dung voi opening balance, tax rate.

Luu y:

- Entity lookup bi whitelist.
- Neu lookup khong tim thay ban ghi phu hop -> nen fallback `0` (khuyen nghi).

---

## 4.5 `op` (phep toan 2 ngoi)

Cau truc:

```json
{
  "op": "MULTIPLY",
  "left": { "ref": "S2A_QUARTERLY_TOTAL" },
  "right": { "literal": 0.01 }
}
```

Toan tu ho tro:

1. `ADD`: `left + right`
2. `SUBTRACT`: `left - right`
3. `MULTIPLY`: `left * right`
4. `DIVIDE`: `left / right`

Quy tac quan trong cho `DIVIDE`:

- Neu mau so = 0 -> tra ve `0` (khong throw).

---

## 4.6 `fn` (ham)

Cau truc:

```json
{
  "fn": "MAX",
  "args": [
    { "literal": 0 },
    { "ref": "S2C_PROFIT" }
  ]
}
```

Ham ho tro:

1. `MAX(a,b,...)`
2. `MIN(a,b,...)`
3. `ABS(a)`
4. `ROUND(value, precision)`

Luu y:

- So luong args phai dung voi tung ham.
- `ROUND` trong expression co the ket hop voi `RoundingMode`/`RoundingPrecision` cap formula; can thong nhat quy uoc de tranh round hai lan ngoai y muon.

---

## 4.7 `context`

Cau truc:

```json
{ "context": "period_start" }
```

Y nghia:

- Lay gia tri runtime tu context hien tai.
- Thuong dung trong filter nang cao hoac lookup dieu kien.

---

## 5. Bieu do phu thuoc toan tu

Thu tu de quy cua 1 expression nhu sau:

```text
op/fn
|- left/arg1
|  |- ...
|- right/arg2
   |- ...
```

Nguyen tac:

- Node con xong thi node cha moi xong.
- Loi o node con se bubble len node cha.

---

## 6. Vi du end-to-end

## 6.1 Formula S2C_PROFIT

Expression:

```json
{
  "op": "SUBTRACT",
  "left": { "ref": "S2C_TOTAL_REVENUE" },
  "right": { "ref": "S2C_TOTAL_COST" }
}
```

Gia su:

- `S2C_TOTAL_REVENUE = 620000000`
- `S2C_TOTAL_COST = 540000000`

Ket qua:

- `S2C_PROFIT = 80000000`

## 6.2 Formula S2C_PIT

Expression:

```json
{
  "op": "MULTIPLY",
  "left": {
    "fn": "MAX",
    "args": [
      { "literal": 0 },
      { "ref": "S2C_PROFIT" }
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

Gia su:

- `S2C_PROFIT = 80000000`
- `PIT_M1 = 0.005`

Ket qua:

- `MAX(0, 80000000) = 80000000`
- `80000000 * 0.005 = 400000`

---

## 7. Quy tac khi sua formula (impact)

Khi sua `ExpressionJson`, impact di theo 2 lop:

1. Lop summary:
- Tong doanh thu/chi phi/thue thay doi neu formula summary doi.

2. Lop row:
- Cac field mapping co `FormulaId` trung formula vua sua se doi gia tri.
- Cac formula khac dung `ref` den formula nay cung doi theo.

Do do can test theo flow:

1. Capture preview truoc khi sua.
2. Update formula.
3. Preview lai.
4. Diff summary + diff row.

---

## 8. Cac loi thuong gap

1. `FORMULA_MISSING_REF`
- Nguyen nhan: `ref` tro den code khong ton tai/khong nam trong tap evaluate.
- Cach xu ly: kiem tra code, order, scope.

2. `FORMULA_CIRCULAR_DEP`
- Nguyen nhan: A ref B va B ref A.
- Cach xu ly: tach cong thuc trung gian, sap xep lai dependency.

3. `FORMULA_ORDER_VIOLATION`
- Nguyen nhan: formula order thap lai ref formula order cao.
- Cach xu ly: doi `CalculationOrder`.

4. `FORMULA_AGGREGATE_INVALID_SOURCE`
- Nguyen nhan: `source` khong thuoc whitelist.
- Cach xu ly: them metadata hop le hoac sua source.

5. `FORMULA_LOOKUP_DENIED`
- Nguyen nhan: lookup entity khong duoc phep.
- Cach xu ly: su dung entity lookup duoc whitelist.

---

## 9. Checklist review nhanh cho Admin/Consultant

Truoc khi activate template/formula:

1. Formula co `ref` dung code va dung order?
2. `aggregate.source` + `field` co trong metadata whitelist?
3. `DIVIDE` co nguy co mau so = 0? da chap nhan rule tra 0 chua?
4. Round co bi lap (ROUND trong expression + rounding cap formula) khong?
5. Da test preview before/after va doc diff summary + row chua?

---

## 10. Appendix: mini snippets

### 10.1 Cong don gian VAT

```json
{
  "op": "MULTIPLY",
  "left": { "ref": "S2B_QUARTERLY_TOTAL" },
  "right": {
    "lookup": {
      "entity": "IndustryTaxRates",
      "field": "TaxRate",
      "filter": { "TaxType": "VAT" }
    }
  }
}
```

### 10.2 Bao ve gia tri am

```json
{
  "fn": "MAX",
  "args": [
    { "literal": 0 },
    { "ref": "S2C_PROFIT" }
  ]
}
```

### 10.3 Binh quan gia quyen

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
