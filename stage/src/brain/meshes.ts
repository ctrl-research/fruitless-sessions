/** Hero neuron meshes (FSM1 files) colored by hero-layer activity. */

import * as THREE from 'three'

export interface MeshIndex {
  lod: number
  voxel_nm: number
  neurons: Record<string, { bodyId: number; vertices: number; triangles: number; file: string }>
}

const MAGIC = 0x314d5346 // "FSM1"

export function decodeFsm(buf: ArrayBuffer): { positions: Float32Array; indices: Uint32Array } {
  const dv = new DataView(buf)
  if (dv.getUint32(0, true) !== MAGIC) throw new Error('not an FSM1 mesh')
  const nv = dv.getUint32(4, true), nf = dv.getUint32(8, true)
  const positions = new Float32Array(buf.slice(12, 12 + 12 * nv))
  const indices = new Uint32Array(buf.slice(12 + 12 * nv, 12 + 12 * nv + 12 * nf))
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
  private byIndex = new Map<number, { mesh: THREE.Mesh; mat: THREE.MeshStandardMaterial; heat: number; base: THREE.Color }>()

  private base: string
  private scale: number

  constructor(base: string, scale = 0.001) {
    this.base = base
    this.scale = scale
  }

  async load(index: MeshIndex, groupOf: (packIdx: number) => string | undefined): Promise<void> {
    const entries = Object.entries(index.neurons)
    await Promise.all(entries.map(async ([k, m]) => {
      const packIdx = Number(k)
      const buf = await (await fetch(`${this.base}/${m.file}`)).arrayBuffer()
      const { positions, indices } = decodeFsm(buf)
      const geom = new THREE.BufferGeometry()
      geom.setAttribute('position', new THREE.BufferAttribute(voxelsToScene(positions, this.scale), 3))
      geom.setIndex(new THREE.BufferAttribute(indices, 1))
      geom.computeVertexNormals()
      const base = groupColor(groupOf(packIdx))
      const mat = new THREE.MeshStandardMaterial({
        color: base, emissive: base.clone().multiplyScalar(0.15), roughness: 0.6, metalness: 0.0,
        transparent: true, opacity: 0.92,
      })
      const mesh = new THREE.Mesh(geom, mat)
      mesh.userData.packIdx = packIdx
      this.group.add(mesh)
      this.byIndex.set(packIdx, { mesh, mat, heat: 0, base })
    }))
  }

  addBin(neuronLocal: Uint32Array, count: Uint8Array, localToPack: Int32Array, gain = 1.0): void {
    for (let e = 0; e < neuronLocal.length; e++) {
      const packIdx = localToPack[neuronLocal[e]]
      const h = this.byIndex.get(packIdx)
      if (h) h.heat = Math.min(1, h.heat + gain * count[e])
    }
  }

  update(dtS: number, decayPerSecond = 4): void {
    const d = Math.exp(-decayPerSecond * dtS)
    const hot = new THREE.Color(1.0, 0.62, 0.18)
    for (const h of this.byIndex.values()) {
      h.heat *= d
      if (h.heat < 0.002) h.heat = 0
      h.mat.emissive.copy(h.base).multiplyScalar(0.15).lerp(hot, h.heat)
      h.mat.color.copy(h.base).lerp(hot, h.heat * 0.6)
    }
  }

  clearHeat(): void { for (const h of this.byIndex.values()) h.heat = 0 }
  get count(): number { return this.byIndex.size }
}

const GROUP_HUES: Record<string, number> = {}
let nextHue = 0.55
export function groupColor(group: string | undefined): THREE.Color {
  const key = group ?? '_'
  if (!(key in GROUP_HUES)) { GROUP_HUES[key] = nextHue; nextHue = (nextHue + 0.23) % 1 }
  return new THREE.Color().setHSL(GROUP_HUES[key], 0.55, 0.55)
}
