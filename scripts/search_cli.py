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


def load_scenario(path: str, scenario: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["scenarios"][scenario]


def build_geo_cte(region: str, lat: float, lon: float, radius_m: float) -> Tuple[str, Dict[str, Any]]:
    params: Dict[str, Any] = {}
    if region:
        params["region"] = region
        cte = """
        geo AS (
          SELECT p.place_id,
                 NULL::double precision AS dist_m
          FROM search.places p
          JOIN search.admin_areas a
            ON ST_Within(p.point, a.geom)
          WHERE a.region_id = %(region)s OR a.name = %(region)s
        )
        """
        return cte, params

    if lat is not None and lon is not None:
        params.update({"lat": lat, "lon": lon, "radius_m": radius_m})
        cte = """
        geo AS (
          SELECT p.place_id,
                 ST_Distance(p.geog, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography) AS dist_m
          FROM search.places p
          WHERE ST_DWithin(p.geog, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, %(radius_m)s)
        )
        """
        return cte, params

    cte = """
    geo AS (
      SELECT p.place_id, NULL::double precision AS dist_m
      FROM search.places p
    )
    """
    return cte, params


def main() -> None:
    ap = argparse.ArgumentParser(description="Geo + text + vector search CLI")
    ap.add_argument("--query", required=True)
    ap.add_argument("--region", default="")
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    ap.add_argument("--radius", type=float, default=3000)
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--scenario", default="S3_geo_text_vector")
    ap.add_argument("--evaluation-config", default="config/evaluation.yml")
    ap.add_argument("--embedding-config", default="config/embedding.yml")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    args = ap.parse_args()

    if not args.dsn:
        raise SystemExit("DATABASE_URL is required")

    model, dims = load_embedding_config(args.embedding_config)
    scenario = load_scenario(args.evaluation_config, args.scenario)

    qvec = ollama_embed_one(args.ollama_url, model, args.query)
    if len(qvec) != dims:
        raise SystemExit(f"Expected {dims}-dim embedding, got {len(qvec)}")

    geo_cte, geo_params = build_geo_cte(args.region, args.lat, args.lon, args.radius)

    candidates = scenario.get("candidates", {})
    text_k = candidates.get("text_k", 50)
    vec_k = candidates.get("vec_k", 50)
    rrf_k = 60

    weights = scenario.get("weights", {"text": 0.7, "vector": 1.0, "geo": 0.2})

    sql = f"""
    WITH
    {geo_cte},
    text AS (
      SELECT p.place_id,
             row_number() OVER (ORDER BY pgroonga_score(p.tableoid, p.ctid) DESC) AS r_text,
             pgroonga_score(p.tableoid, p.ctid) AS s_text
      FROM search.places p
      WHERE p.place_id IN (SELECT place_id FROM geo)
        AND p.text_for_search &@~ %(q)s
        AND p.name IS NOT NULL
        AND p.name <> ''
      ORDER BY pgroonga_score(p.tableoid, p.ctid) DESC
      LIMIT %(text_k)s
    ),
    vec AS (
      SELECT e.place_id,
             row_number() OVER (ORDER BY e.embedding <=> %(qvec)s) AS r_vec,
             1 - (e.embedding <=> %(qvec)s) AS s_vec
      FROM search.place_embeddings e
      JOIN search.places p ON p.place_id = e.place_id
      WHERE e.model = %(model)s
        AND e.place_id IN (SELECT place_id FROM geo)
        AND p.name IS NOT NULL
        AND p.name <> ''
      ORDER BY e.embedding <=> %(qvec)s
      LIMIT %(vec_k)s
    ),
    fused AS (
      SELECT
        COALESCE(text.place_id, vec.place_id) AS place_id,
        COALESCE(text.s_text, 0) AS s_text,
        COALESCE(vec.s_vec, 0) AS s_vec,
        COALESCE(1.0 / (%(rrf_k)s + text.r_text), 0.0) AS rrf_text,
        COALESCE(1.0 / (%(rrf_k)s + vec.r_vec), 0.0) AS rrf_vec
      FROM text FULL OUTER JOIN vec USING (place_id)
    )
    SELECT
      p.place_id,
      p.name,
      p.category,
      g.dist_m,
      f.s_text,
      f.s_vec,
      (%(w_text)s * f.rrf_text) + (%(w_vec)s * f.rrf_vec) + (%(w_geo)s * COALESCE(1 / (1 + g.dist_m), 0)) AS final_score
    FROM fused f
    JOIN search.places p USING (place_id)
    JOIN geo g USING (place_id)
    ORDER BY final_score DESC
    LIMIT %(limit)s;
    """

    params: Dict[str, Any] = {
        "q": args.query,
        "qvec": to_pgvector_literal(qvec),
        "model": model,
        "text_k": text_k,
        "vec_k": vec_k,
        "rrf_k": rrf_k,
        "limit": args.limit,
        "w_text": weights.get("text", 0.7),
        "w_vec": weights.get("vector", 1.0),
        "w_geo": weights.get("geo", 0.2),
    }
    params.update(geo_params)

    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    print("place_id | name | category | dist_m | s_text | s_vec | final_score")
    print("-" * 120)
    for row in rows:
        place_id, name, category, dist_m, s_text, s_vec, final_score = row
        print(f"{place_id} | {name} | {category} | {dist_m} | {s_text} | {s_vec} | {final_score}")


if __name__ == "__main__":
    main()
