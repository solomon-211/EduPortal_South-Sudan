# EduPortal South Sudan

A Flask-based education portal connecting students, parents, teachers, school
administrators, NGOs, and platform administrators across South Sudan: a
verified school directory, admission requirements, study materials, national
and local announcements, and scholarship listings with an application
pipeline — all moderated through a two-tier review system before anything
goes public.

## Who uses it

| Role | Can do |
|---|---|
| `student` | Browse schools/materials/announcements, apply for scholarships, bookmark items, track applications |
| `parent` | Same browsing access, plus a linked child's school/grade on their profile |
| `teacher` | Everything a student can, plus upload study materials and post announcements for their school |
| `school_admin` | Manage one school's profile, admission requirements, and materials; approve applications |
| `ngo_officer` | Post and manage scholarships for their NGO |
| `org_publisher` | Post announcements on behalf of a verified organization (ministry, university, exam body) |
| `admin` | Approve/reject all submitted content, manage users and organizations, view analytics and the audit log |

## Features

- **Authentication** — email/phone + password (bcrypt) or Google Sign-In, JWT access tokens (2h) with rotating single-use refresh tokens (30 days)
- **Email verification** — required before login for email-registered accounts; Google Sign-In auto-verifies since Google already proved ownership
- **Password reset** — time-limited, single-use reset codes; no account-enumeration on the request endpoint
- **Role-based authorization** — route-level role checks plus a `role_permissions` table for finer-grained actions
- **In-app notifications** — persisted per-user, with a live unread count
- **Real-time updates** — Server-Sent Events push new notifications to open tabs instantly, no polling
- **Web Push** — VAPID-based browser push for users who aren't actively on the site
- **Email/SMS delivery** — SMTP for email, Africa's Talking for SMS, both optional and independently configurable
- **Background jobs** — APScheduler checks scholarship deadlines and notifies applicants at 3 and 1 days out
- **File storage** — local disk by default, or S3/Supabase Storage when configured
- **Two-tier moderation** — schools, materials, announcements, and scholarships all require admin approval before they're public
- **Audit log** — every admin action (approvals, suspensions, role changes) is recorded

## Tech stack

Flask 3, SQLAlchemy Core (raw SQL, not the ORM) over MySQL or SQLite, Alembic
migrations, PyJWT, bcrypt, Flask-Limiter, APScheduler, pywebpush, google-auth.
No frontend framework — server-rendered HTML with hand-written CSS and vanilla
JavaScript per page.

## Project structure

```text
eduportal/
├─ backend/                 Flask app — flat, no subdirectories
│  ├─ app.py                 all routes
│  ├─ settings.py            env-driven config, paths
│  ├─ db_connection.py       SQLAlchemy engine
│  ├─ db_queries.py          query/execute helpers (? placeholders, lastrowid)
│  ├─ db_schema.py           runs migrations, seeds a fresh database
│  ├─ jwt_helpers.py         access/refresh tokens, role decorators
│  ├─ google_oauth.py        Google ID token verification
│  ├─ scheduler.py           APScheduler background jobs
│  ├─ notify_email.py / notify_sms.py / notify_push.py
│  ├─ notify_store.py        persisted notifications + SSE pub/sub
│  ├─ storage.py             picks local disk or S3 based on env vars
│  ├─ storage_local.py / storage_s3.py
│  └─ test_regression.py     pytest suite (runs on an in-memory SQLite db)
├─ alembic/
│  └─ versions/               one file per migration, applied in order — the
│                              live source of truth for the schema
├─ database/
│  ├─ schema.sql              SRS-aligned reference schema (documentation —
│  │                          the live app uses the Alembic schema above,
│  │                          which uses different table/column names)
├─ frontend/
│  ├─ html/                   one template per page, plus html/marketing/
│  ├─ css/html/                one self-contained stylesheet per page
│  ├─ javascript/
│  │  ├─ app/main.js          main client logic + per-feature modules
│  │  ├─ navigation/sidebar-main.js
│  │  └─ sw.js                service worker for Web Push
│  └─ assets/avatars/ , assets/materials/   uploaded files
├─ requirements.txt
└─ README.md
```

## Getting started

```powershell
cd "c:\Users\HP\OneDrive\Desktop\EduPortal South Sudan\EduPortal_South-Sudan\eduportal"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python backend\app.py
```

On first run, `python backend\app.py` applies every Alembic migration and, if
the database is empty, seeds it with demo schools, materials, announcements,
NGOs, scholarships, and one login per role (see **Demo accounts** below). Open
`http://127.0.0.1:5000/`.

## Environment variables

All of these live in `.env` — copy `.env.example` to start. Only
`JWT_SECRET_KEY` is required for the app to boot; everything else has a
working default or degrades gracefully when unset (Google Sign-In hides its
button, push notifications stay off, email/SMS log to console instead of
sending).

| Variable | Purpose |
|---|---|
| `DATABASE_URL` or `MYSQL_HOST`/`MYSQL_PORT`/`MYSQL_USER`/`MYSQL_PASSWORD`/`MYSQL_DATABASE` | Database connection — see **Database** below |
| `JWT_SECRET_KEY` | Signs access tokens — set a real value outside development |
| `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASS`/`SMTP_FROM` | Outbound email (verification, password reset, notifications) |
| `AT_API_KEY`/`AT_SENDER_ID` | Africa's Talking SMS |
| `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY`/`VAPID_CLAIMS_SUB` | Web Push keypair |
| `GOOGLE_CLIENT_ID` | Google Sign-In — see below |
| `S3_BUCKET`/`S3_REGION`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`/`S3_ENDPOINT_URL`/`S3_PUBLIC_BASE_URL` | Optional S3-compatible file storage; local disk is used when `S3_BUCKET` is blank |

## Database

MySQL is the production database. SQLite is the supported local-development
and test fallback — same schema, same code path, just a different engine (set
via `DATABASE_URL`). Both are driven by the same Alembic migrations in
`alembic/versions/`, written to run correctly on either.

### MySQL (production)

Set either `DATABASE_URL` or the individual variables below.

- `DATABASE_URL` (example: `mysql+pymysql://user:pass@localhost:3306/eduportal?charset=utf8mb4`)

or `MYSQL_HOST` (default `localhost`), `MYSQL_PORT` (default `3306`),
`MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`.

Quick setup — create the database and a scoped user, e.g. in the `mysql`
client as root:

```sql
CREATE DATABASE eduportal CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'eduportal_app'@'localhost' IDENTIFIED BY 'CHANGE_ME';
GRANT ALL PRIVILEGES ON eduportal.* TO 'eduportal_app'@'localhost';
FLUSH PRIVILEGES;
```

Then fill in `MYSQL_PASSWORD` in `.env` and start the backend as above.
Verify with:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/healthz
```

Expected: `status: ok`, `database.engine: mysql`, `database.connected: true`.

### SQLite (local development / testing)

No server to install — set `DATABASE_URL=sqlite:///eduportal.db` in `.env`
(or `sqlite:///:memory:` for an ephemeral database) and start the backend the
same way. This is what `backend/test_regression.py` uses automatically.
`database.engine` in `/healthz` will report `sqlite` in this mode.

### Reference schema

`database/schema.sql` documents the data model exactly as specified in the
project's SRS — MySQL DDL for all 9 core entities with their intended
column names and types. It's kept as a design reference; the live schema in
`alembic/versions/` evolved somewhat differently during development (e.g.
`users.name` instead of `full_name`) and is what `app.py` actually queries.

## Demo accounts

The seed data (loaded automatically into an empty database) includes one
working login per role, all sharing the password `Demo1234!`:

| Role | Email |
|---|---|
| Student | `student@eduportal.ss` |
| Parent | `parent@eduportal.ss` |
| Teacher | `teacher@eduportal.ss` |
| School admin | `schooladmin@eduportal.ss` (manages Juba Day Secondary School) |
| NGO officer | `contact@futuress.org` (posts scholarships for Future South Sudan Trust) |
| Org publisher | `orgpublisher@eduportal.ss` (posts for the Ministry of General Education) |
| Platform admin | `admin@eduportal.ss` / `Admin1234!` |

Plus 10 schools across all 10 states, 4 study materials, 3 announcements, 2
NGOs, and 3 scholarships — enough to exercise every list, filter, and detail
page without registering fresh accounts each time.

## Testing

```powershell
pytest backend\test_regression.py -v
```

Runs against an isolated in-memory SQLite database (independent of whatever
`DATABASE_URL` is set to), so it's safe to run against a MySQL-configured
`.env` without touching real data.

## Sessions

Login, registration, email verification, and Google Sign-In all return an
access token (2h) plus a refresh token (30 days, single-use, rotated on every
refresh). The frontend calls `POST /api/refresh` automatically when a request
401s, and `POST /api/logout` revokes the current refresh token. Changing a
password revokes every other session for that account.

## Notifications

- `GET /api/notifications` returns persisted, per-user notifications (application status changes, scholarship deadline reminders) merged with a live feed of recent announcements.
- `POST /api/notifications/<id>/read` and `POST /api/notifications/read-all` mark persisted notifications read.
- `GET /api/notifications/stream` is a Server-Sent Events endpoint — the bell updates instantly when a notification is created, no polling. Pass the access token as `?token=` (browsers can't set custom headers on `EventSource`).
- This uses an in-process pub/sub, so it only works as-is behind a single worker process. Running multiple Gunicorn workers would need a shared broker (e.g. Redis) for the SSE fan-out to reach every connection.

## Web Push

Enables browser notifications when EduPortal isn't open in a tab. Generate a
VAPID keypair once:

```powershell
python -c "from py_vapid import Vapid02; v=Vapid02(); v.generate_keys()"
```

Set `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_CLAIMS_SUB` in `.env`.
Users opt in from Settings → Push Notifications; subscriptions are stored
per-browser and pushed to whenever a notification is created.

## Google Sign-In

1. Create an OAuth client at the [Google Cloud Console](https://console.cloud.google.com/apis/credentials) (Web application type; add your site as an Authorized JavaScript origin).
2. Set `GOOGLE_CLIENT_ID` in `.env`.
3. The "Continue with Google" button appears automatically on the login/register pages once that variable is set — it's hidden otherwise.

First-time Google sign-in auto-creates a verified account (role `student`);
an existing account with the same email is logged in directly.

## Background jobs

APScheduler runs in-process, starting alongside the dev server (`python
backend/app.py`). It currently checks every 6 hours (and once at startup) for
scholarship deadlines 3 and 1 days out, notifying every applicant once per
milestone by in-app notification + email. It does not run under `flask run`
or a WSGI server that only imports the app — start it explicitly there if you
deploy that way.

## Main URLs

- `/` — home / login
- `/register` — two-step registration
- `/dashboard` — role-aware dashboard
- `/directory` — school directory
- `/materials` — study materials
- `/opportunities` — scholarships
- `/announcements` — announcements feed
- `/organizations` — verified organization directory
- `/admin` — moderation queue, users, analytics, audit log (admin only)
- `/school-dashboard`, `/ngo-dashboard`, `/org-dashboard` — role-specific management views
