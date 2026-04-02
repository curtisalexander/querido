select
    count(*) as total,
    sum(case when "{{ column }}" is null then 1 else 0 end) as null_count
from {{ table }}
