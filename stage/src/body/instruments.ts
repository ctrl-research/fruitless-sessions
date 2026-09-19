/** Instrument props. Static geometry the driven limbs land on. */

import * as THREE from 'three'

const BRASS = new THREE.MeshStandardMaterial({ color: 0xd4a33a, roughness: 0.3, metalness: 0.85 })
const DARK = new THREE.MeshStandardMaterial({ color: 0x2a2620, roughness: 0.6, metalness: 0.4 })

/** A small alto-ish saxophone standing on a stand, bell up and forward. */
export function saxophone(scale = 1): THREE.Group {
  const g = new THREE.Group()
  const pts = [
    new THREE.Vector3(0, 2.2, 0.55),      // mouthpiece, near the fly's head
    new THREE.Vector3(0, 1.9, 0.75),
    new THREE.Vector3(0, 1.1, 0.85),
    new THREE.Vector3(0, 0.35, 0.8),
    new THREE.Vector3(0, 0.15, 1.05),     // bow
    new THREE.Vector3(0, 0.55, 1.35),
    new THREE.Vector3(0, 1.25, 1.45),     // bell
  ].map(v => v.multiplyScalar(scale))
  const curve = new THREE.CatmullRomCurve3(pts)
  const tube = new THREE.Mesh(new THREE.TubeGeometry(curve, 40, 0.11 * scale, 10, false), BRASS)
  g.add(tube)
  const bell = new THREE.Mesh(new THREE.ConeGeometry(0.34 * scale, 0.55 * scale, 16, 1, true), BRASS)
  bell.position.copy(pts[6]).add(new THREE.Vector3(0, 0.25 * scale, 0.02 * scale))
  bell.rotation.x = -0.15
  g.add(bell)
  // keys
  for (let i = 0; i < 7; i++) {
    const key = new THREE.Mesh(new THREE.SphereGeometry(0.045 * scale, 8, 8), DARK)
    const t = 0.22 + i * 0.07
    const at = curve.getPoint(t)
    key.position.set(at.x + 0.11 * scale, at.y, at.z)
    g.add(key)
  }
  // mouthpiece
  const mp = new THREE.Mesh(new THREE.CylinderGeometry(0.05 * scale, 0.09 * scale, 0.3 * scale, 8), DARK)
  mp.position.copy(pts[0]).add(new THREE.Vector3(0, 0.1 * scale, -0.08 * scale))
  mp.rotation.x = 0.7
  g.add(mp)
  // stand
  const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.03 * scale, 0.03 * scale, 0.9 * scale, 6), DARK)
  stand.position.set(0, 0.45 * scale, 1.15 * scale)
  g.add(stand)
  const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.35 * scale, 0.35 * scale, 0.03 * scale, 16), DARK)
  foot.position.set(0, 0.015 * scale, 1.15 * scale)
  g.add(foot)
  return g
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
