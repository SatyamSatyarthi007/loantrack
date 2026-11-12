# LoanTrack: Three-Tier Production Microservice Architecture

[![Architecture: 3-Tier](https://img.shields.io/badge/Architecture-3--Tier-blue.svg)](#architecture)
[![Kubernetes: Minikube](https://img.shields.io/badge/Orchestration-Kubernetes%20%2F%20Minikube-326CE5.svg)](#kubernetes-deployment)
[![Docker Compose: v2](https://img.shields.io/badge/Local-Docker%20Compose-2496ED.svg)](#docker-compose-quickstart)
[![Security: Non--Root](https://img.shields.io/badge/Security-Non--Root%20Containers-green.svg)](#security--hardening)
[![Zero Downtime](https://img.shields.io/badge/Rolling%20Update-Zero%20Downtime-brightgreen.svg)](#sre-hardening--design-decisions)

LoanTrack is a production-hardened, three-tier microservice application designed to track commercial loan originations and risk decisions. It packages a static frontend reverse-proxied through unprivileged Nginx, a high-throughput Python 3.12 Flask WSGI backend, and a dedicated PostgreSQL 16 database. 

The system runs seamlessly under both **Docker Compose** for local development and **Minikube (Kubernetes)** with declarative, zero-downtime rolling updates, persistent volume claim binding, and automated preflight deployment orchestration.

---

## Architecture

```text
                                  [ Browser / Client ]
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │       Kubernetes NodePort: 30080              │
                    │       (Docker Compose Host Port: 8080)        │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │               TIER 1: FRONTEND                │
                    │   Nginx Unprivileged 1.27-Alpine (Port 8080)   │
                    │   - Non-root UID 101                          │
                    │   - Apple-inspired Minimal Static SPA         │
                    │   - Reverse Proxy: /api/* -> http://backend/  │
                    │   - Hard Rule 1: Zero DB references or drivers│
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │               TIER 2: BACKEND                 │
                    │   Flask 3.0 / Gunicorn WSGI (Port 8000)       │
                    │   - Non-root UID 10001 (python:3.12-slim)     │
                    │   - Connection Pool: psycopg[pool] (2-10 conns)│
                    │   - Startup retry with exponential backoff    │
                    │   - Downward API: Injected Pod HOSTNAME       │
                    │   - Endpoints:                                │
                    │     • GET /healthz (Process Liveness, no DB)  │
                    │     • GET /readyz  (Traffic Readiness, DB)    │
                    │     • GET /loans, POST /loans                 │
                    └───────────────────────┬───────────────────────┘
                                            │
                                            ▼
                    ┌───────────────────────────────────────────────┐
                    │               TIER 3: DATABASE                │
                    │   PostgreSQL 16-Alpine (Port 5432)            │
                    │   - Non-root UID 70 (postgres)                │
                    │   - Schema & Seed: /docker-entrypoint-initdb.d│
                    │   - Kubernetes: StatefulSet (db-0)            │
                    │   - Storage: 1Gi PVC (volumeClaimTemplates)   │
                    │   - Isolated Subpath: PGDATA=/.../data/pgdata │
                    └───────────────────────────────────────────────┘
```

---

## Component Overview

| Tier | Component | Technology | Role & Security Isolation |
| :--- | :--- | :--- | :--- |
| **Tier 1** | **Frontend** | `nginxinc/nginx-unprivileged:1.27-alpine` | Serves Apple-styled HTML5/CSS/JS frontend; acts as API reverse proxy (`/api/` $\to$ `http://backend:8000/`). Runs as unprivileged UID `101`. Holds **zero** database drivers, connection strings, or credentials (**Hard Rule 1**). |
| **Tier 2** | **Backend** | `python:3.12-slim` + Flask + Gunicorn | WSGI app running 2 pre-fork worker processes. Employs process-local connection pooling via `psycopg[pool]`, resilient startup exponential retry backoff, and probes (`/healthz` vs `/readyz`). Runs as system user `appuser` (UID `10001`). Size: 225 MB. |
| **Tier 3** | **Database** | `postgres:16-alpine` | Relational storage for loans. Initialized via SQL migration (`001_create_loans.sql`) and seed dataset (`002_seed_loans.sql`). StatefulSet binds dedicated 1Gi PersistentVolumeClaim to isolate data from pod churn. |

---

## Hard Rules Enforcement

1. **Hard Rule 1: Frontend Never Touches Database**:
   - The frontend container image contains **no** PostgreSQL client libraries, Python dependencies, database drivers, or connection credentials.
   - All browser requests target relative URI `/api/loans`. Nginx proxies requests internally to `http://backend:8000/`.
   - Verified via static code analysis:
     ```bash
     git grep -in "postgres\|password\|5432" frontend/  # Yields 0 matches
     ```
2. **Hard Rule 2: No Credentials in Code or Images**:
   - Credentials are injected strictly via environment variables.
   - Local: loaded from git-ignored `.env` (template committed as `.env.example`).
   - Cluster: generated dynamically into Kubernetes Secret `db-credentials` via client-side dry-run apply (`--dry-run=client -o yaml | kubectl apply -f -`).
   - Git repository history is clean: `git log --all --full-history -- .env` yields 0 commits.

---

## Prerequisites

- **Docker Desktop** (version 24.0+ / 29.6+) with WSL2 / Linux container engine
- **Minikube** (version 1.32+)
- **Kubectl** (version 1.28+)
- **Git** & **Bash** (GNU Bash 4.4+ or Git Bash on Windows)
- *(Optional)* **GNU Make** (version 4.0+)

---

## Quickstart: Docker Compose (Local Dev)

Start the entire three-tier stack locally in detached mode:

```bash
# 1. Copy sample environment file (if not already present)
cp .env.example .env

# 2. Launch stack via Docker Compose
docker compose up -d

# 3. Inspect container status
docker compose ps

# 4. View logs
docker compose logs -f backend
```

- **Frontend UI**: [http://localhost:8080](http://localhost:8080)
- **API Liveness Probe**: [http://localhost:8080/api/healthz](http://localhost:8080/api/healthz)
- **API Readiness Probe**: [http://localhost:8080/api/readyz](http://localhost:8080/api/readyz)
- **Loans Endpoint**: [http://localhost:8080/api/loans](http://localhost:8080/api/loans)

**Teardown**:
```bash
docker compose down          # Preserves named pgdata volume
docker compose down -v       # Removes containers AND deletes database volume
```

---

## Kubernetes Deployment (Minikube)

The deployment is completely automated and idempotent via `scripts/deploy.sh` and root `Makefile`.

### Automated One-Step Deploy

```bash
# Deploy full application stack to Minikube
make deploy

# Or directly via bash:
bash scripts/deploy.sh
```

### What `deploy.sh` Automates
1. **Preflight Check**: Verifies Minikube is running; starts it with `--driver=docker` if stopped.
2. **Container Packaging**: Compiles multi-stage container images and loads them directly into Minikube's container store.
3. **Declarative Secret & Config Provisioning**: Generates Kubernetes Secret `db-credentials` and ConfigMap `db-init` via client-side dry run without writing sensitive plain text to disk.
4. **Dependency-Ordered Rollouts**: Applies manifests in sequence (`namespace` $\to$ `config` $\to$ `postgres` $\to$ `backend` $\to$ `frontend`) and gates execution with `kubectl rollout status` waits between tiers.
5. **Idempotency**: Running `make deploy` repeatedly produces zero errors and leaves unchanged resources intact.

### Accessing the Application on Minikube

Because Minikube uses the Docker driver, NodePort services are exposed via Minikube's service bridge:

```bash
# Launch service tunnel in terminal
minikube service frontend -n loantrack --url
```
Open the printed URL (e.g., `http://127.0.0.1:50876`) in any web browser.

---

## API Reference

### 1. Liveness Probe (`GET /healthz`)
Verifies process responsiveness. **Never queries the database.**
- **Path**: `GET /api/healthz`
- **Response**: `200 OK`
```json
{
  "status": "ok"
}
```

### 2. Readiness Probe (`GET /readyz`)
Verifies end-to-end database connectivity via `SELECT 1` with a 2.0s timeout.
- **Path**: `GET /api/readyz`
- **Response (DB Healthy)**: `200 OK`
```json
{
  "status": "ready"
}
```
- **Response (DB Down / Unreachable)**: `503 Service Unavailable`
```json
{
  "error": "database unreachable",
  "status": "unhealthy"
}
```

### 3. List Loans (`GET /loans`)
Retrieves all loan applications, metadata, and the serving pod identity.
- **Path**: `GET /api/loans`
- **Response**: `200 OK`
```json
{
  "loans": [
    {
      "id": 1,
      "borrower_name": "Alice Johnson",
      "loan_amount": 350000.00,
      "property_city": "Seattle",
      "status": "APPROVED",
      "created_at": "2026-11-06T20:58:33.577120+00:00"
    }
  ],
  "served_by": "backend-6ddd66467-fltw4",
  "version": "v1"
}
```

### 4. Originate Loan (`POST /loans`)
Creates a new loan record in the database.
- **Path**: `POST /api/loans`
- **Headers**: `Content-Type: application/json`
- **Request Body**:
```json
{
  "borrower_name": "Grace Hopper",
  "loan_amount": 750000.00,
  "property_city": "New York",
  "status": "APPROVED"
}
```
- **Response**: `201 Created`
```json
{
  "loan": {
    "id": 7,
    "borrower_name": "Grace Hopper",
    "loan_amount": 750000.00,
    "property_city": "New York",
    "status": "APPROVED",
    "created_at": "2026-11-12T04:47:30.422011+00:00"
  },
  "served_by": "backend-6ddd66467-fltw4",
  "version": "v1"
}
```

---

## SRE Hardening & Design Decisions

### 1. Liveness vs. Readiness Probe Decoupling
- **The Pitfall**: Tying `/healthz` (liveness) to the database causes Kubelet to restart every backend pod when PostgreSQL undergoes maintenance or hits connection spikes. This leads to a cascading crash-loop across the entire cluster.
- **The Design**: `/healthz` only checks that the Python process and Gunicorn WSGI workers are responding. `/readyz` queries the database (`SELECT 1`). If the database is down, `/readyz` returns HTTP 503, which prompts Kubernetes to stop routing traffic to backend pods without killing them. When PostgreSQL recovers, readiness probes succeed and traffic resumes immediately.

### 2. PreStop Lifecycle Hook for Zero-Downtime Rolling Updates
- **The Pitfall**: During rolling deployments, Kubelet sends `SIGTERM` to the container concurrently with EndpointSlice/kube-proxy iptables rule teardown. If Gunicorn terminates immediately, in-flight or newly routed packets hit a closed socket, resulting in transient `502 Bad Gateway` errors.
- **The Design**: Configured `lifecycle.preStop.exec.command: ["/bin/sh", "-c", "sleep 5"]` in `k8s/30-backend.yaml`. This 5-second buffer allows kube-proxy to drain traffic and dereference the pod IP before the process stops listening. Verified under continuous load with **zero failed requests** across 70 consecutive HTTP queries.

### 3. StatefulSet with `volumeClaimTemplates` for PostgreSQL
- **The Pitfall**: Deployments with hostPath mounts tie database storage to an ephemeral node location and risk split-brain or data loss when rescheduled.
- **The Design**: A Kubernetes `StatefulSet` provides a stable network identity (`db-0`) and binds a dedicated PersistentVolumeClaim (`loantrack-pgdata-db-0`). When `db-0` is deleted or restarted, the PVC is preserved and re-attached.
- **PGDATA Subpath Configuration**: Ext4 filesystems generate a `lost+found` directory at root mounts, which triggers `initdb: directory exists but is not empty`. Pointing `PGDATA=/var/lib/postgresql/data/pgdata` avoids this failure mode.

### 4. Non-Root Security Hardening
- **Backend**: Container runs as dedicated system user `appuser` (numeric UID `10001`). Enforced via `runAsNonRoot: true` in deployment securityContext.
- **Frontend**: Built from official `nginxinc/nginx-unprivileged` running as UID `101`, listening on non-privileged port `8080`.

### 5. Multi-Stage Docker Builds
- **Backend**: Stage 1 installs dependencies into a virtual environment (`/opt/venv`). Stage 2 copies the virtualenv without build tools or compilers. Final image size is **225 MB** (well under the 300 MB limit).
- **Layer Caching**: `requirements.txt` is copied and cached before application code, ensuring pip install layers are reused when only code changes.

---

## Repository Structure

```text
loantrack/
├── Makefile                     # Root developer automation Makefile
├── README.md                    # Project documentation
├── BRANCHING.md                 # GitFlow topology and branching standards
├── EVIDENCE.md                  # Verbatim terminal logs & verification evidence
├── ISSUES.md                    # Real-world debugging issues & resolutions log
├── AI_USAGE.md                  # Pair-engineering AI collaboration audit log
├── docker-compose.yml           # Local multi-container Docker Compose stack
├── .env.example                 # Environment variables configuration template
├── .gitignore                   # Security-hardened git tracking ignore list
├── backend/
│   ├── app.py                   # Flask backend with psycopg pool and probes
│   ├── test_app.py              # Unit tests for healthz, readyz, and loans
│   ├── requirements.txt         # Pinned Python dependencies
│   ├── Dockerfile               # Multi-stage build (python:3.12-slim, UID 10001)
│   └── .dockerignore            # Build context exclusions
├── frontend/
│   ├── index.html               # Apple-styled minimal SPA UI
│   ├── nginx.conf               # Reverse proxy routing /api/ to backend:8000
│   ├── Dockerfile               # Multi-stage unprivileged Nginx build
│   └── .dockerignore            # Build context exclusions
├── db/
│   ├── migrations/
│   │   └── 001_create_loans.sql # Schema definition (loans table & indexes)
│   └── seed/
│       └── 002_seed_loans.sql   # Seed dataset (6 commercial loan records)
├── k8s/
│   ├── 00-namespace.yaml        # Namespace definition (loantrack)
│   ├── 10-configmap.yaml        # Non-sensitive configuration parameters
│   ├── 11-secret.example.yaml   # Template for database credentials Secret
│   ├── 20-postgres.yaml         # PostgreSQL StatefulSet & ClusterIP Service
│   ├── 30-backend.yaml          # Backend Deployment & ClusterIP Service
│   └── 40-frontend.yaml         # Frontend Deployment & NodePort Service
├── scripts/
│   └── deploy.sh                # Automated, idempotent deployment script
└── notes/                       # Running development logs
    ├── issues.md                # Running log of issues hit during development
    └── ai-usage.md              # Running log of AI pair-engineering decisions
```

---

## Verification & Documentation Index

- **[EVIDENCE.md](file:///C:/Users/satyam/Desktop/loantrack/EVIDENCE.md)**: Real terminal transcripts covering Part B (Docker Compose), Part C (Kubernetes Deployment), Part D (Day-2 Operations: DNS, Scaling, Rolling Update, Rollback, Pod Deletion & Persistence), and Part E (Idempotent Deployment Pipeline).
- **[ISSUES.md](file:///C:/Users/satyam/Desktop/loantrack/ISSUES.md)**: Detailed post-mortem reports for the 5 real issues encountered during development.
- **[BRANCHING.md](file:///C:/Users/satyam/Desktop/loantrack/BRANCHING.md)**: GitFlow-lite branch topology, atomic commit standards, and team scaling recommendations.
- **[AI_USAGE.md](file:///C:/Users/satyam/Desktop/loantrack/AI_USAGE.md)**: Transparent collaboration log detailing AI generation, human engineering review, and corrections.
