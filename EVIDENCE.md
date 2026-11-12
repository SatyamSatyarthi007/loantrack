# Verification Evidence: LoanTrack

This document captures verbatim terminal commands and real runtime outputs collected during testing across all development phases.

---

## Part A: Application & Database Baseline Evidence

### A1: Backend Unit Test Suite Execution
Command:
```powershell
python -m unittest backend/test_app.py
```
Output:
```text
2026-11-12 11:23:45,424 [WARNING] [31928] loantrack-backend: db not ready, attempt 1/10, retrying in 1s: POSTGRES_PASSWORD environment variable is required and must not be empty
.2026-11-12 11:23:45,462 [ERROR] [31928] loantrack-backend: Error retrieving loans: POSTGRES_PASSWORD environment variable is required and must not be empty
...2026-11-12 11:23:45,463 [WARNING] [31928] loantrack-backend: Readiness probe check failed: POSTGRES_PASSWORD environment variable is required and must not be empty
.
----------------------------------------------------------------------
Ran 5 tests in 0.038s

OK
```
*Verification: All 5 test cases passed, verifying `/healthz` (always 200), `/readyz` (checks DB and returns 503 on failure), `/loans` GET & POST error boundaries, and connection retry exponential backoff logic.*

### A2: Hard Rule 1 Verification (Frontend Isolation from Database)
Command:
```bash
git grep -in "postgres\|password\|5432" frontend/
```
Output:
```text
(no matches found, exit code 1)
```
*Verification: The entire `frontend/` directory contains 0 matches for PostgreSQL drivers, connection strings, ports, or credentials. Hard Rule 1 is strictly satisfied.*

---

## Part B: Docker & Local Compose Evidence

### B1: Compose Stack Health & Status
Command:
```powershell
docker compose ps
```
Output:
```text
NAME                   IMAGE                COMMAND                  SERVICE    CREATED          STATUS                    PORTS
loantrack-backend-1    loantrack-backend    "gunicorn -b 0.0.0.0…"   backend    19 seconds ago   Up 12 seconds (healthy)   8000/tcp
loantrack-db-1         postgres:16-alpine   "docker-entrypoint.s…"   db         19 seconds ago   Up 18 seconds (healthy)   5432/tcp
loantrack-frontend-1   loantrack-frontend   "/docker-entrypoint.…"   frontend   18 seconds ago   Up 11 seconds             0.0.0.0:8080->8080/tcp, [::]:8080->8080/tcp
```

### B2: Image Size Optimization (< 300 MB Target)
Command:
```powershell
docker images | Select-String "loantrack"
```
Output:
```text
loantrack-backend:latest     66f6fb44ccf7   225MB   54.7MB
loantrack-frontend:latest    dda89d81b3cc   73.7MB  21MB
```
*Verification: Backend image size is 225 MB, well within the 300 MB upper limit.*

### B3: Non-Root Execution Verification
Command:
```powershell
docker compose exec backend whoami; docker compose exec frontend whoami; docker compose exec backend id
```
Output:
```text
appuser
nginx
uid=10001(appuser) gid=999(appuser) groups=999(appuser)
```
*Verification: Backend runs as numeric UID 10001 (`appuser`), frontend runs as unprivileged user `nginx` (UID 101).*

### B4: Probe Independence & Database Outage Handling
Command:
```powershell
docker compose stop db
curl.exe -i http://localhost:8080/api/readyz
curl.exe -i http://localhost:8080/api/healthz
```
Output:
```text
HTTP/1.1 503 SERVICE UNAVAILABLE
Server: nginx/1.27.5
Content-Type: application/json
Content-Length: 68

{"error":"database connection check failed","status":"unavailable"}

HTTP/1.1 200 OK
Server: nginx/1.27.5
Content-Type: application/json
Content-Length: 16

{"status":"ok"}
```
*Verification: When PostgreSQL is stopped, `/readyz` fails with 503, while `/healthz` stays 200 without crashing.*

### B5: Exponential Backoff Retry Log
Command:
```powershell
docker compose restart backend
docker compose logs --tail=20 backend
```
Output:
```text
backend-1  | 2026-11-11 20:32:45,718 [INFO] [7] loantrack-backend: Initialized database connection pool (min=1, max=5)
backend-1  | 2026-11-11 20:32:48,719 [WARNING] [7] loantrack-backend: db not ready, attempt 1/10, retrying in 1s: couldn't get a connection after 3.00 sec
backend-1  | 2026-11-11 20:32:52,720 [WARNING] [7] loantrack-backend: db not ready, attempt 2/10, retrying in 2s: couldn't get a connection after 3.00 sec
backend-1  | 2026-11-11 20:32:57,720 [WARNING] [7] loantrack-backend: db not ready, attempt 3/10, retrying in 4s: couldn't get a connection after 3.00 sec
backend-1  | 2026-11-11 20:33:04,084 [INFO] [7] loantrack-backend: Database connection established on attempt 4/10
```
*Verification: Backend retried with backoff delays (1s, 2s, 4s...) and reconnected cleanly on attempt 4 once DB was started.*

### B6: Data Persistence & Volume Lifecycle
1. Originate loan #7 and verify in PostgreSQL:
Command:
```powershell
docker compose exec db psql -U loantrack_user -d loantrack -c "SELECT * FROM loans ORDER BY id DESC LIMIT 3;"
```
Output:
```text
 id |   borrower_name   | loan_amount | property_city |  status  |          created_at           
----+-------------------+-------------+---------------+----------+-------------------------------
  7 | Wayne Enterprises |  1250000.00 | Gotham        | APPROVED | 2026-11-11 20:34:26.638178+00
  6 | Fiona Gallagher   |   195000.00 | Boston        | APPROVED | 2026-11-11 20:30:41.124146+00
  5 | Ethan Hunt        |   510000.00 | Chicago       | PENDING  | 2026-11-10 20:30:41.124146+00
(3 rows)
```

2. Container recreation without volume removal:
Command:
```powershell
docker compose down
docker compose up -d
docker compose exec db psql -U loantrack_user -d loantrack -c "SELECT count(*), max(id) FROM loans;"
```
Output:
```text
 count | max 
-------+-----
     7 |   7
(1 row)
```
*Verification: Row 7 survived container recreation.*

3. Volume wipe:
Command:
```powershell
docker compose down -v
docker compose up -d
docker compose exec db psql -U loantrack_user -d loantrack -c "SELECT count(*), max(id) FROM loans;"
```
Output:
```text
 count | max 
-------+-----
     6 |   6
(1 row)
```
*Verification: The volume was deleted, so the added loan is gone and only the 6 seed rows remain.*

---

## Part C: Kubernetes Deployment Evidence (Minikube)

### C1: All Workloads & Services in `loantrack` Namespace
Command:
```powershell
kubectl get all -n loantrack
```
Output:
```text
NAME                            READY   STATUS    RESTARTS   AGE
pod/backend-c664ccb4c-fln5p     1/1     Running   0          45s
pod/backend-c664ccb4c-w4ksn     1/1     Running   0          52s
pod/db-0                        1/1     Running   0          65s
pod/frontend-5fc98c545c-bvbvl   1/1     Running   0          25s
pod/frontend-5fc98c545c-zdxhg   1/1     Running   0          31s

NAME               TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)          AGE
service/backend    ClusterIP   10.98.68.49      <none>        8000/TCP         122m
service/db         ClusterIP   10.98.131.40     <none>        5432/TCP         123m
service/frontend   NodePort    10.100.162.181   <none>        8080:30080/TCP   122m

NAME                       READY   UP-TO-DATE   AVAILABLE   AGE
deployment.apps/backend    2/2     2            2           122m
deployment.apps/frontend   2/2     2            2           122m

NAME                  READY   AGE
statefulset.apps/db   1/1     65s
```

### C2: Storage, Config, and Secret Resources
Command:
```powershell
kubectl get pvc,configmap,secret -n loantrack
```
Output:
```text
NAME                                STATUS   VOLUME                                     CAPACITY   ACCESS MODES   STORAGECLASS   AGE
persistentvolumeclaim/pgdata-db-0   Bound    pvc-aefee691-fadc-43d9-b7a1-c2758570d22c   1Gi        RWO            standard       65s

NAME                         DATA   AGE
configmap/db-init            2      123m
configmap/kube-root-ca.crt   1      123m
configmap/loantrack-config   4      123m

NAME                    TYPE     DATA   AGE
secret/db-credentials   Opaque   2      74s
```

### C3: Network Isolation & Service Types (Part D3)
Command:
```powershell
kubectl -n loantrack get svc
```
Output:
```text
NAME       TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)          AGE
backend    ClusterIP   10.98.68.49      <none>        8000/TCP         122m
db         ClusterIP   10.98.131.40     <none>        5432/TCP         123m
frontend   NodePort    10.100.162.181   <none>        8080:30080/TCP   122m
```
*Verification: `db` and `backend` are ClusterIP only (internal cluster networking, zero external attack surface). Only `frontend` exposes a NodePort (30080).*

### C4: Live Cluster Probes & REST API Responses
Command:
```powershell
curl.exe -i http://127.0.0.1:57770/api/healthz
curl.exe -i http://127.0.0.1:57770/api/readyz
curl.exe -s http://127.0.0.1:57770/api/loans
```
Output:
```text
HTTP/1.1 200 OK
Server: nginx/1.27.5
Content-Type: application/json
Content-Length: 16

{"status":"ok"}

HTTP/1.1 200 OK
Server: nginx/1.27.5
Content-Type: application/json
Content-Length: 19

{"status":"ready"}

{"loans":[{"borrower_name":"Alice Johnson","created_at":"2026-11-06T20:58:33.577120+00:00","id":1,"loan_amount":350000.0,"property_city":"Seattle","status":"APPROVED"},{"borrower_name":"Bob Smith","created_at":"2026-11-07T20:58:33.577120+00:00","id":2,"loan_amount":480000.0,"property_city":"Austin","status":"PENDING"},{"borrower_name":"Carlos Rodriguez","created_at":"2026-11-08T20:58:33.577120+00:00","id":3,"loan_amount":275000.0,"property_city":"Denver","status":"APPROVED"},{"borrower_name":"Diana Prince","created_at":"2026-11-09T20:58:33.577120+00:00","id":4,"loan_amount":620000.0,"property_city":"San Francisco","status":"REJECTED"},{"borrower_name":"Ethan Hunt","created_at":"2026-11-10T20:58:33.577120+00:00","id":5,"loan_amount":510000.0,"property_city":"Chicago","status":"PENDING"},{"borrower_name":"Fiona Gallagher","created_at":"2026-11-11T20:58:33.577120+00:00","id":6,"loan_amount":195000.0,"property_city":"Boston","status":"APPROVED"}],"served_by":"backend-c664ccb4c-fln5p","version":"v1"}
```

### C5: Multi-Pod Load Balancing Verification
Command:
```powershell
1..6 | ForEach-Object { (Invoke-RestMethod -Uri "http://127.0.0.1:57770/api/loans").served_by }
```
Output:
```text
backend-c664ccb4c-fln5p
backend-c664ccb4c-w4ksn
backend-c664ccb4c-w4ksn
backend-c664ccb4c-w4ksn
backend-c664ccb4c-w4ksn
backend-c664ccb4c-fln5p
```
*Verification: Requests distribute across both backend pods (`backend-c664ccb4c-fln5p` and `backend-c664ccb4c-w4ksn`) as proven by `served_by` populated via Downward API.*

---

## Part D: Kubernetes Operational Evidence (Day-2)

### D1: In-Cluster CoreDNS Name Resolution
Command (resolving database service by short name and fully qualified domain name `db.loantrack.svc.cluster.local` from a backend pod):
```bash
kubectl -n loantrack exec deploy/backend -- python -c "import socket; print('Short hostname (db):', socket.gethostbyname('db')); print('FQDN (db.loantrack.svc.cluster.local):', socket.getaddrinfo('db.loantrack.svc.cluster.local', 5432)[0][4])"
```
Output:
```text
Short hostname (db): 10.98.131.40
FQDN (db.loantrack.svc.cluster.local): ('10.98.131.40', 5432)
```

Command (resolving backend service from within the namespace):
```bash
kubectl -n loantrack exec deploy/backend -- python -c "import socket; print('backend service IP:', socket.gethostbyname('backend'))"
```
Output:
```text
backend service IP: 10.98.68.49
```
*Verification: CoreDNS resolves both relative names (`db`) within the `loantrack` namespace search domain and FQDNs (`db.loantrack.svc.cluster.local`) directly to their respective ClusterIP virtual addresses.*

### D2: Horizontal Scaling and 3-Pod Load Balancing
Commands:
```bash
kubectl -n loantrack scale deploy/backend --replicas=3
kubectl -n loantrack rollout status deploy/backend
kubectl -n loantrack get pods -l app=backend -o wide
```
Output:
```text
deployment.apps/backend scaled
Waiting for deployment "backend" rollout to finish: 2 of 3 updated replicas are available...
deployment "backend" successfully rolled out
NAME                      READY   STATUS    RESTARTS   AGE     IP            NODE       NOMINATED NODE   READINESS GATES
backend-c664ccb4c-fln5p   1/1     Running   0          7h41m   10.244.0.10   minikube   <none>           <none>
backend-c664ccb4c-hbkkb   1/1     Running   0          6s      10.244.0.13   minikube   <none>           <none>
backend-c664ccb4c-w4ksn   1/1     Running   0          7h41m   10.244.0.9    minikube   <none>           <none>
```

Command (10 consecutive requests through frontend reverse proxy):
```powershell
1..10 | ForEach-Object { (Invoke-RestMethod -Uri "http://127.0.0.1:50876/api/loans").served_by }
```
Output:
```text
backend-c664ccb4c-w4ksn
backend-c664ccb4c-w4ksn
backend-c664ccb4c-w4ksn
backend-c664ccb4c-hbkkb
backend-c664ccb4c-fln5p
backend-c664ccb4c-w4ksn
backend-c664ccb4c-w4ksn
backend-c664ccb4c-fln5p
backend-c664ccb4c-hbkkb
backend-c664ccb4c-fln5p
```
*Verification: The backend deployment scales dynamically from 2 to 3 replicas without downtime, and incoming HTTP requests distribute across all 3 active backend pods (`backend-c664ccb4c-fln5p`, `backend-c664ccb4c-hbkkb`, and `backend-c664ccb4c-w4ksn`).*

### D3: Zero-Downtime Rolling Update & Rollback

#### Rolling Update to v2
Command:
```bash
# Build v2 image with APP_VERSION=v2 and load into minikube
docker build -t loantrack-backend:v2 --build-arg APP_VERSION=v2 ./backend
minikube image load loantrack-backend:v2

# Trigger rolling update
kubectl -n loantrack set image deploy/backend backend=loantrack-backend:v2
```

Loop querying the service endpoint during the rolling update:
```powershell
for ($i = 0; $i -lt 35; $i++) {
    try {
        $res = Invoke-RestMethod -Uri "http://127.0.0.1:50876/api/loans" -TimeoutSec 2
        Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] HTTP 200 - version: $($res.version), pod: $($res.served_by)"
    } catch {
        Write-Host "[$((Get-Date).ToString('HH:mm:ss'))] ERROR: $($_.Exception.Message)"
    }
    Start-Sleep -Milliseconds 600
}
kubectl -n loantrack rollout status deploy/backend
```
Output:
```text
deployment.apps/backend image updated
[10.14.50] HTTP 200 - version: v1, pod: backend-6ddd66467-wtwgt
[10.14.51] HTTP 200 - version: v1, pod: backend-6ddd66467-fm996
[10.14.51] HTTP 200 - version: v1, pod: backend-6ddd66467-wtwgt
[10.14.52] HTTP 200 - version: v1, pod: backend-6ddd66467-fm996
[10.14.53] HTTP 200 - version: v1, pod: backend-6ddd66467-wtwgt
[10.14.53] HTTP 200 - version: v1, pod: backend-6ddd66467-wtwgt
[10.14.54] HTTP 200 - version: v1, pod: backend-6ddd66467-fm996
[10.14.55] HTTP 200 - version: v1, pod: backend-6ddd66467-wtwgt
[10.14.55] HTTP 200 - version: v1, pod: backend-6ddd66467-fm996
[10.14.56] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.14.57] HTTP 200 - version: v1, pod: backend-6ddd66467-wtwgt
[10.14.57] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.14.58] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.14.58] HTTP 200 - version: v1, pod: backend-6ddd66467-wtwgt
[10.14.59] HTTP 200 - version: v1, pod: backend-6ddd66467-wtwgt
[10.15.00] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.00] HTTP 200 - version: v1, pod: backend-6ddd66467-wtwgt
[10.15.01] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.02] HTTP 200 - version: v1, pod: backend-6ddd66467-wtwgt
[10.15.02] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.03] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.03] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.04] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.05] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.05] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.06] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.07] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.07] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.08] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.09] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.09] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.10] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.11] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.11] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.12] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
deployment "backend" successfully rolled out
```

#### Rollback to v1
Command:
```bash
kubectl -n loantrack rollout undo deploy/backend
```

Loop querying the service endpoint during the rollback:
```text
deployment.apps/backend rolled back
[10.15.28] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.29] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.30] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.30] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.31] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.32] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.32] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.33] HTTP 200 - version: v2, pod: backend-7d54c9f988-fncxf
[10.15.33] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.34] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.35] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.35] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.36] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.37] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.37] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.38] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.38] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.39] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.40] HTTP 200 - version: v2, pod: backend-7d54c9f988-9bgdz
[10.15.40] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.41] HTTP 200 - version: v1, pod: backend-6ddd66467-h2h8x
[10.15.42] HTTP 200 - version: v1, pod: backend-6ddd66467-h2h8x
[10.15.42] HTTP 200 - version: v1, pod: backend-6ddd66467-h2h8x
[10.15.43] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.44] HTTP 200 - version: v1, pod: backend-6ddd66467-h2h8x
[10.15.44] HTTP 200 - version: v1, pod: backend-6ddd66467-h2h8x
[10.15.45] HTTP 200 - version: v1, pod: backend-6ddd66467-h2h8x
[10.15.45] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.46] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.47] HTTP 200 - version: v1, pod: backend-6ddd66467-h2h8x
[10.15.47] HTTP 200 - version: v1, pod: backend-6ddd66467-h2h8x
[10.15.48] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.49] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
[10.15.49] HTTP 200 - version: v1, pod: backend-6ddd66467-h2h8x
[10.15.50] HTTP 200 - version: v1, pod: backend-6ddd66467-vfxb2
deployment "backend" successfully rolled out
```

#### Why Zero Downtime Occurred (SRE Architectural Analysis)
A user mid-rollout experiences 0 dropped connections and 0 HTTP errors due to the interplay of three mechanisms:
1. **`maxUnavailable: 0`**: Ensures Kubernetes does not terminate any active pod until replacement pods are ready. Old pods remain in the Service endpoints handling existing and incoming traffic.
2. **`maxSurge: 1` + `readinessProbe`**: A new pod is scheduled above replica count (`n + 1`). Traffic is NOT routed to this new pod until its `readinessProbe` (`GET /readyz`, verifying DB `SELECT 1`) passes consecutive health checks.
3. **`lifecycle.preStop` delay (`sleep 5`)**: When an old pod is marked for termination, Kubernetes initiates endpoint dereference and `SIGTERM` concurrently. The `preStop` hook introduces a 5-second buffer allowing CoreDNS and kube-proxy iptables rules to complete IP removal before Gunicorn stops accepting connections, completely preventing `502 Bad Gateway` / `Connection reset` race conditions.

### D4: Pod Self-Healing & StatefulSet Storage Persistence

#### Backend Pod Deletion & Immediate Self-Healing
Command:
```bash
# Get current backend pods
kubectl -n loantrack get pods -l app=backend

# Delete one backend pod
kubectl -n loantrack delete pod backend-6ddd66467-h2h8x

# Inspect pod list immediately after deletion
kubectl -n loantrack get pods -l app=backend
kubectl -n loantrack wait --for=condition=ready pod -l app=backend --timeout=30s
kubectl -n loantrack get pods -l app=backend
```
Output:
```text
NAME                      READY   STATUS    RESTARTS   AGE
backend-6ddd66467-h2h8x   1/1     Running   0          79s
backend-6ddd66467-vfxb2   1/1     Running   0          85s

pod "backend-6ddd66467-h2h8x" deleted from loantrack namespace

NAME                      READY   STATUS    RESTARTS   AGE
backend-6ddd66467-vfxb2   1/1     Running   0          96s
backend-6ddd66467-vvlv9   1/1     Running   0          6s

pod/backend-6ddd66467-vfxb2 condition met
pod/backend-6ddd66467-vvlv9 condition met

NAME                      READY   STATUS    RESTARTS   AGE
backend-6ddd66467-vfxb2   1/1     Running   0          107s
backend-6ddd66467-vvlv9   1/1     Running   0          17s
```
*Verification: Kubernetes ReplicaSet controller detected the pod deletion and instantly scheduled a replacement pod (`backend-6ddd66467-vvlv9`), maintaining the desired replica count of 2.*

#### StatefulSet Pod Deletion & Data Persistence Verification
Command (originate loan #7 via HTTP API before deleting the database pod):
```powershell
$body = @{
    borrower_name = "Grace Hopper"
    loan_amount = 750000.00
    property_city = "New York"
    status = "APPROVED"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:50876/api/loans" -Method Post -ContentType "application/json" -Body $body
```
Output:
```json
{
  "loan": {
    "borrower_name": "Grace Hopper",
    "created_at": "2026-11-12T04:47:30.422011+00:00",
    "id": 7,
    "loan_amount": 750000.0,
    "property_city": "New York",
    "status": "APPROVED"
  },
  "served_by": "backend-6ddd66467-vvlv9",
  "version": "v1"
}
```

Command (delete StatefulSet pod `db-0` and await recreation):
```bash
kubectl -n loantrack delete pod db-0
kubectl -n loantrack get pods -l app=db
kubectl -n loantrack wait --for=condition=ready pod/db-0 --timeout=60s
kubectl -n loantrack get pods -l app=db
```
Output:
```text
pod "db-0" deleted from loantrack namespace
NAME   READY   STATUS              RESTARTS   AGE
db-0   0/1     ContainerCreating   0          0s

pod/db-0 condition met
NAME   READY   STATUS    RESTARTS   AGE
db-0   1/1     Running   0          10s
```

Command (verify data survived pod recreation via psql and REST API):
```bash
kubectl -n loantrack exec db-0 -- psql -U loantrack_user -d loantrack -c "SELECT count(*) FROM loans;"
```
Output:
```text
 count 
-------
     7
(1 row)
```

Querying all loans via frontend reverse proxy:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:50876/api/loans" | Select-Object -ExpandProperty loans | Select-Object id, borrower_name, loan_amount, property_city, status | Format-Table -AutoSize
```
Output:
```text
id borrower_name    loan_amount property_city status  
-- -------------    ----------- ------------- ------  
 1 Alice Johnson       350000.0 Seattle       APPROVED
 2 Bob Smith           480000.0 Austin        PENDING 
 3 Carlos Rodriguez    275000.0 Denver        APPROVED
 4 Diana Prince        620000.0 San Francisco REJECTED
 5 Ethan Hunt          510000.0 Chicago       PENDING 
 6 Fiona Gallagher     195000.0 Boston        APPROVED
 7 Grace Hopper        750000.0 New York      APPROVED
```
*Verification: StatefulSet `volumeClaimTemplates` binds the PersistentVolumeClaim `loantrack-pgdata-db-0` independently of the pod lifecycle. When `db-0` was deleted, the underlying PVC was reattached to the newly scheduled pod, preserving all data (including newly originated loan #7).*

---

## Part E: Deployment Automation & Idempotency Evidence

### E1: Cold-Start Deployment from Zero State (`scripts/deploy.sh`)
Command (executing deployment pipeline against clean cluster after `kubectl delete namespace loantrack`):
```bash
bash scripts/deploy.sh
```
Output:
```text
============================================================
 Starting LoanTrack Deployment Pipeline
 Working directory: /c/Users/satyam/Desktop/loantrack
============================================================
==> Step 1: Checking Minikube status...
    Minikube is running and healthy.
==> Step 2: Packaging container images...
    Packaging loantrack-backend:v1 from ./backend...
    Loading loantrack-backend:v1 into Minikube image store...
    Packaging loantrack-frontend:v1 from ./frontend...
    Loading loantrack-frontend:v1 into Minikube image store...
==> Step 3: Ensuring namespace 'loantrack' exists...
namespace/loantrack created
==> Step 4: Provisioning Secret and ConfigMap...
    Loading database credentials from local .env...
secret/db-credentials created
configmap/db-init created
==> Step 5: Applying manifests in dependency order...
    [1/4] Applying ConfigMap (k8s/10-configmap.yaml)...
configmap/loantrack-config created
    [2/4] Applying PostgreSQL StatefulSet (k8s/20-postgres.yaml)...
service/db created
statefulset.apps/db created
    Waiting for PostgreSQL StatefulSet rollout...
Waiting for 1 pods to be ready...
partitioned roll out complete: 1 new pods have been updated...
    [3/4] Applying Backend Deployment (k8s/30-backend.yaml)...
service/backend created
deployment.apps/backend created
    Waiting for Backend Deployment rollout...
Waiting for deployment "backend" rollout to finish: 0 of 2 updated replicas are available...
Waiting for deployment "backend" rollout to finish: 1 of 2 updated replicas are available...
deployment "backend" successfully rolled out
    [4/4] Applying Frontend Deployment (k8s/40-frontend.yaml)...
service/frontend created
deployment.apps/frontend created
    Waiting for Frontend Deployment rollout...
Waiting for deployment "frontend" rollout to finish: 0 of 2 updated replicas are available...
Waiting for deployment "frontend" rollout to finish: 1 of 2 updated replicas are available...
deployment "frontend" successfully rolled out
============================================================
 LoanTrack Deployment Finished Successfully!
============================================================
Cluster Node IP: 192.168.49.2
Frontend NodePort: 30080
Direct NodePort URL: http://192.168.49.2:30080

Note: If using Docker driver on Windows/macOS, access via minikube tunnel or run:
      minikube service frontend -n loantrack --url
============================================================
```

### E2: Secondary Deployment Pass Proving Script Idempotency
Command (re-running deployment pipeline immediately with zero changes):
```bash
bash scripts/deploy.sh
```
Output:
```text
============================================================
 Starting LoanTrack Deployment Pipeline
 Working directory: /c/Users/satyam/Desktop/loantrack
============================================================
==> Step 1: Checking Minikube status...
    Minikube is running and healthy.
==> Step 2: Packaging container images...
    Packaging loantrack-backend:v1 from ./backend...
    Loading loantrack-backend:v1 into Minikube image store...
    Packaging loantrack-frontend:v1 from ./frontend...
    Loading loantrack-frontend:v1 into Minikube image store...
==> Step 3: Ensuring namespace 'loantrack' exists...
namespace/loantrack unchanged
==> Step 4: Provisioning Secret and ConfigMap...
    Loading database credentials from local .env...
secret/db-credentials unchanged
configmap/db-init unchanged
==> Step 5: Applying manifests in dependency order...
    [1/4] Applying ConfigMap (k8s/10-configmap.yaml)...
configmap/loantrack-config unchanged
    [2/4] Applying PostgreSQL StatefulSet (k8s/20-postgres.yaml)...
service/db unchanged
statefulset.apps/db configured
    Waiting for PostgreSQL StatefulSet rollout...
partitioned roll out complete: 1 new pods have been updated...
    [3/4] Applying Backend Deployment (k8s/30-backend.yaml)...
service/backend unchanged
deployment.apps/backend unchanged
    Waiting for Backend Deployment rollout...
deployment "backend" successfully rolled out
    [4/4] Applying Frontend Deployment (k8s/40-frontend.yaml)...
service/frontend unchanged
deployment.apps/frontend unchanged
    Waiting for Frontend Deployment rollout...
deployment "frontend" successfully rolled out
============================================================
 LoanTrack Deployment Finished Successfully!
============================================================
Cluster Node IP: 192.168.49.2
Frontend NodePort: 30080
Direct NodePort URL: http://192.168.49.2:30080

Note: If using Docker driver on Windows/macOS, access via minikube tunnel or run:
      minikube service frontend -n loantrack --url
============================================================
```
*Verification: Every resource reported `unchanged` or cleanly `configured`. No errors occurred, no duplicate resources were created, and the script completed idempotently.*

### E3: End-to-End Application Verification from Newly Deployed Cluster
Command:
```bash
kubectl -n loantrack exec deploy/frontend -- wget -qO- http://127.0.0.1:8080/api/readyz
kubectl -n loantrack exec deploy/frontend -- wget -qO- http://127.0.0.1:8080/api/loans
```
Output:
```json
{"status":"ready"}
{"loans":[{"borrower_name":"Alice Johnson","created_at":"2026-11-07T05:07:11.466672+00:00","id":1,"loan_amount":350000.0,"property_city":"Seattle","status":"APPROVED"},{"borrower_name":"Bob Smith","created_at":"2026-11-08T05:07:11.466672+00:00","id":2,"loan_amount":480000.0,"property_city":"Austin","status":"PENDING"},{"borrower_name":"Carlos Rodriguez","created_at":"2026-11-09T05:07:11.466672+00:00","id":3,"loan_amount":275000.0,"property_city":"Denver","status":"APPROVED"},{"borrower_name":"Diana Prince","created_at":"2026-11-10T05:07:11.466672+00:00","id":4,"loan_amount":620000.0,"property_city":"San Francisco","status":"REJECTED"},{"borrower_name":"Ethan Hunt","created_at":"2026-11-11T05:07:11.466672+00:00","id":5,"loan_amount":510000.0,"property_city":"Chicago","status":"PENDING"},{"borrower_name":"Fiona Gallagher","created_at":"2026-11-12T05:07:11.466672+00:00","id":6,"loan_amount":195000.0,"property_city":"Boston","status":"APPROVED"}],"served_by":"backend-6ddd66467-j4w9h","version":"v1"}
```
*Verification: Cold-start deployment script automatically mounted init SQL scripts into PostgreSQL, bringing all 6 initial loans into ready state without manual human intervention.*





