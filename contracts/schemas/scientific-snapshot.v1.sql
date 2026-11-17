PRAGMA user_version = 1;

CREATE TABLE snapshot_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE TABLE weather_locations (
    weather_id TEXT PRIMARY KEY,
    cell_id TEXT NOT NULL UNIQUE,
    weather_lat REAL NOT NULL,
    weather_lon REAL NOT NULL,
    center_lat REAL NOT NULL,
    center_lon REAL NOT NULL,
    center_inside INTEGER NOT NULL CHECK (center_inside IN (0, 1)),
    intersects INTEGER NOT NULL CHECK (intersects IN (0, 1))
) WITHOUT ROWID;

CREATE TABLE weather_daily (
    weather_id TEXT NOT NULL,
    date TEXT NOT NULL,
    temperature_2m REAL NOT NULL,
    relative_humidity_2m REAL NOT NULL,
    wind_speed_10m REAL NOT NULL,
    rain_24h REAL NOT NULL,
    ffmc REAL NOT NULL,
    dmc REAL NOT NULL,
    dc REAL NOT NULL,
    isi REAL NOT NULL,
    bui REAL NOT NULL,
    fwi REAL NOT NULL,
    firms_count INTEGER NOT NULL CHECK (firms_count >= 0),
    PRIMARY KEY (weather_id, date)
) WITHOUT ROWID;

CREATE INDEX weather_daily_date_idx ON weather_daily (date);

CREATE TABLE monthly_fwi_reference (
    weather_id TEXT NOT NULL,
    month INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    median_fwi REAL NOT NULL,
    PRIMARY KEY (weather_id, month)
) WITHOUT ROWID;
