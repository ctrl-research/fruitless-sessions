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
  private heat: Float32Array      // 0..1 activity per neuron, decays each frame; the shader lerps colour from it
  private active = new Set<number>()   // neurons with heat > 0, so update() is O(active) not O(N)
  private hasSoma: Uint8Array
  private heatAttr: THREE.BufferAttribute
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

    const base = new Float32Array(this.n * 3)   // resting color per neuron, static on the GPU
    const c = new THREE.Color()
    for (let i = 0; i < this.n; i++) {
      const name = superclass[i] === 255 ? '' : legend[superclass[i]]
      const hue = SUPERCLASS_HUE[name] ?? 0.0
      c.setHSL(hue, 0.4, 0.075)   // resting tint; with normal blending this is as bright as rest ever gets
      base[3 * i] = c.r; base[3 * i + 1] = c.g; base[3 * i + 2] = c.b
    }
    this.heat = new Float32Array(this.n)

    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geom.setAttribute('color', new THREE.BufferAttribute(base, 3))
    // only the one-float heat attribute changes per frame: a quarter of the upload of a live rgb buffer
    this.heatAttr = new THREE.BufferAttribute(this.heat, 1)
    this.heatAttr.setUsage(THREE.DynamicDrawUsage)
    geom.setAttribute('heat', this.heatAttr)
    geom.boundingSphere = new THREE.Sphere(this.center.clone(), this.radius)

    const mat = new THREE.PointsMaterial({
      // normal blending: overlapping resting dots no longer add up to white in the dense optic
      // lobes, so the haze stays a haze and a spiking dot is the brightest thing in the brain
      size: 0.4, vertexColors: true, sizeAttenuation: true, transparent: true, opacity: 0.4,
      depthWrite: false, blending: THREE.NormalBlending,
    })
    // lerp from the resting tint toward a hot amber-white by heat, on the GPU
    mat.customProgramCacheKey = () => 'brain-points'
    mat.onBeforeCompile = shader => {
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', '#include <common>\nattribute float heat;\nvarying float vHeat;')
        .replace('#include <color_vertex>', '#include <color_vertex>\nvHeat = heat;')
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', '#include <common>\nvarying float vHeat;')
        .replace('#include <color_fragment>', '#include <color_fragment>\ndiffuseColor.rgb = mix(diffuseColor.rgb, vec3(1.0, 0.7, 0.25), vHeat);')
    }
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
    const h = this.heat
    for (const i of this.active) {
      const v = h[i] * d
      const t = v < 0.002 ? 0 : v
      h[i] = t
      if (t === 0) this.active.delete(i)
    }
    this.heatAttr.needsUpdate = true
  }

  clearHeat(): void {
    this.heat.fill(0)
    this.active.clear()
    this.heatAttr.needsUpdate = true
  }
}
