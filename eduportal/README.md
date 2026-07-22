# EduPortal South Sudan

Flask-based education portal for students, parents, teachers, school admins, NGO officers, and platform admins.

## Top-Level Structure

The project is organized into three core areas:

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

## Frontend Organization

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

## Sessions

Login, registration, email verification, and Google Sign-In all return an access token (2h) plus a refresh token (30 days, single-use, rotated on every refresh). The frontend calls `POST /api/refresh` automatically when a request 401s, and `POST /api/logout` revokes the current refresh token. Changing a password revokes every other session for that account.

## Notifications

- `GET /api/notifications` returns persisted, per-user notifications (application status changes, scholarship deadline reminders) merged with a live feed of recent announcements.
- `POST /api/notifications/<id>/read` and `POST /api/notifications/read-all` mark persisted notifications read.
- `GET /api/notifications/stream` is a Server-Sent Events endpoint — the bell updates instantly when a notification is created, no polling. Pass the access token as `?token=` (browsers can't set custom headers on `EventSource`).
- This uses an in-process pub/sub, so it only works as-is behind a single worker process. Running multiple Gunicorn workers would need a shared broker (e.g. Redis) for the SSE fan-out to reach every connection.

## Web Push

Enables browser notifications when EduPortal isn't open in a tab. Generate a VAPID keypair once:

```powershell
python -c "from py_vapid import Vapid02; v=Vapid02(); v.generate_keys()"
```

Set `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_CLAIMS_SUB` in `.env`. Users opt in from Settings → Push Notifications; subscriptions are stored per-browser and pushed to whenever a notification is created.

## Google Sign-In

1. Create an OAuth client at the [Google Cloud Console](https://console.cloud.google.com/apis/credentials) (Web application type; add your site as an Authorized JavaScript origin).
2. Set `GOOGLE_CLIENT_ID` in `.env`.
3. The "Continue with Google" button appears automatically on the login/register pages once that variable is set — it's hidden otherwise.

First-time Google sign-in auto-creates a verified account (role `student`); an existing account with the same email is logged in directly.

## Background Jobs

APScheduler runs in-process, starting alongside the dev server (`python backend/app.py`). It currently checks every 6 hours (and once at startup) for scholarship deadlines 3 and 1 days out, notifying every applicant once per milestone by in-app notification + email. It does not run under `flask run` or a WSGI server that only imports the app — start it explicitly there if you deploy that way.

## Main URLs

- `http://127.0.0.1:5000/` login
- `http://127.0.0.1:5000/dashboard` dashboard
