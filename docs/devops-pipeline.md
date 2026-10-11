# DevOps Pipeline — Hostel Maintenance System

This document describes how **local development**, **Git**, **GitHub Actions CI**, **Docker**, and **future deployment** fit together for the academic case study *Applying DevOps Practices to a University Hostel Maintenance System* (Oxford Brookes University context).

> **Disclaimer:** This is a student prototype using sample data. It is not connected to real Oxford Brookes University systems, and no real operational metrics have been collected.

## End-to-end flow

```text
Developer writes code
    → Git commit
    → GitHub push
    → GitHub Actions (CI)
        → Install Python dependencies
        → Run unittest suite (isolated temp database)
        → Ruff lint and format checks
        → Docker image build (validation)
    → Deployment (when separately configured — not implemented here)
    → Running application (logs + GET /health)
    → Feedback and continuous improvement
```

## What is implemented locally

| Area | Implemented in this repository |
|------|--------------------------------|
| Web application | Flask monolith with HTML/CSS/JS UI |
| Database | SQLite with schema init and demo seed commands |
| Authentication | Sessions, hashed passwords, CSRF on forms |
| Logging | Python `logging` for login, complaints, errors |
| Health check | `GET /health` JSON endpoint |
| Tests | `tests/test_app.py` (unittest + Flask test client) |
| Lint/format | Ruff configuration in `pyproject.toml` |
| Container | `Dockerfile`, `docker-compose.yml` |
| CI workflow | `.github/workflows/ci.yml` |

## What CI validates on GitHub

When you push to `main` or open a pull request targeting `main`, GitHub Actions:

1. Installs dependencies from `requirements.txt` and Ruff.
2. Runs `python -m unittest discover -s tests -v` with `DATABASE_PATH` pointing to a temporary file (not your laptop database).
3. Runs `ruff check .` and `ruff format --check .`.
4. Builds the Docker image to confirm the container recipe still works.

CI does **not** deploy the app to a cloud server. Deployment is a separate manual or pipeline step you would configure later (for example, pulling the image onto a VM or university test server).

## Docker build vs runtime

- **Build:** Copies application code, installs dependencies, runs as non-root user, starts Gunicorn on port 5000.
- **Runtime:** `docker-compose.yml` mounts a **named volume** at `/data` for SQLite persistence.
- **First run:** Initialize and seed inside the container:

  ```powershell
  docker compose exec web python app.py init-db
  docker compose exec web python app.py seed-demo
  ```

Deleting the named volume (`docker compose down -v`) removes stored database files.

## Deployment (not implemented)

A full production deployment would typically add:

- Strong `SECRET_KEY` and HTTPS (`SESSION_COOKIE_SECURE=true`)
- Managed backups for SQLite or migration to a server-grade database
- Reverse proxy (nginx) and TLS certificates
- Secrets stored in GitHub Actions secrets or a vault — never in Git
- Monitoring alerts on `/health` and log aggregation

These steps are **out of scope** for the college prototype but are important for real universities.

## Feedback loop and future improvements

Even with sample data, a DevOps mindset uses feedback to prioritize work:

| Signal | How you might observe it | Possible improvement |
|--------|--------------------------|----------------------|
| Response time | Logs timestamps on complaint creation vs assignment | Auto-notify staff for Urgent priority |
| Resolution time | History in `complaint_updates` | Dashboard SLA charts for admins |
| Failed deployments | CI or deploy pipeline failures | Stricter tests, staging environment |
| Availability | Repeated `/health` checks returning 503 | Database redundancy, better alerting |
| User satisfaction | Post-resolution resident survey (future feature) | Simple rating field on close |

Discuss these as **design ideas** in your presentation — the current project demonstrates the pipeline foundation (code, tests, CI, container) rather than live operational analytics.

## Suggested demonstration narrative

1. Show the running app and role-based dashboards (sample accounts from README).
2. Submit a complaint as a resident; assign and resolve as admin/staff.
3. Show `/health` in the browser.
4. Run tests and Ruff locally (or show a green GitHub Actions run after push).
5. Explain `docs/devops-pipeline.md` and what would come next for real deployment.
