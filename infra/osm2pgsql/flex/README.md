# osm2pgsql flex

- `raw.lua` は OSM の nodes/ways/relations を `raw` スキーマへ投入するための最小構成です。
- 目的は「OSM をなるべく失わず保持」することなので、tags は jsonb で保持します。
- 変換ロジックは `scripts/transform.py` で `search` スキーマに反映します。
