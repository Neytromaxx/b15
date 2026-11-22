# b15 — Beton Ariq (Lotok) va Kolodets Ishlab Chiqarish Korxonasi ERP + MES + 3D Digital Twin

Tayyor beton ariqlar (`22-lik`, `30-lik`, `40-lik`, `50-lik`) hamda kanalizatsiya quduqlari (`Kolodets Ø118/104 sm`) ishlab chiqarish korxonasining barcha jarayonlarini raqamlashtirish va 3D makonda boshqarish tizimi (**Monorepo**).

## Arxitektura (Monorepo)

* **`backend/`** — **Python FastAPI + SQLite** (`database.py`, `main.py`):
  * Mahsulot o'lchamlari va beton hajmi ($m^3$) kalkulyatori (`22, 30, 40, 50-lik` trapetsiya ariqlar va `Ø118/104` siklli kolodets).
  * Qoliplar reestri, 3D koordinatalari (`X, Z, Qavat/Ustma-ust`), quyish sikllari va sifat nazorati (ketma-ket burchak ushlab qolishini aniqlash va avtomatik remontga chiqarish).
  * Universal 3D Maydon elementlari (`workshop_elements`: `6.0 m` ikki yondagi Tal relslari, A-ramali Tal ko'targich, har qatorda 2 tadan yotqiziladigan Taglik Stoykalar, Betonomeshalka, Vibrator/Vibrostol).
  * Kunlik ish logi va `Open-Meteo API` orqali hudud ob-havosini avtomatik qayd etish.
  * Buyurtmalar, shoshilinch (joyida) savdolar va korxonada mavjud bo'lmagan (so'ralgan) o'lchamlar radari.
  * Xomashyo partiyalari (`Sement`, `Shag'al`, `Sim` — qachon keldi, qachon tugadi va shu partiyadan nechta mahsulot chiqdi).
  * Moliya va **"Pulni qayerga yo'naltirish kerak?" (Smart Advisor)** tahlil moduli.
* **`frontend/`** — **Vue 3 (Composition API, Pinia) + Three.js (WebGL) + TailwindCSS**:
  * **1:1 Matematik 3D Maydon Konstruktori:** Uzunligi `16.5 m` (eshikdan oxirgi shlakoblokli devorgacha), eshik tomoni `7.0 m`, oxiri `8.2 m` bo'lgan trapetsiya maydon va orasi `6.0 m` bo'lgan ikki yondagi Tal relslari.
  * **3D Chaqirish va Sudrab Joylash (`Spawn & Direct 3D Drag`):** Elementlarni 3D makonga chaqirib sichqoncha bilan sudrab istalgan joyga qo'yish, `R` bilan burish, `Q` bilan 2-qavatga (ustma-ust) chiqarish yoki qator qilib matematik terish.

---

## Ishga Tushirish

### 1. Backend (`FastAPI` — `8000`-port)
```bash
cd backend
pip install fastapi uvicorn pydantic
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend (`Vue 3 + Vite + Three.js` — `5173`-port)
```bash
cd frontend
npm install
npm run dev
```

Brauzerda **http://localhost:5173** manzilini oching.
