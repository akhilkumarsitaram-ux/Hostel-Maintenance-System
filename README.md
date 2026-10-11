# Applying DevOps Practices to a University Hostel Maintenance System

**A case study based on the Oxford Brookes University context**

## Academic disclaimer

This repository is an **academic prototype** for a college DevOps project. It is **inspired by** the Oxford Brookes University hostel context but is **not** an official Oxford Brookes University application, has **not** been approved by the university, and does **not** integrate with any real university systems.

---

## Abstract and problem statement

University hostels need a reliable way for residents to report maintenance issues (electrical faults, plumbing, cleaning, furniture) and for staff and administrators to track assignments, progress, and resolution. Paper forms and informal messages are hard to audit and slow to prioritize.

This project demonstrates a simple **web-based maintenance portal** together with **DevOps practices**: automated tests, linting, Git version control, Docker containerization, and GitHub Actions CI.

## Objectives and solution

| Objective | Solution in this project |
|-----------|---------------------------|
| Structured complaint logging | SQLite database with complaints and history tables |
| Role-based access | Resident, staff, and admin dashboards |
| Secure sign-in | Flask sessions and Werkzeug password hashing |
| Quality assurance | `unittest` test suite and Ruff checks in CI |
| Repeatable environments | Dockerfile and docker-compose with persistent volume |
| Operability | Python logging and `GET /health` |

## Features by role

- **Resident:** Submit complaints, search/filter own requests, view detail and staff updates.
- **Staff:** View assigned complaints, set status to *In Progress* or *Resolved*, add notes, view history.
- **Admin:** View all complaints, filter by status/category/priority/staff, assign to staff, change priority and status, see summary counts.

## Technology stack

- HTML5, CSS3, vanilla JavaScript
- Python 3.11+ and Flask
- SQLite (`sqlite3` module)
- Flask-WTF / WTForms (CSRF + validation)
- unittest, Ruff, Git, Docker, GitHub Actions, Gunicorn (container)

## Architecture (simple monolith)

```text
Browser (HTML/CSS/JS)
    → Flask (app.py) — routes, auth, validation
    → models.py — parameterized SQL, SQLite
    → SQLite file (DATABASE_PATH)
```

Authentication uses server-side sessions; authorization checks run on every protected route using the session user, never client-supplied role fields.

## Folder structure

```text
hostel-maintenance-system/
├── app.py                 # Flask app and CLI (init-db, seed-demo)
├── models.py              # Database schema and queries
├── wsgi.py                # Gunicorn entry point
├── requirements.txt
├── pyproject.toml         # Ruff configuration
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── templates/             # Jinja2 HTML templates
├── static/css/style.css
├── static/js/app.js
├── tests/test_app.py
├── docs/devops-pipeline.md
└── .github/workflows/ci.yml
```

---

## Windows prerequisites

1. **Python 3.11 or 3.12** — [python.org/downloads](https://www.python.org/downloads/) (check “Add Python to PATH”).
2. **Git** — [git-scm.com/download/win](https://git-scm.com/download/win)
3. **Docker Desktop** (optional, for containers) — [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)

---

## Setup (PowerShell)

Open PowerShell in the project folder (`Hostel-Maintenance-System`).

### 1. Check Python

```powershell
python --version
```

### 2. Create and activate a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If activation is blocked:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

### 3. Install dependencies

```powershell
pip install -r requirements.txt
pip install ruff
```

### 4. Environment variables

```powershell
Copy-Item .env.example .env
```

Edit `.env` if needed. Default `DATABASE_PATH` is `data/hostel_maintenance.db`.

### 5. Initialize the database

```powershell
python app.py init-db
```

Safe to run again — it creates missing tables without deleting data.

### 6. Seed demo data

```powershell
python app.py seed-demo
```

Idempotent: demo users and sample complaints are skipped if they already exist.

### 7. Start the application

```powershell
python app.py
```

### 8. Open in browser

[http://127.0.0.1:5000](http://127.0.0.1:5000)

---

## Demo accounts (local demonstration only)

| Role | Username | Password |
|------|----------|----------|
| Resident | `resident1` | `demo1234` |
| Staff | `staff1` | `demo1234` |
| Staff | `staff2` | `demo1234` |
| Admin | `admin1` | `demo1234` |

**Do not use these credentials in production.** They exist only for faculty demos after `seed-demo`.

---

## Automated tests

```powershell
python -m unittest discover -s tests -v
```

Tests use a **temporary SQLite file** (via `DATABASE_PATH` in each test case) and do not touch your normal `data/hostel_maintenance.db`.

## Ruff (lint and format)

```powershell
ruff check .
ruff format --check .
```

Auto-fix (optional):

```powershell
ruff check . --fix
ruff format .
```

## Health check

With the app running, visit:

[http://127.0.0.1:5000/health](http://127.0.0.1:5000/health)

Expected JSON when healthy:

```json
{
  "status": "healthy",
  "database": "connected",
  "application": "hostel-maintenance-system"
}
```

HTTP **503** is returned if the database cannot be reached.

### Logs

Application events (startup, login success/failure, complaints) are written to the console where you ran `python app.py`. Passwords are never logged.

---

## Docker

### Prerequisites

Docker Desktop running on Windows.

### Build and run

```powershell
docker compose up --build
```

Default URL: [http://localhost:5000](http://localhost:5000)

Set a strong secret (example):

```powershell
$env:SECRET_KEY="your-long-random-secret-at-least-16-chars"
docker compose up --build
```

### Initialize database in the container (first time)

```powershell
docker compose exec web python app.py init-db
docker compose exec web python app.py seed-demo
```

### Volume persistence

SQLite is stored in the Docker **named volume** `hostel_db_data` (mounted at `/data`). Recreating the container keeps data; **`docker compose down -v` deletes the volume and the database**.

### Development vs container

| Mode | Command |
|------|---------|
| Local development | `python app.py` (Flask dev server) |
| Container | Gunicorn via `wsgi:application` |

---

## Git and GitHub

```powershell
git --version
git init
git status
git add .
git commit -m "Initial hostel maintenance system"
```

Create an empty repository on GitHub, then:

```powershell
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
git push -u origin main
```

Never commit `.env`, real secrets, or local `*.db` files (see `.gitignore`).

## GitHub Actions CI

Workflow file: `.github/workflows/ci.yml`

- Triggers on push/PR to `main`
- Runs tests, Ruff lint, Ruff format check, Docker build

Pushing code **starts CI**; **deployment** to a server is a separate step (not implemented in this repo). Check the **Actions** tab on GitHub after pushing.

See also: [docs/devops-pipeline.md](docs/devops-pipeline.md)

---

## Troubleshooting (Windows / Python)

| Problem | Try |
|---------|-----|
| `python` not found | Reinstall Python with “Add to PATH”, or use `py -3.12` |
| Cannot activate venv | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Port 5000 in use | `$env:FLASK_PORT="5001"; python app.py` |
| Database locked | Close other apps using the same `.db` file |
| CSRF errors in browser | Ensure cookies enabled; restart app after `.env` changes |
| Production refuses to start | Set `SECRET_KEY` (16+ chars) when `FLASK_ENV=production` |

---

## Security limitations and production notes

This prototype is suitable for **local demos and coursework**, not public production:

- SQLite is fine for demos; production would need backups and possibly PostgreSQL.
- Set a strong `SECRET_KEY` and HTTPS with `SESSION_COOKIE_SECURE=true`.
- Demo passwords in README are intentional for teaching only.
- No rate limiting, email notifications, or file uploads.
- Authorization is enforced server-side; always keep dependencies updated.

---

## College presentation script (5–8 minutes)

1. **Introduction:** Problem of hostel maintenance tracking; Oxford Brookes **context** (disclaimer: not official).
2. **Demo resident:** Log in as `resident1`, submit a plumbing complaint.
3. **Demo admin:** Log in as `admin1`, show dashboard counts, assign complaint to `staff1`, change priority if needed.
4. **Demo staff:** Log in as `staff1`, mark *In Progress*, add note, mark *Resolved*; show history on detail page.
5. **DevOps:** Run tests or show GitHub Actions; mention Ruff and Docker image build.
6. **Operations:** Open `/health`; mention logs in terminal.
7. **Close:** Point to `docs/devops-pipeline.md` — CI today, deployment and monitoring as future work.

---

## CLI reference

```powershell
python app.py init-db      # Create schema
python app.py seed-demo    # Demo users and sample complaints
python app.py              # Run development server
```

## License

Academic/educational use for coursework demonstration.
