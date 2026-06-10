# PassFlow - Wallet Pass Management Platform

PassFlow is a Django-based platform that allows merchants in the European Union to create, manage, and analyze Google Wallet and Apple Wallet passes.

---

## Technical Stack
* **Backend**: Django 6.0, Django REST Framework (DRF)
* **Frontend**: HTML5, Tailwind CSS, Vanilla JS
* **Database**: PostgreSQL (GCP Cloud SQL)
* **Infrastructure**: Google Cloud Platform (Region: `europe-north1`)
* **CI/CD**: GitHub Actions to Google Cloud Run

---

## Local Development Setup

Follow these steps to run the application locally:

### 1. Initialize Virtual Environment
Ensure Python 3.11+ is installed.
```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
source .venv/bin/activate    # macOS/Linux
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Variables
Create a `.env` file in the root directory (one has been auto-generated for you):
```ini
DEBUG=True
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=127.0.0.1,localhost
DATABASE_URL=sqlite:///db.sqlite3
```

### 4. Database Migrations
Run migrations to set up the local database:
```bash
python manage.py migrate
```

### 5. Create Superuser
Create an admin account to access the Django admin portal (`/admin/`):
```bash
python manage.py createsuperuser
```
*(A default superuser `admin` with password `adminpass` has already been created for you in your local DB).*

### 6. Start the Server
```bash
python manage.py runserver
```
Visit the landing page at `http://127.0.0.1:8000/`.

---

## Google Cloud Infrastructure

The following GCP resources have been automatically created and configured in the **`europe-north1` (Finland)** region:

1. **Project ID**: `wallet-devcertifit`
2. **Billing Linked**: Active billing account `015D03-8D9953-EE64AE`.
3. **Cloud SQL Instance**: PostgreSQL 15 database instance (`wallet-db`).
   - Connection Name: `wallet-devcertifit:europe-north1:wallet-db`
   - Database Name: `wallet_db`
   - Database User: `wallet_user`
4. **Artifact Registry**: Docker container repository (`wallet-app`).
5. **Cloud Storage**: Asset storage bucket (`gs://wallet-assets-devcertifit`).


---

## CI/CD Pipeline

The GitHub Actions configuration is stored under `.github/workflows/deploy.yml`. 

To configure deployment:
1. Create a service account in your Google Cloud console with roles for Cloud Run Developer, Artifact Registry Writer, and Storage Admin.
2. Generate a JSON key for the service account.
3. In your GitHub repository settings, add the JSON key as a repository secret named `GCP_SA_KEY`.
4. Push code to the `main` branch to trigger build and deployment to Cloud Run automatically.
