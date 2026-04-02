with stats as (
    select
        count(*) as total,
        count_if("{{ column }}" is null) as null_count,
        min("{{ column }}")::double as min_val,
        max("{{ column }}")::double as max_val
    from {{ source }}
),
binned as (
    select
        case
            when s.max_val = s.min_val then 0
            else least(
                floor(
                    ("{{ column }}"::double - s.min_val)
                    / ((s.max_val - s.min_val) / {{ buckets }}.0)
                )::integer,
                {{ buckets - 1 }}
            )
        end as bucket
    from {{ source }}
    cross join stats s
    where "{{ column }}" is not null
)
select
    bucket,
    round(s.min_val + bucket * ((s.max_val - s.min_val) / {{ buckets }}.0), 4) as bucket_min,
    round(s.min_val + (bucket + 1) * ((s.max_val - s.min_val) / {{ buckets }}.0), 4) as bucket_max,
    count(*) as count,
    s.total as total_rows,
    s.null_count as null_count
from binned
cross join stats s
group by bucket, s.min_val, s.max_val, s.total, s.null_count
order by bucket
