-- psql variables: :qvec
SELECT place_id, 1 - (embedding <=> :qvec) AS cos_sim
FROM search.place_embeddings
ORDER BY embedding <=> :qvec
LIMIT 20;
