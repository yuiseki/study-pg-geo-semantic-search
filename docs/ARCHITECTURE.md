# Architecture

- Docker Compose: Postgres (PostGIS + PGroonga + pgvector)
- osm2pgsql (flex) で raw スキーマへ投入
- transform で search スキーマへ整形
- Ollama で埋め込み生成
