# EduPortal South Sudan

A Flask-based education portal for South Sudan that connects students, parents, teachers, school administrators, NGOs, and platform administrators. It provides a verified school directory, study materials, announcements, and scholarship listings — all moderated before going public.

---

## Table of Contents

- [User Roles](#user-roles)
- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Environment Variables](#environment-variables)
- [Database Setup](#database-setup)
- [Demo Accounts](#demo-accounts)
- [Running Tests](#running-tests)
- [Main Pages](#main-pages)
- [API Reference](#api-reference)
- [Background Jobs](#background-jobs)
- [File Storage](#file-storage)
- [Notifications](#notifications)
- [Web Push](#web-push)
- [Google Sign-In](#google-sign-in)
- [Material Thumbnails](#material-thumbnails)
- [Backups](#backups)
- [Security](#security)
- [Deployment](#deployment)

---

## User Roles

| Role | What they can do |
|---|---|
| `student` | Browse schools, materials, announcements; apply for scholarships; bookmark items |
| `parent` | Same as student, plus a linked child's school/grade on their profile |
| `teacher` | Everything a student can, plus upload study materials and post school announcements |
| `school_admin` | Manage their school's profile, admission requirements, materials, and applications |
| `ngo_officer` | Post and manage scholarships for their NGO |
| `org_publisher` | Post announcements on behalf of a verified organization |
| `admin` | Onboard schools/NGOs/organizations; approve/reject all submitted content; manage users, roles, analytics, and the audit log |

> The platform admin manages the platform, not the content. Their sidebar only shows the Admin Panel — no Dashboard, Materials, Scholarships, or Announcements. Every role only sees the nav items it's entitled to use, enforced both client-side (`sidebar-main.js`) and server-side (`@require_role`).

---

## Features

- **Authentication** — Email/phone + password or Google Sign-In; JWT access tokens (2h) with rotating refresh tokens (30 days)
- **Email verification** — Required before login for email-registered accounts; Google Sign-In auto-verifies
- **Password reset** — Time-limited, single-use reset codes sent by email or SMS; no account enumeration
- **Role-based access control** — Every write route is guarded server-side by `@require_role(...)`
- **Rate limiting** — Caps login, registration, password reset, and other sensitive endpoints per client
- **Upload validation** — Files are verified by actual content (not just extension) before being accepted
- **In-app notifications** — Persisted per-user with a live unread count
- **Real-time updates** — Server-Sent Events push new notifications instantly, no polling
- **Web Push** — VAPID-based browser push for users not actively on the site
- **Email/SMS delivery** — SMTP for email, Africa's Talking for SMS (both optional)
- **Background jobs** — APScheduler handles scholarship deadline reminders and scheduled database backups
- **File storage** — Local disk by default, or S3/Supabase Storage when configured
- **Two-tier moderation** — Schools, NGOs, materials, announcements, and scholarships require admin approval before going public
- **Analytics + CSV export** — User stats, top content, and downloadable reports from the Admin Panel
- **Audit log** — Every admin action is recorded and filterable

---

## Tech Stack

**Backend**
- Flask 3, SQLAlchemy Core (raw SQL), Alembic migrations
- PyJWT, bcrypt, Flask-Limiter, APScheduler
- pywebpush, google-auth, PyMuPDF

**Frontend**
- No framework, no build step — server-rendered HTML
- One self-contained stylesheet per page, vanilla JavaScript
- Fonts: Poppins (headings), Open Sans (body/UI)

**Database**
- MySQL (production), SQLite (local dev and testing)

**Testing**
- pytest against an in-memory SQLite database

---

## Project Structure

```
EduPortal_South-Sudan/
├── backend/
│   ├── app.py                  # All routes (flat, no blueprints)
│   ├── settings.py             # Env-driven config
│   ├── database.py             # Engine, query helpers, migrations, seeding
│   ├── jwt_helpers.py          # Tokens and role decorators
│   ├── google_oauth.py         # Google ID token verification
│   ├── scheduler.py            # APScheduler background jobs
│   ├── notification.py         # Email, SMS, web push, SSE pub/sub
│   ├── storage.py              # Local disk or S3 file storage
│   ├── backup.py               # Scheduled database snapshots
│   └── test_regression.py      # pytest suite
├── alembic/
│   └── versions/               # One migration file per schema change
├── database/
│   └── schema.sql              # Reference schema (documentation only)
├── frontend/
│   ├── html/                   # One template per page
│   ├── css/html/               # One stylesheet per page
│   ├── javascript/
│   │   ├── app/main.js         # Main client logic
│   │   ├── app/shared-utils.js # Shared helpers (window.EP)
│   │   ├── navigation/sidebar-main.js
│   │   └── sw.js               # Service worker for Web Push
│   └── assets/                 # Uploaded files (avatars, materials, logos, etc.)
├── requirements.txt
├── .env.example
└── README.md
```

---

## Getting Started

**Requirements:** Python 3.11+, and MySQL 8+ (optional — SQLite works for local dev).

```bash
# 1. Clone the repo
git clone https://github.com/solomon-211/EduPortal_South-Sudan.git
cd EduPortal_South-Sudan

# 2. Create and activate a virtual environment
python -m venv .venv

# Windows
.\.venv\Scripts\Activate.ps1

# macOS/Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up environment variables
copy .env.example .env   # Windows
cp .env.example .env     # macOS/Linux

# 5. Start the app
python backend/app.py
```

Open `http://127.0.0.1:5000/` in your browser.

**No MySQL?** Open `.env` and replace the `MYSQL_*` lines with:

```env
DATABASE_URL=sqlite:///eduportal.db
```

On first run, the app automatically applies all Alembic migrations and creates a platform admin account using `ADMIN_EMAIL` / `ADMIN_PASSWORD` from `.env` (defaults: `admin@eduportal.ss` / `Admin1234!`).

---

## Environment Variables

Copy `.env.example` to `.env` to get started. Only `JWT_SECRET_KEY` is required to boot — everything else has a working default or degrades gracefully when unset.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Full DB connection string (e.g. `sqlite:///eduportal.db` or `mysql+pymysql://...`) |
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` | MySQL connection (used if `DATABASE_URL` is not set) |
| `JWT_SECRET_KEY` | Signs access tokens — **change this before going live** |
| `FLASK_DEBUG` | Set `true` for local dev auto-reload. **Never enable in production** |
| `PORT` | Dev server port (default `5000`) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | First-run admin account (defaults: `admin@eduportal.ss` / `Admin1234!`) |
| `SEED_DEMO_DATA` | Set `true` to load sample data on first run (local dev only) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `SMTP_FROM` | Outbound email — logs to console when unset |
| `AT_API_KEY` / `AT_SENDER_ID` | Africa's Talking SMS — optional |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` / `VAPID_CLAIMS_SUB` | Web Push keypair |
| `GOOGLE_CLIENT_ID` | Google Sign-In — button is hidden when unset |
| `S3_BUCKET` / `S3_REGION` / `S3_ACCESS_KEY` / `S3_SECRET_KEY` / `S3_ENDPOINT_URL` / `S3_PUBLIC_BASE_URL` | S3-compatible file storage — local disk used when `S3_BUCKET` is blank |
| `BACKUP_RETENTION_DAYS` | Days to keep database backups before pruning (default `14`) |

---

## Database Setup

### SQLite (local development)

No setup needed. Just set this in `.env`:

```env
DATABASE_URL=sqlite:///eduportal.db
```

### MySQL (production)

Run this in your MySQL client as root:

```sql
CREATE DATABASE eduportal CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'eduportal_app'@'localhost' IDENTIFIED BY 'CHANGE_ME';
GRANT ALL PRIVILEGES ON eduportal.* TO 'eduportal_app'@'localhost';
FLUSH PRIVILEGES;
```

Then update `MYSQL_PASSWORD` in `.env` and start the app. Verify the connection:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/healthz
```

Expected response: `status: ok`, `database.engine: mysql`, `database.connected: true`.

> Migrations run automatically on startup — no manual `alembic upgrade` needed.

---

## Demo Accounts

Set `SEED_DEMO_DATA=true` in `.env` before the **first run** on an empty database to load sample schools, materials, announcements, scholarships, and one login per role. All demo accounts share the password `Demo1234!`.

| Role | Email |
|---|---|
| Student | `student@eduportal.ss` |
| Parent | `parent@eduportal.ss` |
| Teacher | `teacher@eduportal.ss` |
| School Admin | `schooladmin@eduportal.ss` |
| NGO Officer | `contact@futuress.org` |
| Org Publisher | `orgpublisher@eduportal.ss` |
| Platform Admin | `admin@eduportal.ss` / `Admin1234!` |

> Never enable `SEED_DEMO_DATA` in production.

---

## Running Tests

```bash
pytest backend/test_regression.py -v
```

Runs against an isolated in-memory SQLite database — safe to run even with a MySQL-configured `.env`.

---

## Main Pages

| URL | Description |
|---|---|
| `/` | Redirects to `/login` |
| `/login` | Sign in |
| `/register` | Two-step registration |
| `/dashboard` | Role-aware dashboard |
| `/directory` | School directory |
| `/materials` | Study materials |
| `/opportunities` | Scholarships |
| `/my-applications` | Track your scholarship applications |
| `/announcements` | Announcements feed |
| `/organizations` | Verified organization directory |
| `/bookmarks` | Saved items |
| `/profile` | Account details |
| `/settings` | Notification and security preferences |
| `/admin` | Admin panel (admin only) |
| `/school-dashboard` | School management view |
| `/ngo-dashboard` | NGO management view |
| `/org-dashboard` | Organization management view |
| `/healthz` | Health check endpoint |

---

## API Reference

All request/response bodies are JSON except file uploads (`multipart/form-data`). Authenticated routes require `Authorization: Bearer <access_token>`. Error responses use `{"error": "message"}` with a non-2xx status.

**Auth legend:** Public — no token · Any user — any logged-in role · Role(s) — specific role only · Owner — the record's own school/NGO/org (admins can always act on any record)

### Authentication

| Method & Path | Auth | Description |
|---|---|---|
| `POST /api/login` | Public | Email/phone + password → tokens. Rate-limited 10/min |
| `POST /api/register` | Public | Create an account. Rate-limited 5/min |
| `GET /api/verify-email?token=` | Public | Confirm email verification link |
| `POST /api/resend-verification` | Public | Re-send verification email. Rate-limited 3/min |
| `POST /api/auth/google` | Public | Google Sign-In. Rate-limited 15/min |
| `POST /api/refresh` | Public | Rotate refresh token → new token pair. Rate-limited 30/min |
| `POST /api/logout` | Public | Revoke current refresh token |
| `POST /api/forgot-password` | Public | Send password reset code. Rate-limited 5/min |
| `POST /api/reset-password` | Public | Consume reset code and set new password |
| `POST /api/accept-invite` | Public | Accept an invitation and create account. Rate-limited 10/min |
| `GET /api/invitations/check?token=` | Public | Look up invite details for pre-filling the form |

### Profile & Account

| Method & Path | Auth | Description |
|---|---|---|
| `GET /api/me` | Any user | Get signed-in user's full profile |
| `PUT /api/me` | Any user | Update profile fields |
| `POST /api/me/avatar` | Any user | Upload profile picture |
| `POST /api/change-password` | Any user | Change password; revokes all other sessions |
| `POST /api/deactivate-account` | Any user | Deactivate account and revoke all sessions |

### Schools

| Method & Path | Auth | Description |
|---|---|---|
| `GET /api/schools` | Public | Search/filter approved schools; paginated |
| `GET /api/schools/<id>` | Public | Full school profile |
| `POST /api/schools` | `school_admin`, `admin` | Create a school |
| `PUT /api/schools/<id>` | Owner, `admin` | Update school profile |
| `DELETE /api/schools/<id>` | `admin` | Delete school |
| `GET /api/schools/<id>/requirements` | Public | Admission requirements checklist |
| `PUT /api/schools/<id>/requirements` | Owner, `admin` | Replace requirements checklist |
| `POST /api/schools/<id>/requirements-doc` | Owner, `admin` | Upload requirements PDF |
| `GET /api/schools/<id>/exam-results` | Public | National exam pass-rate history |
| `PUT /api/schools/<id>/exam-results` | Owner, `admin` | Replace exam results |
| `POST /api/schools/<id>/logo` | Owner, `admin` | Upload school logo |
| `GET /api/my-school` | `school_admin` | Caller's own school data in one call |

### Study Materials

| Method & Path | Auth | Description |
|---|---|---|
| `GET /api/materials` | Public | Search/filter approved materials; paginated |
| `GET /api/materials/<id>` | Public | Single material metadata |
| `POST /api/materials` | `teacher`, `school_admin` | Submit a material record for review |
| `POST /api/materials/<id>/upload` | Owner, `admin` | Attach file to material record |
| `PUT /api/materials/<id>` | Owner, `admin` | Edit metadata |
| `DELETE /api/materials/<id>` | Owner, `admin` | Delete material |
| `GET /api/materials/<id>/stream` | Any user | Stream file inline in browser |
| `GET /api/materials/<id>/download` | Any user (except `parent`) | Download file; increments counter |

### Announcements

| Method & Path | Auth | Description |
|---|---|---|
| `GET /api/announcements` | Public | Filter approved announcements |
| `POST /api/announcements/<id>/view` | Public | Increment impression counter |
| `POST /api/announcements` | `school_admin`, `ngo_officer`, `org_publisher`, `admin` | Create announcement |
| `POST /api/announcements/<id>/upload` | Owner, `admin` | Attach PDF to announcement |
| `PUT /api/announcements/<id>` | Owner, `admin` | Edit announcement |
| `DELETE /api/announcements/<id>` | Owner, `admin` | Delete announcement |

### Scholarships & Applications

| Method & Path | Auth | Description |
|---|---|---|
| `GET /api/scholarships` | Public | Filter approved scholarships |
| `GET /api/scholarships/<id>` | Public | Full scholarship detail |
| `POST /api/scholarships` | `ngo_officer` | Create a scholarship |
| `PUT /api/scholarships/<id>` | Owner, `admin` | Edit scholarship |
| `DELETE /api/scholarships/<id>` | Owner, `admin` | Delete scholarship |
| `POST /api/scholarships/<id>/poster` | Owner, `admin` | Upload poster image |
| `POST /api/scholarships/<id>/video` | Owner, `admin` | Upload promo video |
| `GET /api/applications` | Any user | Caller's own applications |
| `POST /api/applications` | Any user | Apply to a scholarship |
| `DELETE /api/applications/<id>` | Any user | Withdraw a submitted application |
| `POST /api/admin/applications/<id>/status` | `admin` | Update application status |

### Bookmarks

| Method & Path | Auth | Description |
|---|---|---|
| `GET /api/bookmarks` | Any user | Raw bookmark rows |
| `GET /api/bookmarks/detailed` | Any user | Bookmarks with full item details |
| `POST /api/bookmarks` | Any user (except `parent`) | Save a school, material, or scholarship |
| `DELETE /api/bookmarks/<id>` | Any user | Remove a bookmark |

### Notifications & Push

| Method & Path | Auth | Description |
|---|---|---|
| `GET /api/notifications` | Any user | Persisted notifications + unread count |
| `POST /api/notifications/<id>/read` | Any user | Mark one notification read |
| `POST /api/notifications/read-all` | Any user | Mark all notifications read |
| `GET /api/notifications/stream` | Any user (via `?token=`) | SSE stream for live notifications |
| `GET /api/push/vapid-public-key` | Public | VAPID public key |
| `POST /api/push/subscribe` | Any user | Register a push subscription |
| `POST /api/push/unsubscribe` | Any user | Remove a push subscription |

### NGO Profile & Programs

| Method & Path | Auth | Description |
|---|---|---|
| `GET /api/my-ngo` | `ngo_officer` | Caller's NGO with scholarships, announcements, and programs |
| `PUT /api/my-ngo` | `ngo_officer` | Create or update NGO profile |
| `POST /api/my-ngo/logo` | `ngo_officer` | Upload NGO logo |
| `GET /api/my-ngo/programs` | `ngo_officer` | List NGO programs |
| `POST /api/my-ngo/programs` | `ngo_officer` | Add a program |
| `DELETE /api/my-ngo/programs/<id>` | `ngo_officer` | Remove a program |
| `GET /api/ngos/<id>/programs` | Public | Public view of an NGO's programs |

### Organizations

| Method & Path | Auth | Description |
|---|---|---|
| `GET /api/organizations` | Public | List verified organizations |
| `GET /api/organizations/<id>` | Public | Organization profile + recent announcements |
| `POST /api/organizations/request` | Public | Self-service listing request |
| `PUT /api/my-org/profile` | `org_publisher` | Update own organization profile |
| `GET /api/my-org` | `org_publisher` | Caller's organization and posted content |

### Admin

| Method & Path | Auth | Description |
|---|---|---|
| `GET /api/admin/queue` | `admin` | All items awaiting approval |
| `POST /api/admin/approve` | `admin` | Approve or reject an item |
| `POST /api/admin/onboard-school` | `admin` | Create school and send invite |
| `POST /api/admin/onboard-ngo` | `admin` | Create NGO and send invite |
| `POST /api/admin/organizations` | `admin` | Create organization and send invite |
| `PUT /api/admin/organizations/<id>` | `admin` | Update organization |
| `DELETE /api/admin/organizations/<id>` | `admin` | Delete organization |
| `GET /api/admin/ngos` | `admin` | List all NGOs |
| `DELETE /api/admin/ngos/<id>` | `admin` | Delete NGO |
| `GET /api/admin/users` | `admin` | List users, filterable by role |
| `POST /api/admin/users/<id>/role` | `admin` | Change a user's role |
| `POST /api/admin/users/<id>/suspend` | `admin` | Suspend an account |
| `POST /api/admin/users/<id>/unsuspend` | `admin` | Reactivate a suspended account |
| `DELETE /api/admin/users/<id>` | `admin` | Delete a user |
| `GET /api/admin/analytics` | `admin` | Platform analytics |
| `GET /api/admin/analytics/export.csv` | `admin` | Download analytics as CSV |
| `GET /api/admin/audit-log` | `admin` | Filterable admin action log |
| `GET /api/admin/backup-status` | `admin` | Last 20 backup runs |
| `GET /api/stats` | Public | Homepage counters (schools, materials, scholarships, etc.) |
| `GET /healthz` | Public | Health check |

---

## Background Jobs

APScheduler runs in-process alongside the app. Two jobs run on startup and on a schedule:

- **Deadline reminders** — every 6 hours, notifies applicants at 3 and 1 days before a scholarship deadline (in-app + email)
- **Database backup** — every 24 hours, snapshots the database into `backups/`

> These are single-process assumptions. If you move to a multi-worker WSGI setup, you'll need a shared broker (e.g. Redis) for both jobs and SSE.

---

## File Storage

By default, uploaded files are saved to local disk under `frontend/assets/`. To use S3 or Supabase Storage, set `S3_BUCKET` and the related variables in `.env`.

Covers: avatars, school/NGO logos, admission requirement documents, study materials, announcement attachments, and scholarship poster images/promo videos.

---

## Notifications

- Persisted per-user notifications for application status changes and scholarship deadline reminders
- `GET /api/notifications/stream` — SSE endpoint for live bell updates (pass token as `?token=` since browsers can't set headers on `EventSource`)
- In-app + email + Web Push all fire from the same notification creation path

---

## Web Push

Enables browser notifications when the user isn't on the site. Generate a VAPID keypair once:

```bash
python -c "from py_vapid import Vapid02; v=Vapid02(); v.generate_keys()"
```

Set `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, and `VAPID_CLAIMS_SUB` in `.env`. Users opt in from Settings → Push Notifications.

---

## Google Sign-In

### Setting up for local testing

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials) and create a new project (or use an existing one)
2. Click **Create Credentials → OAuth 2.0 Client ID**
3. Set the application type to **Web application**
4. Under **Authorized JavaScript origins**, add:
   ```
   http://localhost:5000
   http://127.0.0.1:5000
   ```
5. Click **Create** and copy the **Client ID**
6. Open your `.env` file and set:
   ```env
   GOOGLE_CLIENT_ID=your-client-id-here.apps.googleusercontent.com
   ```
7. Start the app and open `http://127.0.0.1:5000/login` — the **Continue with Google** button will appear automatically

> Use `http://127.0.0.1:5000` in your browser (not `localhost:5000`) — Google's OAuth sometimes rejects `localhost` depending on your browser/OS configuration.

### How it works

- **Existing account** — if the Google email matches an existing account, you're logged in directly
- **New account** — you'll be prompted to choose a role (student, parent, teacher, school admin, or NGO officer) before the account is created
- The `admin` role is not available through Google Sign-In by design — admin accounts must be created manually
- Google Sign-In auto-verifies the email, so no verification email is sent

### Troubleshooting locally

- **Button not showing** — check that `GOOGLE_CLIENT_ID` is set in `.env` and the app was restarted after the change
- **"Origin not allowed" error** — make sure `http://127.0.0.1:5000` is listed under Authorized JavaScript origins in the Google Cloud Console (changes can take a few minutes to propagate)
- **"redirect_uri_mismatch" error** — this app uses the Google Identity Services popup flow, not a redirect URI, so you don't need to set Authorized redirect URIs

---

## Material Thumbnails

Each material card shows a real preview instead of a generic icon, generated once at upload time.

- **PDFs** — first page rendered via PyMuPDF (included in `requirements.txt`, no system package needed)
- **Videos** — a frame ~1 second in, extracted via the system `ffmpeg` binary

Install `ffmpeg` if you want video thumbnails:

```bash
# Ubuntu/Debian
sudo apt install ffmpeg

# Windows
winget install --id Gyan.FFmpeg -e

# macOS
brew install ffmpeg
```

If `ffmpeg` isn't installed, uploads still succeed — the card just shows a generic icon instead.

---

## Backups

`backend/backup.py` snapshots the database on a schedule:
- SQLite — uses Python's built-in `.backup()`
- MySQL — uses `mysqldump` (must be on `PATH`)

Files older than `BACKUP_RETENTION_DAYS` (default 14) are pruned automatically. To trigger a backup manually:

```bash
cd backend
python -c "from backup import run_backup; print(run_backup())"
```

Backup history is visible in the Admin Panel under backup status.

---

## Security

- Passwords hashed with bcrypt — only the hash is stored
- JWTs signed with `JWT_SECRET_KEY`; access tokens expire in 2h, refresh tokens in 30 days (single-use, rotated on every refresh)
- Every write route is protected server-side by `@require_role` / `@require_auth`
- Rate limiting on all sensitive endpoints (login, registration, password reset, etc.)
- Uploaded files are content-verified, not trusted by extension
- No account enumeration on `/api/forgot-password` or `/api/resend-verification`
- All SQL uses parameterized queries — no string-interpolated user input
- No hardcoded credentials — all secrets come from environment variables

---

## Deployment

The live instance runs on AWS (single EC2 instance behind Nginx, with S3 for file storage). The app runs anywhere Python 3.11+ and MySQL or SQLite are available.

**Before going live, make sure:**

1. `FLASK_DEBUG` is `false` or unset — Werkzeug's debug console allows arbitrary code execution if exposed
2. `JWT_SECRET_KEY` is a real, private value — the default `dev-jwt-secret-change-in-prod` lets anyone forge tokens
3. `ADMIN_PASSWORD` is changed from the default `Admin1234!`
4. `SEED_DEMO_DATA` is `false` or unset — demo accounts use a well-known password
5. A reverse proxy (Nginx or similar) handles TLS and raises the upload size limit (the app allows up to 100MB for materials/videos, 2MB for avatars/logos)

`python backend/app.py` (Flask's built-in threaded server) is fine for small deployments. Run it under a process supervisor (systemd or equivalent) so it restarts on crash and reboot.
