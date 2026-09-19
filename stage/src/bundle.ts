/** Loads take.json and the shared arrays of a take bundle. */

import { Layer, type LayerMeta } from './format/fsa1'

export interface FlyEntry {
  role: string
  layers: Record<string, LayerMeta>
  circuit: Record<string, number[]>
}

export interface TakeManifest {
  format: string
  name: string
  duration_s: number
  seed: number | null
  flies: FlyEntry[]
  shared: {
    soma_xyz: string
    superclass: string
    superclass_legend: string[]
    n_neurons: number
    with_soma: number
    voxel_nm: number
  }
  audio: string | null
  smoke?: Record<string, unknown>
}

export interface Take {
  base: string
  manifest: TakeManifest
  somaXyz: Float32Array       // n_neurons * 3, NaN when unknown
  superclass: Uint8Array      // n_neurons, 255 = none
  flies: { entry: FlyEntry; layers: Record<string, Layer> }[]
}

export async function loadTake(base: string): Promise<Take> {
  const manifest: TakeManifest = await (await fetch(`${base}/take.json`)).json()
  if (manifest.format !== 'fruitless-take/1') throw new Error(`unknown take format ${manifest.format}`)
  const [xyzBuf, scBuf] = await Promise.all([
    fetch(`${base}/${manifest.shared.soma_xyz}`).then(r => r.arrayBuffer()),
    fetch(`${base}/${manifest.shared.superclass}`).then(r => r.arrayBuffer()),
  ])
  const flies = manifest.flies.map(entry => ({
    entry,
    layers: Object.fromEntries(Object.entries(entry.layers).map(([k, m]) => [k, new Layer(base, m)])),
  }))
  return { base, manifest, somaXyz: new Float32Array(xyzBuf), superclass: new Uint8Array(scBuf), flies }
}
