SHELL := /bin/bash

POSTGRES_PORT ?= 5435
POSTGRES_DB ?= geo_search
POSTGRES_USER ?= postgres
POSTGRES_PASSWORD ?= postgres
DATABASE_URL ?= postgresql://$(POSTGRES_USER):$(POSTGRES_PASSWORD)@localhost:$(POSTGRES_PORT)/$(POSTGRES_DB)
OLLAMA_URL ?= http://localhost:11434
OSM_PBF_PATH ?= ./osm/kanto-latest.osm.pbf

.PHONY: up down logs psql osm-download osm-import transform embed search evaluate profile clean

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

psql:
	docker compose exec db psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

osm-download:
	./osm/download.sh $(OSM_PBF_PATH)

osm-import:
	@echo "Importing $(OSM_PBF_PATH) into PostGIS (raw schema)"
	@docker compose run --rm \
		-e PGPASSWORD=$(POSTGRES_PASSWORD) \
		osm2pgsql \
		"osm2pgsql -H db -U $(POSTGRES_USER) -d $(POSTGRES_DB) -P 5432 \
		--create --slim --output=flex --style /flex/raw.lua /data/$(notdir $(OSM_PBF_PATH))"

transform:
	@python scripts/transform.py --mode $(MODE) --dsn $(DATABASE_URL)

embed:
	@python scripts/embed_places.py --dsn $(DATABASE_URL) --ollama-url $(OLLAMA_URL)

search:
	@python scripts/search_cli.py --dsn $(DATABASE_URL) --ollama-url $(OLLAMA_URL) \
		--query "$(QUERY)" --region "$(REGION)" --lat "$(LAT)" --lon "$(LON)" --radius "$(RADIUS)"

evaluate:
	@python scripts/evaluate.py --dsn $(DATABASE_URL) --ollama-url $(OLLAMA_URL)

profile:
	@python scripts/profile.py --dsn $(DATABASE_URL)

clean:
	rm -rf ./db/data
