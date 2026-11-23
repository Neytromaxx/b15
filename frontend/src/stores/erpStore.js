import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useErpStore = defineStore('erp', () => {
  const loading = ref(false)
  const settings = ref({
    company_name: 'Beton Ariq & Kolodets Zavodi',
    region_id: 'fergana',
    region_name: "Farg'ona",
    workshop_width_m: 7.0,
    workshop_width_front_m: 7.0,
    workshop_width_back_m: 8.2,
    workshop_length_m: 16.5,
    rail_gauge_m: 6.0,
  })
  const regions = ref([])
  const weather = ref(null)
  const products = ref([])
  const molds = ref([])
  const workshopElements = ref([])
  const dailyLogs = ref([])
  const sizeBatches = ref([])
  const workersSummary = ref([])
  const sizeTotals = ref({})
  const orders = ref([])
  const sales = ref([])
  const missingSizes = ref([])
  const materials = ref([])
  const analytics = ref({
    financials: {
      total_sales_revenue: 0,
      cash_received: 0,
      order_fulfillment_sales: { qty: 0, amount: 0 },
      urgent_pickup_sales: { qty: 0, amount: 0 },
      material_expenses: 0,
      labor_expenses: 0,
      repair_expenses: 0,
      total_expenses: 0,
      net_balance: 0,
    },
    product_demand: [],
    missing_demand: [],
    problem_molds: [],
    active_materials: {},
    recommendations: [],
  })

  const selectedMold = ref(null)
  const selectedElement = ref(null)

  async function apiFetch(url, options = {}) {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
    if (!res.ok) {
      const errText = await res.text()
      throw new Error(errText || `HTTP error ${res.status}`)
    }
    return await res.json()
  }

  async function fetchAll() {
    loading.value = true
    try {
      const [
        settingsData,
        weatherData,
        productsData,
        moldsData,
        elementsData,
        logsData,
        sizeBatchesData,
        ordersData,
        salesData,
        missingData,
        materialsData,
        analyticsData,
      ] = await Promise.all([
        apiFetch('/api/settings'),
        apiFetch('/api/weather/current'),
        apiFetch('/api/products'),
        apiFetch('/api/molds'),
        apiFetch('/api/workshop-elements'),
        apiFetch('/api/daily-logs'),
        apiFetch('/api/production/size-batches'),
        apiFetch('/api/orders'),
        apiFetch('/api/sales'),
        apiFetch('/api/missing-sizes'),
        apiFetch('/api/materials'),
        apiFetch('/api/analytics/dashboard'),
      ])

      settings.value = settingsData.settings
      regions.value = settingsData.regions
      weather.value = weatherData.weather
      products.value = productsData
      molds.value = moldsData
      workshopElements.value = elementsData
      dailyLogs.value = logsData
      sizeBatches.value = sizeBatchesData.batches || []
      workersSummary.value = sizeBatchesData.workers_summary || []
      sizeTotals.value = sizeBatchesData.size_totals || {}
      orders.value = ordersData
      sales.value = salesData
      missingSizes.value = missingData
      materials.value = materialsData
      analytics.value = analyticsData

      if (selectedMold.value) {
        const updated = moldsData.find((m) => m.id === selectedMold.value.id)
        selectedMold.value = updated || null
      }
      if (selectedElement.value) {
        const updatedEl = elementsData.find((e) => e.id === selectedElement.value.id)
        selectedElement.value = updatedEl || null
      }
    } catch (err) {
      console.error('Error loading ERP data:', err)
    } finally {
      loading.value = false
    }
  }

  async function updateSettings(payload) {
    await apiFetch('/api/settings', {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    await fetchAll()
  }

  async function createProduct(payload) {
    await apiFetch('/api/products', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
  }

  async function createMold(payload) {
    const res = await apiFetch('/api/molds', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    if (res && res.mold) {
      const created = { ...res.mold }
      if (molds.value.some((m) => m.id === created.id)) {
        const maxId = molds.value.reduce((acc, m) => Math.max(acc, Number(m.id || 0)), 0)
        created.id = maxId + 1
      }
      molds.value = [...molds.value, created]
      selectedMold.value = created
      selectedElement.value = null
    } else {
      await fetchAll()
    }
    return res
  }

  async function createBatchRowMolds(payload) {
    const res = await apiFetch('/api/molds/batch-row', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    if (res && Array.isArray(res.created_molds)) {
      let maxMoldId = molds.value.reduce((acc, m) => Math.max(acc, Number(m.id || 0)), 0)
      const toAdd = res.created_molds.map((cm) => {
        const item = { ...cm }
        if (molds.value.some((m) => m.id === item.id)) {
          maxMoldId += 1
          item.id = maxMoldId
        } else {
          maxMoldId = Math.max(maxMoldId, Number(item.id || 0))
        }
        return item
      })
      molds.value = [...molds.value, ...toAdd]
      if (res.stoyka_element) {
        const stEl = { ...res.stoyka_element }
        if (workshopElements.value.some((e) => e.id === stEl.id)) {
          const maxElId = workshopElements.value.reduce((acc, e) => Math.max(acc, Number(e.id || 0)), 0)
          stEl.id = maxElId + 1
        }
        workshopElements.value = [...workshopElements.value, stEl]
      }
    } else {
      await fetchAll()
    }
    return res
  }

  async function updateMoldPosition(moldId, payload) {
    const res = await apiFetch(`/api/molds/${moldId}/position`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    const idx = molds.value.findIndex((m) => m.id === moldId)
    if (idx !== -1) {
      const updated = res && res.mold
        ? { ...molds.value[idx], ...res.mold, id: moldId }
        : { ...molds.value[idx], ...payload, id: moldId }
      const nextList = [...molds.value]
      nextList[idx] = updated
      molds.value = nextList
      if (selectedMold.value && selectedMold.value.id === moldId) {
        selectedMold.value = updated
      }
    }
    return res
  }

  async function deleteMold(moldId) {
    await apiFetch(`/api/molds/${moldId}`, {
      method: 'DELETE',
    })
    molds.value = molds.value.filter((m) => m.id !== moldId)
    if (selectedMold.value && selectedMold.value.id === moldId) {
      selectedMold.value = null
    }
  }

  async function createWorkshopElement(payload) {
    const res = await apiFetch('/api/workshop-elements', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    const created = { ...res }
    if (workshopElements.value.some((e) => e.id === created.id)) {
      const maxId = workshopElements.value.reduce((acc, e) => Math.max(acc, Number(e.id || 0)), 0)
      created.id = maxId + 1
    }
    workshopElements.value = [...workshopElements.value, created]
    selectedElement.value = created
    selectedMold.value = null
    return created
  }

  async function updateWorkshopElement(elemId, payload) {
    const res = await apiFetch(`/api/workshop-elements/${elemId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    const updated = { ...res, id: elemId }
    const idx = workshopElements.value.findIndex((e) => e.id === elemId)
    if (idx !== -1) {
      const nextList = [...workshopElements.value]
      nextList[idx] = { ...nextList[idx], ...updated }
      workshopElements.value = nextList
    } else {
      workshopElements.value = [...workshopElements.value, updated]
    }
    if (selectedElement.value && selectedElement.value.id === elemId) {
      selectedElement.value = { ...selectedElement.value, ...updated }
    }
    return updated
  }

  async function deleteWorkshopElement(elemId) {
    await apiFetch(`/api/workshop-elements/${elemId}`, {
      method: 'DELETE',
    })
    workshopElements.value = workshopElements.value.filter((e) => e.id !== elemId)
    if (selectedElement.value && selectedElement.value.id === elemId) {
      selectedElement.value = null
    }
  }

  async function clearWorkshopScene(keepRails = true) {
    await apiFetch(`/api/workshop/clear?keep_rails=${keepRails}`, {
      method: 'POST',
    })
    selectedMold.value = null
    selectedElement.value = null
    await fetchAll()
  }

  async function repairMold(moldId, payload) {
    await apiFetch(`/api/molds/${moldId}/repair`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
  }

  async function demoldBatch(payload) {
    const res = await apiFetch('/api/production/demold', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
    return res
  }

  async function castBatch(payload) {
    const res = await apiFetch('/api/production/cast', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
    return res
  }

  async function cyclicCast(payload) {
    const res = await apiFetch('/api/production/cyclic-cast', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
    return res
  }

  async function createSizeBatch(payload) {
    const res = await apiFetch('/api/production/size-batches', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
    return res
  }

  async function updateSizeBatch(batchId, payload) {
    const res = await apiFetch(`/api/production/size-batches/${batchId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    await fetchAll()
    return res
  }

  async function deleteSizeBatch(batchId) {
    await apiFetch(`/api/production/size-batches/${batchId}`, {
      method: 'DELETE',
    })
    await fetchAll()
  }

  async function createOrder(payload) {
    await apiFetch('/api/orders', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
  }

  async function createSale(payload) {
    await apiFetch('/api/sales', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
  }

  async function createMissingSize(payload) {
    await apiFetch('/api/missing-sizes', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
  }

  async function createMaterialBatch(payload) {
    await apiFetch('/api/materials', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
  }

  async function depleteMaterialBatch(batchId, payload) {
    await apiFetch(`/api/materials/${batchId}/deplete`, {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
  }

  return {
    loading,
    settings,
    regions,
    weather,
    products,
    molds,
    workshopElements,
    dailyLogs,
    sizeBatches,
    workersSummary,
    sizeTotals,
    orders,
    sales,
    missingSizes,
    materials,
    analytics,
    selectedMold,
    selectedElement,
    fetchAll,
    updateSettings,
    createProduct,
    createMold,
    createBatchRowMolds,
    updateMoldPosition,
    deleteMold,
    createWorkshopElement,
    updateWorkshopElement,
    deleteWorkshopElement,
    clearWorkshopScene,
    repairMold,
    demoldBatch,
    castBatch,
    cyclicCast,
    createSizeBatch,
    updateSizeBatch,
    deleteSizeBatch,
    createOrder,
    createSale,
    createMissingSize,
    createMaterialBatch,
    depleteMaterialBatch,
  }
})
