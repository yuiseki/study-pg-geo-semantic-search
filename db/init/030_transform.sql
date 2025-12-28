CREATE OR REPLACE FUNCTION search.build_text_for_search(name text, tags jsonb)
RETURNS text LANGUAGE sql IMMUTABLE AS $$
  SELECT trim(
    concat_ws(' ',
      name,
      tags->>'name',
      tags->>'name:ja',
      tags->>'alt_name',
      tags->>'amenity',
      tags->>'shop',
      tags->>'tourism',
      tags->>'leisure',
      tags->>'cuisine',
      tags->>'brand'
    )
  )
$$;
