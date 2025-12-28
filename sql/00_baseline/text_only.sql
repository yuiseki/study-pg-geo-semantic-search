-- psql variables: :q
SELECT place_id, name, category, pgroonga_score(tableoid, ctid) AS score
FROM search.places
WHERE text_for_search &@~ :q
ORDER BY score DESC
LIMIT 20;
