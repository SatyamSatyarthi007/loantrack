import logging
import os
import sys
import threading
import time
from flask import Flask, jsonify, request
from psycopg_pool import ConnectionPool

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(process)d] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("loantrack-backend")

app = Flask(__name__)

# Read configuration from environment variables only (Hard Rule 2: no hardcoded secrets)
DB_HOST = os.environ.get("DB_HOST") or os.environ.get("POSTGRES_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT") or os.environ.get("POSTGRES_PORT", "5432")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "loantrack")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "loantrack_user")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")  # No default! Mandatory in env
APP_VERSION = os.environ.get("APP_VERSION", "v1")

# Process-level connection pool (initialized lazily per gunicorn worker)
_pool = None
_pool_lock = threading.Lock()


def get_conninfo() -> str:
    """Build PostgreSQL connection string from environment variables."""
    if not POSTGRES_PASSWORD:
        raise ValueError("POSTGRES_PASSWORD environment variable is required and must not be empty")
    return (
        f"host={DB_HOST} port={DB_PORT} dbname={POSTGRES_DB} "
        f"user={POSTGRES_USER} password={POSTGRES_PASSWORD} connect_timeout=3"
    )


def get_db_pool() -> ConnectionPool:
    """
    Get or initialize a process-local connection pool.
    Under gunicorn -w 2, opening the pool lazily inside each worker process avoids
    inherited socket file descriptors across forks.
    """
    global _pool
    if _pool is None or _pool.closed:
        with _pool_lock:
            if _pool is None or _pool.closed:
                conninfo = get_conninfo()
                _pool = ConnectionPool(
                    conninfo=conninfo,
                    min_size=1,
                    max_size=5,
                    open=False,
                )
                _pool.open()
                logger.info("Initialized database connection pool (min=1, max=5)")
    return _pool


def wait_for_db(max_attempts: int = 10) -> bool:
    """
    Startup retry with exponential backoff.
    Never crashes the application process if DB is temporarily unreachable.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            pool = get_db_pool()
            with pool.connection(timeout=3.0) as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1;")
            logger.info("Database connection established on attempt %d/%d", attempt, max_attempts)
            return True
        except Exception as err:
            delay = min(2 ** (attempt - 1), 15)
            logger.warning(
                "db not ready, attempt %d/%d, retrying in %ds: %s",
                attempt, max_attempts, delay, err,
            )
            if attempt < max_attempts:
                time.sleep(delay)

    logger.error(
        "Could not connect to database after %d attempts; continuing to serve liveness probe",
        max_attempts,
    )
    return False


# Attempt startup DB connection in background thread so server bind is not blocked
if not os.environ.get("TESTING"):
    threading.Thread(target=wait_for_db, daemon=True).start()


# ------------------------------------------------------------------------------
# Health & Readiness Endpoints (Kubernetes Probes)
# ------------------------------------------------------------------------------

@app.route("/healthz", methods=["GET"])
def healthz():
    """
    Liveness probe endpoint.
    Verifies that the Flask/gunicorn process is alive and responsive.
    CRITICAL: Never touches the database, preventing cascading pod restarts during DB outages.
    """
    return jsonify({"status": "ok"}), 200


@app.route("/readyz", methods=["GET"])
def readyz():
    """
    Readiness probe endpoint.
    Verifies that the backend can successfully execute a lightweight query on PostgreSQL.
    Returns 200 when ready to receive client traffic; 503 if the database is unreachable.
    Uses 2.0s timeout to avoid blocking Kubernetes probe periods.
    """
    try:
        pool = get_db_pool()
        with pool.connection(timeout=2.0) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
        return jsonify({"status": "ready"}), 200
    except Exception as err:
        logger.warning("Readiness probe check failed: %s", err)
        return jsonify({
            "status": "unavailable",
            "error": "database connection check failed"
        }), 503


# ------------------------------------------------------------------------------
# Business Logic Endpoints: Loans API
# ------------------------------------------------------------------------------

def get_pod_metadata() -> dict:
    """Helper to return pod hostname and application version."""
    return {
        "served_by": os.environ.get("HOSTNAME", "localhost"),
        "version": APP_VERSION,
    }


@app.route("/loans", methods=["GET"])
def list_loans():
    """
    List all loans in descending or ascending ID order.
    Returns array of loans along with serving pod hostname and application version.
    """
    try:
        pool = get_db_pool()
        with pool.connection(timeout=3.0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, borrower_name, loan_amount, property_city, status, created_at
                    FROM loans
                    ORDER BY id ASC;
                    """
                )
                rows = cur.fetchall()

        loans = []
        for row in rows:
            loans.append({
                "id": row[0],
                "borrower_name": row[1],
                "loan_amount": float(row[2]) if row[2] is not None else 0.0,
                "property_city": row[3],
                "status": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
            })

        meta = get_pod_metadata()
        return jsonify({
            "loans": loans,
            "served_by": meta["served_by"],
            "version": meta["version"],
        }), 200

    except Exception as err:
        logger.error("Error retrieving loans: %s", err)
        return jsonify({
            "error": "Failed to fetch loans from database",
            "served_by": os.environ.get("HOSTNAME", "localhost"),
            "version": APP_VERSION,
        }), 500


@app.route("/loans", methods=["POST"])
def create_loan():
    """
    Create a new loan record.
    Validates payload: borrower_name (required string), loan_amount (required positive float).
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({"error": "Invalid or missing JSON payload"}), 400

    borrower_name = str(data.get("borrower_name", "")).strip()
    if not borrower_name:
        return jsonify({"error": "Field 'borrower_name' is required"}), 400

    raw_amount = data.get("loan_amount")
    try:
        loan_amount = float(raw_amount)
        if loan_amount <= 0:
            return jsonify({"error": "Field 'loan_amount' must be greater than zero"}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Field 'loan_amount' must be a valid positive number"}), 400

    property_city = data.get("property_city")
    if property_city is not None:
        property_city = str(property_city).strip()

    status = str(data.get("status", "PENDING")).strip().upper()
    if status not in ("PENDING", "APPROVED", "REJECTED"):
        status = "PENDING"

    try:
        pool = get_db_pool()
        with pool.connection(timeout=3.0) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO loans (borrower_name, loan_amount, property_city, status)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, borrower_name, loan_amount, property_city, status, created_at;
                    """,
                    (borrower_name, loan_amount, property_city, status),
                )
                row = cur.fetchone()
            conn.commit()

        created = {
            "id": row[0],
            "borrower_name": row[1],
            "loan_amount": float(row[2]),
            "property_city": row[3],
            "status": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }

        meta = get_pod_metadata()
        return jsonify({
            "loan": created,
            "served_by": meta["served_by"],
            "version": meta["version"],
        }), 201

    except Exception as err:
        logger.error("Error creating loan: %s", err)
        return jsonify({
            "error": "Failed to create loan in database",
            "served_by": os.environ.get("HOSTNAME", "localhost"),
            "version": APP_VERSION,
        }), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
