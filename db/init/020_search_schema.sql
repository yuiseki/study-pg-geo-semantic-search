CREATE SCHEMA IF NOT EXISTS search;

CREATE TABLE IF NOT EXISTS search.places (
  place_id bigserial PRIMARY KEY,
  osm_type text NOT NULL,
  osm_id bigint NOT NULL,
  name text,
  category text,
  tags jsonb,
  geom geometry,
  point geometry(Point, 4326),
  geog geography(Point, 4326),
  region_id text,
  text_for_search text,
  UNIQUE (osm_type, osm_id)
);

CREATE TABLE IF NOT EXISTS search.place_embeddings (
  place_id bigint NOT NULL REFERENCES search.places(place_id) ON DELETE CASCADE,
  model text NOT NULL,
  embedding vector(1024) NOT NULL,
  created_at timestamptz DEFAULT now(),
  PRIMARY KEY (place_id, model)
);

CREATE TABLE IF NOT EXISTS search.admin_areas (
  region_id text PRIMARY KEY,
  name text NOT NULL,
  geom geometry(MultiPolygon, 4326)
);
