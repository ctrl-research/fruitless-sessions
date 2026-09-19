/** Chart, form and note events of a take, drawn along the transport. */

export interface TuneInfo {
  name: string
  tempo_bpm: number
  grid: string
  key: string
  step_s: number
  steps_per_bar: number
  total_steps: number
  duration_s: number
  chart: string[][]
  form: { kind: string; who: string[]; bars: number }[]
  free_style: boolean
}

export interface NoteEvent { t: number; dur: number; midi: number; vel: number; step: number; source: string }

export class Score {
  readonly barS: number
  readonly tune: TuneInfo
  readonly notes: Record<string, NoteEvent[]>
  constructor(tune: TuneInfo, notes: Record<string, NoteEvent[]>) {
    this.tune = tune
    this.notes = notes
    this.barS = tune.step_s * tune.steps_per_bar
  }

  barAt(t: number): number { return Math.floor(t / this.barS) }

  sectionAt(t: number): { kind: string; who: string[]; index: number; barInSection: number } | null {
    let bar = this.barAt(t)
    for (let i = 0; i < this.tune.form.length; i++) {
      const s = this.tune.form[i]
      if (bar < s.bars) return { kind: s.kind, who: s.who, index: i, barInSection: bar }
      bar -= s.bars
    }
    return null
  }

  chordAt(t: number): string {
    const chart = this.tune.chart
    if (!chart.length) return ''
    const bar = this.barAt(t) % chart.length
    const beatS = this.barS / 4
    const beat = Math.floor((t - this.barAt(t) * this.barS) / beatS)
    const row = chart[bar]
    for (let b = Math.min(beat, row.length - 1); b >= 0; b--) if (row[b]) return row[b]
    for (let pb = bar - 1; pb >= 0; pb--) { const prev = chart[pb].filter(Boolean); if (prev.length) return prev[prev.length - 1] }
    return ''
  }

  /** Notes of a role sounding at time t. */
  soundingAt(role: string, t: number): NoteEvent[] {
    const ns = this.notes[role] ?? []
    return ns.filter(n => n.t <= t && t < n.t + n.dur)
  }

  /** Draw form sections and note density onto a canvas the width of the transport. */
  drawStrip(canvas: HTMLCanvasElement, t: number): void {
    const ctx = canvas.getContext('2d')!
    const w = canvas.width = canvas.clientWidth * devicePixelRatio
    const h = canvas.height = canvas.clientHeight * devicePixelRatio
    ctx.clearRect(0, 0, w, h)
    const dur = this.tune.duration_s
    const x = (s: number) => (s / dur) * w
    // sections
    let bar = 0
    const colors: Record<string, string> = { head: '#2a2438', solo: '#1f2f3a', trade: '#3a2a1f', free: '#1f3a2a' }
    for (const s of this.tune.form) {
      const x0 = x(bar * this.barS), x1 = x((bar + s.bars) * this.barS)
      ctx.fillStyle = colors[s.kind] ?? '#222'
      ctx.fillRect(x0, 0, x1 - x0, h)
      ctx.fillStyle = '#8a8a96'
      ctx.font = `${10 * devicePixelRatio}px system-ui`
      ctx.fillText(s.kind + (s.who.length ? ' ' + s.who.join('/') : ''), x0 + 4 * devicePixelRatio, 11 * devicePixelRatio)
      bar += s.bars
    }
    // bar lines
    ctx.strokeStyle = '#2c2c38'
    for (let b = 0; b * this.barS < dur; b++) { const xb = x(b * this.barS); ctx.beginPath(); ctx.moveTo(xb, h * 0.35); ctx.lineTo(xb, h); ctx.stroke() }
    // notes as small marks, pitch on y
    for (const [role, ns] of Object.entries(this.notes)) {
      ctx.fillStyle = role === 'sax' ? '#f2b35c' : '#7fb3d5'
      for (const n of ns) {
        const y = h - ((n.midi - 48) / 40) * (h * 0.6) - h * 0.05
        ctx.globalAlpha = 0.35 + 0.65 * (n.vel / 127)
        ctx.fillRect(x(n.t), y, Math.max(1.5 * devicePixelRatio, x(n.dur)), 2 * devicePixelRatio)
      }
      ctx.globalAlpha = 1
    }
    // playhead
    ctx.fillStyle = '#e8e6e1'
    ctx.fillRect(x(t) - devicePixelRatio, 0, 2 * devicePixelRatio, h)
  }
}
