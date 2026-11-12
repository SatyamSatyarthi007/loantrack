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

## Phase 3: Kubernetes Deployment on Minikube (`feature/k8s`)
- **Generated**:
  - `k8s/00-namespace.yaml` (`loantrack` namespace with standard labels)
  - `k8s/10-configmap.yaml` (non-sensitive parameters: `DB_HOST`, `DB_PORT`, `POSTGRES_DB`, `APP_VERSION`)
  - `k8s/11-secret.example.yaml` (template with dummy credentials)
  - `k8s/20-postgres.yaml` (StatefulSet + ClusterIP service, 1Gi volumeClaimTemplates, `PGDATA` subpath, `pg_isready` probes, resource requests/limits)
  - `k8s/30-backend.yaml` (Deployment with 2 replicas, ClusterIP service, Downward API `HOSTNAME`, liveness/readiness probes, RollingUpdate maxUnavailable: 0 / maxSurge: 1, `runAsNonRoot: true`, resource requests/limits)
  - `k8s/40-frontend.yaml` (Deployment with 2 replicas, NodePort 30080 service, RollingUpdate strategy, liveness/readiness probes, `runAsNonRoot: true`, resource requests/limits)
  - Appended Part C live Kubernetes deployment and load-balancing evidence to `EVIDENCE.md`
- **Accepted as-is**:
  - StatefulSet volume claim template and PGDATA subpath pattern
  - Downward API `metadata.name` injection pattern for pod identity verification
- **Modifications / Decisions**:
  - Encountered Windows containerd limitation with `minikube docker-env` (SSH agent failure); switched to `minikube image build` to build images directly into Minikube's image store without requiring an external container registry. Logged as Issue 2 in `notes/issues.md`.

## Phase 4: Kubernetes Operations & Day-2 Management (`feature/k8s-ops`)
- **Generated**:
  - Appended Part D operational evidence to `EVIDENCE.md`:
    - D1: CoreDNS verification (short name `db` and FQDN `db.loantrack.svc.cluster.local` resolution from backend pod).
    - D2: Horizontal scaling of backend to 3 replicas with 10-request load-balancing distribution across all 3 pods.
    - D3: Zero-downtime rolling update to `loantrack-backend:v2` and rollback to `v1` with SRE architectural analysis.
    - D4: Pod self-healing verification (backend pod deletion) and StatefulSet persistence verification (originate loan #7, delete `db-0`, verify data intact upon restart).
  - Updated `k8s/30-backend.yaml` with graceful shutdown lifecycle hook (`preStop: sleep 5`).
  - Updated `k8s/10-configmap.yaml` to decouple `APP_VERSION` from ConfigMap so versioning is immutably governed by container image tags.
- **Accepted as-is**:
  - SRE diagnostic methodology: testing under continuous load, capturing real Nginx log entries, and applying standard Kubernetes connection draining hooks.
- **Modifications / Decisions**:
  - `minikube image build` does not support `--build-arg`: Built `loantrack-backend:v2` with Docker Desktop daemon and transferred it via `minikube image load`. Documented as Issue 3 in `notes/issues.md`.
  - Discovered transient 502 Bad Gateway during rolling update due to race condition between Kubelet SIGTERM and kube-proxy iptables teardown. Introduced `lifecycle.preStop.exec.command: ["/bin/sh", "-c", "sleep 5"]` in backend deployment, achieving 100% zero downtime (0 failed requests across 35 requests during both rollout and rollback). Documented as Issue 4 in `notes/issues.md`.

## Phase 5: Deployment Script & Automation (`feature/deploy-script`)
- **Generated**:
  - `scripts/deploy.sh`:
    - Strict `set -euo pipefail` bash script automating preflight checks, image building & loading, namespace creation, declarative secret generation, and dependency-ordered manifest application.
    - Uses client-side dry-run creation (`--dry-run=client -o yaml | kubectl apply -f -`) for `db-credentials` Secret and `db-init` ConfigMap to eliminate hardcoded secret files while retaining idempotency.
    - Rollout status gates for StatefulSet and Deployments before moving to dependent tiers.
  - Root `Makefile`:
    - Self-documenting targets: `help`, `deploy`, `up`, `down`, `clean`, `test-idempotency`.
  - Appended Part E evidence to `EVIDENCE.md` capturing cold-start deployment and secondary idempotency pass.
- **Accepted as-is**:
  - Declarative dry-run piping pattern for Kubernetes Secret and ConfigMap creation.
  - Rollout status gate ordering matching service dependencies.
- **Modifications / Decisions**:
  - Script tested under cold start from zero state (`kubectl delete namespace loantrack`) to verify automated end-to-end recovery, followed by immediate second execution to prove complete idempotency. Documented CRLF newline handling as Issue 5 in `notes/issues.md`.


