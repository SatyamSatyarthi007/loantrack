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

---

### Issue 3: `minikube image build` Does Not Support `--build-arg` Flag
- **Phase**: Phase 4 (Kubernetes Operations)
- **Symptom / Exact Error Text**:
  ```text
  minikube image build -t loantrack-backend:v2 --build-arg APP_VERSION=v2 ./backend
  Error: unknown flag: --build-arg
  See 'minikube image build --help' for usage.
  ```
- **Commands Executed**:
  1. `minikube image build -t loantrack-backend:v2 --build-arg APP_VERSION=v2 ./backend`
  2. `minikube image build --help`
  3. `docker build -t loantrack-backend:v2 --build-arg APP_VERSION=v2 ./backend`
  4. `minikube image load loantrack-backend:v2`
  5. `minikube image list | Select-String "loantrack-backend:v2"`
- **Root Cause**:
  The `minikube image build` CLI command provides `--build-env` and `--build-opt` but does not expose the standard Docker `--build-arg` flag directly for passing build-time variables into multi-stage Dockerfiles.
- **Resolution**:
  Built the image using local Docker daemon (`docker build -t loantrack-backend:v2 --build-arg APP_VERSION=v2 ./backend`), then transferred the built artifact directly into Minikube's container store via `minikube image load loantrack-backend:v2`.
- **Verification**:
  `minikube image list` confirmed `docker.io/library/loantrack-backend:v2` present in Minikube's local repository.

---

### Issue 4: Transient 502 Bad Gateway During Rolling Update Due to Missing Pod PreStop Hook
- **Phase**: Phase 4 (Kubernetes Operations)
- **Symptom / Exact Error Text**:
  ```text
  [10.13.14] ERROR: The remote server returned an error: (502) Bad Gateway.
  2026/11/12 04:43:14 [error] 29#29: *530 recv() failed (104: Connection reset by peer) while reading response header from upstream, client: 10.244.0.1, server: localhost, request: "GET /api/loans HTTP/1.1", upstream: "http://10.98.68.49:8000/loans", host: "127.0.0.1:50876"
  2026/11/12 04:43:26 [error] 29#29: *530 connect() failed (111: Connection refused) while connecting to upstream, client: 10.244.0.1, server: localhost, request: "GET /api/loans HTTP/1.1", upstream: "http://10.98.68.49:8000/loans", host: "127.0.0.1:50876"
  ```
- **Commands Executed**:
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

