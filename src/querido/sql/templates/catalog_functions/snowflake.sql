select
    function_schema as schema,
    function_name as name,
    'function' as type,
    data_type as return_type,
    function_language as language
from {{ database }}.information_schema.functions
where function_schema = '{{ schema }}'
order by function_schema, function_name, data_type
