#!/usr/bin/env python3
import argparse
import os
from typing import Iterable, List, Tuple

import psycopg
import requests
import yaml


def load_embedding_config(path: str) -> Tuple[str, int]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["model"], int(cfg["dims"])


def fetch_places(conn: psycopg.Connection, model: str, limit: int, force: bool) -> Iterable[Tuple[int, str]]:
    if force:
        sql = "SELECT place_id, text_for_search FROM search.places ORDER BY place_id LIMIT %s"
        params = (limit,)
    else:
        sql = """
        SELECT p.place_id, p.text_for_search
        FROM search.places p
        LEFT JOIN search.place_embeddings e
          ON p.place_id = e.place_id AND e.model = %s
        WHERE e.place_id IS NULL
        ORDER BY p.place_id
        LIMIT %s
        """
        params = (model, limit)

    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def ollama_embed(ollama_url: str, model: str, texts: List[str]) -> List[List[float]]:
    r = requests.post(
        f"{ollama_url.rstrip('/')}/api/embed",
        json={"model": model, "input": texts},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()["embeddings"]


def to_pgvector_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def main() -> None:
    ap = argparse.ArgumentParser(description="Embed places with Ollama")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--config", default="config/embedding.yml")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--limit", type=int, default=100000)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    if not args.dsn:
        raise SystemExit("DATABASE_URL is required")

    model, dims = load_embedding_config(args.config)

    with psycopg.connect(args.dsn) as conn:
        offset = 0
        while True:
            rows = fetch_places(conn, model, args.batch_size, args.force)
            if not rows:
                break

            place_ids, texts = zip(*rows)
            embeddings = ollama_embed(args.ollama_url, model, list(texts))
            if any(len(vec) != dims for vec in embeddings):
                raise SystemExit("Embedding dimension mismatch")

            with conn.cursor() as cur:
                for place_id, vec in zip(place_ids, embeddings):
                    cur.execute(
                        """
                        INSERT INTO search.place_embeddings (place_id, model, embedding)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (place_id, model) DO UPDATE
                        SET embedding = EXCLUDED.embedding, created_at = now()
                        """,
                        (place_id, model, to_pgvector_literal(vec)),
                    )
            conn.commit()

            offset += len(rows)
            if offset >= args.limit:
                break


if __name__ == "__main__":
    main()
