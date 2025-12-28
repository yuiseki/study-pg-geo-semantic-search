local raw_points = osm2pgsql.define_table({
  name = 'osm_points',
  schema = 'raw',
  ids = { type = 'any', id_column = 'osm_id' },
  columns = {
    { column = 'osm_type', type = 'text' },
    { column = 'tags', type = 'jsonb' },
    { column = 'geom', type = 'point', not_null = true },
  },
})

local raw_lines = osm2pgsql.define_table({
  name = 'osm_lines',
  schema = 'raw',
  ids = { type = 'any', id_column = 'osm_id' },
  columns = {
    { column = 'osm_type', type = 'text' },
    { column = 'tags', type = 'jsonb' },
    { column = 'geom', type = 'linestring', not_null = true },
  },
})

local raw_polygons = osm2pgsql.define_table({
  name = 'osm_polygons',
  schema = 'raw',
  ids = { type = 'any', id_column = 'osm_id' },
  columns = {
    { column = 'osm_type', type = 'text' },
    { column = 'tags', type = 'jsonb' },
    { column = 'geom', type = 'multipolygon', not_null = true },
  },
})

function osm2pgsql.process_node(object)
  if not object.tags or next(object.tags) == nil then
    return
  end
  raw_points:insert({
    osm_id = object.id,
    osm_type = 'node',
    tags = object.tags,
    geom = object:as_point(),
  })
end

function osm2pgsql.process_way(object)
  if not object.tags or next(object.tags) == nil then
    return
  end

  if object.is_closed then
    raw_polygons:insert({
      osm_id = object.id,
      osm_type = 'way',
      tags = object.tags,
      geom = object:as_polygon(),
    })
  else
    raw_lines:insert({
      osm_id = object.id,
      osm_type = 'way',
      tags = object.tags,
      geom = object:as_linestring(),
    })
  end
end

function osm2pgsql.process_relation(object)
  if not object.tags or next(object.tags) == nil then
    return
  end

  if object.tags.type == 'multipolygon' then
    local geom = object:as_multipolygon()
    if geom then
      raw_polygons:insert({
        osm_id = object.id,
        osm_type = 'relation',
        tags = object.tags,
        geom = geom,
      })
    end
  end
end
