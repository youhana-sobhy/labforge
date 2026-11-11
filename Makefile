.PHONY: install dev run test lint integration ci-labs docker up down

install:        ## install LabForge
	pip install .

dev:            ## editable install with test tools
	pip install -e ".[dev]"

run:            ## start the web UI on http://localhost:8080
	labforge serve

lint:
	ruff check .

test:           ## fast tests, no Docker needed
	pytest -q

integration:    ## boot every template and run its tests (needs Docker)
	pytest -q -m integration

ci-labs:        ## same as CI: launch, test and destroy every template
	labforge test

up:             ## run LabForge in Docker
	docker compose up -d --build

down:
	docker compose down
