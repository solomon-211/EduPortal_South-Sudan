# EduPortal South Sudan

Flask-based education portal for students, parents, teachers, school admins, NGO officers, and platform admins.

## Top-Level Structure

- `backend/` — Flask app, database access, auth, notifications, background jobs
- `alembic/` — database migrations (source of truth for the schema)
- `frontend/` — HTML templates, CSS, JavaScript, and uploaded assets

## Current Directory Structure

```text
eduportal/
├─ backend/                    (flat — no subdirectories)
│  ├─ app.py                   Flask app, all routes
│  ├─ settings.py               env-driven config, paths
│  ├─ db_connection.py / db_queries.py / db_schema.py
│  ├─ jwt_helpers.py            access/refresh tokens, role checks
│  ├─ google_oauth.py           Google ID token verification
│  ├─ scheduler.py              APScheduler background jobs
│  ├─ notify_email.py / notify_sms.py / notify_push.py
│  ├─ notify_store.py           persisted notifications + SSE pub/sub
│  ├─ storage.py                picks local disk or S3 based on env vars
│  ├─ storage_local.py / storage_s3.py
│  └─ test_regression.py
├─ alembic/
│  ├─ env.py
│  └─ versions/                (one file per migration, applied in order)
├─ frontend/
│  ├─ html/                    (one template per page, plus html/marketing/)
│  ├─ css/
│  │  ├─ marketing.css
│  │  └─ html/                 (one self-contained stylesheet per page)
│  ├─ javascript/
│  │  ├─ app.js                (loader that injects app/main.js)
│  │  ├─ sidebar.js
│  │  ├─ sw.js                 (service worker for Web Push)
│  │  ├─ app/                  (main.js + per-feature modules)
│  │  └─ navigation/sidebar-main.js
│  └─ assets/
│     ├─ avatars/
│     └─ materials/
├─ requirements.txt
└─ README.md
```

## Frontend Organization

- `frontend/html/`: page templates rendered by Flask
- `frontend/css/`: one self-contained stylesheet per page under `css/html/`, plus `marketing.css` for the public marketing pages — no shared base stylesheet, each page's CSS is complete on its own
- `frontend/javascript/`: entry scripts and modular client logic
- `frontend/assets/`: uploaded files (avatars/materials)

Examples:
- `frontend/html/login.html` -> `frontend/css/html/login.css`
- `frontend/html/dashboard.html` -> `frontend/css/html/dashboard.css`

## URL Compatibility

Static assets are served from `/static/...`:

- `/static/html/<page>.css` -> `frontend/css/html/<page>.css`
- `/static/app.js` -> `frontend/javascript/app.js`
- `/static/sidebar.js` -> `frontend/javascript/sidebar.js`
- `/static/app/main.js` -> `frontend/javascript/app/main.js`
- `/static/navigation/sidebar-main.js` -> `frontend/javascript/navigation/sidebar-main.js`
- `/static/avatars/...` -> `frontend/assets/avatars/...`
- `/static/materials/...` -> `frontend/assets/materials/...`
- `/sw.js` is served from the root path (not `/static/`) so its service worker scope covers the whole site.

## Run Locally

```powershell
cd "c:\Users\HP\OneDrive\Desktop\EduPortal South Sudan\EduPortal_South-Sudan\eduportal"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python backend\app.py
```

## Database Mode

PostgreSQL is the production database. If `DATABASE_URL` / `POSTGRES_*` aren't set, `config/settings.py` falls back to an in-memory or file-based SQLite database — the test suite relies on this, and it's fine for a quick look around, but not for real use (background jobs, refresh-token storage, and file uploads all expect a real database to persist across restarts).

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

1. Create the database and a role for the app, e.g. in `psql` as a superuser:

   ```sql
   CREATE ROLE eduportal_app LOGIN PASSWORD 'CHANGE_ME';
   CREATE DATABASE eduportal OWNER eduportal_app;
   ```

2. Copy `.env.example` to `.env` and fill in `POSTGRES_PASSWORD` (and any other values you're changing).
3. Start the backend — `python backend\app.py` runs Alembic migrations against an empty database automatically on first boot, then seeds it with demo schools/scholarships/announcements.

```powershell
cd "c:\Users\HP\OneDrive\Desktop\EduPortal South Sudan\EduPortal_South-Sudan\eduportal"
Copy-Item .env.example .env
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

If PostgreSQL isn't reachable, `config/settings.py` falls back to a local SQLite file — fine for a quick look around, but the test suite is the only thing that relies on this in practice.

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
