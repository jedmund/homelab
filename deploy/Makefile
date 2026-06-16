# Per-stack deployment Makefile
#
# This is a thin convenience wrapper around `ansible-playbook` for the per-stack
# playbooks alongside it. The root Makefile (../Makefile) covers the full
# infrastructure workflow (deploy-all, vault management, lint, etc.); this one
# is meant for the common day-to-day case of "redeploy one stack".
#
# Invoked from this directory:
#   make                    # list available stacks
#   make help               # ditto
#   make <stack>            # deploy that stack (e.g. `make petlibro`)
#   make deploy STACK=<s>   # same, but parameterised
#   make check STACK=<s>    # --check --diff dry run
#   make syntax STACK=<s>   # --syntax-check
#
# Inventory and vault flag are picked up the same way the root Makefile does.

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help list deploy check syntax

# Colors
GREEN  := \033[0;32m
YELLOW := \033[0;33m
BLUE   := \033[0;34m
RED    := \033[0;31m
NC     := \033[0m

ROOT      := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
ANSIBLE   := ansible-playbook
INVENTORY := $(ROOT)/inventory/hosts.yml
VAULT_PASS := $(HOME)/.ansible-vault-pass
VAULT_FLAG := $(if $(wildcard $(VAULT_PASS)),--vault-password-file $(VAULT_PASS),--ask-vault-pass)

# Auto-discover all *.yml playbooks in this directory (excluding all.yml,
# which is the meta-playbook driven by the root Makefile's deploy-all).
STACKS := $(filter-out all migrate_content_reading_products migrate_productivity_products migrate_utilities_products migrate_media_consumption_products migrate_media_acquisition_products migrate_development_products migrate_line_from_infra_gateway archive_legacy_content_reading_stacks,$(basename $(notdir $(wildcard *.yml))))

help: ## Show this help and list available stacks
	@printf "$(BLUE)Per-stack deployment$(NC)\n\n"
	@printf "Usage:\n"
	@printf "  make $(GREEN)<stack>$(NC)              deploy a stack by name\n"
	@printf "  make $(GREEN)deploy STACK=<stack>$(NC) same, parameterised\n"
	@printf "  make $(GREEN)check  STACK=<stack>$(NC) dry-run (--check --diff)\n"
	@printf "  make $(GREEN)syntax STACK=<stack>$(NC) --syntax-check\n"
	@printf "  make $(GREEN)list$(NC)                 list discoverable stacks\n\n"
	@printf "$(YELLOW)Available stacks:$(NC)\n"
	@printf "  %s\n" $(sort $(STACKS))
	@printf "\nFor the full lifecycle (deploy-all, lint, vault, docker mgmt, ...)\n"
	@printf "see $(BLUE)../Makefile$(NC).\n"

list: ## List discoverable stacks
	@printf "%s\n" $(sort $(STACKS))

# Generic targets driven by STACK=<name>.

deploy: _require_stack ## Deploy a stack (STACK=<name>)
	@printf "$(BLUE)Deploying $(STACK)...$(NC)\n"
	@$(ANSIBLE) -i $(INVENTORY) $(STACK).yml $(VAULT_FLAG) $(EXTRA_ARGS)

check: _require_stack ## Dry-run a stack (STACK=<name>)
	@printf "$(BLUE)Dry-run for $(STACK)...$(NC)\n"
	@$(ANSIBLE) -i $(INVENTORY) $(STACK).yml $(VAULT_FLAG) --check --diff $(EXTRA_ARGS)

syntax: _require_stack ## Syntax-check a stack (STACK=<name>)
	@printf "$(BLUE)Syntax check for $(STACK)...$(NC)\n"
	@$(ANSIBLE) -i $(INVENTORY) $(STACK).yml $(VAULT_FLAG) --syntax-check

_require_stack:
	@if [ -z "$(STACK)" ]; then \
		printf "$(RED)Error: STACK is required. e.g. make deploy STACK=petlibro$(NC)\n"; \
		exit 1; \
	fi
	@if [ ! -f "$(STACK).yml" ]; then \
		printf "$(RED)Error: $(STACK).yml not found in $(CURDIR)$(NC)\n"; \
		printf "Available: %s\n" "$(sort $(STACKS))"; \
		exit 1; \
	fi

# Per-stack shortcut targets so `make petlibro` works without STACK=…
# Each one just defers to the generic `deploy` rule.
$(STACKS):
	@$(MAKE) --no-print-directory deploy STACK=$@ EXTRA_ARGS="$(EXTRA_ARGS)"

.PHONY: $(STACKS)
