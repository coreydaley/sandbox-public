.DEFAULT_GOAL := help

help: ## Show targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-8s %s\n", $$1, $$2}'

hooks: ## Install git hooks (requires: brew install gitleaks)
	@bash tools/setup-hooks.sh

test: ## Run every example's tests (each test_*.py, from its own folder)
	@set -e; for t in $$(git ls-files '*/test_*.py'); do \
		echo "== $$t"; (cd "$$(dirname "$$t")" && python3 -I "$$(basename "$$t")"); \
	done

.PHONY: help hooks test
