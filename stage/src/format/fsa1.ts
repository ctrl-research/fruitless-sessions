/** FSA1 binned activity chunks, as written by fruitless.recording.activity. */

export interface Chunk {
  binMs: number
  nBins: number
  nNeurons: number
  offsets: Uint32Array   // nBins + 1
  neuron: Uint32Array    // nEvents
  count: Uint8Array      // nEvents
}

export interface LayerMeta {
  format: 'fsa1'
  bin_ms: number
  chunk_s: number
  n_bins: number
  n_chunks: number
  n_neurons: number
  space: 'pack' | 'subset'
  subset?: string
  ticks: number
  dt_ms: number
  path: string
}

const MAGIC = 0x31415346 // "FSA1" little-endian

export function decodeChunk(buf: ArrayBuffer): Chunk {
  const dv = new DataView(buf)
  if (dv.getUint32(0, true) !== MAGIC) throw new Error('not an FSA1 chunk')
  const binMs = dv.getUint32(4, true)
  const nBins = dv.getUint32(8, true)
  const nNeurons = dv.getUint32(12, true)
  const nEvents = dv.getUint32(16, true)
  let o = 20
  const offsets = new Uint32Array(buf.slice(o, o + 4 * (nBins + 1)))
  o += 4 * (nBins + 1)
  const neuron = new Uint32Array(buf.slice(o, o + 4 * nEvents))
  o += 4 * nEvents
  const count = new Uint8Array(buf.slice(o, o + nEvents))
  return { binMs, nBins, nNeurons, offsets, neuron, count }
}

/** Lazily fetches chunk files of one layer and answers "events in global bin b". */
export class Layer {
  private chunks = new Map<number, Promise<Chunk>>()
  readonly binsPerChunk: number
  readonly subset: Promise<Int32Array | null>
  readonly base: string
  readonly meta: LayerMeta

  constructor(base: string, meta: LayerMeta) {
    this.base = base
    this.meta = meta
    this.binsPerChunk = Math.round((meta.chunk_s * 1000) / meta.bin_ms)
    this.subset = meta.subset
      ? fetch(`${base}/${meta.path}/${meta.subset}`).then(r => r.arrayBuffer()).then(decodeNpyInt32)
      : Promise.resolve(null)
  }

  get durationS(): number { return (this.meta.n_bins * this.meta.bin_ms) / 1000 }

  binAt(timeS: number): number {
    return Math.min(this.meta.n_bins - 1, Math.max(0, Math.floor((timeS * 1000) / this.meta.bin_ms)))
  }

  chunk(index: number): Promise<Chunk> {
    let p = this.chunks.get(index)
    if (!p) {
      const name = `chunk_${String(index).padStart(4, '0')}.bin`
      p = fetch(`${this.base}/${this.meta.path}/${name}`).then(r => {
        if (!r.ok) throw new Error(`${name}: ${r.status}`)
        return r.arrayBuffer()
      }).then(decodeChunk)
      this.chunks.set(index, p)
    }
    return p
  }

  /** Resolve synchronously if the chunk is loaded, else kick off the load and return null. */
  private loaded = new Map<number, Chunk>()
  binSync(globalBin: number): { neuron: Uint32Array; count: Uint8Array } | null {
    const ci = Math.floor(globalBin / this.binsPerChunk)
    const local = globalBin - ci * this.binsPerChunk
    const c = this.loaded.get(ci)
    if (!c) {
      this.chunk(ci).then(ch => this.loaded.set(ci, ch)).catch(console.error)
      return null
    }
    if (local >= c.nBins) return { neuron: new Uint32Array(0), count: new Uint8Array(0) }
    const lo = c.offsets[local], hi = c.offsets[local + 1]
    return { neuron: c.neuron.subarray(lo, hi), count: c.count.subarray(lo, hi) }
  }

  prefetch(globalBin: number, ahead = 1): void {
    const ci = Math.floor(globalBin / this.binsPerChunk)
    for (let i = ci; i <= Math.min(ci + ahead, this.meta.n_chunks - 1); i++) {
      if (!this.loaded.has(i)) this.chunk(i).then(ch => this.loaded.set(i, ch)).catch(console.error)
    }
  }
}

/** Minimal .npy reader for a 1-D little-endian int32 array (what subset.npy is). */
export function decodeNpyInt32(buf: ArrayBuffer): Int32Array {
  const dv = new DataView(buf)
  if (dv.getUint8(0) !== 0x93) throw new Error('not a .npy file')
  const major = dv.getUint8(6)
  const headerLen = major === 1 ? dv.getUint16(8, true) : dv.getUint32(8, true)
  const start = (major === 1 ? 10 : 12) + headerLen
  const header = new TextDecoder().decode(new Uint8Array(buf, major === 1 ? 10 : 12, headerLen))
  if (!/'<i4'/.test(header)) throw new Error(`subset.npy dtype not <i4: ${header}`)
  return new Int32Array(buf.slice(start))
}
