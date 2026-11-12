#!/usr/bin/env bash
# ==============================================================================
# LoanTrack Production Deployment Automation Script
#
# Idempotent deployment engine for local Minikube Kubernetes cluster.
# Automates:
#   1. Minikube cluster preflight checks and startup
#   2. Container image building and registration into Minikube container runtime
#   3. Declarative client-side dry-run creation of Secret and db-init ConfigMap
#   4. Ordered manifest reconciliation with deployment rollout health gates
#   5. Dynamic service URL discovery and endpoint verification
# ==============================================================================

set -euo pipefail

# Determine repository root directory relative to this script's path
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

echo "============================================================"
echo " Starting LoanTrack Deployment Pipeline"
echo " Working directory: ${REPO_ROOT}"
echo "============================================================"

# ------------------------------------------------------------------------------
# 1. Cluster Preflight Check
# ------------------------------------------------------------------------------
echo "==> Step 1: Checking Minikube status..."
if ! minikube status >/dev/null 2>&1; then
  echo "    Minikube is not running. Starting minikube with docker driver..."
  minikube start --driver=docker
else
  echo "    Minikube is running and healthy."
fi

# ------------------------------------------------------------------------------
# 2. Container Image Build & Registration
# ------------------------------------------------------------------------------
echo "==> Step 2: Packaging container images..."

build_and_load() {
  local image_tag="$1"
  local build_dir="$2"
  echo "    Packaging ${image_tag} from ${build_dir}..."

  if docker build -t "${image_tag}" "${build_dir}"; then
    echo "    Loading ${image_tag} into Minikube image store..."
    minikube image load "${image_tag}"
  else
    echo "    Docker build failed, falling back to minikube image build..."
    minikube image build -t "${image_tag}" "${build_dir}"
  fi
}

build_and_load "loantrack-backend:v1" "./backend"
build_and_load "loantrack-frontend:v1" "./frontend"

# ------------------------------------------------------------------------------
# 3. Namespace Creation
# ------------------------------------------------------------------------------
echo "==> Step 3: Ensuring namespace 'loantrack' exists..."
kubectl apply -f k8s/00-namespace.yaml

# ------------------------------------------------------------------------------
# 4. Secret & Init ConfigMap Creation (Idempotent Dry-Run Apply)
# ------------------------------------------------------------------------------
echo "==> Step 4: Provisioning Secret and ConfigMap..."

# Read credentials from git-ignored .env if present; fallback to safe defaults
DB_NAME="loantrack"
DB_USER="loantrack_user"
DB_PASS="change_me_dummy"

if [ -f ".env" ]; then
  echo "    Loading database credentials from local .env..."
  # Extract values safely without sourcing arbitrary bash
  DB_NAME=$(grep -E '^POSTGRES_DB=' .env | cut -d '=' -f2- || echo "loantrack")
  DB_USER=$(grep -E '^POSTGRES_USER=' .env | cut -d '=' -f2- || echo "loantrack_user")
  DB_PASS=$(grep -E '^POSTGRES_PASSWORD=' .env | cut -d '=' -f2- || echo "change_me_dummy")
elif [ -f ".env.example" ]; then
  echo "    .env not found; using default values from .env.example..."
fi

# Idempotently create or update Secret without plain-text disk storage
kubectl create secret generic db-credentials \
  --namespace=loantrack \
  --from-literal=POSTGRES_DB="${DB_NAME}" \
  --from-literal=POSTGRES_USER="${DB_USER}" \
  --from-literal=POSTGRES_PASSWORD="${DB_PASS}" \
  --dry-run=client -o yaml | kubectl apply -f -

# Idempotently create or update ConfigMap from migration and seed SQL scripts
kubectl create configmap db-init \
  --namespace=loantrack \
  --from-file=001_create_loans.sql=db/migrations/001_create_loans.sql \
  --from-file=002_seed_loans.sql=db/seed/002_seed_loans.sql \
  --dry-run=client -o yaml | kubectl apply -f -

# ------------------------------------------------------------------------------
# 5. Ordered Manifest Reconciliation with Rollout Gates
# ------------------------------------------------------------------------------
echo "==> Step 5: Applying manifests in dependency order..."

# Apply application configuration parameters
echo "    [1/4] Applying ConfigMap (k8s/10-configmap.yaml)..."
kubectl apply -f k8s/10-configmap.yaml

# Apply PostgreSQL StatefulSet & wait for ready status
echo "    [2/4] Applying PostgreSQL StatefulSet (k8s/20-postgres.yaml)..."
kubectl apply -f k8s/20-postgres.yaml
echo "    Waiting for PostgreSQL StatefulSet rollout..."
kubectl rollout status statefulset/db -n loantrack --timeout=120s

# Apply Backend Deployment & wait for ready status
echo "    [3/4] Applying Backend Deployment (k8s/30-backend.yaml)..."
kubectl apply -f k8s/30-backend.yaml
echo "    Waiting for Backend Deployment rollout..."
kubectl rollout status deployment/backend -n loantrack --timeout=120s

# Apply Frontend Deployment & NodePort Service
echo "    [4/4] Applying Frontend Deployment (k8s/40-frontend.yaml)..."
kubectl apply -f k8s/40-frontend.yaml
echo "    Waiting for Frontend Deployment rollout..."
kubectl rollout status deployment/frontend -n loantrack --timeout=120s

# ------------------------------------------------------------------------------
# 6. Service URL Discovery
# ------------------------------------------------------------------------------
echo "============================================================"
echo " LoanTrack Deployment Finished Successfully!"
echo "============================================================"

MINIKUBE_IP=$(minikube ip 2>/dev/null || echo "127.0.0.1")
echo "Cluster Node IP: ${MINIKUBE_IP}"
echo "Frontend NodePort: 30080"
echo "Direct NodePort URL: http://${MINIKUBE_IP}:30080"
echo ""
echo "Note: If using Docker driver on Windows/macOS, access via minikube tunnel or run:"
echo "      minikube service frontend -n loantrack --url"
echo "============================================================"
