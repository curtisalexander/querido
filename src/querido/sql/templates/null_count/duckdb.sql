select
    count(*) as total,
    count_if("{{ column }}" is null) as null_count
from {{ table }}
