"""Generate synthetic test data and import into SQLite and DuckDB.

Creates three tables per database:
- customers (1000 rows): strings, dates, emails, phones, nulls
- products (1000 rows): numeric, categorical, varying nulls
- datatypes (100 rows): exotic/complex types per database engine

All data is deterministic (seeded RNG) for reproducible test runs.

Usage:
    uv run python scripts/init_test_data.py
"""

import csv
import json
import random
import sqlite3
import struct
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

DATA_DIR = Path(__file__).parent.parent / "data"

# Seed for reproducibility
RNG = random.Random(42)

# ---------------------------------------------------------------------------
# Word lists for synthetic data
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Alice",
    "Bob",
    "Carol",
    "David",
    "Emma",
    "Frank",
    "Grace",
    "Henry",
    "Iris",
    "Jack",
    "Karen",
    "Leo",
    "Mia",
    "Noah",
    "Olivia",
    "Paul",
    "Quinn",
    "Rosa",
    "Sam",
    "Tina",
    "Uma",
    "Victor",
    "Wendy",
    "Xander",
    "Yara",
    "Zane",
    "Aisha",
    "Boris",
    "Clara",
    "Diego",
    "Elena",
    "Felix",
    "Greta",
    "Hugo",
    "Ines",
    "Jorge",
    "Kira",
    "Lars",
    "Maya",
    "Niko",
    "Olga",
    "Pedro",
    "Rina",
    "Sven",
    "Thea",
    "Uri",
    "Vera",
    "Wolf",
]

LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Martinez",
    "Anderson",
    "Taylor",
    "Thomas",
    "Moore",
    "Jackson",
    "Lee",
    "Harris",
    "Clark",
    "Lewis",
    "Walker",
    "Hall",
    "Allen",
    "Young",
    "King",
    "Wright",
    "Hill",
    "Scott",
    "Green",
    "Adams",
    "Baker",
    "Rivera",
    "Campbell",
    "Mitchell",
    "Roberts",
    "Carter",
    "Phillips",
    "Evans",
    "Turner",
    "Torres",
    "Parker",
    "Collins",
    "Edwards",
    "Stewart",
    "Morris",
    "Murphy",
    "Cook",
    "Rogers",
    "Morgan",
    "Peterson",
    "Cooper",
    "Reed",
]

COMPANIES = [
    "Acme Corp",
    "Globex Inc",
    "Initech",
    "Umbrella Co",
    "Cyberdyne Systems",
    "Stark Industries",
    "Wayne Enterprises",
    "Oscorp",
    "Soylent Corp",
    "Tyrell Corp",
    "Weyland-Yutani",
    "Aperture Science",
    "Massive Dynamic",
    "Hooli",
    "Pied Piper",
    "Dunder Mifflin",
    "Sterling Cooper",
    "Prestige",
    "InGen",
    "Wonka Industries",
]

CITIES = [
    "New York",
    "London",
    "Tokyo",
    "Paris",
    "Berlin",
    "Sydney",
    "Toronto",
    "Mumbai",
    "São Paulo",
    "Mexico City",
    "Seoul",
    "Amsterdam",
    "Dubai",
    "Singapore",
    "Stockholm",
    "Barcelona",
    "Zurich",
    "Cape Town",
    "Dublin",
    "Vienna",
    "Prague",
    "Warsaw",
    "Istanbul",
    "Bangkok",
    "Lima",
    "Buenos Aires",
    "Nairobi",
    "Helsinki",
    "Oslo",
    "Lisbon",
]

COUNTRIES = [
    "United States",
    "United Kingdom",
    "Japan",
    "France",
    "Germany",
    "Australia",
    "Canada",
    "India",
    "Brazil",
    "Mexico",
    "South Korea",
    "Netherlands",
    "UAE",
    "Singapore",
    "Sweden",
]

DOMAINS = [
    "example.com",
    "testmail.org",
    "fakecorp.net",
    "demo.io",
    "sample.dev",
    "acme.co",
    "widgets.biz",
    "datatest.com",
    "mockmail.org",
    "synth.dev",
]

PRODUCT_ADJ = [
    "Premium",
    "Classic",
    "Ultra",
    "Pro",
    "Essential",
    "Deluxe",
    "Basic",
    "Advanced",
    "Elite",
    "Standard",
    "Compact",
    "Heavy-Duty",
    "Portable",
    "Industrial",
    "Mini",
    "Mega",
    "Smart",
    "Eco",
    "Turbo",
    "Quantum",
]

PRODUCT_NOUNS = [
    "Widget",
    "Gadget",
    "Sensor",
    "Module",
    "Controller",
    "Adapter",
    "Connector",
    "Processor",
    "Filter",
    "Valve",
    "Panel",
    "Switch",
    "Monitor",
    "Bracket",
    "Cable",
    "Converter",
    "Regulator",
    "Amplifier",
    "Transmitter",
    "Detector",
    "Relay",
    "Capacitor",
    "Transformer",
    "Pump",
]

BRANDS = [
    "TechNova",
    "AlphaGear",
    "NexGen",
    "CoreTech",
    "VoltEdge",
    "PrimeLine",
    "SkyForge",
    "IronPeak",
    "BlueShift",
    "OmniWare",
    "ZenithPro",
    "PulseCore",
    "ArcLight",
    "SteelVine",
    "ClearPath",
    "DataForge",
    "NovaSync",
    "QuantumLeap",
    "SolidState",
    "DeepRoot",
]

CATEGORIES = [
    "Electronics",
    "Hardware",
    "Sensors",
    "Networking",
    "Power",
    "Automation",
    "Safety",
    "Optics",
    "Audio",
    "Industrial",
]

COLORS = [
    "Red",
    "Blue",
    "Green",
    "Black",
    "White",
    "Silver",
    "Gold",
    "Navy",
    "Orange",
    "Purple",
    "Teal",
    "Charcoal",
]

SIZES = ["XS", "S", "M", "L", "XL", "XXL", "10mm", "25mm", "50mm", "100mm"]

AVAILABILITY = ["In Stock", "Out of Stock", "Preorder", "Discontinued"]

CURRENCIES = ["USD", "EUR", "GBP", "JPY", "CAD"]

DESCRIPTIONS = [
    "High-performance component for demanding applications.",
    "Reliable and cost-effective solution for everyday use.",
    "Next-generation design with improved efficiency.",
    "Compact form factor with enterprise-grade durability.",
    "Industry-standard interface with backward compatibility.",
    "Low-power consumption with high throughput.",
    "Precision-engineered for critical systems.",
    "Versatile module supporting multiple protocols.",
    "Weather-resistant housing for outdoor deployment.",
    "Certified for use in hazardous environments.",
]


# ---------------------------------------------------------------------------
# Data generators
# ---------------------------------------------------------------------------


def gen_phone() -> str:
    return f"+1-{RNG.randint(200, 999)}-{RNG.randint(100, 999)}-{RNG.randint(1000, 9999)}"


def gen_date(start_year: int = 2018, end_year: int = 2025) -> str:
    start = date(start_year, 1, 1)
    end = date(end_year, 12, 31)
    delta = (end - start).days
    d = start + timedelta(days=RNG.randint(0, delta))
    return d.isoformat()


def gen_datetime(start_year: int = 2018, end_year: int = 2025) -> str:
    start = datetime(start_year, 1, 1)
    end = datetime(end_year, 12, 31, 23, 59, 59)
    delta = int((end - start).total_seconds())
    dt = start + timedelta(seconds=RNG.randint(0, delta))
    return dt.isoformat()


def gen_ean() -> str:
    return "".join(str(RNG.randint(0, 9)) for _ in range(13))


def gen_uuid() -> str:
    hex_chars = "0123456789abcdef"
    h = "".join(RNG.choice(hex_chars) for _ in range(32))
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def gen_customers(n: int = 1000) -> tuple[list[str], list[list[object]]]:
    headers = [
        "customer_id",
        "first_name",
        "last_name",
        "company",
        "city",
        "country",
        "phone1",
        "phone2",
        "email",
        "subscription_date",
        "website",
    ]
    rows: list[list[object]] = []
    for i in range(1, n + 1):
        first = RNG.choice(FIRST_NAMES)
        last = RNG.choice(LAST_NAMES)
        domain = RNG.choice(DOMAINS)
        email = f"{first.lower()}.{last.lower()}@{domain}"
        company = RNG.choice(COMPANIES) if RNG.random() > 0.15 else None
        phone2 = gen_phone() if RNG.random() > 0.30 else None
        website = f"https://www.{domain}/{last.lower()}" if RNG.random() > 0.20 else None

        rows.append(
            [
                f"CUST-{i:04d}",
                first,
                last,
                company,
                RNG.choice(CITIES),
                RNG.choice(COUNTRIES),
                gen_phone(),
                phone2,
                email,
                gen_date(2019, 2025),
                website,
            ]
        )
    return headers, rows


def gen_products(n: int = 1000) -> tuple[list[str], list[list[object]]]:
    headers = [
        "name",
        "description",
        "brand",
        "category",
        "price",
        "currency",
        "stock",
        "ean",
        "color",
        "size",
        "availability",
        "internal_id",
    ]
    rows: list[list[object]] = []
    for _ in range(n):
        adj = RNG.choice(PRODUCT_ADJ)
        noun = RNG.choice(PRODUCT_NOUNS)
        desc = RNG.choice(DESCRIPTIONS) if RNG.random() > 0.10 else None
        price: object = round(RNG.uniform(0.99, 9999.99), 2) if RNG.random() > 0.05 else None
        stock: object = RNG.randint(0, 10000) if RNG.random() > 0.05 else None
        color = RNG.choice(COLORS) if RNG.random() > 0.10 else None
        size = RNG.choice(SIZES) if RNG.random() > 0.15 else None

        rows.append(
            [
                f"{adj} {noun}",
                desc,
                RNG.choice(BRANDS),
                RNG.choice(CATEGORIES),
                price,
                RNG.choice(CURRENCIES),
                stock,
                gen_ean(),
                color,
                size,
                RNG.choice(AVAILABILITY),
                gen_uuid(),
            ]
        )
    return headers, rows


# ---------------------------------------------------------------------------
# CSV writing
# ---------------------------------------------------------------------------


def write_csv(path: Path, headers: list[str], rows: list[list[object]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for row in rows:
            writer.writerow(["" if v is None else v for v in row])
    print(f"  [csv] {path.name} ({len(rows)} rows, {path.stat().st_size:,} bytes)")


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


def init_sqlite(
    db_path: Path, customers: list[list[object]], products: list[list[object]]
) -> None:
    print(f"\n  Creating SQLite database: {db_path}")
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(str(db_path))

    # Customers table
    conn.execute("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id TEXT,
            first_name TEXT,
            last_name TEXT,
            company TEXT,
            city TEXT,
            country TEXT,
            phone1 TEXT,
            phone2 TEXT,
            email TEXT,
            subscription_date TEXT,
            website TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO customers (customer_id, first_name, last_name, company,"
        " city, country, phone1, phone2, email, subscription_date, website)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        customers,
    )

    # Products table
    conn.execute("""
        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            description TEXT,
            brand TEXT,
            category TEXT,
            price REAL,
            currency TEXT,
            stock INTEGER,
            ean TEXT,
            color TEXT,
            size TEXT,
            availability TEXT,
            internal_id TEXT
        )
    """)
    conn.executemany(
        "INSERT INTO products (name, description, brand, category, price,"
        " currency, stock, ean, color, size, availability, internal_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        products,
    )

    # Datatypes table — exercises SQLite's type flexibility
    conn.execute("""
        CREATE TABLE datatypes (
            id INTEGER PRIMARY KEY,
            bool_val INTEGER,
            date_val TEXT,
            datetime_val TEXT,
            int_val INTEGER,
            big_int_val INTEGER,
            float_val REAL,
            negative_val REAL,
            text_val TEXT,
            long_text_val TEXT,
            empty_str_val TEXT,
            blob_val BLOB,
            json_val TEXT,
            nullable_int INTEGER,
            nullable_text TEXT,
            zero_val REAL
        )
    """)
    for i in range(100):
        blob_data = struct.pack("!If", i, float(i) * 1.5) + bytes(
            range(i % 256, min(i % 256 + 8, 256))
        )
        json_data = json.dumps(
            {
                "id": i,
                "tags": [f"tag{j}" for j in range(i % 5)],
                "nested": {"key": f"val_{i}", "flag": i % 2 == 0},
            }
        )
        long_text = f"Row {i}: " + "abcdefghij " * (i % 50 + 1)

        conn.execute(
            "INSERT INTO datatypes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                i,
                i % 2,  # bool_val: 0 or 1
                gen_date(),  # date_val
                gen_datetime(),  # datetime_val
                RNG.randint(-1_000_000, 1_000_000),  # int_val
                RNG.randint(2**31, 2**53),  # big_int_val
                round(RNG.uniform(-1e6, 1e6), 6),  # float_val
                round(-abs(RNG.gauss(100, 50)), 4),  # negative_val
                RNG.choice(FIRST_NAMES),  # text_val
                long_text,  # long_text_val
                "" if i % 10 == 0 else f"content_{i}",  # empty_str_val
                blob_data,  # blob_val
                json_data,  # json_val
                RNG.randint(0, 999) if i % 3 != 0 else None,  # nullable_int
                RNG.choice(CITIES) if i % 4 != 0 else None,  # nullable_text
                0.0,  # zero_val
            ),
        )

    conn.commit()

    for table in ["customers", "products", "datatypes"]:
        result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        count = result[0] if result else 0
        print(f"  [ok] {table}: {count} rows")

    conn.close()


# ---------------------------------------------------------------------------
# DuckDB
# ---------------------------------------------------------------------------


def init_duckdb(
    db_path: Path, customers: list[list[object]], products: list[list[object]]
) -> None:
    print(f"\n  Creating DuckDB database: {db_path}")
    if db_path.exists():
        db_path.unlink()

    conn = duckdb.connect(str(db_path))

    # Customers — load from CSV for proper type inference
    customers_csv = str(DATA_DIR / "customers-1000.csv").replace("\\", "/")
    conn.execute(f"""
        CREATE TABLE customers AS
        SELECT
            ROW_NUMBER() OVER () AS id,
            customer_id, first_name, last_name, company, city, country,
            phone1, phone2, email, subscription_date, website
        FROM read_csv('{customers_csv}', header=true, null_padding=true)
    """)

    # Products — load from CSV for proper type inference
    products_csv = str(DATA_DIR / "products-1000.csv").replace("\\", "/")
    conn.execute(f"""
        CREATE TABLE products AS
        SELECT
            ROW_NUMBER() OVER () AS id,
            name, description, brand, category,
            CAST(price AS DOUBLE) AS price,
            currency,
            CAST(stock AS INTEGER) AS stock,
            ean, color, size, availability, internal_id
        FROM read_csv('{products_csv}', header=true, null_padding=true)
    """)

    # Datatypes table — exercises DuckDB's rich type system
    conn.execute("""
        CREATE TABLE datatypes (
            id INTEGER PRIMARY KEY,
            bool_val BOOLEAN,
            date_val DATE,
            datetime_val TIMESTAMP,
            time_val TIME,
            int_val INTEGER,
            bigint_val BIGINT,
            hugeint_val HUGEINT,
            float_val FLOAT,
            double_val DOUBLE,
            decimal_val DECIMAL(18, 4),
            text_val VARCHAR,
            long_text_val VARCHAR,
            blob_val BLOB,
            json_val JSON,
            list_int_val INTEGER[],
            list_text_val VARCHAR[],
            struct_val STRUCT(name VARCHAR, value INTEGER, active BOOLEAN),
            map_val MAP(VARCHAR, INTEGER),
            nested_list_val INTEGER[][],
            uuid_val UUID,
            nullable_int INTEGER,
            nullable_text VARCHAR,
            empty_str_val VARCHAR,
            negative_val DOUBLE,
            zero_val DOUBLE
        )
    """)

    for i in range(100):
        blob_hex = (struct.pack("!If", i, float(i) * 1.5)).hex()
        json_data = json.dumps(
            {
                "id": i,
                "tags": [f"tag{j}" for j in range(i % 5)],
                "nested": {"key": f"val_{i}", "flag": i % 2 == 0},
            }
        )
        long_text = f"Row {i}: " + "abcdefghij " * (i % 50 + 1)
        list_int = [RNG.randint(0, 100) for _ in range(i % 7)]
        list_text = [RNG.choice(COLORS) for _ in range(i % 4)]
        struct_name = RNG.choice(FIRST_NAMES)
        struct_val = RNG.randint(0, 1000)
        struct_active = i % 2 == 0
        map_keys = [f"k{j}" for j in range(i % 5)]
        map_vals = [RNG.randint(0, 100) for _ in range(i % 5)]
        nested_list = [[RNG.randint(0, 10) for _ in range(j % 3 + 1)] for j in range(i % 4)]
        uuid_val = gen_uuid()
        nullable_int = str(RNG.randint(0, 999)) if i % 3 != 0 else "NULL"
        nullable_text = f"'{RNG.choice(CITIES)}'" if i % 4 != 0 else "NULL"
        empty_str = "''" if i % 10 == 0 else f"'content_{i}'"
        hour = RNG.randint(0, 23)
        minute = RNG.randint(0, 59)
        second = RNG.randint(0, 59)
        negative = round(-abs(RNG.gauss(100, 50)), 4)
        hugeint = RNG.randint(2**63, 2**100)

        conn.execute(f"""
            INSERT INTO datatypes VALUES (
                {i},
                {str(struct_active).lower()},
                '{gen_date()}',
                '{gen_datetime()}',
                '{hour:02d}:{minute:02d}:{second:02d}',
                {RNG.randint(-1000000, 1000000)},
                {RNG.randint(2**31, 2**53)},
                {hugeint},
                {round(RNG.uniform(-1e6, 1e6), 6)},
                {round(RNG.uniform(-1e15, 1e15), 10)},
                {round(RNG.uniform(-99999, 99999), 4)},
                '{RNG.choice(FIRST_NAMES)}',
                '{long_text.replace("'", "''")}',
                '\\x{blob_hex}',
                '{json_data.replace("'", "''")}',
                {list_int},
                {list_text},
                {{'name': '{struct_name}', 'value': {struct_val},
                  'active': {str(struct_active).lower()}}},
                MAP {{{
            ", ".join(f"'{k}': {v}" for k, v in zip(map_keys, map_vals, strict=True))
        }}},
                {nested_list},
                '{uuid_val}',
                {nullable_int},
                {nullable_text},
                {empty_str},
                {negative},
                0.0
            )
        """)

    for table in ["customers", "products", "datatypes"]:
        result = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        count = result[0] if result else 0
        print(f"  [ok] {table}: {count} rows")

    conn.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=== qdo test data initialization ===\n")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Generate synthetic data
    print("Generating synthetic data...")
    cust_headers, cust_rows = gen_customers(1000)
    prod_headers, prod_rows = gen_products(1000)

    # Write CSVs
    print("\nWriting CSVs...")
    write_csv(DATA_DIR / "customers-1000.csv", cust_headers, cust_rows)
    write_csv(DATA_DIR / "products-1000.csv", prod_headers, prod_rows)

    # Create databases
    print("\nCreating databases...")
    init_sqlite(DATA_DIR / "test.db", cust_rows, prod_rows)
    init_duckdb(DATA_DIR / "test.duckdb", cust_rows, prod_rows)

    print("\n=== Done! ===")
    print(f"Data directory: {DATA_DIR.resolve()}")
    print("Files:")
    for f in sorted(DATA_DIR.iterdir()):
        print(f"  {f.name} ({f.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
