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

  /** Draw the form across the top and one lane of notes per band member below it. */
  drawStrip(canvas: HTMLCanvasElement, t: number): void {
    const ctx = canvas.getContext('2d')!
    const dpr = devicePixelRatio
    const w = canvas.width = canvas.clientWidth * dpr
    const h = canvas.height = canvas.clientHeight * dpr
    ctx.clearRect(0, 0, w, h)
    const dur = this.tune.duration_s
    const x = (s: number) => (s / dur) * w
    const headerH = 16 * dpr
    const roles = Object.keys(this.notes)
    const laneH = roles.length ? (h - headerH) / roles.length : 0
    // sections
    let bar = 0
    const colors: Record<string, string> = { head: '#2a2438', solo: '#1f2f3a', trade: '#3a2a1f', free: '#1f3a2a' }
    for (const s of this.tune.form) {
      const x0 = x(bar * this.barS), x1 = x((bar + s.bars) * this.barS)
      ctx.fillStyle = colors[s.kind] ?? '#222'
      ctx.fillRect(x0, 0, x1 - x0, headerH)
      ctx.fillStyle = (colors[s.kind] ?? '#222') + '66'
      ctx.fillRect(x0, headerH, x1 - x0, h - headerH)
      ctx.fillStyle = '#8a8a96'
      ctx.font = `${10 * dpr}px system-ui`
      ctx.fillText(s.kind + (s.who.length && s.kind !== 'free' ? ' ' + s.who.join('/') : ''), x0 + 4 * dpr, 11 * dpr)
      bar += s.bars
    }
    // bar lines
    ctx.strokeStyle = '#2c2c38'
    for (let b = 0; b * this.barS < dur; b++) { const xb = x(b * this.barS); ctx.beginPath(); ctx.moveTo(xb, headerH); ctx.lineTo(xb, h); ctx.stroke() }
    // one lane per role: label at the left, notes by pitch within the lane
    const laneColor: Record<string, string> = { sax: '#f2b35c', bass: '#7fb3d5', drums: '#c98ad6', piano: '#8fd6a8' }
    roles.forEach((role, ri) => {
      const y0 = headerH + ri * laneH
      ctx.strokeStyle = '#1b1b24'
      ctx.beginPath(); ctx.moveTo(0, y0); ctx.lineTo(w, y0); ctx.stroke()
      ctx.fillStyle = 'rgba(7,7,11,0.7)'
      ctx.fillRect(0, y0 + 2 * dpr, 44 * dpr, laneH - 4 * dpr)
      ctx.fillStyle = laneColor[role] ?? '#ccc'
      ctx.font = `${10 * dpr}px system-ui`
      ctx.fillText(role, 5 * dpr, y0 + laneH / 2 + 3.5 * dpr)
      const ns = this.notes[role]
      const pitches = ns.map(n => n.midi)
      const lo = Math.min(...pitches, 127), hi = Math.max(...pitches, 0)
      const span = Math.max(1, hi - lo)
      const pad = 3 * dpr
      for (const n of ns) {
        const y = y0 + laneH - pad - ((n.midi - lo) / span) * (laneH - 2 * pad)
        ctx.globalAlpha = 0.35 + 0.65 * (n.vel / 127)
        ctx.fillRect(x(n.t), y - dpr, Math.max(1.5 * dpr, x(n.dur)), 2 * dpr)
      }
      ctx.globalAlpha = 1
    })
    // playhead
    ctx.fillStyle = '#e8e6e1'
    ctx.fillRect(x(t) - dpr, 0, 2 * dpr, h)
  }
}
