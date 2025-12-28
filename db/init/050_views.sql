CREATE OR REPLACE VIEW search.place_overview AS
SELECT
  p.place_id,
  p.osm_type,
  p.osm_id,
  p.name,
  p.category,
  p.region_id,
  p.point,
  p.geog,
  p.text_for_search,
  EXISTS (
    SELECT 1 FROM search.place_embeddings e
    WHERE e.place_id = p.place_id
  ) AS has_embedding
FROM search.places p;
