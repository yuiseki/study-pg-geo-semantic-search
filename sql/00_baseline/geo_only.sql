-- psql variables: :lat :lon :radius_m
SELECT place_id, name, category, ST_Distance(geog, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) AS distance_m
FROM search.places
WHERE ST_DWithin(geog, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius_m)
ORDER BY geog <-> ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
LIMIT 20;
