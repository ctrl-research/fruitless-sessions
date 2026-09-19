import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import './style.css'
import { loadTake } from './bundle'
import { BrainPoints } from './brain/points'
import { HeroMeshes, type MeshIndex } from './brain/meshes'
import { Transport } from './transport'

const params = new URLSearchParams(location.search)
const takeName = params.get('take') ?? 'smoke'
const base = `${import.meta.env.BASE_URL}takes/${takeName}`

async function main() {
  const status = document.getElementById('status')!
  status.textContent = `loading ${takeName}…`
  const take = await loadTake(base)
  const fly = take.flies[0]
  const soma = fly.layers['soma']
  status.textContent = ''

  document.getElementById('title')!.textContent = `${take.manifest.name} · ${fly.entry.role}`
  document.getElementById('meta')!.textContent =
    `${take.manifest.shared.with_soma.toLocaleString()} of ${take.manifest.shared.n_neurons.toLocaleString()} neurons have a soma · ` +
    `soma layer ${soma.meta.bin_ms} ms bins · hero layer ${fly.layers['hero']?.meta.bin_ms ?? '–'} ms bins · seed ${take.manifest.seed}`

  // ---------------------------------------------------------------- scene
  const canvas = document.getElementById('stage') as HTMLCanvasElement
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false })
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
  const scene = new THREE.Scene()
  scene.background = new THREE.Color(0x07070b)

  const points = new BrainPoints(take.somaXyz, take.superclass, take.manifest.shared.superclass_legend)
  scene.add(points.object)
  scene.add(new THREE.AmbientLight(0xffffff, 0.35))
  const key = new THREE.DirectionalLight(0xffffff, 1.2)
  key.position.set(1, 1, 1)
  scene.add(key)

  // hero meshes: the circuit groups' neurons as real morphology, if the bundle has them
  const hero = fly.layers['hero']
  const heroMeshes = new HeroMeshes(base)
  const groupOfIndex = new Map<number, string>()
  for (const [g, idx] of Object.entries(fly.entry.circuit)) for (const i of idx) groupOfIndex.set(i, g)
  const meshInfo = (take.manifest as unknown as { meshes?: { index: string } }).meshes
  if (meshInfo) {
    status.textContent = 'loading hero meshes…'
    const index: MeshIndex = await (await fetch(`${base}/${meshInfo.index}`)).json()
    await heroMeshes.load(index, i => groupOfIndex.get(i))
    scene.add(heroMeshes.group)
    status.textContent = ''
    document.getElementById('meta')!.textContent += ` · ${heroMeshes.count} hero meshes (lod ${index.lod})`
  }

  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000)
  const c = points.center, r = points.radius
  camera.position.set(c.x + r * 1.6, c.y + r * 0.3, c.z + r * 1.4)
  camera.lookAt(c)
  const controls = new OrbitControls(camera, canvas)
  controls.target.copy(c)
  controls.enableDamping = true
  controls.autoRotate = true
  controls.autoRotateSpeed = 0.4
  controls.addEventListener('start', () => { controls.autoRotate = false })

  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }
  new ResizeObserver(resize).observe(canvas)
  resize()

  // ---------------------------------------------------------------- transport
  const transport = new Transport(soma.durationS, document.getElementById('transport')!)
  let lastBin = -1
  let lastHeroBin = -1

  // ---------------------------------------------------------------- readout strip
  const heroIds = hero ? await hero.subset : null
  const circuit = fly.entry.circuit
  const readout = document.getElementById('readout')!
  const groups = Object.entries(circuit)
  readout.innerHTML = groups.map(([g, idx]) =>
    `<div class="group"><span class="name">${g}</span><span class="n">${idx.length}</span><span class="bar"><i></i></span></div>`).join('')
  const bars = Array.from(readout.querySelectorAll<HTMLElement>('.bar i'))
  const heroPos = new Map<number, number>()
  heroIds?.forEach((packIdx, k) => heroPos.set(packIdx, k))
  const groupRate = new Float32Array(groups.length)
  const groupSmooth = new Float32Array(groups.length)   // running mean over ~100 ms of bins

  transport.addSeekListener(() => { points.clearHeat(); heroMeshes.clearHeat(); lastBin = -1; lastHeroBin = -1; groupSmooth.fill(0) })

  // ---------------------------------------------------------------- loop
  function frame(now: number) {
    const dt = transport.tick(now)
    const bin = soma.binAt(transport.time)
    soma.prefetch(bin)
    if (bin !== lastBin) {
      // apply every bin we skipped over since the last frame, so fast playback still shows spikes
      const from = lastBin < 0 || bin < lastBin ? bin : lastBin + 1
      for (let b = from; b <= bin; b++) {
        const ev = soma.binSync(b)
        if (ev) points.addBin(ev.neuron, ev.count)
      }
      lastBin = bin
    }
    if (hero && heroIds) {
      const hb = hero.binAt(transport.time)
      if (hb !== lastHeroBin) {
        // walk every bin since the last frame so a slow frame does not skip spikes
        const from = lastHeroBin < 0 || hb < lastHeroBin ? hb : lastHeroBin + 1
        for (let b = from; b <= hb; b++) {
          const ev = hero.binSync(b)
          if (!ev) continue
          heroMeshes.addBin(ev.neuron, ev.count, heroIds)
          groupRate.fill(0)
          groups.forEach(([, idx], gi) => {
            let s = 0
            for (const packIdx of idx) {
              const k = heroPos.get(packIdx)
              if (k === undefined) continue
              for (let e = 0; e < ev.neuron.length; e++) if (ev.neuron[e] === k) s += ev.count[e]
            }
            // spikes per neuron per bin -> Hz
            groupRate[gi] = (s / Math.max(1, idx.length)) * (1000 / hero.meta.bin_ms)
          })
          for (let gi = 0; gi < groups.length; gi++) groupSmooth[gi] += (groupRate[gi] - groupSmooth[gi]) * 0.1
        }
        bars.forEach((el, gi) => { el.style.width = `${Math.min(100, groupSmooth[gi] / 1.5)}%`; el.title = `${groupSmooth[gi].toFixed(0)} Hz` })
        readout.querySelectorAll<HTMLElement>('.n').forEach((el, gi) => { el.textContent = `${groupSmooth[gi].toFixed(0)} Hz` })
        lastHeroBin = hb
      }
    }
    points.update(dt)
    heroMeshes.update(dt)
    controls.update()
    renderer.render(scene, camera)
    requestAnimationFrame(frame)
  }
  requestAnimationFrame(frame)
}

main().catch(err => {
  document.getElementById('status')!.textContent = String(err)
  console.error(err)
})
