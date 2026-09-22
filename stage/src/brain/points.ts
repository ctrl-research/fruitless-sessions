/** Whole-brain soma points, colored by binned activity with a short decay.
 *
 *  Drawn as one instanced quad per soma rather than gl.POINTS: Chrome on Windows runs WebGL on
 *  Direct3D, which has no point sprites, so ANGLE expands every point in a geometry shader and
 *  a 140k-point cloud crawls. Quads take the ordinary vertex path everywhere. The quad is sized
 *  in pixels exactly as PointsMaterial's sizeAttenuation would size a point. */

import * as THREE from 'three'

const SUPERCLASS_HUE: Record<string, number> = {
  ol_intrinsic: 0.62, ol_sensory: 0.58, visual_projection: 0.55, visual_centrifugal: 0.52,
  cb_intrinsic: 0.66, cb_sensory: 0.70, cb_motor: 0.08, cb_endocrine: 0.80, cb_efferent: 0.10,
  descending_neuron: 0.12, ascending_neuron: 0.18, sensory_ascending: 0.20,
  vnc_intrinsic: 0.45, vnc_sensory: 0.40, vnc_motor: 0.06, vnc_efferent: 0.09, vnc_endocrine: 0.85,
}

const VERT = /* glsl */`
  uniform float size;      // world units, as PointsMaterial.size
  uniform float scale;     // half the logical viewport height, as PointsMaterial's scale uniform
  uniform vec2 viewport;   // drawing buffer size in pixels
  attribute vec2 corner;
  attribute vec3 offset;
  attribute vec3 tint;
  attribute float heat;
  varying vec3 vColor;
  void main() {
    vColor = mix(tint, vec3(1.0, 0.7, 0.25), heat);   // resting tint toward a hot amber-white
    vec4 mvPosition = modelViewMatrix * vec4(offset, 1.0);
    vec4 clip = projectionMatrix * mvPosition;
    float px = size * (scale / -mvPosition.z);        // the point's size in pixels
    clip.xy += corner * px / viewport * clip.w;        // a px-wide square around it, screen aligned
    gl_Position = clip;
  }
`
const FRAG = /* glsl */`
  uniform float opacity;
  varying vec3 vColor;
  void main() {
    gl_FragColor = vec4(vColor, opacity);
    #include <tonemapping_fragment>
    #include <colorspace_fragment>
  }
`

export class BrainPoints {
  readonly object: THREE.Mesh
  readonly n: number
  private heat: Float32Array           // 0..1 activity per instance, decays each frame
  private instOf: Int32Array           // pack index -> instance, or -1 for a neuron with no soma
  private active = new Set<number>()   // instances with heat > 0, so update() is O(active) not O(N)
  private heatAttr: THREE.InstancedBufferAttribute
  readonly center = new THREE.Vector3()
  readonly radius: number

  constructor(xyz: Float32Array, superclass: Uint8Array, legend: string[], scale = 0.001) {
    this.n = superclass.length
    this.instOf = new Int32Array(this.n).fill(-1)
    let m = 0
    for (let i = 0; i < this.n; i++) if (Number.isFinite(xyz[3 * i])) this.instOf[i] = m++
    const pos = new Float32Array(m * 3)
    const base = new Float32Array(m * 3)   // resting color per soma, static on the GPU
    const bb = new THREE.Box3()
    const c = new THREE.Color()
    const v = new THREE.Vector3()
    for (let i = 0; i < this.n; i++) {
      const k = this.instOf[i]
      if (k < 0) continue
      // MaleCNS voxels are 8 nm. z runs along the body axis; put it vertical so the
      // brain sits above the ventral nerve cord, x stays left/right, y becomes depth.
      pos[3 * k] = xyz[3 * i] * scale
      pos[3 * k + 1] = -xyz[3 * i + 2] * scale
      pos[3 * k + 2] = xyz[3 * i + 1] * scale
      bb.expandByPoint(v.set(pos[3 * k], pos[3 * k + 1], pos[3 * k + 2]))
      const name = superclass[i] === 255 ? '' : legend[superclass[i]]
      c.setHSL(SUPERCLASS_HUE[name] ?? 0.0, 0.4, 0.075)   // resting tint; with normal blending this is as bright as rest ever gets
      base[3 * k] = c.r; base[3 * k + 1] = c.g; base[3 * k + 2] = c.b
    }
    bb.getCenter(this.center)
    this.radius = bb.getSize(new THREE.Vector3()).length() / 2
    this.heat = new Float32Array(m)

    const geom = new THREE.InstancedBufferGeometry()
    geom.setAttribute('corner', new THREE.BufferAttribute(new Float32Array([-1, -1, 1, -1, 1, 1, -1, 1]), 2))
    geom.setIndex([0, 1, 2, 0, 2, 3])
    geom.setAttribute('offset', new THREE.InstancedBufferAttribute(pos, 3))
    geom.setAttribute('tint', new THREE.InstancedBufferAttribute(base, 3))
    // only the one-float heat attribute changes per frame
    this.heatAttr = new THREE.InstancedBufferAttribute(this.heat, 1)
    this.heatAttr.setUsage(THREE.DynamicDrawUsage)
    geom.setAttribute('heat', this.heatAttr)
    geom.instanceCount = m
    geom.boundingSphere = new THREE.Sphere(this.center.clone(), this.radius)

    const uniforms = { size: { value: 0.4 }, scale: { value: 1 }, viewport: { value: new THREE.Vector2(1, 1) }, opacity: { value: 0.4 } }
    const mat = new THREE.ShaderMaterial({
      uniforms, vertexShader: VERT, fragmentShader: FRAG,
      // normal blending: overlapping resting dots no longer add up to white in the dense optic
      // lobes, so the haze stays a haze and a spiking dot is the brightest thing in the brain
      transparent: true, depthWrite: false, blending: THREE.NormalBlending,
    })
    this.object = new THREE.Mesh(geom, mat)
    const size = new THREE.Vector2()
    this.object.onBeforeRender = renderer => {
      renderer.getSize(size)
      uniforms.scale.value = size.y * 0.5
      renderer.getDrawingBufferSize(uniforms.viewport.value)
    }
  }

  /** Add this bin's spikes as heat; call once per new bin. */
  addBin(neuron: Uint32Array, count: Uint8Array, gain = 1.0): void {
    for (let e = 0; e < neuron.length; e++) {
      const i = neuron[e]
      if (i >= this.n) continue
      const k = this.instOf[i]
      if (k < 0) continue
      this.heat[k] = Math.min(1, this.heat[k] + gain * count[e])
      this.active.add(k)
    }
  }

  /** Decay heat and repaint. decayPerSecond ~ 3 gives a ~300 ms glow. */
  update(dtS: number, decayPerSecond = 3): void {
    if (this.active.size === 0) return
    const d = Math.exp(-decayPerSecond * dtS)
    const h = this.heat
    for (const k of this.active) {
      const v = h[k] * d
      const t = v < 0.002 ? 0 : v
      h[k] = t
      if (t === 0) this.active.delete(k)
    }
    this.heatAttr.needsUpdate = true
  }

  clearHeat(): void {
    this.heat.fill(0)
    this.active.clear()
    this.heatAttr.needsUpdate = true
  }
}
