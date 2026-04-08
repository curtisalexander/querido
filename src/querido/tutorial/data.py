"""Generate the National Parks tutorial DuckDB database.

All data is deterministic (seeded RNG) so the tutorial output is
reproducible across runs.
"""

from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path

SEED = 42

# ---------------------------------------------------------------------------
# Word lists
# ---------------------------------------------------------------------------

# fmt: off
PARKS: list[tuple[str, str, str, float, str, int, int, bool, bool, str | None]] = [
    # (name, state, region, area_sq_km, established, elevation_ft, annual_visitors, camping, lodging, description)
    ("Yellowstone", "Wyoming", "Intermountain", 8983.2, "1872-03-01", 11358, 4860242, True, True, "First national park, famous for geysers and hot springs."),
    ("Yosemite", "California", "Pacific West", 3074.1, "1890-10-01", 13114, 3667550, True, True, "Granite cliffs, waterfalls, and giant sequoia groves."),
    ("Grand Canyon", "Arizona", "Intermountain", 4862.9, "1919-02-26", 8297, 6380495, True, True, "Mile-deep canyon carved by the Colorado River."),
    ("Zion", "Utah", "Intermountain", 595.9, "1919-11-19", 8726, 4692417, True, True, None),
    ("Glacier", "Montana", "Intermountain", 4100.0, "1910-05-11", 10466, 2946681, True, True, "Crown of the Continent with over 700 miles of trails."),
    ("Rocky Mountain", "Colorado", "Intermountain", 1075.6, "1915-01-26", 14259, 4670053, True, True, "Alpine tundra, peaks over 14,000 feet."),
    ("Grand Teton", "Wyoming", "Intermountain", 1254.7, "1929-02-26", 13775, 3405614, True, True, None),
    ("Acadia", "Maine", "Northeast", 198.6, "1919-02-26", 1530, 3970260, True, False, "Rocky coastline on the Atlantic."),
    ("Olympic", "Washington", "Pacific West", 3733.8, "1938-06-29", 7980, 2718925, True, True, "Rainforests, glaciated peaks, and wild coastline."),
    ("Great Smoky Mountains", "Tennessee", "Southeast", 2114.2, "1934-06-15", 6643, 12104020, True, True, "Most visited park, famous for misty mountain ridges."),
    ("Shenandoah", "Virginia", "Northeast", 805.4, "1935-12-26", 4051, 1399247, True, True, "Skyline Drive winds through the Blue Ridge Mountains."),
    ("Joshua Tree", "California", "Pacific West", 3199.6, "1994-10-31", 5814, 2942382, True, False, None),
    ("Death Valley", "California", "Pacific West", 13793.3, "1994-10-31", 11049, 1128862, True, True, "Hottest, driest, lowest point in North America."),
    ("Arches", "Utah", "Intermountain", 310.3, "1971-11-12", 5653, 1806865, False, False, "Over 2,000 natural stone arches."),
    ("Canyonlands", "Utah", "Intermountain", 1366.2, "1964-09-12", 7120, 911594, True, False, None),
    ("Bryce Canyon", "Utah", "Intermountain", 145.0, "1928-02-25", 9115, 2365110, True, True, "Crimson-colored hoodoos in an amphitheater of rock."),
    ("Capitol Reef", "Utah", "Intermountain", 979.0, "1971-12-18", 8960, 1227627, True, False, "Waterpocket Fold, a 100-mile wrinkle in the earth's crust."),
    ("Mesa Verde", "Colorado", "Intermountain", 212.4, "1906-06-29", 8572, 556203, True, True, "Ancestral Puebloan cliff dwellings."),
    ("Badlands", "South Dakota", "Midwest", 978.0, "1978-11-10", 3282, 1009987, True, True, "Sharply eroded buttes and the richest fossil beds of the age of mammals."),
    ("Crater Lake", "Oregon", "Pacific West", 741.5, "1902-05-22", 8929, 704712, True, True, "Deepest lake in the US, formed in a collapsed volcano."),
    ("Mount Rainier", "Washington", "Pacific West", 956.6, "1899-03-02", 14411, 1670063, True, True, None),
    ("North Cascades", "Washington", "Pacific West", 2042.8, "1968-10-02", 9220, 38208, True, False, "Rugged peaks and over 300 glaciers."),
    ("Redwood", "California", "Pacific West", 560.0, "1968-10-02", 3170, 449722, True, False, "Tallest trees on Earth, ancient coastal redwoods."),
    ("Sequoia", "California", "Pacific West", 1635.2, "1890-09-25", 14494, 1059548, True, True, "Home of General Sherman, the world's largest tree by volume."),
    ("Kings Canyon", "California", "Pacific West", 1869.3, "1940-03-04", 14248, 562918, True, False, None),
    ("Lassen Volcanic", "California", "Pacific West", 431.4, "1916-08-09", 10457, 359635, True, False, "All four types of volcanoes found here."),
    ("Pinnacles", "California", "Pacific West", 108.0, "2013-01-10", 3304, 348857, True, False, "Remnants of an ancient volcano, talus caves."),
    ("Channel Islands", "California", "Pacific West", 1009.9, "1980-03-05", 2450, 319252, True, False, "Five remote islands off the Southern California coast."),
    ("Denali", "Alaska", "Alaska", 24585.0, "1917-02-26", 20310, 229521, True, True, "North America's tallest peak at 20,310 feet."),
    ("Kenai Fjords", "Alaska", "Alaska", 2711.3, "1980-12-02", 6612, 411782, True, False, "Where ice meets the sea — massive glaciers calving into the ocean."),
    ("Wrangell-St. Elias", "Alaska", "Alaska", 53321.0, "1980-12-02", 18008, 74518, True, False, None),
    ("Gates of the Arctic", "Alaska", "Alaska", 34287.0, "1980-12-02", 8510, 7362, False, False, "No roads, no trails. Pure wilderness above the Arctic Circle."),
    ("Katmai", "Alaska", "Alaska", 14870.0, "1980-12-02", 7600, 84167, True, True, "Famous for brown bears catching salmon at Brooks Falls."),
    ("Glacier Bay", "Alaska", "Alaska", 13044.6, "1980-12-02", 15325, 597915, True, True, "Tidewater glaciers, whales, and temperate rainforest."),
    ("Everglades", "Florida", "Southeast", 6106.5, "1947-12-06", 8, 954279, True, False, "Largest subtropical wilderness in the US."),
    ("Biscayne", "Florida", "Southeast", 700.0, "1980-06-28", 10, 705655, True, False, "95% underwater — mangroves, coral reefs, and Keys."),
    ("Dry Tortugas", "Florida", "Southeast", 261.8, "1992-10-26", 10, 83817, True, False, None),
    ("Hot Springs", "Arkansas", "Southeast", 22.5, "1921-03-04", 1405, 2162884, False, True, "Thermal springs flowing from Hot Springs Mountain."),
    ("Mammoth Cave", "Kentucky", "Southeast", 214.3, "1941-07-01", 968, 551590, True, True, "World's longest known cave system with 400+ miles mapped."),
    ("Congaree", "South Carolina", "Southeast", 107.1, "2003-11-10", 143, 215181, True, False, "Largest intact expanse of old-growth bottomland hardwood forest."),
    ("Big Bend", "Texas", "Intermountain", 3242.2, "1944-06-12", 7832, 581220, True, True, None),
    ("Guadalupe Mountains", "Texas", "Intermountain", 349.5, "1972-09-30", 8749, 243291, True, False, "Guadalupe Peak is the highest point in Texas."),
    ("Carlsbad Caverns", "New Mexico", "Intermountain", 189.3, "1930-05-14", 6368, 438228, False, False, "Over 119 caves, including a massive limestone chamber."),
    ("White Sands", "New Mexico", "Intermountain", 592.2, "2019-12-20", 4235, 782469, True, False, "World's largest gypsum dune field."),
    ("Petrified Forest", "Arizona", "Intermountain", 895.9, "1962-12-09", 6234, 602279, False, False, None),
    ("Saguaro", "Arizona", "Intermountain", 371.0, "1994-10-14", 8666, 1080688, False, False, "Giant saguaro cacti up to 50 feet tall and 200 years old."),
    ("Voyageurs", "Minnesota", "Midwest", 883.1, "1975-04-08", 1425, 243042, True, False, "Interconnected waterways and boreal forest."),
    ("Theodore Roosevelt", "North Dakota", "Midwest", 285.1, "1978-11-10", 2865, 691658, True, False, "Colorful painted canyon and wild bison herds."),
    ("Wind Cave", "South Dakota", "Midwest", 137.5, "1903-01-09", 5013, 709001, True, False, "One of the longest caves in the world with rare boxwork formations."),
    ("Indiana Dunes", "Indiana", "Midwest", 62.1, "2019-02-15", 803, 3177210, True, False, None),
    ("Cuyahoga Valley", "Ohio", "Midwest", 131.8, "2000-10-11", 1075, 2096053, False, True, "Waterfalls, forests, and the scenic Cuyahoga River."),
    ("Isle Royale", "Michigan", "Midwest", 2314.0, "1940-04-03", 1394, 25798, True, False, "Remote island wilderness, wolf and moose research."),
    ("Virgin Islands", "US Virgin Islands", "Southeast", 59.5, "1956-08-02", 1277, 323999, True, False, "Pristine beaches, coral reefs, and tropical forests."),
    ("Haleakala", "Hawaii", "Pacific West", 134.0, "1916-08-01", 10023, 994394, True, False, "Volcanic crater above the clouds on Maui."),
    ("Hawaii Volcanoes", "Hawaii", "Pacific West", 1308.9, "1916-08-01", 13681, 1262747, True, True, "Active volcanoes including Kilauea."),
    ("American Samoa", "American Samoa", "Pacific West", 33.4, "1988-10-31", 3170, 8495, False, False, None),
    ("Gateway Arch", "Missouri", "Midwest", 0.8, "2018-02-22", 630, 2016180, False, False, "The Gateway Arch towers 630 feet over the St. Louis riverfront."),
    ("New River Gorge", "West Virginia", "Northeast", 28.6, "2020-12-27", 3185, 1682720, True, False, "One of the oldest rivers on the continent carving a deep canyon."),
    ("Black Canyon of the Gunnison", "Colorado", "Intermountain", 124.6, "1999-10-21", 8563, 308910, True, False, "Sheer cliffs dropping 2,000 feet to the Gunnison River."),
]
# fmt: on

TRAIL_PREFIXES = [
    "Eagle",
    "River",
    "Sunset",
    "Bear",
    "Hidden",
    "Thunder",
    "Crystal",
    "Shadow",
    "Cedar",
    "Falcon",
    "Aspen",
    "Granite",
    "Wildflower",
    "Pine",
    "Elk",
    "Osprey",
    "Lakeshore",
    "Canyon",
    "Summit",
    "Cascade",
]

TRAIL_MIDDLES = [
    "Summit",
    "Bend",
    "Ridge",
    "Creek",
    "Canyon",
    "Falls",
    "Valley",
    "Peak",
    "Lake",
    "Meadow",
    "Point",
    "Basin",
    "Overlook",
    "Crossing",
]

TRAIL_SUFFIXES = ["Trail", "Loop", "Path", "Route"]

SPECIES: list[tuple[str, str]] = [
    # mammals
    ("Black Bear", "mammal"),
    ("Grizzly Bear", "mammal"),
    ("Elk", "mammal"),
    ("Mule Deer", "mammal"),
    ("White-tailed Deer", "mammal"),
    ("Moose", "mammal"),
    ("Gray Wolf", "mammal"),
    ("Mountain Lion", "mammal"),
    ("Bighorn Sheep", "mammal"),
    ("Bison", "mammal"),
    ("Coyote", "mammal"),
    ("Red Fox", "mammal"),
    ("Pronghorn", "mammal"),
    ("Bobcat", "mammal"),
    ("River Otter", "mammal"),
    ("Marmot", "mammal"),
    ("Pika", "mammal"),
    ("Raccoon", "mammal"),
    # birds
    ("Bald Eagle", "bird"),
    ("Golden Eagle", "bird"),
    ("Osprey", "bird"),
    ("Great Blue Heron", "bird"),
    ("Peregrine Falcon", "bird"),
    ("Steller's Jay", "bird"),
    ("Clark's Nutcracker", "bird"),
    ("Wild Turkey", "bird"),
    ("Raven", "bird"),
    ("Red-tailed Hawk", "bird"),
    ("Great Horned Owl", "bird"),
    ("Trumpeter Swan", "bird"),
    # reptiles
    ("Western Rattlesnake", "reptile"),
    ("Garter Snake", "reptile"),
    ("Collared Lizard", "reptile"),
    ("Desert Tortoise", "reptile"),
    # amphibians
    ("Spotted Salamander", "amphibian"),
    ("Pacific Tree Frog", "amphibian"),
    ("Bullfrog", "amphibian"),
    # fish
    ("Cutthroat Trout", "fish"),
    ("Rainbow Trout", "fish"),
    ("Brook Trout", "fish"),
]

SPECIES_WEIGHTS = [
    # mammals (heavier — more commonly sighted)
    8,
    3,
    12,
    10,
    10,
    4,
    2,
    1,
    5,
    6,
    8,
    4,
    3,
    2,
    2,
    3,
    2,
    6,
    # birds
    4,
    3,
    5,
    4,
    2,
    6,
    3,
    5,
    8,
    6,
    3,
    2,
    # reptiles
    3,
    4,
    2,
    1,
    # amphibians
    2,
    3,
    2,
    # fish
    4,
    5,
    3,
]

TIME_OF_DAY = ["dawn", "morning", "afternoon", "dusk", "night"]
TIME_WEIGHTS = [15, 35, 30, 15, 5]

DIFFICULTIES = ["easy", "moderate", "strenuous", "expert"]
DIFFICULTY_WEIGHTS = [25, 45, 20, 10]

TRAIL_TYPES = ["out-and-back", "loop", "point-to-point"]
TRAIL_TYPE_WEIGHTS = [50, 35, 15]

SURFACES = ["paved", "gravel", "dirt", "rocky", "mixed"]
SURFACE_WEIGHTS = [10, 20, 35, 15, 20]

TRAIL_CONDITIONS = ["excellent", "good", "fair", "poor", "closed"]

RANGERS = [
    "A. Martinez",
    "B. Chen",
    "C. Okafor",
    "D. Johansson",
    "E. Patel",
    "F. Reyes",
    "G. Thompson",
    "H. Yamamoto",
    "I. Kowalski",
    "J. Williams",
    "K. Nguyen",
    "L. Brown",
    "M. Garcia",
    "N. Kim",
    "O. Petrov",
    "P. Santos",
    "Q. Al-Rashid",
    "R. Larsen",
    "S. Dubois",
    "T. Acharya",
]

SIGHTING_NOTES = [
    "Observed near trailhead at close range.",
    "Spotted from overlook, moving through meadow.",
    "Heard vocalizations before visual confirmation.",
    "Photographed by visitor, confirmed by ranger.",
    "Feeding along stream bank.",
    "Crossing trail approximately 50 meters ahead.",
    "Tracks and scat found, then visual sighting.",
    "Nesting pair with juveniles.",
    "Briefly visible before retreating into brush.",
    "Seen at dusk near campground perimeter.",
    "Large group grazing in open valley.",
    "Soaring overhead, distinctive markings noted.",
]

# Region → base temp offset for seasonal calculation
REGION_TEMP_BASE: dict[str, float] = {
    "Pacific West": 55.0,
    "Intermountain": 45.0,
    "Southeast": 65.0,
    "Northeast": 45.0,
    "Midwest": 42.0,
    "Alaska": 25.0,
    "National Capital": 55.0,
}

# Month → seasonal offset (Jan=1)
MONTH_TEMP_OFFSET = [-15, -12, -5, 5, 15, 22, 28, 26, 18, 8, -3, -12]

# Month → visitor multiplier (summer peak)
MONTH_VISITOR_MULT = [0.3, 0.3, 0.5, 0.7, 0.9, 1.4, 1.8, 1.7, 1.2, 0.8, 0.4, 0.3]


# ---------------------------------------------------------------------------
# Database creation
# ---------------------------------------------------------------------------


def create_tutorial_db(db_path: Path) -> Path:
    """Generate the National Parks tutorial DuckDB database at *db_path*.

    Returns the path for convenience.  All data is deterministic (seeded RNG).
    Requires duckdb to be installed.
    """
    import duckdb

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(db_path))
    rng = random.Random(SEED)

    try:
        _create_parks(conn)
        _create_trails(conn, rng)
        _create_wildlife_sightings(conn, rng)
        _create_visitor_stats(conn, rng)
    finally:
        conn.close()

    return db_path


def _create_parks(conn: object) -> None:
    """Create and populate the parks table from curated data."""
    conn.execute("""
        create table parks (
            park_id integer primary key,
            name varchar not null,
            state varchar not null,
            region varchar not null,
            area_sq_km double,
            established_date date,
            elevation_ft integer,
            annual_visitors integer,
            has_camping boolean,
            has_lodging boolean,
            description varchar
        )
    """)  # type: ignore[union-attr]
    for i, p in enumerate(PARKS, 1):
        name, state, region, area, est, elev, visitors, camp, lodge, desc = p
        conn.execute(  # type: ignore[union-attr]
            "insert into parks values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [i, name, state, region, area, est, elev, visitors, camp, lodge, desc],
        )


def _create_trails(conn: object, rng: random.Random) -> None:
    """Create and populate the trails table with generated data."""
    conn.execute("""
        create table trails (
            trail_id integer primary key,
            park_id integer not null,
            name varchar not null,
            distance_miles double,
            elevation_gain_ft integer,
            difficulty varchar,
            trail_type varchar,
            surface varchar,
            dog_friendly boolean,
            estimated_hours double
        )
    """)  # type: ignore[union-attr]

    trail_id = 0
    for park_id in range(1, len(PARKS) + 1):
        n_trails = rng.randint(2, 6)
        for _ in range(n_trails):
            trail_id += 1
            prefix = rng.choice(TRAIL_PREFIXES)
            middle = rng.choice(TRAIL_MIDDLES)
            suffix = rng.choice(TRAIL_SUFFIXES)
            name = f"{prefix} {middle} {suffix}"

            distance = round(rng.uniform(0.5, 25.0), 1)
            elevation = rng.randint(50, 5000)
            difficulty = rng.choices(DIFFICULTIES, weights=DIFFICULTY_WEIGHTS)[0]
            trail_type = rng.choices(TRAIL_TYPES, weights=TRAIL_TYPE_WEIGHTS)[0]
            surface = rng.choices(SURFACES, weights=SURFACE_WEIGHTS)[0]
            dog_friendly = rng.random() < 0.3

            if rng.random() < 0.10:
                est_hours = None
            else:
                speed = rng.uniform(1.5, 3.0)
                est_hours = round(distance / speed, 1)

            conn.execute(  # type: ignore[union-attr]
                "insert into trails values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    trail_id,
                    park_id,
                    name,
                    distance,
                    elevation,
                    difficulty,
                    trail_type,
                    surface,
                    dog_friendly,
                    est_hours,
                ],
            )


def _create_wildlife_sightings(conn: object, rng: random.Random) -> None:
    """Create and populate the wildlife_sightings table."""
    conn.execute("""
        create table wildlife_sightings (
            sighting_id integer primary key,
            park_id integer not null,
            species varchar not null,
            category varchar not null,
            sighting_date date,
            time_of_day varchar,
            trail_id integer,
            observer varchar,
            count integer,
            verified boolean,
            notes varchar
        )
    """)  # type: ignore[union-attr]

    # Build lookup: park_id → list of trail_ids for that park
    n_parks = len(PARKS)
    # We need to reconstruct which trails belong to which park.
    # Re-seed a separate RNG to match _create_trails exactly.
    trail_rng = random.Random(SEED)
    park_trails: dict[int, list[int]] = {}
    trail_id = 0
    for park_id in range(1, n_parks + 1):
        n_trails = trail_rng.randint(2, 6)
        trails_for_park = []
        for _ in range(n_trails):
            trail_id += 1
            # Consume the same random calls as _create_trails
            trail_rng.choice(TRAIL_PREFIXES)
            trail_rng.choice(TRAIL_MIDDLES)
            trail_rng.choice(TRAIL_SUFFIXES)
            trail_rng.uniform(0.5, 25.0)
            trail_rng.randint(50, 5000)
            trail_rng.choices(DIFFICULTIES, weights=DIFFICULTY_WEIGHTS)
            trail_rng.choices(TRAIL_TYPES, weights=TRAIL_TYPE_WEIGHTS)
            trail_rng.choices(SURFACES, weights=SURFACE_WEIGHTS)
            trail_rng.random()  # dog_friendly
            if trail_rng.random() < 0.10:
                pass
            else:
                trail_rng.uniform(1.5, 3.0)
            trails_for_park.append(trail_id)
        park_trails[park_id] = trails_for_park

    # Weight parks by annual visitors for sighting distribution
    park_weights = [p[7] for p in PARKS]
    park_ids = list(range(1, n_parks + 1))

    start_date = date(2020, 1, 1)
    date_range = (date(2024, 12, 31) - start_date).days

    for sid in range(1, 1001):
        park_id = rng.choices(park_ids, weights=park_weights)[0]
        species, category = rng.choices(SPECIES, weights=SPECIES_WEIGHTS)[0]
        sighting_date = start_date + timedelta(days=rng.randint(0, date_range))
        time = rng.choices(TIME_OF_DAY, weights=TIME_WEIGHTS)[0]

        if rng.random() < 0.70 and park_trails.get(park_id):
            t_id = rng.choice(park_trails[park_id])
        else:
            t_id = None

        observer = rng.choice(RANGERS)
        count = min(max(1, int(rng.expovariate(0.5))), 50)
        verified = rng.random() < 0.80
        notes = rng.choice(SIGHTING_NOTES) if rng.random() < 0.40 else None

        conn.execute(  # type: ignore[union-attr]
            "insert into wildlife_sightings values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                sid,
                park_id,
                species,
                category,
                str(sighting_date),
                time,
                t_id,
                observer,
                count,
                verified,
                notes,
            ],
        )


def _create_visitor_stats(conn: object, rng: random.Random) -> None:
    """Create and populate the visitor_stats table."""
    conn.execute("""
        create table visitor_stats (
            stat_id integer primary key,
            park_id integer not null,
            month varchar not null,
            visitors integer,
            camping_permits integer,
            search_and_rescue_incidents integer,
            trail_conditions varchar,
            avg_temp_f double
        )
    """)  # type: ignore[union-attr]

    stat_id = 0
    sar_weights = [60, 25, 10, 3, 1, 1]

    for park_idx, park in enumerate(PARKS):
        park_id = park_idx + 1
        region = park[2]
        annual = park[6]
        has_camping = park[7]
        base_monthly = annual / 12

        base_temp = REGION_TEMP_BASE.get(region, 50.0)

        for year in range(2020, 2025):
            for month_num in range(1, 13):
                # Skip ~20% of park-months for realistic gaps
                if rng.random() < 0.20:
                    continue

                stat_id += 1
                month_str = f"{year}-{month_num:02d}"

                # Visitors: seasonal pattern + noise
                mult = MONTH_VISITOR_MULT[month_num - 1]
                noise = rng.uniform(0.8, 1.2)
                visitors = max(0, int(base_monthly * mult * noise))

                # Camping permits: NULL if no camping, else proportional
                if not has_camping:
                    camping = None
                else:
                    camping = max(0, int(visitors * rng.uniform(0.05, 0.20)))

                # SAR incidents: rare
                sar = rng.choices(range(6), weights=sar_weights)[0]

                # Trail conditions: seasonal
                if month_num in (6, 7, 8):
                    cond = rng.choices(TRAIL_CONDITIONS, weights=[40, 40, 15, 4, 1])[0]
                elif month_num in (12, 1, 2):
                    cond = rng.choices(TRAIL_CONDITIONS, weights=[5, 15, 30, 30, 20])[0]
                else:
                    cond = rng.choices(TRAIL_CONDITIONS, weights=[20, 35, 30, 10, 5])[0]

                # Temperature: region base + seasonal offset + noise
                temp_offset = MONTH_TEMP_OFFSET[month_num - 1]
                temp = round(base_temp + temp_offset + rng.gauss(0, 3), 1)

                conn.execute(  # type: ignore[union-attr]
                    "insert into visitor_stats values (?, ?, ?, ?, ?, ?, ?, ?)",
                    [stat_id, park_id, month_str, visitors, camping, sar, cond, temp],
                )
