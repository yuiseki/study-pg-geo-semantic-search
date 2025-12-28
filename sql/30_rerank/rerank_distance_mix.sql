-- psql variables: :lat :lon :radius_m :q :qvec :limit
WITH geo AS (
  SELECT place_id,
         ST_Distance(geog, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS dist_m
  FROM search.places
  WHERE ST_DWithin(geog, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius_m)
),
text AS (
  SELECT place_id,
         pgroonga_score(tableoid, ctid) AS s_text
  FROM search.places
  WHERE place_id IN (SELECT place_id FROM geo)
    AND text_for_search &@~ :q
),
vec AS (
  SELECT place_id,
         1 - (embedding <=> :qvec) AS s_vec
  FROM search.place_embeddings
  WHERE place_id IN (SELECT place_id FROM geo)
),
joined AS (
  SELECT g.place_id, g.dist_m,
         COALESCE(t.s_text, 0) AS s_text,
         COALESCE(v.s_vec, 0) AS s_vec
  FROM geo g
  LEFT JOIN text t USING (place_id)
  LEFT JOIN vec v USING (place_id)
)
SELECT p.place_id, p.name, p.category,
       (0.6 * s_text) + (1.0 * s_vec) + (0.2 * (1 / (1 + dist_m))) AS final_score,
       s_text, s_vec, dist_m
FROM joined j
JOIN search.places p USING (place_id)
ORDER BY final_score DESC
LIMIT :limit;
