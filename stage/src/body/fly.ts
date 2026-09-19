/** A stylised fruit fly built from capsules and cylinders, posed each frame.
 *
 *  Body axis is +Z (head forward), up is +Y. Units are scene units: the body is
 *  about 3 long so it sits comfortably below a brain that is ~120 tall.
 *  Every joint is a THREE.Group whose rotation the rig sets from a Pose.
 */

import * as THREE from 'three'

export interface Pose {
  /** wing angle from the body, radians, per side (0 folded back, ~1.2 extended); L then R */
  wingExtend: [number, number]
  /** wing oscillation amplitude in radians (vibration around the extended angle) */
  wingFlap: number
  /** oscillation frequency in Hz (visual, not biological) */
  wingHz: number
  /** per leg [side L0..2, R0..2] joint angles: [coxa swing, femur lift, tibia bend] */
  legs: [number, number, number][]
  bodyHeight: number      // 0 = standing, +ve = jumping
  bodyPitch: number       // radians, +ve nose down
  bodyRoll: number
  antennae: number        // radians, twitch
  abdomenScale: number    // breathing
  proboscis: number       // 0 retracted .. 1 extended
  headYaw: number
}

export function idlePose(): Pose {
  return {
    wingExtend: [0.12, 0.12], wingFlap: 0, wingHz: 0,
    // [coxa swing (+ forward), femur drop below the coxa line, tibia fold back down toward the floor]
    legs: [
      [0.55, 0.15, 1.8], [0.0, 0.15, 1.8], [-0.55, 0.15, 1.8],
      [0.55, 0.15, 1.8], [0.0, 0.15, 1.8], [-0.55, 0.15, 1.8],
    ],
    bodyHeight: 0, bodyPitch: 0, bodyRoll: 0, antennae: 0, abdomenScale: 1, proboscis: 0.1, headYaw: 0,
  }
}

const MAT = {
  body: new THREE.MeshStandardMaterial({ color: 0x6b5a3e, roughness: 0.7, metalness: 0.05 }),
  thorax: new THREE.MeshStandardMaterial({ color: 0x8a6f45, roughness: 0.65 }),
  abdomen: new THREE.MeshStandardMaterial({ color: 0x4a3a24, roughness: 0.75 }),
  eye: new THREE.MeshStandardMaterial({ color: 0xc8352b, roughness: 0.35, emissive: 0x3a0a08 }),
  leg: new THREE.MeshStandardMaterial({ color: 0x3a2f1e, roughness: 0.8 }),
  wing: new THREE.MeshPhysicalMaterial({
    color: 0xcfd8ff, transparent: true, opacity: 0.35, roughness: 0.15, metalness: 0.0,
    side: THREE.DoubleSide, iridescence: 0.6, iridescenceIOR: 1.3, depthWrite: false,
  }),
}

function capsule(r: number, len: number, mat: THREE.Material): THREE.Mesh {
  const m = new THREE.Mesh(new THREE.CapsuleGeometry(r, len, 6, 12), mat)
  m.rotation.x = Math.PI / 2   // capsule along Z
  return m
}

function segment(r0: number, r1: number, len: number, mat: THREE.Material): THREE.Mesh {
  // cylinder along +Y from the origin (so a parent group rotation bends it at the joint)
  const g = new THREE.CylinderGeometry(r1, r0, len, 8)
  g.translate(0, len / 2, 0)
  return new THREE.Mesh(g, mat)
}

interface Leg { coxa: THREE.Group; femur: THREE.Group; tibia: THREE.Group; tarsusTip: THREE.Object3D }

export class FlyBody {
  readonly group = new THREE.Group()
  private body = new THREE.Group()
  private head = new THREE.Group()
  private abdomen!: THREE.Mesh
  private proboscis!: THREE.Mesh
  private antL!: THREE.Group
  private antR!: THREE.Group
  private wingL!: THREE.Group
  private wingR!: THREE.Group
  private legs: Leg[] = []
  private t = 0
  readonly scale: number

  constructor(scale = 1) {
    this.scale = scale
    this.group.add(this.body)
    this.body.position.y = 1.05 * scale

    // thorax
    const thorax = capsule(0.42 * scale, 0.5 * scale, MAT.thorax)
    thorax.position.z = 0.1 * scale
    this.body.add(thorax)
    // abdomen (behind, tapering)
    this.abdomen = new THREE.Mesh(new THREE.SphereGeometry(0.5 * scale, 14, 10), MAT.abdomen)
    this.abdomen.scale.set(0.8, 0.7, 1.5)
    this.abdomen.position.set(0, -0.08 * scale, -0.95 * scale)
    this.body.add(this.abdomen)
    // stripes
    for (let i = 0; i < 4; i++) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.36 * scale * (1 - i * 0.12), 0.025 * scale, 6, 20), MAT.body)
      ring.position.set(0, -0.08 * scale, (-0.75 - i * 0.22) * scale)
      ring.scale.set(1, 0.85, 1)
      this.body.add(ring)
    }
    // head
    this.head.position.set(0, 0.05 * scale, 0.72 * scale)
    this.body.add(this.head)
    const skull = new THREE.Mesh(new THREE.SphereGeometry(0.3 * scale, 14, 12), MAT.body)
    skull.scale.set(1.15, 1, 0.85)
    this.head.add(skull)
    for (const side of [-1, 1]) {
      const eye = new THREE.Mesh(new THREE.SphereGeometry(0.17 * scale, 12, 10), MAT.eye)
      eye.scale.set(0.8, 1.2, 0.9)
      eye.position.set(side * 0.24 * scale, 0.04 * scale, 0.08 * scale)
      this.head.add(eye)
    }
    // proboscis (down and forward)
    this.proboscis = segment(0.05 * scale, 0.035 * scale, 0.35 * scale, MAT.leg)
    this.proboscis.position.set(0, -0.2 * scale, 0.12 * scale)
    this.proboscis.rotation.x = Math.PI - 0.5
    this.head.add(this.proboscis)
    // antennae
    this.antL = this.antenna(scale, -1)
    this.antR = this.antenna(scale, 1)
    // wings: hinge at the top of the thorax, blade extends backwards (-Z) when folded
    this.wingL = this.wing(scale, -1)
    this.wingR = this.wing(scale, 1)
    // legs: three per side at z = +0.35, 0.05, -0.25
    const zs = [0.35, 0.05, -0.25]
    for (const side of [-1, 1]) {
      for (let i = 0; i < 3; i++) this.legs.push(this.leg(scale, side, zs[i] * scale))
    }
    this.group.traverse(o => { o.castShadow = false; o.receiveShadow = false })
  }

  private antenna(scale: number, side: number): THREE.Group {
    const g = new THREE.Group()
    g.position.set(side * 0.08 * scale, 0.18 * scale, 0.22 * scale)
    const shaft = segment(0.03 * scale, 0.02 * scale, 0.22 * scale, MAT.leg)
    shaft.rotation.set(-0.9, 0, side * 0.5)
    g.add(shaft)
    const arista = segment(0.012 * scale, 0.004 * scale, 0.28 * scale, MAT.leg)
    arista.position.set(side * 0.1 * scale, 0.14 * scale, 0.14 * scale)
    arista.rotation.set(-0.6, 0, side * 1.0)
    g.add(arista)
    this.head.add(g)
    return g
  }

  private wing(scale: number, side: number): THREE.Group {
    const hinge = new THREE.Group()
    hinge.position.set(side * 0.3 * scale, 0.38 * scale, 0.15 * scale)
    // blade: an ellipse in the XZ plane, long axis along -Z, hinge at one end
    const shape = new THREE.Shape()
    const L = 1.9 * scale, W = 0.42 * scale
    shape.moveTo(0, 0)
    shape.bezierCurveTo(side * W * 1.2, -L * 0.25, side * W, -L * 0.85, 0, -L)
    shape.bezierCurveTo(-side * W * 0.35, -L * 0.8, -side * W * 0.15, -L * 0.3, 0, 0)
    const geom = new THREE.ShapeGeometry(shape, 24)
    geom.rotateX(-Math.PI / 2)   // shape's (x, y) -> (x, -z)
    const blade = new THREE.Mesh(geom, MAT.wing)
    // veins
    const veins = new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 0, -L),
        new THREE.Vector3(0, 0, -L * 0.15), new THREE.Vector3(side * W * 0.9, 0, -L * 0.55),
        new THREE.Vector3(0, 0, -L * 0.35), new THREE.Vector3(side * W * 0.7, 0, -L * 0.8),
      ]),
      new THREE.LineBasicMaterial({ color: 0x9aa4c8, transparent: true, opacity: 0.5 }),
    )
    hinge.add(blade, veins)
    this.body.add(hinge)
    return hinge
  }

  private leg(scale: number, side: number, z: number): Leg {
    const coxa = new THREE.Group()
    coxa.position.set(side * 0.3 * scale, -0.15 * scale, z)
    const c = segment(0.06 * scale, 0.05 * scale, 0.25 * scale, MAT.leg)
    coxa.add(c)
    const femur = new THREE.Group()
    femur.position.y = 0.25 * scale
    const f = segment(0.05 * scale, 0.04 * scale, 0.75 * scale, MAT.leg)
    femur.add(f)
    coxa.add(femur)
    const tibia = new THREE.Group()
    tibia.position.y = 0.75 * scale
    const tb = segment(0.035 * scale, 0.025 * scale, 0.8 * scale, MAT.leg)
    tibia.add(tb)
    const tarsus = segment(0.022 * scale, 0.015 * scale, 0.45 * scale, MAT.leg)
    tarsus.position.y = 0.8 * scale
    tarsus.rotation.x = 0.5
    tibia.add(tarsus)
    femur.add(tibia)
    this.body.add(coxa)
    const tip = new THREE.Object3D()
    tip.position.y = 0.45 * scale
    tarsus.add(tip)
    return { coxa, femur, tibia, tarsusTip: tip }
  }

  /** Apply a pose; dt advances the wing oscillator. */
  apply(p: Pose, dt: number): void {
    this.t += dt
    const s = this.scale
    this.body.position.y = (1.05 + p.bodyHeight) * s
    this.body.rotation.set(p.bodyPitch, 0, p.bodyRoll)
    this.head.rotation.y = p.headYaw
    this.abdomen.scale.set(0.8 * p.abdomenScale, 0.7 * p.abdomenScale, 1.5)
    this.proboscis.scale.y = 0.4 + 0.9 * p.proboscis
    this.antL.rotation.z = -p.antennae
    this.antR.rotation.z = p.antennae
    const osc = p.wingFlap * Math.sin(2 * Math.PI * p.wingHz * this.t)
    // rotate wings out about the vertical axis from folded (blade along -Z) to extended (blade sideways)
    this.wingL.rotation.set(0, -p.wingExtend[0], osc * 0.4)
    this.wingL.rotation.x = osc
    this.wingR.rotation.set(0, p.wingExtend[1], -osc * 0.4)
    this.wingR.rotation.x = osc
    for (let i = 0; i < 6; i++) {
      const [swing, lift, bend] = p.legs[i]
      const side = i < 3 ? -1 : 1
      const L = this.legs[i]
      // coxa points outward and a little down (+Y of the segment -> (0.94·side, -0.34));
      // femur and tibia then fold downward toward the ground on that side. The old sign
      // pointed the coxa inward and up, which stood the fly on its back.
      L.coxa.rotation.set(-swing, 0, -side * (Math.PI / 2 + 0.35))
      L.femur.rotation.z = -side * lift
      L.tibia.rotation.z = -side * Math.abs(bend)
    }
  }
}
