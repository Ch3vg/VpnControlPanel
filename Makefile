SHELL := /bin/bash
.PHONY: help init-env secrets render deploy deploy-deps deploy-users deploy-db install-app \
        setup-config migrate create-admin install-systemd install-sudoers install-nginx \
        restart status logs chmod-scripts check-scripts uninstall uninstall-keep-db update

help: ## Show available targets
	@grep -E '^[a-zA-Z0-9_-]+:.*##' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

init-env: ## Copy deploy/env.example → deploy/.env
	cp deploy/env.example deploy/.env
	@echo "Edit deploy/.env (VCP_TASK_BROKER_WHL, domains, paths)"

secrets: chmod-scripts ## Generate secrets in deploy/.env
	deploy/scripts/generate-secrets.sh

render: chmod-scripts ## Render templates → deploy/output/
	deploy/scripts/render.sh

deploy: chmod-scripts ## Full production deploy (sudo)
	sudo deploy/scripts/deploy.sh

deploy-quick: chmod-scripts ## Deploy without apt/nginx/admin prompts
	sudo deploy/scripts/deploy.sh --skip-deps --skip-nginx --skip-admin

deploy-deps: chmod-scripts ## Install apt packages (root)
	sudo deploy/scripts/install-deps.sh

deploy-users: chmod-scripts ## Create OS users and directories (root)
	sudo deploy/scripts/setup-users.sh

deploy-db: chmod-scripts ## Create PostgreSQL role and database (root)
	sudo deploy/scripts/setup-postgres.sh

install-app: chmod-scripts ## Install venv + pip packages (root)
	sudo deploy/scripts/install-app.sh

setup-config: chmod-scripts ## Render and install panel.yaml / broker.yaml (root)
	sudo deploy/scripts/setup-config.sh

migrate: chmod-scripts ## Run alembic upgrade head (root)
	sudo deploy/scripts/migrate.sh

create-admin: chmod-scripts ## Create first admin user (root)
	sudo deploy/scripts/create-admin.sh

install-systemd: chmod-scripts ## Install and start systemd units (root)
	sudo deploy/scripts/install-systemd.sh

install-sudoers: chmod-scripts ## Install worker sudoers (root)
	sudo deploy/scripts/install-sudoers.sh

fix-config-perms: chmod-scripts ## Fix panel.yaml permissions for worker (root)
	sudo deploy/scripts/fix-config-perms.sh

install-nginx: chmod-scripts ## Install nginx site config (root)
	sudo deploy/scripts/install-nginx.sh

restart: ## Restart all panel services
	sudo systemctl restart vpn-broker vpn-api vpn-worker

status: ## Show service status
	systemctl status vpn-broker vpn-api vpn-worker --no-pager || true

logs: ## Tail service logs
	sudo journalctl -u vpn-api -u vpn-worker -u vpn-broker -f

chmod-scripts: ## Mark deploy scripts executable
	chmod +x deploy/scripts/*.sh

check-scripts: chmod-scripts ## Syntax-check deploy scripts
	@for f in deploy/scripts/*.sh; do bash -n "$$f" && echo "OK $$f"; done

uninstall: chmod-scripts ## Remove panel services, configs, data (sudo; reads deploy/.env)
	sudo deploy/scripts/uninstall.sh

uninstall-keep-db: chmod-scripts ## Uninstall but keep PostgreSQL database
	sudo deploy/scripts/uninstall.sh --keep-db

update: chmod-scripts ## Apply updates after git pull (sudo)
	sudo deploy/scripts/update.sh

update-quick: chmod-scripts ## Update without git pull / nginx
	sudo deploy/scripts/update.sh --no-pull --skip-nginx
