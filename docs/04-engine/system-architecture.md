# System Architecture

## 1. Overview

BizFlow is a multi-tier, cloud-hosted platform that supports digital transformation for household businesses in Vietnam. The system is composed of four main subsystems deployed on a VPS, two client applications deployed separately, a managed cloud database, and a set of external third-party services.

The architecture follows **Clean Architecture** principles on the backend — the domain and application logic are completely independent from infrastructure concerns (database, file storage, external APIs). All subsystems communicate exclusively over HTTPS.

---

## 2. System Architecture Diagram

```markdown
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                   CLIENT TIER                                   │
│                                                                                 │
│   ┌─────────────────────────────┐      ┌─────────────────────────────────────┐  │
│   │     Web Application         │      │      Mobile Application             │  │
│   │     (ReactJS)               │      │      (Flutter)                      │  │
│   │                             │      │                                     │  │
│   │  Deployed on: Vercel        │      │  Distributed as: Internal APK       │  │
│   │  Users: Admin, Consultant,  │      │  Users: Business Owner, Employee    │  │
│   │         Business Owner      │      │                                     │  │
│   └─────────────┬───────────────┘      └────────────────────┬────────────────┘  │
└─────────────────┼───────────────────────────────────────────┼───────────────────┘
                  │ HTTPS (REST/JSON)                         │ HTTPS (REST/JSON)
                  └─────────────────────┬─────────────────────┘
                                        │
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        VPS — Docker Compose                                      │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │  Nginx (Reverse Proxy + SSL Termination)                                 │   │
│   │  • Terminates HTTPS with Let's Encrypt certificate                       │   │
│   │  • Routes /api/* → BizFlow API                                           │   │
│   │  • Routes /ai/*  → AI Service                                            │   │
│   │  • Rate limiting, security headers                                       │   │
│   └────────────────────────────┬─────────────────────────────────────────────┘   │
│                                │                                                 │
│          ┌─────────────────────┴────────────────────┐                            │
│          │                                          │                            │
│   ┌──────▼──────────────────────────┐  ┌────────────▼───────────────────────┐    │
│   │   BizFlow API                   │  │   AI Service                       │    │
│   │   (.NET 8 / ASP.NET Core)       │  │   (Python / FastAPI)               │    │
│   │                                 │  │                                    │    │
│   │  • REST API (Controllers)       │  │  • Voice-to-Draft-Order            │    │
│   │  • JWT Authentication           │  │    (Whisper STT + RAG + LLM)       │    │
│   │  • Google OAuth 2.0             │  │  • Revenue Forecasting             │    │
│   │  • Business Logic (Services)    │  │    (Facebook Prophet)              │    │
│   │  • Background Jobs (Hangfire)   │  │  • Anomaly Detection               │    │
│   │  • i18n (vi / en)               │  │    (Isolation Forest)              │    │
│   │  • Triggers AI jobs (scheduled) │  │  • Reorder Suggestions             │    │
│   └─────────────────────────────────┘  │    (sales velocity + seasonality)  │    │
│                                        └────────────────────────────────────┘    │
│                        │                                                         │
└────────────────────────┼─────────────────────────────────────────────────────────┘
                         │ SSL/TLS (required)
┌────────────────────────▼────────────────────┐
│   Aiven.io — Managed MySQL 8.0              │
│   • Primary data store                      │
│   • Automatic backups + point-in-time       │
│     restore                                 │
│   • High availability                       │
│   • Monitoring dashboard                    │
└─────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│                           EXTERNAL SERVICES                                      │
│                                                                                  │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐   │
│   │  Google OAuth    │  │  Cloudinary      │  │  Stripe                      │   │
│   │  2.0             │  │  (Image CDN)     │  │  (Subscription Payment)      │   │
│   │                  │  │                  │  │                              │   │
│   │  Social login    │  │  Upload, store   │  │  sk_test_* (dev)             │   │
│   │  for all users   │  │  & serve images  │  │  sk_live_* (prod)            │   │
│   └──────────────────┘  └──────────────────┘  └──────────────────────────────┘   │
│                                                                                  │
│   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────────┐   │
│   │  Firebase FCM    │  │  Firebase Phone  │  │  OpenAI / Gemini             │   │
│   │  (Push Notif.)   │  │  Auth (SMS OTP)  │  │  (LLM)                       │   │
│   │                  │  │                  │  │                              │   │
│   │  Mobile + Web    │  │  Registration &  │  │  Used by AI Svc              │   │
│   │  push            │  │  password change │  │                              │   │
│   └──────────────────┘  └──────────────────┘  └──────────────────────────────┘   │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │  Google Speech-to-Text / Whisper (STT) — Used by AI Service              │   │
│   └──────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────────────────┐
│                             CI/CD PIPELINE                                       │
│                                                                                  │
│   Developer → git push → GitHub → GitHub Actions                                 │
│                                        │                                         │
│                          ┌─────────────┴─────────────┐                           │
│                          │  build → test → docker    │                           │
│                          │  build → SSH deploy to VPS│                           │
│                          └───────────────────────────┘                           │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Component Descriptions

### 3.1 Client Applications

#### Web Application (ReactJS)

- **Role:** Primary management interface for Administrators, Consultants, and Business Owners accessing through a browser.
- **Deployment:** Vercel (global CDN, zero-config deployment, automatic preview deployments per branch).
- **Connectivity:** Communicates with the BizFlow API exclusively via HTTPS REST calls. Receives push notifications via Firebase FCM Web SDK.
- **Users:** Admin (platform management, user management, subscription pricing, analytics), Consultant (financial template management, notifications), Business Owner (orders, products, inventory, reports, debt management).

#### Mobile Application (Flutter)

- **Role:** Primary interface for Business Owners and Employees in day-to-day operations — creating orders, recording imports, managing products, and using the AI voice-to-order feature.
- **Deployment:** Distributed as an internal APK (no public app store release at this stage).
- **Connectivity:** Communicates with the BizFlow API via HTTPS. Receives push notifications via Firebase FCM Flutter SDK. Audio for speech-to-text is captured on device and sent to the AI Service.
- **Users:** Business Owner, Employee.

---

### 3.2 VPS — Docker Compose

All server-side services run in Docker containers on a single VPS, orchestrated by Docker Compose. The environment is split into two configurations: `dev` (local machine) using a local MySQL container, and `prod` (VPS) using the Aiven managed database.

#### Nginx (Reverse Proxy)

- **Role:** The single entry point for all inbound traffic to the VPS. It terminates TLS (HTTPS), handles SSL certificates via Let's Encrypt (Certbot), and proxies requests to the appropriate backend container.
- **Responsibilities:**
  - Redirect HTTP → HTTPS.
  - Route `/api/*` → BizFlow API container.
  - Route `/ai/*` → AI Service container.
  - Add HTTP security headers (`X-Frame-Options`, `Strict-Transport-Security`, etc.).
  - Rate limiting to protect against abuse.
- **Why needed:** Without Nginx, each service would need to manage its own TLS certificate. Nginx centralises this, allowing backend services to listen on plain HTTP internally while the public internet only ever sees HTTPS.

#### BizFlow API (.NET 8 / ASP.NET Core)

- **Role:** The core backend REST API. Implements all business logic for the platform.
- **Architecture:** Clean Architecture with four layers — Domain, Application, Infrastructure, API (Presentation).
- **Key responsibilities:**
  - Authenticate and authorise users (JWT Bearer + Google OAuth 2.0).
  - Verify Firebase ID Tokens issued after successful SMS OTP verification (registration & password change).
  - Expose REST endpoints for all platform features (products, locations, imports, hire, roles, etc.).
  - Coordinate with the database via the Repository/Unit of Work pattern.
  - Delegate image upload/delete to Cloudinary.
  - Trigger push notifications via Firebase FCM.
  - Process subscription payments via Stripe.
  - Schedule and execute background maintenance jobs via Hangfire.
  - Provide i18n responses in Vietnamese and English.

#### AI Service (Python / FastAPI)

- **Role:** An independent microservice that handles all AI/ML processing. Deployed as a Docker container on the same VPS, accessible only from the BizFlow API via the Docker internal network.
- **Key responsibilities:**
  - **Voice-to-Draft-Order:** Transcribe audio (Whisper / Google STT), retrieve matching products from ChromaDB (RAG), and use a Large Language Model (GPT-4o / Gemini) to extract a structured draft order from a natural language command.
  - **Revenue Forecasting:** Load historical daily sales from MySQL and run Facebook Prophet to generate 7–30 day forecasts with confidence intervals. Supports Vietnamese holiday effects and weekly seasonality.
  - **Anomaly Detection:** Analyse daily revenue and accounting records using Isolation Forest (scikit-learn) to detect unusual values (zero-revenue days, erroneous pricing, unexpected spikes). Generates Vietnamese-language alert descriptions via LLM.
  - **Reorder Suggestions:** Calculate sales velocity (14-day rolling average) and reorder points per product, factoring in current stock levels and seasonal demand patterns. Flag products at risk of stockout.
- **Communication patterns:**
  - *Synchronous* — Draft Order: BizFlow API proxies the client request and awaits the AI response (timeout: 30 s).
  - *Asynchronous / Scheduled* — Forecast, Anomaly, Reorder: Hangfire jobs (nightly, 01:00–03:00 AM) trigger the AI Service to recompute results. Results are stored in MySQL. Clients read pre-computed results via the BizFlow API with no model inference delay.
- **See also:** [AI Architecture](ai-architecture.md) for detailed design, data flows, and database schema for each feature.

---

### 3.3 Database — Aiven Managed MySQL 8.0

- **Role:** Primary persistent data store for the entire platform.
- **Why Aiven instead of a self-hosted container in production:**
  - Automatic daily backups with point-in-time restore.
  - Built-in high availability (read replicas available).
  - Enforced TLS/SSL for all connections.
  - Monitoring, alerting, and metrics dashboard without additional setup.
  - Frees VM resources — the VPS only runs application containers.
- **In development:** A local MySQL 8.0 Docker container (defined in `docker-compose.dev.yml`) is used instead, keeping dev isolated from production data.

---

### 3.4 External Services

| Service | Provider | Purpose | Used By |
|---|---|---|---|
| Google OAuth 2.0 | Google Cloud | Social login (sign in with Google) | BizFlow API |
| Cloudinary | Cloudinary Ltd. | Upload, store, transform, and CDN-serve images (products, users, import receipts) | BizFlow API |
| Stripe | Stripe Inc. | Subscription payment processing (test mode in dev, live mode in prod) | BizFlow API |
| Firebase FCM | Google Firebase | Push notification delivery to Flutter mobile app and ReactJS web app | BizFlow API |
| Firebase Phone Auth | Google Firebase | SMS OTP delivery and verification for account registration and password change | Client SDK + BizFlow API (Admin SDK) |
| OpenAI / Gemini | OpenAI / Google | Large Language Model for natural language → structured order extraction | AI Service |
| Google STT / Whisper | Google / OpenAI | Speech-to-text transcription for voice order input | AI Service |

---

### 3.5 CI/CD Pipeline (GitHub Actions)

- **Trigger:** `git push` to the `main` branch.
- **Steps:**
  1. Build the .NET solution and run unit tests.
  2. Build the Docker image for the BizFlow API.
  3. Push the image to the container registry (or build on the VPS directly).
  4. SSH into the VPS and execute `docker compose pull && docker compose up -d` to perform a rolling update with zero downtime.
- **Environment secrets** (`.env.prod` values) are stored as GitHub Actions Secrets and injected at deploy time — they are never committed to the repository.

---

## 4. Communication Flows

### 4.1 Standard API Request (e.g., Create Product)

```
Flutter/ReactJS
    → HTTPS POST /api/products
    → Nginx (TLS termination)
    → BizFlow API (ProductController)
    → ProductService (business logic)
    → IProductRepository → UnitOfWork
    → Aiven MySQL (persisted)
    ← Response JSON
    ← Nginx
    ← Client
```

### 4.2 AI Draft Order Flow (Voice to Draft)

```
Flutter App (captures audio)
    → HTTPS POST /api/ai/draft-order  (audio file)
    → Nginx
    → BizFlow API (proxies to AI Service)
    → AI Service: STT (audio → text)
    → AI Service: RAG (fetch product context from ChromaDB)
    → AI Service: LLM (text + context → structured draft order JSON)
    ← BizFlow API receives draft order
    ← Returns draft order to Flutter
Flutter shows draft for user to review/confirm
```

### 4.3 Image Upload Flow (e.g., Product Image)

```
ReactJS/Flutter (sends image file as multipart/form-data)
    → HTTPS POST /api/products/{id}/image
    → Nginx
    → BizFlow API (ImageService)
    → Cloudinary SDK: upload image
    ← Cloudinary returns public_id + secure_url
    → BizFlow API saves public_id to MySQL
    ← Returns image URL to client
Client renders image via Cloudinary CDN URL (no server bandwidth used)
```

### 4.4 OTP SMS — Account Registration Flow

OTP verification is handled client-side by the **Firebase Phone Auth SDK**. The backend never sees or stores the OTP — it only receives the resulting Firebase ID Token, which it verifies using the **Firebase Admin SDK**.

```
[Step 1 — Request OTP]
Flutter/ReactJS (user enters phone number)
    → Firebase SDK: verifyPhoneNumber(phoneNumber)
    → Firebase Phone Auth service
    → Firebase sends SMS OTP to user's phone
    ← Firebase SDK returns verificationId (stored on client)

[Step 2 — Verify OTP]
User enters received OTP in the UI
    → Firebase SDK: confirmCode(verificationId, otpCode)
    → Firebase Phone Auth service verifies OTP
    ← Firebase SDK returns FirebaseUser + Firebase ID Token

[Step 3 — Complete Registration]
Flutter/ReactJS sends Firebase ID Token + registration data (name, password, ...)
    → HTTPS POST /api/auth/register
    → Nginx
    → BizFlow API (AuthController)
    → Firebase Admin SDK: verifyIdToken(firebaseIdToken)
    ← Firebase confirms token is valid + returns verified phone number
    → BizFlow API creates User record in MySQL with verified phone number
    ← Returns BizFlow JWT (access token + refresh token)
```

### 4.5 OTP SMS — Change Password Flow

```
[Step 1 — Request OTP] (same as above)
User triggers "Change Password" → Firebase SDK sends SMS OTP

[Step 2 — Verify OTP] (same as above)
User enters OTP → Firebase SDK returns Firebase ID Token

[Step 3 — Change Password]
Flutter/ReactJS sends Firebase ID Token + newPassword
    → HTTPS POST /api/auth/change-password
    → Nginx
    → BizFlow API (AuthController)
    → Firebase Admin SDK: verifyIdToken(firebaseIdToken)
    ← Confirms token is valid + phone matches the authenticated user's account
    → BizFlow API updates hashed password in MySQL
    ← Returns success response
```

> **Why Firebase Phone Auth instead of a custom OTP implementation:**
> - **Same Firebase project** as FCM — no new service to register or pay for.
> - **Free tier:** 10,000 SMS verifications per month (sufficient for a capstone and early production use).
> - **No OTP state on the backend:** BizFlow API does not need to generate, store, expire, or rate-limit OTP codes. Firebase handles all of this, eliminating a common source of security vulnerabilities.
> - **Replay-attack protection:** Firebase ID Tokens are short-lived (1 hour) and single-use for this context.
> - The backend only needs the **Firebase Admin SDK** (NuGet: `FirebaseAdmin`) to validate the token — a ~5-line call.

---

---

# Package Diagram

## 1. Overview

BizFlow's backend is structured according to **Clean Architecture**, which enforces a strict **inward dependency rule**: outer layers depend on inner layers, but inner layers have zero knowledge of outer layers. This guarantees the domain and business logic are always testable and replaceable in isolation.

```
┌───────────────────────────────────────────────────────────────────────┐
│                         BizFlow.Api                                    │
│  (Presentation Layer — HTTP, Authentication, Middleware)               │
│                                                                        │
│   depends on ↓                                                         │
├───────────────────────────────────────────────────────────────────────┤
│                      BizFlow.Application                               │
│  (Application Layer — Use Cases, Services, DTOs, Interfaces)          │
│                                                                        │
│   depends on ↓                                                         │
├───────────────────────────────────────────────────────────────────────┤
│                        BizFlow.Domain                                  │
│  (Domain Layer — Entities, Enums, Business Rules)                      │
│                                                                        │
│   ← depends on nothing internal →                                      │
├───────────────────────────────────────────────────────────────────────┤
│                     BizFlow.Infrastructure                             │
│  (Infrastructure Layer — EF Core, Repositories, External Services)    │
│                                                                        │
│   depends on Application (implements interfaces) + Domain (entities)  │
└───────────────────────────────────────────────────────────────────────┘
```

> **Key rule:** `BizFlow.Domain` and `BizFlow.Application` do **not** reference `BizFlow.Infrastructure`. The infrastructure layer implements the interfaces defined in the application layer — this is the Dependency Inversion Principle.

---

## 2. BizFlow.Domain

**Responsibility:** The innermost layer. Contains the core business objects with no external dependencies whatsoever.

```
BizFlow.Domain
├── Entities/
│   ├── BusinessLocation.cs         Entity: a physical store or business outlet owned by a user
│   ├── BusinessType.cs             Entity: category of business (e.g., grocery, hardware)
│   ├── BusinessTypeTax.cs          Entity: tax configuration associated with a business type
│   ├── Hire.cs                     Entity: employment relationship between a user and a location
│   ├── Import.cs                   Entity: a stock import batch (purchase of goods)
│   ├── ImportSchema.cs             Entity: defines the import template structure (master)
│   ├── ImportSchemaVersion.cs      Entity: a versioned revision of an ImportSchema
│   ├── Product.cs                  Entity: a product/item sold at a location
│   ├── ProductImport.cs            Entity: join table linking products to import batches
│   ├── ProductPricePolicy.cs       Entity: pricing rules per unit of measure for a product
│   ├── Role.cs                     Entity: system role (Admin, Consultant, User)
│   ├── SaleItem.cs                 Entity: a line item within an order/sale
│   ├── User.cs                     Entity: platform user account
│   └── UserLocationAssignment.cs   Entity: assignment of a user to manage a specific location
│
└── Enums/
    ├── BusinessTypeStatus.cs       Enum: Active / Inactive
    ├── ImportStatus.cs             Enum: Draft / Confirmed / Cancelled
    └── ProductStatus.cs            Enum: Active / Inactive
```

**Package explanations:**

| Package | Description |
|---|---|
| `Entities` | Plain C# classes (POCO) that map to database tables. They contain only properties and any domain invariants expressed as computed properties or validation guards. No EF Core attributes — configuration is done in the Infrastructure layer via Fluent API. |
| `Enums` | Strongly-typed enumerations representing the possible states of domain models. Defined here so both Application and Infrastructure layers can reference them without circular dependencies. |

---

## 3. BizFlow.Application

**Responsibility:** The application use-case layer. Orchestrates domain objects to fulfill business requirements. Defines **what** the system does, without knowing **how** it's implemented (no database or HTTP knowledge).

```
BizFlow.Application
├── ApplicationModule.cs                AutoFac DI registration for application-layer services
│
├── Common/
│   ├── Constants/
│   │   └── MessageKeys.cs              String constants for i18n message lookup keys
│   │
│   ├── Exceptions/
│   │   ├── BadRequestException.cs      400 — invalid input
│   │   ├── ConflictException.cs        409 — business rule conflict (e.g., duplicate name)
│   │   ├── ForbiddenException.cs       403 — access denied
│   │   ├── NotFoundException.cs        404 — resource not found
│   │   └── UnauthorizedException.cs    401 — unauthenticated request
│   │
│   ├── Interfaces/
│   │   ├── IJwtService.cs              Contract: generate and validate JWT tokens
│   │   ├── IMessageService.cs          Contract: i18n message resolution
│   │   ├── IPaymentService.cs          Contract: subscription payment processing (Stripe)
│   │   └── ISpecification.cs           Contract: Specification pattern for query expressions
│   │
│   ├── Models/
│   │   ├── ApiResponse.cs              Wrapper for all API responses (success/error shape)
│   │   ├── CloudinaryResourcePage.cs   Pagination model for Cloudinary resource queries
│   │   ├── CloudinarySettings.cs       Strongly-typed config model for Cloudinary
│   │   ├── GoogleAuthConfig.cs         Strongly-typed config model for Google OAuth
│   │   ├── ImageSettings.cs            Config: max file size, allowed extensions
│   │   ├── ImageUploadInfo.cs          DTO carrying image upload result (public_id, url)
│   │   ├── JwtSettings.cs              Strongly-typed config model for JWT
│   │   ├── PaginatedResponse.cs        Generic paginated list wrapper
│   │   ├── PaginationParams.cs         Incoming pagination parameters (page, size)
│   │   └── PaginationSettings.cs       Config: default and max page sizes
│   │
│   └── Specifications/
│       └── BaseSpecification.cs        Base class implementing ISpecification with filter, include, sort
│
├── DTOs/                               Data Transfer Objects — the shapes of request/response JSON
│   ├── BusinessType/
│   │   └── BusinessTypeDto.cs
│   ├── Hire/
│   │   ├── EmployeeSummaryDto.cs
│   │   ├── EmployeeValidationResult.cs
│   │   └── HiredEmployeeDto.cs
│   ├── Import/
│   │   ├── CreateImportRequest.cs
│   │   ├── ImportDetailDto.cs
│   │   ├── ImportItemRequest.cs
│   │   ├── ImportPatchResultDto.cs
│   │   ├── ImportQueryParams.cs
│   │   ├── ImportSchemaDto.cs
│   │   ├── ImportSummaryDto.cs
│   │   ├── PatchImportRequest.cs
│   │   └── UpdateImportRequest.cs
│   ├── ImportSchema/
│   │   ├── CreateImportSchemaRequest.cs
│   │   ├── ImportSchemaListItemDto.cs
│   │   ├── ImportSchemaResponse.cs
│   │   └── UpdateImportSchemaRequest.cs
│   ├── Location/
│   │   ├── BusinessLocationDto.cs
│   │   ├── CreateLocationRequest.cs
│   │   ├── UpdateLocationRequest.cs
│   │   └── UpdateLocationStatusRequest.cs
│   ├── Product/
│   │   ├── CreateProductRequest.cs
│   │   ├── ProductDetailDto.cs
│   │   ├── ProductListItemDto.cs
│   │   ├── ProductQueryParams.cs
│   │   ├── ProductSaleItemsResponseDto.cs
│   │   ├── SaleItemDto.cs
│   │   ├── UpdateProductRequest.cs
│   │   └── UpdateProductStatusRequest.cs
│   └── RoleDto.cs
│
├── Interfaces/                         Port definitions (implemented by Infrastructure)
│   ├── Repositories/
│   │   ├── IBusinessLocationRepository.cs
│   │   ├── IBusinessTypeRepository.cs
│   │   ├── IHireRepository.cs
│   │   ├── IImportRepository.cs
│   │   ├── IImportSchemaRepository.cs
│   │   ├── IProductRepository.cs
│   │   ├── IRoleRepository.cs
│   │   └── IUnitOfWork.cs              Transaction coordinator across multiple repositories
│   │
│   └── Services/
│       ├── IBusinessLocationService.cs
│       ├── IBusinessTypeService.cs
│       ├── ICloudinaryService.cs       Contract: upload/delete images on Cloudinary
│       ├── IHireService.cs
│       ├── IImageService.cs            Contract: image validation and resize
│       ├── IImportSchemaService.cs
│       ├── IImportService.cs
│       ├── IProductService.cs
│       └── IRoleService.cs
│
├── Mappers/                            AutoMapper profiles (Entity ↔ DTO mapping)
│   ├── HireProfile.cs
│   ├── ImportProfile.cs
│   ├── ImportSchemaProfile.cs
│   ├── LocationProfile.cs
│   └── ProductProfile.cs
│
├── Services/                           Concrete application service implementations
│   ├── BusinessLocationService.cs
│   ├── BusinessTypeService.cs
│   ├── HireService.cs
│   ├── ImageService.cs
│   ├── ImportSchemaService.cs
│   ├── ImportService.cs
│   ├── ProductService.cs
│   └── RoleService.cs
│
└── Specifications/
    └── Products/
        └── ProductSearchSpec.cs        Concrete specification: filter/sort/paginate products
```

**Package explanations:**

| Package | Description |
|---|---|
| `Common/Constants` | Centralises all i18n message key strings to avoid magic strings scattered across the codebase. |
| `Common/Exceptions` | Domain-specific exception types that are mapped to HTTP status codes by `GlobalExceptionMiddleware` in the API layer. |
| `Common/Interfaces` | Cross-cutting service contracts (JWT, messaging, payment) that don't belong to a single domain entity. |
| `Common/Models` | Shared value objects, config models, and response envelopes used across multiple features. |
| `Common/Specifications` | Base implementation of the Specification pattern, enabling query logic to be encapsulated and reused without coupling services to EF Core. |
| `DTOs` | Flat, serialisable objects that define the exact shape of HTTP request bodies and response payloads. Separated from domain entities to allow the API contract to evolve independently. |
| `Interfaces/Repositories` | Abstractions for data access. The `IUnitOfWork` interface groups repositories into a single transaction boundary. |
| `Interfaces/Services` | Abstractions for infrastructure services (Cloudinary, image processing). Defined here so application services can depend on them without knowledge of the concrete SDKs. |
| `Mappers` | AutoMapper profile classes that declare bidirectional mappings between domain entities and DTOs. |
| `Services` | Concrete implementations of the business use cases. Each service class is responsible for one domain aggregate (Product, Location, Import, etc.). |
| `Specifications` | Concrete query specifications for complex filtered queries (e.g., product search with keyword, category filter, pagination). |

---

## 4. BizFlow.Infrastructure

**Responsibility:** The outermost implementation layer. Adapts the contracts defined in `BizFlow.Application` to concrete technology implementations — Entity Framework Core, MySQL, Cloudinary SDK, JWT, etc.

```
BizFlow.Infrastructure
├── InfrastructureModule.cs             AutoFac DI registration for all infrastructure components
│
├── DataContext/
│   ├── BizFlowDbContext.cs             EF Core DbContext: DbSet declarations + SaveChanges
│   └── BizFlowDbContext.Custom.cs      Partial class: Fluent API entity configurations
│
├── Jobs/
│   └── ImageCleanupJob.cs              Hangfire background job: removes orphaned Cloudinary images
│
├── Repositories/                       EF Core implementations of Application repository interfaces
│   ├── BusinessLocationRepository.cs
│   ├── BusinessTypeRepository.cs
│   ├── HireRepository.cs
│   ├── ImportRepository.cs
│   ├── ImportSchemaRepository.cs
│   ├── ProductRepository.cs
│   ├── RoleRepository.cs
│   └── UnitOfWork.cs                   Coordinates SaveChangesAsync across all repositories
│
├── Services/                           Concrete implementations of external service interfaces
│   ├── CloudinaryService.cs            Cloudinary SDK: upload image, delete by public_id, list
│   ├── JwtService.cs                   System.IdentityModel: generate / validate JWT tokens
│   └── MessageService.cs               File-based i18n: loads Messages.vi.json / Messages.en.json
│
└── Specifications/
    └── SpecificationEvaluator.cs       Translates ISpecification into EF Core LINQ/IQueryable
```

**Package explanations:**

| Package | Description |
|---|---|
| `DataContext` | The EF Core database context. Split into two partial classes — one for `DbSet` declarations and one for Fluent API configuration — to keep the file manageable as the entity count grows. |
| `Jobs` | Hangfire background job classes. Jobs are scheduled in `Program.cs` and executed by the Hangfire server running inside the same API process. Currently handles periodic cleanup of images that were uploaded but whose associated records were later deleted. |
| `Repositories` | Each repository class wraps a specific domain aggregate (Product, Import, etc.) and provides typed query methods using EF Core. The pattern prevents raw LINQ from leaking into the application layer. |
| `Services` | Concrete adapters for external SDK calls. `CloudinaryService` is registered as a singleton (one SDK client reused across requests). `JwtService` generates and validates access/refresh tokens. `MessageService` loads JSON language files once at startup and resolves message keys based on the `Accept-Language` request header. |
| `Specifications` | `SpecificationEvaluator` is an internal query builder that translates an `ISpecification<T>` object (filter, includes, ordering, pagination) into an EF Core `IQueryable<T>`, keeping all ORM concerns in this layer. |

---

## 5. BizFlow.Api

**Responsibility:** The presentation layer. Handles HTTP request/response, authentication filters, routing, middleware, and Swagger documentation. Has no business logic.

```
BizFlow.Api
├── Program.cs                          Application entry point: service registration + pipeline setup
│
├── Common/
│   ├── Controllers/
│   │   ├── BaseApiController.cs        Abstract base controller: shared route prefix, auth filter
│   │   └── PaginatedApiController.cs   Extension of BaseApiController: adds pagination helpers
│   │
│   ├── Middleware/
│   │   ├── GlobalExceptionMiddleware.cs  Catches all unhandled exceptions → maps to HTTP status codes
│   │   └── JwtAuthenticationMiddleware.cs  Validates Bearer token on every secured request
│   │
│   ├── ModelBinders/
│   │   └── FormDataJsonModelBinder.cs  Custom binder: deserializes JSON strings embedded in multipart/form-data
│   │
│   └── Resources/
│       ├── Messages.vi.json            Vietnamese i18n strings
│       └── Messages.en.json            English i18n strings
│
└── Controllers/
    ├── BusinessType/
    │   └── BusinessTypeController.cs
    ├── Hire/
    │   └── HireController.cs
    ├── Import/
    │   └── ImportController.cs
    ├── ImportSchema/
    │   └── ImportSchemaController.cs
    ├── Location/
    │   └── BusinessLocationController.cs
    ├── Product/
    │   └── ProductController.cs
    ├── RoleController.cs
    └── TestController.cs
```

**Package explanations:**

| Package | Description |
|---|---|
| `Common/Controllers` | Abstract base controller classes that provide shared route prefixes (`/api/`), authorization attributes, and helper methods (e.g., extracting the current user ID from JWT claims). All concrete controllers inherit from these. |
| `Common/Middleware` | Middleware components inserted into the ASP.NET Core pipeline. `GlobalExceptionMiddleware` catches every unhandled exception and maps it to the appropriate HTTP response (400/401/403/404/409/500) using the custom exception types from `BizFlow.Application`. `JwtAuthenticationMiddleware` inspects the `Authorization` header and short-circuits requests with invalid or expired tokens. |
| `Common/ModelBinders` | A custom `IModelBinder` that allows request bodies sent as `multipart/form-data` (required for file uploads) to carry complex JSON sub-objects as string fields — bridging file upload and structured data in a single request. |
| `Common/Resources` | JSON files for internationalisation. Loaded once at startup by `MessageService`. Separating strings into files makes adding a new language trivial. |
| `Controllers` | One controller class per domain module. Each controller is thin: it validates the HTTP request, delegates to the appropriate application service, and wraps the result in the `ApiResponse` envelope. Business logic is never placed here. |

---

## 6. Dependency Graph Summary

```
BizFlow.Api
   ├──► BizFlow.Application
   │         ├──► BizFlow.Domain
   │         └──► (defines interfaces only — no concrete deps)
   └──► BizFlow.Infrastructure
             ├──► BizFlow.Application  (implements interfaces)
             └──► BizFlow.Domain       (uses entities with EF Core)
```

`BizFlow.Domain` has **no dependencies** on any other project — it is the stable core of the system. All other layers reference inward toward it, never outward. This means domain logic can be unit tested without any database, HTTP server, or external SDK being present.
