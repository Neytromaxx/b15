<script setup>
import { ref, onMounted, onBeforeUnmount, watch, computed } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { useErpStore } from '../stores/erpStore'

const store = useErpStore()
const containerRef = ref(null)

// ---------------- MATHEMATICAL YARD DIMENSIONS (FROM USER SPECIFICATION) ----------------
// Eshikdan oxiriga qadar (shlakoblokli devor) = 16.5m
// Yon devorlar orasi: Eshik tomon (Z=0) = 7.0m, Oxiri (Z=16.5m) = 8.2m
// Ikki yondagi Tal relslari orasi = 6.0m (X = -3.0m va X = +3.0m)
const yardDims = ref({
  length_m: 16.5,
  width_front_m: 7.0,
  width_back_m: 8.2,
  rail_gauge_m: 6.0,
})

watch(
  () => store.settings,
  (s) => {
    if (s) {
      yardDims.value.length_m = Number(s.workshop_length_m || 16.5)
      yardDims.value.width_front_m = Number(s.workshop_width_front_m || s.workshop_width_m || 7.0)
      yardDims.value.width_back_m = Number(s.workshop_width_back_m || 8.2)
      yardDims.value.rail_gauge_m = Number(s.rail_gauge_m || 6.0)
    }
  },
  { immediate: true, deep: true }
)

function getYardWidthAtZ(z) {
  const L = yardDims.value.length_m || 16.5
  const wf = yardDims.value.width_front_m || 7.0
  const wb = yardDims.value.width_back_m || 8.2
  const clampedZ = Math.max(0, Math.min(L, Number(z || 0)))
  return wf + ((wb - wf) * clampedZ) / L
}

function zToWorld(z) {
  const L = yardDims.value.length_m || 16.5
  return Number(z || 0) - L / 2
}

function worldToZ(wz) {
  const L = yardDims.value.length_m || 16.5
  return Number(wz || 0) + L / 2
}

// Interactive 3D Controls
const explodeFactor = ref(0.05)
const activeTierFilter = ref(0)
const statusFilter = ref('all')
const colorMode = ref('realistic')
const lightingMode = ref('daylight')
const activeCameraPreset = ref('overview')
const showLabels = ref(true)
const showWallMode = ref('low')
const snapStepM = ref(0.05) // 0.05m = 5sm qadam, yoki 0.01m = 1sm aniq qadam

// Live 3D Mathematical Cursor on Floor
const cursorPoint = ref({
  x: 0.0,
  z: 2.5,
  widthAtZ: 7.18,
  distFromLeftWall: 3.59,
  distFromRightWall: 3.59,
  distFromLeftRail: 3.0,
  distFromRightRail: 3.0,
})

// ---------------- 3D DRAG-AND-DROP & LIVE GHOST SPAWN PALETTE ----------------
// Palette items that the user can click to summon into 3D (following mouse) OR drag-and-drop onto canvas!
const paletteCatalog = [
  { id: 'stoyka_pair', label: '🧱 2 ta Stoyka (Qator tagligi)', category: 'stoyka', isPair: true, color: 'border-amber-500/60 bg-amber-500/15 text-amber-200' },
  { id: 'stoyka_single', label: '🧱 1 ta Stoyka (Brusok)', category: 'stoyka', isPair: false, color: 'border-amber-500/40 bg-slate-800 text-amber-300' },
  { id: 'mold_A22', label: '🟦 22-lik Qolip', category: 'mold', code: 'A22', color: 'border-sky-500/50 bg-sky-500/15 text-sky-200' },
  { id: 'mold_A30', label: '🟦 30-lik Qolip', category: 'mold', code: 'A30', color: 'border-blue-500/50 bg-blue-500/15 text-blue-200' },
  { id: 'mold_A40', label: '🟪 40-lik Qolip', category: 'mold', code: 'A40', color: 'border-indigo-500/50 bg-indigo-500/15 text-indigo-200' },
  { id: 'mold_A50', label: '🟪 50-lik Qolip', category: 'mold', code: 'A50', color: 'border-purple-500/50 bg-purple-500/15 text-purple-200' },
  { id: 'mold_K104', label: '🟡 Kolodets Qolipi', category: 'mold', code: 'K104', color: 'border-amber-500/50 bg-amber-500/15 text-amber-200' },
  { id: 'tal_crane', label: '🏗️ Tal (6m Kran)', category: 'tal_crane', color: 'border-orange-500/50 bg-orange-500/15 text-orange-200' },
  { id: 'meshalka', label: '⚙️ Meshalka', category: 'meshalka', color: 'border-teal-500/50 bg-teal-500/15 text-teal-200' },
  { id: 'vibrator', label: '📳 Vibrator', category: 'vibrator', color: 'border-emerald-500/50 bg-emerald-500/15 text-emerald-200' },
]

const activeSpawnTool = ref(null) // Currently summoned palette item following mouse in 3D
const spawnRotationDeg = ref(0)
const spawnTier = ref(1) // 1 = 1-qavat, 2 = 2-qavat (ustma-ust)
const keepSpawningMulti = ref(true) // Keep tool active after click so user can place multiple items quickly
const autoStackOnHover = ref(true) // Automatically jump to 2-qavat when hovering over an existing 1-qavat mold

// Direct 3D dragging state (for grabbing and dragging already placed 3D elements)
const isDraggingExisting = ref(false)
const draggedItemInfo = ref(null) // { kind: 'mold'|'element', data: obj, group: THREE.Group, startX, startZ, moved: false }

// ---------------- UNIVERSAL "+ ELEMENT QO'SHISH" FORM STATE (FOR MATHEMATICAL BATCH/EXACT INPUT) ----------------
const showAddPanel = ref(false)
const addCategory = ref('stoyka')
const xRefMode = ref('center')
const xInputVal = ref(0.0)

const addForm = ref({
  pos_z: 2.5,
  pos_x: 0.0,
  pos_y: 0.0,
  rotation_deg: 0,
  notes: '',

  stoyka_is_pair: true,
  stoyka_row_width_m: 5.8,
  stoyka_pair_spacing_m: 1.45,
  stoyka_beam_w_cm: 16,
  stoyka_beam_h_cm: 14,
  stoyka_name: '1-Qator Taglik Stoykalar (2 ta)',

  mold_code: 'A30',
  mold_number: '',
  mold_zone: '1-Qator',
  mold_tier: 1,
  mold_status: 'empty',

  row_mold_code: 'A30',
  row_count: 6,
  row_gap_cm: 8,
  row_align: 'center',
  row_start_x: -2.4,
  row_add_stoyka_pair: true,

  crane_span_m: 6.0,
  crane_height_m: 3.0,
  crane_hoist_x: 0.0,

  rails_gauge_m: 6.0,
  rails_z_start: 0.0,
  rails_z_end: 16.5,

  equip_length_m: 1.3,
  equip_width_m: 1.1,
  equip_height_m: 1.4,
})

function syncPosXFromInput() {
  const z = Number(addForm.value.pos_z || 0)
  const wAtZ = getYardWidthAtZ(z)
  const halfRail = (yardDims.value.rail_gauge_m || 6.0) / 2
  const val = Number(xInputVal.value || 0)

  if (xRefMode.value === 'center') {
    addForm.value.pos_x = Number(val.toFixed(3))
  } else if (xRefMode.value === 'left_rail') {
    addForm.value.pos_x = Number((-halfRail + val).toFixed(3))
  } else if (xRefMode.value === 'left_wall') {
    addForm.value.pos_x = Number((-wAtZ / 2 + val).toFixed(3))
  }
}

function setPosXAndSyncInput(newPosX, zVal = null) {
  const z = zVal !== null ? Number(zVal) : Number(addForm.value.pos_z || 0)
  const wAtZ = getYardWidthAtZ(z)
  const halfRail = (yardDims.value.rail_gauge_m || 6.0) / 2
  addForm.value.pos_x = Number(Number(newPosX).toFixed(2))

  if (xRefMode.value === 'center') {
    xInputVal.value = addForm.value.pos_x
  } else if (xRefMode.value === 'left_rail') {
    xInputVal.value = Number((addForm.value.pos_x + halfRail).toFixed(2))
  } else if (xRefMode.value === 'left_wall') {
    xInputVal.value = Number((addForm.value.pos_x + wAtZ / 2).toFixed(2))
  }
}

watch([xInputVal, xRefMode, () => addForm.value.pos_z], () => {
  syncPosXFromInput()
})

const rowMathPreview = computed(() => {
  const prod = store.products.find((p) => p.code === addForm.value.row_mold_code)
  let moldW = 0.49
  if (prod) {
    if (prod.category === 'kolodets') {
      moldW = (prod.outer_diameter_cm || 118) / 100
    } else {
      moldW = (prod.inner_top_cm || 30) / 100 + (2 * (prod.wall_thickness_cm || 5.5)) / 100 + 0.08
    }
  }
  const count = Math.max(1, Number(addForm.value.row_count || 1))
  const gapM = Math.max(0, Number(addForm.value.row_gap_cm || 0) / 100)
  const stepM = moldW + gapM
  const totalWidthM = count * moldW + (count - 1) * gapM
  const yardW = getYardWidthAtZ(addForm.value.pos_z)
  const railW = yardDims.value.rail_gauge_m || 6.0
  return {
    moldWidthCm: Math.round(moldW * 100),
    stepCm: Math.round(stepM * 100),
    totalWidthM: totalWidthM.toFixed(2),
    yardWidthAtZ: yardW.toFixed(2),
    railGaugeM: railW.toFixed(2),
    fitsInsideRails: totalWidthM <= railW,
    fitsInsideWalls: totalWidthM <= yardW - 0.2,
  }
})

function openQuickAdd(cat, moldCode = null) {
  showAddPanel.value = true
  addCategory.value = cat
  if (moldCode) {
    addForm.value.mold_code = moldCode
    addForm.value.row_mold_code = moldCode
  }
}

// Activate 3D Live Summon / Ghost Spawn Tool
function selectSpawnTool(tool) {
  if (activeSpawnTool.value && activeSpawnTool.value.id === tool.id) {
    activeSpawnTool.value = null
    rebuildGhostPreview()
    return
  }
  activeSpawnTool.value = tool
  spawnTier.value = 1
  store.selectedMold = null
  store.selectedElement = null
  rebuildGhostPreview()
}

function cancelSpawnTool() {
  activeSpawnTool.value = null
  rebuildGhostPreview()
}

function rotateSpawnOrSelected(deltaDeg = 90) {
  if (activeSpawnTool.value) {
    spawnRotationDeg.value = (spawnRotationDeg.value + deltaDeg) % 360
    updateGhostPosition()
  } else if (editItemForm.value.kind) {
    editItemForm.value.rotation_deg = (Number(editItemForm.value.rotation_deg || 0) + deltaDeg) % 360
    saveSelectedEdit()
  }
}

// Place a palette item at exact (x, z) coordinates in 3D space!
async function placePaletteItemAt(tool, x, z) {
  if (!tool) return
  const pz = Number(z.toFixed(2))
  const px = Number(x.toFixed(2))

  if (tool.category === 'stoyka') {
    const isPair = tool.isPair
    const spacingM = Number(addForm.value.stoyka_pair_spacing_m || 1.45)
    const rowWidthM = isPair ? Number(addForm.value.stoyka_row_width_m || 5.8) : 2.2
    const beamWM = 0.16
    const beamHM = 0.14
    const stoykaCount = store.workshopElements.filter((e) => e.element_type === 'stoyka').length + 1
    await store.createWorkshopElement({
      element_type: 'stoyka',
      name: isPair ? `${stoykaCount}-Qator 2 ta Stoyka (Brusok)` : `Stoyka #${stoykaCount} (Brusok)`,
      pos_x: isPair ? 0.0 : px,
      pos_z: pz,
      pos_y: 0.0,
      rotation_deg: spawnRotationDeg.value,
      length_m: isPair ? spacingM : beamWM,
      width_m: rowWidthM,
      height_m: beamHM,
      extra_json: JSON.stringify({
        is_pair: isPair,
        pair_spacing_m: spacingM,
        beam_width_m: beamWM,
        beam_height_m: beamHM,
      }),
      notes: `3D makonda joylandi: Eshikdan Z=${pz}m, X=${isPair ? 0 : px}m`,
    })
  } else if (tool.category === 'mold') {
    const prod = store.products.find((p) => p.code === tool.code) || store.products[0]
    if (!prod) return

    // Check if hovered over an existing 1-qavat mold to automatically stack on 2-qavat!
    let targetTier = spawnTier.value
    if (autoStackOnHover.value && targetTier === 1) {
      const underMold = findMoldUnderPoint(px, pz)
      if (underMold) {
        targetTier = Math.min(3, (underMold.stack_tier || 1) + 1)
      }
    }

    const nextNum = store.molds.length + 1
    let moldNum = `#${String(nextNum).padStart(2, '0')} (${prod.code})`
    let suffix = 0
    while (store.molds.some((m) => m.mold_number === moldNum)) {
      suffix++
      moldNum = `#${String(nextNum + suffix).padStart(2, '0')} (${prod.code})`
    }

    await store.createMold({
      mold_number: moldNum,
      product_type_id: prod.id,
      zone: `Z=${pz}m Qator`,
      pos_x: px,
      pos_z: pz,
      stack_tier: targetTier,
      rotation_deg: spawnRotationDeg.value,
      status: 'empty',
      notes: `3D makonda joylandi: Eshikdan Z=${pz}m, Markazdan X=${px}m (${targetTier}-qavat)`,
    })
  } else if (tool.category === 'tal_crane') {
    await store.createWorkshopElement({
      element_type: 'tal_crane',
      name: `Talning o'zi (A-ramali Ko'targich, ${yardDims.value.rail_gauge_m}m)`,
      pos_x: 0.0,
      pos_z: pz,
      pos_y: 0.0,
      rotation_deg: 0,
      length_m: 1.4,
      width_m: Number(yardDims.value.rail_gauge_m || 6.0),
      height_m: 3.0,
      extra_json: JSON.stringify({ hoist_x: px }),
      notes: `Rels ustida Eshikdan Z=${pz}m masofada`,
    })
  } else if (tool.category === 'meshalka') {
    await store.createWorkshopElement({
      element_type: 'meshalka',
      name: 'Meshalka (Beton qorgich)',
      pos_x: px,
      pos_z: pz,
      pos_y: 0.0,
      rotation_deg: spawnRotationDeg.value,
      length_m: 1.4,
      width_m: 1.3,
      height_m: 1.65,
      extra_json: '{}',
      notes: `3D makonda joylandi: Eshikdan Z=${pz}m, X=${px}m`,
    })
  } else if (tool.category === 'vibrator') {
    await store.createWorkshopElement({
      element_type: 'vibrator',
      name: 'Vibrator (4-prujinali Vibrostol)',
      pos_x: px,
      pos_z: pz,
      pos_y: 0.0,
      rotation_deg: spawnRotationDeg.value,
      length_m: 1.35,
      width_m: 1.1,
      height_m: 0.35,
      extra_json: '{}',
      notes: `3D makonda joylandi: Eshikdan Z=${pz}m, X=${px}m`,
    })
  }

  if (!keepSpawningMulti.value) {
    activeSpawnTool.value = null
    rebuildGhostPreview()
  }
}

// HTML5 Drag & Drop handlers from palette buttons directly onto the 3D WebGL Canvas!
let draggedPaletteTool = null
function onPaletteDragStart(event, tool) {
  draggedPaletteTool = tool
  activeSpawnTool.value = tool
  rebuildGhostPreview()
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'copy'
    event.dataTransfer.setData('text/plain', tool.id)
  }
}

function onCanvasDragOver(event) {
  event.preventDefault()
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy'
  }
  updatePointerAndGroundPoint(event)
}

async function onCanvasDrop(event) {
  event.preventDefault()
  updatePointerAndGroundPoint(event)
  const tool = draggedPaletteTool || activeSpawnTool.value
  if (tool) {
    await placePaletteItemAt(tool, cursorPoint.value.x, cursorPoint.value.z)
    draggedPaletteTool = null
  }
}

async function submitAddElement() {
  const z = Number(addForm.value.pos_z || 0)
  const x = Number(addForm.value.pos_x || 0)

  if (addCategory.value === 'stoyka') {
    const isPair = addForm.value.stoyka_is_pair
    const spacingM = Number(addForm.value.stoyka_pair_spacing_m || 1.45)
    const rowWidthM = Number(addForm.value.stoyka_row_width_m || 5.8)
    const beamWM = Number(addForm.value.stoyka_beam_w_cm || 16) / 100
    const beamHM = Number(addForm.value.stoyka_beam_h_cm || 14) / 100
    await store.createWorkshopElement({
      element_type: 'stoyka',
      name: addForm.value.stoyka_name || (isPair ? `2 ta Stoyka (Z=${z}m)` : `Stoyka (Z=${z}m)`),
      pos_x: x,
      pos_z: z,
      pos_y: 0.0,
      rotation_deg: Number(addForm.value.rotation_deg || 0),
      length_m: isPair ? spacingM : beamWM,
      width_m: rowWidthM,
      height_m: beamHM,
      extra_json: JSON.stringify({
        is_pair: isPair,
        pair_spacing_m: spacingM,
        beam_width_m: beamWM,
        beam_height_m: beamHM,
      }),
      notes: `Eshikdan Z=${z}m, Markazdan X=${x}m, Kengligi=${rowWidthM}m`,
    })
  } else if (addCategory.value === 'mold_single') {
    const prod = store.products.find((p) => p.code === addForm.value.mold_code) || store.products[0]
    if (!prod) return
    const nextNum = store.molds.length + 1
    const moldNum =
      addForm.value.mold_number.trim() || `#${String(nextNum).padStart(2, '0')} (${prod.code})`
    await store.createMold({
      mold_number: moldNum,
      product_type_id: prod.id,
      zone: addForm.value.mold_zone || `Z=${z}m Qator`,
      pos_x: x,
      pos_z: z,
      stack_tier: Number(addForm.value.mold_tier || 1),
      rotation_deg: Number(addForm.value.rotation_deg || 0),
      status: addForm.value.mold_status || 'empty',
      notes: addForm.value.notes || `Eshikdan Z=${z}m, Markazdan X=${x}m`,
    })
    addForm.value.mold_number = ''
  } else if (addCategory.value === 'mold_row') {
    const prod = store.products.find((p) => p.code === addForm.value.row_mold_code) || store.products[0]
    if (!prod) return
    await store.createBatchRowMolds({
      product_type_id: prod.id,
      count: Number(addForm.value.row_count || 4),
      zone: addForm.value.mold_zone || `Qator (Z=${z}m)`,
      pos_z: z,
      start_x: addForm.value.row_align === 'from_x' ? Number(addForm.value.row_start_x) : null,
      gap_m: Number(addForm.value.row_gap_cm || 8) / 100,
      stack_tier: Number(addForm.value.mold_tier || 1),
      rotation_deg: Number(addForm.value.rotation_deg || 0),
      status: addForm.value.mold_status || 'empty',
      add_stoyka_pair: Boolean(addForm.value.row_add_stoyka_pair),
      stoyka_spacing_m: Number(addForm.value.stoyka_pair_spacing_m || 1.45),
      notes: addForm.value.notes || `Qator Z=${z}m`,
    })
  } else if (addCategory.value === 'tal_crane') {
    await store.createWorkshopElement({
      element_type: 'tal_crane',
      name: `Talning o'zi (A-ramali Ko'targich, ${addForm.value.crane_span_m}m)`,
      pos_x: 0.0,
      pos_z: z,
      pos_y: 0.0,
      rotation_deg: 0,
      length_m: 1.4,
      width_m: Number(addForm.value.crane_span_m || 6.0),
      height_m: Number(addForm.value.crane_height_m || 3.0),
      extra_json: JSON.stringify({
        hoist_x: Number(addForm.value.crane_hoist_x || 0.0),
      }),
      notes: `Rels ustida Eshikdan Z=${z}m masofada`,
    })
  } else if (addCategory.value === 'tal_rails') {
    const z1 = Number(addForm.value.rails_z_start || 0)
    const z2 = Number(addForm.value.rails_z_end || yardDims.value.length_m)
    const gauge = Number(addForm.value.rails_gauge_m || 6.0)
    await store.createWorkshopElement({
      element_type: 'tal_rails',
      name: `Ikki yondagi Tal relslari (Orasi ${gauge}m)`,
      pos_x: 0.0,
      pos_z: Number(((z1 + z2) / 2).toFixed(2)),
      pos_y: 0.0,
      rotation_deg: 0,
      length_m: Number(Math.abs(z2 - z1).toFixed(2)),
      width_m: gauge,
      height_m: 0.1,
      extra_json: JSON.stringify({
        z_start: z1,
        z_end: z2,
        gauge_m: gauge,
      }),
      notes: `Z=${z1}m dan ${z2}m gacha, orasi ${gauge}m`,
    })
  } else if (addCategory.value === 'meshalka') {
    await store.createWorkshopElement({
      element_type: 'meshalka',
      name: 'Meshalka (Beton qorgich)',
      pos_x: x,
      pos_z: z,
      pos_y: 0.0,
      rotation_deg: Number(addForm.value.rotation_deg || 0),
      length_m: 1.4,
      width_m: 1.3,
      height_m: 1.65,
      extra_json: '{}',
      notes: `Eshikdan Z=${z}m, Markazdan X=${x}m`,
    })
  } else if (addCategory.value === 'vibrator') {
    await store.createWorkshopElement({
      element_type: 'vibrator',
      name: 'Vibrator (4-prujinali Vibrostol)',
      pos_x: x,
      pos_z: z,
      pos_y: 0.0,
      rotation_deg: Number(addForm.value.rotation_deg || 0),
      length_m: Number(addForm.value.equip_length_m || 1.35),
      width_m: Number(addForm.value.equip_width_m || 1.1),
      height_m: 0.35,
      extra_json: '{}',
      notes: `Eshikdan Z=${z}m, Markazdan X=${x}m`,
    })
  } else if (addCategory.value === 'yard_dims') {
    await store.updateSettings({
      company_name: store.settings.company_name || 'Beton Ariq & Kolodets Zavodi',
      region_id: store.settings.region_id || 'fergana',
      workshop_width_m: Number(yardDims.value.width_front_m),
      workshop_width_front_m: Number(yardDims.value.width_front_m),
      workshop_width_back_m: Number(yardDims.value.width_back_m),
      workshop_length_m: Number(yardDims.value.length_m),
      rail_gauge_m: Number(yardDims.value.rail_gauge_m),
    })
  }
}

// ---------------- SELECTED ITEM MATHEMATICAL INSPECTOR (MOLD OR ELEMENT) ----------------
const editItemForm = ref({
  kind: null,
  id: null,
  name: '',
  pos_x: 0,
  pos_z: 0,
  pos_y: 0,
  stack_tier: 1,
  rotation_deg: 0,
  length_m: 1.45,
  width_m: 5.8,
  height_m: 0.14,
  status: 'empty',
  hoist_x: 0.0,
  notes: '',
})

watch(
  () => [store.selectedMold, store.selectedElement],
  ([m, el]) => {
    if (m) {
      editItemForm.value = {
        kind: 'mold',
        id: m.id,
        name: m.mold_number,
        pos_x: Number(m.pos_x || 0),
        pos_z: Number(m.pos_z || 0),
        pos_y: 0,
        stack_tier: Number(m.stack_tier || 1),
        rotation_deg: Number(m.rotation_deg || 0),
        length_m: (m.length_cm || 220) / 100,
        width_m: (m.inner_top_cm || 30) / 100,
        height_m: 0.35,
        status: m.status || 'empty',
        hoist_x: 0,
        notes: m.notes || '',
      }
    } else if (el) {
      let extra = {}
      try {
        extra = JSON.parse(el.extra_json || '{}')
      } catch (e) {
        extra = {}
      }
      editItemForm.value = {
        kind: 'element',
        id: el.id,
        element_type: el.element_type,
        name: el.name,
        pos_x: Number(el.pos_x || 0),
        pos_z: Number(el.pos_z || 0),
        pos_y: Number(el.pos_y || 0),
        stack_tier: 1,
        rotation_deg: Number(el.rotation_deg || 0),
        length_m: Number(el.length_m || 1.0),
        width_m: Number(el.width_m || 1.0),
        height_m: Number(el.height_m || 0.15),
        status: 'empty',
        hoist_x: Number(extra.hoist_x || 0),
        extra_obj: extra,
        notes: el.notes || '',
      }
    } else {
      editItemForm.value.kind = null
    }
  },
  { immediate: true, deep: true }
)

async function saveSelectedEdit() {
  if (!editItemForm.value.kind) return
  if (editItemForm.value.kind === 'mold') {
    await store.updateMoldPosition(editItemForm.value.id, {
      pos_x: Number(editItemForm.value.pos_x),
      pos_z: Number(editItemForm.value.pos_z),
      stack_tier: Number(editItemForm.value.stack_tier || 1),
      rotation_deg: Number(editItemForm.value.rotation_deg || 0),
      status: editItemForm.value.status,
      notes: editItemForm.value.notes,
    })
  } else if (editItemForm.value.kind === 'element') {
    const extra = { ...(editItemForm.value.extra_obj || {}) }
    if (editItemForm.value.element_type === 'tal_crane') {
      extra.hoist_x = Number(editItemForm.value.hoist_x || 0)
    } else if (editItemForm.value.element_type === 'stoyka') {
      extra.pair_spacing_m = Number(editItemForm.value.length_m || 1.45)
    } else if (editItemForm.value.element_type === 'tal_rails') {
      extra.gauge_m = Number(editItemForm.value.width_m || 6.0)
    }
    await store.updateWorkshopElement(editItemForm.value.id, {
      name: editItemForm.value.name,
      pos_x: Number(editItemForm.value.pos_x),
      pos_z: Number(editItemForm.value.pos_z),
      pos_y: Number(editItemForm.value.pos_y || 0),
      rotation_deg: Number(editItemForm.value.rotation_deg || 0),
      length_m: Number(editItemForm.value.length_m || 1.0),
      width_m: Number(editItemForm.value.width_m || 1.0),
      height_m: Number(editItemForm.value.height_m || 0.15),
      extra_json: JSON.stringify(extra),
      notes: editItemForm.value.notes,
    })
  }
}

async function nudgeSelected(dx, dz) {
  if (!editItemForm.value.kind) return
  editItemForm.value.pos_x = Number((Number(editItemForm.value.pos_x) + dx).toFixed(2))
  editItemForm.value.pos_z = Number((Number(editItemForm.value.pos_z) + dz).toFixed(2))
  await saveSelectedEdit()
}

async function deleteSelectedItem() {
  if (!editItemForm.value.kind) return
  if (editItemForm.value.kind === 'mold') {
    await store.deleteMold(editItemForm.value.id)
  } else {
    await store.deleteWorkshopElement(editItemForm.value.id)
  }
}

// ---------------- THREE.JS SCENE & GEOMETRY BUILDERS ----------------
let scene = null
let camera = null
let renderer = null
let controls = null
let raycaster = null
let pointer = null
let animationFrameId = null
let floorMeshForRaycast = null
let cursorMarkerGroup = null
let ghostPreviewGroup = null
const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0)
const planeIntersectPt = new THREE.Vector3()
const clickableItems = new Map() // Mesh -> { kind: 'mold'|'element', data: obj, rootGroup: THREE.Group, baseHeight: number }

const statusColors = {
  empty: 0x64748b,
  poured: 0x2563eb,
  ready_demold: 0x10b981,
  maintenance: 0xef4444,
  cyclic_active: 0xf59e0b,
}

function createGravelTexture() {
  const c = document.createElement('canvas')
  c.width = 512
  c.height = 512
  const ctx = c.getContext('2d')
  ctx.fillStyle = '#57544f'
  ctx.fillRect(0, 0, 512, 512)
  for (let i = 0; i < 6000; i++) {
    const x = Math.random() * 512
    const y = Math.random() * 512
    const r = Math.random() * 3.0 + 0.6
    const shade = 72 + Math.floor(Math.random() * 70)
    ctx.fillStyle = `rgb(${shade}, ${shade - 2}, ${shade - 5})`
    ctx.fillRect(x, y, r, r)
  }
  const tex = new THREE.CanvasTexture(c)
  tex.wrapS = THREE.RepeatWrapping
  tex.wrapT = THREE.RepeatWrapping
  tex.repeat.set(5, 8)
  return tex
}

function createShlakoblokTexture() {
  const c = document.createElement('canvas')
  c.width = 512
  c.height = 256
  const ctx = c.getContext('2d')
  ctx.fillStyle = '#8b9196'
  ctx.fillRect(0, 0, 512, 256)
  const bw = 64
  const bh = 32
  for (let row = 0; row < 8; row++) {
    const offset = row % 2 === 0 ? 0 : bw / 2
    for (let col = -1; col < 9; col++) {
      const x = col * bw + offset
      const y = row * bh
      const v = 135 + Math.floor(Math.random() * 25)
      ctx.fillStyle = `rgb(${v}, ${v + 2}, ${v + 4})`
      ctx.fillRect(x + 2, y + 2, bw - 4, bh - 4)
      ctx.strokeStyle = '#4b5563'
      ctx.lineWidth = 2
      ctx.strokeRect(x + 1, y + 1, bw - 2, bh - 2)
    }
  }
  const tex = new THREE.CanvasTexture(c)
  tex.wrapS = THREE.RepeatWrapping
  tex.wrapT = THREE.RepeatWrapping
  tex.repeat.set(3, 1.4)
  return tex
}

function createTextSprite(text, bgColor = '#0f172a', borderColor = '#38bdf8', scaleW = 1.05, scaleH = 0.28) {
  const canvas = document.createElement('canvas')
  canvas.width = 320
  canvas.height = 80
  const ctx = canvas.getContext('2d')

  ctx.fillStyle = bgColor
  ctx.strokeStyle = borderColor
  ctx.lineWidth = 5
  ctx.beginPath()
  ctx.roundRect(6, 6, 308, 68, 14)
  ctx.fill()
  ctx.stroke()

  ctx.fillStyle = '#ffffff'
  ctx.font = 'bold 23px sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(text, 160, 40)

  const texture = new THREE.CanvasTexture(canvas)
  const material = new THREE.SpriteMaterial({ map: texture, depthTest: false })
  const sprite = new THREE.Sprite(material)
  sprite.scale.set(scaleW, scaleH, 1)
  sprite.renderOrder = 999
  return sprite
}

// ---------------- 1. BUILD EXACT MATHEMATICAL TRAPEZOIDAL YARD (16.5m x 7.0m -> 8.2m) ----------------
function buildMathematicalYard() {
  const archGroup = new THREE.Group()
  archGroup.userData = { isSceneObject: true }

  const L = yardDims.value.length_m || 16.5
  const Wf = yardDims.value.width_front_m || 7.0
  const Wb = yardDims.value.width_back_m || 8.2
  const zFront = zToWorld(0)
  const zBack = zToWorld(L)

  const gravelTex = createGravelTexture()
  const blockTex = createShlakoblokTexture()

  const floorShape = new THREE.Shape()
  floorShape.moveTo(-Wf / 2, -zFront)
  floorShape.lineTo(Wf / 2, -zFront)
  floorShape.lineTo(Wb / 2, -zBack)
  floorShape.lineTo(-Wb / 2, -zBack)
  floorShape.closePath()

  const floorGeo = new THREE.ShapeGeometry(floorShape)
  floorGeo.rotateX(-Math.PI / 2)

  const floorMat = new THREE.MeshStandardMaterial({
    map: gravelTex,
    color: lightingMode.value === 'daylight' ? 0xd6d3cd : 0x334155,
    roughness: 0.94,
    metalness: 0.04,
  })
  const floorMesh = new THREE.Mesh(floorGeo, floorMat)
  floorMesh.receiveShadow = true
  archGroup.add(floorMesh)
  floorMeshForRaycast = floorMesh

  const linePoints1m = []
  const linePointsHalfM = []
  const centerAxisPoints = [new THREE.Vector3(0, 0.015, zFront), new THREE.Vector3(0, 0.015, zBack)]

  for (let z = 0; z <= L + 0.001; z += 0.5) {
    const clampedZ = Math.min(z, L)
    const wz = zToWorld(clampedZ)
    const wAtZ = getYardWidthAtZ(clampedZ)
    const isWholeMeter = Math.abs(clampedZ - Math.round(clampedZ)) < 0.01 || Math.abs(clampedZ - L) < 0.01
    const targetArr = isWholeMeter ? linePoints1m : linePointsHalfM
    targetArr.push(new THREE.Vector3(-wAtZ / 2, 0.012, wz), new THREE.Vector3(wAtZ / 2, 0.012, wz))

    if (isWholeMeter && showLabels.value && (Math.round(clampedZ) % 2 === 0 || Math.abs(clampedZ - L) < 0.05)) {
      const lbl = createTextSprite(
        `Z=${clampedZ}m (${wAtZ.toFixed(1)}m)`,
        '#0f172a',
        clampedZ === 0 ? '#10b981' : Math.abs(clampedZ - L) < 0.05 ? '#f59e0b' : '#475569',
        0.92,
        0.22
      )
      lbl.position.set(-wAtZ / 2 - 0.65, 0.14, wz)
      archGroup.add(lbl)
    }
  }

  for (let x = -4; x <= 4; x += 1) {
    if (x === 0) continue
    let zStart = 0
    if (Math.abs(x) > Wf / 2) {
      if (Wb > Wf && Math.abs(x) <= Wb / 2) {
        zStart = ((Math.abs(x) * 2 - Wf) / (Wb - Wf)) * L
      } else {
        continue
      }
    }
    linePoints1m.push(
      new THREE.Vector3(x, 0.012, zToWorld(zStart)),
      new THREE.Vector3(x, 0.012, zBack)
    )
  }

  const grid1mGeo = new THREE.BufferGeometry().setFromPoints(linePoints1m)
  const grid1m = new THREE.LineSegments(
    grid1mGeo,
    new THREE.LineBasicMaterial({
      color: lightingMode.value === 'daylight' ? 0x334155 : 0x475569,
      transparent: true,
      opacity: 0.45,
    })
  )
  archGroup.add(grid1m)

  const gridHalfGeo = new THREE.BufferGeometry().setFromPoints(linePointsHalfM)
  const gridHalf = new THREE.LineSegments(
    gridHalfGeo,
    new THREE.LineBasicMaterial({
      color: 0x64748b,
      transparent: true,
      opacity: 0.2,
    })
  )
  archGroup.add(gridHalf)

  const centerLine = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(centerAxisPoints),
    new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.7 })
  )
  archGroup.add(centerLine)

  const wallH = showWallMode.value === 'full' ? 2.25 : 0.55
  const blockMat = new THREE.MeshStandardMaterial({
    map: blockTex,
    roughness: 0.88,
    metalness: 0.05,
  })
  const sideWallMat = new THREE.MeshStandardMaterial({
    color: 0xc2ab8e,
    roughness: 0.9,
    transparent: showWallMode.value === 'low',
    opacity: showWallMode.value === 'low' ? 0.78 : 0.96,
  })

  // Oxirgi Shlakoblokli Devor (Z = 16.5m, Kengligi = 8.2m)
  const backWall = new THREE.Mesh(new THREE.BoxGeometry(Wb + 0.4, 2.25, 0.28), blockMat)
  backWall.position.set(0, 1.125, zBack + 0.14)
  backWall.castShadow = true
  backWall.receiveShadow = true
  archGroup.add(backWall)

  const backBanner = createTextSprite(
    `OXIRI: SHLAKOBLOK DEVOR (Z=${L}m • Kengligi: ${Wb}m)`,
    '#1e293b',
    '#f59e0b',
    2.5,
    0.42
  )
  backBanner.position.set(0, 2.6, zBack + 0.14)
  archGroup.add(backBanner)

  // Chap va O'ng Yon Devorlar (Eshik tomon 7.0m -> Oxiri 8.2m, Uzunligi 16.5m)
  const halfDiff = (Wb - Wf) / 2
  const sideWallLen = Math.sqrt(L * L + halfDiff * halfDiff)
  const sideAngle = Math.atan2(halfDiff, L)

  for (const side of [-1, 1]) {
    const sideWall = new THREE.Mesh(new THREE.BoxGeometry(0.24, wallH, sideWallLen), sideWallMat)
    const midX = side * ((Wf / 2 + Wb / 2) / 2 + 0.12)
    sideWall.position.set(midX, wallH / 2, 0)
    sideWall.rotation.y = side * sideAngle
    sideWall.receiveShadow = true
    archGroup.add(sideWall)
  }

  // Eshik Tomon (Z = 0.0m, Kengligi = 7.0m)
  const doorFrameMat = new THREE.MeshStandardMaterial({ color: 0x10b981, metalness: 0.4, roughness: 0.4 })
  const entranceThreshold = new THREE.Mesh(new THREE.BoxGeometry(Wf, 0.04, 0.12), doorFrameMat)
  entranceThreshold.position.set(0, 0.02, zFront)
  archGroup.add(entranceThreshold)

  for (const dx of [-1.1, 1.1]) {
    const pillar = new THREE.Mesh(new THREE.BoxGeometry(0.16, 1.8, 0.16), doorFrameMat)
    pillar.position.set(dx, 0.9, zFront)
    archGroup.add(pillar)
  }
  const frontBanner = createTextSprite(
    `ESHIK TOMON (Z=0.0m • Kengligi: ${Wf}m)`,
    '#064e3b',
    '#10b981',
    2.3,
    0.4
  )
  frontBanner.position.set(0, 2.1, zFront)
  archGroup.add(frontBanner)

  // 3D Interactive Floor Cursor Ring
  cursorMarkerGroup = new THREE.Group()
  const ringGeo = new THREE.RingGeometry(0.14, 0.22, 24)
  ringGeo.rotateX(-Math.PI / 2)
  const ringMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8, side: THREE.DoubleSide })
  cursorMarkerGroup.add(new THREE.Mesh(ringGeo, ringMat))
  cursorMarkerGroup.position.set(cursorPoint.value.x, 0.025, zToWorld(cursorPoint.value.z))
  archGroup.add(cursorMarkerGroup)

  scene.add(archGroup)
}

// ---------------- 2. BUILD WORKSHOP STRUCTURAL & EQUIPMENT ELEMENTS ----------------
function createWorkshopElementGroup(el, isSelected) {
  const group = new THREE.Group()
  let extra = {}
  try {
    extra = JSON.parse(el.extra_json || '{}')
  } catch (e) {
    extra = {}
  }

  const hitMeshes = []
  const highlightEmissive = isSelected ? 0x38bdf8 : 0x000000
  const highlightIntensity = isSelected ? 0.45 : 0

  if (el.element_type === 'tal_rails') {
    const gauge = Number(el.width_m || extra.gauge_m || yardDims.value.rail_gauge_m || 6.0)
    const len = Number(el.length_m || yardDims.value.length_m || 16.5)
    const railH = Number(el.height_m || 0.1)
    const railMat = new THREE.MeshStandardMaterial({
      color: isSelected ? 0x38bdf8 : 0x0284c7,
      metalness: 0.7,
      roughness: 0.3,
      emissive: highlightEmissive,
      emissiveIntensity: highlightIntensity,
    })

    for (const side of [-1, 1]) {
      const rx = side * (gauge / 2)
      const railMesh = new THREE.Mesh(new THREE.BoxGeometry(0.11, railH, len), railMat)
      railMesh.position.set(rx, railH / 2, 0)
      railMesh.castShadow = true
      group.add(railMesh)
      hitMeshes.push(railMesh)

      if (showLabels.value) {
        const rLbl = createTextSprite(
          `${side < 0 ? 'CHAP' : "O'NG"} TAL RELSI (X=${rx > 0 ? '+' : ''}${rx.toFixed(1)}m)`,
          '#0c4a6e',
          '#38bdf8',
          1.35,
          0.26
        )
        rLbl.position.set(rx, 0.32, -len / 2 + 1.4)
        group.add(rLbl)
      }
    }
  } else if (el.element_type === 'tal_crane') {
    const span = Number(el.width_m || yardDims.value.rail_gauge_m || 6.0)
    const h = Number(el.height_m || 3.0)
    const hoistX = Number(extra.hoist_x || 0.0)

    const legBlueMat = new THREE.MeshStandardMaterial({
      color: 0x0284c7,
      metalness: 0.6,
      roughness: 0.4,
      emissive: highlightEmissive,
      emissiveIntensity: highlightIntensity,
    })
    const legOrangeMat = new THREE.MeshStandardMaterial({
      color: 0xea580c,
      metalness: 0.6,
      roughness: 0.4,
      emissive: highlightEmissive,
      emissiveIntensity: highlightIntensity,
    })
    const beamMat = new THREE.MeshStandardMaterial({
      color: 0x475569,
      metalness: 0.75,
      roughness: 0.35,
      emissive: highlightEmissive,
      emissiveIntensity: highlightIntensity,
    })

    for (const side of [-1, 1]) {
      const rx = side * (span / 2)
      const carriage = new THREE.Mesh(new THREE.BoxGeometry(0.18, 0.14, 1.35), beamMat)
      carriage.position.set(rx, 0.12, 0)
      group.add(carriage)
      hitMeshes.push(carriage)

      for (const legZ of [-0.52, 0.52]) {
        const leg = new THREE.Mesh(
          new THREE.BoxGeometry(0.11, h, 0.11),
          legZ < 0 ? legOrangeMat : legBlueMat
        )
        leg.position.set(rx, h / 2 + 0.1, legZ * 0.5)
        leg.rotation.x = legZ < 0 ? 0.18 : -0.18
        leg.castShadow = true
        group.add(leg)
        hitMeshes.push(leg)
      }
    }

    const iBeam = new THREE.Mesh(new THREE.BoxGeometry(span + 0.35, 0.18, 0.16), beamMat)
    iBeam.position.set(0, h + 0.12, 0)
    iBeam.castShadow = true
    group.add(iBeam)
    hitMeshes.push(iBeam)

    const hoistMotor = new THREE.Mesh(
      new THREE.CylinderGeometry(0.16, 0.16, 0.36, 16),
      new THREE.MeshStandardMaterial({ color: 0xf59e0b, metalness: 0.6, roughness: 0.3 })
    )
    hoistMotor.position.set(hoistX, h - 0.08, 0)
    group.add(hoistMotor)
    hitMeshes.push(hoistMotor)

    const cable = new THREE.Mesh(
      new THREE.CylinderGeometry(0.015, 0.015, h - 0.9, 8),
      new THREE.MeshBasicMaterial({ color: 0x0f172a })
    )
    cable.position.set(hoistX, (h - 0.9) / 2 + 0.85, 0)
    group.add(cable)

    const spreader = new THREE.Mesh(
      new THREE.BoxGeometry(0.1, 0.1, 1.4),
      new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.8, roughness: 0.25 })
    )
    spreader.position.set(hoistX, 0.85, 0)
    group.add(spreader)

    if (showLabels.value) {
      const lbl = createTextSprite(
        `TAL KO'TARGICH (Z=${Number(el.pos_z).toFixed(2)}m • Eni ${span}m)`,
        '#451a03',
        '#f59e0b',
        1.75,
        0.32
      )
      lbl.position.set(0, h + 0.55, 0)
      group.add(lbl)
    }
  } else if (el.element_type === 'stoyka') {
    const isPair = extra.is_pair !== false
    const spacingM = Number(el.length_m || extra.pair_spacing_m || 1.45)
    const rowWidthM = Number(el.width_m || 5.8)
    const beamWM = Number(extra.beam_width_m || 0.16)
    const beamHM = Number(el.height_m || extra.beam_height_m || 0.14)

    const stoykaMat = new THREE.MeshStandardMaterial({
      color: isSelected ? 0x38bdf8 : 0xcbd5e1,
      roughness: 0.88,
      metalness: 0.05,
      emissive: highlightEmissive,
      emissiveIntensity: highlightIntensity,
    })

    const zOffsets = isPair ? [-spacingM / 2, spacingM / 2] : [0]
    for (const zOff of zOffsets) {
      const beam = new THREE.Mesh(new THREE.BoxGeometry(rowWidthM, beamHM, beamWM), stoykaMat)
      beam.position.set(0, beamHM / 2, zOff)
      beam.castShadow = true
      beam.receiveShadow = true
      group.add(beam)
      hitMeshes.push(beam)

      const edges = new THREE.LineSegments(
        new THREE.EdgesGeometry(beam.geometry),
        new THREE.LineBasicMaterial({ color: isSelected ? 0x0284c7 : 0x475569 })
      )
      beam.add(edges)
    }

    if (showLabels.value) {
      const lbl = createTextSprite(
        `${el.name} (Z=${Number(el.pos_z).toFixed(2)}m)`,
        '#1e293b',
        '#94a3b8',
        1.45,
        0.25
      )
      lbl.position.set(0, beamHM + 0.22, 0)
      group.add(lbl)
    }
  } else if (el.element_type === 'meshalka') {
    const standMat = new THREE.MeshStandardMaterial({
      color: 0x475569,
      metalness: 0.6,
      roughness: 0.45,
      emissive: highlightEmissive,
      emissiveIntensity: highlightIntensity,
    })
    const base = new THREE.Mesh(new THREE.BoxGeometry(1.15, 0.65, 0.9), standMat)
    base.position.y = 0.325
    group.add(base)
    hitMeshes.push(base)

    const drum = new THREE.Mesh(
      new THREE.CylinderGeometry(0.45, 0.62, 0.95, 18),
      new THREE.MeshStandardMaterial({
        color: 0x9ca3af,
        metalness: 0.4,
        roughness: 0.55,
        emissive: highlightEmissive,
        emissiveIntensity: highlightIntensity,
      })
    )
    drum.position.y = 1.05
    drum.rotation.z = 0.12
    drum.castShadow = true
    group.add(drum)
    hitMeshes.push(drum)

    if (showLabels.value) {
      const lbl = createTextSprite(
        `MESHALKA (Z=${Number(el.pos_z).toFixed(2)}m, X=${Number(el.pos_x).toFixed(2)}m)`,
        '#0f172a',
        '#38bdf8',
        1.55,
        0.28
      )
      lbl.position.set(0, 1.85, 0)
      group.add(lbl)
    }
  } else if (el.element_type === 'vibrator') {
    const w = Number(el.width_m || 1.1)
    const l = Number(el.length_m || 1.35)
    const springMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, metalness: 0.7, roughness: 0.3 })

    for (const [sx, sz] of [
      [-w * 0.38, -l * 0.38],
      [w * 0.38, -l * 0.38],
      [-w * 0.38, l * 0.38],
      [w * 0.38, l * 0.38],
    ]) {
      const spring = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.22, 12), springMat)
      spring.position.set(sx, 0.11, sz)
      group.add(spring)
    }

    const tableTop = new THREE.Mesh(
      new THREE.BoxGeometry(w, 0.08, l),
      new THREE.MeshStandardMaterial({
        color: 0x0d9488,
        metalness: 0.55,
        roughness: 0.4,
        emissive: highlightEmissive,
        emissiveIntensity: highlightIntensity,
      })
    )
    tableTop.position.y = 0.25
    tableTop.castShadow = true
    group.add(tableTop)
    hitMeshes.push(tableTop)

    if (showLabels.value) {
      const lbl = createTextSprite(
        `VIBRATOR (Z=${Number(el.pos_z).toFixed(2)}m, X=${Number(el.pos_x).toFixed(2)}m)`,
        '#042f2e',
        '#14b8a6',
        1.55,
        0.28
      )
      lbl.position.set(0, 0.65, 0)
      group.add(lbl)
    }
  }

  return { group, hitMeshes }
}

// ---------------- 3. BUILD INVERTED TRAPEZOIDAL ARIQ & KOLODETS MOLDS ----------------
function createAriqMoldGroup(mold, isSelected) {
  const group = new THREE.Group()

  const len = (mold.length_cm || 220) / 100
  const innerBottomW = (mold.inner_bottom_cm || 15) / 100
  const innerTopW = (mold.inner_top_cm || 30) / 100
  const wall = (mold.wall_thickness_cm || 5.5) / 100
  const sideSlope = (mold.inner_side_cm || 22) / 100

  const halfDiff = Math.max((innerTopW - innerBottomW) / 2, 0.03)
  const innerDepth = sideSlope > halfDiff ? Math.sqrt(sideSlope * sideSlope - halfDiff * halfDiff) : sideSlope

  const baseW = innerTopW + 2 * wall + 0.08
  const topW = innerBottomW + 2 * wall + 0.04
  const outerH = innerDepth + wall + 0.04

  const sColor = statusColors[mold.status] || 0x64748b
  const hasDefect = mold.consecutive_corner_defects >= 1 || mold.status === 'maintenance'

  const shellColor =
    colorMode.value === 'status'
      ? sColor
      : mold.status === 'maintenance'
      ? 0x991b1b
      : 0x5b636b

  const steelMat = new THREE.MeshStandardMaterial({
    color: shellColor,
    metalness: colorMode.value === 'realistic' ? 0.55 : 0.25,
    roughness: colorMode.value === 'realistic' ? 0.55 : 0.45,
    emissive: isSelected ? 0x38bdf8 : mold.status === 'maintenance' ? 0x7f1d1d : 0x000000,
    emissiveIntensity: isSelected ? 0.45 : mold.status === 'maintenance' ? 0.35 : 0,
  })

  const outerShape = new THREE.Shape()
  outerShape.moveTo(-baseW / 2, 0)
  outerShape.lineTo(baseW / 2, 0)
  outerShape.lineTo(topW / 2, outerH)
  outerShape.lineTo(-topW / 2, outerH)
  outerShape.closePath()

  const holePath = new THREE.Path()
  const hBot = innerTopW * 0.92
  const hTop = innerBottomW * 0.92
  const hH = innerDepth * 0.88
  holePath.moveTo(-hBot / 2, 0.025)
  holePath.lineTo(hBot / 2, 0.025)
  holePath.lineTo(hTop / 2, hH)
  holePath.lineTo(-hTop / 2, hH)
  holePath.closePath()
  outerShape.holes.push(holePath)

  const extrudeGeo = new THREE.ExtrudeGeometry(outerShape, {
    depth: len,
    bevelEnabled: false,
  })
  extrudeGeo.translate(0, 0, -len / 2)

  const shellMesh = new THREE.Mesh(extrudeGeo, steelMat)
  shellMesh.castShadow = true
  shellMesh.receiveShadow = true
  group.add(shellMesh)

  const rebarMat = new THREE.MeshStandardMaterial({ color: 0x27272a, metalness: 0.75, roughness: 0.35 })
  for (const clampZ of [-len / 2 + 0.06, 0, len / 2 - 0.06]) {
    const tieBar = new THREE.Mesh(new THREE.CylinderGeometry(0.01, 0.01, topW + 0.12, 8), rebarMat)
    tieBar.rotation.z = Math.PI / 2
    tieBar.position.set(0, outerH + 0.032, clampZ)
    group.add(tieBar)
  }

  const diagLen = Math.sqrt(hBot * hBot * 0.45 + hH * hH * 0.75)
  const xMat = new THREE.MeshStandardMaterial({ color: 0x262b30, metalness: 0.7, roughness: 0.4 })
  for (const endZ of [-len / 2 + 0.05, len / 2 - 0.05]) {
    const b1 = new THREE.Mesh(new THREE.BoxGeometry(0.022, diagLen, 0.022), xMat)
    b1.position.set(0, hH * 0.52, endZ)
    b1.rotation.z = 0.68
    const b2 = new THREE.Mesh(new THREE.BoxGeometry(0.022, diagLen, 0.022), xMat)
    b2.position.set(0, hH * 0.52, endZ)
    b2.rotation.z = -0.68
    group.add(b1, b2)
  }

  if (mold.status === 'poured' || mold.status === 'ready_demold') {
    const concMat = new THREE.MeshStandardMaterial({
      color: mold.status === 'poured' ? 0x717a82 : 0xa1a8b0,
      roughness: 0.6,
    })
    const concSlab = new THREE.Mesh(new THREE.BoxGeometry(topW - 0.04, 0.026, len - 0.05), concMat)
    concSlab.position.set(0, outerH + 0.012, 0)
    group.add(concSlab)
  }

  const ledStrip = new THREE.Mesh(
    new THREE.BoxGeometry(topW * 0.72, 0.018, 0.06),
    new THREE.MeshBasicMaterial({ color: sColor })
  )
  ledStrip.position.set(0, outerH + 0.04, -len / 2 + 0.09)
  group.add(ledStrip)

  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(extrudeGeo, 28),
    new THREE.LineBasicMaterial({
      color: isSelected ? 0x38bdf8 : hasDefect ? 0xf87171 : 0x1e293b,
    })
  )
  group.add(edges)

  if (showLabels.value) {
    const tierSuffix = mold.stack_tier > 1 ? ` [${mold.stack_tier}-Q]` : ''
    const label = createTextSprite(
      `${mold.mold_number}${tierSuffix}`,
      mold.stack_tier > 1 ? '#312e81' : '#0f172a',
      isSelected ? '#38bdf8' : mold.stack_tier > 1 ? '#c084fc' : '#64748b',
      1.05,
      0.26
    )
    label.position.set(0, outerH + 0.25, 0)
    group.add(label)
  }

  return { group, hitMesh: shellMesh, heightM: outerH }
}

function createKolodetsMoldGroup(mold, isSelected) {
  const group = new THREE.Group()
  const outerR = (mold.outer_diameter_cm || 118) / 200
  const innerR = (mold.inner_diameter_cm || 104) / 200
  const h = (mold.max_height_cm || 60) / 100

  const shape = new THREE.Shape()
  shape.absarc(0, 0, outerR, 0, Math.PI * 2, false)
  const holePath = new THREE.Path()
  holePath.absarc(0, 0, innerR, 0, Math.PI * 2, true)
  shape.holes.push(holePath)

  const ringGeo = new THREE.ExtrudeGeometry(shape, { depth: h, bevelEnabled: false, curveSegments: 32 })
  ringGeo.rotateX(-Math.PI / 2)

  const ringMat = new THREE.MeshStandardMaterial({
    color: statusColors[mold.status] || 0xf59e0b,
    metalness: 0.55,
    roughness: 0.35,
    emissive: isSelected ? 0x38bdf8 : 0x000000,
    emissiveIntensity: isSelected ? 0.45 : 0,
  })
  const ringMesh = new THREE.Mesh(ringGeo, ringMat)
  ringMesh.castShadow = true
  group.add(ringMesh)

  if (showLabels.value) {
    const label = createTextSprite(
      `${mold.mold_number}`,
      '#451a03',
      isSelected ? '#38bdf8' : '#f59e0b',
      1.3,
      0.28
    )
    label.position.set(0, h + 0.3, 0)
    group.add(label)
  }

  return { group, hitMesh: ringMesh, heightM: h }
}

function getStoykaHeightAtPoint(x, z) {
  for (const el of store.workshopElements) {
    if (el.element_type === 'stoyka') {
      const dz = Math.abs(Number(z || 0) - Number(el.pos_z || 0))
      const dx = Math.abs(Number(x || 0) - Number(el.pos_x || 0))
      const halfW = Number(el.width_m || 5.8) / 2 + 0.3
      if (dz <= 1.25 && dx <= halfW) {
        return Number(el.height_m || 0.14)
      }
    }
  }
  return 0.0
}

function findMoldUnderPoint(x, z, excludeMoldId = null) {
  for (const m of store.molds) {
    if (excludeMoldId && m.id === excludeMoldId) continue
    if ((m.stack_tier || 1) === 1) {
      const dx = Math.abs(Number(m.pos_x || 0) - x)
      const dz = Math.abs(Number(m.pos_z || 0) - z)
      if (dx < 0.38 && dz < 0.85) {
        return m
      }
    }
  }
  return null
}

// ---------------- 4. LIVE 3D GHOST PREVIEW FOR SUMMONED / DRAGGED PALETTE ELEMENT ----------------
function rebuildGhostPreview() {
  if (!scene) return
  if (ghostPreviewGroup) {
    scene.remove(ghostPreviewGroup)
    ghostPreviewGroup = null
  }
  const tool = activeSpawnTool.value
  if (!tool) return

  const g = new THREE.Group()
  g.userData = { isGhostPreview: true }

  const ghostMat = new THREE.MeshStandardMaterial({
    color: 0x38bdf8,
    transparent: true,
    opacity: 0.62,
    emissive: 0x0284c7,
    emissiveIntensity: 0.45,
    roughness: 0.3,
  })

  if (tool.category === 'stoyka') {
    const isPair = tool.isPair
    const spacingM = Number(addForm.value.stoyka_pair_spacing_m || 1.45)
    const rowWidthM = isPair ? Number(addForm.value.stoyka_row_width_m || 5.8) : 2.2
    const zOffsets = isPair ? [-spacingM / 2, spacingM / 2] : [0]
    for (const zOff of zOffsets) {
      const beam = new THREE.Mesh(new THREE.BoxGeometry(rowWidthM, 0.14, 0.16), ghostMat)
      beam.position.set(0, 0.07, zOff)
      g.add(beam)
    }
  } else if (tool.category === 'mold') {
    const prod = store.products.find((p) => p.code === tool.code)
    if (tool.code === 'K104') {
      const cyl = new THREE.Mesh(new THREE.CylinderGeometry(0.59, 0.59, 0.6, 24), ghostMat)
      cyl.position.y = 0.3
      g.add(cyl)
    } else {
      const len = ((prod && prod.length_cm) || 220) / 100
      const innerTopW = ((prod && prod.inner_top_cm) || 30) / 100
      const wall = ((prod && prod.wall_thickness_cm) || 5.5) / 100
      const baseW = innerTopW + 2 * wall + 0.08
      const topW = baseW * 0.68
      const outerH = ((prod && prod.inner_side_cm) || 22) / 100 + wall

      const shape = new THREE.Shape()
      shape.moveTo(-baseW / 2, 0)
      shape.lineTo(baseW / 2, 0)
      shape.lineTo(topW / 2, outerH)
      shape.lineTo(-topW / 2, outerH)
      shape.closePath()
      const geo = new THREE.ExtrudeGeometry(shape, { depth: len, bevelEnabled: false })
      geo.translate(0, 0, -len / 2)
      g.add(new THREE.Mesh(geo, ghostMat))
    }
  } else if (tool.category === 'tal_crane') {
    const span = yardDims.value.rail_gauge_m || 6.0
    const beam = new THREE.Mesh(new THREE.BoxGeometry(span + 0.3, 0.18, 0.18), ghostMat)
    beam.position.set(0, 3.1, 0)
    g.add(beam)
    for (const s of [-1, 1]) {
      const leg = new THREE.Mesh(new THREE.BoxGeometry(0.14, 3.1, 0.9), ghostMat)
      leg.position.set(s * (span / 2), 1.55, 0)
      g.add(leg)
    }
  } else if (tool.category === 'meshalka') {
    const drum = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.65, 1.35, 16), ghostMat)
    drum.position.y = 0.75
    g.add(drum)
  } else if (tool.category === 'vibrator') {
    const tbl = new THREE.Mesh(new THREE.BoxGeometry(1.1, 0.3, 1.35), ghostMat)
    tbl.position.y = 0.15
    g.add(tbl)
  }

  const badge = createTextSprite(
    `🎯 ${tool.label} (Bosib joylang)`,
    '#0284c7',
    '#e0f2fe',
    1.6,
    0.3
  )
  badge.position.set(0, 0.85, 0)
  g.add(badge)

  ghostPreviewGroup = g
  scene.add(ghostPreviewGroup)
  updateGhostPosition()
}

function updateGhostPosition() {
  if (!ghostPreviewGroup || !activeSpawnTool.value) return
  const tool = activeSpawnTool.value
  const x =
    tool.category === 'tal_crane' || (tool.category === 'stoyka' && tool.isPair)
      ? 0.0
      : cursorPoint.value.x
  const z = cursorPoint.value.z

  let yPos = 0.0
  if (tool.category === 'mold') {
    const stoykaH = getStoykaHeightAtPoint(x, z)
    let tier = spawnTier.value
    if (autoStackOnHover.value && tier === 1) {
      const under = findMoldUnderPoint(x, z)
      if (under) tier = Math.min(3, (under.stack_tier || 1) + 1)
    }
    yPos = stoykaH + (tier - 1) * (0.36 + Number(explodeFactor.value))
  }

  ghostPreviewGroup.position.set(x, yPos, zToWorld(z))
  ghostPreviewGroup.rotation.y = (spawnRotationDeg.value * Math.PI) / 180
}

function rebuildSceneContents() {
  if (!scene) return

  scene.background = new THREE.Color(lightingMode.value === 'daylight' ? 0xdbe4ee : 0x090d16)

  const toRemove = []
  scene.traverse((obj) => {
    if (obj.userData && obj.userData.isSceneObject) {
      toRemove.push(obj)
    }
  })
  toRemove.forEach((obj) => scene.remove(obj))
  clickableItems.clear()

  buildMathematicalYard()

  for (const el of store.workshopElements) {
    const isSel = store.selectedElement && store.selectedElement.id === el.id
    const builtEl = createWorkshopElementGroup(el, isSel)
    builtEl.group.position.set(
      Number(el.pos_x || 0),
      Number(el.pos_y || 0),
      zToWorld(Number(el.pos_z || 0))
    )
    builtEl.group.rotation.y = (Number(el.rotation_deg || 0) * Math.PI) / 180
    builtEl.group.userData = { isSceneObject: true, elementId: el.id }
    scene.add(builtEl.group)

    for (const hm of builtEl.hitMeshes) {
      clickableItems.set(hm, {
        kind: 'element',
        data: el,
        rootGroup: builtEl.group,
        baseHeight: Number(el.height_m || 0.14),
      })
    }
  }

  for (const mold of store.molds) {
    if (activeTierFilter.value !== 0 && mold.stack_tier !== activeTierFilter.value) continue
    if (statusFilter.value !== 'all') {
      if (statusFilter.value === 'defect' && mold.consecutive_corner_defects < 1 && mold.status !== 'maintenance') {
        continue
      } else if (statusFilter.value !== 'defect' && mold.status !== statusFilter.value) {
        continue
      }
    }

    const isSelected = store.selectedMold && store.selectedMold.id === mold.id
    const built =
      mold.product_category === 'kolodets'
        ? createKolodetsMoldGroup(mold, isSelected)
        : createAriqMoldGroup(mold, isSelected)

    const tier = mold.stack_tier || 1
    const baseHeight = built.heightM || 0.34
    const stoykaH = getStoykaHeightAtPoint(mold.pos_x, mold.pos_z)
    const yPos = stoykaH + (tier - 1) * (baseHeight + 0.03 + Number(explodeFactor.value))

    built.group.position.set(Number(mold.pos_x || 0), yPos, zToWorld(Number(mold.pos_z || 0)))
    built.group.rotation.y = (Number(mold.rotation_deg || 0) * Math.PI) / 180
    built.group.userData = { isSceneObject: true, moldId: mold.id }

    scene.add(built.group)
    clickableItems.set(built.hitMesh, {
      kind: 'mold',
      data: mold,
      rootGroup: built.group,
      baseHeight,
    })
  }

  rebuildGhostPreview()
}

// ---------------- CAMERA PRESETS FOR THE 16.5m x (7.0m -> 8.2m) YARD ----------------
function setCameraPreset(preset) {
  activeCameraPreset.value = preset
  if (!camera || !controls) return

  if (preset === 'entrance') {
    camera.position.set(0, 4.2, zToWorld(-2.4))
    controls.target.set(0, 0.3, zToWorld(8.25))
  } else if (preset === 'back_wall') {
    camera.position.set(0, 4.4, zToWorld(18.8))
    controls.target.set(0, 0.3, zToWorld(7.5))
  } else if (preset === 'top') {
    camera.position.set(0, 19.5, 0.01)
    controls.target.set(0, 0, 0)
  } else {
    camera.position.set(-8.2, 8.8, zToWorld(-2.0))
    controls.target.set(0, 0.3, zToWorld(8.25))
  }
  controls.update()
}

// Raycast mouse against horizontal Y=0 plane and update cursorPoint
function updatePointerAndGroundPoint(event) {
  if (!renderer || !raycaster || !camera) return false
  const rect = renderer.domElement.getBoundingClientRect()
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1

  raycaster.setFromCamera(pointer, camera)
  const hit = raycaster.ray.intersectPlane(groundPlane, planeIntersectPt)
  if (!hit) return false

  const L = yardDims.value.length_m || 16.5
  const step = Number(snapStepM.value || 0.05)
  const rawZ = worldToZ(planeIntersectPt.z)
  const z = Math.max(0, Math.min(L, Math.round(rawZ / step) * step))
  const wAtZ = getYardWidthAtZ(z)
  const x = Math.max(-wAtZ / 2, Math.min(wAtZ / 2, Math.round(planeIntersectPt.x / step) * step))
  const halfRail = (yardDims.value.rail_gauge_m || 6.0) / 2

  cursorPoint.value = {
    x: Number(x.toFixed(2)),
    z: Number(z.toFixed(2)),
    widthAtZ: Number(wAtZ.toFixed(2)),
    distFromLeftWall: Number((x + wAtZ / 2).toFixed(2)),
    distFromRightWall: Number((wAtZ / 2 - x).toFixed(2)),
    distFromLeftRail: Number((x + halfRail).toFixed(2)),
    distFromRightRail: Number((halfRail - x).toFixed(2)),
  }

  if (cursorMarkerGroup) {
    cursorMarkerGroup.position.set(x, 0.025, zToWorld(z))
  }
  updateGhostPosition()
  return true
}

// ---------------- DIRECT 3D POINTER DOWN / MOVE / UP (GRAB & DRAG ANY ELEMENT IN 3D!) ----------------
let downScreenPos = { x: 0, y: 0 }

function handleCanvasPointerDown(event) {
  if (!renderer || !raycaster || !camera) return
  if (event.button === 2) {
    // Right-click cancels active spawn tool
    if (activeSpawnTool.value) {
      cancelSpawnTool()
    }
    return
  }
  if (event.button !== 0) return

  downScreenPos = { x: event.clientX, y: event.clientY }
  updatePointerAndGroundPoint(event)

  // If user is currently holding a summoned 3D Ghost element, don't start object dragging; wait for pointerup to place it
  if (activeSpawnTool.value) {
    return
  }

  // Otherwise check if user pressed on an existing 3D element (mold, stoyka, tal crane, meshalka, vibrator)
  const meshes = Array.from(clickableItems.keys())
  const intersects = raycaster.intersectObjects(meshes, false)
  if (intersects.length > 0) {
    const hitInfo = clickableItems.get(intersects[0].object)
    if (hitInfo && !(hitInfo.kind === 'element' && hitInfo.data.element_type === 'tal_rails')) {
      if (hitInfo.kind === 'mold') {
        store.selectedMold = hitInfo.data
        store.selectedElement = null
      } else {
        store.selectedElement = hitInfo.data
        store.selectedMold = null
      }

      // Lock OrbitControls so the user can smoothly drag this 3D object across the floor!
      if (controls) controls.enabled = false
      isDraggingExisting.value = true
      draggedItemInfo.value = {
        kind: hitInfo.kind,
        data: hitInfo.data,
        rootGroup: hitInfo.rootGroup,
        baseHeight: hitInfo.baseHeight || 0.34,
        newX: Number(hitInfo.data.pos_x || 0),
        newZ: Number(hitInfo.data.pos_z || 0),
        newTier: Number(hitInfo.data.stack_tier || 1),
        moved: false,
      }
    }
  }
}

function handleCanvasPointerMove(event) {
  updatePointerAndGroundPoint(event)

  // If currently dragging an existing 3D object across the floor:
  if (isDraggingExisting.value && draggedItemInfo.value) {
    const distPx = Math.hypot(event.clientX - downScreenPos.x, event.clientY - downScreenPos.y)
    if (distPx > 3) {
      draggedItemInfo.value.moved = true
    }
    if (!draggedItemInfo.value.moved) return

    const info = draggedItemInfo.value
    let targetX = cursorPoint.value.x
    const targetZ = cursorPoint.value.z

    // Keep Tal Crane centered on the 6m rails (X = 0) while sliding along Z (and move hoist along X!)
    if (info.kind === 'element' && info.data.element_type === 'tal_crane') {
      targetX = 0.0
      editItemForm.value.hoist_x = Math.max(-2.8, Math.min(2.8, cursorPoint.value.x))
    }

    info.newX = targetX
    info.newZ = targetZ
    editItemForm.value.pos_x = targetX
    editItemForm.value.pos_z = targetZ

    let yPos = Number(info.data.pos_y || 0)
    if (info.kind === 'mold') {
      const stoykaH = getStoykaHeightAtPoint(targetX, targetZ)
      let tier = info.newTier
      if (autoStackOnHover.value) {
        const under = findMoldUnderPoint(targetX, targetZ, info.data.id)
        tier = under ? 2 : 1
        info.newTier = tier
        editItemForm.value.stack_tier = tier
      }
      yPos = stoykaH + (tier - 1) * (info.baseHeight + 0.03 + Number(explodeFactor.value))
    }

    if (info.rootGroup) {
      info.rootGroup.position.set(targetX, yPos, zToWorld(targetZ))
    }
  }
}

async function handleCanvasPointerUp(event) {
  if (controls) controls.enabled = true

  // 1. Finish dragging an existing 3D object & save its new (X, Z) to database!
  if (isDraggingExisting.value && draggedItemInfo.value) {
    const info = draggedItemInfo.value
    isDraggingExisting.value = false
    draggedItemInfo.value = null

    if (info.moved) {
      editItemForm.value.pos_x = info.newX
      editItemForm.value.pos_z = info.newZ
      if (info.kind === 'mold') {
        editItemForm.value.stack_tier = info.newTier
      }
      await saveSelectedEdit()
    } else {
      rebuildSceneContents()
    }
    return
  }

  // 2. If user clicked (without dragging camera) while a 3D Spawn Tool is active, place the element!
  const distPx = Math.hypot(event.clientX - downScreenPos.x, event.clientY - downScreenPos.y)
  if (distPx <= 6 && event.button === 0) {
    updatePointerAndGroundPoint(event)
    if (activeSpawnTool.value) {
      await placePaletteItemAt(activeSpawnTool.value, cursorPoint.value.x, cursorPoint.value.z)
    } else {
      // Clicked on empty floor -> update form coordinates
      addForm.value.pos_z = cursorPoint.value.z
      setPosXAndSyncInput(cursorPoint.value.x, cursorPoint.value.z)
    }
  }
}

function handleKeyDown(event) {
  if (event.key === 'Escape' && activeSpawnTool.value) {
    cancelSpawnTool()
  } else if ((event.key === 'r' || event.key === 'R') && activeSpawnTool.value) {
    rotateSpawnOrSelected(90)
  } else if ((event.key === 'q' || event.key === 'Q') && activeSpawnTool.value) {
    spawnTier.value = spawnTier.value === 1 ? 2 : 1
    updateGhostPosition()
  }
}

function initThree() {
  const el = containerRef.value
  if (!el) return

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0xdbe4ee)

  camera = new THREE.PerspectiveCamera(48, el.clientWidth / el.clientHeight, 0.1, 250)

  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setSize(el.clientWidth, el.clientHeight)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.shadowMap.enabled = true
  renderer.shadowMap.type = THREE.PCFSoftShadowMap
  el.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.dampingFactor = 0.06
  controls.maxPolarAngle = Math.PI / 2 - 0.02

  const hemiLight = new THREE.HemisphereLight(0xf1f5f9, 0x475569, 1.1)
  scene.add(hemiLight)

  const dirLight = new THREE.DirectionalLight(0xffffff, 1.15)
  dirLight.position.set(10, 18, -10)
  dirLight.castShadow = true
  dirLight.shadow.mapSize.width = 2048
  dirLight.shadow.mapSize.height = 2048
  scene.add(dirLight)

  raycaster = new THREE.Raycaster()
  pointer = new THREE.Vector2()

  rebuildSceneContents()
  setCameraPreset('overview')

  const animate = () => {
    animationFrameId = requestAnimationFrame(animate)
    controls.update()
    renderer.render(scene, camera)
  }
  animate()
}

function handleResize() {
  const el = containerRef.value
  if (!el || !camera || !renderer) return
  camera.aspect = el.clientWidth / el.clientHeight
  camera.updateProjectionMatrix()
  renderer.setSize(el.clientWidth, el.clientHeight)
}

watch(
  () => [
    store.molds,
    store.workshopElements,
    store.selectedMold,
    store.selectedElement,
    yardDims.value,
    explodeFactor.value,
    activeTierFilter.value,
    statusFilter.value,
    colorMode.value,
    lightingMode.value,
    showLabels.value,
    showWallMode.value,
  ],
  () => {
    rebuildSceneContents()
  },
  { deep: true }
)

let resizeObserver = null

onMounted(() => {
  initThree()
  window.addEventListener('resize', handleResize)
  window.addEventListener('keydown', handleKeyDown)
  if (containerRef.value && typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(() => {
      handleResize()
    })
    resizeObserver.observe(containerRef.value)
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  window.removeEventListener('keydown', handleKeyDown)
  if (resizeObserver) resizeObserver.disconnect()
  if (animationFrameId) cancelAnimationFrame(animationFrameId)
  if (renderer) renderer.dispose()
})
</script>

<template>
  <div class="space-y-2.5">
    <!-- 1. COMPACT 3D SPAWN & DRAG-AND-DROP PALETTE DOCK (CHAQIRIB SUDRAB JOYLASH PANELI) -->
    <div class="bg-slate-900 border border-blue-500/40 rounded-xl px-3 py-2 space-y-2 shadow-xl">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-center gap-1.5 text-xs">
          <span class="px-2 py-0.5 rounded-lg bg-blue-600 text-white font-bold">
            🖐️ 3D Chaqirish va Sudrab Joylash:
          </span>
          <!-- Draggable & Clickable 3D Spawn Palette Items -->
          <button
            v-for="item in paletteCatalog"
            :key="item.id"
            draggable="true"
            @dragstart="onPaletteDragStart($event, item)"
            @click="selectSpawnTool(item)"
            :class="[
              activeSpawnTool && activeSpawnTool.id === item.id
                ? 'ring-2 ring-sky-400 bg-sky-500 text-slate-950 font-black scale-105'
                : item.color + ' hover:brightness-125 font-semibold'
            ]"
            class="px-2.5 py-1 rounded-lg border text-xs transition cursor-grab active:cursor-grabbing select-none"
            title="Bosing (3D makonda sichqonchaga ergashadi) yoki ushlab 3D maydonga sudrab tashlang!"
          >
            {{ item.label }}
          </button>
        </div>

        <div class="flex items-center gap-1.5 text-xs">
          <button
            @click="showAddPanel = !showAddPanel"
            class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-semibold transition cursor-pointer"
          >
            {{ showAddPanel ? '▲ Matematik Formani Yopish' : '📐 Qator / Matematik Kiritish ▼' }}
          </button>
          <button
            @click="store.clearWorkshopScene(true)"
            class="px-2.5 py-1 rounded-lg bg-red-950/70 hover:bg-red-700 border border-red-500/40 text-red-200 font-semibold transition cursor-pointer"
          >
            🧹 Tozalash
          </button>
        </div>
      </div>

      <!-- Active Spawn Tool Helper Controls (Shown when user summoned an element into 3D!) -->
      <div
        v-if="activeSpawnTool"
        class="flex flex-wrap items-center justify-between gap-2 bg-sky-950/80 border border-sky-400/50 rounded-lg px-3 py-1.5 text-xs"
      >
        <div class="flex flex-wrap items-center gap-2 text-sky-100">
          <span class="font-bold text-sky-300">🎯 3D Makonda: {{ activeSpawnTool.label }}</span>
          <span>— Sichqonchani 3D maydon bo'ylab yuriting va <strong>Chap tugmani bosib</strong> joylang!</span>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <button
            @click="rotateSpawnOrSelected(90)"
            class="px-2.5 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-amber-300 font-bold cursor-pointer"
          >
            🔄 90° Burish (R) [Hozir: {{ spawnRotationDeg }}°]
          </button>
          <button
            v-if="activeSpawnTool.category === 'mold'"
            @click="spawnTier = spawnTier === 1 ? 2 : 1; updateGhostPosition()"
            :class="spawnTier === 2 ? 'bg-purple-600 text-white' : 'bg-slate-800 text-purple-300'"
            class="px-2.5 py-0.5 rounded font-bold cursor-pointer"
          >
            📚 Qavat (Q): {{ spawnTier }}-Qavat
          </button>
          <label class="flex items-center gap-1 text-slate-200 cursor-pointer">
            <input type="checkbox" v-model="keepSpawningMulti" class="accent-sky-400" />
            <span>Ketma-ket qo'yish</span>
          </label>
          <button
            @click="cancelSpawnTool"
            class="px-2.5 py-0.5 rounded bg-red-600 hover:bg-red-500 text-white font-bold cursor-pointer"
          >
            ✋ Bekor qilish (Esc)
          </button>
        </div>
      </div>

      <!-- COLLAPSIBLE MATHEMATICAL BATCH / EXACT FORM -->
      <div v-if="showAddPanel" class="bg-slate-950/90 border border-slate-800 rounded-xl p-3 space-y-3 text-xs">
        <div class="flex flex-wrap items-center gap-1.5 pb-2 border-b border-slate-800">
          <span class="text-slate-400 font-semibold">Rejim:</span>
          <button
            @click="openQuickAdd('mold_row', 'A30')"
            :class="addCategory === 'mold_row' ? 'bg-blue-600 text-white font-bold' : 'bg-slate-800 text-slate-300'"
            class="px-2.5 py-1 rounded-lg cursor-pointer"
          >
            📐 Qator Qilib Qo'shish (N ta qolip + 2 ta Stoyka)
          </button>
          <button
            @click="openQuickAdd('stoyka')"
            :class="addCategory === 'stoyka' ? 'bg-amber-500 text-slate-950 font-bold' : 'bg-slate-800 text-slate-300'"
            class="px-2.5 py-1 rounded-lg cursor-pointer"
          >
            🧱 2 ta Stoyka (Aniq koordinata)
          </button>
          <button
            @click="openQuickAdd('mold_single')"
            :class="addCategory === 'mold_single' ? 'bg-emerald-500 text-slate-950 font-bold' : 'bg-slate-800 text-slate-300'"
            class="px-2.5 py-1 rounded-lg cursor-pointer"
          >
            + Yakka Qolip (Aniq koordinata)
          </button>
          <button
            @click="openQuickAdd('yard_dims')"
            :class="addCategory === 'yard_dims' ? 'bg-slate-200 text-slate-950 font-bold' : 'bg-slate-800 text-slate-300'"
            class="px-2.5 py-1 rounded-lg cursor-pointer"
          >
            📏 Maydon O'lchamlari (16.5m × 7m/8.2m)
          </button>
        </div>

        <div v-if="addCategory !== 'yard_dims' && addCategory !== 'tal_rails'" class="grid grid-cols-1 md:grid-cols-4 gap-3 pb-2 border-b border-slate-800/80">
          <div>
            <label class="block text-slate-400 mb-1 font-semibold">
              Eshikdan masofa Z (0 .. {{ yardDims.length_m }} m):
            </label>
            <input
              type="number"
              step="0.1"
              min="0"
              :max="yardDims.length_m"
              v-model.number="addForm.pos_z"
              class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono"
            />
          </div>

          <div>
            <label class="block text-slate-400 mb-1 font-semibold">
              Kenglik bo'yicha o'lchov nuqtasi (X):
            </label>
            <select
              v-model="xRefMode"
              class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white"
            >
              <option value="center">Markaziy o'qdan (X = 0.0m o'rta)</option>
              <option value="left_rail">Chap Tal relsidan (X = -3.0m dan o'ngga)</option>
              <option value="left_wall">Chap devordan ichkariga (metrda)</option>
            </select>
          </div>

          <div>
            <label class="block text-slate-400 mb-1 font-semibold">
              {{
                xRefMode === 'center'
                  ? 'Markazdan X (-chap / +o\'ng, m):'
                  : xRefMode === 'left_rail'
                  ? 'Chap relsdan masofa (m):'
                  : 'Chap devordan masofa (m):'
              }}
            </label>
            <input
              type="number"
              step="0.05"
              v-model.number="xInputVal"
              class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono"
            />
          </div>

          <div>
            <label class="block text-slate-400 mb-1 font-semibold">Burilish burchagi (°):</label>
            <div class="flex items-center gap-1.5">
              <input
                type="number"
                step="15"
                v-model.number="addForm.rotation_deg"
                class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono"
              />
              <button @click="addForm.rotation_deg = 0" class="px-2 py-1.5 rounded bg-slate-800 text-slate-200 cursor-pointer">0°</button>
              <button @click="addForm.rotation_deg = 90" class="px-2 py-1.5 rounded bg-slate-800 text-slate-200 cursor-pointer">90°</button>
            </div>
          </div>
        </div>

        <!-- STOYKA FORM -->
        <div v-if="addCategory === 'stoyka'" class="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
          <div>
            <label class="block text-slate-400 mb-1">Nomi / Qator:</label>
            <input type="text" v-model="addForm.stoyka_name" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white" />
          </div>
          <div>
            <label class="block text-slate-400 mb-1">Stoyka turi:</label>
            <select v-model="addForm.stoyka_is_pair" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white">
              <option :value="true">Har qatorda 2 tadan (Juft stoyka)</option>
              <option :value="false">Yakka 1 ta stoyka (Brusok)</option>
            </select>
          </div>
          <div>
            <label class="block text-slate-400 mb-1">Stoyka uzunligi (Qator eni, m):</label>
            <input type="number" step="0.1" v-model.number="addForm.stoyka_row_width_m" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono" />
          </div>
          <div v-if="addForm.stoyka_is_pair">
            <label class="block text-slate-400 mb-1">2 ta stoyka orasi (m):</label>
            <input type="number" step="0.05" v-model.number="addForm.stoyka_pair_spacing_m" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono" />
          </div>
          <div>
            <button @click="submitAddElement" class="w-full py-2 px-4 rounded-xl bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold transition cursor-pointer">
              ➕ Stoykani Qo'shish
            </button>
          </div>
        </div>

        <!-- BATCH ROW FORM -->
        <div v-else-if="addCategory === 'mold_row'" class="space-y-2.5">
          <div class="grid grid-cols-1 md:grid-cols-6 gap-3 items-end">
            <div>
              <label class="block text-slate-400 mb-1">Qolip o'lchami:</label>
              <select v-model="addForm.row_mold_code" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-bold">
                <option value="A22">22-lik Ariq Qolipi</option>
                <option value="A30">30-lik Ariq Qolipi</option>
                <option value="A40">40-lik Ariq Qolipi</option>
                <option value="A50">50-lik Ariq Qolipi</option>
                <option value="K104">Kolodets Qolipi (Ø118/104)</option>
              </select>
            </div>
            <div>
              <label class="block text-slate-400 mb-1">Qatorda nechta (N dona):</label>
              <input type="number" min="1" max="20" v-model.number="addForm.row_count" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono" />
            </div>
            <div>
              <label class="block text-slate-400 mb-1">Qoliplar orasi (zazor, sm):</label>
              <input type="number" min="0" max="100" v-model.number="addForm.row_gap_cm" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono" />
            </div>
            <div>
              <label class="block text-slate-400 mb-1">Tekislash (X bo'yicha):</label>
              <select v-model="addForm.row_align" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white">
                <option value="center">Markazda (Simmetrik)</option>
                <option value="from_x">Boshlanish X nuqtasidan</option>
              </select>
            </div>
            <div>
              <label class="flex items-center gap-2 text-amber-300 font-semibold cursor-pointer py-1.5">
                <input type="checkbox" v-model="addForm.row_add_stoyka_pair" class="accent-amber-500 w-4 h-4" />
                <span>Tagiga 2 ta Stoyka</span>
              </label>
            </div>
            <div>
              <button @click="submitAddElement" class="w-full py-2 px-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold transition cursor-pointer">
                ➕ {{ addForm.row_count }} ta Qolipni Terish
              </button>
            </div>
          </div>
          <div class="flex flex-wrap items-center justify-between gap-2 bg-slate-900/90 border border-slate-800 rounded-lg px-3 py-1.5 text-[11px]">
            <div>
              1 ta qolip eni = <strong class="text-white">{{ rowMathPreview.moldWidthCm }} sm</strong> •
              Qadam = <strong class="text-white">{{ rowMathPreview.stepCm }} sm</strong> •
              Jami kenglik = <strong class="text-sky-300">{{ rowMathPreview.totalWidthM }} m</strong>
            </div>
            <div>
              <span v-if="rowMathPreview.fitsInsideRails" class="text-emerald-300 font-semibold">
                ✅ 6.0m Tal relslari orasiga sig'adi
              </span>
              <span v-else class="text-amber-300 font-semibold">
                ⚠️ 6.0m relsdan kengroq (Devor orasi: {{ rowMathPreview.yardWidthAtZ }}m)
              </span>
            </div>
          </div>
        </div>

        <!-- SINGLE MOLD FORM -->
        <div v-else-if="addCategory === 'mold_single'" class="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
          <div>
            <label class="block text-slate-400 mb-1">Qolip turi:</label>
            <select v-model="addForm.mold_code" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-bold">
              <option value="A22">22-lik Ariq Qolipi</option>
              <option value="A30">30-lik Ariq Qolipi</option>
              <option value="A40">40-lik Ariq Qolipi</option>
              <option value="A50">50-lik Ariq Qolipi</option>
              <option value="K104">Kolodets Qolipi (Ø118/104)</option>
            </select>
          </div>
          <div>
            <label class="block text-slate-400 mb-1">Qolip raqami:</label>
            <input type="text" placeholder="Avto (#01...)" v-model="addForm.mold_number" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white" />
          </div>
          <div>
            <label class="block text-slate-400 mb-1">Qavati:</label>
            <select v-model.number="addForm.mold_tier" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white">
              <option :value="1">1-Qavat</option>
              <option :value="2">2-Qavat (Ustma-ust)</option>
              <option :value="3">3-Qavat</option>
            </select>
          </div>
          <div>
            <label class="block text-slate-400 mb-1">Holati:</label>
            <select v-model="addForm.mold_status" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white">
              <option value="empty">Bo'sh</option>
              <option value="poured">Quyilgan</option>
              <option value="ready_demold">Tayyor</option>
            </select>
          </div>
          <div>
            <button @click="submitAddElement" class="w-full py-2 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold transition cursor-pointer">
              ➕ Qolipni Qo'shish
            </button>
          </div>
        </div>

        <!-- YARD DIMS FORM -->
        <div v-else-if="addCategory === 'yard_dims'" class="grid grid-cols-1 md:grid-cols-5 gap-3 items-end">
          <div>
            <label class="block text-slate-400 mb-1">Uzunligi (Eshikdan oxirigacha, m):</label>
            <input type="number" step="0.1" v-model.number="yardDims.length_m" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono" />
          </div>
          <div>
            <label class="block text-slate-400 mb-1">Eshik tomon kengligi (Z=0m, m):</label>
            <input type="number" step="0.1" v-model.number="yardDims.width_front_m" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono" />
          </div>
          <div>
            <label class="block text-slate-400 mb-1">Oxirgi devor kengligi (Z={{ yardDims.length_m }}m, m):</label>
            <input type="number" step="0.1" v-model.number="yardDims.width_back_m" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono" />
          </div>
          <div>
            <label class="block text-slate-400 mb-1">Tal relslari orasi (m):</label>
            <input type="number" step="0.1" v-model.number="yardDims.rail_gauge_m" class="w-full bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1.5 text-white font-mono" />
          </div>
          <div>
            <button @click="submitAddElement" class="w-full py-2 px-4 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-bold transition cursor-pointer">
              💾 O'lchamni Saqlash
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- 2. SELECTED ELEMENT / MOLD MATHEMATICAL INSPECTOR (OPENS WHEN ANY ITEM IN 3D IS CLICKED OR DRAGGED) -->
    <div
      v-if="editItemForm.kind"
      class="bg-slate-900 border-2 border-sky-500/70 rounded-xl px-3.5 py-2.5 space-y-2 text-xs shadow-xl"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-center gap-2">
          <span class="px-2 py-0.5 rounded bg-sky-500 text-slate-950 font-bold">
            🖐️ Tanlangan (Sudrab surish mumkin): {{ editItemForm.name }}
          </span>
          <span class="text-slate-300 font-mono">
            Eshikdan Z = <strong class="text-amber-300">{{ editItemForm.pos_z }}m</strong> •
            Markazdan X = <strong class="text-emerald-300">{{ editItemForm.pos_x }}m</strong> •
            Chap relsdan = <strong>{{ (editItemForm.pos_x + yardDims.rail_gauge_m / 2).toFixed(2) }}m</strong>
          </span>
        </div>
        <div class="flex items-center gap-1">
          <button @click="nudgeSelected(-0.05, 0)" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 cursor-pointer">◀ X -5sm</button>
          <button @click="nudgeSelected(0.05, 0)" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 cursor-pointer">X +5sm ▶</button>
          <button @click="nudgeSelected(0, -0.05)" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 cursor-pointer">▲ Z -5sm</button>
          <button @click="nudgeSelected(0, 0.05)" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-200 cursor-pointer">▼ Z +5sm</button>
          <button @click="rotateSpawnOrSelected(90)" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-amber-300 font-bold cursor-pointer">🔄 90°</button>
          <button @click="deleteSelectedItem" class="px-2.5 py-1 rounded bg-red-600 hover:bg-red-500 text-white font-bold cursor-pointer ml-1">🗑️ O'chirish</button>
          <button @click="store.selectedMold = null; store.selectedElement = null" class="px-2 py-1 rounded bg-slate-800 text-slate-400 hover:text-white cursor-pointer">✕</button>
        </div>
      </div>

      <div class="grid grid-cols-2 md:grid-cols-6 gap-2 items-end">
        <div>
          <label class="block text-slate-400 mb-0.5">Eshikdan Z (m):</label>
          <input type="number" step="0.05" v-model.number="editItemForm.pos_z" @change="saveSelectedEdit" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-white font-mono" />
        </div>
        <div>
          <label class="block text-slate-400 mb-0.5">Markazdan X (m):</label>
          <input type="number" step="0.05" v-model.number="editItemForm.pos_x" @change="saveSelectedEdit" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-white font-mono" />
        </div>
        <div v-if="editItemForm.kind === 'mold'">
          <label class="block text-slate-400 mb-0.5">Qavati:</label>
          <select v-model.number="editItemForm.stack_tier" @change="saveSelectedEdit" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-white">
            <option :value="1">1-Qavat</option>
            <option :value="2">2-Qavat (Ustma-ust)</option>
            <option :value="3">3-Qavat</option>
          </select>
        </div>
        <div v-if="editItemForm.kind === 'element' && editItemForm.element_type === 'tal_crane'">
          <label class="block text-amber-300 mb-0.5">Tal Ilgagi X (-2.8..+2.8m):</label>
          <input type="range" min="-2.8" max="2.8" step="0.05" v-model.number="editItemForm.hoist_x" @change="saveSelectedEdit" class="w-full accent-amber-500" />
        </div>
        <div v-if="editItemForm.kind === 'element' && editItemForm.element_type === 'stoyka'">
          <label class="block text-slate-400 mb-0.5">2 ta Stoyka orasi (m):</label>
          <input type="number" step="0.05" v-model.number="editItemForm.length_m" @change="saveSelectedEdit" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-white font-mono" />
        </div>
        <div>
          <label class="block text-slate-400 mb-0.5">Burchagi (°):</label>
          <input type="number" step="15" v-model.number="editItemForm.rotation_deg" @change="saveSelectedEdit" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-white font-mono" />
        </div>
        <div v-if="editItemForm.kind === 'mold'">
          <label class="block text-slate-400 mb-0.5">Holati:</label>
          <select v-model="editItemForm.status" @change="saveSelectedEdit" class="w-full bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-white">
            <option value="empty">Bo'sh</option>
            <option value="poured">Quyilgan</option>
            <option value="ready_demold">Tayyor</option>
            <option value="maintenance">Remont</option>
          </select>
        </div>
        <div>
          <button @click="saveSelectedEdit" class="w-full py-1 px-3 rounded-lg bg-sky-500 hover:bg-sky-400 text-slate-950 font-bold transition cursor-pointer">
            💾 Saqlash
          </button>
        </div>
      </div>
    </div>

    <!-- 3. CAMERA PRESETS & 3D VIEW CONTROLS TOOLBAR -->
    <div class="flex flex-wrap items-center justify-between gap-2 bg-slate-900 border border-slate-800 rounded-xl px-3 py-1.5 text-xs">
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="text-slate-400 font-semibold mr-1">📷 Rakurslar:</span>
        <button
          @click="setCameraPreset('overview')"
          :class="activeCameraPreset === 'overview' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'"
          class="px-2.5 py-1 rounded-lg font-semibold transition cursor-pointer"
        >
          🏭 Umumiy 3D (16.5m × 7m/8.2m)
        </button>
        <button
          @click="setCameraPreset('entrance')"
          :class="activeCameraPreset === 'entrance' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'"
          class="px-2.5 py-1 rounded-lg font-semibold transition cursor-pointer"
        >
          🚪 Eshik Tomondan (Z=0m, 7.0m)
        </button>
        <button
          @click="setCameraPreset('back_wall')"
          :class="activeCameraPreset === 'back_wall' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'"
          class="px-2.5 py-1 rounded-lg font-semibold transition cursor-pointer"
        >
          🧱 Oxirgi Shlakoblok Devordan (Z=16.5m, 8.2m)
        </button>
        <button
          @click="setCameraPreset('top')"
          :class="activeCameraPreset === 'top' ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-300 hover:bg-slate-700'"
          class="px-2.5 py-1 rounded-lg font-semibold transition cursor-pointer"
        >
          🦅 Tepadan Chizma
        </button>
      </div>

      <div class="flex flex-wrap items-center gap-1.5">
        <button
          @click="snapStepM = snapStepM === 0.05 ? 0.01 : 0.05"
          class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-amber-300 font-semibold transition cursor-pointer"
        >
          📏 Qadam: {{ snapStepM === 0.05 ? '5 sm' : '1 sm (Aniq)' }}
        </button>
        <button
          @click="showWallMode = showWallMode === 'low' ? 'full' : 'low'"
          class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-medium transition cursor-pointer"
        >
          {{ showWallMode === 'low' ? '🧱 Devor: Past' : '🧱 Devor: 2.3m' }}
        </button>
        <button
          @click="lightingMode = lightingMode === 'daylight' ? 'dark' : 'daylight'"
          class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-medium transition cursor-pointer"
        >
          {{ lightingMode === 'daylight' ? '☀️ Kunduzgi' : '🌙 Tungi' }}
        </button>
        <button
          @click="showLabels = !showLabels"
          class="px-2.5 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-medium transition cursor-pointer"
        >
          {{ showLabels ? '🏷️ Yozuvlar: Yoq' : '🏷️ Yozuvlar: O\'ch' }}
        </button>
      </div>
    </div>

    <!-- 4. MAIN 3D WEBGL CANVAS WITH DIRECT DRAG & LIVE MATHEMATICAL HUD -->
    <div class="relative w-full h-[calc(100vh-175px)] min-h-[520px] rounded-2xl overflow-hidden border border-slate-800 bg-slate-950 shadow-2xl">
      <!-- Top Floating Status & Tier Bar -->
      <div class="absolute top-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 pointer-events-none">
        <div class="flex flex-wrap items-center gap-1 bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-xl px-2.5 py-1.5 pointer-events-auto text-xs">
          <span class="text-slate-400 mr-1">Elementlar: <strong class="text-white">{{ store.workshopElements.length }}</strong> • Qoliplar: <strong class="text-white">{{ store.molds.length }}</strong></span>
          <button
            @click="statusFilter = 'all'"
            :class="statusFilter === 'all' ? 'bg-blue-600 text-white' : 'text-slate-300 hover:bg-slate-800'"
            class="px-2 py-0.5 rounded-lg font-medium transition cursor-pointer"
          >
            Barchasi
          </button>
          <button
            @click="statusFilter = 'poured'"
            :class="statusFilter === 'poured' ? 'bg-blue-600 text-white' : 'text-slate-300 hover:bg-slate-800'"
            class="px-2 py-0.5 rounded-lg transition cursor-pointer"
          >
            Quyilgan
          </button>
          <button
            @click="statusFilter = 'ready_demold'"
            :class="statusFilter === 'ready_demold' ? 'bg-emerald-600 text-white' : 'text-slate-300 hover:bg-slate-800'"
            class="px-2 py-0.5 rounded-lg transition cursor-pointer"
          >
            Tayyor
          </button>
          <button
            @click="statusFilter = 'empty'"
            :class="statusFilter === 'empty' ? 'bg-slate-600 text-white' : 'text-slate-300 hover:bg-slate-800'"
            class="px-2 py-0.5 rounded-lg transition cursor-pointer"
          >
            Bo'sh
          </button>
        </div>

        <!-- Live Mathematical Cursor Coordinate Readout -->
        <div class="bg-slate-900/95 backdrop-blur-md border border-sky-500/50 rounded-xl px-3 py-1.5 text-xs font-mono text-slate-200 pointer-events-auto">
          <span class="text-sky-400 font-bold">📐 Kursor:</span>
          Eshikdan Z = <strong class="text-amber-300">{{ cursorPoint.z }}m</strong> •
          Markazdan X = <strong class="text-emerald-300">{{ cursorPoint.x > 0 ? '+' : '' }}{{ cursorPoint.x }}m</strong> •
          Kenglik W(Z) = <strong>{{ cursorPoint.widthAtZ }}m</strong> •
          Chap relsdan = <strong>{{ cursorPoint.distFromLeftRail }}m</strong>
        </div>
      </div>

      <!-- Bottom Helper Bar -->
      <div class="absolute bottom-3 left-3 right-3 z-10 flex flex-wrap items-center justify-between gap-2 bg-slate-900/85 backdrop-blur-md border border-slate-700 rounded-xl px-3.5 py-1.5 text-xs text-slate-200 pointer-events-none">
        <div>
          <span class="text-blue-400 font-bold">Maydon:</span>
          <strong>{{ yardDims.length_m }}m</strong> (Eshik <strong>{{ yardDims.width_front_m }}m</strong> → Oxiri <strong>{{ yardDims.width_back_m }}m</strong>, Rels <strong>{{ yardDims.rail_gauge_m }}m</strong>)
        </div>
        <div class="text-amber-300 font-medium">
          🖐️ Tepadagi elementni bosib (yoki sudrab) 3D maydonga qo'ying • Mavjud elementni ustidan ushlab sudrab suring!
        </div>
      </div>

      <!-- Three.js Mount -->
      <div
        ref="containerRef"
        @pointerdown="handleCanvasPointerDown"
        @pointermove="handleCanvasPointerMove"
        @pointerup="handleCanvasPointerUp"
        @dragover="onCanvasDragOver"
        @drop="onCanvasDrop"
        @contextmenu.prevent
        :class="activeSpawnTool ? 'cursor-copy' : isDraggingExisting ? 'cursor-grabbing' : 'cursor-grab'"
        class="w-full h-full"
      ></div>
    </div>
  </div>
</template>
