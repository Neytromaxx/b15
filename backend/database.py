import sqlite3
import math
import os
import re
from datetime import datetime, timedelta

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None

# Detect Supabase / Vercel Postgres connection URL automatically
POSTGRES_URL = (
    os.environ.get("POSTGRES_URL_NON_POOLING")
    or os.environ.get("POSTGRES_URL")
    or os.environ.get("DATABASE_URL")
)

if os.environ.get("VERCEL"):
    DB_PATH = "/tmp/beton_erp.db"
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), "beton_erp.db")


def clean_pg_url(url: str) -> str:
    """
    Cleans Supabase/Vercel Postgres URI so psycopg2 connects without unknown query param errors (e.g. supa=...).
    """
    url = url.strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if "?" in url:
        base, _ = url.split("?", 1)
        return base + "?sslmode=require"
    return url


class PgRow(dict):
    """
    Dict-like row that also supports integer indexing (row[0]) just like sqlite3.Row.
    """
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


class PgCursorWrapper:
    """
    Wraps psycopg2 RealDictCursor so existing SQLite queries (?, AUTOINCREMENT, INSERT OR IGNORE, lastrowid)
    execute seamlessly on Supabase PostgreSQL.
    """
    def __init__(self, raw_conn, raw_cur):
        self.raw_conn = raw_conn
        self.raw_cur = raw_cur
        self.lastrowid = None

    def _translate_sql(self, sql: str):
        s = sql.strip()
        if s.upper().startswith("PRAGMA"):
            return None, False

        # Translate AUTOINCREMENT -> SERIAL
        s = re.sub(
            r"INTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT",
            "SERIAL PRIMARY KEY",
            s,
            flags=re.IGNORECASE,
        )

        # Translate ALTER TABLE ... ADD COLUMN -> ADD COLUMN IF NOT EXISTS
        s = re.sub(
            r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(?!IF\s+NOT\s+EXISTS)",
            r"ALTER TABLE \1 ADD COLUMN IF NOT EXISTS ",
            s,
            flags=re.IGNORECASE,
        )

        # Translate INSERT OR IGNORE INTO -> INSERT INTO ... ON CONFLICT DO NOTHING
        has_insert_or_ignore = False
        if re.search(r"INSERT\s+OR\s+IGNORE\s+INTO", s, flags=re.IGNORECASE):
            has_insert_or_ignore = True
            s = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", s, flags=re.IGNORECASE)
            s = s.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING;"

        # Translate ? parameter placeholders to %s
        s = s.replace("?", "%s")

        # Determine if we should append RETURNING id to capture lastrowid
        upper_s = s.upper()
        needs_returning = (
            upper_s.startswith("INSERT INTO")
            and not has_insert_or_ignore
            and "ON CONFLICT" not in upper_s
            and "RETURNING " not in upper_s
        )
        if needs_returning:
            s = s.rstrip().rstrip(";") + " RETURNING id;"

        return s, needs_returning

    def execute(self, sql: str, params=None):
        pg_sql, needs_returning = self._translate_sql(sql)
        if pg_sql is None:
            return self
        self.raw_cur.execute(pg_sql, params or ())
        if needs_returning:
            row = self.raw_cur.fetchone()
            if row and "id" in row:
                self.lastrowid = row["id"]
        return self

    def fetchone(self):
        row = self.raw_cur.fetchone()
        return PgRow(row) if row is not None else None

    def fetchall(self):
        rows = self.raw_cur.fetchall()
        return [PgRow(r) for r in rows]


class PgConnectionWrapper:
    def __init__(self, raw_conn):
        self.raw_conn = raw_conn

    def cursor(self):
        return PgCursorWrapper(
            self.raw_conn,
            self.raw_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor),
        )

    def execute(self, sql: str, params=None):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self.raw_conn.commit()

    def rollback(self):
        self.raw_conn.rollback()

    def close(self):
        self.raw_conn.close()

UZBEKISTAN_REGIONS = [
    {"id": "tashkent", "name": "Toshkent", "lat": 41.2995, "lon": 69.2401},
    {"id": "samarkand", "name": "Samarqand", "lat": 39.6542, "lon": 66.9597},
    {"id": "fergana", "name": "Farg'ona", "lat": 40.3842, "lon": 71.7843},
    {"id": "andijan", "name": "Andijon", "lat": 40.7821, "lon": 72.3442},
    {"id": "namangan", "name": "Namangan", "lat": 40.9983, "lon": 71.6726},
    {"id": "bukhara", "name": "Buxoro", "lat": 39.7747, "lon": 64.4286},
    {"id": "qarshi", "name": "Qarshi (Qashqadaryo)", "lat": 38.8606, "lon": 65.7891},
    {"id": "navoiy", "name": "Navoiy", "lat": 40.0844, "lon": 65.3792},
    {"id": "urganch", "name": "Urganch (Xorazm)", "lat": 41.5500, "lon": 60.6333},
    {"id": "termiz", "name": "Termiz (Surxondaryo)", "lat": 37.2242, "lon": 67.2783},
    {"id": "jizzakh", "name": "Jizzax", "lat": 40.1158, "lon": 67.8422},
    {"id": "guliston", "name": "Guliston (Sirdaryo)", "lat": 40.4897, "lon": 68.7842},
    {"id": "nukus", "name": "Nukus (Qoraqalpog'iston)", "lat": 42.4619, "lon": 59.6166},
]


_DB_READY = False
_IN_INIT_DB = False


def _raw_connect():
    pg_url = (
        os.environ.get("POSTGRES_URL_NON_POOLING")
        or os.environ.get("POSTGRES_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("SUPABASE_DB_URL")
    )
    if pg_url and psycopg2 is not None:
        raw_conn = psycopg2.connect(clean_pg_url(pg_url))
        return PgConnectionWrapper(raw_conn)

    conn = sqlite3.connect(DB_PATH, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def get_connection():
    global _DB_READY, _IN_INIT_DB
    pg_url = (
        os.environ.get("POSTGRES_URL_NON_POOLING")
        or os.environ.get("POSTGRES_URL")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("SUPABASE_DB_URL")
    )
    need_init = not _DB_READY or (not pg_url and not os.path.exists(DB_PATH))
    if need_init and not _IN_INIT_DB:
        init_db()
    return _raw_connect()


def calculate_concrete_volume_m3(
    category: str,
    inner_bottom_cm: float = 0,
    inner_side_cm: float = 0,
    inner_top_cm: float = 0,
    wall_thickness_cm: float = 0,
    length_cm: float = 0,
    outer_diameter_cm: float = 0,
    inner_diameter_cm: float = 0,
    height_cm: float = 60.0,
) -> float:
    """
    Calculates exact concrete volume in m3 based on product geometry.
    """
    if category == "kolodets":
        r_out = (outer_diameter_cm / 2.0) / 100.0
        r_in = (inner_diameter_cm / 2.0) / 100.0
        h = height_cm / 100.0
        vol = math.pi * (r_out ** 2 - r_in ** 2) * h
        return round(max(vol, 0.01), 4)
    else:
        # Ariq (trapezoidal U-channel):
        # Inner vertical depth derived from side slope or direct height
        half_diff = max((inner_top_cm - inner_bottom_cm) / 2.0, 0.0)
        if inner_side_cm > half_diff:
            inner_depth_cm = math.sqrt(inner_side_cm ** 2 - half_diff ** 2)
        else:
            inner_depth_cm = inner_side_cm

        inner_area_cm2 = ((inner_bottom_cm + inner_top_cm) / 2.0) * inner_depth_cm
        outer_bottom_cm = inner_bottom_cm + 2.0 * wall_thickness_cm
        outer_top_cm = inner_top_cm + 2.0 * wall_thickness_cm
        outer_depth_cm = inner_depth_cm + wall_thickness_cm
        outer_area_cm2 = ((outer_bottom_cm + outer_top_cm) / 2.0) * outer_depth_cm

        concrete_area_cm2 = max(outer_area_cm2 - inner_area_cm2, 10.0)
        vol_cm3 = concrete_area_cm2 * length_cm
        vol_m3 = vol_cm3 / 1_000_000.0
        return round(max(vol_m3, 0.01), 4)


def init_db():
    global _DB_READY, _IN_INIT_DB
    _IN_INIT_DB = True
    try:
        _init_db_tables()
        _DB_READY = True
    finally:
        _IN_INIT_DB = False


def _init_db_tables():
    conn = _raw_connect()
    cur = conn.cursor()

    # 1. Settings
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        company_name TEXT NOT NULL DEFAULT 'Beton Ariq & Kolodets Zavodi',
        region_id TEXT NOT NULL DEFAULT 'fergana',
        region_name TEXT NOT NULL DEFAULT 'Farg''ona',
        latitude REAL NOT NULL DEFAULT 40.3842,
        longitude REAL NOT NULL DEFAULT 71.7843,
        workshop_width_m REAL NOT NULL DEFAULT 7.0,
        workshop_width_front_m REAL NOT NULL DEFAULT 7.0,
        workshop_width_back_m REAL NOT NULL DEFAULT 8.2,
        workshop_length_m REAL NOT NULL DEFAULT 16.5,
        rail_gauge_m REAL NOT NULL DEFAULT 6.0,
        stack_Alert_threshold INTEGER NOT NULL DEFAULT 2,
        updated_at TEXT
    );
    """)

    # Ensure new trapezoidal dimension columns exist on existing settings table
    for col_name, col_def in [
        ("workshop_width_front_m", "REAL NOT NULL DEFAULT 7.0"),
        ("workshop_width_back_m", "REAL NOT NULL DEFAULT 8.2"),
        ("rail_gauge_m", "REAL NOT NULL DEFAULT 6.0"),
    ]:
        try:
            cur.execute(f"ALTER TABLE settings ADD COLUMN {col_name} {col_def};")
            conn.commit()
        except Exception:
            if hasattr(conn, "rollback"):
                conn.rollback()

    # 1b. Workshop Structural & Equipment Elements (Tal relslari, Talning o'zi, Meshalka, Vibrator, Taglik Stoykalar)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS workshop_elements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        element_type TEXT NOT NULL, -- 'tal_rails' | 'tal_crane' | 'meshalka' | 'vibrator' | 'stoyka'
        name TEXT NOT NULL,
        pos_x REAL NOT NULL DEFAULT 0.0,      -- Markazdan X (metrda, -4.1 .. +4.1)
        pos_z REAL NOT NULL DEFAULT 8.25,     -- Eshikdan masofa Z (metrda, 0.0 .. 16.5)
        pos_y REAL NOT NULL DEFAULT 0.0,      -- Yerdan balandligi Y (metrda)
        rotation_deg REAL NOT NULL DEFAULT 0.0,
        length_m REAL NOT NULL DEFAULT 1.0,   -- Uzunligi (Z yoki X bo'yicha, metrda)
        width_m REAL NOT NULL DEFAULT 1.0,    -- Kengligi yoki juftlik orasi (metrda)
        height_m REAL NOT NULL DEFAULT 0.15,  -- Balandligi (metrda)
        extra_json TEXT DEFAULT '{}',
        notes TEXT DEFAULT ''
    );
    """)

    # 2. Product Types (22-lik, 30-lik, 40-lik, 50-lik ariqlar va 104/118 kolodets)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        category TEXT NOT NULL, -- 'ariq' | 'kolodets'
        casting_mode TEXT NOT NULL DEFAULT 'stationary', -- 'stationary' (qolipda qotadi) | 'cyclic' (kuniga 20+ marta quyib-yechiladi)
        inner_bottom_cm REAL DEFAULT 0,
        inner_side_cm REAL DEFAULT 0,
        inner_top_cm REAL DEFAULT 0,
        wall_thickness_cm REAL DEFAULT 0,
        length_cm REAL DEFAULT 0,
        outer_diameter_cm REAL DEFAULT 0,
        inner_diameter_cm REAL DEFAULT 0,
        max_height_cm REAL DEFAULT 0,
        default_height_cm REAL DEFAULT 0,
        concrete_volume_m3 REAL NOT NULL DEFAULT 0.05,
        cement_norm_kg REAL NOT NULL DEFAULT 18.0,
        gravel_norm_kg REAL NOT NULL DEFAULT 85.0,
        wire_norm_kg REAL NOT NULL DEFAULT 1.2,
        casting_labor_cost REAL NOT NULL DEFAULT 15000,
        selling_price REAL NOT NULL DEFAULT 85000,
        stock_qty INTEGER NOT NULL DEFAULT 0,
        color_hex TEXT DEFAULT '#3b82f6',
        description TEXT
    );
    """)

    # 3. Molds (Har bir qolip raqamlangan + 3D joylashuv + ustma-ust qavat stack_tier)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS molds (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mold_number TEXT NOT NULL UNIQUE,
        product_type_id INTEGER NOT NULL,
        zone TEXT NOT NULL DEFAULT 'Asosiy Sex',
        pos_x REAL NOT NULL DEFAULT 0.0,
        pos_z REAL NOT NULL DEFAULT 0.0,
        stack_tier INTEGER NOT NULL DEFAULT 1, -- 1 = yerda, 2 = 1-qolip ustida, 3 = 2-qolip ustida (ustma-ust!)
        rotation_deg REAL NOT NULL DEFAULT 0.0,
        status TEXT NOT NULL DEFAULT 'empty', -- 'empty' | 'poured' | 'ready_demold' | 'maintenance' | 'cyclic_active'
        total_casts INTEGER NOT NULL DEFAULT 0,
        consecutive_corner_defects INTEGER NOT NULL DEFAULT 0,
        total_defects INTEGER NOT NULL DEFAULT 0,
        last_cast_date TEXT,
        last_quality_status TEXT DEFAULT 'clean', -- 'clean' | 'corner_stuck' | 'cracked'
        last_defect_note TEXT DEFAULT '',
        today_cyclic_count INTEGER NOT NULL DEFAULT 0,
        notes TEXT DEFAULT '',
        FOREIGN KEY (product_type_id) REFERENCES product_types(id)
    );
    """)

    # 4. Daily Work Logs & Weather
    cur.execute("""
    CREATE TABLE IF NOT EXISTS daily_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_date TEXT NOT NULL UNIQUE,
        is_working_day INTEGER NOT NULL DEFAULT 1,
        region_name TEXT,
        weather_temp_max REAL,
        weather_temp_min REAL,
        weather_temp_avg REAL,
        weather_humidity REAL,
        weather_wind_kmh REAL,
        weather_condition TEXT,
        curing_advice TEXT,
        demolded_count INTEGER NOT NULL DEFAULT 0,
        cast_count INTEGER NOT NULL DEFAULT 0,
        cyclic_cast_count INTEGER NOT NULL DEFAULT 0,
        defect_count INTEGER NOT NULL DEFAULT 0,
        labor_cost_total REAL NOT NULL DEFAULT 0,
        notes TEXT DEFAULT '',
        created_at TEXT
    );
    """)

    # 5. Production Events (Har bir quyish va qolipdan chiqarish amaliyoti)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS production_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        work_date TEXT NOT NULL,
        event_type TEXT NOT NULL, -- 'demold' | 'cast' | 'cyclic_cast'
        mold_id INTEGER NOT NULL,
        product_type_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        custom_height_cm REAL DEFAULT 0,
        quality_status TEXT NOT NULL DEFAULT 'clean', -- 'clean' | 'corner_stuck' | 'cracked'
        defect_location TEXT DEFAULT '',
        labor_cost_accrued REAL NOT NULL DEFAULT 0,
        cement_used_kg REAL NOT NULL DEFAULT 0,
        gravel_used_kg REAL NOT NULL DEFAULT 0,
        wire_used_kg REAL NOT NULL DEFAULT 0,
        notes TEXT DEFAULT '',
        created_at TEXT,
        FOREIGN KEY (mold_id) REFERENCES molds(id) ON DELETE CASCADE,
        FOREIGN KEY (product_type_id) REFERENCES product_types(id)
    );
    """)

    # 6. Mold Repairs (Ta'mirlash tarixi)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS mold_repairs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mold_id INTEGER NOT NULL,
        repair_date TEXT NOT NULL,
        issue_description TEXT NOT NULL,
        repair_action TEXT NOT NULL,
        repair_cost REAL NOT NULL DEFAULT 0,
        performed_by TEXT DEFAULT 'Usta',
        created_at TEXT,
        FOREIGN KEY (mold_id) REFERENCES molds(id) ON DELETE CASCADE
    );
    """)

    # 7. Orders (Buyurtmalar)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT NOT NULL UNIQUE,
        customer_name TEXT NOT NULL,
        customer_phone TEXT DEFAULT '',
        order_date TEXT NOT NULL,
        due_date TEXT,
        product_type_id INTEGER NOT NULL,
        ordered_qty INTEGER NOT NULL,
        delivered_qty INTEGER NOT NULL DEFAULT 0,
        custom_height_cm REAL DEFAULT 0,
        unit_price REAL NOT NULL,
        total_amount REAL NOT NULL,
        advance_paid REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending', -- 'pending' | 'partial' | 'completed'
        notes TEXT DEFAULT '',
        FOREIGN KEY (product_type_id) REFERENCES product_types(id)
    );
    """)

    # 8. Sales (Buyurtma asosida sotilgan + Shoshilinch olib ketilgan)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_date TEXT NOT NULL,
        sale_type TEXT NOT NULL, -- 'order_fulfillment' | 'urgent_pickup'
        order_id INTEGER,
        customer_name TEXT NOT NULL,
        customer_phone TEXT DEFAULT '',
        product_type_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        total_amount REAL NOT NULL,
        paid_amount REAL NOT NULL,
        payment_method TEXT DEFAULT 'Naqd',
        notes TEXT DEFAULT '',
        created_at TEXT,
        FOREIGN KEY (order_id) REFERENCES orders(id),
        FOREIGN KEY (product_type_id) REFERENCES product_types(id)
    );
    """)

    # 9. Missing / Unfulfilled Size Requests (Mavjud bo'lmagan o'lchamlar talabi)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS missing_size_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_date TEXT NOT NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT DEFAULT '',
        requested_category TEXT NOT NULL DEFAULT 'ariq', -- 'ariq' | 'kolodets' | 'boshqa'
        requested_size_name TEXT NOT NULL,
        dimensions_details TEXT DEFAULT '',
        requested_qty INTEGER NOT NULL DEFAULT 1,
        estimated_unit_price REAL NOT NULL DEFAULT 0,
        notes TEXT DEFAULT '',
        created_at TEXT
    );
    """)

    # 10. Raw Material Batches (Sement, Shag'al, Sim - qachon keldi, qachon tugadi)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS raw_material_batches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        material_type TEXT NOT NULL, -- 'cement' | 'gravel' | 'wire'
        batch_code TEXT NOT NULL,
        material_name TEXT NOT NULL,
        supplier TEXT DEFAULT '',
        arrived_date TEXT NOT NULL,
        depleted_date TEXT, -- NULL if still active
        status TEXT NOT NULL DEFAULT 'active', -- 'active' | 'depleted'
        initial_quantity REAL NOT NULL,
        remaining_quantity REAL NOT NULL,
        unit TEXT NOT NULL DEFAULT 'kg',
        unit_price REAL NOT NULL,
        total_cost REAL NOT NULL,
        notes TEXT DEFAULT ''
    );
    """)

    conn.commit()
    seed_initial_data(conn)
    sync_real_media_layout(conn)
    conn.close()


def get_real_media_molds_seed():
    """
    Exact 38-mold workshop layout mapped 1:1 from the 20 high-res photos & 2 videos in media/:
    - 1-Qator (Z = -3.8m, Meshalka va Omborxona oldi): 4 ta 30-lik ariq (#01-#04) + 4-prujinali Vibrostol Plita qolipi (#37) + Kolodets siklli qolipi (#38)
    - 2-Qator (Z = -1.1m, 1-tokchadan O'ralgan gilamgacha): O'ngda 4 ta qolip (#12-#15, #14 ichida svarka '14' raqami va yon borti ochilgan) + Chapda 7 ta 22-lik ariq (#05-#11, #05 ichida svarka '5' raqami, beton taglik toshlar ustida)
    - 3-Qator (Z = +1.6m, 2-tokchadan Temir kirish eshigigacha): 9 ta 1-qavat 30-lik ariq (#16-#24) + ularning ustida sement qoplar ustiga qo'yilgan 2 ta 2-qavat X-karkasli 40-lik qolip (#25 [2-Q] va #26 [2-Q])
    - 4-Qator (Z = +4.2m, Kran-balka / Tal ko'targich va Shlakoblok devor oldi): O'ngda Ikki A-ramali Kran-balka va Tal ilgagi ostidagi 4 ta 1-qavat 50-lik (#27-#30) + 2 ta 2-qavat 50-lik (#35 [2-Q], #36 [2-Q]), Chapda ustiga SHAFFOF/YASIN sement qoplari yopilgan 4 ta 30-lik (#31-#34)
    """
    return [
        # --- 1-QATOR: MESHALKA VA SEMENT OMBORXONASI ESHIGI OLDI (110253, 110530, 110821-rasmlar) ---
        ("#01 (A30)", "A30", "1-Qator (Omborxona va Meshalka oldi)", 1.35, -3.8, 1, 0, "poured", 92, 0, 2, "clean", "Meshalka va omborxona eshigi oldida (110253-rasm), beton quyilgan"),
        ("#02 (A30)", "A30", "1-Qator (Omborxona va Meshalka oldi)", 2.20, -3.8, 1, 0, "poured", 89, 0, 1, "clean", "Omborxona eshigi ro'parasida (110253-rasm), beton quyilgan"),
        ("#03 (A30)", "A30", "1-Qator (Omborxona va Meshalka oldi)", 3.05, -3.8, 1, 0, "ready_demold", 95, 0, 2, "clean", "Yon temir bortlari bo'shatib ochilgan — yechishga tayyor (110821-rasm markazi)"),
        ("#04 (A30)", "A30", "1-Qator (Omborxona va Meshalka oldi)", 3.90, -3.8, 1, 0, "ready_demold", 87, 0, 1, "clean", "Jigarang tunuka panel yonida, yon bortlari bo'shatilgan (110821-rasm o'ngda)"),

        # --- 2-QATOR CHAP (SHARQIY): 7 TA 22-LIK ARIQLAR GURUHI (110253, 110520, 110530, 110722, 111136, 111150-rasmlar) ---
        ("#05 (A22)", "A22", "2-Qator (22-liklar guruhi)", -0.55, -1.1, 1, 0, "poured", 76, 1, 4, "corner_stuck", "SVARKA RAQAMI '5' (110722-rasm): Betonga '5' muhri tushgan, burchagida beton qoldig'i bor, yonida sariq qopqoqli idish"),
        ("#06 (A22)", "A22", "2-Qator (22-liklar guruhi)",  0.18, -1.1, 1, 0, "poured", 74, 0, 1, "clean", "Ustida siniq beton plita parchasi yotibdi (110253 va 111150-rasm), sim quloqchali"),
        ("#07 (A22)", "A22", "2-Qator (22-liklar guruhi)",  0.91, -1.1, 1, 0, "poured", 71, 0, 2, "clean", "Tagida beton taglik tosh (111136-rasm), tepasida U-simon sim quloqchalar"),
        ("#08 (A22)", "A22", "2-Qator (22-liklar guruhi)",  1.64, -1.1, 1, 0, "poured", 69, 0, 1, "clean", "22-lik qolip (111150-rasm), rezbali tortqichi mahkamlangan"),
        ("#09 (A22)", "A22", "2-Qator (22-liklar guruhi)",  2.37, -1.1, 1, 0, "ready_demold", 73, 0, 2, "clean", "Betoni qotgan, yechishga tayyor (111150-rasm)"),
        ("#10 (A22)", "A22", "2-Qator (22-liklar guruhi)",  3.10, -1.1, 1, 0, "ready_demold", 68, 0, 1, "clean", "Betoni qotgan, yechishga tayyor (110520-rasm)"),
        ("#11 (A22)", "A22", "2-Qator (22-liklar guruhi)",  3.83, -1.1, 1, 0, "ready_demold", 66, 0, 1, "clean", "Sharqiy paxsa devor va o'ralgan gilam yonida (110850-rasm)"),

        # --- 2-QATOR O'NG (G'ARBIY): 1-TOKCHA VA VIBROSTOL RO'PARASI (110407, 110648, 110654, 110707, 110758-rasmlar) ---
        ("#12 (A30)", "A30", "2-Qator (1-Tokcha tomon)", -4.45, -1.1, 1, 0, "poured", 88, 0, 2, "clean", "Paxsa devor va temir rels yonida, ustida '2' shaklidagi beton izi bor (110648-rasm o'ngda)"),
        ("#13 (A30)", "A30", "2-Qator (1-Tokcha tomon)", -3.60, -1.1, 1, 0, "poured", 85, 0, 1, "clean", "110648-rasm chapda: 3 ta armatura rezbali dastagi mahkam tortilgan"),
        ("#14 (A22)", "A22", "2-Qator (1-Tokcha tomon)", -2.80, -1.1, 1, 0, "maintenance", 82, 2, 7, "corner_stuck", "SVARKA RAQAMI '14' (110758-rasm): Betonga teskari '14' muhri tushgan! Chap yon borti yechib qo'yilgan (110654 va 110707-rasm) — remont/tozalashda"),
        ("#15 (A30)", "A30", "2-Qator (1-Tokcha tomon)", -1.98, -1.1, 1, 0, "poured", 79, 0, 2, "clean", "110654 va 110707-rasm chap chetida, beton quyilgan"),

        # --- 3-QATOR: MARKAZIY QATOR (2-TOKCHADAN TEMIR KIRISH ESHIGIGACHA + 2 TA 2-QAVAT USTMA-UST 40-LIK, 110407, 110507, 110520, 110850-rasmlar) ---
        ("#16 (A30)", "A30", "3-Qator (Markaz - 2-Tokcha)", -4.45, 1.55, 1, 0, "poured", 83, 0, 2, "clean", "2-tokcha va oq-qora ustun ro'parasida (110407 va 110654-rasm)"),
        ("#17 (A30)", "A30", "3-Qator (Markaz - 2-Tokcha)", -3.60, 1.55, 1, 0, "poured", 80, 0, 1, "clean", "110654-rasm orqa qator o'rtada, ichki X-karkasi ko'rinadi"),
        ("#18 (A30)", "A30", "3-Qator (Markaz)", -2.75, 1.55, 1, 0, "poured", 77, 0, 2, "clean", "110654-rasm orqa qator chapda, beton quyilgan"),
        ("#19 (A30)", "A30", "3-Qator (Markaz - 1-Qavat)", -1.90, 1.55, 1, 0, "poured", 84, 0, 2, "clean", "1-qavat tayanch: Ustiga SHAFFOF SEMENT qoplari to'shalib, ustiga #25 (2-qavat) qo'yilgan"),
        ("#20 (A30)", "A30", "3-Qator (Markaz - 1-Qavat)", -1.05, 1.55, 1, 0, "poured", 81, 0, 1, "clean", "1-qavat tayanch: Ustiga YASIN SEMENT qoplari to'shalib, ustiga #25 (2-qavat) qo'yilgan"),
        ("#21 (A30)", "A30", "3-Qator (Markaz)", -0.20, 1.55, 1, 0, "poured", 75, 0, 2, "clean", "Markaziy qator, ikki 2-qavat qolip orasida (110850-rasm)"),
        ("#22 (A30)", "A30", "3-Qator (Kirish eshigi - 1-Qavat)", 0.65, 1.55, 1, 0, "poured", 78, 0, 1, "clean", "1-qavat tayanch: Ustiga sement qoplari to'shalib, ustiga #26 (2-qavat) qo'yilgan (110507-rasm)"),
        ("#23 (A30)", "A30", "3-Qator (Kirish eshigi - 1-Qavat)", 1.50, 1.55, 1, 0, "poured", 76, 0, 2, "clean", "1-qavat tayanch: Temir kirish eshigi ro'parasida, ustida #26 (2-qavat) turibdi"),
        ("#24 (A30)", "A30", "3-Qator (Kirish eshigi oldi)", 2.35, 1.55, 1, 0, "ready_demold", 72, 0, 1, "clean", "Temir kirish eshigi va o'ralgan gilam oldida (110520-rasm)"),

        # 3-QATOR 2-QAVAT USTMA-UST QOLIPLAR (110507, 110520, 110850-rasmlar va VID_110157 0:17 da aniq ko'ringan!)
        ("#25 (A40)", "A40", "3-Qator (2-Qavat Ustma-ust)", -1.48, 1.55, 2, 0, "poured", 64, 0, 2, "clean", "2-QAVAT (Ustma-ust): #19 va #20 ustida sement qoplar ustiga qo'yilgan X-karkasli 40-lik qolip (110507 va 110850-rasm)"),
        ("#26 (A40)", "A40", "3-Qator (2-Qavat Ustma-ust)",  1.08, 1.55, 2, 0, "poured", 61, 0, 1, "clean", "2-QAVAT (Ustma-ust): Temir kirish eshigi oldida #22 va #23 ustida turgan 40-lik qolip (110507 va 110520-rasm)"),

        # --- 4-QATOR O'NG: A-RAMALI KRAN-BALKA (TAL KO'TARGICH) OSTIDAGI 50-LIK OG'IR QOLIPLAR (110431, 110455, 110707, 110913-rasmlar) ---
        ("#27 (A50)", "A50", "4-Qator (Kran-balka osti - 1-Qavat)", -4.35, 4.15, 1, 0, "ready_demold", 58, 0, 2, "clean", "G'arbiy A-rama kran oyog'i ostida: tayyor 50-lik beton ariq (ustida #35 qolip turibdi, 110431-rasm)"),
        ("#28 (A50)", "A50", "4-Qator (Kran-balka osti - 1-Qavat)", -3.15, 4.15, 1, 0, "poured", 55, 0, 1, "clean", "Kran-balka ostida 50-lik katta qolip (ustida #36 turibdi, 110431 va 110707-rasm)"),
        ("#29 (A50)", "A50", "4-Qator (Kran-balka osti - 1-Qavat)", -1.95, 4.15, 1, 0, "poured", 53, 0, 2, "clean", "Kran-balka ostida, ustida po'lat tros yotibdi (110455-rasm o'rtada)"),
        ("#30 (A50)", "A50", "4-Qator (Kran-balka osti - Tal ilgagi)", -0.75, 4.15, 1, 0, "poured", 57, 1, 3, "corner_stuck", "Kran-balka ostida: Qora traversa va Tal ko'targich ilgagi ulangan 50-lik qolip (110455 va 110507-rasm)"),

        # 4-QATOR CHAP: USTIGA SEMENT QOPLARI YOPILGAN QATOR (110455, 110507, 110850-rasmlar)
        ("#31 (A30)", "A30", "4-Qator (Sement qoplar ostida)", 0.35, 4.15, 1, 0, "poured", 74, 0, 1, "clean", "Namlikni saqlash uchun ustiga SHAFFOF va YASIN SEMENT qoplari to'liq yopilgan (110507-rasm markazi)"),
        ("#32 (A30)", "A30", "4-Qator (Sement qoplar ostida)", 1.20, 4.15, 1, 0, "poured", 71, 0, 2, "clean", "Ustiga SHAFFOF va YASIN SEMENT qoplari yopilgan (110507-rasm markazi)"),
        ("#33 (A30)", "A30", "4-Qator (Sement qoplar ostida)", 2.05, 4.15, 1, 0, "poured", 69, 0, 1, "clean", "Tunuka list ro'parasida, ustiga sement qoplari yopilgan (110507-rasm)"),
        ("#34 (A30)", "A30", "4-Qator (Sement qoplar ostida)", 2.90, 4.15, 1, 0, "ready_demold", 67, 0, 1, "clean", "Sharqiy shlakoblok devor va tunuka list yonida, sement qoplar ostida"),

        # 4-QATOR 2-QAVAT: KRAN-BALKA OSTIDAGI 2-QAVAT 50-LIKLAR (110431, 110455, 110707, 110913-rasmlar)
        ("#35 (A50)", "A50", "4-Qator (Kran osti - 2-Qavat)", -4.35, 4.15, 2, 0, "empty", 52, 0, 1, "clean", "2-QAVAT (Kran-balka ostida): Yog'och brusoklar ustiga qo'yilgan bo'sh 50-lik temir qolip (110431-rasm old planda)"),
        ("#36 (A50)", "A50", "4-Qator (Kran osti - 2-Qavat)", -3.15, 4.15, 2, 0, "ready_demold", 50, 0, 1, "clean", "2-QAVAT (Kran-balka ostida): Tal bilan ko'tarib qo'yilgan 50-lik ariq (110707 va 110913-rasm orqa fon)"),

        # --- MAXSUS QOLIPLAR: 4-PRUJINALI YER OSTI VIBROSTOL PLITA QOLIPI (111247-RASM) VA SIKLLI KOLODETS QOLIPI ---
        ("#37 (PLITA)", "PL80", "Vibrostol Chuquri (Meshalka yonida)", -2.05, -3.75, 1, 0, "poured", 145, 0, 2, "clean", "4 ta katta prujinali yer osti Vibrostol ustidagi tekis Plita qolipi (110253, 110913 va 111247-rasmlar)"),
        ("#38 (KOLODETS)", "K104", "Kolodets Maydoni (Omborxona yonida)", 4.15, -5.75, 1, 0, "cyclic_active", 412, 0, 6, "clean", "Bitta siklli Kolodets qolipi (Ø118/104sm, max 60sm): kuniga 20+ marta quyib darhol yechiladi"),
    ]


def sync_real_media_layout(conn: sqlite3.Connection):
    """
    Upgrades settings to the exact trapezoidal mathematical yard dimensions specified by the user:
      - Eshikdan oxiriga qadar (shlakoblokli devor): 16.5 metr (Z: 0.0m -> 16.5m)
      - Yon devorlar orasi: Eshik tomon 7.0 metr, Oxiri (shlakoblok devor) 8.2 metr
      - Ikki yondagi Tal relslari orasi: 6.0 metr (X = -3.0m va X = +3.0m)
    And seeds the initial 6.0m Tal rails in workshop_elements if none exist yet.
    """
    cur = conn.cursor()
    cur.execute("""
        UPDATE settings
        SET workshop_length_m = 16.5,
            workshop_width_m = 7.0,
            workshop_width_front_m = 7.0,
            workshop_width_back_m = 8.2,
            rail_gauge_m = 6.0
        WHERE id = 1
    """)
    conn.commit()

    cur.execute("SELECT id FROM product_types WHERE code = 'PL80'")
    if not cur.fetchone():
        vol = calculate_concrete_volume_m3("ariq", 60.0, 8.0, 60.0, 4.0, 80.0, 0, 0, 0)
        cur.execute("""
        INSERT INTO product_types (
            code, name, category, casting_mode,
            inner_bottom_cm, inner_side_cm, inner_top_cm, wall_thickness_cm, length_cm,
            outer_diameter_cm, inner_diameter_cm, max_height_cm, default_height_cm,
            concrete_volume_m3, cement_norm_kg, gravel_norm_kg, wire_norm_kg,
            casting_labor_cost, selling_price, stock_qty, color_hex, description
        ) VALUES ('PL80', 'Vibrostol Beton Plita (80x60x8sm)', 'ariq', 'stationary',
                  60.0, 8.0, 60.0, 4.0, 80.0, 0, 0, 0, 0, ?, 11.0, 48.0, 0.8,
                  10000, 55000, 18, '#14b8a6',
                  'Vibrostol ustida quyiladigan tekis beton plita.')
        """, (vol,))
        conn.commit()

    # If molds still have old negative Z coordinates (< 0), clear the old guessed layout
    # so the universal mathematical 16.5m x (7.0m -> 8.2m) constructor starts clean!
    cur.execute("SELECT COUNT(*) as cnt FROM molds WHERE pos_z < 0")
    if cur.fetchone()["cnt"] > 0:
        cur.execute("PRAGMA foreign_keys = OFF;")
        cur.execute("DELETE FROM molds;")
        cur.execute("PRAGMA foreign_keys = ON;")
        conn.commit()

    # Seed base 6.0m Tal rails if workshop_elements is completely empty
    cur.execute("SELECT COUNT(*) as cnt FROM workshop_elements")
    if cur.fetchone()["cnt"] == 0:
        cur.execute("""
        INSERT INTO workshop_elements (
            element_type, name, pos_x, pos_z, pos_y, rotation_deg,
            length_m, width_m, height_m, extra_json, notes
        ) VALUES (
            'tal_rails',
            'Ikki yondagi Tal relslari (Orasi 6.0m)',
            0.0, 8.25, 0.0, 0.0,
            16.5, 6.0, 0.10,
            '{"z_start": 0.0, "z_end": 16.5, "gauge_m": 6.0}',
            'Eshikdan (0m) oxirgi shlakoblok devorgacha (16.5m) cho''zilgan 6 metr oraliqdagi ikki yon rels (X = -3.0m va X = +3.0m)'
        )
        """)
        conn.commit()


def seed_initial_data(conn: sqlite3.Connection):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM settings")
    if cur.fetchone()["cnt"] == 0:
        cur.execute("""
        INSERT INTO settings (id, company_name, region_id, region_name, latitude, longitude, workshop_width_m, workshop_length_m, updated_at)
        VALUES (1, 'Beton Ariq & Kolodets Zavodi', 'tashkent', 'Toshkent', 41.2995, 69.2401, 13.0, 16.0, ?)
        """, (datetime.now().isoformat(),))

    cur.execute("SELECT COUNT(*) as cnt FROM product_types")
    if cur.fetchone()["cnt"] > 0:
        conn.commit()
        return

    # 1. Seed the exact product types described by the user:
    # 22-lik, 30-lik, 40-lik, 50-lik ariqlar + 104/118-lik kolodets (max 60sm, devori 7sm)
    products = [
        {
            "code": "A22",
            "name": "22-lik Beton Ariq (Lotok)",
            "category": "ariq",
            "casting_mode": "stationary",
            "inner_bottom_cm": 11.0,
            "inner_side_cm": 16.0,
            "inner_top_cm": 22.0,
            "wall_thickness_cm": 4.5,
            "length_cm": 220.0,
            "outer_diameter_cm": 0,
            "inner_diameter_cm": 0,
            "max_height_cm": 0,
            "default_height_cm": 0,
            "cement_norm_kg": 14.0,
            "gravel_norm_kg": 60.0,
            "wire_norm_kg": 0.9,
            "casting_labor_cost": 12000,
            "selling_price": 65000,
            "stock_qty": 34,
            "color_hex": "#38bdf8",
            "description": "Kichik suv yo'llari va hovli ariqlari uchun 22-lik beton lotok."
        },
        {
            "code": "A30",
            "name": "30-lik Beton Ariq (Lotok)",
            "category": "ariq",
            "casting_mode": "stationary",
            "inner_bottom_cm": 15.0,
            "inner_side_cm": 22.0,
            "inner_top_cm": 30.0,
            "wall_thickness_cm": 5.5,
            "length_cm": 220.0,
            "outer_diameter_cm": 0,
            "inner_diameter_cm": 0,
            "max_height_cm": 0,
            "default_height_cm": 0,
            "cement_norm_kg": 20.0,
            "gravel_norm_kg": 88.0,
            "wire_norm_kg": 1.4,
            "casting_labor_cost": 16000,
            "selling_price": 95000,
            "stock_qty": 48,
            "color_hex": "#3b82f6",
            "description": "Ichki pastki qismi (suv oqadigan joyi) 15sm, yoni 22sm, og'zi 29-30sm bo'lgan xaridorgir 30-lik ariq."
        },
        {
            "code": "A40",
            "name": "40-lik Beton Ariq (Lotok)",
            "category": "ariq",
            "casting_mode": "stationary",
            "inner_bottom_cm": 20.0,
            "inner_side_cm": 30.0,
            "inner_top_cm": 40.0,
            "wall_thickness_cm": 6.5,
            "length_cm": 220.0,
            "outer_diameter_cm": 0,
            "inner_diameter_cm": 0,
            "max_height_cm": 0,
            "default_height_cm": 0,
            "cement_norm_kg": 28.0,
            "gravel_norm_kg": 125.0,
            "wire_norm_kg": 2.1,
            "casting_labor_cost": 22000,
            "selling_price": 135000,
            "stock_qty": 22,
            "color_hex": "#6366f1",
            "description": "Ko'cha va o'rta magistral suv yo'llari uchun 40-lik mustahkam ariq."
        },
        {
            "code": "A50",
            "name": "50-lik Beton Ariq (Lotok)",
            "category": "ariq",
            "casting_mode": "stationary",
            "inner_bottom_cm": 25.0,
            "inner_side_cm": 38.0,
            "inner_top_cm": 50.0,
            "wall_thickness_cm": 7.5,
            "length_cm": 220.0,
            "outer_diameter_cm": 0,
            "inner_diameter_cm": 0,
            "max_height_cm": 0,
            "default_height_cm": 0,
            "cement_norm_kg": 38.0,
            "gravel_norm_kg": 170.0,
            "wire_norm_kg": 2.8,
            "casting_labor_cost": 30000,
            "selling_price": 185000,
            "stock_qty": 14,
            "color_hex": "#8b5cf6",
            "description": "Katta hajmli suv oqimlari uchun 50-lik og'ir beton ariq."
        },
        {
            "code": "K104",
            "name": "Kolodets Xalqasi Ø118/104 (Max 60sm)",
            "category": "kolodets",
            "casting_mode": "cyclic",
            "inner_bottom_cm": 0,
            "inner_side_cm": 0,
            "inner_top_cm": 0,
            "wall_thickness_cm": 7.0,
            "length_cm": 0,
            "outer_diameter_cm": 118.0,
            "inner_diameter_cm": 104.0,
            "max_height_cm": 60.0,
            "default_height_cm": 60.0,
            "cement_norm_kg": 48.0,
            "gravel_norm_kg": 215.0,
            "wire_norm_kg": 3.2,
            "casting_labor_cost": 35000,
            "selling_price": 230000,
            "stock_qty": 29,
            "color_hex": "#f59e0b",
            "description": "Tashqi diametri 118sm, ichki diametri 104sm (qalinligi 7sm), balandligi max 60sm. Bitta qolipda kuniga 20+ marta quyib-yechiladi!"
        },
        {
            "code": "PL80",
            "name": "Vibrostol Beton Plita (80x60x8sm)",
            "category": "ariq",
            "casting_mode": "stationary",
            "inner_bottom_cm": 60.0,
            "inner_side_cm": 8.0,
            "inner_top_cm": 60.0,
            "wall_thickness_cm": 4.0,
            "length_cm": 80.0,
            "outer_diameter_cm": 0,
            "inner_diameter_cm": 0,
            "max_height_cm": 0,
            "default_height_cm": 0,
            "cement_norm_kg": 11.0,
            "gravel_norm_kg": 48.0,
            "wire_norm_kg": 0.8,
            "casting_labor_cost": 10000,
            "selling_price": 55000,
            "stock_qty": 18,
            "color_hex": "#14b8a6",
            "description": "Meshalka yonidagi 4-prujinali yer osti vibrostol ustida quyiladigan tekis beton plita (111247-rasm)."
        }
    ]

    product_ids = {}
    for p in products:
        vol = calculate_concrete_volume_m3(
            p["category"],
            p["inner_bottom_cm"],
            p["inner_side_cm"],
            p["inner_top_cm"],
            p["wall_thickness_cm"],
            p["length_cm"],
            p["outer_diameter_cm"],
            p["inner_diameter_cm"],
            p["default_height_cm"] or 60.0,
        )
        cur.execute("""
        INSERT INTO product_types (
            code, name, category, casting_mode,
            inner_bottom_cm, inner_side_cm, inner_top_cm, wall_thickness_cm, length_cm,
            outer_diameter_cm, inner_diameter_cm, max_height_cm, default_height_cm,
            concrete_volume_m3, cement_norm_kg, gravel_norm_kg, wire_norm_kg,
            casting_labor_cost, selling_price, stock_qty, color_hex, description
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            p["code"], p["name"], p["category"], p["casting_mode"],
            p["inner_bottom_cm"], p["inner_side_cm"], p["inner_top_cm"], p["wall_thickness_cm"], p["length_cm"],
            p["outer_diameter_cm"], p["inner_diameter_cm"], p["max_height_cm"], p["default_height_cm"],
            vol, p["cement_norm_kg"], p["gravel_norm_kg"], p["wire_norm_kg"],
            p["casting_labor_cost"], p["selling_price"], p["stock_qty"], p["color_hex"], p["description"]
        ))
        product_ids[p["code"]] = cur.lastrowid

    # 2. Seed Molds matching ALL 20 PHOTOS & 2 VIDEOS from C:\Users\99890\.gemini\antigravity\scratch\beton-erp\media (38 molds total!)
    # Three.js Right-Handed Coordinate System (when looking from Mixer -Z toward Back Wall +Z):
    #   -Z (Back-North): Omborxona open brick doorway (X=+2.8), Betonomeshalka (X=-0.5, Z=-5.6), 4-Spring Vibrostol Pit (X=-2.1, Z=-3.7)
    #   -X (Right side from Mixer view): Long Paxsa wall with 2 niches (1-tokcha, 2-tokcha), steel floor rail, & West A-Frame Crane leg
    #   +X (Left side from Mixer view): Paxsa wall with brown panel & rolled carpet -> Grey Metal Door -> Shlakoblok wall with tin sheet -> East A-Frame Crane leg
    #   +Z (Far South end): Back Shlakoblok wall with cement bag piles, Small Mud Shed, & Overhead Gantry Crane (Kran-balka / Tal) over 50-lik molds
    molds_seed = get_real_media_molds_seed()

    today_str = datetime.now().strftime("%Y-%m-%d")
    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    two_days_ago_str = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
    five_days_ago_str = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    ten_days_ago_str = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")

    for m in molds_seed:
        mold_num, p_code, zone, px, pz, tier, rot, st, t_casts, c_def, tot_def, qual, note = m
        today_cyc = 18 if p_code == "K104" else 0
        cur.execute("""
        INSERT INTO molds (
            mold_number, product_type_id, zone, pos_x, pos_z, stack_tier, rotation_deg,
            status, total_casts, consecutive_corner_defects, total_defects,
            last_cast_date, last_quality_status, last_defect_note, today_cyclic_count, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mold_num, product_ids[p_code], zone, px, pz, tier, rot,
            st, t_casts, c_def, tot_def,
            today_str if st in ("poured", "cyclic_active") else yesterday_str,
            qual, note, today_cyc, note
        ))

    # 3. Seed Raw Material Batches (Sement, Shag'al, Sim — qachon keldi, qachon tugadi)
    batches = [
        # Old completed batches (to show history of "qachon keldi -> qachon tugadi")
        ("cement", "SEM-01", "Sement M450 (Qop/Val - 10 tonna)", "Ohangaron Sement Diler", ten_days_ago_str, five_days_ago_str, "depleted", 10000, 0, "kg", 1150, 11500000, "5 kunda to'liq ishlatib bo'lindi (195 ta ariq va 68 ta kolodets chiqdi)"),
        ("gravel", "SHG-01", "Yuvilgan Shag'al + Qum (Howo 25t)", "Chirchiq Karyer", ten_days_ago_str, two_days_ago_str, "depleted", 25000, 0, "kg", 140, 3500000, "8 kunda tugadi"),
        ("wire", "SIM-01", "Beton Armatura Simi Ø4mm / Ø5mm", "Metall Baza", ten_days_ago_str, yesterday_str, "depleted", 400, 0, "kg", 11500, 4600000, "9 kunda tugadi"),

        # Current active batches
        ("cement", "SEM-02", "Sement M450 (Yangi partiya - 12 tonna)", "Ohangaron Sement Diler", five_days_ago_str, None, "active", 12000, 4850, "kg", 1150, 13800000, "Hozirda ishlatilmoqda"),
        ("gravel", "SHG-02", "Yuvilgan Shag'al + Qum (2 ta Howo - 50t)", "Chirchiq Karyer", two_days_ago_str, None, "active", 50000, 36400, "kg", 140, 7000000, "Hozirda ishlatilmoqda"),
        ("wire", "SIM-02", "Beton Armatura Simi Ø4mm (500 kg)", "Metall Baza", yesterday_str, None, "active", 500, 425, "kg", 11800, 5900000, "Kecha yangi partiya olindi"),
    ]
    for b in batches:
        cur.execute("""
        INSERT INTO raw_material_batches (
            material_type, batch_code, material_name, supplier,
            arrived_date, depleted_date, status,
            initial_quantity, remaining_quantity, unit, unit_price, total_cost, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, b)

    # 4. Seed Daily Logs (Oxirgi 3 kunlik ish va ob-havo logi)
    daily_seed = [
        (two_days_ago_str, 1, "Toshkent", 21.0, 9.0, 15.0, 48.0, 12.0, "Ochiq quyoshli", "Mo'tadil ob-havo: Beton qotishi uchun ideal sharoit (18-20 soatda yechish mumkin).", 16, 18, 19, 1, 953000, "19 ta kolodets bitta qolipda quyildi"),
        (yesterday_str, 1, "Toshkent", 18.5, 7.5, 13.0, 55.0, 15.0, "Qisman bulutli", "Normal harorat: Qoliplarni moylashga e'tibor bering.", 18, 17, 21, 2, 1025000, "#12 va #19 qoliplar burchagi ushlab qoldi, #26 kolodets qolipida 21 dona chiqdi"),
        (today_str, 1, "Toshkent", 19.2, 8.1, 14.2, 50.0, 10.5, "Ochiq va iliq", "Qotish me'yorda. #12 qolip remontga olindi.", 14, 13, 18, 1, 868000, "Bugun 18 ta kolodets va 13 ta ariq quyildi"),
    ]
    for d in daily_seed:
        cur.execute("""
        INSERT INTO daily_logs (
            work_date, is_working_day, region_name,
            weather_temp_max, weather_temp_min, weather_temp_avg, weather_humidity, weather_wind_kmh,
            weather_condition, curing_advice,
            demolded_count, cast_count, cyclic_cast_count, defect_count, labor_cost_total, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (*d, datetime.now().isoformat()))

    # 5. Seed Orders (Buyurtmalar)
    orders_seed = [
        ("ORD-101", "Rustam Qurilish MChJ", "+998 90 123-45-67", five_days_ago_str, today_str, product_ids["A30"], 60, 40, 0, 95000, 5700000, 3000000, "partial", "Qolgan 20 ta 30-lik ariqni ertaga olib ketadi"),
        ("ORD-102", "Suvsoz Obod Ko'cha", "+998 97 700-11-22", two_days_ago_str, (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d"), product_ids["K104"], 35, 15, 60.0, 230000, 8050000, 5000000, "partial", "Balandligi 60sm lik kolodetslar"),
        ("ORD-103", "Abror aka (Yangi mahalla)", "+998 93 555-88-99", yesterday_str, (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d"), product_ids["A40"], 30, 0, 0, 135000, 4050000, 1500000, "pending", "40-lik ariq navbatda"),
        ("ORD-104", "Farhod Stroy", "+998 99 888-77-66", ten_days_ago_str, two_days_ago_str, product_ids["A22"], 40, 40, 0, 65000, 2600000, 2600000, "completed", "To'liq topshirilgan"),
    ]
    order_ids = {}
    for o in orders_seed:
        cur.execute("""
        INSERT INTO orders (
            order_number, customer_name, customer_phone, order_date, due_date,
            product_type_id, ordered_qty, delivered_qty, custom_height_cm,
            unit_price, total_amount, advance_paid, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, o)
        order_ids[o[0]] = cur.lastrowid

    # 6. Seed Sales (Buyurtma asosida sotilgan + Shoshilinch kerak bo'lib olib ketilgan!)
    sales_seed = [
        (two_days_ago_str, "order_fulfillment", order_ids["ORD-104"], "Farhod Stroy", "+998 99 888-77-66", product_ids["A22"], 40, 65000, 2600000, 2600000, "Perechisleniye", "ORD-104 buyurtma asosida topshirildi"),
        (two_days_ago_str, "urgent_pickup", None, "Shavkat aka (Kran bilan keldi)", "+998 94 611-22-33", product_ids["K104"], 8, 240000, 1920000, 1920000, "Naqd", "Shoshilinch kanalizatsiya qazilgan ekan, tayyoridan 8 ta olib ketdi"),
        (yesterday_str, "order_fulfillment", order_ids["ORD-101"], "Rustam Qurilish MChJ", "+998 90 123-45-67", product_ids["A30"], 40, 95000, 3800000, 3800000, "Naqd", "ORD-101 buyurtmasidan 1-reyis (40 dona) ketdi"),
        (yesterday_str, "urgent_pickup", None, "Baxtiyor usta", "+998 91 333-44-55", product_ids["A30"], 15, 100000, 1500000, 1500000, "Karta / Click", "Shoshilinch kerak bo'lib tayyor zaxiradan olib ketdi"),
        (today_str, "order_fulfillment", order_ids["ORD-102"], "Suvsoz Obod Ko'cha", "+998 97 700-11-22", product_ids["K104"], 15, 230000, 3450000, 3450000, "Perechisleniye", "ORD-102 buyurtmasidan 15 ta kolodets yuklandi"),
        (today_str, "urgent_pickup", None, "Ulug'bek (Qo'shni tuman)", "+998 90 999-00-11", product_ids["A50"], 10, 190000, 1900000, 1900000, "Naqd", "Shoshilinch ko'prik yoniga 10 ta 50-lik ariq olib ketdi"),
    ]
    for s in sales_seed:
        cur.execute("""
        INSERT INTO sales (
            sale_date, sale_type, order_id, customer_name, customer_phone,
            product_type_id, quantity, unit_price, total_amount, paid_amount, payment_method, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (*s, datetime.now().isoformat()))

    # 7. Seed Missing Size Requests (Korxonada mavjud bo'lmagan o'lchamlar so'rovi)
    missing_seed = [
        (two_days_ago_str, "Sardor Qurilish", "+998 90 321-45-67", "kolodets", "150-lik Katta Kolodets (Ichki Ø150sm)", "Tashqi diametri ~168sm, balandligi 90sm", 25, 420000, "Katta septik uchun so'radi, bizda faqat 104/118 borligi uchun qaytib ketdi"),
        (yesterday_str, "Yo'l Qurilish Bo'limi", "+998 98 111-22-33", "ariq", "60-lik Magistral Beton Ariq", "Ichki og'zi 60sm, chuqurligi 45sm, uzunligi 200sm", 80, 260000, "Trassa chetiga katta lotok kerak ekan"),
        (today_str, "Otabek (Xususiy uy)", "+998 93 444-55-66", "kolodets", "Kolodets Qopqog'i (Lyukli Plita Ø118sm)", "Bizning 118sm kolodets ustiga tushadigan beton qopqoq", 18, 140000, "Kolodets xalqasini bizdan oldi, lekin ustki qopqog'ini boshqa joydan qidirdi!"),
        (today_str, "dilshod Prorab", "+998 97 404-30-20", "kolodets", "150-lik Katta Kolodets (Ichki Ø150sm)", "Balandligi 60-90sm", 15, 420000, "Yana 150-lik kolodets so'raldi"),
    ]
    for ms in missing_seed:
        cur.execute("""
        INSERT INTO missing_size_requests (
            request_date, customer_name, customer_phone, requested_category,
            requested_size_name, dimensions_details, requested_qty, estimated_unit_price, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (*ms, datetime.now().isoformat()))

    conn.commit()
