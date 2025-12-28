#!/usr/bin/env python3
import argparse
import os
from typing import Any, Dict, List, Tuple

import psycopg
import requests
import yaml


def to_pgvector_literal(vec: List[float]) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec) + "]"


def ollama_embed_one(ollama_url: str, model: str, text: str) -> List[float]:
    r = requests.post(
        f"{ollama_url.rstrip('/')}/api/embed",
        json={"model": model, "input": text},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["embeddings"][0]


def load_embedding_config(path: str) -> Tuple[str, int]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["model"], int(cfg["dims"])


def load_scenario(path: str, scenario: str) -> Dict[str, object]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["scenarios"][scenario]


def main() -> None:
    ap = argparse.ArgumentParser(description="Profile a representative hybrid query")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--embedding-config", default="config/embedding.yml")
    ap.add_argument("--evaluation-config", default="config/evaluation.yml")
    ap.add_argument("--scenario", default="S3_geo_text_vector")
    ap.add_argument("--query", default="カフェ")
    ap.add_argument("--lat", type=float, default=35.681236)
    ap.add_argument("--lon", type=float, default=139.767125)
    ap.add_argument("--radius", type=float, default=3000)
    args = ap.parse_args()

    if not args.dsn:
        raise SystemExit("DATABASE_URL is required")

    model, dims = load_embedding_config(args.embedding_config)
    scenario = load_scenario(args.evaluation_config, args.scenario)
    qvec = ollama_embed_one(args.ollama_url, model, args.query)
    if len(qvec) != dims:
        raise SystemExit("Embedding dimension mismatch")

    candidates = scenario.get("candidates", {})
    text_k = candidates.get("text_k", 50)
    vec_k = candidates.get("vec_k", 50)
    weights = scenario.get("weights", {"text": 0.7, "vector": 1.0, "geo": 0.2})

    sql = """
    EXPLAIN (ANALYZE, BUFFERS)
    WITH
    geo AS (
      SELECT p.place_id,
             ST_Distance(p.geog, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography) AS dist_m
      FROM search.places p
      WHERE ST_DWithin(p.geog, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, %(radius)s)
    ),
    text AS (
      SELECT p.place_id,
             row_number() OVER (ORDER BY pgroonga_score(p.tableoid, p.ctid) DESC) AS r_text
      FROM search.places p
      WHERE p.place_id IN (SELECT place_id FROM geo)
        AND p.text_for_search &@~ %(q)s
      ORDER BY pgroonga_score(p.tableoid, p.ctid) DESC
      LIMIT %(text_k)s
    ),
    vec AS (
      SELECT e.place_id,
             row_number() OVER (ORDER BY e.embedding <=> %(qvec)s) AS r_vec
      FROM search.place_embeddings e
      WHERE e.model = %(model)s
        AND e.place_id IN (SELECT place_id FROM geo)
      ORDER BY e.embedding <=> %(qvec)s
      LIMIT %(vec_k)s
    ),
    fused AS (
      SELECT
        COALESCE(text.place_id, vec.place_id) AS place_id,
        COALESCE(1.0 / (60 + text.r_text), 0.0) AS rrf_text,
        COALESCE(1.0 / (60 + vec.r_vec), 0.0) AS rrf_vec
      FROM text FULL OUTER JOIN vec USING (place_id)
    )
    SELECT f.place_id
    FROM fused f
    JOIN geo g USING (place_id)
    ORDER BY (%(w_text)s * f.rrf_text) + (%(w_vec)s * f.rrf_vec) + (%(w_geo)s * COALESCE(1 / (1 + g.dist_m), 0)) DESC
    LIMIT 20;
    """

    params: Dict[str, Any] = {
        "q": args.query,
        "qvec": to_pgvector_literal(qvec),
        "model": model,
        "text_k": text_k,
        "vec_k": vec_k,
        "w_text": weights.get("text", 0.7),
        "w_vec": weights.get("vector", 1.0),
        "w_geo": weights.get("geo", 0.2),
        "lat": args.lat,
        "lon": args.lon,
        "radius": args.radius,
    }

    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    print("\n".join(r[0] for r in rows))


if __name__ == "__main__":
    main()
