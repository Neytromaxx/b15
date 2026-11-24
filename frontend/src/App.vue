<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useErpStore } from './stores/erpStore'
import Workshop3D from './components/Workshop3D.vue'
import Product3DPreview from './components/Product3DPreview.vue'

const store = useErpStore()
const activeTab = ref('workshop')
const toastMessage = ref('')
const topCollapsed = ref(true) // Collapses big header & KPI cards into a slim 1-row bar so 3D scene gets maximum screen space!

function showToast(msg) {
  toastMessage.value = msg
  setTimeout(() => {
    if (toastMessage.value === msg) toastMessage.value = ''
  }, 4000)
}

function formatMoney(val) {
  return Number(val || 0).toLocaleString('uz-UZ') + " so'm"
}

// ---------------- 1. MOLD PASSPORT, POSITION & REPAIR ----------------
const posForm = ref({
  zone: '',
  pos_x: 0,
  pos_z: 0,
  stack_tier: 1,
  rotation_deg: 0,
  notes: '',
})

const repairForm = ref({
  issue_description: 'Burchagi doimiy ushlab qolyapti',
  repair_action: 'Burchak choklari svarka qilindi va ichki devori shlifovka qilindi',
  repair_cost: 350000,
  performed_by: 'Usta Mahmud',
})

const newMoldModal = ref(false)
const newMoldForm = ref({
  mold_number: '#27 (A30)',
  product_type_id: 2,
  zone: 'Markaziy Qator (2-Zona)',
  pos_x: -0.5,
  pos_z: -3.2,
  stack_tier: 3,
  rotation_deg: 0,
  status: 'empty',
  notes: '16-qolip ustiga (3-qavat)',
})

watch(
  () => store.selectedMold,
  (m) => {
    if (m) {
      posForm.value = {
        zone: m.zone,
        pos_x: m.pos_x,
        pos_z: m.pos_z,
        stack_tier: m.stack_tier || 1,
        rotation_deg: m.rotation_deg || 0,
        notes: m.notes || '',
      }
    }
  },
  { immediate: true }
)

async function saveMoldPosition() {
  if (!store.selectedMold) return
  await store.updateMoldPosition(store.selectedMold.id, posForm.value)
  showToast(`${store.selectedMold.mold_number} joylashuvi va qavati yangilandi!`)
}

async function submitMoldRepair() {
  if (!store.selectedMold) return
  await store.repairMold(store.selectedMold.id, repairForm.value)
  showToast(`${store.selectedMold.mold_number} ta'mirlandi va 'Bo'sh' holatga o'tkazildi!`)
}

async function submitNewMold() {
  await store.createMold(newMoldForm.value)
  newMoldModal.value = false
  showToast("Yangi qolip sex xaritasiga qo'shildi!")
}

// ---------------- 2. DAILY PRODUCTION: DEMOLD, CAST & CYCLIC KOLODETS ----------------
const selectedForDemold = ref({}) // moldId -> { checked, quality_status, defect_location }
const selectedForCast = ref([]) // array of moldIds

const cyclicForm = ref({
  mold_id: null,
  quantity: 20,
  custom_height_cm: 60,
  clean_qty: 19,
  corner_stuck_qty: 1,
  cracked_qty: 0,
  defect_location: 'Pastki qirrasida 1 donasida biroz yopishish bo\'ldi',
  notes: 'Kun davomida bitta qolipda ketma-ket quyib yechildi',
})

const pouredOrReadyMolds = computed(() =>
  store.molds.filter((m) => m.casting_mode === 'stationary' && (m.status === 'poured' || m.status === 'ready_demold'))
)

const emptyStationaryMolds = computed(() =>
  store.molds.filter((m) => m.casting_mode === 'stationary' && m.status === 'empty')
)

const cyclicMolds = computed(() =>
  store.molds.filter((m) => m.casting_mode === 'cyclic' || m.product_category === 'kolodets')
)

watch(
  () => store.molds,
  (list) => {
    const map = {}
    for (const m of list) {
      if (m.status === 'poured' || m.status === 'ready_demold') {
        map[m.id] = selectedForDemold.value[m.id] || {
          checked: m.status === 'ready_demold',
          quality_status: 'clean',
          defect_location: '',
        }
      }
    }
    selectedForDemold.value = map
    if (cyclicMolds.value.length > 0 && !cyclicForm.value.mold_id) {
      cyclicForm.value.mold_id = cyclicMolds.value[0].id
    }
  },
  { immediate: true }
)

async function submitDemoldBatch() {
  const items = []
  for (const [mId, data] of Object.entries(selectedForDemold.value)) {
    if (data.checked) {
      items.push({
        mold_id: Number(mId),
        quality_status: data.quality_status,
        defect_location: data.defect_location,
        notes: data.defect_location,
      })
    }
  }
  if (items.length === 0) {
    showToast('Qolipdan yechish uchun kamida 1 ta qolipni belgilang!')
    return
  }
  const res = await store.demoldBatch({ items })
  if (res.auto_maintenance_molds && res.auto_maintenance_molds.length > 0) {
    showToast(`Yechildi: ${res.demolded_count} ta. DIQQAT: ${res.auto_maintenance_molds.join(', ')} remontga tushdi!`)
  } else {
    showToast(`${res.demolded_count} ta mahsulot qolipdan chiqarildi va omborga qo'shildi!`)
  }
}

async function submitCastBatch() {
  if (selectedForCast.value.length === 0) {
    showToast("Quyish uchun bo'sh qoliplardan tanlang!")
    return
  }
  const res = await store.castBatch({
    mold_ids: selectedForCast.value,
    notes: 'Kunlik rejali quyish',
  })
  selectedForCast.value = []
  showToast(
    `${res.cast_count} ta qolip quyildi! Usta haqi: ${formatMoney(res.labor_cost_added)}, Sement: -${res.cement_used_kg} kg`
  )
}

async function submitCyclicCast() {
  if (!cyclicForm.value.mold_id) return
  const res = await store.cyclicCast(cyclicForm.value)
  showToast(
    `Kolodets qolipida ${res.cyclic_cast_qty} dona quyildi! Omborga +${res.usable_added_to_stock} dona, Sement: -${res.cement_used_kg} kg`
  )
}

// ---------------- 2B. UNNUMBERED DAILY SIZE BATCH & WORKER PAYROLL (SHUHRATJON, AHLIDDIN, KADIROV) ----------------
const editingSizeBatchId = ref(null)
const showLegacyMoldProduction = ref(false)

const sizeBatchForm = ref({
  work_date: new Date().toISOString().slice(0, 10),
  quantities: {
    A50: 1,
    A40: 5,
    A30: 0,
    A22: 12,
    K104: 7,
    PL80: 0,
  },
  uniform_wage: 180000,
  workers: [
    { name: 'Shuhratjon', amount: 180000, active: true },
    { name: 'Ahliddin', amount: 180000, active: true },
    { name: 'Kadirov', amount: 180000, active: true },
  ],
  new_worker_name: '',
  notes: '',
})

const sizeCatalogMeta = [
  { code: 'A50', shortLabel: '50-lik Ariq', badge: 'bg-purple-500/20 text-purple-300 border-purple-500/40' },
  { code: 'A40', shortLabel: '40-lik Ariq', badge: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40' },
  { code: 'A30', shortLabel: '30-lik Ariq', badge: 'bg-blue-500/20 text-blue-300 border-blue-500/40' },
  { code: 'A22', shortLabel: '22-lik Ariq', badge: 'bg-sky-500/20 text-sky-300 border-sky-500/40' },
  { code: 'K104', shortLabel: 'Kolodets Ø118/104', badge: 'bg-amber-500/20 text-amber-300 border-amber-500/40' },
  { code: 'PL80', shortLabel: 'Vibrostol Plita', badge: 'bg-teal-500/20 text-teal-300 border-teal-500/40' },
]

function applyUniformWageToAll() {
  const w = Number(sizeBatchForm.value.uniform_wage || 0)
  for (const worker of sizeBatchForm.value.workers) {
    if (worker.active) {
      worker.amount = w
    }
  }
}

function addNewWorkerToForm() {
  const nm = (sizeBatchForm.value.new_worker_name || '').trim()
  if (!nm) return
  if (!sizeBatchForm.value.workers.some((w) => w.name.toLowerCase() === nm.toLowerCase())) {
    sizeBatchForm.value.workers.push({
      name: nm,
      amount: Number(sizeBatchForm.value.uniform_wage || 170000),
      active: true,
    })
  }
  sizeBatchForm.value.new_worker_name = ''
}

const sizeBatchPreview = computed(() => {
  let totalQty = 0
  let totalCem = 0
  let totalGrv = 0
  let totalWir = 0
  let totalVol = 0

  for (const meta of sizeCatalogMeta) {
    const q = Math.max(0, Number(sizeBatchForm.value.quantities[meta.code] || 0))
    if (q > 0) {
      totalQty += q
      const prod = store.products.find((p) => p.code === meta.code)
      if (prod) {
        totalCem += Number(prod.cement_norm_kg || 0) * q
        totalGrv += Number(prod.gravel_norm_kg || 0) * q
        totalWir += Number(prod.wire_norm_kg || 0) * q
        totalVol += Number(prod.concrete_volume_m3 || 0) * q
      }
    }
  }

  const activeWorkers = sizeBatchForm.value.workers.filter((w) => w.active && w.name.trim())
  const totalLabor = activeWorkers.reduce((acc, w) => acc + Number(w.amount || 0), 0)

  return {
    totalQty,
    activeWorkersCount: activeWorkers.length,
    totalLabor,
    totalCem: totalCem.toFixed(1),
    totalGrv: totalGrv.toFixed(1),
    fineGrv: (totalGrv * 0.75).toFixed(1),
    coarseGrv: (totalGrv * 0.25).toFixed(1),
    totalWir: totalWir.toFixed(2),
    totalVol: totalVol.toFixed(3),
  }
})

function loadSizeBatchForEdit(batch) {
  editingSizeBatchId.value = batch.id
  const qMap = { A50: 0, A40: 0, A30: 0, A22: 0, K104: 0, PL80: 0 }
  for (const it of batch.items || []) {
    if (it.code in qMap) {
      qMap[it.code] = Number(it.quantity || 0)
    }
  }

  const existingWorkers = (batch.workers || []).map((w) => ({
    name: w.name,
    amount: Number(w.amount || 0),
    active: true,
  }))
  for (const defaultName of ['Shuhratjon', 'Ahliddin', 'Kadirov']) {
    if (!existingWorkers.some((w) => w.name.toLowerCase() === defaultName.toLowerCase())) {
      existingWorkers.push({
        name: defaultName,
        amount: Number(batch.per_worker_wage || 170000),
        active: false,
      })
    }
  }

  sizeBatchForm.value = {
    work_date: batch.work_date || new Date().toISOString().slice(0, 10),
    quantities: qMap,
    uniform_wage: Number(batch.per_worker_wage || 170000),
    workers: existingWorkers,
    new_worker_name: '',
    notes: batch.notes || '',
  }
}

function resetSizeBatchForm() {
  editingSizeBatchId.value = null
  sizeBatchForm.value = {
    work_date: new Date().toISOString().slice(0, 10),
    quantities: { A50: 0, A40: 0, A30: 0, A22: 0, K104: 0, PL80: 0 },
    uniform_wage: 170000,
    workers: [
      { name: 'Shuhratjon', amount: 170000, active: true },
      { name: 'Ahliddin', amount: 170000, active: true },
      { name: 'Kadirov', amount: 170000, active: true },
    ],
    new_worker_name: '',
    notes: '',
  }
}

async function submitSizeBatch() {
  const items = sizeCatalogMeta.map((m) => ({
    code: m.code,
    quantity: Math.max(0, Number(sizeBatchForm.value.quantities[m.code] || 0)),
  }))
  const workers = sizeBatchForm.value.workers
    .filter((w) => w.active && w.name.trim())
    .map((w) => ({
      name: w.name.trim(),
      amount: Number(w.amount || 0),
    }))

  const payload = {
    work_date: sizeBatchForm.value.work_date,
    items,
    workers,
    notes: sizeBatchForm.value.notes,
  }

  if (editingSizeBatchId.value) {
    const res = await store.updateSizeBatch(editingSizeBatchId.value, payload)
    showToast(
      `Kunlik yozuv (#${editingSizeBatchId.value}) yangilandi! Jami: ${res.total_qty} dona, Ish haqi: ${formatMoney(res.total_labor_cost)}`
    )
    editingSizeBatchId.value = null
  } else {
    const res = await store.createSizeBatch(payload)
    showToast(
      `Saqlandi! Jami: ${res.total_qty} dona quyildi, ${workers.length} ta ishchiga jami ${formatMoney(res.total_labor_cost)} yozildi!`
    )
  }
}

async function handleDeleteSizeBatch(batchId) {
  await store.deleteSizeBatch(batchId)
  if (editingSizeBatchId.value === batchId) {
    editingSizeBatchId.value = null
  }
  showToast("Kunlik quyish yozuvi o'chirildi.")
}

// ---------------- 3. PRODUCTS & 3D CATALOG ----------------
const activePreviewProduct = ref(null)
watch(
  () => store.products,
  (prods) => {
    if (prods.length > 0 && !activePreviewProduct.value) {
      activePreviewProduct.value = prods.find((p) => p.code === 'A30') || prods[0]
    } else if (activePreviewProduct.value) {
      const updated = prods.find((p) => p.id === activePreviewProduct.value.id)
      if (updated) activePreviewProduct.value = updated
    }
  },
  { immediate: true }
)

const newProductModal = ref(false)
const newProductForm = ref({
  code: 'A60',
  name: '60-lik Magistral Beton Ariq',
  category: 'ariq',
  casting_mode: 'stationary',
  inner_bottom_cm: 30,
  inner_side_cm: 45,
  inner_top_cm: 60,
  wall_thickness_cm: 8,
  length_cm: 150,
  outer_diameter_cm: 0,
  inner_diameter_cm: 0,
  max_height_cm: 60,
  default_height_cm: 60,
  cement_norm_kg: 46,
  gravel_norm_kg: 210,
  wire_norm_kg: 3.5,
  casting_labor_cost: 35000,
  selling_price: 240000,
  stock_qty: 0,
  color_hex: '#ec4899',
  description: 'Katta suv kanallari uchun yangi o\'lcham',
})

async function submitNewProduct() {
  await store.createProduct(newProductForm.value)
  newProductModal.value = false
  showToast("Yangi mahsulot o'lchami katalogga qo'shildi!")
}

// ---------------- 4. ORDERS, URGENT SALES & MISSING SIZES ----------------
const orderForm = ref({
  customer_name: '',
  customer_phone: '+998 ',
  product_type_id: 2,
  ordered_qty: 20,
  custom_height_cm: 60,
  unit_price: 95000,
  advance_paid: 1000000,
  due_date: new Date().toISOString().slice(0, 10),
  notes: '',
})

const saleForm = ref({
  sale_type: 'urgent_pickup', // 'urgent_pickup' or 'order_fulfillment'
  order_id: null,
  customer_name: '',
  customer_phone: '+998 ',
  product_type_id: 2,
  quantity: 10,
  unit_price: 95000,
  paid_amount: 950000,
  payment_method: 'Naqd',
  notes: '',
})

const missingSizeForm = ref({
  customer_name: '',
  customer_phone: '+998 ',
  requested_category: 'ariq',
  requested_size_name: '',
  dimensions_details: '',
  requested_qty: 20,
  estimated_unit_price: 200000,
  notes: '',
})

function onOrderProductChange() {
  const p = store.products.find((x) => x.id === Number(orderForm.value.product_type_id))
  if (p) orderForm.value.unit_price = p.selling_price
}

function onSaleProductChange() {
  const p = store.products.find((x) => x.id === Number(saleForm.value.product_type_id))
  if (p) {
    saleForm.value.unit_price = p.selling_price
    saleForm.value.paid_amount = p.selling_price * saleForm.value.quantity
  }
}

function onSaleOrderSelect() {
  const ord = store.orders.find((o) => o.id === Number(saleForm.value.order_id))
  if (ord) {
    saleForm.value.customer_name = ord.customer_name
    saleForm.value.customer_phone = ord.customer_phone
    saleForm.value.product_type_id = ord.product_type_id
    saleForm.value.quantity = Math.max(ord.ordered_qty - ord.delivered_qty, 1)
    saleForm.value.unit_price = ord.unit_price
    saleForm.value.paid_amount = saleForm.value.quantity * ord.unit_price
  }
}

async function submitOrder() {
  if (!orderForm.value.customer_name) return
  await store.createOrder(orderForm.value)
  orderForm.value.customer_name = ''
  orderForm.value.notes = ''
  showToast("Yangi buyurtma ro'yxatga olindi!")
}

async function submitSale() {
  if (!saleForm.value.customer_name) return
  await store.createSale(saleForm.value)
  saleForm.value.customer_name = ''
  saleForm.value.notes = ''
  showToast('Sotuv muvaffaqiyatli qayd etildi va ombor yangilandi!')
}

async function submitMissingSize() {
  if (!missingSizeForm.value.requested_size_name) return
  await store.createMissingSize(missingSizeForm.value)
  missingSizeForm.value.customer_name = ''
  missingSizeForm.value.requested_size_name = ''
  missingSizeForm.value.dimensions_details = ''
  missingSizeForm.value.notes = ''
  showToast("So'ralgan (mavjud bo'lmagan) o'lcham talab radariga yozildi!")
}

// ---------------- 5. RAW MATERIALS (SEMENT, SHAG'AL, SIM) ----------------
const matForm = ref({
  material_type: 'cement',
  batch_code: 'SEM-03',
  material_name: 'Sement M450 (Yangi partiya)',
  supplier: 'Ohangaron Sement Diler',
  arrived_date: new Date().toISOString().slice(0, 10),
  initial_quantity: 10000,
  unit: 'kg',
  unit_price: 1150,
  notes: '',
})

async function submitMaterialBatch() {
  await store.createMaterialBatch(matForm.value)
  showToast("Yangi xomashyo partiyasi omborga kirim qilindi!")
}

async function markDepleted(batch) {
  const today = new Date().toISOString().slice(0, 10)
  await store.depleteMaterialBatch(batch.id, {
    depleted_date: today,
    notes: `${today} sanasida to'liq tugadi`,
  })
  showToast(`${batch.batch_code} partiyasi 'Tugadi' deb belgilandi!`)
}

// ---------------- 6. SETTINGS MODAL ----------------
const settingsModal = ref(false)
const settingsForm = ref({
  company_name: '',
  region_id: 'tashkent',
  workshop_width_m: 14,
  workshop_length_m: 10,
})

function openSettings() {
  settingsForm.value = {
    company_name: store.settings.company_name,
    region_id: store.settings.region_id,
    workshop_width_m: store.settings.workshop_width_m,
    workshop_length_m: store.settings.workshop_length_m,
  }
  settingsModal.value = true
}

async function saveSettings() {
  await store.updateSettings(settingsForm.value)
  settingsModal.value = false
  showToast('Sozlamalar va ob-havo hududi yangilandi!')
}

onMounted(() => {
  store.fetchAll()
})
</script>

<template>
  <div class="min-h-screen bg-slate-950 text-slate-100 flex flex-col">
    <!-- Toast Notification -->
    <div
      v-if="toastMessage"
      class="fixed bottom-5 right-5 z-50 bg-blue-600 text-white px-5 py-3 rounded-xl shadow-2xl border border-blue-400 font-medium text-sm flex items-center gap-2"
    >
      <span>✓</span>
      <span>{{ toastMessage }}</span>
    </div>

    <!-- TOP HEADER BAR (COLLAPSIBLE INTO SLIM 1-LINE BAR!) -->
    <header class="sticky top-0 z-30 bg-slate-900/95 backdrop-blur-md border-b border-slate-800 px-3 lg:px-6" :class="topCollapsed ? 'py-1.5' : 'py-3'">
      <!-- SLIM COLLAPSED MODE (1 compact row!) -->
      <div v-if="topCollapsed" class="max-w-[1700px] mx-auto flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <div class="w-7 h-7 rounded-lg bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center font-black text-xs">
            3D
          </div>
          <span class="text-sm font-bold text-white hidden sm:inline">{{ store.settings.company_name }}</span>

          <!-- Compact Single-Row Navigation Tabs -->
          <div class="flex flex-wrap items-center gap-1 ml-1">
            <button
              v-for="tab in [
                { id: 'workshop', label: '🏭 1. 3D Sex' },
                { id: 'production', label: '⚡ 2. Kunlik Ish' },
                { id: 'catalog', label: '📐 3. Katalog' },
                { id: 'sales', label: '🛒 4. Buyurtma & Savdo' },
                { id: 'materials', label: '🧱 5. Xomashyo' },
                { id: 'analytics', label: '📊 6. Moliya' },
              ]"
              :key="tab.id"
              @click="activeTab = tab.id"
              :class="
                activeTab === tab.id
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-800/90 text-slate-300 hover:bg-slate-700'
              "
              class="px-2.5 py-1 rounded-lg text-[11px] font-semibold transition cursor-pointer"
            >
              {{ tab.label }}
            </button>
          </div>
        </div>

        <div class="flex items-center gap-2 text-xs">
          <div
            v-if="store.weather"
            class="hidden md:flex items-center gap-1.5 bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1 text-[11px]"
          >
            <span class="font-bold text-amber-400">{{ store.settings.region_name }}:</span>
            <span class="font-bold text-white">{{ store.weather.temp_current }}°C</span>
            <span class="text-sky-300">{{ store.weather.condition }}</span>
          </div>
          <button
            @click="openSettings"
            class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-[11px] font-semibold text-slate-200 cursor-pointer"
          >
            ⚙️ Sozlamalar
          </button>
          <button
            @click="topCollapsed = false"
            class="px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500 hover:text-slate-950 border border-amber-500/40 text-[11px] font-bold text-amber-300 transition cursor-pointer"
            title="Tepa qism va KPI kartalarni to'liq yoyib ko'rsatish"
          >
            ▼ Tepani Yoyish
          </button>
        </div>
      </div>

      <!-- EXPANDED HEADER MODE -->
      <div v-else>
        <div class="max-w-[1700px] mx-auto flex flex-wrap items-center justify-between gap-4">
          <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center font-black text-base shadow-lg shadow-blue-500/20">
              3D
            </div>
            <div>
              <h1 class="text-base font-bold tracking-tight text-white flex items-center gap-2">
                {{ store.settings.company_name }}
                <span class="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-300 border border-blue-500/30 font-medium">
                  MES + ERP + Three.js
                </span>
              </h1>
              <p class="text-xs text-slate-400">
                Beton ariqlar (22, 30, 40, 50-lik) va Kolodets (Ø118/104, h≤60sm) raqamli boshqaruv tizimi
              </p>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2.5">
            <div
              v-if="store.weather"
              class="flex items-center gap-3 bg-slate-950/90 border border-slate-800 rounded-xl px-3 py-1.5 text-xs"
            >
              <div>
                <div class="flex items-center gap-2">
                  <span class="font-bold text-amber-400">{{ store.settings.region_name }}:</span>
                  <span class="font-bold text-white text-sm">{{ store.weather.temp_current }}°C</span>
                  <span class="text-slate-400">(Kun: {{ store.weather.temp_min }}°..{{ store.weather.temp_max }}°C)</span>
                  <span class="px-2 py-0.5 rounded bg-slate-800 text-sky-300 font-medium">{{ store.weather.condition }}</span>
                </div>
                <div class="text-[11px] text-slate-400 mt-0.5">
                  Namlik: {{ store.weather.humidity }}% • {{ store.weather.curing_advice }}
                </div>
              </div>
            </div>

            <button
              @click="openSettings"
              class="px-3 py-2 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-xs font-semibold text-slate-200 transition cursor-pointer"
            >
              ⚙️ Hudud va Sex Sozlamalari
            </button>
            <button
              @click="topCollapsed = true"
              class="px-3 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold transition cursor-pointer"
            >
              ▲ Tepani Yig'ish (Collapse)
            </button>
          </div>
        </div>

        <!-- Navigation Tabs -->
        <div class="max-w-[1700px] mx-auto mt-2.5 flex flex-wrap items-center gap-1.5 border-t border-slate-800/80 pt-2">
          <button
            v-for="tab in [
              { id: 'workshop', label: '🏭 1. 3D Sex va Qoliplar (Ustma-ust)' },
              { id: 'production', label: '⚡ 2. Kunlik Ish: Quyish va Yechish' },
              { id: 'catalog', label: '📐 3. O\'lchamlar va 3D Katalog' },
              { id: 'sales', label: '🛒 4. Buyurtmalar, Shoshilinch Savdo va Talab' },
              { id: 'materials', label: '🧱 5. Xomashyo (Sement, Shag\'al, Sim)' },
              { id: 'analytics', label: '📊 6. Moliya va Pulni Yo\'naltirish (Advisor)' },
            ]"
            :key="tab.id"
            @click="activeTab = tab.id"
            :class="
              activeTab === tab.id
                ? 'bg-blue-600 text-white shadow-lg shadow-blue-600/25'
                : 'bg-slate-900 text-slate-300 hover:bg-slate-800 border border-slate-800'
            "
            class="px-3.5 py-1.5 rounded-xl text-xs font-semibold transition cursor-pointer"
          >
            {{ tab.label }}
          </button>
        </div>
      </div>
    </header>

    <!-- MAIN CONTENT CONTAINER -->
    <main class="flex-1 max-w-[1700px] w-full mx-auto px-3 lg:px-6" :class="topCollapsed ? 'py-2.5' : 'py-5'">
      <!-- ==================== TAB 1: 3D WORKSHOP & MOLDS ==================== -->
      <div v-if="activeTab === 'workshop'" class="space-y-3">
        <!-- Quick Summary Cards (Only shown when header is expanded!) -->
        <div v-if="!topCollapsed" class="grid grid-cols-2 md:grid-cols-6 gap-3">
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-3">
            <div class="text-xs text-slate-400">Jami Raqamlangan Qoliplar</div>
            <div class="text-xl font-black text-white mt-0.5">{{ store.molds.length }} ta</div>
            <div class="text-[11px] text-purple-400">
              Shundan {{ store.molds.filter((m) => m.stack_tier > 1).length }} tasi ustma-ust (2/3-qavat)
            </div>
          </div>
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-3">
            <div class="text-xs text-slate-400">Quyilgan (Qotmoqda)</div>
            <div class="text-xl font-black text-blue-400 mt-0.5">
              {{ store.molds.filter((m) => m.status === 'poured').length }} ta
            </div>
            <div class="text-[11px] text-slate-400">Ichida beton bor</div>
          </div>
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-3">
            <div class="text-xs text-slate-400">Yechishga Tayyor</div>
            <div class="text-xl font-black text-emerald-400 mt-0.5">
              {{ store.molds.filter((m) => m.status === 'ready_demold').length }} ta
            </div>
            <div class="text-[11px] text-slate-400">Bugun qolipdan chiqariladi</div>
          </div>
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-3">
            <div class="text-xs text-slate-400">Bo'sh (Quyishga tayyor)</div>
            <div class="text-xl font-black text-slate-200 mt-0.5">
              {{ store.molds.filter((m) => m.status === 'empty').length }} ta
            </div>
            <div class="text-[11px] text-slate-400">Tozalangan va moylangan</div>
          </div>
          <div class="bg-slate-900 border border-amber-500/30 rounded-xl p-3">
            <div class="text-xs text-amber-300">Kolodets Qolipi</div>
            <div class="text-xl font-black text-amber-400 mt-0.5">
              {{ store.molds.find((m) => m.product_category === 'kolodets')?.today_cyclic_count || 0 }} dona
            </div>
            <div class="text-[11px] text-amber-200/80">Bugun 1 ta qolipda quyildi</div>
          </div>
          <div class="bg-slate-900 border border-red-500/40 rounded-xl p-3">
            <div class="text-xs text-red-300">Burchagi Ushlagan / Remont</div>
            <div class="text-xl font-black text-red-400 mt-0.5">
              {{ store.molds.filter((m) => m.status === 'maintenance' || m.consecutive_corner_defects >= 1).length }} ta
            </div>
            <div class="text-[11px] text-red-300/80">Nazorat & ta'mir kerak</div>
          </div>
        </div>

        <!-- Main 3D View (Full 12-col width when no mold passport is open!) -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-4">
          <div :class="store.selectedMold ? 'lg:col-span-8' : 'lg:col-span-12'">
            <Workshop3D />
          </div>

          <!-- Right Sidebar: Selected Mold Passport (ONLY rendered when a mold is selected!) -->
          <div v-if="store.selectedMold" class="lg:col-span-4">
            <div
              class="bg-slate-900 border border-slate-800 rounded-2xl p-4 space-y-3 sticky top-14"
            >
              <div class="flex items-start justify-between border-b border-slate-800 pb-3">
                <div>
                  <span class="text-xs uppercase tracking-wider text-blue-400 font-bold">
                    Qolip Pasporti #{{ store.selectedMold.id }}
                  </span>
                  <h3 class="text-xl font-black text-white mt-0.5">
                    {{ store.selectedMold.mold_number }}
                  </h3>
                  <p class="text-xs text-slate-400">{{ store.selectedMold.product_name }}</p>
                </div>
                <span
                  :class="{
                    'bg-blue-500/20 text-blue-300 border-blue-500/40': store.selectedMold.status === 'poured',
                    'bg-emerald-500/20 text-emerald-300 border-emerald-500/40': store.selectedMold.status === 'ready_demold',
                    'bg-slate-700 text-slate-200 border-slate-600': store.selectedMold.status === 'empty',
                    'bg-red-500/20 text-red-300 border-red-500/40': store.selectedMold.status === 'maintenance',
                    'bg-amber-500/20 text-amber-300 border-amber-500/40': store.selectedMold.status === 'cyclic_active',
                  }"
                  class="px-2.5 py-1 rounded-lg text-xs font-bold border"
                >
                  {{
                    store.selectedMold.status === 'poured'
                      ? 'Quyilgan (Qotmoqda)'
                      : store.selectedMold.status === 'ready_demold'
                      ? 'Yechishga tayyor'
                      : store.selectedMold.status === 'maintenance'
                      ? 'REMONT KERAK'
                      : store.selectedMold.status === 'cyclic_active'
                      ? 'Siklli Faol (20+/kun)'
                      : "Bo'sh"
                  }}
                </span>
              </div>

              <!-- Stats -->
              <div class="grid grid-cols-3 gap-2 text-center bg-slate-950 rounded-xl p-3 border border-slate-800">
                <div>
                  <div class="text-[11px] text-slate-400">Jami quyilgan</div>
                  <div class="text-base font-bold text-white">{{ store.selectedMold.total_casts }} marta</div>
                </div>
                <div>
                  <div class="text-[11px] text-slate-400">Qavati (Ustma-ust)</div>
                  <div class="text-base font-bold text-purple-400">{{ store.selectedMold.stack_tier }}-Qavat</div>
                </div>
                <div>
                  <div class="text-[11px] text-slate-400">Ketma-ket defekt</div>
                  <div
                    :class="store.selectedMold.consecutive_corner_defects > 0 ? 'text-red-400' : 'text-emerald-400'"
                    class="text-base font-bold"
                  >
                    {{ store.selectedMold.consecutive_corner_defects }} marta
                  </div>
                </div>
              </div>

              <!-- Defect Warning Box -->
              <div
                v-if="store.selectedMold.consecutive_corner_defects > 0 || store.selectedMold.status === 'maintenance'"
                class="bg-red-950/50 border border-red-500/50 rounded-xl p-3.5 space-y-2"
              >
                <div class="text-xs font-bold text-red-300 flex items-center gap-1.5">
                  <span>⚠️</span> Burchak ushlab qolishi / Ta'mir ogohlantirishi:
                </div>
                <p class="text-xs text-red-200">{{ store.selectedMold.notes || store.selectedMold.last_defect_note }}</p>

                <!-- Quick Repair Form -->
                <div class="pt-2 border-t border-red-800/60 space-y-2">
                  <input
                    v-model="repairForm.repair_action"
                    type="text"
                    placeholder="Qanday remont qilindi?"
                    class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white"
                  />
                  <div class="flex gap-2">
                    <input
                      v-model.number="repairForm.repair_cost"
                      type="number"
                      placeholder="Xarajat (so'm)"
                      class="w-1/2 bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white"
                    />
                    <button
                      @click="submitMoldRepair"
                      class="w-1/2 bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs rounded-lg py-1.5 transition cursor-pointer"
                    >
                      🔧 Remont qilindi
                    </button>
                  </div>
                </div>
              </div>

              <!-- 3D Position & Stacking Editor (For aligning with workshop photo!) -->
              <div class="bg-slate-950 border border-slate-800 rounded-xl p-3.5 space-y-2.5">
                <div class="text-xs font-bold text-slate-200 flex items-center justify-between">
                  <span>📍 Sexdagi 3D Joylashuvi va Qavati</span>
                  <span class="text-[11px] text-purple-400">Ustma-ust sozlash</span>
                </div>
                <div class="grid grid-cols-3 gap-2">
                  <div>
                    <label class="text-[11px] text-slate-400">X (Eni, m)</label>
                    <input
                      v-model.number="posForm.pos_x"
                      type="number"
                      step="0.2"
                      class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white"
                    />
                  </div>
                  <div>
                    <label class="text-[11px] text-slate-400">Z (Bo'yi, m)</label>
                    <input
                      v-model.number="posForm.pos_z"
                      type="number"
                      step="0.2"
                      class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white"
                    />
                  </div>
                  <div>
                    <label class="text-[11px] text-purple-300 font-semibold">Qavat (1, 2, 3)</label>
                    <select
                      v-model.number="posForm.stack_tier"
                      class="w-full bg-slate-900 border border-purple-500/50 rounded-lg px-2 py-1 text-xs text-white"
                    >
                      <option :value="1">1-Qavat (Yerda)</option>
                      <option :value="2">2-Qavat (Ustida)</option>
                      <option :value="3">3-Qavat (Ustida)</option>
                    </select>
                  </div>
                </div>
                <div class="grid grid-cols-2 gap-2">
                  <div>
                    <label class="text-[11px] text-slate-400">Qator / Zona</label>
                    <input
                      v-model="posForm.zone"
                      type="text"
                      class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white"
                    />
                  </div>
                  <div>
                    <label class="text-[11px] text-slate-400">Burilish (°)</label>
                    <input
                      v-model.number="posForm.rotation_deg"
                      type="number"
                      step="15"
                      class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white"
                    />
                  </div>
                </div>
                <button
                  @click="saveMoldPosition"
                  class="w-full bg-slate-800 hover:bg-blue-600 text-xs font-semibold text-white py-2 rounded-lg border border-slate-700 transition cursor-pointer"
                >
                  Joylashuvni 3D Xaritada Yangilash
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Full Molds Registry Table -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5">
          <h3 class="text-sm font-bold text-white mb-3">
            Barcha Raqamlangan Qoliplar Reestri (Joylashuvi, Qavati va Oxirgi Beton Holati)
          </h3>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs">
              <thead class="text-slate-400 border-b border-slate-800 bg-slate-950/60">
                <tr>
                  <th class="py-2.5 px-3">Qolip Raqami</th>
                  <th class="py-2.5 px-3">O'lchami</th>
                  <th class="py-2.5 px-3">Sexdagi Joylashuvi</th>
                  <th class="py-2.5 px-3">Qavati (Ustma-ust)</th>
                  <th class="py-2.5 px-3">Quyish Narxi (Usta)</th>
                  <th class="py-2.5 px-3">Hozirgi Holati</th>
                  <th class="py-2.5 px-3">Oxirgi Beton Sifati</th>
                  <th class="py-2.5 px-3">Jami Sikl</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-800/70">
                <tr
                  v-for="m in store.molds"
                  :key="m.id"
                  @click="store.selectedMold = m"
                  :class="store.selectedMold?.id === m.id ? 'bg-blue-950/40' : 'hover:bg-slate-800/50'"
                  class="cursor-pointer transition"
                >
                  <td class="py-2.5 px-3 font-bold text-white">{{ m.mold_number }}</td>
                  <td class="py-2.5 px-3 text-slate-300">{{ m.product_name }}</td>
                  <td class="py-2.5 px-3 text-slate-400">{{ m.zone }} (X:{{ m.pos_x }}, Z:{{ m.pos_z }})</td>
                  <td class="py-2.5 px-3">
                    <span
                      :class="m.stack_tier > 1 ? 'bg-purple-500/20 text-purple-300 border-purple-500/40' : 'bg-slate-800 text-slate-300 border-slate-700'"
                      class="px-2 py-0.5 rounded border text-[11px] font-semibold"
                    >
                      {{ m.stack_tier }}-Qavat {{ m.stack_tier > 1 ? '(Ustida)' : '(Yerda)' }}
                    </span>
                  </td>
                  <td class="py-2.5 px-3 font-medium text-amber-300">{{ formatMoney(m.casting_labor_cost) }}</td>
                  <td class="py-2.5 px-3">
                    <span
                      :class="{
                        'text-blue-400 font-semibold': m.status === 'poured',
                        'text-emerald-400 font-semibold': m.status === 'ready_demold',
                        'text-slate-400': m.status === 'empty',
                        'text-red-400 font-bold': m.status === 'maintenance',
                        'text-amber-400 font-bold': m.status === 'cyclic_active',
                      }"
                    >
                      {{
                        m.status === 'poured'
                          ? 'Quyilgan'
                          : m.status === 'ready_demold'
                          ? 'Yechishga tayyor'
                          : m.status === 'maintenance'
                          ? 'REMONT KERAK'
                          : m.status === 'cyclic_active'
                          ? `Siklli (${m.today_cyclic_count} ta bugun)`
                          : "Bo'sh"
                      }}
                    </span>
                  </td>
                  <td class="py-2.5 px-3">
                    <span
                      :class="m.last_quality_status === 'clean' ? 'text-emerald-400' : 'text-red-400 font-semibold'"
                    >
                      {{ m.last_quality_status === 'clean' ? '✓ Toza chiqqan' : '⚠️ Burchagi ushlagan' }}
                    </span>
                    <span v-if="m.notes" class="block text-[11px] text-slate-400">{{ m.notes }}</span>
                  </td>
                  <td class="py-2.5 px-3 font-bold text-slate-200">{{ m.total_casts }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ==================== TAB 2: DAILY PRODUCTION (UNNUMBERED BY SIZE + WORKERS PAYROLL) ==================== -->
      <div v-if="activeTab === 'production'" class="space-y-6">
        <!-- NEW PRIMARY SECTION: UNNUMBERED DAILY CASTING BY SIZE & WORKER PAYROLL -->
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <!-- Left 7 Cols: Size Quantities & Workers Form -->
          <div class="lg:col-span-7 bg-slate-900 border border-blue-500/40 rounded-2xl p-5 space-y-4 shadow-xl">
            <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-3">
              <div>
                <span class="px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-300 text-xs font-bold border border-blue-500/30">
                  {{ editingSizeBatchId ? `✏️ Yozuvni Tahrirlash (#${editingSizeBatchId})` : "⚡ Qolip Raqamisiz Kunlik Quyish va Ishchilar Tabeli" }}
                </span>
                <h2 class="text-base font-black text-white mt-1.5">
                  Qaysi O'lchamdan Nechta Quyilgani va Ishchilar Ish Haqi
                </h2>
              </div>
              <div class="flex items-center gap-2">
                <label class="text-xs text-slate-400 font-semibold">Sana:</label>
                <input
                  v-model="sizeBatchForm.work_date"
                  type="date"
                  class="bg-slate-950 border border-slate-700 rounded-xl px-3 py-1.5 text-xs font-bold text-white"
                />
              </div>
            </div>

            <!-- 1. Product Sizes Quantities Grid -->
            <div>
              <div class="text-xs font-bold text-slate-300 mb-2 flex items-center justify-between">
                <span>1. Quyilgan mahsulotlar soni (qolip raqamisiz, o'lcham bo'yicha):</span>
                <span class="text-blue-400">Jami: {{ sizeBatchPreview.totalQty }} dona</span>
              </div>
              <div class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                <div
                  v-for="meta in sizeCatalogMeta"
                  :key="meta.code"
                  :class="Number(sizeBatchForm.quantities[meta.code] || 0) > 0 ? 'border-blue-500 bg-blue-950/25' : 'border-slate-800 bg-slate-950'"
                  class="rounded-xl border p-3 transition space-y-2"
                >
                  <div class="flex items-center justify-between">
                    <span :class="meta.badge" class="px-2 py-0.5 rounded border text-[11px] font-bold">
                      {{ meta.code }}
                    </span>
                    <span class="text-xs font-bold text-white">{{ meta.shortLabel }}</span>
                  </div>
                  <div class="flex items-center gap-1.5">
                    <button
                      type="button"
                      @click="sizeBatchForm.quantities[meta.code] = Math.max(0, Number(sizeBatchForm.quantities[meta.code] || 0) - 1)"
                      class="w-8 h-8 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-bold text-sm cursor-pointer"
                    >
                      -
                    </button>
                    <input
                      v-model.number="sizeBatchForm.quantities[meta.code]"
                      type="number"
                      min="0"
                      class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2 py-1.5 text-center text-sm font-black text-white"
                    />
                    <button
                      type="button"
                      @click="sizeBatchForm.quantities[meta.code] = Number(sizeBatchForm.quantities[meta.code] || 0) + 1"
                      class="w-8 h-8 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-bold text-sm cursor-pointer"
                    >
                      +
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <!-- 2. Workers & Wages Section (Shuhratjon, Ahliddin, Kadirov) -->
            <div class="bg-slate-950 border border-slate-800 rounded-xl p-4 space-y-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <div class="text-xs font-bold text-amber-300">
                    👷 2. Ishlagan Ishchilar va Kunlik Yozilgan Summasi
                  </div>
                  <div class="text-[11px] text-slate-400">
                    Har bir ishchiga bir xil yoki alohida summa yozish mumkin
                  </div>
                </div>
                <div class="flex items-center gap-1.5">
                  <span class="text-[11px] text-slate-400">Kishi boshiga:</span>
                  <input
                    v-model.number="sizeBatchForm.uniform_wage"
                    @input="applyUniformWageToAll"
                    type="number"
                    step="5000"
                    class="w-28 bg-slate-900 border border-amber-500/50 rounded-lg px-2.5 py-1 text-xs font-bold text-amber-300"
                  />
                  <button
                    type="button"
                    @click="applyUniformWageToAll"
                    class="px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500 hover:text-slate-950 text-amber-300 text-[11px] font-bold border border-amber-500/40 transition cursor-pointer"
                  >
                    Barchasiga
                  </button>
                </div>
              </div>

              <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                <div
                  v-for="(w, idx) in sizeBatchForm.workers"
                  :key="idx"
                  :class="w.active ? 'border-amber-500/50 bg-slate-900' : 'border-slate-800 bg-slate-900/40 opacity-60'"
                  class="rounded-xl border p-2.5 space-y-1.5"
                >
                  <label class="flex items-center justify-between cursor-pointer">
                    <span class="flex items-center gap-2">
                      <input type="checkbox" v-model="w.active" class="w-4 h-4 accent-amber-500 rounded" />
                      <span class="text-xs font-bold text-white">{{ w.name }}</span>
                    </span>
                    <span v-if="w.active" class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 font-semibold">
                      Ishladi
                    </span>
                  </label>
                  <div v-if="w.active" class="flex items-center gap-1">
                    <input
                      v-model.number="w.amount"
                      type="number"
                      step="5000"
                      class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs font-bold text-amber-300"
                    />
                    <span class="text-[10px] text-slate-400">so'm</span>
                  </div>
                </div>
              </div>

              <!-- Add extra worker input -->
              <div class="flex items-center gap-2 pt-1">
                <input
                  v-model="sizeBatchForm.new_worker_name"
                  @keyup.enter="addNewWorkerToForm"
                  type="text"
                  placeholder="+ Yangi ishchi ismi (masalan: Usta...)"
                  class="flex-1 bg-slate-900 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-white"
                />
                <button
                  type="button"
                  @click="addNewWorkerToForm"
                  class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-200 border border-slate-700 cursor-pointer"
                >
                  + Ishchi Qo'shish
                </button>
              </div>
            </div>

            <!-- 3. Auto Calculated Norms & Notes -->
            <div class="grid grid-cols-2 sm:grid-cols-5 gap-2 bg-slate-950 border border-slate-800 rounded-xl p-3 text-center text-xs">
              <div>
                <div class="text-[10px] text-slate-400">Jami Quyilgan</div>
                <div class="font-black text-blue-400 text-sm">{{ sizeBatchPreview.totalQty }} dona</div>
              </div>
              <div>
                <div class="text-[10px] text-slate-400">Jami Ish Haqi ({{ sizeBatchPreview.activeWorkersCount }} kishi)</div>
                <div class="font-black text-amber-400 text-sm">{{ formatMoney(sizeBatchPreview.totalLabor) }}</div>
              </div>
              <div>
                <div class="text-[10px] text-slate-400">Sement sarfi</div>
                <div class="font-bold text-white">{{ sizeBatchPreview.totalCem }} kg</div>
              </div>
              <div>
                <div class="text-[10px] text-slate-400">Shag'al (3:1 nisbat)</div>
                <div class="font-bold text-white">{{ sizeBatchPreview.totalGrv }} kg</div>
                <div class="text-[10px] text-emerald-400">
                  Mayda: {{ sizeBatchPreview.fineGrv }} • Yirik: {{ sizeBatchPreview.coarseGrv }} kg
                </div>
              </div>
              <div>
                <div class="text-[10px] text-slate-400">Beton / Sim</div>
                <div class="font-bold text-sky-300">{{ sizeBatchPreview.totalVol }} m³ / {{ sizeBatchPreview.totalWir }} kg</div>
              </div>
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <input
                v-model="sizeBatchForm.notes"
                type="text"
                placeholder="Qo'shimcha izoh (ixtiyoriy)..."
                class="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-3 py-2.5 text-xs text-white"
              />
              <button
                v-if="editingSizeBatchId"
                type="button"
                @click="resetSizeBatchForm"
                class="px-4 py-2.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-xs font-bold text-slate-300 cursor-pointer"
              >
                Bekor qilish
              </button>
              <button
                type="button"
                @click="submitSizeBatch"
                class="px-5 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-black text-xs shadow-lg shadow-blue-600/25 transition cursor-pointer"
              >
                {{ editingSizeBatchId ? "✓ O'zgarishlarni Saqlash" : "✓ Kunlik Quyish va Ish Haqini Saqlash" }}
              </button>
            </div>
          </div>

          <!-- Right 5 Cols: Workers Earnings Summary & Unnumbered Batches History -->
          <div class="lg:col-span-5 space-y-4">
            <!-- Workers Payroll Summary Card -->
            <div class="bg-slate-900 border border-amber-500/30 rounded-2xl p-5 space-y-3">
              <div class="flex items-center justify-between">
                <span class="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-300 text-xs font-bold">
                  👷 Ishchilar Hisob-Kitobi (Tabel)
                </span>
                <span class="text-xs text-slate-400">
                  Jami: {{ formatMoney(store.workersSummary.reduce((a, b) => a + Number(b.total_earned || 0), 0)) }}
                </span>
              </div>
              <div class="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                <div
                  v-for="ws in store.workersSummary"
                  :key="ws.name"
                  class="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-1"
                >
                  <div class="text-sm font-black text-white">{{ ws.name }}</div>
                  <div class="text-xs font-bold text-amber-400">{{ formatMoney(ws.total_earned) }}</div>
                  <div class="text-[11px] text-slate-400">
                    {{ ws.days_count }} smena • Oxirgi: {{ ws.last_work_date }}
                  </div>
                </div>
              </div>
            </div>

            <!-- Recent Unnumbered Size Batches List (With 1-Click Edit!) -->
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-3">
              <div class="flex items-center justify-between">
                <h3 class="text-sm font-bold text-white">
                  📋 Kunlik Quyilganlar Tarixi (O'lcham va Ishchilar bo'yicha)
                </h3>
                <span class="text-xs text-slate-400">{{ store.sizeBatches.length }} ta yozuv</span>
              </div>

              <div class="space-y-3 max-h-[420px] overflow-y-auto pr-1">
                <div
                  v-for="b in store.sizeBatches"
                  :key="b.id"
                  :class="editingSizeBatchId === b.id ? 'border-blue-500 bg-blue-950/20' : 'border-slate-800 bg-slate-950'"
                  class="rounded-xl border p-3.5 space-y-2.5 transition"
                >
                  <div class="flex items-center justify-between">
                    <div class="flex items-center gap-2">
                      <span class="text-xs font-black text-white bg-slate-800 px-2.5 py-1 rounded-lg">
                        📅 {{ b.work_date }}
                      </span>
                      <span class="text-xs font-bold text-blue-400">
                        Jami: {{ b.total_qty }} dona
                      </span>
                    </div>
                    <div class="flex items-center gap-1.5">
                      <button
                        @click="loadSizeBatchForEdit(b)"
                        class="px-2.5 py-1 rounded-lg bg-blue-600/20 hover:bg-blue-600 text-blue-300 hover:text-white border border-blue-500/40 text-[11px] font-bold transition cursor-pointer"
                      >
                        ✏️ Tahrirlash
                      </button>
                      <button
                        @click="handleDeleteSizeBatch(b.id)"
                        class="px-2 py-1 rounded-lg bg-red-500/15 hover:bg-red-600 text-red-300 hover:text-white border border-red-500/30 text-[11px] font-bold transition cursor-pointer"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>

                  <!-- Cast items badges -->
                  <div class="flex flex-wrap gap-1.5">
                    <span
                      v-for="it in (b.items || []).filter((x) => Number(x.quantity || 0) > 0)"
                      :key="it.code"
                      class="px-2.5 py-1 rounded-lg bg-slate-900 border border-slate-700 text-xs font-bold text-white"
                    >
                      {{ it.name }}: <strong class="text-sky-400">{{ it.quantity }} dona</strong>
                    </span>
                  </div>

                  <!-- Material & Gravel 3:1 Breakdown Row -->
                  <div class="flex flex-wrap items-center gap-2 text-[11px] text-slate-300 bg-slate-900/80 border border-slate-800 rounded-lg px-2.5 py-1.5">
                    <span>Sement: <strong class="text-white">{{ b.total_cement_kg }} kg</strong></span>
                    <span>•</span>
                    <span>
                      Shag'al (3:1):
                      <strong class="text-emerald-400">Mayda (qum kabi) {{ (Number(b.total_gravel_kg || 0) * 0.75).toFixed(0) }} kg</strong>
                      /
                      <strong class="text-sky-300">Yirik {{ (Number(b.total_gravel_kg || 0) * 0.25).toFixed(0) }} kg</strong>
                    </span>
                    <span>•</span>
                    <span>Beton: <strong class="text-white">{{ b.total_concrete_m3 }} m³</strong></span>
                  </div>

                  <!-- Workers badges -->
                  <div class="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-slate-800/80 text-xs">
                    <div class="flex flex-wrap gap-1.5">
                      <span
                        v-for="w in b.workers || []"
                        :key="w.name"
                        class="px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/30 text-amber-200 text-[11px] font-semibold"
                      >
                        👷 {{ w.name }}: {{ formatMoney(w.amount) }}
                      </span>
                    </div>
                    <div class="font-black text-amber-400">
                      Jami: {{ formatMoney(b.total_labor_cost) }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Toggle for Legacy Numbered-Mold Production Panels -->
        <div class="flex items-center justify-between bg-slate-900/70 border border-slate-800 rounded-xl px-4 py-2.5">
          <span class="text-xs text-slate-400">
            Raqamlangan qoliplar (#01, #02...) bo'yicha birma-bir quyish va yechish bo'limi
          </span>
          <button
            @click="showLegacyMoldProduction = !showLegacyMoldProduction"
            class="px-3 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-xs font-semibold text-slate-300 border border-slate-700 cursor-pointer"
          >
            {{ showLegacyMoldProduction ? "▲ Raqamlangan qoliplar bo'limini yashirish" : "▼ Raqamlangan qoliplar bo'limini ko'rsatish" }}
          </button>
        </div>

        <div v-if="showLegacyMoldProduction" class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Column 1: Demolding (Qolipdan chiqarish va beton holatini tekshirish) -->
          <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col justify-between">
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <span class="px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 text-xs font-bold">
                  1-Qadam: Qolipdan Chiqarish
                </span>
                <span class="text-xs text-slate-400">{{ pouredOrReadyMolds.length }} ta qolipda beton bor</span>
              </div>
              <h3 class="text-base font-bold text-white">
                Qolipdan Yechish va Beton Holatini Qayd Etish
              </h3>
              <p class="text-xs text-slate-400">
                Qolipdan chiqqanda burchagi ushlab qolgan bo'lsa belgilang — ketma-ket 2 marta qaytarilsa qolip avtomatik remontga tushadi.
              </p>

              <div class="max-h-80 overflow-y-auto space-y-2 pr-1">
                <div
                  v-for="m in pouredOrReadyMolds"
                  :key="m.id"
                  class="bg-slate-950 border border-slate-800 rounded-xl p-3 space-y-2"
                >
                  <div class="flex items-center justify-between">
                    <label class="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        v-model="selectedForDemold[m.id].checked"
                        class="w-4 h-4 accent-emerald-500 rounded"
                      />
                      <span class="font-bold text-xs text-white">{{ m.mold_number }}</span>
                      <span class="text-[11px] text-purple-400">({{ m.stack_tier }}-qavat)</span>
                    </label>
                    <span class="text-[11px] text-slate-400">{{ m.product_name }}</span>
                  </div>

                  <div v-if="selectedForDemold[m.id]?.checked" class="grid grid-cols-2 gap-2 pt-1">
                    <select
                      v-model="selectedForDemold[m.id].quality_status"
                      class="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white"
                    >
                      <option value="clean">✓ Toza chiqdi (A'lo)</option>
                      <option value="corner_stuck">⚠️ Burchagi ushlab qoldi</option>
                      <option value="cracked">❌ Yoriq / Yaroqsiz brak</option>
                    </select>
                    <input
                      v-model="selectedForDemold[m.id].defect_location"
                      type="text"
                      placeholder="Qayeri? (masalan: Chap burchak)"
                      class="bg-slate-900 border border-slate-700 rounded-lg px-2 py-1 text-xs text-white"
                    />
                  </div>
                </div>
              </div>
            </div>

            <button
              @click="submitDemoldBatch"
              class="mt-4 w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs py-3 rounded-xl shadow-lg shadow-emerald-600/20 transition cursor-pointer"
            >
              Belgilangan Qoliplarni Yechish va Omborga Kiritish
            </button>
          </div>

          <!-- Column 2: Stationary Ariq Molds Casting -->
          <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col justify-between">
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <span class="px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-300 text-xs font-bold">
                  2-Qadam: Ariq Qoliplarini Quyish
                </span>
                <span class="text-xs text-slate-400">{{ emptyStationaryMolds.length }} ta bo'sh qolip</span>
              </div>
              <h3 class="text-base font-bold text-white">
                Bugun Quyilgan Ariq Qoliplarini Belgilash
              </h3>
              <p class="text-xs text-slate-400">
                Tanlangan qoliplar quyilganda usta haqi, sement, shag'al va sim normasi avtomatik hisoblanadi.
              </p>

              <div class="max-h-80 overflow-y-auto space-y-2 pr-1">
                <label
                  v-for="m in emptyStationaryMolds"
                  :key="m.id"
                  class="flex items-center justify-between bg-slate-950 border border-slate-800 hover:border-blue-500/40 rounded-xl p-3 cursor-pointer transition"
                >
                  <div class="flex items-center gap-2.5">
                    <input
                      type="checkbox"
                      :value="m.id"
                      v-model="selectedForCast"
                      class="w-4 h-4 accent-blue-500 rounded"
                    />
                    <div>
                      <div class="text-xs font-bold text-white">
                        {{ m.mold_number }}
                        <span class="text-purple-400 font-normal">({{ m.stack_tier }}-Qavat)</span>
                      </div>
                      <div class="text-[11px] text-slate-400">{{ m.product_name }}</div>
                    </div>
                  </div>
                  <div class="text-right">
                    <div class="text-xs font-bold text-amber-300">{{ formatMoney(m.casting_labor_cost) }}</div>
                    <div class="text-[10px] text-slate-400">Quyish narxi</div>
                  </div>
                </label>
              </div>
            </div>

            <button
              @click="submitCastBatch"
              class="mt-4 w-full bg-blue-600 hover:bg-blue-500 text-white font-bold text-xs py-3 rounded-xl shadow-lg shadow-blue-600/20 transition cursor-pointer"
            >
              Tanlangan Qoliplarni Quyish ({{ selectedForCast.length }} ta)
            </button>
          </div>

          <!-- Column 3: Single Kolodets Mold Cyclic Casting (20+ times a day!) -->
          <div class="bg-slate-900 border border-amber-500/40 rounded-2xl p-5 flex flex-col justify-between">
            <div class="space-y-3">
              <div class="flex items-center justify-between">
                <span class="px-2.5 py-1 rounded-lg bg-amber-500/20 text-amber-300 text-xs font-bold">
                  3-Qadam: Kolodets Siklli Quyish (20+/kun)
                </span>
                <span class="text-xs text-amber-300 font-semibold">Ø118 / Ø104 (7sm)</span>
              </div>
              <h3 class="text-base font-bold text-white">
                Bitta Kolodets Qolipida Qayta-Qayta Quyish
              </h3>
              <p class="text-xs text-slate-400">
                Tashqi Ø118sm, ichki Ø104sm, balandligi max 60sm bo'lgan kolodets qolipida bugun nechta quyib-yechilganini kiriting:
              </p>

              <div class="space-y-3 bg-slate-950 border border-slate-800 rounded-xl p-3.5 text-xs">
                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="text-slate-400 block mb-1">Bugun nechta quyildi? (dona)</label>
                    <input
                      v-model.number="cyclicForm.quantity"
                      type="number"
                      min="1"
                      max="60"
                      class="w-full bg-slate-900 border border-amber-500/50 rounded-lg px-3 py-2 text-sm font-bold text-amber-300"
                    />
                  </div>
                  <div>
                    <label class="text-slate-400 block mb-1">Balandligi (Max 60 sm)</label>
                    <input
                      v-model.number="cyclicForm.custom_height_cm"
                      type="number"
                      min="20"
                      max="60"
                      class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-sm font-bold text-white"
                    />
                  </div>
                </div>

                <div class="grid grid-cols-2 gap-3">
                  <div>
                    <label class="text-slate-400 block mb-1">Burchagi/qirrasi ushlagani (dona)</label>
                    <input
                      v-model.number="cyclicForm.corner_stuck_qty"
                      type="number"
                      min="0"
                      class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-white"
                    />
                  </div>
                  <div>
                    <label class="text-slate-400 block mb-1">Yaroqsiz brak (dona)</label>
                    <input
                      v-model.number="cyclicForm.cracked_qty"
                      type="number"
                      min="0"
                      class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-white"
                    />
                  </div>
                </div>

                <div>
                  <label class="text-slate-400 block mb-1">Sifat va qolip holati izohi</label>
                  <input
                    v-model="cyclicForm.defect_location"
                    type="text"
                    class="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-white"
                  />
                </div>
              </div>
            </div>

            <button
              @click="submitCyclicCast"
              class="mt-4 w-full bg-amber-500 hover:bg-amber-400 text-slate-950 font-black text-xs py-3 rounded-xl shadow-lg shadow-amber-500/20 transition cursor-pointer"
            >
              + {{ cyclicForm.quantity }} ta Kolodets Quyilganini Saqlash
            </button>
          </div>
        </div>

        <!-- Daily Work & Weather Logs Table -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5">
          <h3 class="text-sm font-bold text-white mb-3">
            Kunlik Ish va Avtomatik Ob-havo Jurnali (Qaysi kuni ish bo'ldi, ob-havo va natijalar)
          </h3>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs">
              <thead class="text-slate-400 border-b border-slate-800 bg-slate-950/60">
                <tr>
                  <th class="py-2.5 px-3">Sana</th>
                  <th class="py-2.5 px-3">Hudud va Ob-havo (Avto-Log)</th>
                  <th class="py-2.5 px-3">Qolipdan Chiqarildi</th>
                  <th class="py-2.5 px-3">Ariq Quyildi</th>
                  <th class="py-2.5 px-3">Kolodets Quyildi (Siklli)</th>
                  <th class="py-2.5 px-3">Burchak Ushlash / Defekt</th>
                  <th class="py-2.5 px-3">Jami Usta Haqi</th>
                  <th class="py-2.5 px-3">Texnologik Maslahat</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-slate-800/70">
                <tr v-for="lg in store.dailyLogs" :key="lg.id" class="hover:bg-slate-800/40">
                  <td class="py-3 px-3 font-bold text-white">{{ lg.work_date }}</td>
                  <td class="py-3 px-3">
                    <span class="font-semibold text-sky-300">{{ lg.weather_condition }}</span>
                    <span class="text-slate-300 ml-1">
                      ({{ lg.weather_temp_min }}°..{{ lg.weather_temp_max }}°C, namlik {{ lg.weather_humidity }}%)
                    </span>
                  </td>
                  <td class="py-3 px-3 font-bold text-emerald-400">{{ lg.demolded_count }} dona</td>
                  <td class="py-3 px-3 font-bold text-blue-400">{{ lg.cast_count }} dona</td>
                  <td class="py-3 px-3 font-bold text-amber-400">{{ lg.cyclic_cast_count }} dona</td>
                  <td class="py-3 px-3">
                    <span :class="lg.defect_count > 0 ? 'text-red-400 font-bold' : 'text-slate-400'">
                      {{ lg.defect_count }} ta
                    </span>
                  </td>
                  <td class="py-3 px-3 font-bold text-white">{{ formatMoney(lg.labor_cost_total) }}</td>
                  <td class="py-3 px-3 text-slate-400 max-w-xs">{{ lg.curing_advice }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- ==================== TAB 3: PRODUCT SIZES & 3D CATALOG ==================== -->
      <div v-if="activeTab === 'catalog'" class="space-y-6">
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 class="text-base font-bold text-white">
              Korxona Mahsulot O'lchamlari, 3D Parametrik Chizmasi va Quyish Narxlari
            </h2>
            <p class="text-xs text-slate-400">
              22-lik, 30-lik (tagi 15sm, yoni 22sm, og'zi 29-30sm), 40-lik, 50-lik beton ariqlar va Ø118/104sm (7sm qalinlik, ≤60sm) kolodets
            </p>
          </div>
          <button
            @click="newProductModal = true"
            class="px-4 py-2 rounded-xl bg-blue-600 hover:bg-blue-500 text-xs font-bold text-white transition cursor-pointer"
          >
            + Yangi O'lcham Kiritish
          </button>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <!-- Left: Interactive 3D Product Model -->
          <div class="lg:col-span-5" v-if="activePreviewProduct">
            <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-4 sticky top-28">
              <Product3DPreview :product="activePreviewProduct" />

              <div class="space-y-2">
                <div class="flex items-center justify-between">
                  <h3 class="text-lg font-black text-white">{{ activePreviewProduct.name }}</h3>
                  <span class="px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-300 text-xs font-bold">
                    Omborda: {{ activePreviewProduct.stock_qty }} dona
                  </span>
                </div>
                <p class="text-xs text-slate-400">{{ activePreviewProduct.description }}</p>
              </div>

              <!-- Geometric Specs -->
              <div
                v-if="activePreviewProduct.category === 'ariq'"
                class="grid grid-cols-4 gap-2 bg-slate-950 p-3 rounded-xl border border-slate-800 text-center text-xs"
              >
                <div>
                  <div class="text-[10px] text-slate-400">Pastki (Suv yo'li)</div>
                  <div class="font-bold text-sky-400">{{ activePreviewProduct.inner_bottom_cm }} sm</div>
                </div>
                <div>
                  <div class="text-[10px] text-slate-400">Yon tomoni</div>
                  <div class="font-bold text-sky-400">{{ activePreviewProduct.inner_side_cm }} sm</div>
                </div>
                <div>
                  <div class="text-[10px] text-slate-400">Ustki og'zi</div>
                  <div class="font-bold text-sky-400">{{ activePreviewProduct.inner_top_cm }} sm</div>
                </div>
                <div>
                  <div class="text-[10px] text-slate-400">Uzunligi</div>
                  <div class="font-bold text-white">{{ activePreviewProduct.length_cm }} sm</div>
                </div>
              </div>

              <div
                v-else
                class="grid grid-cols-4 gap-2 bg-slate-950 p-3 rounded-xl border border-slate-800 text-center text-xs"
              >
                <div>
                  <div class="text-[10px] text-slate-400">Tashqi Ø</div>
                  <div class="font-bold text-amber-400">{{ activePreviewProduct.outer_diameter_cm }} sm</div>
                </div>
                <div>
                  <div class="text-[10px] text-slate-400">Ichki Ø</div>
                  <div class="font-bold text-amber-400">{{ activePreviewProduct.inner_diameter_cm }} sm</div>
                </div>
                <div>
                  <div class="text-[10px] text-slate-400">Devor qalinligi</div>
                  <div class="font-bold text-white">{{ activePreviewProduct.wall_thickness_cm }} sm</div>
                </div>
                <div>
                  <div class="text-[10px] text-slate-400">Max Balandlik</div>
                  <div class="font-bold text-white">≤ {{ activePreviewProduct.max_height_cm }} sm</div>
                </div>
              </div>

              <!-- Recipe & Prices -->
              <div class="grid grid-cols-2 gap-3 text-xs">
                <div class="bg-slate-950 border border-slate-800 rounded-xl p-3">
                  <div class="text-slate-400">1 dona quyish narxi (Usta haqi)</div>
                  <div class="text-base font-black text-amber-400 mt-0.5">
                    {{ formatMoney(activePreviewProduct.casting_labor_cost) }}
                  </div>
                </div>
                <div class="bg-slate-950 border border-slate-800 rounded-xl p-3">
                  <div class="text-slate-400">Sotish narxi (1 dona)</div>
                  <div class="text-base font-black text-emerald-400 mt-0.5">
                    {{ formatMoney(activePreviewProduct.selling_price) }}
                  </div>
                </div>
              </div>

              <div class="text-xs text-slate-400 bg-slate-950 border border-slate-800 rounded-xl p-3 flex justify-between">
                <span>Beton hajmi: <strong class="text-white">{{ activePreviewProduct.concrete_volume_m3 }} m³</strong></span>
                <span>Sement: <strong class="text-white">{{ activePreviewProduct.cement_norm_kg }} kg</strong></span>
                <span>Shag'al: <strong class="text-white">{{ activePreviewProduct.gravel_norm_kg }} kg</strong></span>
                <span>Sim: <strong class="text-white">{{ activePreviewProduct.wire_norm_kg }} kg</strong></span>
              </div>
            </div>
          </div>

          <!-- Right: Product Cards List -->
          <div class="lg:col-span-7 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div
              v-for="p in store.products"
              :key="p.id"
              @click="activePreviewProduct = p"
              :class="
                activePreviewProduct?.id === p.id
                  ? 'border-blue-500 bg-slate-900 ring-2 ring-blue-500/30'
                  : 'border-slate-800 bg-slate-900/70 hover:bg-slate-900'
              "
              class="rounded-2xl border p-5 cursor-pointer transition space-y-3"
            >
              <div class="flex items-start justify-between">
                <div>
                  <span
                    :class="p.casting_mode === 'cyclic' ? 'bg-amber-500/20 text-amber-300' : 'bg-blue-500/20 text-blue-300'"
                    class="px-2 py-0.5 rounded text-[11px] font-bold"
                  >
                    {{ p.casting_mode === 'cyclic' ? 'Siklli qolip (20+/kun)' : 'Statsionar qolip' }}
                  </span>
                  <h4 class="text-base font-bold text-white mt-1.5">{{ p.name }}</h4>
                </div>
                <span class="text-xs font-bold px-2.5 py-1 rounded-lg bg-slate-800 text-slate-200">
                  {{ p.molds_count }} ta qolip
                </span>
              </div>

              <div v-if="p.category === 'ariq'" class="text-xs text-slate-300 space-y-1">
                <div>• Suv oqadigan pastki qismi: <strong>{{ p.inner_bottom_cm }} sm</strong></div>
                <div>• Yon tomoni: <strong>{{ p.inner_side_cm }} sm</strong> | Og'zi: <strong>{{ p.inner_top_cm }} sm</strong></div>
                <div>• Devor qalinligi: <strong>{{ p.wall_thickness_cm }} sm</strong> | Uzunligi: <strong>{{ p.length_cm }} sm</strong></div>
              </div>
              <div v-else class="text-xs text-slate-300 space-y-1">
                <div>• Tashqi diametri: <strong>{{ p.outer_diameter_cm }} sm</strong> | Ichki diametri: <strong>{{ p.inner_diameter_cm }} sm</strong></div>
                <div>• Devor qalinligi: <strong>{{ p.wall_thickness_cm }} sm</strong> | Balandligi: <strong>max {{ p.max_height_cm }} sm</strong></div>
              </div>

              <div class="pt-3 border-t border-slate-800 flex items-center justify-between text-xs">
                <div>
                  <span class="text-slate-400">Quyish:</span>
                  <span class="font-bold text-amber-400 ml-1">{{ formatMoney(p.casting_labor_cost) }}</span>
                </div>
                <div>
                  <span class="text-slate-400">Narxi:</span>
                  <span class="font-bold text-emerald-400 ml-1">{{ formatMoney(p.selling_price) }}</span>
                </div>
                <div>
                  <span class="text-slate-400">Zaxira:</span>
                  <span class="font-bold text-white ml-1">{{ p.stock_qty }} dona</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- ==================== TAB 4: ORDERS, URGENT SALES & MISSING SIZES ==================== -->
      <div v-if="activeTab === 'sales'" class="space-y-6">
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <!-- Form 1: New Order -->
          <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-3">
            <span class="px-2.5 py-1 rounded-lg bg-blue-500/20 text-blue-300 text-xs font-bold">
              📋 1. Yangi Buyurtma Qabul Qilish
            </span>
            <h3 class="text-sm font-bold text-white">Oldindan Buyurtma Yozish</h3>
            <div class="space-y-2.5 text-xs">
              <input
                v-model="orderForm.customer_name"
                type="text"
                placeholder="Mijoz ismi yoki tashkilot"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              />
              <div class="grid grid-cols-2 gap-2">
                <input
                  v-model="orderForm.customer_phone"
                  type="text"
                  placeholder="Telefon"
                  class="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                />
                <input
                  v-model="orderForm.due_date"
                  type="date"
                  class="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                />
              </div>
              <select
                v-model="orderForm.product_type_id"
                @change="onOrderProductChange"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              >
                <option v-for="p in store.products" :key="p.id" :value="p.id">
                  {{ p.name }} (Omborda: {{ p.stock_qty }} dona)
                </option>
              </select>
              <div class="grid grid-cols-3 gap-2">
                <div>
                  <label class="text-[11px] text-slate-400">Miqdori (dona)</label>
                  <input
                    v-model.number="orderForm.ordered_qty"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-white"
                  />
                </div>
                <div>
                  <label class="text-[11px] text-slate-400">Dona narxi</label>
                  <input
                    v-model.number="orderForm.unit_price"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-white"
                  />
                </div>
                <div>
                  <label class="text-[11px] text-slate-400">Avans (Zaklad)</label>
                  <input
                    v-model.number="orderForm.advance_paid"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-white"
                  />
                </div>
              </div>
              <input
                v-model="orderForm.notes"
                type="text"
                placeholder="Izoh (masalan: kran bilan yetkazib berish)"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              />
              <button
                @click="submitOrder"
                class="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2.5 rounded-xl transition cursor-pointer"
              >
                Buyurtmani Saqlash
              </button>
            </div>
          </div>

          <!-- Form 2: Record Sale (Order Fulfillment vs Urgent Pickup!) -->
          <div class="bg-slate-900 border border-emerald-500/40 rounded-2xl p-5 space-y-3">
            <span class="px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 text-xs font-bold">
              🚚 2. Sotilgan / Olib Ketilgan Mahsulot
            </span>
            <h3 class="text-sm font-bold text-white">
              Buyurtma asosida yoki Shoshilinch (Srochniy) sotuv
            </h3>
            <div class="space-y-2.5 text-xs">
              <div class="grid grid-cols-2 gap-2 bg-slate-950 p-1.5 rounded-xl border border-slate-800">
                <button
                  @click="saleForm.sale_type = 'urgent_pickup'; saleForm.order_id = null"
                  :class="saleForm.sale_type === 'urgent_pickup' ? 'bg-amber-500 text-slate-950 font-bold' : 'text-slate-300'"
                  class="py-1.5 rounded-lg transition cursor-pointer"
                >
                  ⚡ Shoshilinch olib ketildi
                </button>
                <button
                  @click="saleForm.sale_type = 'order_fulfillment'"
                  :class="saleForm.sale_type === 'order_fulfillment' ? 'bg-emerald-600 text-white font-bold' : 'text-slate-300'"
                  class="py-1.5 rounded-lg transition cursor-pointer"
                >
                  📦 Buyurtma asosida
                </button>
              </div>

              <select
                v-if="saleForm.sale_type === 'order_fulfillment'"
                v-model="saleForm.order_id"
                @change="onSaleOrderSelect"
                class="w-full bg-slate-950 border border-emerald-500/50 rounded-xl px-3 py-2 text-white"
              >
                <option :value="null">-- Qaysi buyurtma bo'yicha? --</option>
                <option
                  v-for="o in store.orders.filter((x) => x.status !== 'completed')"
                  :key="o.id"
                  :value="o.id"
                >
                  {{ o.order_number }} - {{ o.customer_name }} ({{ o.product_name }}: {{ o.ordered_qty - o.delivered_qty }} ta qolgan)
                </option>
              </select>

              <input
                v-model="saleForm.customer_name"
                type="text"
                placeholder="Xaridor ismi"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              />
              <select
                v-model="saleForm.product_type_id"
                @change="onSaleProductChange"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              >
                <option v-for="p in store.products" :key="p.id" :value="p.id">
                  {{ p.name }} (Omborda: {{ p.stock_qty }} dona)
                </option>
              </select>

              <div class="grid grid-cols-3 gap-2">
                <div>
                  <label class="text-[11px] text-slate-400">Soni (dona)</label>
                  <input
                    v-model.number="saleForm.quantity"
                    @input="onSaleProductChange"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-white"
                  />
                </div>
                <div>
                  <label class="text-[11px] text-slate-400">Narxi</label>
                  <input
                    v-model.number="saleForm.unit_price"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-white"
                  />
                </div>
                <div>
                  <label class="text-[11px] text-slate-400">To'landi</label>
                  <input
                    v-model.number="saleForm.paid_amount"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-white"
                  />
                </div>
              </div>

              <button
                @click="submitSale"
                class="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-2.5 rounded-xl transition cursor-pointer"
              >
                Sotuvni Qayd Etish
              </button>
            </div>
          </div>

          <!-- Form 3: Missing / Requested Size Radar -->
          <div class="bg-slate-900 border border-purple-500/40 rounded-2xl p-5 space-y-3">
            <span class="px-2.5 py-1 rounded-lg bg-purple-500/20 text-purple-300 text-xs font-bold">
              📡 3. Korxonada Yo'q O'lcham So'rovi
            </span>
            <h3 class="text-sm font-bold text-white">
              Mavjud bo'lmagan o'lcham so'ralganda yozib olish
            </h3>
            <div class="space-y-2.5 text-xs">
              <input
                v-model="missingSizeForm.requested_size_name"
                type="text"
                placeholder="Qanday o'lcham so'raldi? (Masalan: 150-lik Kolodets)"
                class="w-full bg-slate-950 border border-purple-500/40 rounded-xl px-3 py-2 text-white"
              />
              <input
                v-model="missingSizeForm.dimensions_details"
                type="text"
                placeholder="O'lcham tafsiloti (Masalan: Ichki Ø150sm, qopqog'i bilan)"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              />
              <div class="grid grid-cols-2 gap-2">
                <input
                  v-model="missingSizeForm.customer_name"
                  type="text"
                  placeholder="So'ragan mijoz"
                  class="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                />
                <input
                  v-model="missingSizeForm.customer_phone"
                  type="text"
                  placeholder="Telefoni"
                  class="bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                />
              </div>
              <div class="grid grid-cols-2 gap-2">
                <div>
                  <label class="text-[11px] text-slate-400">Nechta kerak edi?</label>
                  <input
                    v-model.number="missingSizeForm.requested_qty"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-white"
                  />
                </div>
                <div>
                  <label class="text-[11px] text-slate-400">Taxminiy narxi (dona)</label>
                  <input
                    v-model.number="missingSizeForm.estimated_unit_price"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-white"
                  />
                </div>
              </div>
              <button
                @click="submitMissingSize"
                class="w-full bg-purple-600 hover:bg-purple-500 text-white font-bold py-2.5 rounded-xl transition cursor-pointer"
              >
                Talab Radariga Qo'shish
              </button>
            </div>
          </div>
        </div>

        <!-- Tables: Sales History & Missing Sizes Log -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <h3 class="text-sm font-bold text-white mb-3">
              Sotilgan Mahsulotlar (Buyurtma asosida vs Shoshilinch olib ketilgan)
            </h3>
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead class="text-slate-400 border-b border-slate-800">
                  <tr>
                    <th class="py-2 px-2">Sana</th>
                    <th class="py-2 px-2">Turi</th>
                    <th class="py-2 px-2">Mijoz</th>
                    <th class="py-2 px-2">Mahsulot</th>
                    <th class="py-2 px-2">Soni</th>
                    <th class="py-2 px-2">Summa</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/70">
                  <tr v-for="s in store.sales" :key="s.id">
                    <td class="py-2.5 px-2 text-slate-300">{{ s.sale_date }}</td>
                    <td class="py-2.5 px-2">
                      <span
                        :class="
                          s.sale_type === 'urgent_pickup'
                            ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                            : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                        "
                        class="px-2 py-0.5 rounded border text-[10px] font-bold"
                      >
                        {{ s.sale_type === 'urgent_pickup' ? '⚡ Shoshilinch' : `📦 Buyurtma (${s.order_number || ''})` }}
                      </span>
                    </td>
                    <td class="py-2.5 px-2 font-semibold text-white">{{ s.customer_name }}</td>
                    <td class="py-2.5 px-2 text-slate-300">{{ s.product_name }}</td>
                    <td class="py-2.5 px-2 font-bold text-white">{{ s.quantity }} ta</td>
                    <td class="py-2.5 px-2 font-bold text-emerald-400">{{ formatMoney(s.total_amount) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <h3 class="text-sm font-bold text-white mb-3">
              So'ralgan (Korxonada Mavjud Bo'lmagan) O'lchamlar Jurnali
            </h3>
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead class="text-slate-400 border-b border-slate-800">
                  <tr>
                    <th class="py-2 px-2">Sana</th>
                    <th class="py-2 px-2">So'ralgan O'lcham</th>
                    <th class="py-2 px-2">Tafsiloti</th>
                    <th class="py-2 px-2">Miqdori</th>
                    <th class="py-2 px-2">Yo'qotilgan Savdo</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/70">
                  <tr v-for="ms in store.missingSizes" :key="ms.id">
                    <td class="py-2.5 px-2 text-slate-400">{{ ms.request_date }}</td>
                    <td class="py-2.5 px-2 font-bold text-purple-300">{{ ms.requested_size_name }}</td>
                    <td class="py-2.5 px-2 text-slate-300">{{ ms.dimensions_details }}</td>
                    <td class="py-2.5 px-2 font-bold text-white">{{ ms.requested_qty }} dona</td>
                    <td class="py-2.5 px-2 font-bold text-amber-400">
                      {{ formatMoney(ms.requested_qty * ms.estimated_unit_price) }}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- ==================== TAB 5: RAW MATERIALS (SEMENT, SHAG'AL, SIM) ==================== -->
      <div v-if="activeTab === 'materials'" class="space-y-6">
        <div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
          <!-- Left: Add New Batch Form -->
          <div class="lg:col-span-4 bg-slate-900 border border-slate-800 rounded-2xl p-5 space-y-3 h-fit">
            <h3 class="text-base font-bold text-white">
              Yangi Xomashyo Partiyasi Keldi (Kirim)
            </h3>
            <p class="text-xs text-slate-400">
              Sement, shag'al yoki beton simi qachon va qanchadan olinganini kiriting:
            </p>
            <div class="space-y-2.5 text-xs">
              <div>
                <label class="text-slate-400 block mb-1">Xomashyo turi</label>
                <select
                  v-model="matForm.material_type"
                  class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-semibold"
                >
                  <option value="cement">🧱 Sement (kg)</option>
                  <option value="gravel">🪨 Shag'al / Qum (kg)</option>
                  <option value="wire">➰ Beton ichiga Sim / Armatura (kg)</option>
                </select>
              </div>
              <div class="grid grid-cols-2 gap-2">
                <div>
                  <label class="text-slate-400 block mb-1">Partiya kodi</label>
                  <input
                    v-model="matForm.batch_code"
                    type="text"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                  />
                </div>
                <div>
                  <label class="text-slate-400 block mb-1">Kelgan sanasi</label>
                  <input
                    v-model="matForm.arrived_date"
                    type="date"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                  />
                </div>
              </div>
              <div>
                <label class="text-slate-400 block mb-1">Nomi va markasi</label>
                <input
                  v-model="matForm.material_name"
                  type="text"
                  class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
                />
              </div>
              <div class="grid grid-cols-2 gap-2">
                <div>
                  <label class="text-slate-400 block mb-1">Miqdori (kg)</label>
                  <input
                    v-model.number="matForm.initial_quantity"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-bold"
                  />
                </div>
                <div>
                  <label class="text-slate-400 block mb-1">1 kg narxi (so'm)</label>
                  <input
                    v-model.number="matForm.unit_price"
                    type="number"
                    class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-bold"
                  />
                </div>
              </div>
              <div class="bg-slate-950 p-3 rounded-xl border border-slate-800 flex justify-between">
                <span class="text-slate-400">Jami partiya summasi:</span>
                <span class="font-black text-amber-400">
                  {{ formatMoney(matForm.initial_quantity * matForm.unit_price) }}
                </span>
              </div>
              <button
                @click="submitMaterialBatch"
                class="w-full bg-blue-600 hover:bg-blue-500 text-white font-bold py-2.5 rounded-xl transition cursor-pointer"
              >
                + Partiyani Ro'yxatga Olish
              </button>
            </div>
          </div>

          <!-- Right: Batches Lifecycle Table ("Qachon keldi -> Qachon tugadi") -->
          <div class="lg:col-span-8 bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <h3 class="text-base font-bold text-white mb-1">
              Sement, Shag'al va Sim Partiyalari ("Qachon keldi — Qachon tugadi" Tahlili)
            </h3>
            <p class="text-xs text-slate-400 mb-4">
              Har bir partiya kelgan kundan tugagan kungacha nechta ariq va kolodets chiqqani avtomatik hisoblanadi.
            </p>
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead class="text-slate-400 border-b border-slate-800 bg-slate-950/60">
                  <tr>
                    <th class="py-2.5 px-3">Partiya / Xomashyo</th>
                    <th class="py-2.5 px-3">Qachon Keldi</th>
                    <th class="py-2.5 px-3">Qachon Tugadi</th>
                    <th class="py-2.5 px-3">Kelgan Miqdor va Qoldiq</th>
                    <th class="py-2.5 px-3">Narxi va Jami Summa</th>
                    <th class="py-2.5 px-3">Shu Partiyada Chiqqan Mahsulot</th>
                    <th class="py-2.5 px-3">Amal</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/70">
                  <tr v-for="b in store.materials" :key="b.id">
                    <td class="py-3 px-3">
                      <div class="font-bold text-white">{{ b.batch_code }} — {{ b.material_name }}</div>
                      <div class="text-[11px] text-slate-400">{{ b.supplier }}</div>
                    </td>
                    <td class="py-3 px-3 font-semibold text-emerald-400">{{ b.arrived_date }}</td>
                    <td class="py-3 px-3">
                      <span v-if="b.depleted_date" class="font-semibold text-amber-400">{{ b.depleted_date }}</span>
                      <span v-else class="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 text-[11px] font-bold">
                        Ishlatilmoqda
                      </span>
                    </td>
                    <td class="py-3 px-3">
                      <div class="font-bold text-white">
                        {{ b.remaining_quantity }} / {{ b.initial_quantity }} {{ b.unit }}
                      </div>
                      <div class="w-28 h-1.5 bg-slate-800 rounded-full overflow-hidden mt-1">
                        <div
                          class="h-full bg-blue-500"
                          :style="{ width: Math.min(100, (b.remaining_quantity / b.initial_quantity) * 100) + '%' }"
                        ></div>
                      </div>
                    </td>
                    <td class="py-3 px-3">
                      <div class="font-bold text-white">{{ formatMoney(b.total_cost) }}</div>
                      <div class="text-[11px] text-slate-400">1 {{ b.unit }} = {{ formatMoney(b.unit_price) }}</div>
                    </td>
                    <td class="py-3 px-3">
                      <span class="font-bold text-sky-400">{{ b.produced_units_in_period }} dona</span>
                      <span class="block text-[10px] text-slate-400">ariq va kolodets</span>
                    </td>
                    <td class="py-3 px-3">
                      <button
                        v-if="b.status === 'active'"
                        @click="markDepleted(b)"
                        class="px-2.5 py-1 rounded-lg bg-amber-500/20 hover:bg-amber-500 hover:text-slate-950 text-amber-300 border border-amber-500/40 font-bold text-[11px] transition cursor-pointer"
                      >
                        Bugun Tugadi deb belgilash
                      </button>
                      <span v-else class="text-slate-500 text-[11px]">Yopilgan</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      <!-- ==================== TAB 6: FINANCE & SMART ADVISOR ==================== -->
      <div v-if="activeTab === 'analytics'" class="space-y-6">
        <!-- Financial Summary Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div class="bg-slate-900 border border-emerald-500/30 rounded-2xl p-5">
            <div class="text-xs text-slate-400">Jami Sotuv Tushumi (Kirim)</div>
            <div class="text-2xl font-black text-emerald-400 mt-1">
              {{ formatMoney(store.analytics.financials.total_sales_revenue) }}
            </div>
            <div class="text-xs text-slate-400 mt-1">
              Buyurtma asosida: {{ formatMoney(store.analytics.financials.order_fulfillment_sales?.amount) }}
            </div>
          </div>

          <div class="bg-slate-900 border border-amber-500/30 rounded-2xl p-5">
            <div class="text-xs text-amber-300">Shoshilinch (Srochniy) Savdo Ulushi</div>
            <div class="text-2xl font-black text-amber-400 mt-1">
              {{ formatMoney(store.analytics.financials.urgent_pickup_sales?.amount) }}
            </div>
            <div class="text-xs text-slate-400 mt-1">
              {{ store.analytics.financials.urgent_pickup_sales?.qty || 0 }} dona tayyor zaxiradan olib ketildi
            </div>
          </div>

          <div class="bg-slate-900 border border-red-500/30 rounded-2xl p-5">
            <div class="text-xs text-slate-400">Jami Xarajatlar (Chiqim)</div>
            <div class="text-2xl font-black text-red-400 mt-1">
              {{ formatMoney(store.analytics.financials.total_expenses) }}
            </div>
            <div class="text-[11px] text-slate-400 mt-1">
              Xomashyo: {{ formatMoney(store.analytics.financials.material_expenses) }} • Usta: {{ formatMoney(store.analytics.financials.labor_expenses) }}
            </div>
          </div>

          <div class="bg-slate-900 border border-blue-500/40 rounded-2xl p-5">
            <div class="text-xs text-blue-300">Pulni Qayerga Yo'naltirish Kerak?</div>
            <div class="text-xl font-black text-white mt-1">
              {{ store.analytics.recommendations.length }} ta Strategik Yo'nalish
            </div>
            <div class="text-xs text-blue-400 mt-1">Quyidagi aqlli tavsiyalarni ko'ring ↓</div>
          </div>
        </div>

        <!-- Smart Advisor: "Pulni Qayerga Yo'naltirish Kerak?" -->
        <div class="bg-gradient-to-br from-slate-900 via-slate-900 to-blue-950/40 border border-blue-500/40 rounded-2xl p-6 space-y-4">
          <div>
            <span class="px-2.5 py-1 rounded-full bg-blue-500/20 text-blue-300 text-xs font-bold border border-blue-500/30">
              🧠 Smart Investment Advisor
            </span>
            <h2 class="text-lg font-black text-white mt-2">
              Pulni Qayerga Yo'naltirish Kerak? (Korxona Loglari Asosida Avtomatik Tahlil)
            </h2>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div
              v-for="(rec, idx) in store.analytics.recommendations"
              :key="idx"
              class="bg-slate-950/90 border border-slate-800 rounded-xl p-4 space-y-2"
            >
              <div class="flex items-center justify-between">
                <span class="px-2.5 py-0.5 rounded bg-blue-500/20 text-blue-300 text-xs font-bold">
                  {{ rec.category }}
                </span>
                <span class="text-xs font-bold text-amber-400">
                  Tavsiya byudjeti: ~{{ formatMoney(rec.estimated_budget) }}
                </span>
              </div>
              <h4 class="text-sm font-bold text-white">{{ rec.title }}</h4>
              <p class="text-xs text-slate-300 leading-relaxed">{{ rec.action }}</p>
            </div>
          </div>
        </div>

        <!-- Demand Ranking by Product Size -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <h3 class="text-sm font-bold text-white mb-3">
              Mavjud O'lchamlarga Talab Reytingi (Qaysi mahsulot eng ko'p pul keltiryapti?)
            </h3>
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead class="text-slate-400 border-b border-slate-800">
                  <tr>
                    <th class="py-2 px-2">O'lcham</th>
                    <th class="py-2 px-2">Sotildi</th>
                    <th class="py-2 px-2">Shoshilinch</th>
                    <th class="py-2 px-2">Navbatda</th>
                    <th class="py-2 px-2">Tushum</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/70">
                  <tr v-for="pd in store.analytics.product_demand" :key="pd.id">
                    <td class="py-2.5 px-2 font-bold text-white">{{ pd.name }}</td>
                    <td class="py-2.5 px-2 font-bold text-emerald-400">{{ pd.sold_qty }} dona</td>
                    <td class="py-2.5 px-2 text-amber-300">{{ pd.urgent_sold_qty }} dona</td>
                    <td class="py-2.5 px-2 font-bold text-blue-400">{{ pd.pending_order_qty }} dona</td>
                    <td class="py-2.5 px-2 font-bold text-white">{{ formatMoney(pd.revenue) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5">
            <h3 class="text-sm font-bold text-white mb-3">
              Yangi O'lchamlar Talabi (Mavjud bo'lmagan o'lchamlar bo'yicha yo'qotilgan daromad)
            </h3>
            <div class="overflow-x-auto">
              <table class="w-full text-left text-xs">
                <thead class="text-slate-400 border-b border-slate-800">
                  <tr>
                    <th class="py-2 px-2">So'ralgan Yangi O'lcham</th>
                    <th class="py-2 px-2">So'rovlar Soni</th>
                    <th class="py-2 px-2">Jami Dona</th>
                    <th class="py-2 px-2">Potensial Savdo</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-800/70">
                  <tr v-for="(md, i) in store.analytics.missing_demand" :key="i">
                    <td class="py-2.5 px-2 font-bold text-purple-300">{{ md.requested_size_name }}</td>
                    <td class="py-2.5 px-2 text-slate-300">{{ md.request_count }} marta</td>
                    <td class="py-2.5 px-2 font-bold text-white">{{ md.total_requested_qty }} dona</td>
                    <td class="py-2.5 px-2 font-bold text-amber-400">{{ formatMoney(md.potential_revenue) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- ==================== MODAL: SETTINGS (REGION & WORKSHOP DIMENSIONS) ==================== -->
    <div
      v-if="settingsModal"
      class="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div class="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4">
        <h3 class="text-base font-bold text-white">⚙️ Korxona va Ob-havo Hududi Sozlamalari</h3>
        <div class="space-y-3 text-xs">
          <div>
            <label class="text-slate-400 block mb-1">Korxona nomi</label>
            <input
              v-model="settingsForm.company_name"
              type="text"
              class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
            />
          </div>
          <div>
            <label class="text-slate-400 block mb-1">Hudud (Avtomatik Ob-havo Logi uchun)</label>
            <select
              v-model="settingsForm.region_id"
              class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white font-semibold"
            >
              <option v-for="r in store.regions" :key="r.id" :value="r.id">
                {{ r.name }} (GPS: {{ r.lat }}, {{ r.lon }})
              </option>
            </select>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="text-slate-400 block mb-1">Sex Eni (metr)</label>
              <input
                v-model.number="settingsForm.workshop_width_m"
                type="number"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              />
            </div>
            <div>
              <label class="text-slate-400 block mb-1">Sex Bo'yi (metr)</label>
              <input
                v-model.number="settingsForm.workshop_length_m"
                type="number"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              />
            </div>
          </div>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button
            @click="settingsModal = false"
            class="px-4 py-2 rounded-xl bg-slate-800 text-xs text-slate-300"
          >
            Bekor qilish
          </button>
          <button
            @click="saveSettings"
            class="px-4 py-2 rounded-xl bg-blue-600 text-xs font-bold text-white"
          >
            Saqlash
          </button>
        </div>
      </div>
    </div>

    <!-- ==================== MODAL: ADD NEW MOLD ==================== -->
    <div
      v-if="newMoldModal"
      class="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div class="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-4">
        <h3 class="text-base font-bold text-white">+ Sexga Yangi Raqamlangan Qolip Qo'shish</h3>
        <div class="space-y-3 text-xs">
          <div>
            <label class="text-slate-400 block mb-1">Qolip raqami</label>
            <input
              v-model="newMoldForm.mold_number"
              type="text"
              placeholder="#27 (A30)"
              class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
            />
          </div>
          <div>
            <label class="text-slate-400 block mb-1">Qaysi o'lcham?</label>
            <select
              v-model.number="newMoldForm.product_type_id"
              class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
            >
              <option v-for="p in store.products" :key="p.id" :value="p.id">{{ p.name }}</option>
            </select>
          </div>
          <div class="grid grid-cols-3 gap-2">
            <div>
              <label class="text-slate-400 block mb-1">X (m)</label>
              <input
                v-model.number="newMoldForm.pos_x"
                type="number"
                step="0.2"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              />
            </div>
            <div>
              <label class="text-slate-400 block mb-1">Z (m)</label>
              <input
                v-model.number="newMoldForm.pos_z"
                type="number"
                step="0.2"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              />
            </div>
            <div>
              <label class="text-purple-300 font-bold block mb-1">Qavati (1/2/3)</label>
              <select
                v-model.number="newMoldForm.stack_tier"
                class="w-full bg-slate-950 border border-purple-500/50 rounded-xl px-3 py-2 text-white"
              >
                <option :value="1">1-Qavat (Yerda)</option>
                <option :value="2">2-Qavat (Ustma-ust)</option>
                <option :value="3">3-Qavat (Ustma-ust)</option>
              </select>
            </div>
          </div>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button @click="newMoldModal = false" class="px-4 py-2 rounded-xl bg-slate-800 text-xs text-slate-300">
            Bekor qilish
          </button>
          <button @click="submitNewMold" class="px-4 py-2 rounded-xl bg-blue-600 text-xs font-bold text-white">
            Qo'shish
          </button>
        </div>
      </div>
    </div>

    <!-- ==================== MODAL: ADD NEW PRODUCT SIZE ==================== -->
    <div
      v-if="newProductModal"
      class="fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4"
    >
      <div class="bg-slate-900 border border-slate-700 rounded-2xl max-w-lg w-full p-6 space-y-4">
        <h3 class="text-base font-bold text-white">+ Katalogga Yangi O'lcham Qo'shish</h3>
        <div class="space-y-3 text-xs">
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="text-slate-400 block mb-1">Kodi (masalan: A60, K150)</label>
              <input
                v-model="newProductForm.code"
                type="text"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              />
            </div>
            <div>
              <label class="text-slate-400 block mb-1">Toifasi</label>
              <select
                v-model="newProductForm.category"
                class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
              >
                <option value="ariq">Beton Ariq (Lotok)</option>
                <option value="kolodets">Kolodets (Quduq xalqasi)</option>
              </select>
            </div>
          </div>
          <div>
            <label class="text-slate-400 block mb-1">Nomi</label>
            <input
              v-model="newProductForm.name"
              type="text"
              class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-2 text-white"
            />
          </div>
          <div v-if="newProductForm.category === 'ariq'" class="grid grid-cols-4 gap-2">
            <div>
              <label class="text-slate-400 block mb-1">Tagi (sm)</label>
              <input v-model.number="newProductForm.inner_bottom_cm" type="number" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-2 py-1.5 text-white" />
            </div>
            <div>
              <label class="text-slate-400 block mb-1">Yoni (sm)</label>
              <input v-model.number="newProductForm.inner_side_cm" type="number" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-2 py-1.5 text-white" />
            </div>
            <div>
              <label class="text-slate-400 block mb-1">Og'zi (sm)</label>
              <input v-model.number="newProductForm.inner_top_cm" type="number" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-2 py-1.5 text-white" />
            </div>
            <div>
              <label class="text-slate-400 block mb-1">Qalinligi (sm)</label>
              <input v-model.number="newProductForm.wall_thickness_cm" type="number" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-2 py-1.5 text-white" />
            </div>
          </div>
          <div v-else class="grid grid-cols-3 gap-2">
            <div>
              <label class="text-slate-400 block mb-1">Tashqi Ø (sm)</label>
              <input v-model.number="newProductForm.outer_diameter_cm" type="number" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-2 py-1.5 text-white" />
            </div>
            <div>
              <label class="text-slate-400 block mb-1">Ichki Ø (sm)</label>
              <input v-model.number="newProductForm.inner_diameter_cm" type="number" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-2 py-1.5 text-white" />
            </div>
            <div>
              <label class="text-slate-400 block mb-1">Balandlik (sm)</label>
              <input v-model.number="newProductForm.max_height_cm" type="number" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-2 py-1.5 text-white" />
            </div>
          </div>
          <div class="grid grid-cols-2 gap-2">
            <div>
              <label class="text-slate-400 block mb-1">Quyish narxi (Usta haqi)</label>
              <input v-model.number="newProductForm.casting_labor_cost" type="number" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-white" />
            </div>
            <div>
              <label class="text-slate-400 block mb-1">Sotish narxi</label>
              <input v-model.number="newProductForm.selling_price" type="number" class="w-full bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-white" />
            </div>
          </div>
        </div>
        <div class="flex justify-end gap-2 pt-2">
          <button @click="newProductModal = false" class="px-4 py-2 rounded-xl bg-slate-800 text-xs text-slate-300">
            Bekor qilish
          </button>
          <button @click="submitNewProduct" class="px-4 py-2 rounded-xl bg-blue-600 text-xs font-bold text-white">
            Saqlash
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
