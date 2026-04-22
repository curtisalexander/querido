select
    schema_name as schema,
    function_name as name,
    function_type as type,
    return_type,
    description,
    internal,
    has_side_effects,
    stability,
    categories
from duckdb_functions()
where schema_name not in ('pg_catalog', 'information_schema')
order by schema_name, function_name, function_type, return_type
