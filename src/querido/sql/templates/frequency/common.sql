with grouped as (
    select "{{ column }}" as value, count(*) as count
    from {{ source }}
    group by "{{ column }}"
)
select
    cast(value as text) as value,
    count,
    sum(count) over() as total_rows,
    coalesce((select count from grouped where value is null), 0) as null_count
from grouped
where value is not null
order by count desc
limit {{ top }}
