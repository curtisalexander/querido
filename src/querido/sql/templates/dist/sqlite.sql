with stats as (
    select
        count(*) as total,
        sum(case when "{{ column }}" is null then 1 else 0 end) as null_count,
        min("{{ column }}") as min_val,
        max("{{ column }}") as max_val
    from {{ source }}
),
bins as (
    select
        case
        {% for i in range(buckets) %}
            when "{{ column }}" >= s.min_val + {{ i }} * (s.max_val - s.min_val) / {{ buckets }}.0
                 and "{{ column }}" {{ '<' if not loop.last else '<=' }} s.min_val + {{ i + 1 }} * (s.max_val - s.min_val) / {{ buckets }}.0
            then {{ i }}
        {% endfor %}
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
from bins
cross join stats s
where bucket is not null
group by bucket, s.min_val, s.max_val, s.total, s.null_count
order by bucket
