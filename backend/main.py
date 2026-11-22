from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import urllib.request
import json
import os

from database import (
    init_db,
    get_connection,
    UZBEKISTAN_REGIONS,
    calculate_concrete_volume_m3,
    get_real_media_molds_seed,
    sync_real_media_layout,
)

app = FastAPI(
    title="Beton Ariq & Kolodets ERP + 3D Digital Twin API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "media"))
if os.path.isdir(MEDIA_DIR):
    app.mount("/media", StaticFiles(directory=MEDIA_DIR), name="media")


@app.on_event("startup")
def on_startup():
    init_db()


# -------------------- PYDANTIC MODELS --------------------

class SettingsUpdate(BaseModel):
    company_name: str
    region_id: str
    workshop_width_m: float = 7.0
    workshop_width_front_m: float = 7.0
    workshop_width_back_m: float = 8.2
    workshop_length_m: float = 16.5
    rail_gauge_m: float = 6.0


class WorkshopElementCreate(BaseModel):
    element_type: str  # 'tal_rails' | 'tal_crane' | 'meshalka' | 'vibrator' | 'stoyka'
    name: str
    pos_x: float = 0.0
    pos_z: float = 8.25
    pos_y: float = 0.0
    rotation_deg: float = 0.0
    length_m: float = 1.0
    width_m: float = 1.0
    height_m: float = 0.15
    extra_json: str = "{}"
    notes: str = ""


class WorkshopElementUpdate(BaseModel):
    name: Optional[str] = None
    pos_x: float
    pos_z: float
    pos_y: float = 0.0
    rotation_deg: float = 0.0
    length_m: float = 1.0
    width_m: float = 1.0
    height_m: float = 0.15
    extra_json: Optional[str] = None
    notes: Optional[str] = None


class BatchRowMoldsCreate(BaseModel):
    product_type_id: int
    count: int = 4
    zone: str = "1-Qator"
    pos_z: float = 3.0            # Eshikdan masofa Z (0 .. 16.5m)
    start_x: Optional[float] = None  # Agar None bo'lsa, markaz (0.0) atrofida simmetrik joylashadi
    gap_m: float = 0.08           # Qoliplar orasidagi masofa (metrda, masalan 0.08m = 8sm)
    stack_tier: int = 1
    rotation_deg: float = 0.0
    status: str = "empty"
    add_stoyka_pair: bool = True  # Har qatorda tagiga 2 tadan beton stoyka (brusok) yotqizish
    stoyka_spacing_m: float = 1.45  # 2 ta stoyka orasidagi masofa (metrda)
    notes: str = ""


class ProductCreate(BaseModel):
    code: str
    name: str
    category: str  # 'ariq' | 'kolodets'
    casting_mode: str = "stationary"  # 'stationary' | 'cyclic'
    inner_bottom_cm: float = 0
    inner_side_cm: float = 0
    inner_top_cm: float = 0
    wall_thickness_cm: float = 5.0
    length_cm: float = 150.0
    outer_diameter_cm: float = 0
    inner_diameter_cm: float = 0
    max_height_cm: float = 60.0
    default_height_cm: float = 60.0
    cement_norm_kg: float = 20.0
    gravel_norm_kg: float = 90.0
    wire_norm_kg: float = 1.5
    casting_labor_cost: float = 16000
    selling_price: float = 95000
    stock_qty: int = 0
    color_hex: str = "#3b82f6"
    description: str = ""


class MoldCreate(BaseModel):
    mold_number: str
    product_type_id: int
    zone: str = "Asosiy Sex"
    pos_x: float = 0.0
    pos_z: float = 0.0
    stack_tier: int = 1
    rotation_deg: float = 0.0
    status: str = "empty"
    notes: str = ""


class MoldPositionUpdate(BaseModel):
    zone: Optional[str] = None
    pos_x: float
    pos_z: float
    stack_tier: int = 1
    rotation_deg: float = 0.0
    status: Optional[str] = None
    notes: Optional[str] = None


class MoldRepairRequest(BaseModel):
    issue_description: str
    repair_action: str
    repair_cost: float = 0.0
    performed_by: str = "Sex ustasi"


class DemoldItem(BaseModel):
    mold_id: int
    quality_status: str = "clean"  # 'clean' | 'corner_stuck' | 'cracked'
    defect_location: str = ""
    notes: str = ""


class DemoldBatchRequest(BaseModel):
    work_date: Optional[str] = None
    items: List[DemoldItem]


class CastBatchRequest(BaseModel):
    work_date: Optional[str] = None
    mold_ids: List[int]
    notes: str = ""


class CyclicCastRequest(BaseModel):
    work_date: Optional[str] = None
    mold_id: int
    quantity: int
    custom_height_cm: float = 60.0
    clean_qty: int
    corner_stuck_qty: int = 0
    cracked_qty: int = 0
    defect_location: str = ""
    notes: str = ""


class OrderCreate(BaseModel):
    customer_name: str
    customer_phone: str = ""
    order_date: Optional[str] = None
    due_date: Optional[str] = None
    product_type_id: int
    ordered_qty: int
    custom_height_cm: float = 0.0
    unit_price: float
    advance_paid: float = 0.0
    notes: str = ""


class SaleCreate(BaseModel):
    sale_date: Optional[str] = None
    sale_type: str  # 'order_fulfillment' | 'urgent_pickup'
    order_id: Optional[int] = None
    customer_name: str
    customer_phone: str = ""
    product_type_id: int
    quantity: int
    unit_price: float
    paid_amount: float
    payment_method: str = "Naqd"
    notes: str = ""


class MissingSizeCreate(BaseModel):
    request_date: Optional[str] = None
    customer_name: str
    customer_phone: str = ""
    requested_category: str = "ariq"
    requested_size_name: str
    dimensions_details: str = ""
    requested_qty: int = 1
    estimated_unit_price: float = 0.0
    notes: str = ""


class RawMaterialBatchCreate(BaseModel):
    material_type: str  # 'cement' | 'gravel' | 'wire'
    batch_code: str
    material_name: str
    supplier: str = ""
    arrived_date: Optional[str] = None
    initial_quantity: float
    unit: str = "kg"
    unit_price: float
    notes: str = ""


class DepleteBatchRequest(BaseModel):
    depleted_date: Optional[str] = None
    notes: str = ""


# -------------------- HELPER: WEATHER FETCH & LOG --------------------

def fetch_weather_from_open_meteo(lat: float, lon: float) -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m"
        f"&daily=temperature_2m_max,temperature_2m_min"
        f"&timezone=auto&forecast_days=1"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "BetonERP/1.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            curr = data.get("current", {})
            daily = data.get("daily", {})
            t_curr = float(curr.get("temperature_2m", 16.0))
            t_max = float((daily.get("temperature_2m_max") or [t_curr + 3])[0])
            t_min = float((daily.get("temperature_2m_min") or [t_curr - 4])[0])
            hum = float(curr.get("relative_humidity_2m", 50.0))
            wind = float(curr.get("wind_speed_10m", 10.0))
            w_code = int(curr.get("weather_code", 0))

            if w_code == 0:
                cond = "Ochiq quyoshli"
            elif w_code in (1, 2, 3):
                cond = "Qisman bulutli"
            elif w_code in (45, 48):
                cond = "Tumanli"
            elif w_code in (51, 53, 55, 61, 63, 65, 80, 81, 82):
                cond = "Yomg'irli"
            elif w_code in (71, 73, 75, 77, 85, 86):
                cond = "Qorli / Sovuq"
            else:
                cond = "O'zgaruvchan ob-havo"

            if t_min < 5:
                advice = "Sovuq ob-havo: Beton sekin qotadi. Qolipdan erta yechmang (burchaklari ko'chib qolishi mumkin)!"
            elif t_max > 32:
                advice = "Jazirama issiq: Beton yorilmasligi uchun ustini namlab (suv sepib) turing!"
            elif "Yomg'ir" in cond:
                advice = "Namlik yuqori: Ochiq joydagi tayyor kolodets va ariqlarni yomg'irdan himoyalang."
            else:
                advice = "Mo'tadil ob-havo: Beton qotishi va qoliplarni yechish uchun qulay harorat."

            return {
                "temp_current": round(t_curr, 1),
                "temp_max": round(t_max, 1),
                "temp_min": round(t_min, 1),
                "temp_avg": round((t_max + t_min) / 2.0, 1),
                "humidity": round(hum, 0),
                "wind_kmh": round(wind, 1),
                "condition": cond,
                "curing_advice": advice,
                "source": "live_open_meteo",
            }
    except Exception:
        return {
            "temp_current": 17.5,
            "temp_max": 20.0,
            "temp_min": 9.0,
            "temp_avg": 14.5,
            "humidity": 52.0,
            "wind_kmh": 11.0,
            "condition": "Ochiq va iliq",
            "curing_advice": "Mo'tadil harorat: Beton qotishi me'yorda.",
            "source": "cached_estimate",
        }


def ensure_daily_log(conn, work_date: str):
    cur = conn.cursor()
    cur.execute("SELECT * FROM daily_logs WHERE work_date = ?", (work_date,))
    row = cur.fetchone()
    if row:
        return dict(row)

    cur.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cur.fetchone())
    w = fetch_weather_from_open_meteo(settings["latitude"], settings["longitude"])

    cur.execute("""
    INSERT OR IGNORE INTO daily_logs (
        work_date, is_working_day, region_name,
        weather_temp_max, weather_temp_min, weather_temp_avg, weather_humidity, weather_wind_kmh,
        weather_condition, curing_advice,
        demolded_count, cast_count, cyclic_cast_count, defect_count, labor_cost_total, notes, created_at
    ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 0, '', ?)
    """, (
        work_date, settings["region_name"],
        w["temp_max"], w["temp_min"], w["temp_avg"], w["humidity"], w["wind_kmh"],
        w["condition"], w["curing_advice"], datetime.now().isoformat()
    ))
    conn.commit()
    cur.execute("SELECT * FROM daily_logs WHERE work_date = ?", (work_date,))
    return dict(cur.fetchone())


def deduct_raw_materials(conn, cement_kg: float, gravel_kg: float, wire_kg: float, work_date: str):
    cur = conn.cursor()
    for m_type, used_val in [("cement", cement_kg), ("gravel", gravel_kg), ("wire", wire_kg)]:
        if used_val <= 0:
            continue
        cur.execute("""
            SELECT * FROM raw_material_batches
            WHERE material_type = ? AND status = 'active'
            ORDER BY arrived_date ASC, id ASC
        """, (m_type,))
        batches = [dict(r) for r in cur.fetchall()]
        rem_to_deduct = used_val
        for b in batches:
            if rem_to_deduct <= 0:
                break
            avail = b["remaining_quantity"]
            if avail <= rem_to_deduct:
                rem_to_deduct -= avail
                cur.execute("""
                    UPDATE raw_material_batches
                    SET remaining_quantity = 0, status = 'depleted', depleted_date = ?
                    WHERE id = ?
                """, (work_date, b["id"]))
            else:
                new_rem = round(avail - rem_to_deduct, 2)
                rem_to_deduct = 0
                cur.execute("""
                    UPDATE raw_material_batches
                    SET remaining_quantity = ?
                    WHERE id = ?
                """, (new_rem, b["id"]))


# -------------------- ENDPOINTS --------------------

@app.get("/api/settings")
def get_settings():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cur.fetchone())
    conn.close()
    return {
        "settings": settings,
        "regions": UZBEKISTAN_REGIONS,
    }


@app.put("/api/settings")
def update_settings(payload: SettingsUpdate):
    region = next((r for r in UZBEKISTAN_REGIONS if r["id"] == payload.region_id), UZBEKISTAN_REGIONS[0])
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE settings
        SET company_name = ?, region_id = ?, region_name = ?, latitude = ?, longitude = ?,
            workshop_width_m = ?, workshop_width_front_m = ?, workshop_width_back_m = ?,
            workshop_length_m = ?, rail_gauge_m = ?, updated_at = ?
        WHERE id = 1
    """, (
        payload.company_name,
        region["id"],
        region["name"],
        region["lat"],
        region["lon"],
        payload.workshop_width_front_m or payload.workshop_width_m,
        payload.workshop_width_front_m,
        payload.workshop_width_back_m,
        payload.workshop_length_m,
        payload.rail_gauge_m,
        datetime.now().isoformat(),
    ))
    # Also refresh today's weather for the newly selected region
    today_str = datetime.now().strftime("%Y-%m-%d")
    w = fetch_weather_from_open_meteo(region["lat"], region["lon"])
    cur.execute("""
        UPDATE daily_logs
        SET region_name = ?, weather_temp_max = ?, weather_temp_min = ?, weather_temp_avg = ?,
            weather_humidity = ?, weather_wind_kmh = ?, weather_condition = ?, curing_advice = ?
        WHERE work_date = ?
    """, (
        region["name"], w["temp_max"], w["temp_min"], w["temp_avg"],
        w["humidity"], w["wind_kmh"], w["condition"], w["curing_advice"], today_str
    ))
    conn.commit()
    cur.execute("SELECT * FROM settings WHERE id = 1")
    updated = dict(cur.fetchone())
    conn.close()
    return {"settings": updated, "weather": w}


@app.get("/api/weather/current")
def get_current_weather():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM settings WHERE id = 1")
    settings = dict(cur.fetchone())
    today_str = datetime.now().strftime("%Y-%m-%d")
    log = ensure_daily_log(conn, today_str)
    w = fetch_weather_from_open_meteo(settings["latitude"], settings["longitude"])
    conn.close()
    return {
        "region_name": settings["region_name"],
        "date": today_str,
        "weather": w,
        "daily_log": log,
    }


@app.get("/api/products")
def list_products():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.*,
               (SELECT COUNT(*) FROM molds m WHERE m.product_type_id = p.id) as molds_count,
               (SELECT COUNT(*) FROM molds m WHERE m.product_type_id = p.id AND m.status = 'maintenance') as maintenance_molds_count
        FROM product_types p
        ORDER BY p.category ASC, p.id ASC
    """)
    items = [dict(r) for r in cur.fetchall()]
    conn.close()
    return items


@app.post("/api/products")
def create_product(payload: ProductCreate):
    vol = calculate_concrete_volume_m3(
        payload.category,
        payload.inner_bottom_cm,
        payload.inner_side_cm,
        payload.inner_top_cm,
        payload.wall_thickness_cm,
        payload.length_cm,
        payload.outer_diameter_cm,
        payload.inner_diameter_cm,
        payload.default_height_cm or 60.0,
    )
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO product_types (
                code, name, category, casting_mode,
                inner_bottom_cm, inner_side_cm, inner_top_cm, wall_thickness_cm, length_cm,
                outer_diameter_cm, inner_diameter_cm, max_height_cm, default_height_cm,
                concrete_volume_m3, cement_norm_kg, gravel_norm_kg, wire_norm_kg,
                casting_labor_cost, selling_price, stock_qty, color_hex, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            payload.code, payload.name, payload.category, payload.casting_mode,
            payload.inner_bottom_cm, payload.inner_side_cm, payload.inner_top_cm,
            payload.wall_thickness_cm, payload.length_cm,
            payload.outer_diameter_cm, payload.inner_diameter_cm,
            payload.max_height_cm, payload.default_height_cm,
            vol, payload.cement_norm_kg, payload.gravel_norm_kg, payload.wire_norm_kg,
            payload.casting_labor_cost, payload.selling_price, payload.stock_qty,
            payload.color_hex, payload.description
        ))
        conn.commit()
        new_id = cur.lastrowid
        cur.execute("SELECT * FROM product_types WHERE id = ?", (new_id,))
        row = dict(cur.fetchone())
        conn.close()
        return row
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/molds")
def list_molds():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT m.*,
               p.code as product_code,
               p.name as product_name,
               p.category as product_category,
               p.casting_mode as casting_mode,
               p.inner_bottom_cm, p.inner_side_cm, p.inner_top_cm, p.wall_thickness_cm, p.length_cm,
               p.outer_diameter_cm, p.inner_diameter_cm, p.max_height_cm, p.default_height_cm,
               p.casting_labor_cost, p.selling_price, p.color_hex
        FROM molds m
        JOIN product_types p ON p.id = m.product_type_id
        ORDER BY m.id ASC
    """)
    molds = [dict(r) for r in cur.fetchall()]

    # Attach recent production history & repairs to each mold
    for m in molds:
        cur.execute("""
            SELECT * FROM production_events
            WHERE mold_id = ?
            ORDER BY id DESC LIMIT 6
        """, (m["id"],))
        m["recent_events"] = [dict(e) for e in cur.fetchall()]

        cur.execute("""
            SELECT * FROM mold_repairs
            WHERE mold_id = ?
            ORDER BY id DESC LIMIT 5
        """, (m["id"],))
        m["repairs"] = [dict(rep) for rep in cur.fetchall()]

    conn.close()
    return molds


@app.post("/api/molds")
def create_mold(payload: MoldCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO molds (
                mold_number, product_type_id, zone, pos_x, pos_z, stack_tier, rotation_deg,
                status, total_casts, consecutive_corner_defects, total_defects,
                last_quality_status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 'clean', ?)
        """, (
            payload.mold_number, payload.product_type_id, payload.zone,
            payload.pos_x, payload.pos_z, payload.stack_tier, payload.rotation_deg,
            payload.status, payload.notes
        ))
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return {"id": new_id, "message": "Yangi qolip qo'shildi"}
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/molds/{mold_id}/position")
def update_mold_position(mold_id: int, payload: MoldPositionUpdate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM molds WHERE id = ?", (mold_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Qolip topilmadi")

    zone = payload.zone if payload.zone is not None else existing["zone"]
    notes = payload.notes if payload.notes is not None else existing["notes"]
    status = payload.status if payload.status is not None else existing["status"]

    cur.execute("""
        UPDATE molds
        SET zone = ?, pos_x = ?, pos_z = ?, stack_tier = ?, rotation_deg = ?, status = ?, notes = ?
        WHERE id = ?
    """, (zone, payload.pos_x, payload.pos_z, payload.stack_tier, payload.rotation_deg, status, notes, mold_id))
    conn.commit()
    conn.close()
    return {"status": "ok", "mold_id": mold_id}


@app.delete("/api/molds/{mold_id}")
def delete_mold(mold_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = OFF;")
    cur.execute("DELETE FROM production_events WHERE mold_id = ?", (mold_id,))
    cur.execute("DELETE FROM mold_repairs WHERE mold_id = ?", (mold_id,))
    cur.execute("DELETE FROM molds WHERE id = ?", (mold_id,))
    cur.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    conn.close()
    return {"status": "deleted", "mold_id": mold_id}


@app.post("/api/molds/batch-row")
def create_batch_row_molds(payload: BatchRowMoldsCreate):
    """
    Mathematically places a row of N molds across the yard at distance Z from the entrance door,
    and optionally places a pair of concrete stoykas (2 ta brusok taglik) beneath the row.
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM product_types WHERE id = ?", (payload.product_type_id,))
    prod = cur.fetchone()
    if not prod:
        conn.close()
        raise HTTPException(status_code=404, detail="Mahsulot turi topilmadi")
    prod = dict(prod)

    # Calculate exact outer width of one mold in meters
    if prod["category"] == "kolodets":
        mold_w_m = (prod["outer_diameter_cm"] or 118.0) / 100.0
    else:
        inner_top_m = (prod["inner_top_cm"] or 30.0) / 100.0
        wall_m = (prod["wall_thickness_cm"] or 5.5) / 100.0
        mold_w_m = inner_top_m + 2.0 * wall_m + 0.08

    count = max(1, min(payload.count, 30))
    step_x = round(mold_w_m + max(payload.gap_m, 0.0), 4)
    total_span_m = round((count - 1) * step_x, 4)

    if payload.start_x is not None:
        first_x = payload.start_x
    else:
        first_x = round(-total_span_m / 2.0, 3)

    # Determine next sequential mold number
    cur.execute("SELECT COUNT(*) as cnt FROM molds")
    base_idx = cur.fetchone()["cnt"] + 1

    created_ids = []
    for i in range(count):
        px = round(first_x + i * step_x, 3)
        pz = round(payload.pos_z, 3)
        num_str = f"#{base_idx + i:02d} ({prod['code']})"
        # Avoid duplicate mold_number if any were deleted
        suffix = 0
        while True:
            cur.execute("SELECT id FROM molds WHERE mold_number = ?", (num_str,))
            if not cur.fetchone():
                break
            suffix += 1
            num_str = f"#{base_idx + i + suffix:02d} ({prod['code']})"

        cur.execute("""
            INSERT INTO molds (
                mold_number, product_type_id, zone, pos_x, pos_z, stack_tier, rotation_deg,
                status, total_casts, consecutive_corner_defects, total_defects,
                last_quality_status, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 'clean', ?)
        """, (
            num_str,
            prod["id"],
            payload.zone,
            px,
            pz,
            payload.stack_tier,
            payload.rotation_deg,
            payload.status,
            payload.notes or f"Eshikdan Z={pz}m, X={px}m",
        ))
        created_ids.append(cur.lastrowid)

    # Optionally add the 2 parallel concrete stoykas (taglik brusoklar, 2 tadan) beneath this row
    stoyka_id = None
    if payload.add_stoyka_pair and payload.stack_tier == 1:
        row_width_m = round(max(total_span_m + mold_w_m + 0.3, 1.2), 2)
        center_x = round(first_x + total_span_m / 2.0, 3)
        extra = json.dumps({
            "is_pair": True,
            "pair_spacing_m": round(payload.stoyka_spacing_m, 2),
            "beam_width_m": 0.16,
            "beam_height_m": 0.14,
        })
        cur.execute("""
            INSERT INTO workshop_elements (
                element_type, name, pos_x, pos_z, pos_y, rotation_deg,
                length_m, width_m, height_m, extra_json, notes
            ) VALUES (?, ?, ?, ?, 0.0, 0.0, ?, ?, 0.14, ?, ?)
        """, (
            "stoyka",
            f"{payload.zone} — 2 ta Taglik Stoyka (Brusok)",
            center_x,
            round(payload.pos_z, 3),
            round(payload.stoyka_spacing_m, 2),
            row_width_m,
            extra,
            f"Har qatorda 2 tadan yotqizilgan stoyka (Z={round(payload.pos_z, 2)}m, kengligi={row_width_m}m, orasi={payload.stoyka_spacing_m}m)",
        ))
        stoyka_id = cur.lastrowid

    conn.commit()
    conn.close()
    return {
        "created_mold_ids": created_ids,
        "stoyka_id": stoyka_id,
        "count": count,
        "step_x_m": step_x,
    }


# -------------------- WORKSHOP STRUCTURAL & EQUIPMENT ELEMENTS (3D BUILDER) --------------------

@app.get("/api/workshop-elements")
def list_workshop_elements():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM workshop_elements ORDER BY id ASC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/api/workshop-elements")
def create_workshop_element(payload: WorkshopElementCreate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO workshop_elements (
            element_type, name, pos_x, pos_z, pos_y, rotation_deg,
            length_m, width_m, height_m, extra_json, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        payload.element_type,
        payload.name,
        payload.pos_x,
        payload.pos_z,
        payload.pos_y,
        payload.rotation_deg,
        payload.length_m,
        payload.width_m,
        payload.height_m,
        payload.extra_json or "{}",
        payload.notes,
    ))
    conn.commit()
    new_id = cur.lastrowid
    cur.execute("SELECT * FROM workshop_elements WHERE id = ?", (new_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row


@app.put("/api/workshop-elements/{elem_id}")
def update_workshop_element(elem_id: int, payload: WorkshopElementUpdate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM workshop_elements WHERE id = ?", (elem_id,))
    existing = cur.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Element topilmadi")

    name = payload.name if payload.name is not None else existing["name"]
    extra_json = payload.extra_json if payload.extra_json is not None else existing["extra_json"]
    notes = payload.notes if payload.notes is not None else existing["notes"]

    cur.execute("""
        UPDATE workshop_elements
        SET name = ?, pos_x = ?, pos_z = ?, pos_y = ?, rotation_deg = ?,
            length_m = ?, width_m = ?, height_m = ?, extra_json = ?, notes = ?
        WHERE id = ?
    """, (
        name,
        payload.pos_x,
        payload.pos_z,
        payload.pos_y,
        payload.rotation_deg,
        payload.length_m,
        payload.width_m,
        payload.height_m,
        extra_json,
        notes,
        elem_id,
    ))
    conn.commit()
    cur.execute("SELECT * FROM workshop_elements WHERE id = ?", (elem_id,))
    row = dict(cur.fetchone())
    conn.close()
    return row


@app.delete("/api/workshop-elements/{elem_id}")
def delete_workshop_element(elem_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM workshop_elements WHERE id = ?", (elem_id,))
    conn.commit()
    conn.close()
    return {"status": "deleted", "id": elem_id}


@app.post("/api/workshop/clear")
def clear_workshop_scene(keep_rails: bool = True):
    """
    Clears all molds and workshop elements (optionally keeping the 6.0m side Tal rails)
    so the user can build the 16.5m x (7.0m -> 8.2m) scene from scratch mathematically.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = OFF;")
    cur.execute("DELETE FROM production_events;")
    cur.execute("DELETE FROM mold_repairs;")
    cur.execute("DELETE FROM molds;")
    if keep_rails:
        cur.execute("DELETE FROM workshop_elements WHERE element_type != 'tal_rails';")
        cur.execute("SELECT COUNT(*) as cnt FROM workshop_elements WHERE element_type = 'tal_rails'")
        if cur.fetchone()["cnt"] == 0:
            cur.execute("""
            INSERT INTO workshop_elements (
                element_type, name, pos_x, pos_z, pos_y, rotation_deg,
                length_m, width_m, height_m, extra_json, notes
            ) VALUES (
                'tal_rails', 'Ikki yondagi Tal relslari (Orasi 6.0m)',
                0.0, 8.25, 0.0, 0.0, 16.5, 6.0, 0.10,
                '{"z_start": 0.0, "z_end": 16.5, "gauge_m": 6.0}',
                'Eshikdan (0m) oxirgi shlakoblok devorgacha (16.5m) 6m oraliqdagi ikki yon rels'
            )
            """)
    else:
        cur.execute("DELETE FROM workshop_elements;")
    cur.execute("PRAGMA foreign_keys = ON;")
    conn.commit()
    conn.close()
    return {"status": "cleared", "keep_rails": keep_rails}


@app.post("/api/molds/{mold_id}/repair")
def repair_mold(mold_id: int, payload: MoldRepairRequest):
    conn = get_connection()
    cur = conn.cursor()
    today_str = datetime.now().strftime("%Y-%m-%d")

    cur.execute("""
        INSERT INTO mold_repairs (
            mold_id, repair_date, issue_description, repair_action, repair_cost, performed_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        mold_id, today_str, payload.issue_description, payload.repair_action,
        payload.repair_cost, payload.performed_by, datetime.now().isoformat()
    ))

    cur.execute("""
        UPDATE molds
        SET status = 'empty',
            consecutive_corner_defects = 0,
            last_quality_status = 'clean',
            last_defect_note = ?,
            notes = ?
        WHERE id = ?
    """, (f"Ta'mirlandi ({today_str}): {payload.repair_action}", f"Ta'mirlandi: {payload.repair_action}", mold_id))

    conn.commit()
    conn.close()
    return {"status": "repaired", "mold_id": mold_id}


# -------------------- DAILY PRODUCTION: DEMOLD, CAST, CYCLIC CAST --------------------

@app.post("/api/production/demold")
def demold_batch(payload: DemoldBatchRequest):
    work_date = payload.work_date or datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    ensure_daily_log(conn, work_date)
    cur = conn.cursor()

    demolded_total = 0
    defect_total = 0
    auto_maintenance_molds = []

    for item in payload.items:
        cur.execute("SELECT * FROM molds WHERE id = ?", (item.mold_id,))
        mold = cur.fetchone()
        if not mold:
            continue
        mold = dict(mold)
        p_id = mold["product_type_id"]

        # Update consecutive corner defects & maintenance trigger
        consec = mold["consecutive_corner_defects"]
        tot_def = mold["total_defects"]
        new_status = "empty"

        if item.quality_status == "corner_stuck":
            consec += 1
            tot_def += 1
            defect_total += 1
            if consec >= 2:
                new_status = "maintenance"
                auto_maintenance_molds.append(mold["mold_number"])
        elif item.quality_status == "cracked":
            consec += 1
            tot_def += 1
            defect_total += 1
            if consec >= 2:
                new_status = "maintenance"
                auto_maintenance_molds.append(mold["mold_number"])
        else:
            consec = 0

        note_text = item.defect_location or item.notes or ("Toza chiqdi" if item.quality_status == "clean" else "Burchagi ushlab qoldi")
        if new_status == "maintenance":
            note_text = f"AVTO-OGOHLANTIRISH: Ketma-ket {consec} marta defekt ({item.defect_location or 'burchagi ushladi'})! Remont kerak."

        cur.execute("""
            UPDATE molds
            SET status = ?,
                consecutive_corner_defects = ?,
                total_defects = ?,
                last_quality_status = ?,
                last_defect_note = ?,
                notes = ?
            WHERE id = ?
        """, (new_status, consec, tot_def, item.quality_status, note_text, note_text, mold["id"]))

        # Add to finished product stock (unless completely cracked/unusable)
        if item.quality_status != "cracked":
            cur.execute("UPDATE product_types SET stock_qty = stock_qty + 1 WHERE id = ?", (p_id,))

        cur.execute("""
            INSERT INTO production_events (
                work_date, event_type, mold_id, product_type_id, quantity,
                custom_height_cm, quality_status, defect_location,
                labor_cost_accrued, cement_used_kg, gravel_used_kg, wire_used_kg, notes, created_at
            ) VALUES (?, 'demold', ?, ?, 1, 0, ?, ?, 0, 0, 0, 0, ?, ?)
        """, (
            work_date, mold["id"], p_id, item.quality_status,
            item.defect_location, item.notes, datetime.now().isoformat()
        ))
        demolded_total += 1

    cur.execute("""
        UPDATE daily_logs
        SET demolded_count = demolded_count + ?,
            defect_count = defect_count + ?
        WHERE work_date = ?
    """, (demolded_total, defect_total, work_date))

    conn.commit()
    conn.close()
    return {
        "demolded_count": demolded_total,
        "defect_count": defect_total,
        "auto_maintenance_molds": auto_maintenance_molds,
    }


@app.post("/api/production/cast")
def cast_stationary_molds(payload: CastBatchRequest):
    work_date = payload.work_date or datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    ensure_daily_log(conn, work_date)
    cur = conn.cursor()

    cast_total = 0
    total_labor = 0.0
    total_cement = 0.0
    total_gravel = 0.0
    total_wire = 0.0

    for m_id in payload.mold_ids:
        cur.execute("""
            SELECT m.*, p.casting_labor_cost, p.cement_norm_kg, p.gravel_norm_kg, p.wire_norm_kg
            FROM molds m
            JOIN product_types p ON p.id = m.product_type_id
            WHERE m.id = ?
        """, (m_id,))
        row = cur.fetchone()
        if not row:
            continue
        m = dict(row)

        cur.execute("""
            UPDATE molds
            SET status = 'poured',
                total_casts = total_casts + 1,
                last_cast_date = ?
            WHERE id = ?
        """, (work_date, m_id))

        labor = float(m["casting_labor_cost"])
        cem = float(m["cement_norm_kg"])
        grv = float(m["gravel_norm_kg"])
        wir = float(m["wire_norm_kg"])

        cur.execute("""
            INSERT INTO production_events (
                work_date, event_type, mold_id, product_type_id, quantity,
                custom_height_cm, quality_status, defect_location,
                labor_cost_accrued, cement_used_kg, gravel_used_kg, wire_used_kg, notes, created_at
            ) VALUES (?, 'cast', ?, ?, 1, 0, 'clean', '', ?, ?, ?, ?, ?, ?)
        """, (
            work_date, m_id, m["product_type_id"],
            labor, cem, grv, wir, payload.notes, datetime.now().isoformat()
        ))

        cast_total += 1
        total_labor += labor
        total_cement += cem
        total_gravel += grv
        total_wire += wir

    deduct_raw_materials(conn, total_cement, total_gravel, total_wire, work_date)

    cur.execute("""
        UPDATE daily_logs
        SET cast_count = cast_count + ?,
            labor_cost_total = labor_cost_total + ?
        WHERE work_date = ?
    """, (cast_total, total_labor, work_date))

    conn.commit()
    conn.close()
    return {
        "cast_count": cast_total,
        "labor_cost_added": total_labor,
        "cement_used_kg": round(total_cement, 1),
        "gravel_used_kg": round(total_gravel, 1),
        "wire_used_kg": round(total_wire, 2),
    }


@app.post("/api/production/cyclic-cast")
def cast_cyclic_mold(payload: CyclicCastRequest):
    """
    Handles single Kolodets mold (Ø118/104, height <= 60cm) that is cast & immediately demolded
    repeatedly 20+ times in a single day!
    """
    work_date = payload.work_date or datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    ensure_daily_log(conn, work_date)
    cur = conn.cursor()

    cur.execute("""
        SELECT m.*, p.casting_labor_cost, p.cement_norm_kg, p.gravel_norm_kg, p.wire_norm_kg, p.max_height_cm
        FROM molds m
        JOIN product_types p ON p.id = m.product_type_id
        WHERE m.id = ?
    """, (payload.mold_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Kolodets qolipi topilmadi")
    m = dict(row)

    qty = max(payload.quantity, 1)
    height_ratio = min(max(payload.custom_height_cm, 20.0), 60.0) / (m["max_height_cm"] or 60.0)

    labor_total = float(m["casting_labor_cost"]) * qty
    cement_total = round(float(m["cement_norm_kg"]) * height_ratio * qty, 1)
    gravel_total = round(float(m["gravel_norm_kg"]) * height_ratio * qty, 1)
    wire_total = round(float(m["wire_norm_kg"]) * height_ratio * qty, 2)

    defects = payload.corner_stuck_qty + payload.cracked_qty
    usable_qty = max(qty - payload.cracked_qty, 0)

    qual_status = "clean"
    if payload.cracked_qty > 0:
        qual_status = "cracked"
    elif payload.corner_stuck_qty > 0:
        qual_status = "corner_stuck"

    consec = m["consecutive_corner_defects"] + (1 if payload.corner_stuck_qty >= 2 else 0)
    if payload.corner_stuck_qty == 0 and payload.cracked_qty == 0:
        consec = 0

    new_status = "maintenance" if consec >= 2 else "cyclic_active"

    cur.execute("""
        UPDATE molds
        SET status = ?,
            total_casts = total_casts + ?,
            today_cyclic_count = today_cyclic_count + ?,
            consecutive_corner_defects = ?,
            total_defects = total_defects + ?,
            last_cast_date = ?,
            last_quality_status = ?,
            last_defect_note = ?
        WHERE id = ?
    """, (
        new_status, qty, qty, consec, defects, work_date, qual_status,
        payload.defect_location or payload.notes, payload.mold_id
    ))

    cur.execute("""
        UPDATE product_types
        SET stock_qty = stock_qty + ?
        WHERE id = ?
    """, (usable_qty, m["product_type_id"]))

    cur.execute("""
        INSERT INTO production_events (
            work_date, event_type, mold_id, product_type_id, quantity,
            custom_height_cm, quality_status, defect_location,
            labor_cost_accrued, cement_used_kg, gravel_used_kg, wire_used_kg, notes, created_at
        ) VALUES (?, 'cyclic_cast', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        work_date, payload.mold_id, m["product_type_id"], qty,
        payload.custom_height_cm, qual_status, payload.defect_location,
        labor_total, cement_total, gravel_total, wire_total,
        payload.notes or f"Bir kunda {qty} dona (h={payload.custom_height_cm}sm) quyib-yechildi",
        datetime.now().isoformat()
    ))

    deduct_raw_materials(conn, cement_total, gravel_total, wire_total, work_date)

    cur.execute("""
        UPDATE daily_logs
        SET cyclic_cast_count = cyclic_cast_count + ?,
            defect_count = defect_count + ?,
            labor_cost_total = labor_cost_total + ?
        WHERE work_date = ?
    """, (qty, defects, labor_total, work_date))

    conn.commit()
    conn.close()
    return {
        "cyclic_cast_qty": qty,
        "usable_added_to_stock": usable_qty,
        "labor_cost_added": labor_total,
        "cement_used_kg": cement_total,
        "gravel_used_kg": gravel_total,
        "wire_used_kg": wire_total,
    }


@app.get("/api/daily-logs")
def list_daily_logs():
    conn = get_connection()
    today_str = datetime.now().strftime("%Y-%m-%d")
    ensure_daily_log(conn, today_str)
    cur = conn.cursor()
    cur.execute("SELECT * FROM daily_logs ORDER BY work_date DESC LIMIT 30")
    logs = [dict(r) for r in cur.fetchall()]

    for lg in logs:
        cur.execute("""
            SELECT e.*, m.mold_number, p.name as product_name, p.code as product_code
            FROM production_events e
            JOIN molds m ON m.id = e.mold_id
            JOIN product_types p ON p.id = e.product_type_id
            WHERE e.work_date = ?
            ORDER BY e.id DESC
        """, (lg["work_date"],))
        lg["events"] = [dict(ev) for ev in cur.fetchall()]

    conn.close()
    return logs


# -------------------- ORDERS, SALES & MISSING SIZES --------------------

@app.get("/api/orders")
def list_orders():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT o.*, p.code as product_code, p.name as product_name, p.stock_qty
        FROM orders o
        JOIN product_types p ON p.id = o.product_type_id
        ORDER BY o.id DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/api/orders")
def create_order(payload: OrderCreate):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) as cnt FROM orders")
    next_num = cur.fetchone()["cnt"] + 101
    order_number = f"ORD-{next_num}"
    order_date = payload.order_date or datetime.now().strftime("%Y-%m-%d")
    total_amount = payload.ordered_qty * payload.unit_price

    cur.execute("""
        INSERT INTO orders (
            order_number, customer_name, customer_phone, order_date, due_date,
            product_type_id, ordered_qty, delivered_qty, custom_height_cm,
            unit_price, total_amount, advance_paid, status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 'pending', ?)
    """, (
        order_number, payload.customer_name, payload.customer_phone,
        order_date, payload.due_date or order_date,
        payload.product_type_id, payload.ordered_qty, payload.custom_height_cm,
        payload.unit_price, total_amount, payload.advance_paid, payload.notes
    ))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "order_number": order_number}


@app.get("/api/sales")
def list_sales():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT s.*, p.code as product_code, p.name as product_name, o.order_number
        FROM sales s
        JOIN product_types p ON p.id = s.product_type_id
        LEFT JOIN orders o ON o.id = s.order_id
        ORDER BY s.id DESC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/api/sales")
def create_sale(payload: SaleCreate):
    conn = get_connection()
    cur = conn.cursor()
    sale_date = payload.sale_date or datetime.now().strftime("%Y-%m-%d")
    total_amount = payload.quantity * payload.unit_price

    cur.execute("SELECT * FROM product_types WHERE id = ?", (payload.product_type_id,))
    product = cur.fetchone()
    if not product:
        conn.close()
        raise HTTPException(status_code=404, detail="Mahsulot turi topilmadi")

    # Deduct from stock (allow going down to 0 or negative if pre-sold)
    new_stock = max(0, product["stock_qty"] - payload.quantity)
    cur.execute("UPDATE product_types SET stock_qty = ? WHERE id = ?", (new_stock, payload.product_type_id))

    # If tied to an order, update order delivered_qty and status
    if payload.order_id:
        cur.execute("SELECT * FROM orders WHERE id = ?", (payload.order_id,))
        ord_row = cur.fetchone()
        if ord_row:
            new_deliv = ord_row["delivered_qty"] + payload.quantity
            new_status = "completed" if new_deliv >= ord_row["ordered_qty"] else "partial"
            cur.execute("""
                UPDATE orders
                SET delivered_qty = ?, status = ?
                WHERE id = ?
            """, (new_deliv, new_status, payload.order_id))

    cur.execute("""
        INSERT INTO sales (
            sale_date, sale_type, order_id, customer_name, customer_phone,
            product_type_id, quantity, unit_price, total_amount, paid_amount, payment_method, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        sale_date, payload.sale_type, payload.order_id, payload.customer_name, payload.customer_phone,
        payload.product_type_id, payload.quantity, payload.unit_price, total_amount,
        payload.paid_amount, payload.payment_method, payload.notes, datetime.now().isoformat()
    ))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "total_amount": total_amount}


@app.get("/api/missing-sizes")
def list_missing_sizes():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM missing_size_requests ORDER BY id DESC")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


@app.post("/api/missing-sizes")
def create_missing_size(payload: MissingSizeCreate):
    conn = get_connection()
    cur = conn.cursor()
    req_date = payload.request_date or datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        INSERT INTO missing_size_requests (
            request_date, customer_name, customer_phone, requested_category,
            requested_size_name, dimensions_details, requested_qty, estimated_unit_price, notes, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        req_date, payload.customer_name, payload.customer_phone, payload.requested_category,
        payload.requested_size_name, payload.dimensions_details, payload.requested_qty,
        payload.estimated_unit_price, payload.notes, datetime.now().isoformat()
    ))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id}


# -------------------- RAW MATERIALS (SEMENT, SHAG'AL, SIM) --------------------

@app.get("/api/materials")
def list_materials():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM raw_material_batches ORDER BY id DESC")
    batches = [dict(r) for r in cur.fetchall()]
    today_str = datetime.now().strftime("%Y-%m-%d")

    for b in batches:
        start_d = b["arrived_date"]
        end_d = b["depleted_date"] or today_str
        cur.execute("""
            SELECT COALESCE(SUM(quantity), 0) as produced_units
            FROM production_events
            WHERE event_type IN ('cast', 'cyclic_cast')
              AND work_date >= ? AND work_date <= ?
        """, (start_d, end_d))
        b["produced_units_in_period"] = cur.fetchone()["produced_units"]

    conn.close()
    return batches


@app.post("/api/materials")
def create_material_batch(payload: RawMaterialBatchCreate):
    conn = get_connection()
    cur = conn.cursor()
    arr_date = payload.arrived_date or datetime.now().strftime("%Y-%m-%d")
    total_cost = round(payload.initial_quantity * payload.unit_price, 2)
    cur.execute("""
        INSERT INTO raw_material_batches (
            material_type, batch_code, material_name, supplier,
            arrived_date, depleted_date, status,
            initial_quantity, remaining_quantity, unit, unit_price, total_cost, notes
        ) VALUES (?, ?, ?, ?, ?, NULL, 'active', ?, ?, ?, ?, ?, ?)
    """, (
        payload.material_type, payload.batch_code, payload.material_name, payload.supplier,
        arr_date, payload.initial_quantity, payload.initial_quantity,
        payload.unit, payload.unit_price, total_cost, payload.notes
    ))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return {"id": new_id, "total_cost": total_cost}


@app.post("/api/materials/{batch_id}/deplete")
def mark_batch_depleted(batch_id: int, payload: DepleteBatchRequest):
    conn = get_connection()
    cur = conn.cursor()
    dep_date = payload.depleted_date or datetime.now().strftime("%Y-%m-%d")
    cur.execute("""
        UPDATE raw_material_batches
        SET status = 'depleted', remaining_quantity = 0, depleted_date = ?,
            notes = CASE WHEN ? != '' THEN ? ELSE notes END
        WHERE id = ?
    """, (dep_date, payload.notes, payload.notes, batch_id))
    conn.commit()
    conn.close()
    return {"status": "depleted", "batch_id": batch_id, "depleted_date": dep_date}


# -------------------- ANALYTICS & SMART ADVISOR --------------------

@app.get("/api/analytics/dashboard")
def get_dashboard_analytics():
    conn = get_connection()
    cur = conn.cursor()

    # 1. Revenue & Cash Flow
    cur.execute("SELECT COALESCE(SUM(total_amount), 0) as total_sales, COALESCE(SUM(paid_amount), 0) as cash_received FROM sales")
    sales_row = dict(cur.fetchone())

    cur.execute("""
        SELECT sale_type, COALESCE(SUM(quantity), 0) as qty, COALESCE(SUM(total_amount), 0) as amount
        FROM sales
        GROUP BY sale_type
    """)
    sales_by_type = {r["sale_type"]: dict(r) for r in cur.fetchall()}

    # 2. Expenses (Materials + Labor + Mold Repairs)
    cur.execute("SELECT COALESCE(SUM(total_cost), 0) as mat_cost FROM raw_material_batches")
    mat_cost = cur.fetchone()["mat_cost"]

    cur.execute("SELECT COALESCE(SUM(labor_cost_total), 0) as labor_cost FROM daily_logs")
    labor_cost = cur.fetchone()["labor_cost"]

    cur.execute("SELECT COALESCE(SUM(repair_cost), 0) as rep_cost FROM mold_repairs")
    repair_cost = cur.fetchone()["rep_cost"]

    total_expenses = mat_cost + labor_cost + repair_cost
    net_balance = sales_row["total_sales"] - total_expenses

    # 3. Demand by Product Size (Sold + Pending Orders)
    cur.execute("""
        SELECT p.id, p.code, p.name, p.category, p.selling_price, p.stock_qty,
               COALESCE((SELECT SUM(s.quantity) FROM sales s WHERE s.product_type_id = p.id), 0) as sold_qty,
               COALESCE((SELECT SUM(s.quantity) FROM sales s WHERE s.product_type_id = p.id AND s.sale_type = 'urgent_pickup'), 0) as urgent_sold_qty,
               COALESCE((SELECT SUM(s.total_amount) FROM sales s WHERE s.product_type_id = p.id), 0) as revenue,
               COALESCE((SELECT SUM(o.ordered_qty - o.delivered_qty) FROM orders o WHERE o.product_type_id = p.id AND o.status != 'completed'), 0) as pending_order_qty,
               (SELECT COUNT(*) FROM molds m WHERE m.product_type_id = p.id) as molds_count
        FROM product_types p
        ORDER BY revenue DESC
    """)
    product_demand = [dict(r) for r in cur.fetchall()]

    # 4. Missing Size Demand Aggregation
    cur.execute("""
        SELECT requested_size_name, requested_category,
               COUNT(*) as request_count,
               SUM(requested_qty) as total_requested_qty,
               AVG(estimated_unit_price) as avg_price,
               SUM(requested_qty * estimated_unit_price) as potential_revenue
        FROM missing_size_requests
        GROUP BY requested_size_name, requested_category
        ORDER BY potential_revenue DESC
    """)
    missing_demand = [dict(r) for r in cur.fetchall()]

    # 5. Molds needing repair / attention
    cur.execute("""
        SELECT m.id, m.mold_number, m.zone, m.status, m.consecutive_corner_defects, m.total_defects, m.last_defect_note,
               p.name as product_name
        FROM molds m
        JOIN product_types p ON p.id = m.product_type_id
        WHERE m.status = 'maintenance' OR m.consecutive_corner_defects >= 1
        ORDER BY m.consecutive_corner_defects DESC, m.total_defects DESC
    """)
    problem_molds = [dict(r) for r in cur.fetchall()]

    # 6. Active Raw Material Status
    cur.execute("""
        SELECT material_type, SUM(remaining_quantity) as rem_qty, MIN(unit) as unit
        FROM raw_material_batches
        WHERE status = 'active'
        GROUP BY material_type
    """)
    active_materials = {r["material_type"]: dict(r) for r in cur.fetchall()}

    # 7. Smart Advisor ("Pulni qayerga yo'naltirish kerak?")
    recommendations = []

    # Check cement stock
    cement_rem = active_materials.get("cement", {}).get("rem_qty", 0)
    if cement_rem < 5000:
        recommendations.append({
            "priority": "Yuqori (Shoshilinch)",
            "category": "Xomashyo (Sement)",
            "title": f"Sement zaxirasi kamaymoqda ({int(cement_rem)} kg qoldi)",
            "action": "Yangi 10–12 tonna Sement M450 partiyasini buyurtma qilish uchun ~13.8 mln so'm ajrating. Kunlik kolodets va ariq quyish sur'atida bu zaxira ~3-4 kunga yetadi.",
            "estimated_budget": 13800000,
        })

    # Check problem molds
    if problem_molds:
        urgent_molds = [m["mold_number"] for m in problem_molds if m["consecutive_corner_defects"] >= 2 or m["status"] == "maintenance"]
        if urgent_molds:
            recommendations.append({
                "priority": "Yuqori (Texnik)",
                "category": "Qolip Ta'miri (Remont)",
                "title": f"Burchagi ushlab qolayotgan qoliplar: {', '.join(urgent_molds)}",
                "action": "Ushbu qoliplarda ketma-ket burchak ushlab qolishi kuzatildi. Brak mahsulot va sement isrofini to'xtatish uchun svarka/shlifovka remontiga mablag' yo'naltiring.",
                "estimated_budget": 450000 * len(urgent_molds),
            })

    # Check high demand existing products
    if product_demand:
        top_prod = max(product_demand, key=lambda x: x["sold_qty"] + x["pending_order_qty"])
        recommendations.append({
            "priority": "O'rta (Kengaytirish)",
            "category": "Mavjud O'lcham Quvvatini Oshirish",
            "title": f"Eng yuqori talab: {top_prod['name']} (Sotildi: {top_prod['sold_qty']} dona, Navbatda: {top_prod['pending_order_qty']} dona)",
            "action": f"{top_prod['name']} ga shoshilinch va buyurtma talabi juda yuqori. Joy kichikligini hisobga olib, ustma-ust (2-qavatga) qo'yiladigan yana 3-4 ta yangi qolip yasattirish tez o'zini oqlaydi.",
            "estimated_budget": 6500000,
        })

    # Check missing sizes radar
    if missing_demand:
        top_missing = missing_demand[0]
        recommendations.append({
            "priority": "Strategik (Yangi Bozor)",
            "category": "Yangi O'lcham Qolipini Xarid Qilish",
            "title": f"Mavjud bo'lmagan '{top_missing['requested_size_name']}' ga {int(top_missing['total_requested_qty'])} dona talab ({int(top_missing['potential_revenue']):,} so'm yo'qotilgan savdo)",
            "action": f"Mijozlar '{top_missing['requested_size_name']}' o'lchamini ko'p so'rashmoqda. Foyda fondidan shu o'lcham uchun bitta siklli (yoki statsionar) qolip yasattirishga sarmoya kiriting.",
            "estimated_budget": 8000000,
        })

    conn.close()
    return {
        "financials": {
            "total_sales_revenue": sales_row["total_sales"],
            "cash_received": sales_row["cash_received"],
            "order_fulfillment_sales": sales_by_type.get("order_fulfillment", {"qty": 0, "amount": 0}),
            "urgent_pickup_sales": sales_by_type.get("urgent_pickup", {"qty": 0, "amount": 0}),
            "material_expenses": mat_cost,
            "labor_expenses": labor_cost,
            "repair_expenses": repair_cost,
            "total_expenses": total_expenses,
            "net_balance": net_balance,
        },
        "product_demand": product_demand,
        "missing_demand": missing_demand,
        "problem_molds": problem_molds,
        "active_materials": active_materials,
        "recommendations": recommendations,
    }


@app.post("/api/molds/reset-photo-layout")
def reset_molds_to_photo_layout():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM molds;")
    conn.commit()
    sync_real_media_layout(conn)
    conn.close()
    return {"status": "ok", "message": "38 ta qolip 20 ta rasm va 2 ta videodagi 1:1 joylashuvga tiklandi"}


@app.get("/api/media")
def list_workshop_media():
    """
    Returns all 20 photos and 2 videos from C:\\Users\\99890\\.gemini\\antigravity\\scratch\\beton-erp\\media
    with rich metadata, camera preset link, and mold inspection notes.
    """
    catalog = [
        {
            "filename": "VID_20261119_110105.mp4",
            "type": "video",
            "title": "1-Video: Meshalka orqasidan sex bo'ylab 360° panorama",
            "preset": "mixer_overview",
            "zone": "Butun Sex",
            "description": "Betonomeshalka orqasidan boshlab 1-qator (4 ta 30-lik), 7 ta 22-lik, 4-prujinali Vibrostol chuquri, 2-qavat ustma-ust 40-liklar va Kran-balka ko'rinishi."
        },
        {
            "filename": "VID_20261119_110157.mp4",
            "type": "video",
            "title": "2-Video: Sharqiy devordan barcha qatorlar va 2-qavat qoliplar obzori",
            "preset": "rows_east",
            "zone": "1–4 Qatorlar",
            "description": "Omborxona va meshalka oldidagi 4 ta qolipdan boshlab, markaziy X-karkasli 2-qavat qoliplar (#25, #26) va orqa shlakoblok devordagi Kran-balka zonasi."
        },
        {
            "filename": "IMG_20261119_110253.jpg",
            "type": "image",
            "title": "Meshalka, Sement Omborxonasi, Vibrostol chuquri va 1–2 qatorlar",
            "preset": "mixer_pit",
            "zone": "Meshalka & Vibrostol",
            "description": "O'ngda g'ishtli omborxona eshigi (Цемент М550+ qoplari), markazda Betonomeshalka va elektr shiti, chaproqda yer osti Vibrostol chuquri (#37 Plita) va 7 ta 22-lik qoliplar."
        },
        {
            "filename": "IMG_20261119_110347.jpg",
            "type": "image",
            "title": "Betonomeshalka, Elektr shiti va Omborxona kirishi (Yaqindan)",
            "preset": "mixer_pit",
            "zone": "Meshalka & Omborxona",
            "description": "Beton qorgich (grusha), devordagi ko'k elektr shiti, ombor ichidagi Цемент М550+ qoplari va chapda prujinali vibrostol chuquri."
        },
        {
            "filename": "IMG_20261119_110357.jpg",
            "type": "image",
            "title": "Vibrostol chuquri, 1-Tokcha va G'arbiy Paxsa devor",
            "preset": "mixer_pit",
            "zone": "Vibrostol & 1-Tokcha",
            "description": "Meshalka, yer osti vibrostoldagi beton plita (#37), g'arbiy paxsa devordagi 1-tokcha, ko'k ustun va 2-qator qoliplari."
        },
        {
            "filename": "IMG_20261119_110407.jpg",
            "type": "image",
            "title": "G'arbiy Paxsa devor (1-Tokcha va 2-Tokcha) hamda 2–3 qator qoliplari",
            "preset": "west_wall",
            "zone": "2–3 Qatorlar (G'arb)",
            "description": "Paxsa devordagi 2 ta tokcha, ko'k va oq-qora temir ustunlar hamda ularning oldidagi 2-qator va 3-qator 30-lik ariq qoliplari."
        },
        {
            "filename": "IMG_20261119_110431.jpg",
            "type": "image",
            "title": "G'arbiy A-ramali Kran-balka oyog'i va 2-qavatdagi 50-lik qoliplar",
            "preset": "crane_zone",
            "zone": "4-Qator (Kran-balka)",
            "description": "Tunuka soyabon ostidagi A-ramali kran tayanchi, yog'och brusoklar ustiga 2-qavat qilib qo'yilgan #35 (50-lik) temir qolip va tayyor 50-lik beton ariqlar."
        },
        {
            "filename": "IMG_20261119_110455.jpg",
            "type": "image",
            "title": "Sharqiy A-ramali Kran-balka, Tal ko'targich ilgagi va Kichik ombor",
            "preset": "crane_zone",
            "zone": "4-Qator (Kran-balka)",
            "description": "To'q sariq va ko'k A-ramali kran, tepada chig'ir (lebyodka/tal), qora traversaga ilingan #30 (50-lik) qolip, kichik paxsa xona va sement qoplar uyumi."
        },
        {
            "filename": "IMG_20261119_110507.jpg",
            "type": "image",
            "title": "Temir kirish eshigi, 2-qavat 40-lik qoliplar va Sement qoplar yopilgan qator",
            "preset": "entrance_stacked",
            "zone": "3–4 Qatorlar (Sharq)",
            "description": "Chapda temir kirish eshigi va YASIN/SHAFFOF sement qoplari ustiga 2-qavat qilib qo'yilgan X-karkasli 40-lik qoliplar (#25, #26), o'rtada usti qoplar bilan yopilgan #31-#34 qoliplar."
        },
        {
            "filename": "IMG_20261119_110520.jpg",
            "type": "image",
            "title": "Temir kirish eshigi, 7 ta 22-lik ariqlar va 2-qavat 40-lik qoliplar",
            "preset": "entrance_stacked",
            "zone": "2–3 Qatorlar (Sharq)",
            "description": "Chapda jigarang tunuka panel va 7 ta 22-lik ariqlar (#05-#11), markazda temir eshik, o'ngda 2-qavat ustma-ust 40-lik qoliplar (#25, #26)."
        },
        {
            "filename": "IMG_20261119_110530.jpg",
            "type": "image",
            "title": "Betonomeshalka ustidan 1-qator (4 ta 30-lik) va 2-qator (7 ta 22-lik) ko'rinishi",
            "preset": "mixer_overview",
            "zone": "1–2 Qatorlar",
            "description": "Old planda betonomeshalka og'zi, uning orqasida 4 ta 30-lik qolip (#01-#04), o'ngroqda 7 ta 22-lik qolip (#05-#11) va 2-qavat 40-lik qoliplar."
        },
        {
            "filename": "IMG_20261119_110648.jpg",
            "type": "image",
            "title": "2-Qator #12 va #13 (30-lik) qoliplar: Rezbali tortqichlar va '2' belgisi",
            "preset": "rows_west",
            "zone": "2-Qator (G'arb)",
            "description": "To'nkarilgan trapetsiya qoliplarning armatura rezbali qisqich dastaklari, #12 qolip ustidagi '2' shaklidagi beton izi va o'ngda temir profil rels."
        },
        {
            "filename": "IMG_20261119_110654.jpg",
            "type": "image",
            "title": "#14 Qolipning chap yon borti ochilgan holati hamda #12 va #13 qoliplar",
            "preset": "rows_west",
            "zone": "2–3 Qatorlar (G'arb)",
            "description": "Chapda #14 (22-lik) qolipning yon temir borti yechib qo'yilgan (ichidagi beton ko'rinib turibdi), o'rtada #13 va o'ngda #12 (30-lik) qoliplar."
        },
        {
            "filename": "IMG_20261119_110707.jpg",
            "type": "image",
            "title": "Qoliplarning ichki X-simon po'lat karkasi va orqa fondagi 2-qavat 50-liklar",
            "preset": "rows_west",
            "zone": "2–4 Qatorlar",
            "description": "Pastki rakursdan #12, #13 (ichki X-simon karkaslari), yon borti ochilgan #14 qolip va orqa fonda 2-qavatda turgan 3 ta 50-lik katta qoliplar."
        },
        {
            "filename": "IMG_20261119_110722.jpg",
            "type": "image",
            "title": "Qolip #05: Ichki temir bortga svarka bilan yozilgan '5' raqami va betondagi muhri",
            "preset": "rows_east",
            "zone": "Qolip #05 (QC Diagnostika)",
            "description": "Qolipning ichki temir devoriga svarka bilan '5' raqami yozilgan bo'lib, har quyilganda beton yoniga '5' raqami muhr bo'lib tushadi! Burchagida beton yopishgan joyi ko'ringan."
        },
        {
            "filename": "IMG_20261119_110758.jpg",
            "type": "image",
            "title": "Qolip #14: Ichki bortdagi svarka '14' raqami va betonga tushgan teskari '14' muhri",
            "preset": "rows_west",
            "zone": "Qolip #14 (QC Diagnostika)",
            "description": "Qolip #14 ning ochilgan temir bortida svarka bilan yozilgan '14' raqami va yangi quyilgan beton devorida uning '14' izi — qaysi qolipdan chiqqanini 100% aniqlash tizimi!"
        },
        {
            "filename": "IMG_20261119_110821.jpg",
            "type": "image",
            "title": "1-Qator #03 va #04 (30-lik) qoliplar: Yon bortlari bo'shatilib yechishga tayyorlangan",
            "preset": "mixer_overview",
            "zone": "1-Qator (#03, #04)",
            "description": "Sharqiy devordagi jigarang tunuka panel yonida turgan #03 va #04 qoliplarning rezbali qisqichlari yechilib, yon temir bortlari ikki tomonga ochilgan."
        },
        {
            "filename": "IMG_20261119_110850.jpg",
            "type": "image",
            "title": "Sharqiy devor bo'ylab umumiy panorama: O'ralgan gilam, 2-qavat qoliplar va Kran",
            "preset": "rows_east",
            "zone": "Sharqiy yo'lak va 1–4 Qatorlar",
            "description": "Chapda o'ralgan gilam, YASIN/SHAFFOF qoplari, temir profil rels; o'ngda 1-qator, 2-qator, 3-qatordagi 2-qavat X-karkasli #25 qolip va orqada Kran-balka."
        },
        {
            "filename": "IMG_20261119_110913.jpg",
            "type": "image",
            "title": "G'arbiy devor bo'ylab umumiy panorama: Prujinali Vibrostol va 2–4 Qatorlar",
            "preset": "rows_west",
            "zone": "G'arbiy yo'lak va Vibrostol",
            "description": "Old chapda 4-prujinali yer osti Vibrostol chuquri, o'ngda paxsa devor va temir profil rels, oldinda #12-#14 qoliplar va orqada 2-qavat 50-liklar."
        },
        {
            "filename": "IMG_20261119_111136.jpg",
            "type": "image",
            "title": "Qolip tagiga qo'yiladigan beton taglik tosh (Tayanch brusok)",
            "preset": "rows_east",
            "zone": "2-Qator (#07 tagligi)",
            "description": "Qoliplar shag'al yerda tekis turishi va oson ochilishi uchun ularning tagiga qo'yilgan maxsus beton tayanch tosh."
        },
        {
            "filename": "IMG_20261119_111150.jpg",
            "type": "image",
            "title": "2-Qatordagi 7 ta 22-lik ariq qoliplari (#05–#11): Sim quloqchalar va qisqichlar",
            "preset": "rows_east",
            "zone": "2-Qator (7 ta 22-lik)",
            "description": "Ketma-ket terilgan 7 ta 22-lik qolip: har birining tepasida U-simon armatura sim quloqchalari, o'ng chetida rezbali dastaklar va #06 ustida siniq beton plita parchasi."
        },
        {
            "filename": "IMG_20261119_111247.jpg",
            "type": "image",
            "title": "4 ta Katta Prujinali Yer Osti Vibrostol Chuquri va Plita Qolipi (#37)",
            "preset": "mixer_pit",
            "zone": "Vibrostol Chuquri",
            "description": "Meshalka yonida yer ostiga o'rnatilgan 4 ta kuchli po'lat prujinali vibrostol va uning ustida quyilgan tekis to'rtburchak beton plita qolipi (#37)."
        },
    ]
    return catalog

