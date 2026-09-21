/** Hero neuron meshes (FSM2 files) colored by hero-layer activity.
 *
 *  All of a performer's neurons are merged into one geometry and drawn in a single call. Each
 *  vertex carries the slot of its neuron; a small RGBA float texture holds every slot's resting
 *  colour and current heat, and the shader lerps toward amber from that. Per frame the CPU
 *  touches a few hundred floats and uploads a few kilobytes, whichever machine it runs on. */

import * as THREE from 'three'

export interface MeshIndex {
  lod: number
  voxel_nm: number
  neurons: Record<string, { bodyId: number; vertices: number; triangles: number; file: string }>
}

const MAGIC = 0x324d5346 // "FSM2"
const TEX_W = 256

/** FSM2: 16-bit positions quantized into the neuron's bounding box, uint16 or uint32 indices. */
export function decodeFsm(buf: ArrayBuffer): { positions: Float32Array; indices: Uint32Array | Uint16Array } {
  const dv = new DataView(buf)
  if (dv.getUint32(0, true) !== MAGIC) throw new Error('not an FSM2 mesh')
  const nv = dv.getUint32(4, true), nf = dv.getUint32(8, true), flags = dv.getUint32(12, true)
  const lo = [dv.getFloat32(16, true), dv.getFloat32(20, true), dv.getFloat32(24, true)]
  const size = [dv.getFloat32(28, true), dv.getFloat32(32, true), dv.getFloat32(36, true)]
  let o = 40
  const q = new Uint16Array(buf.slice(o, o + 6 * nv))
  o += 6 * nv
  const positions = new Float32Array(3 * nv)
  for (let i = 0; i < 3 * nv; i++) positions[i] = (q[i] / 65535) * size[i % 3] + lo[i % 3]
  const indices = flags & 1 ? new Uint32Array(buf.slice(o, o + 12 * nf)) : new Uint16Array(buf.slice(o, o + 6 * nf))
  return { positions, indices }
}

/** Same voxel -> scene transform as BrainPoints: x right, -z up, y depth. */
export function voxelsToScene(p: Float32Array, scale: number): Float32Array {
  const out = new Float32Array(p.length)
  for (let i = 0; i < p.length; i += 3) {
    out[i] = p[i] * scale
    out[i + 1] = -p[i + 2] * scale
    out[i + 2] = p[i + 1] * scale
  }
  return out
}

export class HeroMeshes {
  readonly group = new THREE.Group()
  private slotOf = new Map<number, number>()   // pack index -> slot in the texture
  private heat = new Float32Array(0)
  private texData = new Float32Array(0)         // rgb = resting colour, a = heat
  private tex: THREE.DataTexture | null = null
  private dirty = false

  private base: string
  private scale: number

  constructor(base: string, scale = 0.001) {
    this.base = base
    this.scale = scale
  }

  async load(index: MeshIndex, groupOf: (packIdx: number) => string | undefined): Promise<void> {
    const entries = Object.entries(index.neurons)
    const parts = await Promise.all(entries.map(async ([k, m]) => {
      const buf = await (await fetch(`${this.base}/${m.file}`)).arrayBuffer()
      const { positions, indices } = decodeFsm(buf)
      return { packIdx: Number(k), positions: voxelsToScene(positions, this.scale), indices }
    }))
    let nv = 0, ni = 0
    for (const p of parts) { nv += p.positions.length / 3; ni += p.indices.length }
    const n = parts.length
    const texH = Math.max(1, Math.ceil(n / TEX_W))
    const pos = new Float32Array(nv * 3)
    const nid = new Float32Array(nv)
    const idx = new Uint32Array(ni)
    this.heat = new Float32Array(n)
    this.texData = new Float32Array(TEX_W * texH * 4)
    let vo = 0, io = 0
    parts.forEach((p, slot) => {
      const count = p.positions.length / 3
      pos.set(p.positions, vo * 3)
      nid.fill(slot, vo, vo + count)
      for (let i = 0; i < p.indices.length; i++) idx[io + i] = p.indices[i] + vo
      const c = groupColor(groupOf(p.packIdx))
      this.texData[slot * 4] = c.r; this.texData[slot * 4 + 1] = c.g; this.texData[slot * 4 + 2] = c.b; this.texData[slot * 4 + 3] = 0
      this.slotOf.set(p.packIdx, slot)
      vo += count; io += p.indices.length
    })
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geom.setAttribute('nid', new THREE.BufferAttribute(nid, 1))
    geom.setIndex(new THREE.BufferAttribute(idx, 1))
    geom.computeVertexNormals()   // neurons share no indices, so normals stay per neuron

    const tex = new THREE.DataTexture(this.texData, TEX_W, texH, THREE.RGBAFormat, THREE.FloatType)
    tex.minFilter = tex.magFilter = THREE.NearestFilter
    tex.generateMipmaps = false
    tex.needsUpdate = true
    this.tex = tex
    const mat = new THREE.MeshStandardMaterial({ roughness: 0.75, metalness: 0.0, transparent: true, opacity: 0.8 })
    mat.customProgramCacheKey = () => 'hero-meshes'
    mat.onBeforeCompile = shader => {
      shader.uniforms.heroTex = { value: tex }
      shader.uniforms.heroTexW = { value: TEX_W }
      shader.vertexShader = shader.vertexShader
        .replace('#include <common>', `#include <common>
          attribute float nid;
          uniform sampler2D heroTex;
          uniform int heroTexW;
          varying vec4 vHero;`)
        .replace('#include <begin_vertex>', `#include <begin_vertex>
          { int s = int(nid + 0.5); vHero = texelFetch(heroTex, ivec2(s % heroTexW, s / heroTexW), 0); }`)
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <common>', `#include <common>
          varying vec4 vHero;
          const vec3 heroHot = vec3(1.0, 0.62, 0.18);`)
        .replace('#include <color_fragment>', `#include <color_fragment>
          diffuseColor.rgb = mix(vHero.rgb, heroHot, vHero.a * 0.85);`)
        .replace('#include <emissivemap_fragment>', `#include <emissivemap_fragment>
          totalEmissiveRadiance = mix(vHero.rgb * 0.03, heroHot, vHero.a);`)
    }
    this.group.add(new THREE.Mesh(geom, mat))
  }

  addBin(neuronLocal: Uint32Array, count: Uint8Array, localToPack: Int32Array, gain = 1.0): void {
    for (let e = 0; e < neuronLocal.length; e++) {
      const slot = this.slotOf.get(localToPack[neuronLocal[e]])
      if (slot !== undefined) { this.heat[slot] = Math.min(1, this.heat[slot] + gain * count[e]); this.dirty = true }
    }
  }

  update(dtS: number, decayPerSecond = 4): void {
    if (!this.tex || !this.dirty) return
    const d = Math.exp(-decayPerSecond * dtS)
    let anyHot = false
    for (let s = 0; s < this.heat.length; s++) {
      let h = this.heat[s] * d
      if (h < 0.002) h = 0; else anyHot = true
      this.heat[s] = h
      this.texData[s * 4 + 3] = h
    }
    this.tex.needsUpdate = true
    this.dirty = anyHot
  }

  clearHeat(): void {
    this.heat.fill(0)
    for (let s = 0; s < this.heat.length; s++) this.texData[s * 4 + 3] = 0
    if (this.tex) this.tex.needsUpdate = true
    this.dirty = false
  }
  get count(): number { return this.slotOf.size }
}

const GROUP_HUES: Record<string, number> = {}
let nextHue = 0.55
export function groupColor(group: string | undefined): THREE.Color {
  const key = group ?? '_'
  if (!(key in GROUP_HUES)) { GROUP_HUES[key] = nextHue; nextHue = (nextHue + 0.23) % 1 }
  return new THREE.Color().setHSL(GROUP_HUES[key], 0.4, 0.17)   // resting meshes sit well back; a spike lifts them to amber
}
