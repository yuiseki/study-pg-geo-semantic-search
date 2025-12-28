# study-pg-geo-semantic-search

PostgreSQL + PostGIS + PGroonga + pgvector だけで、OSM 由来の地理検索とテキスト/ベクトル検索のハイブリッドを検証するための研究用リポジトリです。

- Geo: PostGIS (ST_Within / ST_DWithin / KNN <->)
- Text: PGroonga (Tokenizer = TokenUnigram 固定)
- Vector: pgvector (model = snowflake-arctic-embed2:568m, dims = 1024 固定)

## クイックスタート

```bash
cp .env.example .env
make up
make osm-download
make osm-import
make transform MODE=focused
make embed
make search QUERY="台東区の床屋" REGION="台東区"
```

## ディレクトリ構成
```
.
├── config/          # 固定値と抽出/評価ルール
├── osm/             # OSM データ取得
├── infra/           # Dockerfile 群
├── db/init/         # DB 初期化 SQL
├── sql/             # 手動クエリ例
├── scripts/         # CLI 群
├── datasets/        # クエリ/評価データ
├── evaluations/     # 評価シナリオ/結果
└── docs/            # 仕様/設計メモ
```

## 前提
- Docker / Docker Compose
- Ollama (ローカルで `ollama serve` 済み)
- Python 3.11+ (CLI 利用時)
 - Postgres ポートは 5435 を使用（`.env` で変更可能）

## コマンド
- `make up` / `make down`
- `make osm-download`
- `make osm-import`
- `make transform MODE=focused|broad`
- `make embed`
- `make search QUERY=... REGION=... LAT=... LON=... RADIUS=...`
- `make evaluate`
- `make profile`

詳細は `docs/` を参照してください。
