# Project Context: Wallet Pass Management Platform

This file serves as the permanent context and source of truth for the project. It details the architecture, design choices, and business logic of the Wallet Pass platform.

---

## 1. Project Overview & Business Logic

The platform enables merchants to create, manage, and distribute digital passes (loyalty cards, gift cards, memberships) via Apple Wallet and Google Wallet. Payment/transaction passes are excluded.

### Core Business Logic
* **Target Audience**: Merchants of all sizes (from SMBs to large enterprises).
* **Onboarding & Credentials**:
  - **Shared Credential Model (Option A)**: Passes are generated and signed using *our* platform's Apple Developer Account and Google Pay Console Issuer ID. This eliminates onboarding friction for merchants who do not have developer accounts. Passes are white-labeled.
* **Pass Verification / Redemption**:
  - **SMB Scanner**: A web-based QR scanner is provided within the merchant's mobile dashboard (using the device's camera) to scan passes, view customer details, and update points or redeem value.
  - **Enterprise API Integration**: A REST API endpoint is exposed for larger merchants to connect their physical barcode/NFC scanners or ERP/POS systems.
* **Subscription & Analytics**:
  - Intermediate metrics tracking: active installs, uninstall rates (via APNs feedback), and redemption/update counts over time.
* **Localization**:
  - Initial launch: **English**.
  - Future-proofed: Django's translation engine (`gettext`) is configured from day one to support multiple languages in the future.

---

## 2. Technical Stack & Architecture

### Backend
* **Framework**: Django (Python) + Django REST Framework (DRF) for APIs.
* **Language Integration**: Standard Django i18n routing and localization markers (`_()`).
* **Database**: PostgreSQL on Google Cloud SQL (starting with the smallest instance `db-f1-micro` to minimize costs).
* **Asynchronous Jobs**: GCP Cloud Tasks. It runs serverless and routes asynchronous events (APNs pushes, Google Wallet API updates) to our Cloud Run service via HTTPS endpoints. Zero idle running costs.

### Frontend
* **Design System**: Tailwind CSS (light installation: standalone CLI or CDN for development, keeping node dependency tree small).
* **Interactivity**: Vanilla JavaScript for DOM manipulations, modals, and the QR scanner.
* **Admin Dashboard**: Django Admin & Custom Django Templates styled with Tailwind.

### Google Cloud Infrastructure (Region: `europe-north1`)
* **Compute**: Google Cloud Run (containerized Django application).
* **Database**: Cloud SQL (PostgreSQL, `db-f1-micro`).
  - Instance Name: `wallet-db`
  - Connection Name: `wallet-devcertifit:europe-north1:wallet-db`
  - Database Name: `wallet_db`
  - Database User: `wallet_user`
* **Async Tasks**: Google Cloud Tasks.
* **Storage**: Google Cloud Storage (for static files, media, and certificates, bucket: `gs://wallet-assets-devcertifit`).
* **Secrets**: Google Secret Manager (for Apple certificates, private keys, and API tokens).


---

## 3. CI/CD Pipeline

* **Repository**: GitHub.
* **Workflow**:
  1. **Test & Build**: GitHub Actions runs automated tests and builds a Docker image.
  2. **Push**: Images are pushed to Google Artifact Registry.
  3. **Deploy**: Automatically deploys to Google Cloud Run in the `europe-north1` region, and applies database migrations.
