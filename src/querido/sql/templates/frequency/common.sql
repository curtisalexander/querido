with stats as (
    select
        count(*) as total_rows,
        sum(case when "{{ column }}" is null then 1 else 0 end) as null_count
    from {{ source }}
)
select
    cast("{{ column }}" as text) as value,
    count(*) as count,
    stats.total_rows,
    stats.null_count
from {{ source }}
cross join stats
group by "{{ column }}", stats.total_rows, stats.null_count
order by count desc
limit {{ top }}
