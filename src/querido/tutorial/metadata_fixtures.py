"""Human-field enrichments for the agent tutorial.

These dicts provide the descriptions, valid_values, and pii flags that a real
user would fill into their metadata YAML.  The agent tutorial runner merges
these on top of the machine-populated fields written by ``metadata init``.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# parks
# ---------------------------------------------------------------------------

PARKS_HUMAN: dict = {
    "table_description": (
        "US National Parks managed by the National Park Service (NPS). "
        "One row per park. Primary reference table — trails, wildlife_sightings, "
        "and visitor_stats all join to this via park_id."
    ),
    "data_owner": "NPS Data Division",
    "update_frequency": "Annual",
    "notes": (
        "established_date reflects the original NPS designation date, not the "
        "initial federal authorization, which may be earlier. "
        "Approximately 20% of parks have NULL descriptions — these are newer "
        "additions without finalized text."
    ),
    "columns": {
        "park_id": {
            "description": (
                "Unique numeric identifier for each park. Primary key. "
                "Referenced by trails.park_id, wildlife_sightings.park_id, "
                "and visitor_stats.park_id."
            ),
            "pii": False,
        },
        "name": {
            "description": "Official NPS park name (e.g. 'Yellowstone', 'Grand Canyon').",
            "pii": False,
        },
        "state": {
            "description": (
                "Two-letter US state or territory abbreviation where the park "
                "is primarily located."
            ),
            "pii": False,
        },
        "region": {
            "description": (
                "NPS administrative region. Use this column for geographic grouping "
                "and regional comparisons."
            ),
            "pii": False,
            "valid_values": [
                "Alaska",
                "Intermountain",
                "Midwest",
                "National Capital",
                "Northeast",
                "Pacific West",
                "Southeast",
            ],
        },
        "area_sq_km": {
            "description": "Total park area in square kilometers.",
            "pii": False,
        },
        "established_date": {
            "description": (
                "Date the park was officially designated by Congress or NPS. "
                "Use EXTRACT(YEAR FROM established_date) to filter or group by year."
            ),
            "pii": False,
        },
        "elevation_ft": {
            "description": "Elevation of the park's highest point in feet.",
            "pii": False,
        },
        "annual_visitors": {
            "description": (
                "Most recent reported annual visitor count. "
                "NULL for parks with incomplete NPS reporting."
            ),
            "pii": False,
        },
        "has_camping": {
            "description": "True if the park has designated frontcountry camping facilities.",
            "pii": False,
        },
        "has_lodging": {
            "description": "True if the park has NPS-operated or concessionaire lodging.",
            "pii": False,
        },
        "description": {
            "description": (
                "Short prose description of the park's notable features. "
                "Approximately 20% NULL — exclude from aggregations or use COALESCE."
            ),
            "pii": False,
        },
    },
}

# ---------------------------------------------------------------------------
# wildlife_sightings
# ---------------------------------------------------------------------------

WILDLIFE_SIGHTINGS_HUMAN: dict = {
    "table_description": (
        "Individual wildlife sightings reported by park rangers and visitors. "
        "One row per sighting event. trail_id is optional — many sightings "
        "occur off established trails."
    ),
    "data_owner": "NPS Wildlife Monitoring Program",
    "update_frequency": "Continuous (daily ingestion)",
    "notes": (
        "notes is sparse (~60% NULL) — avoid filtering on this column. "
        "trail_id is ~30% NULL for off-trail sightings; use LEFT JOIN when "
        "joining to trails. "
        "verified=true records have been confirmed by a ranger; "
        "use WHERE verified = true for higher-confidence analysis."
    ),
    "columns": {
        "sighting_id": {
            "description": "Unique sighting event identifier. Primary key.",
            "pii": False,
        },
        "park_id": {
            "description": "Foreign key to parks.park_id.",
            "pii": False,
        },
        "species": {
            "description": (
                "Common name of the species observed (e.g. 'Black Bear', 'Elk', 'Bald Eagle')."
            ),
            "pii": False,
        },
        "category": {
            "description": "Taxonomic category of the observed species.",
            "pii": False,
            "valid_values": ["mammal", "bird", "reptile", "amphibian", "fish"],
        },
        "sighting_date": {
            "description": "Date the sighting was recorded (YYYY-MM-DD).",
            "pii": False,
        },
        "time_of_day": {
            "description": "Approximate time of day when the sighting occurred.",
            "pii": False,
            "valid_values": ["dawn", "morning", "afternoon", "dusk", "night"],
        },
        "trail_id": {
            "description": (
                "Foreign key to trails.trail_id. "
                "NULL if the sighting was off-trail (~30% of records). "
                "Always use LEFT JOIN when joining to trails."
            ),
            "pii": False,
        },
        "observer": {
            "description": "Name or identifier of the person who reported the sighting.",
            "pii": True,
        },
        "count": {
            "description": "Number of individual animals observed in the sighting event.",
            "pii": False,
        },
        "verified": {
            "description": (
                "True if the sighting was confirmed by a park ranger. "
                "Use WHERE verified = true for higher-confidence queries."
            ),
            "pii": False,
        },
        "notes": {
            "description": (
                "Free-text field for additional observer notes. "
                "Approximately 60% NULL — do not filter on this column."
            ),
            "pii": False,
        },
    },
}
