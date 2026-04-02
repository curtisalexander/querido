with stats as (
    select
        count(*) as total_rows,
        count_if("{{ column }}" is null) as null_count
    from {{ source }}
),
top_k as (
    select approx_top_k("{{ column }}", {{ top }}) as arr
    from {{ source }}
)
select f.value:"value"::varchar as value,
       f.value:"count"::integer as count,
       stats.total_rows,
       stats.null_count
from top_k, table(flatten(input => top_k.arr)) f
cross join stats
order by count desc
