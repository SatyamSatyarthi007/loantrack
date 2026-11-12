# Verification Evidence: LoanTrack

This document captures verbatim terminal commands and real runtime outputs collected during testing across all development phases.

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

