import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import './style.css'
import { loadTake } from './bundle'
import { BrainPoints } from './brain/points'
import { HeroMeshes, type MeshIndex } from './brain/meshes'
import { Transport } from './transport'
import { AudioClock } from './clock'
import { Score, type TuneInfo, type NoteEvent } from './score'
import { FlyBody, idlePose } from './body/fly'
import { rigFor } from './body/rig'
import { riser, saxophone } from './body/instruments'

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
    // meshes are the heaviest download; load them behind the transport so the page is
    // usable at once and the meshes fade in when they arrive
    status.textContent = 'loading hero meshes…'
    fetch(`${base}/${meshInfo.index}`).then(r => r.json()).then((index: MeshIndex) =>
      heroMeshes.load(index, i => groupOfIndex.get(i)).then(() => {
        scene.add(heroMeshes.group)
        status.textContent = ''
        document.getElementById('meta')!.textContent += ` · ${heroMeshes.count} hero meshes (lod ${index.lod})`
      })).catch(err => { status.textContent = `meshes: ${err}`; console.error(err) })
  }

  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000)
  const c = points.center, r = points.radius
  camera.position.set(c.x + r * 1.6, c.y + r * 0.3, c.z + r * 1.4)
  camera.lookAt(c)
  const controls = new OrbitControls(camera, canvas)
  controls.target.copy(c)
  controls.enableDamping = true
  controls.autoRotate = false   // a bandstand has a front; orbit by hand
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

  // ---------------------------------------------------------------- bandstand
  // the fly stands on a riser to the left of its brain, at brain scale
  const bodyScale = points.radius * 0.2
  const stand = new THREE.Group()
  stand.position.set(points.center.x - points.radius * 1.6, points.center.y - points.radius * 0.6, points.center.z + points.radius * 0.3)
  stand.add(riser(bodyScale * 3.2))
  const performer = new THREE.Group()          // fly + instrument, turned toward the audience
  performer.rotation.y = 0.75
  stand.add(performer)
  const flyBody = new FlyBody(bodyScale)
  performer.add(flyBody.group)
  if (fly.entry.role === 'sax') {
    const horn = saxophone(bodyScale)
    horn.position.set(0, 0, bodyScale * 0.55)   // in front of the head, mouthpiece at the proboscis
    performer.add(horn)
  }
  scene.add(stand)
  const stageLight = new THREE.SpotLight(0xfff1d6, 60, points.radius * 3, 0.5, 0.6, 1.2)
  stageLight.position.set(stand.position.x + bodyScale * 4, stand.position.y + bodyScale * 10, stand.position.z + bodyScale * 6)
  stageLight.target = stand
  scene.add(stageLight)
  const rig = rigFor(fly.entry.role)
  let prevPose = idlePose()
  const rigEl = document.getElementById('rig')!
  rigEl.innerHTML = `<div class="title">rig · ${rig.role}</div>` + rig.rules.map(r =>
    `<div class="rule"><span class="joint">${r.joint}</span> <span class="from">← ${r.from}</span><div class="text">${r.rule}</div></div>`).join('')

  // widen the camera framing to include the stand
  controls.target.copy(points.center).add(new THREE.Vector3(-points.radius * 0.75, -points.radius * 0.2, 0))
  camera.position.set(points.center.x - points.radius * 1.0, points.center.y + points.radius * 0.15, points.center.z + points.radius * 2.4)

  // ---------------------------------------------------------------- transport
  const duration = take.manifest.duration_s || soma.durationS
  const transport = new Transport(duration, document.getElementById('transport')!)
  const audioSrc = take.manifest.audio ? `${base}/${take.manifest.audio}` : null
  const clock = new AudioClock(transport, audioSrc)
  clock.onBlocked = why => { status.textContent = `audio blocked by the browser (${why.split(':')[0]}); running silent on the frame clock` }
  ;(window as unknown as { __fs: unknown }).__fs = { transport, clock, take }

  // score: tune, notes per role, motor readouts
  const tuneInfo = (take.manifest as unknown as { tune?: TuneInfo }).tune ?? null
  const notesByRole: Record<string, NoteEvent[]> = {}
  const motorByRole: Record<string, { names: string[]; steps: number; data: Float32Array }> = {}
  for (const f of take.manifest.flies as unknown as { role: string; notes?: string; motor?: { file: string; names: string[]; steps: number } }[]) {
    if (f.notes) notesByRole[f.role] = await (await fetch(`${base}/${f.notes}`)).json()
    if (f.motor) {
      const buf = await (await fetch(`${base}/${f.motor.file}`)).arrayBuffer()
      motorByRole[f.role] = { names: f.motor.names, steps: f.motor.steps, data: new Float32Array(buf) }
    }
  }
  const score = tuneInfo ? new Score(tuneInfo, notesByRole) : null
  const strip = document.getElementById('score') as HTMLCanvasElement
  const nowEl = document.getElementById('now')!
  const motorEl = document.getElementById('motor')!
  const motor = motorByRole[fly.entry.role]
  if (motor) motorEl.innerHTML = motor.names.map(n => `<div class="m"><span class="name">${n}</span><span class="v">–</span></div>`).join('')
  else motorEl.style.display = 'none'
  const motorVals = Array.from(motorEl.querySelectorAll<HTMLElement>('.v'))
  if (!score) strip.style.display = 'none'
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
    if (clock.audio && clock.active && transport.playing) transport.sync(clock.time())
    const tNow = transport.time
    const bin = soma.binAt(tNow)
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
      const hb = hero.binAt(tNow)
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
    if (score) {
      score.drawStrip(strip, tNow)
      const sec = score.sectionAt(tNow)
      const sounding = score.soundingAt(fly.entry.role, tNow)
      nowEl.textContent = `bar ${score.barAt(tNow) + 1} · ${score.chordAt(tNow) || '–'} · ${sec ? sec.kind + (sec.who.length ? ' ' + sec.who.join('/') : '') : ''}` +
        (sounding.length ? ` · ♪ ${sounding.map(n => noteName(n.midi)).join(' ')}` : '')
    }
    if (motor && tuneInfo) {
      const step = Math.min(motor.steps - 1, Math.max(0, Math.floor(tNow / tuneInfo.step_s)))
      motor.names.forEach((_, i) => { motorVals[i].textContent = motor.data[step * motor.names.length + i].toFixed(1) })
    }
    // body from the same signals as the music
    {
      const step = motor && tuneInfo ? Math.min(motor.steps - 1, Math.max(0, Math.floor(tNow / tuneInfo.step_s))) : 0
      const readout: Record<string, number> = {}
      if (motor) motor.names.forEach((n, i) => { readout[n] = motor.data[step * motor.names.length + i] })
      const rates: Record<string, number> = {}
      groups.forEach(([g], gi) => { rates[g] = groupSmooth[gi] })
      const sounding = score ? score.soundingAt(fly.entry.role, tNow) : []
      const noteAge = sounding.length ? tNow - Math.max(...sounding.map(n => n.t)) : 0
      prevPose = rig.pose({ readout, rates, noteOn: sounding.length > 0, noteAge, t: tNow }, prevPose, dt)
      flyBody.apply(prevPose, transport.playing ? dt : 0)
      ;(window as unknown as { __fs: { pose?: unknown; readout?: unknown } }).__fs.pose = prevPose
      ;(window as unknown as { __fs: { pose?: unknown; readout?: unknown } }).__fs.readout = readout
    }
    points.update(dt)
    heroMeshes.update(dt)
    controls.update()
    renderer.render(scene, camera)
    requestAnimationFrame(frame)
  }
  requestAnimationFrame(frame)
}

const NAMES = ['C', 'C♯', 'D', 'E♭', 'E', 'F', 'F♯', 'G', 'A♭', 'A', 'B♭', 'B']
function noteName(m: number): string { return `${NAMES[m % 12]}${Math.floor(m / 12) - 1}` }

main().catch(err => {
  document.getElementById('status')!.textContent = String(err)
  console.error(err)
})
