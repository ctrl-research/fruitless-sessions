/** Instrument props. Static geometry the driven limbs land on. */

import * as THREE from 'three'

const BRASS = new THREE.MeshStandardMaterial({ color: 0xd4a33a, roughness: 0.3, metalness: 0.85 })
const DARK = new THREE.MeshStandardMaterial({ color: 0x2a2620, roughness: 0.6, metalness: 0.4 })
const WOOD = new THREE.MeshStandardMaterial({ color: 0x7a4a22, roughness: 0.55, metalness: 0.05 })
const SKIN = new THREE.MeshStandardMaterial({ color: 0xe8e2d0, roughness: 0.9 })
const CHROME = new THREE.MeshStandardMaterial({ color: 0xbfc4cc, roughness: 0.25, metalness: 0.9 })

/** A small alto-ish saxophone standing on a stand, bell up and forward. */
export function saxophone(scale = 1): THREE.Group {
  const g = new THREE.Group()
  const pts = [
    new THREE.Vector3(0, 2.2, 0.55), new THREE.Vector3(0, 1.9, 0.75), new THREE.Vector3(0, 1.1, 0.85),
    new THREE.Vector3(0, 0.35, 0.8), new THREE.Vector3(0, 0.15, 1.05), new THREE.Vector3(0, 0.55, 1.35),
    new THREE.Vector3(0, 1.25, 1.45),
  ].map(v => v.multiplyScalar(scale))
  const curve = new THREE.CatmullRomCurve3(pts)
  g.add(new THREE.Mesh(new THREE.TubeGeometry(curve, 40, 0.11 * scale, 10, false), BRASS))
  const bell = new THREE.Mesh(new THREE.ConeGeometry(0.34 * scale, 0.55 * scale, 16, 1, true), BRASS)
  bell.position.copy(pts[6]).add(new THREE.Vector3(0, 0.25 * scale, 0.02 * scale))
  bell.rotation.x = -0.15
  g.add(bell)
  for (let i = 0; i < 7; i++) {
    const key = new THREE.Mesh(new THREE.SphereGeometry(0.045 * scale, 8, 8), DARK)
    const at = curve.getPoint(0.22 + i * 0.07)
    key.position.set(at.x + 0.11 * scale, at.y, at.z)
    g.add(key)
  }
  const mp = new THREE.Mesh(new THREE.CylinderGeometry(0.05 * scale, 0.09 * scale, 0.3 * scale, 8), DARK)
  mp.position.copy(pts[0]).add(new THREE.Vector3(0, 0.1 * scale, -0.08 * scale))
  mp.rotation.x = 0.7
  g.add(mp)
  const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.03 * scale, 0.03 * scale, 0.9 * scale, 6), DARK)
  stand.position.set(0, 0.45 * scale, 1.15 * scale)
  g.add(stand)
  const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.35 * scale, 0.35 * scale, 0.03 * scale, 16), DARK)
  foot.position.set(0, 0.015 * scale, 1.15 * scale)
  g.add(foot)
  return g
}

/** An upright bass standing on its endpin beside the fly; the neck leans back toward the player. */
export function upright(scale = 1): THREE.Group {
  const g = new THREE.Group()
  const body = new THREE.Group()
  body.position.set(0, 1.6 * scale, 0.9 * scale)
  body.rotation.x = -0.25
  const lower = new THREE.Mesh(new THREE.SphereGeometry(0.75 * scale, 18, 12), WOOD)
  lower.scale.set(1, 1.05, 0.32)
  const upper = new THREE.Mesh(new THREE.SphereGeometry(0.58 * scale, 18, 12), WOOD)
  upper.scale.set(1, 1.0, 0.3)
  upper.position.y = 1.05 * scale
  body.add(lower, upper)
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.07 * scale, 0.09 * scale, 2.2 * scale, 8), DARK)
  neck.position.set(0, 2.6 * scale, 0.1 * scale)
  body.add(neck)
  const scroll = new THREE.Mesh(new THREE.TorusGeometry(0.12 * scale, 0.05 * scale, 8, 14), DARK)
  scroll.position.set(0, 3.75 * scale, 0.1 * scale)
  body.add(scroll)
  for (let i = 0; i < 4; i++) {
    const str = new THREE.Mesh(new THREE.CylinderGeometry(0.008 * scale, 0.008 * scale, 3.6 * scale, 4), CHROME)
    str.position.set((i - 1.5) * 0.06 * scale, 1.6 * scale, 0.22 * scale)
    body.add(str)
  }
  const bridge = new THREE.Mesh(new THREE.BoxGeometry(0.4 * scale, 0.12 * scale, 0.05 * scale), DARK)
  bridge.position.set(0, -0.1 * scale, 0.24 * scale)
  body.add(bridge)
  g.add(body)
  const endpin = new THREE.Mesh(new THREE.CylinderGeometry(0.03 * scale, 0.02 * scale, 0.9 * scale, 6), CHROME)
  endpin.position.set(0, 0.45 * scale, 1.1 * scale)
  g.add(endpin)
  return g
}

/** A small kit: kick, snare, hi-hat, ride, two toms, crash. Returns the group and the cymbal
 *  meshes so the rig can nudge them on hits. */
export function drumKit(scale = 1): { group: THREE.Group; hits: Record<string, THREE.Object3D> } {
  const g = new THREE.Group()
  const hits: Record<string, THREE.Object3D> = {}
  const drum = (r: number, h: number, x: number, y: number, z: number, tilt = 0) => {
    const d = new THREE.Group()
    const shell = new THREE.Mesh(new THREE.CylinderGeometry(r, r, h, 20, 1, true), WOOD)
    const head = new THREE.Mesh(new THREE.CircleGeometry(r, 20), SKIN)
    head.rotation.x = -Math.PI / 2
    head.position.y = h / 2
    d.add(shell, head)
    d.position.set(x, y, z)
    d.rotation.x = tilt
    g.add(d)
    return d
  }
  const cymbal = (r: number, x: number, y: number, z: number) => {
    const c = new THREE.Mesh(new THREE.ConeGeometry(r, r * 0.12, 24, 1, true), BRASS)
    c.position.set(x, y, z)
    const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.02 * scale, 0.02 * scale, y, 6), CHROME)
    stand.position.set(x, y / 2, z)
    g.add(c, stand)
    return c
  }
  // kick on its side facing the audience (+Z), the fly stands behind it
  const kick = new THREE.Group()
  const kshell = new THREE.Mesh(new THREE.CylinderGeometry(0.75 * scale, 0.75 * scale, 0.7 * scale, 24, 1, true), WOOD)
  const khead = new THREE.Mesh(new THREE.CircleGeometry(0.75 * scale, 24), SKIN)
  khead.position.z = 0.35 * scale
  kshell.rotation.x = Math.PI / 2
  kick.add(kshell, khead)
  kick.position.set(0, 0.8 * scale, 1.4 * scale)
  g.add(kick)
  hits.kick = khead
  hits.snare = drum(0.42 * scale, 0.3 * scale, -0.8 * scale, 1.15 * scale, 0.7 * scale, 0.15)
  hits.tom_hi = drum(0.32 * scale, 0.3 * scale, -0.35 * scale, 1.9 * scale, 1.1 * scale, 0.35)
  hits.tom_lo = drum(0.38 * scale, 0.36 * scale, 0.45 * scale, 1.85 * scale, 1.1 * scale, 0.35)
  hits.hat = cymbal(0.42 * scale, -1.35 * scale, 1.9 * scale, 0.6 * scale)
  hits.ride = cymbal(0.62 * scale, 1.35 * scale, 2.1 * scale, 0.9 * scale)
  hits.crash = cymbal(0.55 * scale, 0.9 * scale, 2.6 * scale, 1.6 * scale)
  return { group: g, hits }
}

/** A round riser for a band member to stand on. */
export function riser(radius: number): THREE.Mesh {
  const m = new THREE.Mesh(
    new THREE.CylinderGeometry(radius, radius * 1.05, radius * 0.12, 32),
    new THREE.MeshStandardMaterial({ color: 0x1a1a24, roughness: 0.9, metalness: 0.1 }),
  )
  m.position.y = -radius * 0.06
  return m
}

/** A small upright piano: case, keyboard with white and black keys, and a lid. The fly stands
 *  behind the keyboard facing the audience. */
export function piano(scale = 1): THREE.Group {
  const g = new THREE.Group()
  const CASE = new THREE.MeshStandardMaterial({ color: 0x1c1a1f, roughness: 0.35, metalness: 0.2 })
  const body = new THREE.Mesh(new THREE.BoxGeometry(2.6 * scale, 1.5 * scale, 0.9 * scale), CASE)
  body.position.set(0, 0.75 * scale, 1.25 * scale)
  g.add(body)
  const shelf = new THREE.Mesh(new THREE.BoxGeometry(2.6 * scale, 0.12 * scale, 0.5 * scale), CASE)
  shelf.position.set(0, 1.05 * scale, 0.75 * scale)
  g.add(shelf)
  const nWhite = 15
  const kw = (2.4 * scale) / nWhite
  for (let i = 0; i < nWhite; i++) {
    const k = new THREE.Mesh(new THREE.BoxGeometry(kw * 0.92, 0.06 * scale, 0.42 * scale), SKIN)
    k.position.set(-1.2 * scale + kw * (i + 0.5), 1.14 * scale, 0.72 * scale)
    g.add(k)
    if ([0, 1, 3, 4, 5].includes(i % 7)) {
      const b = new THREE.Mesh(new THREE.BoxGeometry(kw * 0.55, 0.08 * scale, 0.26 * scale), DARK)
      b.position.set(-1.2 * scale + kw * (i + 1.0), 1.19 * scale, 0.62 * scale)
      g.add(b)
    }
  }
  const lid = new THREE.Mesh(new THREE.BoxGeometry(2.6 * scale, 0.08 * scale, 0.95 * scale), CASE)
  lid.position.set(0, 1.55 * scale, 1.2 * scale)
  g.add(lid)
  return g
}
