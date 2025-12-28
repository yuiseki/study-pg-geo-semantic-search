-- psql variables: :lat :lon :k
SELECT place_id
FROM search.places
ORDER BY point <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
LIMIT :k;
