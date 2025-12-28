#!/usr/bin/env python3
import argparse
import json
import os
from typing import Dict, List, Tuple

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


def load_queries(path: str) -> List[Dict[str, object]]:
    queries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            queries.append(json.loads(line))
    return queries


def load_qrels(path: str) -> Dict[str, Dict[str, int]]:
    qrels: Dict[str, Dict[str, int]] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            qid, pid, rel = line.split("\t")
            qrels.setdefault(qid, {})[pid] = int(rel)
    return qrels


def search(conn: psycopg.Connection, query: str, region: str, lat: float, lon: float, radius: float,
           model: str, dims: int, scenario: Dict[str, object], qvec: List[float]) -> List[int]:
    candidates = scenario.get("candidates", {})
    text_k = candidates.get("text_k", 50)
    vec_k = candidates.get("vec_k", 50)
    weights = scenario.get("weights", {"text": 0.7, "vector": 1.0, "geo": 0.2})

    if region and (lat is None or lon is None):
        geo_cte = """
        geo AS (
          SELECT p.place_id,
                 NULL::double precision AS dist_m
          FROM search.places p
          JOIN search.admin_areas a
            ON ST_Within(p.point, a.geom)
          WHERE a.region_id = %(region)s OR a.name = %(region)s
        )
        """
    else:
        geo_cte = """
        geo AS (
          SELECT p.place_id,
                 ST_Distance(p.geog, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography) AS dist_m
          FROM search.places p
          WHERE ST_DWithin(p.geog, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography, %(radius)s)
        )
        """
    params: Dict[str, object] = {
        "q": query,
        "qvec": to_pgvector_literal(qvec),
        "model": model,
        "text_k": text_k,
        "vec_k": vec_k,
        "rrf_k": 60,
        "limit": 50,
        "w_text": weights.get("text", 0.7),
        "w_vec": weights.get("vector", 1.0),
        "w_geo": weights.get("geo", 0.2),
        "lat": lat,
        "lon": lon,
        "radius": radius,
        "region": region,
    }

    sql = f"""
    WITH
    {geo_cte},
    text AS (
      SELECT p.place_id,
             row_number() OVER (ORDER BY pgroonga_score(p.tableoid, p.ctid) DESC) AS r_text
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
             row_number() OVER (ORDER BY e.embedding <=> %(qvec)s) AS r_vec
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
        COALESCE(1.0 / (%(rrf_k)s + text.r_text), 0.0) AS rrf_text,
        COALESCE(1.0 / (%(rrf_k)s + vec.r_vec), 0.0) AS rrf_vec
      FROM text FULL OUTER JOIN vec USING (place_id)
    )
    SELECT f.place_id
    FROM fused f
    JOIN geo g USING (place_id)
    ORDER BY (%(w_text)s * f.rrf_text) + (%(w_vec)s * f.rrf_vec) + (%(w_geo)s * COALESCE(1 / (1 + g.dist_m), 0)) DESC
    LIMIT %(limit)s;
    """

    with conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [int(r[0]) for r in rows]


def ndcg_at_k(ranked: List[int], rels: Dict[str, int], k: int) -> float:
    def dcg(scores: List[int]) -> float:
        return sum((2 ** s - 1) / (i + 2) for i, s in enumerate(scores))

    gains = [rels.get(str(pid), 0) for pid in ranked[:k]]
    ideal = sorted(rels.values(), reverse=True)[:k]
    return dcg(gains) / dcg(ideal) if ideal else 0.0


def mrr_at_k(ranked: List[int], rels: Dict[str, int], k: int) -> float:
    for i, pid in enumerate(ranked[:k], start=1):
        if rels.get(str(pid), 0) > 0:
            return 1.0 / i
    return 0.0


def recall_at_k(ranked: List[int], rels: Dict[str, int], k: int) -> float:
    if not rels:
        return 0.0
    hit = sum(1 for pid in ranked[:k] if rels.get(str(pid), 0) > 0)
    total = sum(1 for v in rels.values() if v > 0)
    return hit / total if total else 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description="Evaluate search scenarios")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--ollama-url", default=os.environ.get("OLLAMA_URL", "http://localhost:11434"))
    ap.add_argument("--embedding-config", default="config/embedding.yml")
    ap.add_argument("--evaluation-config", default="config/evaluation.yml")
    ap.add_argument("--queries", default="datasets/queries/tokyo_wards.jsonl")
    ap.add_argument("--qrels", default="datasets/queries/qrels.tsv")
    ap.add_argument("--scenario", default="S3_geo_text_vector")
    args = ap.parse_args()

    if not args.dsn:
        raise SystemExit("DATABASE_URL is required")

    model, dims = load_embedding_config(args.embedding_config)
    scenario = load_scenario(args.evaluation_config, args.scenario)
    queries = load_queries(args.queries)
    qrels = load_qrels(args.qrels)

    results = []
    with psycopg.connect(args.dsn) as conn:
        for q in queries:
            qid = str(q["id"])
            qvec = ollama_embed_one(args.ollama_url, model, q["query"])
            ranked = search(
                conn,
                q["query"],
                q.get("region", ""),
                q.get("lat"),
                q.get("lon"),
                q.get("radius", 3000),
                model,
                dims,
                scenario,
                qvec,
            )
            rels = qrels.get(qid, {})
            results.append(
                {
                    "id": qid,
                    "ndcg@10": ndcg_at_k(ranked, rels, 10),
                    "mrr@10": mrr_at_k(ranked, rels, 10),
                    "recall@50": recall_at_k(ranked, rels, 50),
                }
            )

    avg = {
        "ndcg@10": sum(r["ndcg@10"] for r in results) / len(results) if results else 0.0,
        "mrr@10": sum(r["mrr@10"] for r in results) / len(results) if results else 0.0,
        "recall@50": sum(r["recall@50"] for r in results) / len(results) if results else 0.0,
    }

    os.makedirs("evaluations/results", exist_ok=True)
    out_path = os.path.join("evaluations/results", "latest.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"scenario": args.scenario, "avg": avg, "per_query": results}, f, ensure_ascii=False, indent=2)

    print(json.dumps(avg, ensure_ascii=False, indent=2))
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
