# Agent Workflow Example: Writing a Sales Report Query

This document shows a concrete example of how a coding agent uses `qdo` to
explore a database, understand its schema, and write correct SQL -- step by
step. Each step shows the command, a trimmed sample of the JSON output, and
the agent's reasoning.

The example uses a DuckDB database with e-commerce data. The user has asked:

> "Write a query that shows monthly revenue by product category for 2024,
> excluding cancelled orders."

---

## Setup

The agent sets JSON output mode once:

```bash
export QDO_FORMAT=json
```

---

## Step 1: Discover tables

```bash
qdo catalog -c ./ecommerce.duckdb
```

```json
{
  "table_count": 4,
  "tables": [
    {"name": "orders", "type": "table", "row_count": 125000, "columns": [...]},
    {"name": "order_items", "type": "table", "row_count": 340000, "columns": [...]},
    {"name": "products", "type": "table", "row_count": 500, "columns": [...]},
    {"name": "customers", "type": "table", "row_count": 20000, "columns": [...]}
  ]
}
```

**Agent reasoning:** The query needs `orders` (for dates and status),
`order_items` (for revenue), and `products` (for category). I'll get context
for each.

---

## Step 2: Get full context for relevant tables

```bash
qdo context -c ./ecommerce.duckdb -t orders
```

```json
{
  "table": "orders",
  "row_count": 125000,
  "columns": [
    {"name": "order_id", "type": "INTEGER", "null_pct": 0, "distinct_count": 125000},
    {"name": "customer_id", "type": "INTEGER", "null_pct": 0, "distinct_count": 19800},
    {"name": "order_date", "type": "DATE", "null_pct": 0, "min": "2022-01-01", "max": "2024-12-31"},
    {"name": "status", "type": "VARCHAR", "null_pct": 0, "distinct_count": 4,
     "sample_values": ["completed", "pending", "shipped", "cancelled"]}
  ]
}
```

```bash
qdo context -c ./ecommerce.duckdb -t order_items
```

```json
{
  "table": "order_items",
  "row_count": 340000,
  "columns": [
    {"name": "order_id", "type": "INTEGER", "null_pct": 0, "distinct_count": 125000},
    {"name": "product_id", "type": "INTEGER", "null_pct": 0, "distinct_count": 500},
    {"name": "quantity", "type": "INTEGER", "null_pct": 0, "min": 1, "max": 20},
    {"name": "unit_price", "type": "DOUBLE", "null_pct": 0, "min": 4.99, "max": 999.99}
  ]
}
```

```bash
qdo context -c ./ecommerce.duckdb -t products
```

```json
{
  "table": "products",
  "row_count": 500,
  "columns": [
    {"name": "product_id", "type": "INTEGER", "null_pct": 0, "distinct_count": 500},
    {"name": "name", "type": "VARCHAR", "null_pct": 0, "distinct_count": 500},
    {"name": "category", "type": "VARCHAR", "null_pct": 0, "distinct_count": 12,
     "sample_values": ["Electronics", "Clothing", "Home & Garden", "Books", "Sports"]}
  ]
}
```

**Agent reasoning:**
- Join path: `orders.order_id` = `order_items.order_id`, `order_items.product_id` = `products.product_id`
- Revenue = `quantity * unit_price` (no dedicated revenue column)
- Filter: `orders.status != 'cancelled'` (the `status` sample_values confirm the exact string)
- Date filter: `order_date` has data through 2024, use `extract(year from order_date) = 2024`
- Group by: `extract(month from order_date)` and `products.category`

---

## Step 3: Write and validate the query

```bash
qdo query -c ./ecommerce.duckdb --sql "
  select
    extract(month from o.order_date) as month,
    p.category,
    sum(oi.quantity * oi.unit_price) as revenue
  from orders o
  join order_items oi on oi.order_id = o.order_id
  join products p on p.product_id = oi.product_id
  where extract(year from o.order_date) = 2024
    and o.status != 'cancelled'
  group by 1, 2
  order by 1, 2
"
```

```json
{
  "columns": ["month", "category", "revenue"],
  "row_count": 132,
  "rows": [
    {"month": 1, "category": "Books", "revenue": 15234.50},
    {"month": 1, "category": "Clothing", "revenue": 42891.00},
    "..."
  ]
}
```

---

## Step 4: Validate assumptions with assertions

```bash
qdo assert -c ./ecommerce.duckdb \
  --sql "select count(*) from orders where status = 'cancelled' and extract(year from order_date) = 2024" \
  --expect-gt 0 \
  --name "cancelled orders exist in 2024"
```

```json
{
  "passed": true,
  "actual": 3420,
  "expected": 0,
  "operator": "gt",
  "name": "cancelled orders exist in 2024"
}
```

**Agent reasoning:** Good -- there are cancelled orders in 2024, so the filter
is meaningful and we're correctly excluding them.

---

## Key Patterns

1. **Start with `catalog`** to see all tables and their sizes.
2. **Use `context` (not `inspect` + `profile` separately)** to get schema, stats,
   and sample values in one call. This is the most efficient path.
3. **Read `sample_values`** to get exact enum strings for WHERE clauses --
   don't guess.
4. **Read `null_pct`** to decide if you need NULL handling (LEFT JOIN guards,
   COALESCE, IS NOT NULL filters).
5. **Read `min`/`max`** on date columns to confirm the data range covers
   your filter.
6. **Use `assert`** to validate assumptions about the data before delivering
   the final query.
7. **Use `quality`** if you suspect data issues (high null rates, low
   uniqueness on expected-unique columns).

---

## Quick Reference

| Goal | Command |
|------|---------|
| See all tables | `qdo catalog -c <conn>` |
| Understand one table | `qdo context -c <conn> -t <table>` |
| See sample rows | `qdo preview -c <conn> -t <table> -r 10` |
| Check a column's values | `qdo values -c <conn> -t <table> -C <col>` |
| Run a query | `qdo query -c <conn> --sql "..."` |
| Validate a result | `qdo assert -c <conn> --sql "..." --expect N` |
| Check data quality | `qdo quality -c <conn> -t <table>` |
| Aggregate without SQL | `qdo pivot -c <conn> -t <table> -g <col> -a "sum(<col>)"` |
