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
import { drumKit, piano, saxophone, upright } from './body/instruments'

const params = new URLSearchParams(location.search)
const takeName = params.get('take') ?? 'smoke'
const base = `${import.meta.env.BASE_URL}takes/${takeName}`

interface TakeIndexEntry { name: string; path: string; duration_s: number; roles: string[]; iterations: number; audio: boolean }

async function setupControls() {
  const sel = document.getElementById('take-select') as HTMLSelectElement
  try {
    const index: TakeIndexEntry[] = await (await fetch(`${import.meta.env.BASE_URL}takes/index.json`)).json()
    sel.innerHTML = index.map(e =>
      `<option value="${e.path}" ${e.path === takeName ? 'selected' : ''}>${e.name} · ${e.roles.join(', ')} (${e.iterations} take${e.iterations === 1 ? '' : 's'})</option>`).join('')
    sel.onchange = () => { location.search = `?take=${encodeURIComponent(sel.value)}` }
  } catch { sel.innerHTML = `<option>${takeName}</option>` }
  const stats = document.getElementById('toggle-stats') as HTMLInputElement
  const applyStats = () => document.body.classList.toggle('no-stats', !stats.checked)
  stats.onchange = applyStats
  try { stats.checked = localStorage.getItem('fs.stats') === '1' } catch { /* private mode */ }
  applyStats()
  stats.addEventListener('change', () => { try { localStorage.setItem('fs.stats', stats.checked ? '1' : '0') } catch { /* ignore */ } })
}

async function main() {
  const status = document.getElementById('status')!
  await setupControls()
  status.textContent = `loading ${takeName}…`
  const take = await loadTake(base)
  const flies = take.flies
  const fly = flies[0]   // the readout / rig panels show the current soloist; starts on the first fly
  const soma0 = fly.layers['soma']
  status.textContent = ''

  document.getElementById('title')!.textContent = `${take.manifest.name} · ${flies.map(f => f.entry.role).join(' · ')}`
  document.getElementById('meta')!.textContent =
    `${take.manifest.shared.with_soma.toLocaleString()} of ${take.manifest.shared.n_neurons.toLocaleString()} neurons have a soma · ` +
    `soma layer ${soma0.meta.bin_ms} ms bins · hero layer ${fly.layers['hero']?.meta.bin_ms ?? '–'} ms bins · seed ${take.manifest.seed}`

  // ---------------------------------------------------------------- scene
  const canvas = document.getElementById('stage') as HTMLCanvasElement
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false })
  renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
  const scene = new THREE.Scene()
  scene.background = new THREE.Color(0x07070b)
  scene.add(new THREE.AmbientLight(0xffffff, 0.35))
  const key = new THREE.DirectionalLight(0xffffff, 1.2)
  key.position.set(1, 1, 1)
  scene.add(key)

  // one performer per fly: brain (points + meshes) above, body on a riser below, side by side
  interface Performer {
    entry: typeof fly.entry
    layers: typeof fly.layers
    points: BrainPoints
    meshes: HeroMeshes
    body: FlyBody
    rig: ReturnType<typeof rigFor>
    pose: ReturnType<typeof idlePose>
    group: THREE.Group
    heroIds: Int32Array | null
    heroPos: Map<number, number>
    groups: [string, number[]][]
    rate: Float32Array
    smooth: Float32Array
    lastBin: number
    lastHeroBin: number
    motor: { names: string[]; steps: number; data: Float32Array } | null
    notes: NoteEvent[]
    kitHits: Record<string, THREE.Object3D> | null
  }
  const performers: Performer[] = []
  const proto = new BrainPoints(take.somaXyz, take.superclass, take.manifest.shared.superclass_legend)
  const R = proto.radius
  const bodyScale = R * 0.26
  const meshInfo = (take.manifest as unknown as { meshes?: { index: string } }).meshes

  // one shared circular platform; performers in an organic triangular formation on it,
  // rhythm section toward the back, soloists toward the front. Brains float above each fly.
  const n = flies.length
  const formationR = n === 1 ? 0 : R * (0.4 + 0.22 * n)
  // seats on the back half-circle, rhythm section first (drums back centre, then piano and
  // bass alternating left and right), with the sides stepped toward the audience. The sax then
  // takes the outer side of the bassist at the same depth.
  const seats = new Map<string, THREE.Vector3>()
  const backRole = (r: string) => r === 'drums' ? 0 : r === 'piano' ? 1 : r === 'bass' ? 2 : 3
  const ordered = [...flies].sort((a, b) => backRole(a.entry.role) - backRole(b.entry.role))
  ordered.forEach((f, i) => {
    const k = i === 0 ? 0 : (i % 2 === 1 ? -1 : 1) * Math.ceil(i / 2)
    const ang = Math.PI / 2 + k * (Math.PI / Math.max(2, n)) * 1.15 + (i % 2 ? 0.08 : -0.06)
    const rr = formationR * (i === 0 ? 1.0 : 0.9 + 0.05 * (i % 2))
    const forward = i === 0 ? 0 : formationR * 0.3
    seats.set(f.entry.role, new THREE.Vector3(Math.cos(ang) * rr, 0, -Math.sin(ang) * rr + formationR * 0.3 + forward))
  })
  const bassSeat = seats.get('bass')
  if (seats.has('sax') && bassSeat) {
    const outward = Math.sign(bassSeat.x) || 1
    seats.set('sax', new THREE.Vector3(bassSeat.x + outward * formationR * 0.15, 0, bassSeat.z + formationR * 0.5))   // forward of the bassist, just to the outside
  }
  // the disc reaches just past the furthest seat, so a performer stepped forward still stands on it
  const reach = Math.max(formationR, ...[...seats.values()].map(v => Math.hypot(v.x, v.z)))
  const platformR = reach + bodyScale * 1.6
  const platform = new THREE.Mesh(
    new THREE.CylinderGeometry(platformR, platformR * 1.04, bodyScale * 0.35, 64),
    new THREE.MeshStandardMaterial({ color: 0x1a1a24, roughness: 0.85, metalness: 0.1 }),
  )
  platform.position.y = -R * 0.35 - bodyScale * 0.175
  scene.add(platform)
  const rim = new THREE.Mesh(new THREE.TorusGeometry(platformR * 1.02, bodyScale * 0.06, 8, 96),
    new THREE.MeshStandardMaterial({ color: 0xf2b35c, emissive: 0x5a3c10, roughness: 0.4, metalness: 0.6 }))
  rim.rotation.x = Math.PI / 2
  rim.position.y = -R * 0.35
  scene.add(rim)

  // the house spotlight: from a ceiling above the platform, straight down, with a visible beam
  const ceilingY = R * 2.6
  const spot = new THREE.SpotLight(0xfff1d6, 900, ceilingY * 2.2, 0.72, 0.55, 1.4)
  spot.position.set(0, ceilingY, 0)
  spot.target.position.set(0, -R * 0.35, 0)
  scene.add(spot, spot.target)
  const beamH = ceilingY + R * 0.35
  const beam = new THREE.Mesh(
    new THREE.ConeGeometry(platformR * 1.35, beamH, 48, 1, true),
    new THREE.MeshBasicMaterial({ color: 0xfff1d6, transparent: true, opacity: 0.045, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }),
  )
  beam.position.set(0, -R * 0.35 + beamH / 2, 0)
  scene.add(beam)
  const lamp = new THREE.Mesh(new THREE.CylinderGeometry(bodyScale * 0.6, bodyScale * 0.9, bodyScale * 0.8, 16),
    new THREE.MeshStandardMaterial({ color: 0x222228, roughness: 0.5, metalness: 0.6, emissive: 0xfff1d6, emissiveIntensity: 0.6 }))
  lamp.position.set(0, ceilingY + bodyScale * 0.4, 0)
  scene.add(lamp)

  const brainGroups: THREE.Object3D[] = []
  for (let fi = 0; fi < flies.length; fi++) {
    const f = flies[fi]
    const seat = seats.get(f.entry.role) ?? new THREE.Vector3()
    const group = new THREE.Group()
    group.position.copy(seat)
    scene.add(group)
    const points = fi === 0 ? proto : new BrainPoints(take.somaXyz, take.superclass, take.manifest.shared.superclass_legend)
    // brains are wider than the seats are apart, so they fan out from the platform centre
    // just enough not to touch; performers standing forward hang theirs very slightly lower
    const fanX = n > 1 ? seat.x * (Math.max(1, (R * 1.45) / Math.max(1e-6, formationR)) - 1) : 0
    const zs = [...seats.values()].map(v => v.z)
    const zMin = Math.min(...zs), zMax = Math.max(...zs)
    const forwardness = zMax > zMin ? (seat.z - zMin) / (zMax - zMin) : 0
    const yaw = Math.atan2(-seat.x, Math.abs(seat.z) + formationR) * 0.6 + 0.35
    // the brain floats above its fly in the fly's own orientation: laid flat, dorsal side up,
    // brain at the head end pointing where the fly faces, nerve cord trailing behind
    const holder = new THREE.Group()
    holder.position.set(fanX, R * (0.95 - 0.1 * forwardness), 0)
    holder.rotation.y = yaw
    holder.scale.setScalar(0.72)        // face-on brains are wide; a little smaller keeps neighbours apart
    const tilt = new THREE.Group()
    tilt.rotation.x = Math.PI / 2       // the point cloud is built body-axis-vertical; this lays it flat
    holder.add(tilt)
    const meshes = new HeroMeshes(base)
    points.object.position.set(-points.center.x, -points.center.y, -points.center.z)
    meshes.group.position.copy(points.object.position)
    tilt.add(points.object, meshes.group)
    group.add(holder)
    brainGroups.push(points.object, meshes.group)
    const stand = new THREE.Group()
    stand.position.set(0, -R * 0.35, 0)
    const performer = new THREE.Group()
    // face the audience (+Z), turned a little toward the centre of the platform; the piano
    // sits side-on like a real stage piano so the pianist is seen in profile at the keys
    performer.rotation.y = yaw
    stand.add(performer)
    const body = new FlyBody(bodyScale)
    performer.add(body.group)
    let kitHits: Record<string, THREE.Object3D> | null = null
    if (f.entry.role === 'sax') {
      const horn = saxophone(bodyScale); horn.position.set(0, 0, bodyScale * 0.55); performer.add(horn)
    } else if (f.entry.role === 'bass') {
      const b = upright(bodyScale); b.position.set(bodyScale * 0.6, 0, bodyScale * 0.4); performer.add(b)
    } else if (f.entry.role === 'drums') {
      const kit = drumKit(bodyScale); kit.group.position.set(0, 0, bodyScale * 0.9); performer.add(kit.group); kitHits = kit.hits
    } else if (f.entry.role === 'piano') {
      const pf = piano(bodyScale); pf.position.set(0, 0, bodyScale * 0.35); performer.add(pf)
    }
    group.add(stand)
    const heroIds = f.layers['hero'] ? await f.layers['hero'].subset : null
    const heroPos = new Map<number, number>()
    heroIds?.forEach((packIdx, k) => heroPos.set(packIdx, k))
    const groups = Object.entries(f.entry.circuit)
    performers.push({
      entry: f.entry, layers: f.layers, points, meshes, body, rig: rigFor(f.entry.role), pose: idlePose(), group,
      heroIds, heroPos, groups, rate: new Float32Array(groups.length), smooth: new Float32Array(groups.length),
      lastBin: -1, lastHeroBin: -1, motor: null, notes: [], kitHits,
    })
  }
  // brain activity toggle
  const brainToggle = document.getElementById('toggle-brain') as HTMLInputElement
  const applyBrain = () => brainGroups.forEach(o => { o.visible = brainToggle.checked })
  brainToggle.onchange = applyBrain
  applyBrain()

  // hero meshes for every performer, behind the transport
  if (meshInfo) {
    status.textContent = 'loading hero meshes…'
    fetch(`${base}/${meshInfo.index}`).then(r => r.json()).then(async (index: MeshIndex) => {
      for (const pf of performers) {
        const mg = (pf.entry as unknown as { mesh_groups?: string[] }).mesh_groups
        const mine = new Set(Object.entries(pf.entry.circuit).filter(([g]) => !mg || mg.includes(g)).flatMap(([, idx]) => idx))
        const sub: MeshIndex = { ...index, neurons: Object.fromEntries(Object.entries(index.neurons).filter(([k]) => mine.has(Number(k)))) }
        const groupOf = new Map<number, string>()
        for (const [g, idx] of Object.entries(pf.entry.circuit)) for (const i of idx) groupOf.set(i, g)
        await pf.meshes.load(sub, i => groupOf.get(i))
      }
      status.textContent = ''
      document.getElementById('meta')!.textContent += ` · ${performers.reduce((n, pf) => n + pf.meshes.count, 0)} hero meshes (lod ${index.lod})`
    }).catch(err => { status.textContent = `meshes: ${err}`; console.error(err) })
  }

  const camera = new THREE.PerspectiveCamera(40, 1, 0.1, 5000)
  const controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.autoRotate = false
  const lookAt = new THREE.Vector3(0, R * 0.45, 0)
  controls.target.copy(lookAt)
  let userMoved = false
  controls.addEventListener('start', () => { userMoved = true })
  let camDist = R * 6
  function resize() {
    const w = canvas.clientWidth, h = canvas.clientHeight
    if (w === 0 || h === 0) return
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
    // back off until the bandstand's half-width fits the horizontal half-angle of the lens,
    // with margin; re-framed on every resize until the user takes the camera
    // fit both the band's width and the platform-to-brain height, whichever needs more distance
    const halfWidth = (Math.max(reach, R * 1.45) + R * 1.0) * 1.1
    const halfHeight = R * 1.0 * 1.1           // platform at -0.35R, flat brains top out near +1.3R
    const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))
    camDist = Math.max(halfWidth / (tanV * camera.aspect), halfHeight / tanV) * 1.15 + formationR * 0.6   // the front pair stands forward of the centre
    if (!userMoved) {
      camera.position.set(controls.target.x, R * 0.8, camDist)
      camera.lookAt(controls.target)
    }
  }
  new ResizeObserver(resize).observe(canvas)
  resize()

  // panels follow the soloist; start on the first performer
  let focus = 0
  const readout = document.getElementById('readout')!
  const motorEl = document.getElementById('motor')!
  const rigEl = document.getElementById('rig')!
  let bars: HTMLElement[] = []
  let motorVals: HTMLElement[] = []
  function showPanels(pf: Performer) {
    readout.innerHTML = `<div class="title">${pf.entry.role} · circuit</div>` + pf.groups.map(([g, idx]) =>
      `<div class="group"><span class="name">${g}</span><span class="n">${idx.length}</span><span class="bar"><i></i></span></div>`).join('')
    bars = Array.from(readout.querySelectorAll<HTMLElement>('.bar i'))
    if (pf.motor) {
      motorEl.style.display = ''
      motorEl.innerHTML = `<div class="title">${pf.entry.role} · motor readout</div>` + pf.motor.names.map(n => `<div class="m"><span class="name">${n}</span><span class="v">–</span></div>`).join('')
      motorVals = Array.from(motorEl.querySelectorAll<HTMLElement>('.v'))
    } else motorEl.style.display = 'none'
    rigEl.innerHTML = `<div class="title">rig · ${pf.rig.role}</div>` + pf.rig.rules.map(r =>
      `<div class="rule"><span class="joint">${r.joint}</span> <span class="from">← ${r.from}</span><div class="text">${r.rule}</div></div>`).join('')
  }

  // ---------------------------------------------------------------- transport
  const duration = take.manifest.duration_s || soma0.durationS
  const transport = new Transport(duration, document.getElementById('transport')!)
  const audioSrc = take.manifest.audio ? `${base}/${take.manifest.audio}` : null
  const clock = new AudioClock(transport, audioSrc)
  clock.onBlocked = why => { status.textContent = `audio blocked by the browser (${why.split(':')[0]}); running silent on the frame clock` }
  ;(window as unknown as { __fs: unknown }).__fs = { transport, clock, take, performers, camera, controls }

  // score: tune, notes per role, motor readouts
  const tuneInfo = (take.manifest as unknown as { tune?: TuneInfo }).tune ?? null
  const notesByRole: Record<string, NoteEvent[]> = {}
  for (const pf of performers) {
    const f = pf.entry as unknown as { role: string; notes?: string; motor?: { file: string; names: string[]; steps: number } }
    if (f.notes) { pf.notes = await (await fetch(`${base}/${f.notes}`)).json(); notesByRole[f.role] = pf.notes }
    if (f.motor) {
      const buf = await (await fetch(`${base}/${f.motor.file}`)).arrayBuffer()
      pf.motor = { names: f.motor.names, steps: f.motor.steps, data: new Float32Array(buf) }
    }
  }
  const score = tuneInfo ? new Score(tuneInfo, notesByRole) : null
  const strip = document.getElementById('score') as HTMLCanvasElement
  const nowEl = document.getElementById('now')!
  if (!score) strip.style.display = 'none'
  else strip.style.height = `${16 + 22 * Math.max(1, Object.keys(notesByRole).length)}px`
  showPanels(performers[focus])

  transport.addSeekListener(() => {
    for (const pf of performers) { pf.points.clearHeat(); pf.meshes.clearHeat(); pf.lastBin = -1; pf.lastHeroBin = -1; pf.smooth.fill(0) }
  })

  // camera drifts toward the soloist's performer
  const camTarget = new THREE.Vector3().copy(lookAt)
  function soloistIndex(t: number): number {
    if (!score) return 0
    const sec = score.sectionAt(t)
    const who = sec?.kind === 'head' || sec?.kind === 'free' ? 'sax' : sec?.who?.[0]
    const i = performers.findIndex(pf => pf.entry.role === who)
    return i < 0 ? 0 : i
  }

  // ---------------------------------------------------------------- loop
  function frame(now: number) {
    const dt = transport.tick(now)
    if (clock.audio && clock.active && transport.playing) transport.sync(clock.time())
    const tNow = transport.time
    const si = soloistIndex(tNow)
    if (si !== focus) { focus = si; showPanels(performers[focus]) }
    const step = tuneInfo ? Math.max(0, Math.floor(tNow / tuneInfo.step_s)) : 0

    for (let pi = 0; pi < performers.length; pi++) {
      const pf = performers[pi]
      const soma = pf.layers['soma']
      const hero = pf.layers['hero']
      const bin = soma.binAt(tNow)
      soma.prefetch(bin)
      if (bin !== pf.lastBin) {
        const from = pf.lastBin < 0 || bin < pf.lastBin ? bin : pf.lastBin + 1
        for (let b = from; b <= bin; b++) { const ev = soma.binSync(b); if (ev) pf.points.addBin(ev.neuron, ev.count) }
        pf.lastBin = bin
      }
      if (hero && pf.heroIds) {
        const hb = hero.binAt(tNow)
        if (hb !== pf.lastHeroBin) {
          const from = pf.lastHeroBin < 0 || hb < pf.lastHeroBin ? hb : pf.lastHeroBin + 1
          for (let b = from; b <= hb; b++) {
            const ev = hero.binSync(b)
            if (!ev) continue
            pf.meshes.addBin(ev.neuron, ev.count, pf.heroIds)
            pf.rate.fill(0)
            pf.groups.forEach(([, idx], gi) => {
              let s = 0
              for (const packIdx of idx) {
                const k = pf.heroPos.get(packIdx)
                if (k === undefined) continue
                for (let e = 0; e < ev.neuron.length; e++) if (ev.neuron[e] === k) s += ev.count[e]
              }
              pf.rate[gi] = (s / Math.max(1, idx.length)) * (1000 / hero.meta.bin_ms)
            })
            for (let gi = 0; gi < pf.groups.length; gi++) pf.smooth[gi] += (pf.rate[gi] - pf.smooth[gi]) * 0.1
          }
          pf.lastHeroBin = hb
          if (pi === focus) {
            bars.forEach((el, gi) => { el.style.width = `${Math.min(100, pf.smooth[gi] / 1.5)}%` })
            readout.querySelectorAll<HTMLElement>('.n').forEach((el, gi) => { el.textContent = `${pf.smooth[gi].toFixed(0)} Hz` })
          }
        }
      }
      // body from the same signals as the music
      const readoutNow: Record<string, number> = {}
      if (pf.motor) {
        const st = Math.min(pf.motor.steps - 1, step)
        pf.motor.names.forEach((n, i) => { readoutNow[n] = pf.motor!.data[st * pf.motor!.names.length + i] })
        if (pi === focus) pf.motor.names.forEach((_, i) => { motorVals[i].textContent = readoutNow[pf.motor!.names[i]].toFixed(1) })
      }
      const rates: Record<string, number> = {}
      pf.groups.forEach(([g], gi) => { rates[g] = pf.smooth[gi] })
      const sounding = pf.notes.filter(n => n.t <= tNow && tNow < n.t + n.dur)
      const noteAge = sounding.length ? tNow - Math.max(...sounding.map(n => n.t)) : 0
      pf.pose = pf.rig.pose({ readout: readoutNow, rates, noteOn: sounding.length > 0, noteAge, t: tNow }, pf.pose, dt)
      pf.body.apply(pf.pose, transport.playing ? dt : 0)
      if (pf.kitHits) {
        // nudge the drum that was just hit
        for (const n of sounding) {
          const name = n.midi === 36 ? 'kick' : n.midi === 38 ? 'snare' : n.midi === 42 ? 'hat' : n.midi === 51 ? 'ride' : n.midi === 45 ? 'tom_lo' : n.midi === 47 ? 'tom_hi' : 'crash'
          const o = pf.kitHits[name]
          if (o) o.position.y += 0.02 * bodyScale * Math.exp(-(tNow - n.t) * 15) * Math.sin(tNow * 90)
        }
      }
      pf.points.update(dt)
      pf.meshes.update(dt)
    }

    if (score) {
      score.drawStrip(strip, tNow)
      const sec = score.sectionAt(tNow)
      const sounding = performers.flatMap(pf => pf.notes.filter(n => n.t <= tNow && tNow < n.t + n.dur).map(n => `${pf.entry.role[0]}:${noteName(n.midi)}`))
      const freeKeys = (take.manifest as unknown as { free_keys?: (string | null)[] }).free_keys
      const chordLabel = score.chordAt(tNow) || (freeKeys ? (freeKeys[score.barAt(tNow)] ?? 'finding the key…') + ' (from the ring)' : '–')
      nowEl.textContent = `bar ${score.barAt(tNow) + 1}${tuneInfo?.meter && tuneInfo.meter !== '4/4' ? ' (' + tuneInfo.meter + ')' : ''} · ${chordLabel} · ${sec ? sec.kind + (sec.who.length && sec.kind !== 'free' ? ' ' + sec.who.join('/') : '') : ''}` +
        (sounding.length ? ` · ♪ ${sounding.slice(0, 6).join(' ')}` : '')
    }
    // camera pans (not pivots) toward the soloist until the user takes over
    const pfx = performers[focus].group.position.x
    camTarget.set(pfx * 0.2, R * 0.45, 0)
    if (!userMoved) {
      const kcam = 1 - Math.exp(-dt * 1.5)
      const dx = (camTarget.x - controls.target.x) * kcam
      controls.target.x += dx
      camera.position.x += dx
    }
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
