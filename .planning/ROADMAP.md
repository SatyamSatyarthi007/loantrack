# Project Roadmap: LoanTrack (SRE / DevOps Intern Take-Home)

## Project Overview
LoanTrack is a production-grade three-tier web application (Nginx static frontend -> Flask backend -> PostgreSQL database) packaged with Docker and deployed to Minikube Kubernetes.

## Phase Plan

### Phase 0: Repository Setup & Hygiene (`feature/setup`) [IN PROGRESS]
- [x] Configure `.gitignore` to prevent credential and cache leakage
- [x] Create `.env.example` defining environment variables
- [x] Establish directory skeleton (`backend/`, `frontend/`, `db/migrations/`, `db/seed/`, `k8s/`, `scripts/`, `notes/`)
- [x] Document branching policy in `BRANCHING.md`
- [x] Initialize running logs (`notes/issues.md`, `notes/ai-usage.md`)

### Phase 1: Core Application Implementation (`feature/app`)
- Database migrations & seeds:
  - `db/migrations/001_create_loans.sql` (schema: id, borrower_name, amount, interest_rate, status, created_at)
  - `db/seed/002_seed_loans.sql` (6 initial loans for testing)
- Backend (Flask + Gunicorn + Psycopg):
  - Connection pooling with `psycopg_pool.ConnectionPool`
  - Startup exponential backoff retry logic (logs attempts, never crashes)
  - Endpoints: `GET /healthz` (liveness, no DB), `GET /readyz` (readiness, `SELECT 1`, 503 on failure), `GET /loans`, `POST /loans`
  - Include metadata in responses: `served_by` (HOSTNAME) and `version` (APP_VERSION)
  - Self-contained test script (`backend/test_app.py`) for verification
- Frontend:
  - Clean, minimal UI (`frontend/index.html`) using Apple-inspired restraint
  - Interacts exclusively with `/api/loans` (never talks directly to DB or holds DB credentials)

### Phase 2: Docker Packaging & Compose Orchestration (`feature/docker`)
- Packaging:
  - Multi-stage Dockerfiles (`backend/Dockerfile`, `frontend/Dockerfile`)
  - Pinned base images (`python:3.12-slim`, `nginxinc/nginx-unprivileged:1.27-alpine`, `postgres:16-alpine`)
  - Numeric non-root USER execution
  - Backend image size optimization (< 300 MB target)
  - Explicit `.dockerignore` for each tier
  - Native container HEALTHCHECK on backend
- Local Compose (`docker-compose.yml`):
  - Single user-defined bridge network
  - Named persistent volume `pgdata`
  - Environment variable injection via `.env` (git-ignored)
  - Database healthcheck and `depends_on: { db: { condition: service_healthy } }`
  - Nginx reverse proxy configuration (`frontend/nginx.conf`) routing `/api/` to `http://backend:8000/`
- Verification & Milestone Tag:
  - Test startup, health endpoints, data persistence across container recreation
  - Capture real terminal output into `EVIDENCE.md`
  - Merge `feature/docker` -> `develop` -> `main`, tag `v1.0.0`

### Phase 3: Kubernetes Deployment (`feature/k8s`)
- Namespace: `loantrack`
- Configuration:
  - ConfigMap (`k8s/02-configmap.yaml`) for non-sensitive values
  - Secret template (`k8s/11-secret.example.yaml`) and real secret (`k8s/11-secret.yaml`, git-ignored)
- Database:
  - PostgreSQL `StatefulSet` with `volumeClaimTemplates` and `PGDATA` subpath
  - Headless/ClusterIP Service
- Application Workloads:
  - Backend `Deployment`: resource requests/limits, downward API for HOSTNAME, liveness probe (`/healthz`), readiness probe (`/readyz`), RollingUpdate strategy (maxUnavailable: 0, maxSurge: 1)
  - Frontend `Deployment`: unprivileged nginx, resource requests/limits, liveness/readiness probes, RollingUpdate strategy
  - ClusterIP Service for backend; NodePort Service (30080) for frontend
- Verification & Milestone Tag:
  - Build images in Minikube Docker environment (`eval $(minikube docker-env)`)
  - Verify rollouts, endpoint responses, probes
  - Capture real terminal output into `EVIDENCE.md`
  - Merge `feature/k8s` -> `develop` -> `main`, tag `v1.1.0`

### Phase 4: Kubernetes Day-2 Operational Scenarios (`feature/k8s-ops`)
- Execute and record Part D4 operational drills:
  - Horizontal pod scaling (simulate traffic spike)
  - Pod deletion and zero-downtime recovery
  - Database failure simulation (verify readiness probe trips to 503, liveness stays up)
  - Rolling update without downtime
  - Capture all commands and verbatim outputs into `EVIDENCE.md`

### Phase 5: Automated Deployment Scripting (`feature/deploy-script`)
- Develop idempotent `scripts/deploy.sh` and root `Makefile`
- Create Minikube environment from scratch:
  - Handle secret creation and DB init script ConfigMap creation via `--dry-run=client -o yaml | kubectl apply -f -`
  - Sequential ordered rollout and wait logic (`kubectl rollout status`)
  - Test from clean slate (`minikube delete`) and test re-run idempotency

### Phase 6: Comprehensive Documentation (`feature/docs`)
- Finalize `README.md` (architecture, setup, runbook, design decisions)
- Finalize `BRANCHING.md`
- Compile complete `EVIDENCE.md` with verified command outputs
- Complete `ISSUES.md` from running notes
- Finalize `AI_USAGE.md` documenting human/AI pairing

### Phase 7: Final Audit & Delivery
- Clean clone test in temporary directory
- Comprehensive git secret audit (`git log -p`, truffleHog/regex check)
- Tag and branch structure verification
