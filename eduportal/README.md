# EduPortal South Sudan

Starter project structure:
- `frontend/` for HTML, CSS, JavaScript, and static assets
- `backend/` for Flask application code
- `database/` for SQL schema and setup scripts

## Run locally

```powershell
cd "c:\Users\HP\OneDrive\Desktop\EduPortal South Sudan\eduportal"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install flask
python backend\app.py
```

Open:
- `http://127.0.0.1:5000/` for login
- `http://127.0.0.1:5000/dashboard` for dashboard

## Next steps

1. Replace the placeholder auth logic with MySQL-backed user lookup.
2. Add school directory, materials, scholarships, and admin routes.
3. Wire NGINX and HTTPS on deployment.
