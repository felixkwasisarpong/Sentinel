# Sentinel Makefile
# Usage:
#   make up
#   make down
#   make eval
#   make leaderboard
#   make ps
#   make logs
#   make clean
#   make build-core
#   make build-runtime
#   make publish-core
#   make publish-runtime

SHELL := /bin/bash
COMPOSE ?= docker compose
PY ?= python3

# Optional: override from CLI
# make eval BASE_URL=http://localhost:8000
BASE_URL ?= http://localhost:8000
CORE_DIR ?= sdk
RUNTIME_DIR ?= services/gateway-api
TWINE_REPOSITORY ?= pypi

.PHONY: help up down restart ps logs clean eval leaderboard wait \
	build-core build-runtime build-packages publish-core publish-runtime

help:
	@echo "Targets:"
	@echo "  make up           - Build + start services"
	@echo "  make down         - Stop services (keeps volumes)"
	@echo "  make clean        - Stop services + remove volumes"
	@echo "  make ps           - Show running containers"
	@echo "  make logs         - Tail logs"
	@echo "  make eval         - Run eval suite + generate leaderboard"
	@echo "  make leaderboard  - Re-generate leaderboard from eval/results.json"
	@echo "  make build-core   - Build sentinel-core sdist/wheel"
	@echo "  make build-runtime- Build senteniel sdist/wheel"
	@echo "  make build-packages - Build both Python distributions"
	@echo "  make publish-core - Upload sentinel-core dist to Twine repository"
	@echo "  make publish-runtime - Upload senteniel dist to Twine repository"
	@echo ""
	@echo "Vars:"
	@echo "  BASE_URL=$(BASE_URL)"
	@echo "  TWINE_REPOSITORY=$(TWINE_REPOSITORY)"

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down
	$(COMPOSE) up -d --build

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=200

clean:
	$(COMPOSE) down -v

# Wait for the gateway to respond before running eval (CI/local friendly)
wait:
	@echo "Waiting for gateway at $(BASE_URL)/health ..."
	@for i in {1..60}; do \
		if curl -fsS "$(BASE_URL)/health" >/dev/null 2>&1; then \
			echo "Gateway is up."; exit 0; \
		fi; \
		sleep 2; \
	done; \
	echo "Gateway did not become ready in time." ; exit 1

eval: up wait
	@echo "Running eval against $(BASE_URL)"
	BASE_URL=$(BASE_URL) $(PY) eval/run_eval.py
	$(PY) eval/score.py
	@echo ""
	@echo "Leaderboard generated: eval/LEADERBOARD.md"
	@echo "Tip: cat eval/LEADERBOARD.md"

leaderboard:
	$(PY) eval/score.py
	@echo "Leaderboard generated: eval/LEADERBOARD.md"

build-core:
	cd $(CORE_DIR) && $(PY) -m build

build-runtime:
	cd $(RUNTIME_DIR) && $(PY) -m build

build-packages: build-core build-runtime

publish-core: build-core
	$(PY) -m twine upload --repository $(TWINE_REPOSITORY) $(CORE_DIR)/dist/*

publish-runtime: build-runtime
	$(PY) -m twine upload --repository $(TWINE_REPOSITORY) $(RUNTIME_DIR)/dist/*
