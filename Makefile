# Homelab Ansible Makefile
.PHONY: help deploy-all deploy-infra deploy-media check syntax lint encrypt decrypt edit-vault clean test list-hosts list-tags

# Colors for output
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[0;33m
BLUE := \033[0;34m
NC := \033[0m # No Color

# Variables
ANSIBLE := ansible-playbook
INVENTORY := inventory/hosts.yml
VAULT_PASS := ~/.ansible-vault-pass
ANSIBLE_CONFIG := ansible.cfg

# Check if vault password file exists
VAULT_FLAG := $(if $(wildcard $(VAULT_PASS)),--vault-password-file $(VAULT_PASS),--ask-vault-pass)

##@ General

help: ## Display this help message
	@echo "$(BLUE)Homelab Ansible Deployment$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make $(GREEN)<target>$(NC)\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(YELLOW)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

setup: ## Initial setup - create ansible.cfg and vault password file
	@echo "$(BLUE)Setting up Ansible configuration...$(NC)"
	@if [ ! -f ansible.cfg ]; then \
		echo "[defaults]" > ansible.cfg; \
		echo "inventory = $(INVENTORY)" >> ansible.cfg; \
		echo "vault_password_file = $(VAULT_PASS)" >> ansible.cfg; \
		echo "host_key_checking = False" >> ansible.cfg; \
		echo "retry_files_enabled = False" >> ansible.cfg; \
		echo "$(GREEN)Created ansible.cfg$(NC)"; \
	else \
		echo "$(YELLOW)ansible.cfg already exists$(NC)"; \
	fi
	@if [ ! -f $(VAULT_PASS) ]; then \
		read -p "Enter vault password: " pass; \
		echo $$pass > $(VAULT_PASS); \
		chmod 600 $(VAULT_PASS); \
		echo "$(GREEN)Created vault password file at $(VAULT_PASS)$(NC)"; \
	else \
		echo "$(YELLOW)Vault password file already exists$(NC)"; \
	fi

##@ Deployment - Full Stack

deploy-all: ## Deploy entire homelab infrastructure
	@echo "$(BLUE)Deploying entire homelab...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/all.yml $(VAULT_FLAG)

deploy-all-check: ## Dry-run of full deployment
	@echo "$(BLUE)Checking full deployment (dry-run)...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/all.yml $(VAULT_FLAG) --check --diff

deploy-prerequisites: ## Deploy prerequisites (Docker, networks, volumes)
	@echo "$(BLUE)Deploying prerequisites...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/prerequisites.yml $(VAULT_FLAG)

##@ Deployment - Infrastructure

deploy-infra: ## Deploy all infrastructure (core + gateway)
	@echo "$(BLUE)Deploying infrastructure stack...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/all.yml $(VAULT_FLAG) --tags infra

deploy-infra-core: ## Deploy infrastructure core (Komodo, MongoDB)
	@echo "$(BLUE)Deploying infrastructure core...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/infra_core.yml $(VAULT_FLAG)

deploy-infra-gateway: ## Deploy infrastructure gateway (Traefik, AdGuard, etc.)
	@echo "$(BLUE)Deploying infrastructure gateway...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/infra_gateway.yml $(VAULT_FLAG)

##@ Deployment - Media

deploy-media: ## Deploy all media services (acquisition + consumption)
	@echo "$(BLUE)Deploying media stack...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/all.yml $(VAULT_FLAG) --tags media

deploy-media-acquisition: ## Deploy media acquisition (Sonarr, Radarr, etc.)
	@echo "$(BLUE)Deploying media acquisition...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/media_acquisition.yml $(VAULT_FLAG)

deploy-media-consumption: ## Deploy media consumption (Plex, Kavita, etc.)
	@echo "$(BLUE)Deploying media consumption...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/media_consumption.yml $(VAULT_FLAG)

##@ Deployment - Future Stacks

deploy-content: ## Deploy content management stack
	@echo "$(BLUE)Deploying content management...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/content_management.yml $(VAULT_FLAG)

deploy-dev: ## Deploy development stack
	@echo "$(BLUE)Deploying development stack...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/development.yml $(VAULT_FLAG)

deploy-productivity: ## Deploy productivity stack
	@echo "$(BLUE)Deploying productivity stack...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/productivity.yml $(VAULT_FLAG)

deploy-social: ## Deploy social stack
	@echo "$(BLUE)Deploying social stack...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/social.yml $(VAULT_FLAG)

##@ Deployment - Specific Services

deploy-traefik: ## Deploy only Traefik
	@echo "$(BLUE)Deploying Traefik...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/infra_gateway.yml $(VAULT_FLAG) --tags traefik

deploy-plex: ## Deploy only Plex
	@echo "$(BLUE)Deploying Plex...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/media_consumption.yml $(VAULT_FLAG) --tags plex

deploy-sonarr: ## Deploy only Sonarr
	@echo "$(BLUE)Deploying Sonarr...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/media_acquisition.yml $(VAULT_FLAG) --tags sonarr

deploy-radarr: ## Deploy only Radarr
	@echo "$(BLUE)Deploying Radarr...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/media_acquisition.yml $(VAULT_FLAG) --tags radarr

##@ Testing & Validation

check: syntax lint ## Run all checks (syntax + lint)

syntax: ## Check playbook syntax
	@echo "$(BLUE)Checking syntax...$(NC)"
	@for playbook in deploy/*.yml; do \
		echo "Checking $$playbook..."; \
		ansible-playbook $$playbook --syntax-check $(VAULT_FLAG) || exit 1; \
	done
	@echo "$(GREEN)All playbooks passed syntax check$(NC)"

lint: ## Lint playbooks with ansible-lint
	@echo "$(BLUE)Linting playbooks...$(NC)"
	@if command -v ansible-lint >/dev/null 2>&1; then \
		ansible-lint deploy/*.yml || true; \
	else \
		echo "$(YELLOW)ansible-lint not installed. Install with: pip install ansible-lint$(NC)"; \
	fi

dry-run: ## Dry-run full deployment (check mode)
	@echo "$(BLUE)Running dry-run of full deployment...$(NC)"
	@$(ANSIBLE) -i $(INVENTORY) deploy/all.yml $(VAULT_FLAG) --check --diff

test-connection: ## Test SSH connection to all hosts
	@echo "$(BLUE)Testing connection to all hosts...$(NC)"
	@ansible all -i $(INVENTORY) -m ping

##@ Vault Management

encrypt: ## Encrypt a vault file (usage: make encrypt FILE=path/to/file)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)Error: FILE parameter required. Usage: make encrypt FILE=path/to/file$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Encrypting $(FILE)...$(NC)"
	@ansible-vault encrypt $(FILE) $(VAULT_FLAG)

decrypt: ## Decrypt a vault file (usage: make decrypt FILE=path/to/file)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)Error: FILE parameter required. Usage: make decrypt FILE=path/to/file$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Decrypting $(FILE)...$(NC)"
	@ansible-vault decrypt $(FILE) $(VAULT_FLAG)

edit-vault: ## Edit encrypted vault file (usage: make edit-vault FILE=path/to/file)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)Error: FILE parameter required. Usage: make edit-vault FILE=path/to/file$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Editing $(FILE)...$(NC)"
	@ansible-vault edit $(FILE) $(VAULT_FLAG)

view-vault: ## View encrypted vault file (usage: make view-vault FILE=path/to/file)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)Error: FILE parameter required. Usage: make view-vault FILE=path/to/file$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Viewing $(FILE)...$(NC)"
	@ansible-vault view $(FILE) $(VAULT_FLAG)

rekey-vault: ## Change vault password for a file (usage: make rekey-vault FILE=path/to/file)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)Error: FILE parameter required. Usage: make rekey-vault FILE=path/to/file$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Rekeying $(FILE)...$(NC)"
	@ansible-vault rekey $(FILE) $(VAULT_FLAG)

##@ Information

list-hosts: ## List all hosts in inventory
	@echo "$(BLUE)Listing all hosts...$(NC)"
	@ansible all -i $(INVENTORY) --list-hosts

list-groups: ## List all groups in inventory
	@echo "$(BLUE)Listing all groups...$(NC)"
	@ansible localhost -i $(INVENTORY) -m debug -a "var=groups.keys()"

list-tags: ## List all available tags (usage: make list-tags PLAYBOOK=deploy/all.yml)
	@PLAYBOOK=$${PLAYBOOK:-deploy/all.yml}; \
	echo "$(BLUE)Listing tags in $$PLAYBOOK...$(NC)"; \
	ansible-playbook $$PLAYBOOK --list-tags $(VAULT_FLAG)

list-tasks: ## List all tasks in a playbook (usage: make list-tasks PLAYBOOK=deploy/all.yml)
	@PLAYBOOK=$${PLAYBOOK:-deploy/all.yml}; \
	echo "$(BLUE)Listing tasks in $$PLAYBOOK...$(NC)"; \
	ansible-playbook $$PLAYBOOK --list-tasks $(VAULT_FLAG)

show-vars: ## Show variables for a host (usage: make show-vars HOST=mini)
	@if [ -z "$(HOST)" ]; then \
		echo "$(RED)Error: HOST parameter required. Usage: make show-vars HOST=hostname$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Showing variables for $(HOST)...$(NC)"
	@ansible -i $(INVENTORY) $(HOST) -m debug -a "var=hostvars[inventory_hostname]" $(VAULT_FLAG)

##@ Advanced Deployment

deploy-limit: ## Deploy to specific host (usage: make deploy-limit HOST=mini PLAYBOOK=deploy/all.yml)
	@if [ -z "$(HOST)" ]; then \
		echo "$(RED)Error: HOST parameter required. Usage: make deploy-limit HOST=hostname$(NC)"; \
		exit 1; \
	fi
	@PLAYBOOK=$${PLAYBOOK:-deploy/all.yml}; \
	echo "$(BLUE)Deploying $$PLAYBOOK to $(HOST)...$(NC)"; \
	$(ANSIBLE) -i $(INVENTORY) $$PLAYBOOK $(VAULT_FLAG) --limit $(HOST)

deploy-tags: ## Deploy specific tags (usage: make deploy-tags TAGS=traefik,plex PLAYBOOK=deploy/all.yml)
	@if [ -z "$(TAGS)" ]; then \
		echo "$(RED)Error: TAGS parameter required. Usage: make deploy-tags TAGS=tag1,tag2$(NC)"; \
		exit 1; \
	fi
	@PLAYBOOK=$${PLAYBOOK:-deploy/all.yml}; \
	echo "$(BLUE)Deploying tags: $(TAGS) from $$PLAYBOOK...$(NC)"; \
	$(ANSIBLE) -i $(INVENTORY) $$PLAYBOOK $(VAULT_FLAG) --tags $(TAGS)

deploy-skip-tags: ## Skip specific tags (usage: make deploy-skip-tags TAGS=traefik,plex PLAYBOOK=deploy/all.yml)
	@if [ -z "$(TAGS)" ]; then \
		echo "$(RED)Error: TAGS parameter required. Usage: make deploy-skip-tags TAGS=tag1,tag2$(NC)"; \
		exit 1; \
	fi
	@PLAYBOOK=$${PLAYBOOK:-deploy/all.yml}; \
	echo "$(BLUE)Deploying $$PLAYBOOK, skipping tags: $(TAGS)...$(NC)"; \
	$(ANSIBLE) -i $(INVENTORY) $$PLAYBOOK $(VAULT_FLAG) --skip-tags $(TAGS)

deploy-verbose: ## Deploy with verbose output (usage: make deploy-verbose PLAYBOOK=deploy/all.yml)
	@PLAYBOOK=$${PLAYBOOK:-deploy/all.yml}; \
	echo "$(BLUE)Deploying $$PLAYBOOK with verbose output...$(NC)"; \
	$(ANSIBLE) -i $(INVENTORY) $$PLAYBOOK $(VAULT_FLAG) -vvv

deploy-step: ## Deploy with step-by-step confirmation (usage: make deploy-step PLAYBOOK=deploy/all.yml)
	@PLAYBOOK=$${PLAYBOOK:-deploy/all.yml}; \
	echo "$(BLUE)Deploying $$PLAYBOOK with step-by-step confirmation...$(NC)"; \
	$(ANSIBLE) -i $(INVENTORY) $$PLAYBOOK $(VAULT_FLAG) --step

##@ Maintenance

update-roles: ## Update Ansible Galaxy roles
	@echo "$(BLUE)Updating Ansible Galaxy roles...$(NC)"
	@if [ -f requirements.yml ]; then \
		ansible-galaxy install -r requirements.yml --force; \
	else \
		echo "$(YELLOW)No requirements.yml found$(NC)"; \
	fi

clean: ## Clean up temporary files and caches
	@echo "$(BLUE)Cleaning up...$(NC)"
	@find . -type f -name "*.retry" -delete
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ansible" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(GREEN)Cleanup complete$(NC)"

restart-all: ## Restart all Docker containers on all hosts
	@echo "$(YELLOW)Warning: This will restart all Docker containers!$(NC)"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		ansible all -i $(INVENTORY) -m shell -a "docker restart \$$(docker ps -q)" --become; \
	else \
		echo "$(RED)Aborted$(NC)"; \
	fi

stop-all: ## Stop all Docker containers on all hosts
	@echo "$(YELLOW)Warning: This will stop all Docker containers!$(NC)"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		ansible all -i $(INVENTORY) -m shell -a "docker stop \$$(docker ps -q)" --become; \
	else \
		echo "$(RED)Aborted$(NC)"; \
	fi

##@ Docker Management

docker-ps: ## Show running containers on all hosts
	@echo "$(BLUE)Showing running containers...$(NC)"
	@ansible all -i $(INVENTORY) -m shell -a "docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'"

docker-images: ## Show Docker images on all hosts
	@echo "$(BLUE)Showing Docker images...$(NC)"
	@ansible all -i $(INVENTORY) -m shell -a "docker images"

docker-prune: ## Prune unused Docker resources on all hosts
	@echo "$(YELLOW)Warning: This will remove unused Docker resources!$(NC)"
	@read -p "Are you sure? (y/N): " confirm; \
	if [ "$$confirm" = "y" ] || [ "$$confirm" = "Y" ]; then \
		ansible all -i $(INVENTORY) -m shell -a "docker system prune -af" --become; \
	else \
		echo "$(RED)Aborted$(NC)"; \
	fi

docker-logs: ## View logs for a container (usage: make docker-logs HOST=mini CONTAINER=traefik)
	@if [ -z "$(CONTAINER)" ]; then \
		echo "$(RED)Error: CONTAINER parameter required. Usage: make docker-logs HOST=mini CONTAINER=name$(NC)"; \
		exit 1; \
	fi
	@HOST=$${HOST:-all}; \
	echo "$(BLUE)Viewing logs for $(CONTAINER) on $$HOST...$(NC)"; \
	ansible $$HOST -i $(INVENTORY) -m shell -a "docker logs --tail 50 $(CONTAINER)"

##@ Development

create-role: ## Create a new Ansible role (usage: make create-role ROLE=my_role)
	@if [ -z "$(ROLE)" ]; then \
		echo "$(RED)Error: ROLE parameter required. Usage: make create-role ROLE=role_name$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Creating role: $(ROLE)...$(NC)"
	@ansible-galaxy init roles/$(ROLE)
	@echo "$(GREEN)Role $(ROLE) created in roles/$(ROLE)$(NC)"

create-playbook: ## Create a new deployment playbook (usage: make create-playbook STACK=stack_name)
	@if [ -z "$(STACK)" ]; then \
		echo "$(RED)Error: STACK parameter required. Usage: make create-playbook STACK=stack_name$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Creating playbook: deploy-$(STACK).yml...$(NC)"
	@echo "---" > deploy-$(STACK).yml
	@echo "- name: Deploy $(STACK) stack" >> deploy-$(STACK).yml
	@echo "  hosts: compute_servers" >> deploy-$(STACK).yml
	@echo "  become: true" >> deploy-$(STACK).yml
	@echo "  roles:" >> deploy-$(STACK).yml
	@echo "    - $(STACK)" >> deploy-$(STACK).yml
	@echo "$(GREEN)Playbook deploy-$(STACK).yml created$(NC)"

graph: ## Generate dependency graph (requires ansible-inventory-grapher)
	@echo "$(BLUE)Generating inventory graph...$(NC)"
	@if command -v ansible-inventory-grapher >/dev/null 2>&1; then \
		ansible-inventory-grapher -i $(INVENTORY) all | dot -Tpng > inventory-graph.png; \
		echo "$(GREEN)Graph saved to inventory-graph.png$(NC)"; \
	else \
		echo "$(YELLOW)ansible-inventory-grapher not installed. Install with: pip install ansible-inventory-grapher$(NC)"; \
	fi

##@ Quick Access (Shortcuts)

infra: deploy-infra ## Shortcut for deploy-infra
media: deploy-media ## Shortcut for deploy-media
all: deploy-all ## Shortcut for deploy-all
