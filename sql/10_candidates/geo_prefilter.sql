-- psql variables: :lat :lon :radius_m
SELECT place_id
FROM search.places
WHERE ST_DWithin(geog, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, :radius_m)
LIMIT 500;
