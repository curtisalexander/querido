# Agent Workflow Example: Writing a Sales Report Query

This document shows a concrete example of how a coding agent uses `qdo` to
explore a database, understand its schema, enrich it with business context,
and write correct SQL -- step by step. Each step shows the command, a trimmed
sample of the JSON output, and the agent's reasoning.

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

**Agent reasoning:** `context` gave me schema, stats, and sample values in one
call per table. I now know the join path, column types, and exact enum strings.
But I don't yet have business context -- what does `status = 'pending'` really
mean? Are there values I should treat specially? Let me check for metadata.

---

## Step 3: Check for enriched metadata

If a human analyst has already run `qdo metadata init` and filled in business
descriptions, the agent gets dramatically better context for free.

```bash
qdo metadata show -c ./ecommerce.duckdb -t orders
```

```json
{
  "table": "orders",
  "connection": "./ecommerce.duckdb",
  "table_description": "Customer orders placed through the website and mobile app.",
  "data_owner": "order-processing-team",
  "update_frequency": "hourly",
  "notes": "Backdated corrections appear as status='completed' with order_date in the past. Exclude status='test' rows in production reports.",
  "row_count": 125000,
  "columns": [
    {
      "name": "order_id", "type": "INTEGER",
      "description": "Primary key, auto-incrementing."
    },
    {
      "name": "customer_id", "type": "INTEGER",
      "description": "FK to customers.customer_id. Nullable for guest checkouts."
    },
    {
      "name": "order_date", "type": "DATE",
      "description": "Date the order was placed (UTC)."
    },
    {
      "name": "status", "type": "VARCHAR",
      "description": "Fulfillment lifecycle status.",
      "valid_values": ["pending", "shipped", "completed", "cancelled", "test"]
    }
  ]
}
```

```bash
qdo metadata show -c ./ecommerce.duckdb -t order_items
```

```json
{
  "table": "order_items",
  "table_description": "Line items for each order. One row per product per order.",
  "columns": [
    {
      "name": "unit_price", "type": "DOUBLE",
      "description": "Price at time of purchase (not current catalog price). Use this for revenue calculations."
    },
    {
      "name": "quantity", "type": "INTEGER",
      "description": "Units ordered. Always >= 1."
    }
  ]
}
```

**Agent reasoning:** The metadata revealed critical information that schema
alone could not:

- There's a `status = 'test'` value that `sample_values` missed (only 5 shown).
  The `valid_values` list is authoritative -- I need to exclude `'test'` rows too.
- `unit_price` is the price *at time of purchase*, confirming it's correct for
  revenue (not a current catalog price that would overcount).
- The `notes` field warns about backdated corrections -- good to know, though
  not relevant for this query.
- `customer_id` is nullable for guest checkouts -- I'm not joining on it, but
  if I were, I'd need a LEFT JOIN.

**If metadata doesn't exist yet,** the agent can bootstrap it:

```bash
qdo metadata init -c ./ecommerce.duckdb -t orders
qdo metadata init -c ./ecommerce.duckdb -t order_items
qdo metadata init -c ./ecommerce.duckdb -t products
```

This creates YAML files at `.qdo/metadata/` with machine-populated stats. The
human analyst fills in descriptions, valid values, and PII flags over time.
Every subsequent agent session benefits from that accumulated context.

---

## Step 4: Write the query

Armed with schema stats *and* business context, the agent writes correct SQL:

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
    and o.status not in ('cancelled', 'test')
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

Note: without metadata, the agent would have written `status != 'cancelled'`
and silently included test orders in the revenue figures.

---

## Step 5: Validate assumptions with assertions

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

```bash
qdo assert -c ./ecommerce.duckdb \
  --sql "select count(*) from orders where status = 'test' and extract(year from order_date) = 2024" \
  --expect-gt 0 \
  --name "test orders exist in 2024"
```

```json
{
  "passed": true,
  "actual": 47,
  "expected": 0,
  "operator": "gt",
  "name": "test orders exist in 2024"
}
```

**Agent reasoning:** Both cancelled and test orders exist in 2024. The
metadata's `valid_values` list caught the test rows that `sample_values`
missed -- without it, 47 test orders would have inflated the revenue report.

---

## The Metadata Payoff

The workflow above shows metadata at its most valuable: a one-time human
investment (filling in descriptions, valid values, PII flags) that pays off
across every future agent session.

| Without metadata | With metadata |
|-----------------|---------------|
| Agent sees 4 sample values for `status` | Agent sees all 5 valid values including `test` |
| Agent guesses `unit_price` is current price | Agent knows it's price at time of purchase |
| Agent doesn't know about guest checkout nulls | Agent sees `customer_id` is nullable and why |
| Agent has no warning about backdated rows | Agent reads `notes` and can flag edge cases |

### Building metadata incrementally

Metadata doesn't have to be complete to be useful. Even partial metadata helps:

```bash
# Start: auto-populate machine fields (stats, types, sample values)
qdo metadata init -c ./ecommerce.duckdb -t orders

# Human fills in what they know (descriptions, valid_values, pii flags)
qdo metadata edit -c ./ecommerce.duckdb -t orders

# Check progress across all tables
qdo metadata list -c ./ecommerce.duckdb

# After data changes: refresh stats without losing human descriptions
qdo metadata refresh -c ./ecommerce.duckdb -t orders
```

`context` automatically merges stored metadata when it exists. The agent
doesn't need to call `metadata show` separately -- descriptions, valid values,
and PII flags appear directly in `context` output. The separate
`metadata show` call is useful when the agent needs the full metadata
(including notes, data owner, update frequency) that `context` doesn't include.

---

## Key Patterns

1. **Start with `catalog`** to see all tables and their sizes.
2. **Use `context`** to get schema, stats, and sample values in one call.
   If metadata exists, it's merged in automatically.
3. **Check `metadata show`** for business context that goes beyond schema:
   table-level notes, data owner, update frequency, and the full
   `valid_values` list (which may include values too rare for `sample_values`).
4. **Read `sample_values`** to get exact enum strings for WHERE clauses --
   don't guess. But prefer `valid_values` from metadata when available.
5. **Read `null_pct`** to decide if you need NULL handling (LEFT JOIN guards,
   COALESCE, IS NOT NULL filters).
6. **Read `min`/`max`** on date columns to confirm the data range covers
   your filter.
7. **Use `assert`** to validate assumptions about the data before delivering
   the final query.
8. **Bootstrap metadata with `metadata init`** if none exists yet -- even
   without human descriptions, the machine-populated fields help future
   sessions.

---

## Quick Reference

| Goal | Command |
|------|---------|
| See all tables | `qdo catalog -c <conn>` |
| Understand one table | `qdo context -c <conn> -t <table>` |
| Business context for a table | `qdo metadata show -c <conn> -t <table>` |
| Bootstrap metadata | `qdo metadata init -c <conn> -t <table>` |
| See sample rows | `qdo preview -c <conn> -t <table> -r 10` |
| Check a column's values | `qdo values -c <conn> -t <table> -C <col>` |
| Run a query | `qdo query -c <conn> --sql "..."` |
| Validate a result | `qdo assert -c <conn> --sql "..." --expect N` |
| Check data quality | `qdo quality -c <conn> -t <table>` |
| Aggregate without SQL | `qdo pivot -c <conn> -t <table> -g <col> -a "sum(<col>)"` |
| Metadata completeness | `qdo metadata list -c <conn>` |
