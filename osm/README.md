# OSM data

- データは Geofabrik の `kanto-latest.osm.pbf` を利用します。
- `make osm-download` で `osm/` 配下に取得します。
- PBF は Git 管理しません（`.gitignore` 参照）。

更新方針: Geofabrik の公開頻度に合わせて月次/必要時に差し替え。
