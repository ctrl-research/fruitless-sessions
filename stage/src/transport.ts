/** Playback clock and scrub bar. The audio element is the clock when a take has audio
 *  (see AudioClock); otherwise this is a requestAnimationFrame clock at a chosen speed. */

export class Transport {
  time = 0                 // seconds of biological time
  playing = false
  speed = 1                // playback rate; audio takes cannot go below 0.25
  volume = 1               // 0..1, remembered across visits
  muted = false
  private last = 0
  private onSeek: (() => void)[] = []
  onPlay: (() => void) | null = null
  onPause: (() => void) | null = null
  onSeekAudio: ((t: number) => void) | null = null
  onSpeed: ((s: number) => void) | null = null
  onVolume: ((volume: number, muted: boolean) => void) | null = null
  readonly duration: number
  private root: HTMLElement

  constructor(duration: number, root: HTMLElement) {
    this.duration = duration
    this.root = root
    try {
      const v = localStorage.getItem('fs.volume')
      if (v !== null) this.volume = Math.max(0, Math.min(1, parseFloat(v) || 0))
      this.muted = localStorage.getItem('fs.muted') === '1'
    } catch { /* private mode */ }
    this.render()
  }

  private el!: {
    play: HTMLButtonElement; range: HTMLInputElement; time: HTMLSpanElement; speed: HTMLSelectElement
    mute: HTMLButtonElement; volume: HTMLInputElement; audio: HTMLSpanElement
  }

  private render() {
    this.root.innerHTML = `
      <button class="play" title="space">▶</button>
      <input class="range" type="range" min="0" max="${this.duration}" step="0.001" value="0" />
      <span class="time">0.000 s</span>
      <select class="speed" title="playback speed (biological seconds per wall second)">
        <option value="0.1">0.1×</option><option value="0.25">0.25×</option>
        <option value="0.5">0.5×</option><option value="1" selected>1×</option>
      </select>
      <span class="audio">
        <button class="mute" title="mute (m)">🔊</button>
        <input class="volume" type="range" min="0" max="1" step="0.01" value="${this.volume}" title="volume" />
      </span>`
    this.el = {
      play: this.root.querySelector('.play')!,
      range: this.root.querySelector('.range')!,
      time: this.root.querySelector('.time')!,
      speed: this.root.querySelector('.speed')!,
      mute: this.root.querySelector('.mute')!,
      volume: this.root.querySelector('.volume')!,
      audio: this.root.querySelector('.audio')!,
    }
    this.el.play.onclick = () => this.toggle()
    this.el.range.oninput = () => { this.seek(parseFloat(this.el.range.value)) }
    this.el.speed.onchange = () => { this.speed = parseFloat(this.el.speed.value); this.onSpeed?.(this.speed) }
    // dragging the slider up from zero unmutes; dragging to zero is just quiet, not muted
    this.el.volume.oninput = () => { this.setVolume(parseFloat(this.el.volume.value), this.muted && parseFloat(this.el.volume.value) === 0) }
    this.el.mute.onclick = () => this.setVolume(this.volume, !this.muted)
    window.addEventListener('keydown', e => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return
      if (e.code === 'Space') { e.preventDefault(); this.toggle() }
      else if (e.key === 'm' || e.key === 'M') this.setVolume(this.volume, !this.muted)
    })
    this.refreshVolume()
  }

  /** Show the volume controls only when the take has audio to control. */
  showVolume(on: boolean) { this.el.audio.style.display = on ? '' : 'none' }

  setVolume(volume: number, muted = this.muted) {
    this.volume = Math.max(0, Math.min(1, volume))
    this.muted = muted
    this.refreshVolume()
    this.onVolume?.(this.volume, this.muted)
    try {
      localStorage.setItem('fs.volume', String(this.volume))
      localStorage.setItem('fs.muted', this.muted ? '1' : '0')
    } catch { /* ignore */ }
  }

  private refreshVolume() {
    this.el.volume.value = String(this.volume)
    const silent = this.muted || this.volume === 0
    this.el.mute.textContent = silent ? '🔇' : this.volume < 0.5 ? '🔉' : '🔊'
    this.el.mute.title = this.muted ? 'unmute (m)' : 'mute (m)'
    this.el.mute.classList.toggle('muted', this.muted)
  }

  toggle() { this.playing ? this.pause() : this.play() }
  play() { this.playing = true; this.last = performance.now(); this.el.play.textContent = '❚❚'; this.onPlay?.() }
  pause() { this.playing = false; this.el.play.textContent = '▶'; this.onPause?.() }
  seek(t: number) {
    this.time = Math.max(0, Math.min(this.duration, t))
    this.onSeekAudio?.(this.time)
    this.onSeek.forEach(f => f())
    this.refresh()
  }
  /** Adopt an externally authoritative time (the audio element). */
  sync(t: number) { this.time = t; this.refresh() }
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
