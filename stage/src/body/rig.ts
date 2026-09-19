/** Motor readouts -> Pose. One mapping per role, stated here and shown on the page.
 *
 *  Nothing here is keyframed. Every joint angle is a function of the readouts
 *  the take recorded (fruitless.flies.*), the group rates from the hero layer,
 *  and the notes currently sounding, evaluated fresh each frame.
 */

import { type Pose, idlePose } from './fly'

export interface RigInputs {
  readout: Record<string, number>     // motor readouts for the current step
  rates: Record<string, number>       // smoothed group rates in Hz (jo_a, giant_fiber, ...)
  noteOn: boolean                     // a note of this role is sounding
  noteAge: number                     // seconds since the sounding note started
  t: number                           // playback time
}

export interface RigRule { joint: string; from: string; rule: string }

export interface Rig {
  role: string
  rules: RigRule[]
  pose(inp: RigInputs, prev: Pose, dt: number): Pose
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const lerp = (a: number, b: number, k: number) => a + (b - a) * k

/** Shared behaviour: breathing, antennae from ear input, startle from the giant fiber. */
function common(inp: RigInputs, p: Pose, startle: { until: number }): void {
  p.abdomenScale = 1 + 0.03 * Math.sin(inp.t * 2 * Math.PI * 0.6)
  const ear = ((inp.rates['jo_a'] ?? 0) + (inp.rates['jo_b'] ?? 0)) / 120
  p.antennae = clamp(ear, 0, 1) * 0.35 * (0.6 + 0.4 * Math.sin(inp.t * 2 * Math.PI * 7))
  const gf = inp.rates['giant_fiber'] ?? 0
  if (gf > 5 && inp.t > startle.until) startle.until = inp.t + 0.35
  if (inp.t < startle.until) {
    const k = (startle.until - inp.t) / 0.35            // 1 at onset -> 0
    p.bodyHeight = 0.9 * Math.sin(Math.PI * (1 - k))      // hop
    p.wingExtend = [1.3, 1.3]
    p.wingFlap = 0.5
    p.wingHz = 14
    for (const leg of p.legs) { leg[1] = 0.9; leg[2] = -0.6 }   // legs tuck
  }
}

export const saxRig: Rig = {
  role: 'sax',
  rules: [
    { joint: 'right wing extension', from: 'song_on', rule: 'extends ~75° while the song circuit is on (one-wing courtship song), folds back when off' },
    { joint: 'wing vibration', from: 'intensity', rule: 'amplitude = wing MN rate / 80 Hz; pulse song (pulse > 0.9) beats faster and jerkier' },
    { joint: 'body pitch', from: 'intensity', rule: 'leans forward up to 12° with wing MN rate' },
    { joint: 'forelegs', from: 'notes', rule: 'press the keys on each note onset; middle and hind legs hold the stand' },
    { joint: 'proboscis', from: 'notes', rule: 'on the mouthpiece while a note sounds' },
    { joint: 'antennae', from: 'jo_a + jo_b', rule: 'twitch with auditory afferent rate (the fly hearing the band)' },
    { joint: 'whole body', from: 'giant_fiber', rule: 'startle hop with both wings out when DNp01 fires' },
  ],
  pose(inp, prev, dt) {
    const p = idlePose()
    const on = (inp.readout['song_on'] ?? 0) >= 0.5
    const intensity = inp.readout['intensity'] ?? 0
    const pulse = inp.readout['pulse'] ?? 0
    const k = 1 - Math.exp(-dt * 10)   // smoothing toward targets
    // right wing sings, left stays folded
    const targetExt = on ? 1.3 : 0.12
    p.wingExtend = [0.12, lerp(prev.wingExtend[1], targetExt, k)]
    p.wingFlap = lerp(prev.wingFlap, on ? clamp(intensity / 80, 0.05, 1) * 0.35 : 0, k)
    p.wingHz = pulse > 0.9 ? 22 : 13
    p.bodyPitch = lerp(prev.bodyPitch, clamp(intensity / 80, 0, 1) * 0.21, k)
    // sax posture: raise the front, forelegs up on the horn
    p.legs[0] = [0.9, -0.3, -0.9]
    p.legs[3] = [0.9, -0.3, -0.9]
    if (inp.noteOn) {
      const press = Math.exp(-inp.noteAge * 8)
      p.legs[0][2] -= 0.35 * press
      p.legs[3][2] -= 0.35 * (1 - press) * 0.5
      p.proboscis = 1
      p.headYaw = 0.05 * Math.sin(inp.t * 6)
    } else {
      p.proboscis = lerp(prev.proboscis, 0.35, k)
    }
    common(inp, p, this as unknown as { until: number })
    return p
  },
}
;(saxRig as unknown as { until: number }).until = 0

export const idleRig: Rig = {
  role: 'idle',
  rules: [{ joint: 'all', from: 'nothing', rule: 'standing; breathing only' }],
  pose(inp, _prev, _dt) { const p = idlePose(); common(inp, p, this as unknown as { until: number }); return p },
}
;(idleRig as unknown as { until: number }).until = 0

export function rigFor(role: string): Rig {
  return role === 'sax' ? saxRig : idleRig
}
