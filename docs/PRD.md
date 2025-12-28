# PRD

## 1. 概要
OpenStreetMap（Geofabrik の `kanto-latest.osm.pbf`）を PostGIS に取り込み、
PostgreSQL 単体で geo-semantic + hybrid 検索を再現性高く検証する研究用リポジトリ。

- Geo: PostGIS（ST_Within / ST_DWithin / KNN <->）
- Text: PGroonga（Tokenizer = TokenUnigram 固定）
- Vector: pgvector（Embedding model = snowflake-arctic-embed2:568m, dims=1024 固定）

## 2. ゴール
### 2.1 機能ゴール
1) OSM PBF（関東）をワンコマンドで取得し、PostGISに取り込める
2) raw層（OSM由来のタグ＋geom）から検索用 `search.places` を生成できる
3) geo pre-filter を前提に、PGroonga×pgvector のハイブリッド候補生成ができる
4) 距離をランキングに混ぜる rerank を実装し、効果を評価できる
5) 設計（スキーマ/インデックス/クエリ）を中心に、比較・再現ができる

### 2.2 非ゴール
- 地図UI/可視化、APIサーバ、Text-to-SQL
- 同義語辞書運用、クエリ拡張

## 3. 固定要件
- Data source: Geofabrik `kanto-latest.osm.pbf`
- PGroonga tokenizer: TokenUnigram 固定
- Embedding model: snowflake-arctic-embed2:568m 固定
- Embedding dimension: 1024 固定

## 4. パイプライン
- download: `make osm-download`
- import: `make osm-import`
- transform: `make transform MODE=focused|broad`

## 5. スキーマ概要
- raw.* : OSM のほぼ生データ
- search.places / search.place_embeddings / search.admin_areas

## 6. 評価
- nDCG@10 / MRR@10 / Recall@50
- EXPLAIN ANALYZE と index 利用状況
