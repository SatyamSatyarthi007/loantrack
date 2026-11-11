# Running Issues Log

This log tracks real issues encountered during development, debugging, and verification across all phases.

## Format
- **ID**: Sequential issue identifier
- **Phase**: Development phase where issue occurred
- **Symptom / Exact Error Text**: Verbatim output from terminal or logs
- **Commands Executed**: Sequential commands run during investigation
- **Root Cause**: Underlying technical reason
- **Resolution**: Concrete fix applied
- **Verification**: Command and output demonstrating fix

---

### Issue 1: HTTP 502 Bad Gateway in Nginx After Container Restart (Docker DNS Caching)
- **Phase**: Phase 2 (Docker and Compose)
- **Symptom / Exact Error Text**:
  ```text
  HTTP/1.1 502 Bad Gateway
  2026/11/11 20:33:12 [error] 28#28: *14 connect() failed (111: Connection refused) while connecting to upstream, client: 172.19.0.1, server: localhost, request: "GET /api/readyz HTTP/1.1", upstream: "http://172.19.0.3:8000/readyz", host: "localhost:8080"
  ```
- **Commands Executed**:
  1. `docker compose logs --tail=20 frontend`
  2. `docker inspect loantrack-backend-1 --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'`
  3. `docker compose restart frontend`
  4. `curl.exe -i http://localhost:8080/api/readyz`
- **Root Cause**:
  Nginx resolves static upstream hostnames (`http://backend:8000/`) at process startup and caches the resolved IP indefinitely. When `backend` was restarted after stopping `db`, Docker's IPAM reassigned IP `172.19.0.2` to backend (which was previously assigned `172.19.0.3`). Nginx continued forwarding requests to the old IP `172.19.0.3`, receiving connection refused.
- **Resolution**:
  Flushed Nginx's cached IP by restarting the frontend service (`docker compose restart frontend`). Noted that in Kubernetes (Phase 3), the `backend` Service provides an immutable virtual ClusterIP that prevents DNS drift regardless of pod lifecycle.
- **Verification**:
  `curl.exe -i http://localhost:8080/api/readyz` returned `HTTP/1.1 200 OK` with `{"status":"ready"}`.

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
- **Commands Executed**:
  1. `minikube -p minikube docker-env --shell powershell`
  2. `minikube image --help`
  3. `minikube image build -t loantrack-backend:v1 ./backend`
  4. `minikube image build -t loantrack-frontend:v1 ./frontend`
  5. `minikube image ls | Select-String "loantrack"`
- **Root Cause**:
  On Windows when Minikube runs the Docker driver with a `containerd` node runtime, `minikube docker-env` requires an SSH tunnel agent to forward Docker socket traffic, which fails on Windows with `SSH_AGENT_START: starting an SSH agent on Windows is not yet supported`.
- **Resolution**:
  Used Minikube's native build CLI `minikube image build -t <image>:<tag> <dir>` to compile and register container images directly into Minikube's containerd image store without needing an external registry or socket redirection.
- **Verification**:
  Images verified present via `minikube image ls`, and both Deployments rolled out cleanly with `imagePullPolicy: IfNotPresent` (`deployment "backend" successfully rolled out`, `deployment "frontend" successfully rolled out`).
