SHELL := /bin/bash
.PHONY: help init-env secrets render deploy deploy-deps deploy-users deploy-db install-app \
        setup-config migrate create-admin regenerate-all install-systemd install-sudoers install-nginx \
        restart status broker-status logs chmod-scripts check-scripts uninstall uninstall-keep-db update

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

init-env: ## Copy deploy/env.example → deploy/.env
	cp deploy/env.example deploy/.env
	@echo "Edit deploy/.env (VCP_TASK_BROKER_WHL, domains, paths)"

secrets: ## Generate secrets in deploy/.env
	bash deploy/scripts/generate-secrets.sh

render: ## Render templates → deploy/output/
	bash deploy/scripts/render.sh

deploy: ## Full production deploy (sudo)
	sudo bash deploy/scripts/deploy.sh

deploy-quick: ## Deploy without apt/nginx/admin prompts
	sudo bash deploy/scripts/deploy.sh --skip-deps --skip-nginx --skip-admin

deploy-deps: ## Install apt packages (root)
	sudo bash deploy/scripts/install-deps.sh

deploy-users: ## Create OS users and directories (root)
	sudo bash deploy/scripts/setup-users.sh

deploy-db: ## Create PostgreSQL role and database (root)
	sudo bash deploy/scripts/setup-postgres.sh

install-app: ## Install venv + pip packages (root)
	sudo bash deploy/scripts/install-app.sh

setup-config: ## Render and install panel.yaml / broker.yaml (root)
	sudo bash deploy/scripts/setup-config.sh

migrate: ## Run alembic upgrade head (root)
	sudo bash deploy/scripts/migrate.sh

create-admin: ## Create admin user (sudo; optional: USERNAME=alice)
	sudo bash deploy/scripts/create-admin.sh $(USERNAME)

regenerate-all: ## Queue regenerate for all active configs (sudo)
	sudo bash deploy/scripts/regenerate-all-configs.sh

install-systemd: ## Install and start systemd units (root)
	sudo bash deploy/scripts/install-systemd.sh

install-sudoers: ## Install worker sudoers (root)
	sudo bash deploy/scripts/install-sudoers.sh

fix-config-perms: ## Fix panel.yaml permissions for worker (root)
	sudo bash deploy/scripts/fix-config-perms.sh

install-nginx: ## Install nginx site config (root)
	sudo bash deploy/scripts/install-nginx.sh

restart: ## Restart all panel services
	sudo bash deploy/scripts/panel-services.sh restart

status: ## Show service status
	bash deploy/scripts/panel-services.sh status

broker-status: ## Broker task counts (pending, waiting, done, dead)
	bash deploy/scripts/broker-status.sh

logs: ## Tail service logs
	sudo bash deploy/scripts/panel-services.sh logs

chmod-scripts: ## Mark deploy scripts executable (local dev only; not used on server)
	chmod +x deploy/scripts/*.sh

check-scripts: ## Syntax-check deploy scripts
	@for f in deploy/scripts/*.sh; do bash -n "$$f" && echo "OK $$f"; done

uninstall: ## Remove panel services, configs, data (sudo; reads deploy/.env)
	sudo bash deploy/scripts/uninstall.sh

uninstall-keep-db: ## Uninstall but keep PostgreSQL database
	sudo bash deploy/scripts/uninstall.sh --keep-db

update: ## Apply updates after git pull (sudo)
	sudo bash deploy/scripts/update.sh

update-quick: ## Update without git pull / nginx
	sudo bash deploy/scripts/update.sh --no-pull --skip-nginx
