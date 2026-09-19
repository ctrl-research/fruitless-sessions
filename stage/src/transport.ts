/** Playback clock and scrub bar. Audio will become the clock in phase 2;
 *  until then this is a requestAnimationFrame clock at a chosen speed. */

export class Transport {
  time = 0                 // seconds of biological time
  playing = false
  speed = 0.25             // biological seconds per wall second (slow motion by default)
  private last = 0
  private onSeek: (() => void)[] = []
  readonly duration: number
  private root: HTMLElement

  constructor(duration: number, root: HTMLElement) {
    this.duration = duration
    this.root = root
    this.render()
  }

  private el!: { play: HTMLButtonElement; range: HTMLInputElement; time: HTMLSpanElement; speed: HTMLSelectElement }

  private render() {
    this.root.innerHTML = `
      <button class="play" title="space">▶</button>
      <input class="range" type="range" min="0" max="${this.duration}" step="0.001" value="0" />
      <span class="time">0.000 s</span>
      <select class="speed" title="playback speed (biological seconds per wall second)">
        <option value="0.1">0.1×</option><option value="0.25" selected>0.25×</option>
        <option value="0.5">0.5×</option><option value="1">1×</option>
      </select>`
    this.el = {
      play: this.root.querySelector('.play')!,
      range: this.root.querySelector('.range')!,
      time: this.root.querySelector('.time')!,
      speed: this.root.querySelector('.speed')!,
    }
    this.el.play.onclick = () => this.toggle()
    this.el.range.oninput = () => { this.seek(parseFloat(this.el.range.value)) }
    this.el.speed.onchange = () => { this.speed = parseFloat(this.el.speed.value) }
    window.addEventListener('keydown', e => {
      if (e.code === 'Space' && !(e.target instanceof HTMLInputElement)) { e.preventDefault(); this.toggle() }
    })
  }

  toggle() { this.playing ? this.pause() : this.play() }
  play() { this.playing = true; this.last = performance.now(); this.el.play.textContent = '❚❚' }
  pause() { this.playing = false; this.el.play.textContent = '▶' }
  seek(t: number) {
    this.time = Math.max(0, Math.min(this.duration, t))
    this.onSeek.forEach(f => f())
    this.refresh()
  }
  addSeekListener(f: () => void) { this.onSeek.push(f) }

  /** Advance if playing; returns wall dt in seconds. */
  tick(now: number): number {
    const dt = this.last ? (now - this.last) / 1000 : 0
    this.last = now
    if (this.playing) {
      this.time += dt * this.speed
      if (this.time >= this.duration) { this.time = this.duration; this.pause() }
      this.refresh()
    }
    return dt
  }

  private refresh() {
    this.el.range.value = String(this.time)
    this.el.time.textContent = `${this.time.toFixed(3)} s`
  }
}
