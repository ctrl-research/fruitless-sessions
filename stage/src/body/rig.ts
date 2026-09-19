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
    for (const leg of p.legs) { leg[1] = -0.5; leg[2] = 0.9 }   // legs tuck up
  }
}

export const saxRig: Rig = {
  role: 'sax',
  rules: [
    { joint: 'right wing extension', from: 'song_on', rule: 'extends ~75° while the song circuit is on (one-wing courtship song), folds back when off' },
    { joint: 'wing vibration', from: 'intensity', rule: 'amplitude = wing MN rate / 80 Hz; pulse song (pulse > 0.9) beats faster and jerkier' },
    { joint: 'body pitch', from: 'intensity', rule: 'stands up to the horn; leans in up to 12° with wing MN rate' },
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
    // stands up to the horn: nose up ~35°, leaning further in with intensity
    p.bodyPitch = lerp(prev.bodyPitch, -0.6 + clamp(intensity / 80, 0, 1) * 0.2, k)
    p.bodyHeight = 0.25
    // sax posture: forelegs up on the horn
    p.legs[0] = [0.9, -0.7, 1.2]
    p.legs[3] = [0.9, -0.7, 1.2]
    if (inp.noteOn) {
      const press = Math.exp(-inp.noteAge * 8)
      p.legs[0][1] -= 0.3 * press
      p.legs[3][1] -= 0.3 * (1 - press) * 0.5
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

export const bassRig: Rig = {
  role: 'bass',
  rules: [
    { joint: 'legs', from: 'fl_L .. hl_R', rule: 'each leg lifts and swings with its own leg MN rate; the tripod that fires steps, the other stands' },
    { joint: 'forelegs', from: 'step_l / step_r', rule: 'a footfall plucks: the near foreleg snaps on each tripod onset' },
    { joint: 'body height', from: 'load', rule: 'bobs with mean leg MN rate' },
    { joint: 'antennae', from: 'jo_a + jo_b', rule: 'twitch with auditory afferent rate' },
    { joint: 'whole body', from: 'giant_fiber', rule: 'startle hop with both wings out when DNp01 fires' },
  ],
  pose(inp, prev, dt) {
    const p = idlePose()
    const k = 1 - Math.exp(-dt * 14)
    const legs = ['fl_L', 'fl_R', 'ml_L', 'ml_R', 'hl_L', 'hl_R']
    // pose.legs order is [L0 L1 L2 R0 R1 R2] = fl_L ml_L hl_L fl_R ml_R hl_R
    const order = [0, 2, 4, 1, 3, 5]
    for (let i = 0; i < 6; i++) {
      const rate = inp.readout[legs[order[i]]] ?? 0
      const lift = clamp(rate / 40, 0, 1)
      const target: [number, number, number] = [
        idlePose().legs[i][0] + 0.35 * lift * (i % 3 === 0 ? 1 : i % 3 === 2 ? -1 : 0),
        0.15 - 0.6 * lift,          // femur rises as the leg lifts
        1.8 - 0.7 * lift,           // tibia unfolds as it swings
      ]
      p.legs[i] = [lerp(prev.legs[i][0], target[0], k), lerp(prev.legs[i][1], target[1], k), lerp(prev.legs[i][2], target[2], k)]
    }
    if (inp.noteOn) {
      const pluck = Math.exp(-inp.noteAge * 10)
      p.legs[0][1] -= 0.45 * pluck   // left foreleg lifts to pluck the strings
    }
    const load = inp.readout['load'] ?? 0
    p.bodyHeight = lerp(prev.bodyHeight, 0.08 * Math.sin(inp.t * 2 * Math.PI * 2) * clamp(load / 30, 0, 1), k)
    p.bodyPitch = -0.45           // stands up to the neck of the upright
    p.bodyHeight += 0.18
    common(inp, p, this as unknown as { until: number })
    return p
  },
}
;(bassRig as unknown as { until: number }).until = 0

export const drumsRig: Rig = {
  role: 'drums',
  rules: [
    { joint: 'both wings', from: 'power', rule: 'beat amplitude from power muscle MN rate (DLM, DVM); the kit is hit on the downstroke' },
    { joint: 'wing tempo', from: 'burst', rule: 'jerkier, faster strokes when spikes bunch into bursts (fills)' },
    { joint: 'body pitch', from: 'steer', rule: 'leans into the snare with steering muscle MN rate' },
    { joint: 'hind legs', from: 'notes', rule: 'stamp the kick pedal on kick hits' },
    { joint: 'antennae', from: 'jo_a + jo_b', rule: 'twitch with auditory afferent rate' },
    { joint: 'whole body', from: 'giant_fiber', rule: 'startle hop and crash when DNp01 fires' },
  ],
  pose(inp, prev, dt) {
    const p = idlePose()
    const k = 1 - Math.exp(-dt * 10)
    const power = inp.readout['power'] ?? 0
    const steer = inp.readout['steer'] ?? 0
    const burst = inp.readout['burst'] ?? 0
    const amp = clamp(power / 60, 0, 1)
    p.wingExtend = [lerp(prev.wingExtend[0], 0.9, k), lerp(prev.wingExtend[1], 0.9, k)]
    p.wingFlap = lerp(prev.wingFlap, 0.15 + 0.5 * amp, k)
    p.wingHz = burst > 0.9 ? 9 : 5   // slowed far below biology so the strokes read as hits
    p.bodyPitch = lerp(prev.bodyPitch, -0.2 + clamp(steer / 60, 0, 1) * 0.25, k)   // sits up behind the kit, leans in on the snare
    p.legs[0] = [0.7, -0.6, 1.3]; p.legs[3] = [0.7, -0.6, 1.3]   // forelegs up, sticks
    if (inp.noteOn) {
      const stamp = Math.exp(-inp.noteAge * 12)
      p.legs[5][1] -= 0.4 * stamp   // right hind leg lifts to stamp the pedal
    }
    common(inp, p, this as unknown as { until: number })
    return p
  },
}
;(drumsRig as unknown as { until: number }).until = 0

export const pianoRig: Rig = {
  role: 'piano',
  rules: [
    { joint: 'head yaw', from: 'bump_deg', rule: 'turns toward the key the ring points at: left for flats, right for sharps' },
    { joint: 'forelegs', from: 'notes', rule: 'both forelegs drop onto the keys on each comp' },
    { joint: 'body pitch', from: 'epg_hz', rule: 'leans over the keyboard with EPG population rate' },
    { joint: 'abdomen', from: 'mb_gain', rule: 'swells when the mushroom body output is above baseline (reward), shrinks below it' },
    { joint: 'antennae', from: 'jo_a + jo_b', rule: 'twitch with auditory afferent rate' },
    { joint: 'whole body', from: 'giant_fiber', rule: 'startle hop with both wings out when DNp01 fires' },
  ],
  pose(inp, prev, dt) {
    const p = idlePose()
    const k = 1 - Math.exp(-dt * 8)
    const deg = inp.readout['bump_deg'] ?? 180
    const epg = inp.readout['epg_hz'] ?? 0
    const gain = inp.readout['mb_gain'] ?? 1
    // ring angle -> head yaw, -50°..+50°, centred on C
    const yaw = ((((deg + 180) % 360) - 180) / 180) * 0.87
    p.headYaw = lerp(prev.headYaw, yaw, k)
    p.bodyPitch = lerp(prev.bodyPitch, -0.35 + clamp(epg / 40, 0, 1) * 0.25, k)
    p.bodyHeight = 0.2
    p.legs[0] = [0.95, -0.55, 1.1]; p.legs[3] = [0.95, -0.55, 1.1]   // forelegs over the keys
    if (inp.noteOn) {
      const press = Math.exp(-inp.noteAge * 10)
      p.legs[0][1] += 0.35 * press
      p.legs[3][1] += 0.35 * press
    }
    p.abdomenScale = lerp(prev.abdomenScale, 0.85 + 0.3 * clamp(gain - 0.5, 0, 1), k)
    common(inp, p, this as unknown as { until: number })
    return p
  },
}
;(pianoRig as unknown as { until: number }).until = 0

export const idleRig: Rig = {
  role: 'idle',
  rules: [{ joint: 'all', from: 'nothing', rule: 'standing; breathing only' }],
  pose(inp, _prev, _dt) { const p = idlePose(); common(inp, p, this as unknown as { until: number }); return p },
}
;(idleRig as unknown as { until: number }).until = 0

export function rigFor(role: string): Rig {
  return role === 'sax' ? saxRig : role === 'bass' ? bassRig : role === 'drums' ? drumsRig : role === 'piano' ? pianoRig : idleRig
}
