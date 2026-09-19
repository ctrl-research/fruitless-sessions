/** Whole-brain soma points, colored by binned activity with a short decay. */

import * as THREE from 'three'

const SUPERCLASS_HUE: Record<string, number> = {
  ol_intrinsic: 0.62, ol_sensory: 0.58, visual_projection: 0.55, visual_centrifugal: 0.52,
  cb_intrinsic: 0.66, cb_sensory: 0.70, cb_motor: 0.08, cb_endocrine: 0.80, cb_efferent: 0.10,
  descending_neuron: 0.12, ascending_neuron: 0.18, sensory_ascending: 0.20,
  vnc_intrinsic: 0.45, vnc_sensory: 0.40, vnc_motor: 0.06, vnc_efferent: 0.09, vnc_endocrine: 0.85,
}

export class BrainPoints {
  readonly object: THREE.Points
  readonly n: number
  private base: Float32Array      // resting color per neuron (rgb)
  private color: Float32Array     // live color attribute
  private heat: Float32Array      // 0..1 activity, decays each frame
  private active = new Set<number>()   // neurons with heat > 0, so update() is O(active) not O(N)
  private hasSoma: Uint8Array
  private colorAttr: THREE.BufferAttribute
  readonly center = new THREE.Vector3()
  readonly radius: number

  constructor(xyz: Float32Array, superclass: Uint8Array, legend: string[], scale = 0.001) {
    this.n = superclass.length
    const pos = new Float32Array(this.n * 3)
    this.hasSoma = new Uint8Array(this.n)
    const bb = new THREE.Box3()
    for (let i = 0; i < this.n; i++) {
      const x = xyz[3 * i], y = xyz[3 * i + 1], z = xyz[3 * i + 2]
      if (Number.isFinite(x)) {
        this.hasSoma[i] = 1
        // MaleCNS voxels are 8 nm. z runs along the body axis; put it vertical so the
        // brain sits above the ventral nerve cord, x stays left/right, y becomes depth.
        pos[3 * i] = x * scale
        pos[3 * i + 1] = -z * scale
        pos[3 * i + 2] = y * scale
        bb.expandByPoint(new THREE.Vector3(pos[3 * i], pos[3 * i + 1], pos[3 * i + 2]))
      } else {
        pos[3 * i] = pos[3 * i + 1] = pos[3 * i + 2] = 1e9   // parked far away, effectively hidden
      }
    }
    bb.getCenter(this.center)
    this.radius = bb.getSize(new THREE.Vector3()).length() / 2

    this.base = new Float32Array(this.n * 3)
    const c = new THREE.Color()
    for (let i = 0; i < this.n; i++) {
      const name = superclass[i] === 255 ? '' : legend[superclass[i]]
      const hue = SUPERCLASS_HUE[name] ?? 0.0
      c.setHSL(hue, 0.45, 0.07)
      this.base[3 * i] = c.r; this.base[3 * i + 1] = c.g; this.base[3 * i + 2] = c.b
    }
    this.color = new Float32Array(this.base)
    this.heat = new Float32Array(this.n)

    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    this.colorAttr = new THREE.BufferAttribute(this.color, 3)
    this.colorAttr.setUsage(THREE.DynamicDrawUsage)
    geom.setAttribute('color', this.colorAttr)
    geom.boundingSphere = new THREE.Sphere(this.center.clone(), this.radius)

    const mat = new THREE.PointsMaterial({
      size: 0.45, vertexColors: true, sizeAttenuation: true, transparent: true, opacity: 0.85,
      depthWrite: false, blending: THREE.AdditiveBlending,
    })
    this.object = new THREE.Points(geom, mat)
  }

  /** Add this bin's spikes as heat; call once per new bin. */
  addBin(neuron: Uint32Array, count: Uint8Array, gain = 1.0): void {
    for (let k = 0; k < neuron.length; k++) {
      const i = neuron[k]
      if (i >= this.n) continue
      this.heat[i] = Math.min(1, this.heat[i] + gain * count[k])
      this.active.add(i)
    }
  }

  /** Decay heat and repaint. decayPerSecond ~ 3 gives a ~300 ms glow. */
  update(dtS: number, decayPerSecond = 3): void {
    if (this.active.size === 0) return
    const d = Math.exp(-decayPerSecond * dtS)
    const b = this.base, c = this.color, h = this.heat
    for (const i of this.active) {
      const v = h[i] * d
      const t = v < 0.002 ? 0 : v
      h[i] = t
      // lerp from base toward a hot amber-white
      c[3 * i] = b[3 * i] + (1.0 - b[3 * i]) * t
      c[3 * i + 1] = b[3 * i + 1] + (0.62 - b[3 * i + 1]) * t
      c[3 * i + 2] = b[3 * i + 2] + (0.18 - b[3 * i + 2]) * t
      if (t === 0) this.active.delete(i)
    }
    this.colorAttr.needsUpdate = true
  }

  clearHeat(): void {
    for (const i of this.active) { this.color[3 * i] = this.base[3 * i]; this.color[3 * i + 1] = this.base[3 * i + 1]; this.color[3 * i + 2] = this.base[3 * i + 2] }
    this.heat.fill(0)
    this.active.clear()
    this.colorAttr.needsUpdate = true
  }
}
