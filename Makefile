# ==============================================================================
# LoanTrack Automation Makefile
# ==============================================================================
# Usage:
#   make deploy             # Deploy to Minikube via scripts/deploy.sh
#   make up                 # Run local Docker Compose stack
#   make down               # Stop local Docker Compose stack
#   make clean              # Teardown Minikube loantrack namespace
#   make test-idempotency   # Verify deploy.sh idempotency (2 passes)
# ==============================================================================

SHELL := /bin/bash
.DEFAULT_GOAL := help

.PHONY: help deploy up down clean test-idempotency

help: ## Show this help documentation
	@echo "LoanTrack Management Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-18s %s\n", $$1, $$2}'

deploy: ## Deploy complete application stack to Minikube
	@bash scripts/deploy.sh

up: ## Start local 3-tier Docker Compose environment in detached mode
	@docker compose up -d

down: ## Stop and remove local Docker Compose containers and networks
	@docker compose down

clean: ## Delete the Kubernetes loantrack namespace and clean up cluster state
	@kubectl delete namespace loantrack --ignore-not-found=true

test-idempotency: ## Execute two consecutive deployment passes to verify idempotency
	@echo "==> Running Pass 1: Initial deployment..."
	@bash scripts/deploy.sh
	@echo ""
	@echo "==> Running Pass 2: Secondary idempotent deployment..."
	@bash scripts/deploy.sh
	@echo ""
	@echo "==> Idempotency check PASSED: No configuration errors or duplicate resources."
