#!/usr/bin/env python3
import argparse
import os
from typing import Dict, List

import psycopg
import yaml

RAW_TABLES = {
    "osm_points": "geom",
    "osm_lines": "ST_LineInterpolatePoint(geom, 0.5)",
    "osm_polygons": "ST_PointOnSurface(geom)",
}


def load_rules(path: str, mode: str) -> List[Dict[str, object]]:
    with open(path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    if mode not in config:
        raise SystemExit(f"mode '{mode}' not found in {path}")
    return config[mode]


def build_match_sql(table_alias: str, match: Dict[str, object]) -> str:
    key = match["key"]
    values = match.get("values", [])
    if not values:
        return f"({table_alias}.tags ? '{key}')"
    values_sql = ",".join([f"'{v}'" for v in values])
    return f"({table_alias}.tags ? '{key}' AND {table_alias}.tags->>'{key}' IN ({values_sql}))"


def main() -> None:
    ap = argparse.ArgumentParser(description="Transform raw OSM tables into search.places")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"))
    ap.add_argument("--config", default="config/place_extract.yml")
    ap.add_argument("--mode", default="focused")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()

    if not args.dsn:
        raise SystemExit("DATABASE_URL is required")

    rules = load_rules(args.config, args.mode)

    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            if args.reset:
                cur.execute("TRUNCATE search.place_embeddings, search.places RESTART IDENTITY;")

            for rule in rules:
                category = rule["category"]
                matches = rule.get("match", [])
                if not matches:
                    continue

                match_sql = " OR ".join([build_match_sql("r", m) for m in matches])

                for table, point_expr in RAW_TABLES.items():
                    sql = f"""
                    INSERT INTO search.places (osm_type, osm_id, name, category, tags, geom, point, geog, text_for_search)
                    SELECT
                      r.osm_type,
                      r.osm_id,
                      COALESCE(r.tags->>'name', r.tags->>'name:ja') AS name,
                      %s AS category,
                      r.tags,
                      ST_Transform(r.geom, 4326) AS geom,
                      ST_Transform({point_expr}, 4326) AS point,
                      ST_Transform({point_expr}, 4326)::geography AS geog,
                      search.build_text_for_search(COALESCE(r.tags->>'name', r.tags->>'name:ja'), r.tags) AS text_for_search
                    FROM raw.{table} r
                    WHERE {match_sql}
                    ON CONFLICT (osm_type, osm_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        category = EXCLUDED.category,
                        tags = EXCLUDED.tags,
                        geom = EXCLUDED.geom,
                        point = EXCLUDED.point,
                        geog = EXCLUDED.geog,
                        text_for_search = EXCLUDED.text_for_search;
                    """
                    cur.execute(sql, (category,))

        conn.commit()


if __name__ == "__main__":
    main()
