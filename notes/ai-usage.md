# Running AI Usage Log

This document records the exact pair-engineering collaboration between the human engineer and the AI assistant, tracking generated assets, reviews, modifications, and any corrections made during execution.

## Phase 0: Setup (`feature/setup`)
- **Generated**:
  - Initial `.gitignore` (preventing `.env`, build files, OS files, Python caches from git tracking)
  - `.env.example` template with dummy database and backend configuration
  - Directory skeleton (`backend/`, `frontend/`, `db/migrations/`, `db/seed/`, `k8s/`, `scripts/`, `notes/`, `.planning/`)
  - `BRANCHING.md` documenting branch lifecycle, atomic commit rules, and release gates
  - `.planning/ROADMAP.md` defining phase-by-phase execution plan
  - Running tracking documents (`notes/issues.md`, `notes/ai-usage.md`)
- **Accepted as-is**:
  - Initial skeleton layout and `.gitignore` safety patterns
  - Atomic commit sequence on `feature/setup`
- **Modifications / Decisions**:
  - Confirmed repository started at unborn HEAD; cleanly branched to `feature/setup` so neither `main` nor `develop` received direct commits.

## Phase 1: Application & Database (`feature/app`)
- **Generated**:
  - `db/migrations/001_create_loans.sql` (loans schema with id, borrower_name, loan_amount, property_city, status, created_at)
  - `db/seed/002_seed_loans.sql` (6 seed loans with varied cities and statuses: APPROVED, PENDING, REJECTED)
  - `backend/requirements.txt` (Flask, gunicorn, psycopg[binary,pool])
  - `backend/app.py` (lazy process-local connection pool, startup exponential backoff retry logging attempts without crashing, GET /healthz, GET /readyz, GET /loans, POST /loans, metadata served_by and version)
  - `frontend/nginx.conf` (reverse proxy on unprivileged port 8080 routing /api/ to backend:8000)
  - `frontend/index.html` (minimal Apple-inspired UI, system font stack, tabular-nums amounts, status pills, /api/loans fetch and POST, zero DB references)
- **Accepted as-is**:
  - Architectural separation of liveness probe (never touches DB) vs readiness probe (checks DB)
  - Grep verification proving zero DB drivers, connection strings, or credentials in frontend/ (Hard Rule 1 verified)
- **Modifications / Decisions**:
  - Connection pool initialized lazily per gunicorn worker process to prevent shared socket file descriptor corruption across pre-fork workers.

## Phase 2: Docker Packaging & Compose Orchestration (`feature/docker`)
- **Generated**:
  - `backend/Dockerfile` (multi-stage build, pinned `python:3.12-slim`, non-root USER 10001, layer cache separation, stdlib HEALTHCHECK, 225 MB image size)
  - `frontend/Dockerfile` (multi-stage minimal asset staging, pinned `nginxinc/nginx-unprivileged:1.27-alpine` on 8080)
  - `backend/.dockerignore` and `frontend/.dockerignore` (excluding git, env, caches, local tests)
  - `docker-compose.yml` (single network `loantrack-net`, named volume `loantrack-pgdata`, db healthcheck, `depends_on: { db: { condition: service_healthy } }`, individual file mounts into `/docker-entrypoint-initdb.d/`)
  - `EVIDENCE.md` compiling real command outputs for Part B
- **Accepted as-is**:
  - Docker Compose service dependency ordering and named volume isolation
- **Modifications / Decisions**:
  - Resolved and documented Nginx upstream DNS caching issue (Issue 1) when containers restart out of order. Logged root cause and fix in `notes/issues.md`.
