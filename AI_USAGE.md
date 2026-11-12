# AI Usage & Pair-Engineering Collaboration Log

## Overview & Philosophy

This project was built following a disciplined **Human-in-the-Loop Pair-Engineering Model**. The human engineer directed all architectural decisions, enforced rigorous SRE constraints, verified every command on the live terminal, executed all Git pushes, reviewed every Pull Request, and executed all merges. The AI assistant (Antigravity) served as an accelerator for drafting boilerplate, configuring manifests, conducting live forensic analysis, and formatting documentation.

---

## Collaboration Breakdown by Phase

### Phase 0: Repository Setup & GitFlow Topology (`feature/setup`)
- **AI Contributions**:
  - Drafted comprehensive `.gitignore` explicitly blocking `.env`, `*.env`, `k8s/11-secret.yaml`, build artifacts, and virtual environments.
  - Generated `.env.example` with dummy values for database connectivity.
  - Initialized directory structure skeleton and `BRANCHING.md`.
- **Human Review & Modifications**:
  - Enforced that repository began at an unborn HEAD and branched cleanly to `feature/setup` so neither `main` nor `develop` ever received direct commits.
  - Confirmed staging hygiene: ensured `.env` is never staged or committed.

### Phase 1: Application Logic & Database Layer (`feature/app`)
- **AI Contributions**:
  - Wrote SQL migration (`001_create_loans.sql`) and seed data (`002_seed_loans.sql`).
  - Drafted Flask backend (`backend/app.py`) with Gunicorn WSGI and `psycopg[binary,pool]` connection pooling.
  - Created Nginx reverse proxy configuration (`frontend/nginx.conf`) routing `/api/` to `http://backend:8000/`.
  - Designed Apple-inspired minimal SPA (`frontend/index.html`).
- **Human Review & Modifications**:
  - **Connection Pool Safety**: Enforced lazy connection pool initialization per Gunicorn worker process to prevent shared socket file descriptor corruption across pre-fork worker forks.
  - **Hard Rule 1 Gate**: Ran `git grep -in "postgres\|password\|5432" frontend/` to mathematically prove zero database references or credentials exist in the frontend tier.

### Phase 2: Docker Multi-Stage Packaging & Compose (`feature/docker`)
- **AI Contributions**:
  - Generated multi-stage Dockerfiles for backend (`python:3.12-slim`, non-root UID `10001`, size 225 MB) and frontend (`nginxinc/nginx-unprivileged:1.27-alpine`, UID `101`, size 73.7 MB).
  - Drafted `docker-compose.yml` with health checks, `service_healthy` dependency constraints, and named volume persistence.
- **Human Review & Modifications**:
  - **Issue 1 Investigation**: Caught `HTTP 502 Bad Gateway` in Nginx after restarting backend container out of order. Identified Docker IPAM DNS caching in Nginx. Logged forensic root cause and fix into `notes/issues.md`.
  - Validated that stopping `db` caused `/readyz` to return HTTP 503 while `/healthz` remained HTTP 200.

### Phase 3: Kubernetes Architecture on Minikube (`feature/k8s`)
- **AI Contributions**:
  - Drafted Kubernetes manifests in `k8s/`: `00-namespace.yaml`, `10-configmap.yaml`, `11-secret.example.yaml`, `20-postgres.yaml`, `30-backend.yaml`, `40-frontend.yaml`.
  - Configured resource requests/limits, Downward API `HOSTNAME` injection, and rolling update strategy.
- **Human Review & Modifications**:
  - **Issue 2 Investigation**: Hit `SSH_AGENT_START: starting an SSH agent on Windows is not yet supported` when executing `minikube docker-env`. Human engineer and AI pivoted to `minikube image build` / `load` directly into Minikube's containerd image store.
  - Verified multi-pod load balancing across replicas via terminal loop (`fln5p` and `w4ksn`).

### Phase 4: Day-2 Kubernetes Operations (`feature/k8s-ops`)
- **AI Contributions**:
  - Formulated validation commands for CoreDNS name resolution (short name and FQDN).
  - Executed horizontal scaling test (3 replicas) and captured load distribution across all 3 pods.
- **Human Review & Modifications**:
  - **Issue 3 Investigation**: Discovered `minikube image build` lacks `--build-arg` support on Windows CLI. Built `loantrack-backend:v2` with local Docker daemon and transferred via `minikube image load`.
  - **Issue 4 (Critical SRE Discovery)**: Under continuous polling during rolling update, observed two transient `502 Bad Gateway` errors due to a race condition between Kubelet `SIGTERM` and kube-proxy iptables teardown. Introduced `lifecycle.preStop.exec.command: ["/bin/sh", "-c", "sleep 5"]` in `k8s/30-backend.yaml`. Re-tested rollout and rollback under load $\to$ **100% zero downtime (0 failed requests across 70 queries)**.
  - Verified StatefulSet persistence: originated loan #7, deleted pod `db-0`, verified all data intact upon restart.

### Phase 5: Automated Deployment Script & Makefile (`feature/deploy-script`)
- **AI Contributions**:
  - Created `scripts/deploy.sh` with strict bash safety (`set -euo pipefail`), preflight checks, image compilation, and ordered rollout status gates.
  - Implemented client-side dry-run Secret and ConfigMap creation (`--dry-run=client -o yaml | kubectl apply -f -`) for declarative idempotency without storing secrets in git.
  - Created root `Makefile` with self-documenting targets.
- **Human Review & Modifications**:
  - **Issue 5 Investigation**: Resolved Windows CRLF line ending warnings in shell scripts by normalizing encodings to pure LF and registering `--chmod=+x` in Git index.
  - Tested cold-start deployment from deleted namespace (`kubectl delete namespace loantrack`) followed by immediate secondary pass to verify complete idempotency.

### Phase 6: Documentation & Hardening (`feature/docs`)
- **AI Contributions**:
  - Compiled comprehensive `README.md` with ASCII architecture diagrams, API specifications, and SRE design justifications.
  - Structured `ISSUES.md` and `AI_USAGE.md` consolidating all historical evidence.
- **Human Review & Modifications**:
  - Verified all markdown links, code blocks, and diagrams against the live codebase.
  - Confirmed Git history contains zero credential leaks and follows atomic commit standards.

---

## AI Collaboration Matrix

| Deliverable | AI Responsibility | Human Review & Intervention |
| :--- | :--- | :--- |
| **Database Migrations** | Schema draft & seed rows | Verified foreign key, data types, and status constraints |
| **Flask Backend** | API routes & connection pool scaffolding | Verified lazy worker initialization & liveness/readiness decoupling |
| **Frontend SPA** | Apple-style CSS & Fetch API logic | Verified complete isolation from database credentials/drivers (Hard Rule 1) |
| **Docker Packaging** | Multi-stage Dockerfiles & Compose spec | Verified non-root UIDs, layer caching, and image size (< 300 MB) |
| **Kubernetes YAMLs** | Manifest creation (Deployments, StatefulSet) | Verified probe settings, resource limits, and added `preStop` hook |
| **Deployment Automation**| Shell script & Makefile generation | Verified cold-start recovery, idempotency, and LF line ending normalization |
| **Incident Logging** | Formatting issue post-mortems | Verified verbatim error messages and forensic command traces |
