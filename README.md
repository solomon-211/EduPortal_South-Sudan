# EduPortal South Sudan

A Flask-based education portal connecting students, parents, teachers, school
administrators, NGOs, and platform administrators across South Sudan: a
verified school directory, admission requirements, study materials, national
and local announcements, and scholarship listings with an application
pipeline — all moderated through a two-tier review system before anything
goes public.

## Contents

- [Who uses it](#who-uses-it)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Project structure](#project-structure)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [Database](#database)
- [Demo accounts](#demo-accounts)
- [Testing](#testing)
- [Sessions](#sessions)
- [Notifications](#notifications)
- [Web Push](#web-push)
- [Google Sign-In](#google-sign-in)
- [Background jobs](#background-jobs)
- [Material thumbnails](#material-thumbnails)
- [Backups](#backups)
- [Main URLs](#main-urls)
- [REST API reference](#rest-api-reference)
- [Security](#security)
- [Accessibility](#accessibility)
- [Deployment](#deployment)

## Who uses it

| Role | Can do |
| --- | --- |
| `student` | Browse schools/materials/announcements, apply for scholarships, bookmark items, track applications |
| `parent` | Same browsing access, plus a linked child's school/grade on their profile |
| `teacher` | Everything a student can, plus upload study materials and post announcements for their school |
| `school_admin` | Manage one school's profile, admission requirements, and materials; approve applications |
| `ngo_officer` | Post and manage scholarships (with optional poster image / promo video) for their NGO |
| `org_publisher` | Post announcements on behalf of a verified organization (ministry, university, exam body) |
| `admin` | Onboard schools, NGOs, and partner organizations; approve/reject everything submitted for moderation; manage users, roles, and assignments; view analytics and the audit log |

The platform admin runs the platform, not the content — they don't post
materials, announcements, or scholarships themselves (that's what
`school_admin`, `ngo_officer`, and `org_publisher` accounts are for). Their
sidebar reflects this: no Dashboard/Explore/Materials/Scholarships/
Announcements/bookmarks, just the Admin Panel and their own account. Every
other role's sidebar is filtered the same way — a role only ever sees the
nav items it's actually entitled to use, enforced client-side by
`sidebar-main.js` and, for every write, again server-side by `@require_role`.

## Features

- **Authentication** — email/phone + password (bcrypt) or Google Sign-In, JWT access tokens (2h) with rotating single-use refresh tokens (30 days)
- **Email verification** — required before login for email-registered accounts; Google Sign-In auto-verifies since Google already proved ownership
- **Password reset** — time-limited, single-use reset codes sent by email (falling back to SMS if email isn't configured); no account-enumeration on the request endpoint
- **Role-based authorization** — every write route is guarded server-side by `@require_role(...)`; the sidebar and dashboards mirror the same rules client-side, so a role never even sees a nav item or action it isn't entitled to use
- **Rate limiting** — Flask-Limiter caps login (10/min), registration (5/min), password-reset requests (5/min), resend-verification (3/min), Google auth (15/min), token refresh (30/min), and invite acceptance (10/min) per client, to blunt brute-force and enumeration attempts
- **Upload validation** — every uploaded file is checked by its actual content, not just its extension: PDFs are parsed with PyMuPDF, images and videos are signature-sniffed, before being accepted or stored
- **In-app notifications** — persisted per-user, with a live unread count
- **Real-time updates** — Server-Sent Events push new notifications to open tabs instantly, no polling
- **Web Push** — VAPID-based browser push for users who aren't actively on the site
- **Email/SMS delivery** — SMTP for email, Africa's Talking for SMS, both optional and independently configurable
- **Background jobs** — APScheduler checks scholarship deadlines and notifies applicants at 3 and 1 days out, and snapshots the database on a schedule (see [Backups](#backups))
- **File storage** — local disk by default, or S3/Supabase Storage when configured — covers avatars, school/NGO logos, admission-requirement documents, study materials, announcement attachments, and scholarship poster images/promo videos
- **Two-tier moderation** — schools, NGOs, partner organizations, materials, announcements, and scholarships all require admin approval before they're public
- **Analytics + CSV export** — users by role/state, top scholarships/materials/announcements, downloadable from the Admin Panel
- **Audit log** — every admin action (approvals, suspensions, role changes) is recorded, filterable by admin, action, and date range

## Tech stack

**Backend** — Flask 3, SQLAlchemy Core (raw SQL, not the ORM) over MySQL or
SQLite, Alembic migrations, PyJWT, bcrypt, Flask-Limiter, APScheduler,
pywebpush, google-auth, PyMuPDF (PDF parsing/thumbnails). Deliberately flat —
`backend/app.py` holds every route rather than being split into Flask
blueprints; see [Project structure](#project-structure).

**Frontend** — no framework, no build step. Server-rendered HTML, one
hand-written self-contained stylesheet per page, and vanilla JavaScript
(shared helpers on `window.EP`, one `initXxx()` function per page dispatched
by `bootApp()` in `main.js`). Set in Poppins (headings) and Open Sans
(body/UI) throughout. This is a deliberate choice for a low-bandwidth
environment: no bundler, no framework runtime to download, and each page's
CSS/JS ships as a small number of flat files a browser can cache directly.

**Testing** — pytest, running the full route surface against an in-memory
SQLite database (`backend/test_regression.py`).

## Project structure

```text
EduPortal_South-Sudan/
├─ backend/                 Flask app — flat, no subdirectories
│  ├─ app.py                 all routes
│  ├─ settings.py            env-driven config, paths
│  ├─ database.py            engine, query/execute helpers, migrations + first-run seeding
│  ├─ jwt_helpers.py         access/refresh tokens, role decorators
│  ├─ google_oauth.py        Google ID token verification
│  ├─ scheduler.py           APScheduler background jobs
│  ├─ notification.py        email, SMS, web push, persisted notifications + SSE pub/sub
│  ├─ storage.py             file storage — local disk or S3, picked by env vars
│  ├─ backup.py              database snapshot on a schedule
│  └─ test_regression.py     pytest suite (runs on an in-memory SQLite db)
├─ alembic/
│  └─ versions/               one file per migration, applied in order — the
│                              live source of truth for the schema
├─ database/
│  └─ schema.sql              SRS-aligned reference schema (documentation —
│                              the live app uses the Alembic schema above,
│                              which uses different table/column names)
├─ frontend/
│  ├─ html/                   one template per page
│  ├─ css/html/                one self-contained stylesheet per page
│  ├─ javascript/
│  │  ├─ app/main.js          main client logic + per-feature modules
│  │  ├─ app/shared-utils.js  helpers shared across pages, hung off window.EP
│  │  ├─ navigation/sidebar-main.js
│  │  └─ sw.js                service worker for Web Push
│  └─ assets/                 uploaded files — avatars/, materials/, logos/,
│                              requirements/, announcements/, scholarships/
│                              (gitignored per-folder; see .gitignore)
├─ requirements.txt
├─ .env.example
└─ README.md
```

## Getting started

Requires Python 3.11+ and, unless you're using SQLite, a MySQL 8+ server.
Optional: `ffmpeg` on `PATH` for video material thumbnails — see
[Material thumbnails](#material-thumbnails) below. Everything else works
fine without it.

```powershell
git clone https://github.com/solomon-211/EduPortal_South-Sudan.git
cd EduPortal_South-Sudan
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
python backend\app.py
```

(macOS/Linux: `python3 -m venv .venv && source .venv/bin/activate`, same `pip install`/`python backend/app.py` after.)

The `.env.example` you copied defaults to a MySQL connection
(`MYSQL_HOST=localhost` etc.) — if you don't have MySQL installed locally,
open `.env` and replace the `MYSQL_*` lines with:

```env
DATABASE_URL=sqlite:///eduportal.db
```

That's the entire local-dev database setup — no server to install, no
migrations to run by hand. On first run, `python backend\app.py` applies
every Alembic migration and creates one platform admin account if none
exists yet (`ADMIN_EMAIL` / `ADMIN_PASSWORD` in `.env`, defaulting to
`admin@eduportal.ss` / `Admin1234!`). Everything else starts empty — your
own schools, materials, announcements, and users are the only data in the
system unless you opt into demo content (see [Demo accounts](#demo-accounts)).
Open `http://127.0.0.1:5000/`.

## Environment variables

All of these live in `.env` — copy `.env.example` to start. Only
`JWT_SECRET_KEY` is required for the app to boot; everything else has a
working default or degrades gracefully when unset (Google Sign-In hides its
button, push notifications stay off, email/SMS log to console instead of
sending). Adjust whichever section applies to how you're running the app —
the rest can be left at their defaults.

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` or `MYSQL_HOST`/`MYSQL_PORT`/`MYSQL_USER`/`MYSQL_PASSWORD`/`MYSQL_DATABASE` | Database connection — see [Database](#database) below |
| `JWT_SECRET_KEY` | Signs access tokens — set a real value outside development |
| `FLASK_DEBUG` | Set to `true` for local-dev auto-reload + the interactive debugger. Leave `false`/unset anywhere the app is reachable outside your own machine — the debug console allows arbitrary code execution |
| `PORT` | Port the dev server listens on (default `5000`) |
| `ADMIN_EMAIL`/`ADMIN_PASSWORD` | First-run platform admin account (default `admin@eduportal.ss` / `Admin1234!`) — see [Getting started](#getting-started) |
| `SEED_DEMO_DATA` | Set to `true` to load sample schools/materials/accounts into an empty database — see [Demo accounts](#demo-accounts) |
| `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASS`/`SMTP_FROM` | Outbound email (verification, password reset, notifications) — optional, logs to console when unset |
| `AT_API_KEY`/`AT_SENDER_ID` | Africa's Talking SMS — optional |
| `VAPID_PUBLIC_KEY`/`VAPID_PRIVATE_KEY`/`VAPID_CLAIMS_SUB` | Web Push keypair — see [Web Push](#web-push) |
| `GOOGLE_CLIENT_ID` | Google Sign-In — see [Google Sign-In](#google-sign-in) |
| `S3_BUCKET`/`S3_REGION`/`S3_ACCESS_KEY`/`S3_SECRET_KEY`/`S3_ENDPOINT_URL`/`S3_PUBLIC_BASE_URL` | Optional S3-compatible file storage; local disk is used when `S3_BUCKET` is blank |
| `BACKUP_RETENTION_DAYS` | Days to keep database backups before pruning (default 14) — see [Backups](#backups) |

## Database

MySQL is the production database. SQLite is the supported local-development
and test fallback — same schema, same code path, just a different engine (set
via `DATABASE_URL`). Both are driven by the same Alembic migrations in
`alembic/versions/`, written to run correctly on either.

### MySQL

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
`users.name` instead of `full_name`, and no `gender_type` column on
`schools`) and is what `app.py` actually queries.

## Demo accounts

By default the database starts clean — no sample schools, materials, or
demo logins, so your own data is the only data. To load a realistic demo
dataset (useful for local development, never for production), set
`SEED_DEMO_DATA=true` in `.env` before the first run against an empty
database. That gives you one working login per role, all sharing the
password `Demo1234!`:

| Role | Email |
| --- | --- |
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

An existing account with a matching email is logged in directly. A
first-time Google sign-in instead prompts for a role — student, parent,
teacher, school admin, or NGO officer — before the account is created;
`admin` is deliberately not offered here, since there's meant to be exactly
one platform admin unless someone with existing admin access creates
another via the Users tab. The account is created only after a role is
chosen, using the same Google ID token re-verified on the second request —
no separate pending-signup state to manage.

## Background jobs

APScheduler runs in-process, starting alongside the dev server (`python
backend/app.py`). Two jobs, each also running once at startup:

- **Deadline reminders** — every 6 hours, notifies applicants once per
  milestone (3 and 1 days before a scholarship's deadline) by in-app
  notification + email.
- **Database backup** — every 24 hours, snapshots the configured database
  into `backups/` (see below).

It does not run under `flask run` or a WSGI server that only imports the
app — start it explicitly there if you deploy that way (see
[Deployment](#deployment)).

## Material thumbnails

Each materials card shows a real preview — the first page of a PDF, or a
frame pulled from a video — instead of a generic document/play-button icon,
generated once at upload time and cached (a `thumbnail_path` column on the
material) rather than regenerated on every request.

- **PDFs** — rendered with [PyMuPDF](https://pymupdf.readthedocs.io/)
  (`pip install -r requirements.txt` already covers this; no system package
  needed).
- **Videos** — a frame ~1 second in, extracted via the system `ffmpeg`
  binary through a subprocess call. Install it separately:
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: `winget install --id Gyan.FFmpeg -e`
  - macOS: `brew install ffmpeg`

Neither is required for the app to run — if `ffmpeg` isn't installed, or a
particular file fails to render (corrupt PDF, zero-length video, etc.), the
upload still succeeds; that material's card just falls back to the generic
icon instead of a real preview. Thumbnails are stored alongside the
material itself (local disk or S3, whichever `save_file()` is configured
for — see [Environment variables](#environment-variables)).

## Backups

`backend/backup.py` snapshots the live database: `sqlite3`'s built-in
`.backup()` for SQLite, `mysqldump` (must be on `PATH`) for MySQL. Every run
— scheduled or manual — is recorded in the `backup_runs` table (timestamp,
success/failure, file size) and surfaced on the Admin Panel. Files older
than `BACKUP_RETENTION_DAYS` (default 14) are pruned automatically. Trigger
one manually (from `backend/`, so its local imports resolve):

```powershell
cd backend
python -c "from backup import run_backup; print(run_backup())"
```

## Main URLs

- `/` — redirects to `/login`
- `/login` — sign in
- `/register` — two-step registration
- `/dashboard` — role-aware dashboard
- `/directory` — school directory (`/schools/<id>` for a single school's public profile)
- `/materials` — study materials
- `/opportunities` — scholarships (`/my-applications` to track your own)
- `/announcements` — announcements feed
- `/organizations` — verified organization directory
- `/bookmarks`, `/profile`, `/settings` — saved items, account details, notification/security preferences
- `/admin` — onboarding, moderation queue, users, analytics, audit log (admin only)
- `/school-dashboard`, `/ngo-dashboard`, `/org-dashboard` — role-specific management views
- `/forgot-password`, `/accept-invite` — password recovery and invitation acceptance pages
- `/healthz` — health check (`status`, `database.engine`, `database.connected`) — point a load balancer or uptime monitor at this

### Onboarding, from the admin side

Schools, NGOs, and partner organizations (ministries, universities, exam
bodies) all reach the platform the same two ways, both ending in the same
place — an admin review queue:

1. **Admin-initiated** — the Admin Panel's Onboarding tab creates the
   record immediately (visible right away) and emails an invitation link
   for that school/NGO/organization's own admin account.
2. **Self-service** — a visitor requests their school, NGO, or organization
   be listed from the public site; the record is created unverified and
   only appears once an admin approves it from the same Onboarding →
   Approvals queue used for every other moderated content type.

## REST API reference

All request/response bodies are JSON (`Content-Type: application/json`)
except file uploads, which use `multipart/form-data`. Every `/api/*` response
carries `Cache-Control: no-store` so browsers and proxies never serve stale
data. Authenticated routes expect `Authorization: Bearer <access_token>`;
the two exceptions that read a token from a query string instead
(`?token=`) are `/api/materials/<id>/stream` and
`/api/notifications/stream`, since `<a target="_blank">` links and
`EventSource` can't set custom headers. Error responses are
`{"error": "message"}` with a non-2xx status code; list endpoints return
`{"items": [...]}` (paginated ones add `total`/`page`/`per_page`).

**Auth legend**: **Public** — no token needed · **Any user** — any logged-in
role (`@require_auth`) · **Role(s)** — only that role, enforced by
`@require_role(...)` · **Owner** — logged in *and* the record's own
school/NGO/org (an admin can always act on any record too).

### Authentication & sessions

| Method & path | Auth | Description |
| --- | --- | --- |
| `POST /api/login` | Public | Email/phone + password → access + refresh token. Rate-limited 10/min. |
| `POST /api/register` | Public | Create an account (student/parent/teacher/school_admin/ngo_officer/org_publisher). Email accounts require verification; phone-only accounts are auto-verified. Rate-limited 5/min. |
| `GET /api/verify-email?token=` | Public | Confirms a registration email link; returns tokens on success. |
| `POST /api/resend-verification` | Public | Re-sends the verification email if the account exists and is unverified (always returns success, to avoid enumeration). Rate-limited 3/min. |
| `POST /api/auth/google` | Public | Google Sign-In. First-time users without a `role` in the body get `{"needs_role": true}` back instead of an account. Rate-limited 15/min. |
| `POST /api/refresh` | Public (valid refresh token) | Exchanges a refresh token for a new access + refresh token pair (rotation). Rate-limited 30/min. |
| `POST /api/logout` | Public | Revokes the supplied refresh token. |
| `POST /api/forgot-password` | Public | Generates a reset code, sent by email (or SMS if no email). Always returns success. Rate-limited 5/min. |
| `POST /api/reset-password` | Public (valid reset code) | Consumes a reset code (1-hour validity) and sets a new password. |
| `POST /api/accept-invite` | Public (valid invite token) | Creates the invited school_admin/ngo_officer/org_publisher account and marks the invite used. Rate-limited 10/min. |
| `GET /api/invitations/check?token=` | Public | Looks up an invite's role/email/entity name so the accept-invite page can pre-fill itself. |

### Profile & account

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/me` | Any user | Full profile of the signed-in user. |
| `PUT /api/me` | Any user | Update editable profile fields (name, contact info, notification preferences, role-specific fields like `grade`/`subjects`/`institution`). |
| `POST /api/me/avatar` | Any user | Upload a profile picture (`avatar` file field, content-verified image). |
| `POST /api/change-password` | Any user | Requires current password; revokes every other session on success. |
| `POST /api/deactivate-account` | Any user | Self-deactivates the account and revokes all sessions. |

### Schools

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/schools` | Public | Search/filter approved schools by `state`, `level`, `type`, `boarding`, `ownership`, or free-text `search`; paginated (`page`, `per_page`). |
| `GET /api/schools/<id>` | Public (owner if unapproved) | Full school profile. Unapproved schools are only visible to their own `school_admin` or an `admin`. |
| `POST /api/schools` | `school_admin`, `admin` | Create a school. A `school_admin` self-listing goes into the moderation queue and auto-links to their account; an `admin`-created school is auto-approved. |
| `PUT /api/schools/<id>` | Owner (`school_admin`), `admin` | Update any of ~30 profile fields (contact info, mission/vision, facilities checkboxes, fees, etc.). |
| `DELETE /api/schools/<id>` | `admin` | Deletes the school and its requirements/exam-results rows, and clears `school_id` on any user who was linked to it (so they aren't left pointing at a dead record). |
| `GET /api/schools/<id>/requirements` | Public | Itemised admission-requirements checklist. |
| `PUT /api/schools/<id>/requirements` | Owner, `admin` | Replaces the entire checklist. |
| `POST /api/schools/<id>/requirements-doc` | Owner, `admin` | Uploads a single PDF/image requirements document (`doc` field), alongside the itemised checklist. |
| `GET /api/schools/<id>/exam-results` | Public | National exam pass-rate history for the school. |
| `PUT /api/schools/<id>/exam-results` | Owner, `admin` | Replaces the exam-results rows. |
| `POST /api/schools/<id>/logo` | Owner, `admin` | Uploads the school's logo (`logo` field, content-verified image). |
| `GET /api/my-school` | `school_admin` | The caller's own school, requirements, submitted materials/announcements, bookmark count, and exam results in one call. |

### Study materials

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/materials` | Public | Search/filter approved materials by `subject` (substring), `grade`, `year`, `type`, free-text `search`; sortable, paginated. |
| `GET /api/materials/<id>` | Public | Single material's metadata. |
| `POST /api/materials` | `teacher`, `school_admin` | Submits a material record (`title`, `subject`, `grade`, `year`, `type`) for review — no file yet. |
| `POST /api/materials/<id>/upload` | Owner, `admin` | Attaches the actual file (PDF/MP4/WebM/OGG/M4V) to an existing record; generates a thumbnail. |
| `PUT /api/materials/<id>` | Owner, `admin` | Edits metadata; a non-admin edit resets `approved` to 0 for re-review. |
| `DELETE /api/materials/<id>` | Owner, `admin` | Deletes the material and its bookmarks. |
| `GET /api/materials/<id>/stream` | Any user (or `?token=`) | Serves the file inline (view/watch in browser). |
| `GET /api/materials/<id>/download` | Any user except `parent` | Serves the file as a download attachment and increments its download counter. |

### Organizations (verified partners)

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/organizations` | Public | Verified organizations, filterable by `org_type`/`state`. |
| `GET /api/organizations/<id>` | Public | Organization profile plus its 10 most recent announcements. |
| `POST /api/organizations/request` | Public | Self-service listing request — creates an unverified record for admin review. |
| `PUT /api/my-org/profile` | `org_publisher` | Updates the caller's own linked organization's profile. |
| `GET /api/my-org` | `org_publisher` | The caller's own organization plus everything they've posted. |

### Announcements

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/announcements` | Public | Filter approved, non-expired announcements by `source`, `org_type`, `audience`, `priority`, `state`, `date_from`/`date_to`, or `search`. |
| `POST /api/announcements/<id>/view` | Public | Increments an announcement's impression counter (fired once per card shown). |
| `POST /api/announcements` | `school_admin`, `ngo_officer`, `org_publisher`, `admin` | Creates an announcement; auto-approved only for `admin`. |
| `POST /api/announcements/<id>/upload` | Owner, `admin` | Attaches a PDF (`file` field). |
| `PUT /api/announcements/<id>` | Owner, `admin` | Edits the announcement; a non-admin edit resets it for re-review. |
| `DELETE /api/announcements/<id>` | Owner, `admin` | Deletes it. |

### Scholarships & applications

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/scholarships` | Public | Filter approved scholarships by `deadline_after`, `state`/`eligibility` (substring match), or `search`. |
| `GET /api/scholarships/<id>` | Public | Full scholarship detail, joined with the posting NGO's contact info. |
| `POST /api/scholarships` | `ngo_officer` | Creates a scholarship for the caller's own NGO. |
| `PUT /api/scholarships/<id>` | Owner (`ngo_officer`), `admin` | Edits it; a non-admin edit resets it for re-review. |
| `DELETE /api/scholarships/<id>` | Owner, `admin` | Deletes it and its applications/bookmarks. |
| `POST /api/scholarships/<id>/poster` | Owner, `admin` | Uploads a poster image. |
| `POST /api/scholarships/<id>/video` | Owner, `admin` | Uploads a promo video (MP4/WebM/OGG/M4V). |
| `GET /api/applications` | Any user | The caller's own scholarship applications. |
| `POST /api/applications` | Any user | Applies to a scholarship (`scholarship_id`, optional `note`); blocks duplicate applications. |
| `DELETE /api/applications/<id>` | Any user (own application) | Withdraws a still-`submitted` application. |
| `POST /api/admin/applications/<id>/status` | `admin` | Sets status (`under_review`/`shortlisted`/`successful`/`unsuccessful`); notifies the applicant in-app and by email. |

### Bookmarks

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/bookmarks` | Any user | Raw bookmark rows (id/type/item_id). |
| `GET /api/bookmarks/detailed` | Any user | Bookmarks enriched with the full saved item's details (school/material/scholarship), batched to avoid N+1 queries. |
| `POST /api/bookmarks` | Any user except `parent` | Saves a school, material, or scholarship. |
| `DELETE /api/bookmarks/<id>` | Any user (own bookmark) | Removes a bookmark. |

### Notifications & push

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/notifications` | Any user | Persisted notifications merged with upcoming-deadline and recent-announcement feeds; includes unread `count`. |
| `POST /api/notifications/<id>/read` | Any user (own notification) | Marks one notification read. |
| `POST /api/notifications/read-all` | Any user | Marks all of the caller's notifications read. |
| `GET /api/notifications/stream` | Any user (via `?token=`) | Server-Sent Events stream — pushes new notifications live. |
| `GET /api/push/vapid-public-key` | Public | Returns the VAPID public key and whether push is configured. |
| `POST /api/push/subscribe` | Any user | Registers a browser push subscription. |
| `POST /api/push/unsubscribe` | Any user | Removes a push subscription. |

### NGO profile & programs

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/my-ngo` | `ngo_officer` | The caller's own NGO, its scholarships, announcements, programs, and total application count. |
| `PUT /api/my-ngo` | `ngo_officer` | Creates the NGO profile on first save, or updates it thereafter. |
| `POST /api/my-ngo/logo` | `ngo_officer` | Uploads the NGO's logo. |
| `GET /api/my-ngo/programs` | `ngo_officer` | The caller's own NGO's programs. |
| `POST /api/my-ngo/programs` | `ngo_officer` | Adds a program (name + target beneficiaries/coverage/reach). |
| `DELETE /api/my-ngo/programs/<id>` | `ngo_officer` (own program) | Removes a program. |
| `GET /api/ngos/<id>/programs` | Public | An NGO's programs, for its public profile. |

### Admin — moderation & onboarding

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/admin/queue` | `admin` | Counts and full item lists of everything awaiting approval (materials, announcements, scholarships, schools, NGOs, organizations). |
| `POST /api/admin/approve` | `admin` | Approves or rejects one item (`target_type`, `target_id`, `action`, optional rejection `note`); logs the action. |
| `POST /api/admin/onboard-school` | `admin` | Creates a school directly and emails a single-use admin-invite link. |
| `POST /api/admin/onboard-ngo` | `admin` | Creates an NGO directly and emails a single-use admin-invite link. |
| `POST /api/admin/organizations` | `admin` | Creates a verified organization and emails an `org_publisher` invite. |
| `PUT /api/admin/organizations/<id>` | `admin` | Updates an organization's details/verified flag. |
| `DELETE /api/admin/organizations/<id>` | `admin` | Deletes an organization. |
| `GET /api/admin/ngos` | `admin` | Lists every NGO (verified or not). |
| `DELETE /api/admin/ngos/<id>` | `admin` | Deletes an NGO, its programs and scholarships, and unlinks any user assigned to it. |
| `POST /api/admin/registration-verify` | `admin` | Manually attests a school's/NGO's registration number has been checked (not a live registry lookup). |

### Admin — users

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/admin/users` | `admin` | Lists users, filterable by `role`. |
| `GET /api/admin/pending-assignments` | `admin` | `school_admin`/`ngo_officer` accounts not yet linked to a school/NGO. |
| `POST /api/admin/users/<id>/assign-school` | `admin` | Links a `school_admin` to a school (or unassigns with a null `school_id`). |
| `POST /api/admin/users/<id>/assign-ngo` | `admin` | Links an `ngo_officer` to an NGO (or unassigns). |
| `PUT /api/admin/users/<id>` | `admin` | Edits a user's name/contact/location fields. |
| `POST /api/admin/users/<id>/role` | `admin` | Changes a user's role (can't demote yourself out of `admin`). |
| `POST /api/admin/users/<id>/suspend` | `admin` | Suspends an account (can't suspend yourself). |
| `POST /api/admin/users/<id>/unsuspend` | `admin` | Reactivates a suspended account. |
| `POST /api/admin/users/<id>/reset-password` | `admin` | Admin-initiated password reset, sent by email/SMS the same way as self-service. |
| `DELETE /api/admin/users/<id>` | `admin` | Deletes a user and their applications/resets/bookmarks/notifications (can't delete yourself). |
| `GET /api/admin/applications` | `admin` | All scholarship applications platform-wide, filterable by `status`. |

### Admin — analytics, audit & backups

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/admin/analytics` | `admin` | Users by state/role, top bookmarked schools/scholarships/materials, most-viewed announcements, application counts, approved-content totals. |
| `GET /api/admin/analytics/export.csv` | `admin` | The same analytics as a downloadable CSV. |
| `GET /api/admin/audit-log` | `admin` | Every logged admin action, filterable by `action`, `admin_id`, `date_from`/`date_to`. |
| `GET /api/admin/backup-status` | `admin` | The last 20 database backup runs (success/failure, file size, timestamp). |
| `POST /api/notifications/test-email` | `admin` | Sends a test email to verify SMTP configuration. |
| `POST /api/notifications/test-sms` | `admin` | Sends a test SMS to verify Africa's Talking configuration. |

### Misc

| Method & path | Auth | Description |
| --- | --- | --- |
| `GET /api/stats` | Public | Homepage counters — total schools/materials/scholarships/announcements/users. |
| `GET /healthz` | Public | `{"status", "database": {"engine", "connected"}}` — point an uptime monitor or load balancer health check here. |

## Security

- **Passwords** are hashed with bcrypt; the database only ever stores the hash.
- **Tokens** are signed JWTs (`JWT_SECRET_KEY`); access tokens expire after 2 hours, refresh tokens after 30 days and are single-use (each refresh issues a new one and invalidates the old).
- **Role-based access control** is enforced server-side on every write route via `@require_role(...)`/`@require_auth`, independent of whatever the frontend shows or hides.
- **Rate limiting** (Flask-Limiter) guards login, registration, password reset, verification-resend, Google auth, token refresh, and invite acceptance against brute-force and credential-stuffing.
- **Uploaded files are content-verified**, not trusted by extension: PDFs are opened with PyMuPDF, images and videos are signature-checked before being written to disk or S3.
- **No account enumeration** on `/api/forgot-password` and `/api/resend-verification` — both always return the same success message regardless of whether the account exists.
- **SQL is parameterized throughout** (`?` placeholders via SQLAlchemy Core) — no string-interpolated user input reaches a query.
- **HTTPS** is expected to be terminated by the reverse proxy in front of the app (see [Deployment](#deployment)) — this isn't something Flask itself enforces, so confirm your proxy redirects HTTP → HTTPS.
- **Secrets**: nothing in this repo hardcodes a real credential — `JWT_SECRET_KEY`, database credentials, SMTP/SMS/S3/Google keys are all read from environment variables, with `.env` gitignored. The only checked-in defaults are clearly-flagged development fallbacks (`dev-jwt-secret-change-in-prod`, the `Admin1234!`/`Demo1234!` bootstrap passwords) that log a warning and are documented in [Deployment](#deployment) as things to change before going live.

## Accessibility

The UI targets WCAG 2.1 AA but hasn't had a full formal audit. What's
actually in place: semantic heading structure (`<h1>`–`<h3>`, not just
styled `<p>` tags), real `<label>` elements tied to their inputs, checkbox
groups wrapped in `<fieldset>`/`<legend>` rather than a floating label, and
inline `onclick` handlers replaced with `addEventListener` so behavior
doesn't depend on inline JS. Not yet independently verified: colour-contrast
ratios and full screen-reader/keyboard-only navigation testing across every
page. Treat "AA-compliant" as an in-progress target, not a completed
certification.

## Deployment

The live instance runs on AWS (a single EC2 instance behind Nginx, with S3
for file storage); nothing about the app is AWS-specific though — it's a
standard Flask app that runs anywhere Python 3.11+ and either MySQL or
SQLite are available. Note that this is a single-server deployment, not the
load-balanced multi-server topology sometimes described in early design
documents — there is currently one application server and one Nginx
instance, not two behind a load balancer.

Whatever you deploy to, make sure of these before going live:

1. **`FLASK_DEBUG` is unset or `false`.** This is the default — see
   [Environment variables](#environment-variables) — but double-check.
   Werkzeug's debug console lets a visitor execute arbitrary Python if it's
   ever reachable, so this matters more than almost anything else here.
2. **`JWT_SECRET_KEY` is a real, private value**, not the
   `dev-jwt-secret-change-in-prod` default — anyone with that string can
   forge access tokens for any account.
3. **`ADMIN_PASSWORD` is set to something other than the `Admin1234!`
   default** — the app logs a warning and bootstraps the admin account with
   that default if it's left unset, which is fine for local development but
   not for anything reachable by the public. The `SEED_DEMO_DATA` sample
   accounts share a similarly well-known password (`Demo1234!`) — only
   enable that flag for a local demo, never in production.
4. Put a reverse proxy (Nginx or similar) in front with TLS, and raise its
   default upload-size limit — the app allows materials/scholarship media up
   to 100MB and avatars/logos up to 2MB, well above most proxies' 1MB
   default.

`python backend/app.py` (Flask's built-in server, `threaded=True`) is
genuinely fine for a small deployment like this one — the codebase doesn't
assume Gunicorn/uWSGI. Run it under a process supervisor (systemd or
equivalent) so it restarts on crash and on reboot. The one thing to keep in
mind if you ever move to a multi-process WSGI server: the SSE notification
stream and the APScheduler background jobs are both in-process,
single-worker assumptions (see [Notifications](#notifications) and
[Background jobs](#background-jobs)) — stick to a single worker process, or
budget time to move both onto a shared broker first.
