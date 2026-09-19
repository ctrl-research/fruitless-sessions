/** The audio element is the clock when a take has audio; otherwise a rAF clock. */

import { Transport } from './transport'

export class AudioClock {
  readonly audio: HTMLAudioElement | null
  readonly transport: Transport
  constructor(transport: Transport, src: string | null) {
    this.transport = transport
    // an element in the document, not a detached Audio(): Chrome would not start
    // loading the detached one here, and readyState stayed 0
    const el = document.getElementById('audio') as HTMLAudioElement | null
    this.audio = src && el ? el : null
    if (this.audio) {
      const a = this.audio
      a.preload = 'auto'
      a.src = src!
      a.load()
      transport.onPlay = () => { a.playbackRate = transport.speed; a.play().catch(console.error) }
      transport.onPause = () => a.pause()
      transport.onSeekAudio = (t) => { a.currentTime = t }
      transport.onSpeed = (s) => { a.playbackRate = s }
      a.addEventListener('ended', () => transport.pause())
    }
  }

  /** Called every frame; returns the authoritative time. */
  time(): number {
    if (this.audio && this.transport.playing) {
      return this.audio.currentTime
    }
    return this.transport.time
  }
}
