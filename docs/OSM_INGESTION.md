# OSM Ingestion

1. `make osm-download`
2. `make osm-import`
3. `make transform MODE=focused|broad`

`infra/osm2pgsql/flex/raw.lua` が raw スキーマのベース定義です。
