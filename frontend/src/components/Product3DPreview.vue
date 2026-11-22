<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'

const props = defineProps({
  product: {
    type: Object,
    required: true,
  },
})

const mountRef = ref(null)
const showWireframe = ref(false)
const invertedCastingMode = ref(false)

let scene = null
let camera = null
let renderer = null
let controls = null
let meshGroup = null
let animId = null

function buildProductGeometry() {
  if (!scene || !props.product) return

  if (meshGroup) {
    scene.remove(meshGroup)
  }
  meshGroup = new THREE.Group()

  const p = props.product
  if (p.category === 'kolodets') {
    const outerR = (p.outer_diameter_cm || 118) / 200
    const innerR = (p.inner_diameter_cm || 104) / 200
    const h = (p.default_height_cm || p.max_height_cm || 60) / 100

    const shape = new THREE.Shape()
    shape.absarc(0, 0, outerR, 0, Math.PI * 2, false)
    const hole = new THREE.Path()
    hole.absarc(0, 0, innerR, 0, Math.PI * 2, true)
    shape.holes.push(hole)

    const geo = new THREE.ExtrudeGeometry(shape, {
      depth: h,
      bevelEnabled: false,
      curveSegments: 48,
    })
    geo.rotateX(-Math.PI / 2)
    geo.center()

    const mat = new THREE.MeshStandardMaterial({
      color: 0x94a3b8,
      roughness: 0.7,
      metalness: 0.15,
      wireframe: showWireframe.value,
    })
    const mesh = new THREE.Mesh(geo, mat)
    meshGroup.add(mesh)

    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geo, 25),
      new THREE.LineBasicMaterial({ color: 0xf59e0b })
    )
    meshGroup.add(edges)
  } else {
    // Trapezoidal U-channel Ariq (e.g. 30-lik: inner bottom 15cm, side 22cm, mouth 29-30cm)
    const inBot = (p.inner_bottom_cm || 15) / 100
    const inTop = (p.inner_top_cm || 30) / 100
    const inSide = (p.inner_side_cm || 22) / 100
    const wall = (p.wall_thickness_cm || 5.5) / 100
    const len = (p.length_cm || 150) / 100

    const halfDiff = Math.max((inTop - inBot) / 2, 0)
    const inDepth = inSide > halfDiff ? Math.sqrt(inSide * inSide - halfDiff * halfDiff) : inSide

    const outBot = inBot + 2 * wall
    const outTop = inTop + 2 * wall
    const outDepth = inDepth + wall

    // Cross-section shape of trapezoidal concrete trench (Ariq)
    const shape = new THREE.Shape()
    shape.moveTo(-outBot / 2, 0)
    shape.lineTo(outBot / 2, 0)
    shape.lineTo(outTop / 2, outDepth)
    shape.lineTo(inTop / 2, outDepth)
    shape.lineTo(inBot / 2, wall)
    shape.lineTo(-inBot / 2, wall)
    shape.lineTo(-inTop / 2, outDepth)
    shape.lineTo(-outTop / 2, outDepth)
    shape.closePath()

    const geo = new THREE.ExtrudeGeometry(shape, {
      depth: len,
      bevelEnabled: false,
    })
    geo.center()

    const mat = new THREE.MeshStandardMaterial({
      color: 0x94a3b8,
      roughness: 0.72,
      metalness: 0.12,
      wireframe: showWireframe.value,
    })
    const mesh = new THREE.Mesh(geo, mat)
    meshGroup.add(mesh)

    const edges = new THREE.LineSegments(
      new THREE.EdgesGeometry(geo),
      new THREE.LineBasicMaterial({ color: 0x38bdf8 })
    )
    meshGroup.add(edges)

    if (invertedCastingMode.value) {
      meshGroup.rotation.z = Math.PI
    }
  }

  scene.add(meshGroup)
}

onMounted(() => {
  const el = mountRef.value
  if (!el) return

  scene = new THREE.Scene()
  scene.background = new THREE.Color(0x0b1120)

  camera = new THREE.PerspectiveCamera(42, el.clientWidth / el.clientHeight, 0.05, 50)
  camera.position.set(1.6, 1.2, 2.2)

  renderer = new THREE.WebGLRenderer({ antialias: true })
  renderer.setSize(el.clientWidth, el.clientHeight)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  el.appendChild(renderer.domElement)

  controls = new OrbitControls(camera, renderer.domElement)
  controls.enableDamping = true
  controls.autoRotate = true
  controls.autoRotateSpeed = 1.4

  scene.add(new THREE.AmbientLight(0xffffff, 0.85))
  const dLight = new THREE.DirectionalLight(0xffffff, 1.2)
  dLight.position.set(3, 5, 4)
  scene.add(dLight)

  buildProductGeometry()

  const animate = () => {
    animId = requestAnimationFrame(animate)
    controls.update()
    renderer.render(scene, camera)
  }
  animate()
})

watch(
  () => [props.product, showWireframe.value, invertedCastingMode.value],
  () => {
    buildProductGeometry()
  },
  { deep: true }
)

onBeforeUnmount(() => {
  if (animId) cancelAnimationFrame(animId)
  if (renderer) renderer.dispose()
})
</script>

<template>
  <div class="relative w-full h-64 rounded-xl overflow-hidden border border-slate-800 bg-slate-950">
    <div class="absolute top-2.5 left-2.5 z-10 bg-slate-900/85 backdrop-blur px-2.5 py-1 rounded-lg border border-slate-700 text-xs text-slate-200 font-medium">
      3D Parametrik Model: <span class="text-blue-400 font-bold">{{ product.name }}</span>
    </div>
    <div class="absolute top-2.5 right-2.5 z-10 flex items-center gap-1.5">
      <button
        v-if="product.category === 'ariq'"
        @click="invertedCastingMode = !invertedCastingMode"
        class="px-2.5 py-1 rounded-lg bg-slate-900/90 hover:bg-blue-600 border border-slate-700 text-xs text-slate-200 transition cursor-pointer"
      >
        {{ invertedCastingMode ? '🔄 Quyish holati (To\'nkarilgan)' : '💧 Tayyor holat (Suv yo\'li)' }}
      </button>
      <button
        @click="showWireframe = !showWireframe"
        class="px-2.5 py-1 rounded-lg bg-slate-900/90 hover:bg-slate-800 border border-slate-700 text-xs text-slate-300 transition cursor-pointer"
      >
        {{ showWireframe ? 'Solid' : 'Karkas' }}
      </button>
    </div>
    <div ref="mountRef" class="w-full h-full cursor-grab"></div>
  </div>
</template>
