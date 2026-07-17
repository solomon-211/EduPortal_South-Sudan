# EduPortal South Sudan

Flask-based education portal for students, parents, teachers, school admins, NGO officers, and platform admins.

## Required Top-Level Structure

The project is now organized into the three core areas you requested:

- `backend/`
- `database/`
- `frontend/`

## Current Directory Structure

```text
eduportal/
├─ backend/
│  └─ app.py
├─ database/
│  └─ (MySQL schema/migration resources)
├─ frontend/
│  ├─ html/
│  │  ├─ login.html
│  │  ├─ register.html
│  │  ├─ dashboard.html
│  │  ├─ admin.html
│  │  ├─ school-dashboard.html
│  │  ├─ ngo-dashboard.html
│  │  ├─ directory.html
│  │  ├─ materials.html
│  │  ├─ opportunities.html
│  │  ├─ announcements.html
│  │  ├─ my-applications.html
│  │  ├─ bookmarks.html
│  │  ├─ profile.html
│  │  ├─ settings.html
│  │  ├─ school.html
│  │  ├─ forgot-password.html
│  │  ├─ accept-invite.html
│  │  ├─ terms.html
│  │  ├─ privacy.html
│  │  └─ support.html
│  ├─ css/
│  │  ├─ styles.css
│  │  ├─ html/
│  │  │  ├─ login.css
│  │  │  ├─ register.css
│  │  │  ├─ dashboard.css
│  │  │  └─ ... (one CSS file per HTML page)
│  │  ├─ layout/
│  │  │  ├─ shell-layout.css
│  │  │  └─ mobile-sidebar.css
│  │  ├─ auth/
│  │  │  └─ register.css
│  │  ├─ pages/
│  │  │  ├─ dashboard.css
│  │  │  ├─ admin.css
│  │  │  └─ school-dashboard.css
│  │  └─ shared/
│  │     └─ shell.css
│  ├─ javascript/
│  │  ├─ app.js
│  │  ├─ sidebar.js
│  │  ├─ app/
│  │  │  └─ main.js
│  │  └─ navigation/
│  │     └─ sidebar-main.js
│  └─ assets/
│     ├─ avatars/
│     └─ materials/
├─ eduportal.conf
├─ requirements.txt
└─ README.md
```

## Frontend Organization (Requested)

Frontend is organized by type:

- `frontend/html/`: all HTML files
- `frontend/css/`: all CSS files
- `frontend/javascript/`: all JavaScript files

Page-based CSS naming is now in place for easy checking:

- each HTML file has a matching CSS file under `frontend/css/html/`
- each page CSS is self-contained and does not import from `styles.css`
- examples:
  - `frontend/html/login.html` -> `frontend/css/html/login.css`
  - `frontend/html/dashboard.html` -> `frontend/css/html/dashboard.css`
  - `frontend/html/settings.html` -> `frontend/css/html/settings.css`

Static binary uploads are kept in `frontend/assets/`:

- `frontend/assets/avatars/`
- `frontend/assets/materials/`

## What Each Main Folder Does

### backend/

- Flask API and web server logic (`app.py`)
- Authentication/authorization
- Database migrations and CRUD operations
- Static URL compatibility routing (`/static/...`)

### database/

- MySQL schema and migration resources.
- Runtime data is stored in your configured MySQL database.

### frontend/

- `html/`: page templates rendered by Flask
- `css/`: global, shared, and page-specific styles
- `javascript/`: entry scripts and modular client logic
- `assets/`: uploaded files (avatars/materials)

## URL Compatibility

Existing page links still work with `/static/...` URLs.

Examples:

- `/static/styles.css` -> `frontend/css/styles.css`
- `/static/html/<page>.css` -> `frontend/css/html/<page>.css`
- `/static/app.js` -> `frontend/javascript/app.js`
- `/static/sidebar.js` -> `frontend/javascript/sidebar.js`
- `/static/layout/shell-layout.css` -> `frontend/css/layout/shell-layout.css`
- `/static/auth/register.css` -> `frontend/css/auth/register.css`
- `/static/app/main.js` -> `frontend/javascript/app/main.js`
- `/static/navigation/sidebar-main.js` -> `frontend/javascript/navigation/sidebar-main.js`
- `/static/avatars/...` -> `frontend/assets/avatars/...`
- `/static/materials/...` -> `frontend/assets/materials/...`

## Run Locally

```powershell
cd "c:\Users\HP\OneDrive\Desktop\EduPortal South Sudan\EduPortal_South-Sudan\eduportal"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python backend\app.py
```

## Database Mode

This project now supports PostgreSQL as the primary production database.

Backend selection order is:

1. PostgreSQL (when configured)
2. MySQL (legacy compatibility)
3. SQLite fallback (`database/eduportal.sqlite3`) for local development

### PostgreSQL (recommended)

Set either `DATABASE_URL` or the individual PostgreSQL variables below before starting the backend.

- `DATABASE_URL` (example: `postgresql://user:pass@localhost:5432/eduportal`)

or

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_DATABASE`
- `POSTGRES_SSLMODE` (optional, default: `prefer`)

Quick setup:

1. Run `database/postgres_setup.sql` in `psql` as a superuser.
2. Copy `.env.example` to `.env`.
3. Update `.env` values (especially `POSTGRES_PASSWORD`).
4. Start the backend with `python backend\app.py`.

Example:

```powershell
cd "c:\Users\HP\OneDrive\Desktop\EduPortal South Sudan\EduPortal_South-Sudan\eduportal"
Copy-Item .env.example .env

# Run SQL bootstrap as postgres superuser
psql -U postgres -f .\database\postgres_setup.sql

python .\backend\app.py
```

Verify active DB engine and connectivity:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/healthz
```

Expected shape:

- `status: ok`
- `database.engine: postgres`
- `database.connected: true`

### MySQL (legacy)

If PostgreSQL is not configured, MySQL is used when these are set:

- `MYSQL_HOST`
- `MYSQL_PORT`
- `MYSQL_USER`
- `MYSQL_PASSWORD`
- `MYSQL_DATABASE`

## Main URLs

- `http://127.0.0.1:5000/` login
- `http://127.0.0.1:5000/dashboard` dashboard
