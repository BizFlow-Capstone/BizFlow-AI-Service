# Accounting Book Revenue-Centric Plan (MVP)

> Module: Report & Accounting
> Status: Agreed with BA discussion (pre-release, can reset DB)
> Date: 2026-03-28

---

## 1. Muc tieu va ket luan da chot

### 1.1 Muc tieu

- Don gian hoa luong Accounting Book cho Owner.
- Nganh nghe de tinh thue phai di tu doanh thu thuc te.
- Van cho phep chinh sua Revenue/Cost sau khi ky da ket thuc.
- Snapshot da export/da chot khong bi hoi to.

### 1.2 Ket luan nghiep vu da chot

- Nguon phan loai nganh nghe duy nhat: `Revenues.BusinessTypeId`.
- Accounting Book la live view (doc du lieu), khong phan loai nganh trong Book.
- Danh sach nganh trong Book = cac nganh co doanh thu phat sinh trong ky.
- Override chi la `%VAT` va `%PIT` theo tung nganh trong Book.
- Thu tu uu tien tinh: `Override > Default Ruleset`.
- Bat buoc nhap `note` khi override.
- Ky da finalize:
  - Book mode = snapshot/frozen de doi soat.
  - Khong cho sua override tren Book da finalize.
  - Van cho sua Revenue/Cost (du lieu nguon) neu nghiep vu can.
  - Sua du lieu nguon khong lam doi snapshot da export.
- Moi template trong 1 location + period chi co 1 book.

---

## 2. UX Flow cho Frontend

### 2.1 Man hinh: Book List
- Liet ke Book theo ky.
- Moi `TemplateCode` chi hien thi 1 Book.
- Hien `periodStatus` (open/finalized).

### 2.2 Man hinh: Book Detail (Summary + Rows)
- Hien KPI: total revenue, VAT, PIT.
- Hien row theo template (S2a, S2b, ...).
- Hien badge nguon ty le thue theo nganh:
  - `DEFAULT`
  - `OVERRIDE`

### 2.3 Man hinh: Tax Override Drawer
- Hien cac nganh co phat sinh doanh thu trong ky.
- Cho phep user sua `%VAT`, `%PIT`, bat buoc `note`.
- Co nut `Reset ve mac dinh` cho 1 nganh hoac tat ca.
- Sau khi luu: reload summary/rows + hien chenh lech.

### 2.4 Man hinh: Revenue Classification Center
- Hien cac dong Revenue manual chua phan loai hoac sai nganh.
- Ho tro bulk reclassify theo filter + select nhieu dong.
- Bat buoc co buoc preview impact truoc khi apply.

---

## 3. API Contract cho Frontend (MVP)

## 3.1 Nhom API Book (co san, tiep tuc dung)

### A. List books by period
- Method: `GET`
- Endpoint: `/api/locations/{locationId}/accounting/books?periodId={periodId}`
- Man hinh: Book List
- Muc dich: Lay danh sach Book cua 1 ky.
- Response mau:
```json
{
  "data": [
    {
      "bookId": 9001,
      "templateCode": "S2a",
      "templateName": "So doanh thu",
      "status": "active",
      "createdAt": "2026-03-28T09:00:00Z"
    }
  ]
}
```

### B. Get book summary
- Method: `GET`
- Endpoint: `/api/locations/{locationId}/accounting/books/{bookId}/summary`
- Man hinh: Book Detail
- Muc dich: Lay KPI tong hop.
- Response mau:
```json
{
  "data": {
    "bookId": 9001,
    "templateCode": "S2a",
    "totalRows": 132,
    "totalRevenue": 1250000000,
    "totalTax": 19000000,
    "totalVat": 12500000,
    "totalPit": 6500000,
    "lastCalculatedAt": "2026-03-28T09:10:00Z"
  }
}
```

### C. Get book rows
- Method: `GET`
- Endpoint: `/api/locations/{locationId}/accounting/books/{bookId}/rows?cursor={cursor}&batchSize={batchSize}`
- Man hinh: Book Detail
- Muc dich: Render bang chi tiet co phan trang cursor.
- Response mau:
```json
{
  "data": {
    "rows": [
      {
        "lineType": "industry_header",
        "businessTypeId": "c6b1275e-9054-4c89-bf27-df6dfb725001",
        "businessTypeName": "Ban le"
      },
      {
        "lineType": "revenue",
        "revenueId": 10021,
        "soHieu": "ORD-202603-001",
        "soTien": 4500000
      }
    ],
    "hasMore": true,
    "nextCursor": "eyJsYXN0SWQiOjEwMDIxfQ=="
  }
}
```

## 3.2 Nhom API moi: Tax Override theo Book

### D. Get effective tax rates in book
- Method: `GET`
- Endpoint: `/api/locations/{locationId}/accounting/books/{bookId}/tax-rates`
- Man hinh: Tax Override Drawer
- Muc dich: Lay danh sach nganh co phat sinh + ty le dang hieu luc.
- Response mau:
```json
{
  "data": [
    {
      "businessTypeId": "c6b1275e-9054-4c89-bf27-df6dfb725001",
      "businessTypeName": "Ban le",
      "revenueTotal": 900000000,
      "effectiveVatRate": 0.01,
      "effectivePitRate": 0.005,
      "rateSource": "DEFAULT",
      "note": null
    },
    {
      "businessTypeId": "5e0ff9ba-7041-4e0e-8d8f-fd7652a91111",
      "businessTypeName": "Dich vu",
      "revenueTotal": 350000000,
      "effectiveVatRate": 0.03,
      "effectivePitRate": 0.02,
      "rateSource": "OVERRIDE",
      "note": "Dieu chinh theo huong dan cap nhat"
    }
  ]
}
```

### E. Upsert tax override by business type
- Method: `PUT`
- Endpoint: `/api/locations/{locationId}/accounting/books/{bookId}/tax-overrides/{businessTypeId}`
- Man hinh: Tax Override Drawer
- Muc dich: Tao/sua override VAT, PIT cua 1 nganh trong book.
- Request mau:
```json
{
  "vatRate": 0.03,
  "pitRate": 0.02,
  "note": "Dieu chinh theo thong bao moi"
}
```
- Response mau:
```json
{
  "data": {
    "bookId": 9001,
    "businessTypeId": "5e0ff9ba-7041-4e0e-8d8f-fd7652a91111",
    "effectiveVatRate": 0.03,
    "effectivePitRate": 0.02,
    "rateSource": "OVERRIDE",
    "updatedAt": "2026-03-28T09:20:00Z"
  }
}
```

### F. Reset overrides
- Method: `POST`
- Endpoint: `/api/locations/{locationId}/accounting/books/{bookId}/tax-overrides/reset`
- Man hinh: Tax Override Drawer
- Muc dich: Reset 1 nganh hoac tat ca ve default ruleset.
- Request mau (mot so nganh):
```json
{
  "businessTypeIds": [
    "5e0ff9ba-7041-4e0e-8d8f-fd7652a91111"
  ]
}
```
- Request mau (toan bo):
```json
{
  "businessTypeIds": []
}
```

## 3.3 Nhom API moi: Revenue bulk reclassify

### G. List classification candidates
- Method: `GET`
- Endpoint: `/api/locations/{locationId}/revenues/classification-candidates?periodId={periodId}&status={status}`
- Man hinh: Revenue Classification Center
- Muc dich: Lay danh sach dong can sua nganh.
- Response mau:
```json
{
  "data": {
    "items": [
      {
        "revenueId": 10101,
        "revenueDate": "2026-02-15",
        "amount": 2500000,
        "revenueType": "manual",
        "businessTypeId": null,
        "description": "Thu nhap bo sung"
      }
    ],
    "total": 1
  }
}
```

### H. Preview reclassify
- Method: `POST`
- Endpoint: `/api/locations/{locationId}/revenues/reclassify/preview`
- Man hinh: Revenue Classification Center
- Muc dich: Xem tac dong truoc khi apply hang loat.
- Request mau:
```json
{
  "periodId": 202601,
  "revenueIds": [10101, 10102, 10103],
  "targetBusinessTypeId": "c6b1275e-9054-4c89-bf27-df6dfb725001"
}
```
- Response mau:
```json
{
  "data": {
    "affectedCount": 3,
    "beforeByIndustry": [
      { "businessTypeId": "5e0ff9ba-7041-4e0e-8d8f-fd7652a91111", "revenueTotal": 8000000 }
    ],
    "afterByIndustry": [
      { "businessTypeId": "c6b1275e-9054-4c89-bf27-df6dfb725001", "revenueTotal": 8000000 }
    ],
    "estimatedVatDiff": -120000,
    "estimatedPitDiff": -50000
  }
}
```

### I. Apply reclassify
- Method: `POST`
- Endpoint: `/api/locations/{locationId}/revenues/reclassify/apply`
- Man hinh: Revenue Classification Center
- Muc dich: Apply doi nganh cho nhieu dong Revenue.
- Request mau:
```json
{
  "periodId": 202601,
  "revenueIds": [10101, 10102, 10103],
  "targetBusinessTypeId": "c6b1275e-9054-4c89-bf27-df6dfb725001",
  "note": "Nhap nham nganh luc tao du lieu manual"
}
```
- Response mau:
```json
{
  "data": {
    "updatedCount": 3,
    "recalculationQueued": true
  }
}
```

---

## 4. Validation Rules cho Frontend

- Manual revenue bat buoc co `businessTypeId`.
- `vatRate` va `pitRate` trong khoang hop le (de xuat: `0 <= rate <= 1`).
- `note` bat buoc khi tao/sua override.
- Neu ky `finalized`:
  - Disable nut sua override trong Book.
  - Van cho sua Revenue/Cost theo nghiep vu, nhung can hien canh bao: "Khong anh huong snapshot da export".

---

## 5. Migration Action Checklist (pre-release reset)

> Muc tieu: don gian hoa logic theo Revenue-centric model, bo lien ket truc tiep AccountingBook-BusinessType.

### 5.1 File can SUA ngay
- `database/migrations/036_create_revenues.sql`
  - Them cot `BusinessTypeId` (FK den `BusinessTypes`), dung de phan loai nganh tai nguon Revenue.
- `database/migrations/055_create_accounting_book_tables.sql`
  - Bo phan tao bang `AccountingBookBusinessTypes`.
  - Giu `AccountingBooks` + `AccountingExports`.
  - Them unique rule cho 1 book / 1 template / 1 period / 1 location (neu chua co).

### 5.2 File can XOA
- `database/migrations/066_repair_missing_accounting_book_tables.sql`
  - File nay ton tai de sua thieu bang `AccountingBookBusinessTypes`.
  - Khi da bo bang nay thi migration nay khong con y nghia.

### 5.3 File can TAO MOI
- `database/migrations/071_create_accounting_book_tax_overrides.sql`
  - Tao bang override VAT/PIT theo `BookId + BusinessTypeId`.
  - Luu `VatRate`, `PitRate`, `Note`, `UpdatedBy`, `UpdatedAt`.
  - Co unique index `(BookId, BusinessTypeId)`.

### 5.4 Cach reset de chay schema moi
1. Xoa data volume docker mysql.
2. Xoa record `__MigrationHistory` (hoac tao DB moi tu dau).
3. Chay lai toan bo migrations theo thu tu.
4. Scaffold entities va build lai.

---

## 6. Ke hoach trien khai (Sprint-level)

### Sprint 1: Data model + migration
- Revenue co BusinessTypeId.
- Bo AccountingBookBusinessTypes.
- Co AccountingBookTaxOverrides.

### Sprint 2: Book read path
- Book rows/summary doc nganh tu Revenue.
- Tax rate resolver: Override > Default.

### Sprint 3: Override APIs + UI
- Get tax rates in book.
- Upsert/reset override.
- UI Tax Override Drawer.

### Sprint 4: Reclassify APIs + UI
- Candidate list.
- Preview impact.
- Apply bulk reclassify.

### Sprint 5: Hardening
- Validation finalized period behavior.
- UAT cho S2a/S2b voi case sai nganh + override.
- Regression test export snapshot.
