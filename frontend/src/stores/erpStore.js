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
    await fetchAll()
    return res
  }

  async function createBatchRowMolds(payload) {
    const res = await apiFetch('/api/molds/batch-row', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
    return res
  }

  async function updateMoldPosition(moldId, payload) {
    await apiFetch(`/api/molds/${moldId}/position`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    await fetchAll()
  }

  async function deleteMold(moldId) {
    await apiFetch(`/api/molds/${moldId}`, {
      method: 'DELETE',
    })
    if (selectedMold.value && selectedMold.value.id === moldId) {
      selectedMold.value = null
    }
    await fetchAll()
  }

  async function createWorkshopElement(payload) {
    const res = await apiFetch('/api/workshop-elements', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
    await fetchAll()
    selectedElement.value = res
    selectedMold.value = null
    return res
  }

  async function updateWorkshopElement(elemId, payload) {
    const res = await apiFetch(`/api/workshop-elements/${elemId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    })
    await fetchAll()
    return res
  }

  async function deleteWorkshopElement(elemId) {
    await apiFetch(`/api/workshop-elements/${elemId}`, {
      method: 'DELETE',
    })
    if (selectedElement.value && selectedElement.value.id === elemId) {
      selectedElement.value = null
    }
    await fetchAll()
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
    createOrder,
    createSale,
    createMissingSize,
    createMaterialBatch,
    depleteMaterialBatch,
  }
})
