-- psql variables: :lat :lon :radius_m :q :qvec :limit
WITH geo AS (
  SELECT place_id
  FROM search.places
  WHERE ST_DWithin(geog, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius_m)
),
text AS (
  SELECT place_id,
         row_number() OVER (ORDER BY pgroonga_score(tableoid, ctid) DESC) AS r_text
  FROM search.places
  WHERE place_id IN (SELECT place_id FROM geo)
    AND text_for_search &@~ :q
),
vec AS (
  SELECT place_id,
         row_number() OVER (ORDER BY embedding <=> :qvec) AS r_vec
  FROM search.place_embeddings
  WHERE place_id IN (SELECT place_id FROM geo)
),
rrf AS (
  SELECT COALESCE(text.place_id, vec.place_id) AS place_id,
         COALESCE(1.0 / (60 + text.r_text), 0.0) + COALESCE(1.0 / (60 + vec.r_vec), 0.0) AS rrf
  FROM text FULL OUTER JOIN vec USING (place_id)
)
SELECT p.place_id, p.name, p.category, rrf.rrf
FROM rrf
JOIN search.places p USING (place_id)
ORDER BY rrf.rrf DESC
LIMIT :limit;
