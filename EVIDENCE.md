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
