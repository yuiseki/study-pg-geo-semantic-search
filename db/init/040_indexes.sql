CREATE INDEX IF NOT EXISTS idx_places_point_gist ON search.places USING gist (point);
CREATE INDEX IF NOT EXISTS idx_places_geog_gist ON search.places USING gist (geog);

CREATE INDEX IF NOT EXISTS idx_places_text_pgroonga
  ON search.places
  USING pgroonga (text_for_search)
  WITH (tokenizer='TokenUnigram');

CREATE INDEX IF NOT EXISTS idx_place_embeddings_hnsw
  ON search.place_embeddings
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);
