# BizFlow Authentication Flow

> Version: 1.0  
> Status: Draft  
> Last Updated: 2026-03-12

---

## 1. Tổng Quan

BizFlow hỗ trợ 3 phương thức xác thực:

| # | Phương thức         | Identity     | Password |
|---|---------------------|--------------|----------|
| 1 | Phone + Password    | Phone Number | ✅        |
| 2 | Email + Password    | Email        | ✅        |
| 3 | Google OAuth        | Google ID    | ❌        |

Một user có thể liên kết nhiều phương thức xác thực vào cùng một tài khoản.
Phone và Email dùng **chung 1 password** (lưu trên Account).

```
Account
 ├─ PasswordHash (nullable — Google-only accounts không có password)
 ├─ Profile (1:1)
 └─ Credentials (0..3)
      ├─ type=phone  │ identifier=+84901234567
      ├─ type=email  │ identifier=user@mail.com
      └─ type=google │ identifier=google-sub-id
```

---

## 2. Entity Model

### 2.1 Hiện trạng (Before)

```
Accounts
├── AccountId (PK)
├── RoleId (FK → Roles)
├── Email              ← auth field (sẽ tách ra)
├── Phone              ← auth field (sẽ tách ra)
├── PasswordHash       ← auth field (sẽ tách ra)
├── IsActive
├── EmailVerified      ← auth field (sẽ tách ra)
├── LastLoginAt
├── CreatedAt / UpdatedAt / DeletedAt

Profiles
├── ProfileId (PK)
├── AccountId (FK → Accounts, 1:1)
├── FullName / AvatarUrl / TaxCode
├── UpdatedAt
```

### 2.2 Target (After)

```
Accounts                          ← Identity hub + password
├── AccountId (PK, CHAR(36))
├── RoleId (FK → Roles)
├── PasswordHash (VARCHAR(255), nullable) ← Chung cho phone & email login
│                                           NULL khi account chỉ có Google
├── IsActive (BOOLEAN)
├── LastLoginAt (DATETIME)
├── CreatedAt / UpdatedAt / DeletedAt

Profiles                          ← Không đổi
├── ProfileId (PK)
├── AccountId (FK → Accounts, UNIQUE, 1:1)
├── FullName / AvatarUrl / TaxCode
├── UpdatedAt

Credentials                       ← MỚI (bảng chung cho mọi loại credential)
├── CredentialId (PK, CHAR(36))
├── AccountId (FK → Accounts)
├── Type (ENUM: 'phone', 'email', 'google')
├── Identifier (VARCHAR(255))     ← Phone: +84..., Email: user@..., Google: sub-id
├── EmailVerified (BOOLEAN)       ← Chỉ dùng cho type=email, default false
├── GoogleEmail (VARCHAR(255))    ← Chỉ dùng cho type=google (informational)
├── CreatedAt (DATETIME)
├── UNIQUE(Type, Identifier)      ← Mỗi identity là duy nhất trong system
├── UNIQUE(AccountId, Type)       ← Mỗi account chỉ có tối đa 1 credential/type

RefreshTokens                     ← MỚI
├── RefreshTokenId (PK, CHAR(36))
├── AccountId (FK → Accounts)
├── TokenHash (VARCHAR(512))      ← SHA-256 hash of token
├── TokenSalt (VARCHAR(128))      ← Random salt per token
├── DeviceInfo (VARCHAR(500))     ← User-Agent / device identifier
├── ExpiresAt (DATETIME)
├── RevokedAt (DATETIME, nullable) ← NULL = active, NOT NULL = revoked
├── CreatedAt (DATETIME)
```

**Tại sao PasswordHash nằm trên Account?**

- Phone và Email dùng chung 1 password → không cần lưu riêng per credential
- Google-only account → PasswordHash = NULL
- Khi user link thêm Phone hoặc Email lần đầu, bắt buộc set password (nếu chưa có)

### 2.3 ERD Diagram

```
┌──────────────┐       ┌──────────────────┐
│    Roles     │       │    Accounts      │
│──────────────│       │──────────────────│
│ RoleId (PK)  │◄──FK──│ AccountId (PK)   │
│ Name         │       │ RoleId (FK)      │
│ Description  │       │ PasswordHash ?   │
│ CreateAt     │       │ IsActive         │
│ UpdateAt     │       │ LastLoginAt      │
└──────────────┘       │ CreatedAt        │
                       │ UpdatedAt        │
                       │ DeletedAt        │
                       └──┬───────┬───────┘
                          │       │
          ┌───────────────┤       ├───────────────┐
          │               │       │               │
          ▼               ▼       ▼               ▼
┌──────────────┐ ┌──────────────────┐ ┌──────────────────┐
│   Profiles   │ │   Credentials    │ │  RefreshTokens   │
│──────────────│ │──────────────────│ │──────────────────│
│ProfileId(PK) │ │CredentialId (PK) │ │RefreshTokenId    │
│AccountId(UQ) │ │AccountId (FK)    │ │AccountId (FK)    │
│FullName      │ │Type (enum)       │ │TokenHash         │
│AvatarUrl     │ │Identifier (UQ*)  │ │TokenSalt         │
│TaxCode       │ │EmailVerified     │ │DeviceInfo        │
│UpdatedAt     │ │GoogleEmail       │ │ExpiresAt         │
└──────────────┘ │CreatedAt         │ │RevokedAt         │
                 │                  │ │CreatedAt         │
                 │UQ(Type,Identifier)│ └──────────────────┘
                 │UQ(AccountId,Type)│
                 └──────────────────┘
```

---

## 3. Identity Rules

| Identity     | Constraint        | Scope     |
|--------------|-------------------|-----------|
| PhoneNumber  | UNIQUE, NOT NULL  | Global    |
| Email        | UNIQUE, NOT NULL  | Global    |
| GoogleId     | UNIQUE, NOT NULL  | Global    |

Hệ quả:
- 1 phone number = 1 account duy nhất
- 1 email = 1 account duy nhất
- 1 Google account = 1 account duy nhất
- 1 account có thể sở hữu đồng thời: Phone + Email + Google

---

## 4. Phone Number Validation

Chỉ hỗ trợ số điện thoại Việt Nam.

**Input format:**

```markdown
^0\d{9}$
```

**Normalization (trước khi lưu):**

```markdown
0xxxxxxxxx → +84xxxxxxxxx
```

Ví dụ: `0901234567` → `+84901234567`

**Stored format:**

```markdown
^\+84\d{9}$
```

---

## 5. Authentication Flows

### 5.1 Register with Phone + Password

```markdown
┌──────┐          ┌──────────┐          ┌───────────┐
│Client│          │ BizFlow  │          │OTP Service│
└──┬───┘          └────┬─────┘          └─────┬─────┘
   │  POST /auth/      │                      │
   │  phone/register   │                      │
   │  {phone}          │                      │
   │──────────────────►│                      │
   │                   │ Validate format      │
   │                   │ Check phone unique   │
   │                   │ Send OTP ───────────►│
   │  200 {otpToken}   │                      │
   │◄──────────────────│                      │
   │                   │                      │
   │  POST /auth/      │                      │
   │  phone/verify-otp │                      │
   │  {otpToken, otp}  │                      │
   │──────────────────►│                      │
   │                   │ Verify OTP ─────────►│
   │  200 {verified}   │                      │
   │◄──────────────────│                      │
   │                   │                      │
   │  POST /auth/      │                      │
   │  phone/set-password                      │
   │  {otpToken, pwd}  │                      │
   │──────────────────►│                      │
   │                   │ Create Account       │
   │                   │ Create Profile       │
   │                   │ Create Credential    │
   │                   │  (type=phone)        │
   │                   │ Issue JWT + Refresh  │
   │  200 {tokens}     │                      │
   │◄──────────────────│                      │
```

**Steps:**

1. User nhập phone number
2. Server validate format (`^0\d{9}$`)
3. Server normalize (`+84...`) và check unique
4. Server gửi OTP (expire 5 phút)
5. User nhập OTP
6. Server verify OTP
7. User set password
8. Server tạo Account (với PasswordHash) → Profile → Credential (type=phone)
9. Server issue JWT access token + refresh token
10. User logged in

### 5.2 Register with Google OAuth

```markdown
┌──────┐          ┌──────────┐          ┌────────┐
│Client│          │ BizFlow  │          │ Google │
└──┬───┘          └────┬─────┘          └───┬────┘
   │  POST /auth/      │                    │
   │  google            │                    │
   │  {idToken}        │                    │
   │──────────────────►│                    │
   │                   │ Verify token ─────►│
   │                   │◄── GoogleId+Email ─│
   │                   │                    │
   │                   │ GoogleId exists?   │
   │                   │ ┌─YES → Login      │
   │                   │ └─NO  → Register   │
   │                   │                    │
   │  200 {tokens,     │                    │
   │   isNewAccount}   │                    │
   │◄──────────────────│                    │
```

**Nếu GoogleId chưa tồn tại (Register):**

1. Tạo Account (IsActive = true, PasswordHash = NULL)
2. Tạo Profile (FullName = Google display name)
3. Tạo Credential (type=google, identifier=GoogleId, googleEmail=email)
4. Issue JWT + refresh token
5. Response kèm `isNewAccount: true`

**Sau register Google lần đầu:**

- User **phải** thiết lập ít nhất 1 credential fallback:
  - Phone + Password **HOẶC** Email + Password
- UI hiển thị prompt yêu cầu setup

### 5.3 Login with Phone + Password

```markdown
POST /auth/login/phone
{
    "phone": "0901234567",
    "password": "***"
}
```

**Steps:**

1. Normalize phone → `+84901234567`
2. Tìm Credential (type=phone, identifier=+84901234567)
3. Lấy Account → verify Account.PasswordHash (BCrypt)
4. Cập nhật `Account.LastLoginAt`
5. Issue JWT access token + refresh token

### 5.4 Login with Email + Password

```markdown
POST /auth/login/email
{
    "email": "user@example.com",
    "password": "***"
}
```

**Steps:**

1. Tìm Credential (type=email, identifier=email)
2. Lấy Account → verify Account.PasswordHash (BCrypt)
3. Cập nhật `Account.LastLoginAt`
4. Issue JWT access token + refresh token

### 5.5 Login with Google

Cùng endpoint với Register Google (`POST /auth/google`).

- GoogleId tồn tại → Login, issue tokens
- GoogleId chưa tồn tại → Register (tạo account mới)

**Lưu ý khi tạo account mới:**
> "If you already have an account, login first and link Google in Settings."

---

## 6. JWT Token Strategy

### 6.1 Access Token

| Field        | Value                  |
|-------------|------------------------|
| Type        | JWT (JWS, HS256/RS256) |
| Lifetime    | 15 minutes             |
| Storage     | Client memory          |
| Contains    | AccountId, RoleId/RoleName, ProfileId |

**Access Token Claims:**

```json
{
    "sub": "<AccountId>",
    "profileId": "<ProfileId>",
    "role": "<RoleName>",
    "iat": 1741785600,
    "exp": 1741786500
}
```

### 6.2 Refresh Token

| Field        | Value                        |
|-------------|------------------------------|
| Type        | Opaque random string (256-bit)|
| Lifetime    | 7 days                       |
| Storage     | HttpOnly Secure Cookie       |
| DB Storage  | Hash + Salt in RefreshTokens |

### 6.3 Token Flow

```
┌──────┐                    ┌──────────┐
│Client│                    │ BizFlow  │
└──┬───┘                    └────┬─────┘
   │                             │
   │  Login / Register            │
   │─────────────────────────────►│
   │  {accessToken, refreshToken} │
   │◄─────────────────────────────│  ← refreshToken set via HttpOnly cookie
   │                             │
   │  API call                   │
   │  Authorization: Bearer <AT> │
   │─────────────────────────────►│
   │  200 response               │
   │◄─────────────────────────────│
   │                             │
   │  API call (AT expired)      │
   │  Authorization: Bearer <AT> │
   │─────────────────────────────►│
   │  401 Unauthorized           │
   │◄─────────────────────────────│
   │                             │
   │  POST /auth/refresh         │
   │  Cookie: refreshToken=<RT>  │
   │─────────────────────────────►│
   │                             │  Lookup RT hash in DB
   │                             │  Check not expired/revoked
   │                             │  Issue new AT + new RT
   │                             │  Revoke old RT
   │  {accessToken, refreshToken} │
   │◄─────────────────────────────│
   │                             │
   │  POST /auth/logout          │
   │  Cookie: refreshToken=<RT>  │
   │─────────────────────────────►│
   │                             │  Revoke RT (set RevokedAt)
   │  200 OK                     │
   │◄─────────────────────────────│
```

### 6.4 Refresh Token Rotation

Mỗi lần refresh:
1. Verify refresh token hash trong DB
2. Check `ExpiresAt > NOW()` và `RevokedAt IS NULL`
3. Revoke token cũ (`RevokedAt = NOW()`)
4. Tạo refresh token mới (new hash, new salt)
5. Issue access token mới

**Reuse Detection:**
- Nếu client gửi refresh token đã bị revoke → **revoke tất cả refresh tokens** của account đó (potential token theft)
- Force re-login

### 6.5 RefreshTokens Table Design

```sql
RefreshTokens
├── RefreshTokenId   CHAR(36) PK
├── AccountId        CHAR(36) FK → Accounts, NOT NULL
├── TokenHash        VARCHAR(512) NOT NULL     ← SHA-256(token + salt)
├── TokenSalt        VARCHAR(128) NOT NULL     ← Random salt (Base64)
├── DeviceInfo       VARCHAR(500)              ← User-Agent / device name
├── ExpiresAt        DATETIME NOT NULL         ← Token expiry
├── RevokedAt        DATETIME NULL             ← NULL = active
├── CreatedAt        DATETIME NOT NULL
```

**Indexes:**

- `idx_rt_account_id` on (AccountId) — tìm tất cả tokens của user
- `idx_rt_token_hash` on (TokenHash) — lookup nhanh khi verify
- `idx_rt_expires_at` on (ExpiresAt) — cleanup expired tokens

---

## 7. Account Linking

User đã đăng nhập có thể link thêm phương thức xác thực trong Settings.

### 7.1 Link Google

```
POST /auth/link/google
Authorization: Bearer <access_token>
{
    "idToken": "<Google ID Token>"
}
```

**Flow:**
1. Verify Google token → extract GoogleId
2. Check Credential (type=google, identifier=GoogleId) đã tồn tại chưa
   - **Đã tồn tại** → Reject: "This Google account is already linked to another user"
   - **Chưa** → Tạo Credential (type=google) cho account hiện tại

### 7.2 Link Phone

```
POST /auth/link/phone
Authorization: Bearer <access_token>
{
    "phone": "0901234567"
}
→ OTP flow → Verify → Set password →

POST /auth/link/phone/complete
{
    "otpToken": "...",
    "password": "***"
}
```

**Flow:**
1. Validate & normalize phone
2. Check Credential (type=phone, identifier=phone) đã tồn tại chưa
   - **Đã tồn tại** → Reject
   - **Chưa** → Gửi OTP → Verify → Tạo Credential (type=phone)
   - Nếu Account.PasswordHash = NULL → yêu cầu set password

### 7.3 Link Email

```
POST /auth/link/email
Authorization: Bearer <access_token>
{
    "email": "user@example.com",
    "password": "***"
}
```

**Flow:**
1. Validate email format
2. Check Credential (type=email, identifier=email) đã tồn tại chưa
   - **Đã tồn tại** → Reject
   - **Chưa** → Tạo Credential (type=email, emailVerified=false)
   - Nếu Account.PasswordHash = NULL → yêu cầu set password
   - Gửi verification email (optional)

---

## 8. Account Unlinking

### 8.1 Unlink Rule

```
credential_count = COUNT(Credentials WHERE AccountId = current_user)

IF credential_count > 1
    → Allow unlink

IF credential_count = 1
    → Require account deletion confirmation
```

### 8.2 Unlink Flow

```
DELETE /auth/link/{type}
Authorization: Bearer <access_token>
type = google | phone | email
```

**Case A — Còn credential khác:**
1. Xoá credential record
2. Response success

**Case B — Credential cuối cùng:**
1. Trả warning message:
   > "This is your last login method. If you unlink it, your account will be permanently deleted."
2. Client confirm → `DELETE /auth/link/{type}?confirm=true`
3. Hard delete account + tất cả credentials
4. Revoke tất cả refresh tokens
5. Logout user

---

## 9. Password Reset

Reset password chỉ hỗ trợ qua **Phone OTP**.

```
POST /auth/password/reset/request
{ "phone": "0901234567" }
→ Send OTP

POST /auth/password/reset/verify
{ "otpToken": "...", "otp": "123456" }
→ Verify OTP

POST /auth/password/reset/complete
{ "otpToken": "...", "newPassword": "***" }
→ Update Account.PasswordHash
→ Revoke ALL refresh tokens of this account
```

---

## 10. OTP Security Rules

| Rule              | Value       |
|-------------------|-------------|
| OTP Expiry        | 5 minutes   |
| Max Attempts      | 5           |
| Resend Cooldown   | 30 seconds  |
| OTP Length        | 6 digits    |
| OTP Storage       | Server-side |

---

## 11. API Endpoints Summary

### Authentication

| Method | Endpoint                          | Auth  | Description                    |
|--------|-----------------------------------|-------|--------------------------------|
| POST   | `/auth/register/phone`            | ❌     | Bắt đầu đăng ký bằng phone    |
| POST   | `/auth/register/phone/verify-otp` | ❌     | Verify OTP                     |
| POST   | `/auth/register/phone/complete`   | ❌     | Set password, tạo account      |
| POST   | `/auth/google`                    | ❌     | Login/Register bằng Google     |
| POST   | `/auth/login/phone`               | ❌     | Login bằng phone + password    |
| POST   | `/auth/login/email`               | ❌     | Login bằng email + password    |
| POST   | `/auth/refresh`                   | 🍪    | Refresh access token (cookie)  |
| POST   | `/auth/logout`                    | 🍪    | Revoke refresh token           |
| POST   | `/auth/logout/all`                | ✅     | Revoke tất cả refresh tokens   |

### Account Linking

| Method | Endpoint                          | Auth  | Description                    |
|--------|-----------------------------------|-------|--------------------------------|
| POST   | `/auth/link/google`               | ✅     | Link Google account            |
| POST   | `/auth/link/phone`                | ✅     | Bắt đầu link phone (OTP flow) |
| POST   | `/auth/link/phone/complete`       | ✅     | Hoàn tất link phone            |
| POST   | `/auth/link/email`                | ✅     | Link email + password          |
| DELETE | `/auth/link/google`               | ✅     | Unlink Google                  |
| DELETE | `/auth/link/phone`                | ✅     | Unlink Phone                   |
| DELETE | `/auth/link/email`                | ✅     | Unlink Email                   |

### Password

| Method | Endpoint                          | Auth  | Description                    |
|--------|-----------------------------------|-------|--------------------------------|
| POST   | `/auth/password/reset/request`    | ❌     | Gửi OTP reset password         |
| POST   | `/auth/password/reset/verify`     | ❌     | Verify OTP                     |
| POST   | `/auth/password/reset/complete`   | ❌     | Set new password               |
| PUT    | `/auth/password/change`           | ✅     | Đổi password (cần old password)|

### Credentials Info

| Method | Endpoint                          | Auth  | Description                    |
|--------|-----------------------------------|-------|--------------------------------|
| GET    | `/auth/credentials`               | ✅     | Lấy danh sách credentials đã link |

---

## 12. Migration Strategy

### Phase 1: Schema Migration (030)

Từ schema hiện tại (Account chứa Email/Phone/PasswordHash) sang unified credential model:

1. Giữ PasswordHash trên Accounts (nullable)
2. Tạo bảng Credentials (chung cho phone/email/google)
3. Tạo bảng RefreshTokens
4. Migrate dữ liệu:
   - Account.Email → Credential (type=email)
   - Account.Phone → Credential (type=phone, normalized)
5. Xoá columns cũ: Email, Phone, EmailVerified

### Phase 2: Backend Implementation

1. Domain Entities: Credential, RefreshToken
2. Infrastructure: EF configurations, repositories
3. Application: AuthService, JwtService, OtpService
4. API: AuthController

---

## 13. Decisions & Open Items

| #  | Item                               | Status    | Decision / Note                           |
|----|------------------------------------|-----------|-------------------------------------------|
| 1  | Access Token algorithm             | Decided   | HS256 (symmetric, đơn giản cho monolith)  |
| 2  | Access Token lifetime              | Decided   | 15 minutes                                |
| 3  | Refresh Token lifetime             | Decided   | 7 days                                    |
| 4  | Refresh Token storage (client)     | Decided   | HttpOnly Secure Cookie                    |
| 5  | Password hashing                   | Decided   | BCrypt                                    |
| 6  | Password model                     | Decided   | 1 password per account (shared phone/email)|
| 7  | Credential storage                 | Decided   | Unified Credentials table with Type enum  |
| 8  | Account deletion strategy          | **Open**  | Hard delete vs Soft delete (TBD)          |
| 9  | OTP provider                       | **Open**  | Firebase Auth / Twilio / custom?          |
| 10 | Email verification flow            | **Open**  | Required before login? Or optional?       |
| 11 | Rate limiting                      | **Open**  | Login attempt limits? IP-based?           |
