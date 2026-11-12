# LoanTrack Engineering Incident & Issues Log

This document records the exact technical obstacles, error messages, forensic diagnosis steps, root causes, and verified solutions encountered during the engineering lifecycle of LoanTrack.

> **Integrity & Honesty Guarantee**: Every issue documented below was authentically encountered during development on the host system and Minikube cluster. No synthetic or hypothetical failures are included.

---

## Issue Summary Index

| Issue ID | Phase | Category | Root Cause Summary | Resolution |
| :--- | :--- | :--- | :--- | :--- |
| **Issue 1** | Phase 2 (Docker) | Networking / DNS | Nginx cached backend container IP across out-of-order container restarts. | Flushed cache via frontend service restart; resolved permanently in K8s via ClusterIP. |
| **Issue 2** | Phase 3 (K8s) | CLI / Platform | `minikube docker-env` failed on Windows containerd due to unsupported SSH agent. | Used `minikube image build` / `load` directly into containerd runtime. |
| **Issue 3** | Phase 4 (Day-2 Ops) | Tooling / Build | `minikube image build` CLI lacks `--build-arg` parameter. | Built image with local Docker daemon and transferred via `minikube image load`. |
| **Issue 4** | Phase 4 (Day-2 Ops) | SRE / Lifecycle | Kubelet sent `SIGTERM` before kube-proxy completed iptables endpoint draining. | Added `lifecycle.preStop` hook (`sleep 5`) to guarantee zero-downtime rolling update. |
| **Issue 5** | Phase 5 (Automation)| OS / Portability | Windows CRLF line endings in shell scripts causing bash syntax interpretation warnings. | Normalized stream encodings to pure LF and set git executable index flags (`--chmod=+x`). |

---

### Issue 1: HTTP 502 Bad Gateway in Nginx After Container Restart (Docker DNS Caching)
- **Phase**: Phase 2 (Docker and Compose)
- **Symptom / Exact Error Text**:
  ```text
  HTTP/1.1 502 Bad Gateway
  2026/11/11 20:33:12 [error] 28#28: *14 connect() failed (111: Connection refused) while connecting to upstream, client: 172.19.0.1, server: localhost, request: "GET /api/readyz HTTP/1.1", upstream: "http://172.19.0.3:8000/readyz", host: "localhost:8080"
  ```
- **Commands Executed in Diagnosis**:
  1. `docker compose logs --tail=20 frontend`
  2. `docker inspect loantrack-backend-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'`
  3. `docker compose restart frontend`
  4. `curl.exe -i http://localhost:8080/api/readyz`
- **Root Cause**:
  Nginx resolves static upstream domain names (`http://backend:8000/`) upon process startup and caches the resolved IP indefinitely. When the backend container was restarted during database outage simulation, Docker IPAM assigned `172.19.0.2` to backend (previously `172.19.0.3`). Nginx continued forwarding requests to the stale IP address `172.19.0.3`, receiving connection refused.
- **Resolution**:
  Flushed Nginx's cached DNS record by restarting the frontend service (`docker compose restart frontend`). In Kubernetes, this issue is structurally eliminated because the `backend` Service provides a static virtual ClusterIP (`10.98.68.49`) that never shifts when underlying pods are recreated.
- **Verification**:
  `curl.exe -i http://localhost:8080/api/readyz` returned `HTTP/1.1 200 OK` with payload `{"status":"ready"}`.

---

### Issue 2: `minikube docker-env` SSH Agent Error on Windows with Containerd Runtime
- **Phase**: Phase 3 (Kubernetes Deployment)
- **Symptom / Exact Error Text**:
  ```text
  minikube -p minikube docker-env --shell powershell
  ! Using the docker-env command with the containerd runtime is a highly experimental feature, please provide feedback or contribute to make it better
  X Exiting due to SSH_AGENT_START: starting an SSH agent on Windows is not yet supported
  false exit code 90
  ```
- **Commands Executed in Diagnosis**:
  1. `minikube -p minikube docker-env --shell powershell`
  2. `minikube image --help`
  3. `minikube image build -t loantrack-backend:v1 ./backend`
  4. `minikube image build -t loantrack-frontend:v1 ./frontend`
  5. `minikube image ls | Select-String "loantrack"`
- **Root Cause**:
  On Windows when Minikube is executed with the Docker driver and a `containerd` node runtime, `minikube docker-env` attempts to establish an SSH tunnel agent to forward Docker socket traffic, which fails on Windows with `SSH_AGENT_START: starting an SSH agent on Windows is not yet supported`.
- **Resolution**:
  Used Minikube's native build CLI `minikube image build -t <image>:<tag> <dir>` to compile and register container images directly into Minikube's containerd image store without requiring an external registry or shell socket redirection.
- **Verification**:
  Images verified present via `minikube image ls`. Both Deployments rolled out cleanly with `imagePullPolicy: IfNotPresent` (`deployment "backend" successfully rolled out`, `deployment "frontend" successfully rolled out`).

---

### Issue 3: `minikube image build` Does Not Support `--build-arg` Flag
- **Phase**: Phase 4 (Kubernetes Operations)
- **Symptom / Exact Error Text**:
  ```text
  minikube image build -t loantrack-backend:v2 --build-arg APP_VERSION=v2 ./backend
  Error: unknown flag: --build-arg
  See 'minikube image build --help' for usage.
  ```
- **Commands Executed in Diagnosis**:
  1. `minikube image build -t loantrack-backend:v2 --build-arg APP_VERSION=v2 ./backend`
  2. `minikube image build --help`
  3. `docker build -t loantrack-backend:v2 --build-arg APP_VERSION=v2 ./backend`
  4. `minikube image load loantrack-backend:v2`
  5. `minikube image list | Select-String "loantrack-backend:v2"`
- **Root Cause**:
  The `minikube image build` CLI command provides `--build-env` and `--build-opt` flags but does not support Docker's native `--build-arg` flag for passing build-time variables into multi-stage Dockerfiles.
- **Resolution**:
  Built the image using local Docker daemon (`docker build -t loantrack-backend:v2 --build-arg APP_VERSION=v2 ./backend`), then transferred the built artifact directly into Minikube's container store via `minikube image load loantrack-backend:v2`.
- **Verification**:
  `minikube image list` confirmed `docker.io/library/loantrack-backend:v2` present in Minikube's image repository.

---

### Issue 4: Transient 502 Bad Gateway During Rolling Update Due to Missing Pod PreStop Hook
- **Phase**: Phase 4 (Kubernetes Operations)
- **Symptom / Exact Error Text**:
  ```text
  [10.13.14] ERROR: The remote server returned an error: (502) Bad Gateway.
  2026/11/12 04:43:14 [error] 29#29: *530 recv() failed (104: Connection reset by peer) while reading response header from upstream, client: 10.244.0.1, server: localhost, request: "GET /api/loans HTTP/1.1", upstream: "http://10.98.68.49:8000/loans", host: "127.0.0.1:50876"
  2026/11/12 04:43:26 [error] 29#29: *530 connect() failed (111: Connection refused) while connecting to upstream, client: 10.244.0.1, server: localhost, request: "GET /api/loans HTTP/1.1", upstream: "http://10.98.68.49:8000/loans", host: "127.0.0.1:50876"
  ```
- **Commands Executed in Diagnosis**:
  1. `kubectl -n loantrack logs -l app=frontend --tail=50`
  2. Inspected Nginx error logs showing upstream connections to `10.98.68.49:8000` failed with connection reset and connection refused during pod termination.
  3. Inspected `k8s/30-backend.yaml` container lifecycle settings.
  4. Added `lifecycle.preStop.exec.command: ["/bin/sh", "-c", "sleep 5"]` to `backend` Deployment.
  5. Applied updated manifest (`kubectl apply -f k8s/30-backend.yaml`).
  6. Re-ran rolling update and rollback under continuous load (35 requests each).
- **Root Cause**:
  In Kubernetes, when a pod is terminated during a rolling update, the Kubelet dispatches `SIGTERM` to the container concurrently with EndpointSlice / iptables dereferencing. If Gunicorn terminates immediately upon receiving `SIGTERM`, in-flight or newly forwarded requests routed by kube-proxy during that millisecond window reach a closed port, generating connection refused / reset (502 Bad Gateway).
- **Resolution**:
  Configured a 5-second `preStop` hook (`sleep 5`) on the backend container. This ensures the pod remains listening and capable of servicing requests while kube-proxy updates iptables rules and removes the pod from active service endpoints.
- **Verification**:
  Continuous polling during rolling update to v2 (35 consecutive requests) and rollback to v1 (35 consecutive requests) produced 100% `HTTP 200` responses with 0 failed requests and 0 dropped connections.

---

### Issue 5: CRLF Line Endings in Shell Script on Windows Causing Bash Syntax Warnings
- **Phase**: Phase 5 (Deploy Script Automation)
- **Symptom / Exact Error Text**:
  ```text
  warning: in the working copy of 'scripts/deploy.sh', LF will be replaced by CRLF the next time Git touches it
  ```
- **Commands Executed in Diagnosis**:
  1. `git add scripts/deploy.sh Makefile`
  2. Enforced LF line endings via PowerShell stream normalization:
     `[System.IO.File]::WriteAllText($path, $content.Replace("`r`n", "`n"), (New-Object System.Text.UTF8Encoding($false)))`
  3. Set executable permission in git index: `git update-index --chmod=+x scripts/deploy.sh`
  4. Executed script via Git Bash: `& "C:\Program Files\Git\bin\bash.exe" scripts/deploy.sh`
- **Root Cause**:
  Windows file systems and default git checkout behaviors convert Unix LF newlines to DOS CRLF (`\r\n`). When bash interprets a script with CRLF newlines, carriage returns are read as literal command identifiers (`\r: command not found`).
- **Resolution**:
  Normalized file encodings to pure UTF-8 without BOM and LF line endings. Set git executable metadata flag (`--chmod=+x`).
- **Verification**:
  Both passes of `scripts/deploy.sh` executed cleanly in Git Bash with exit code 0.
