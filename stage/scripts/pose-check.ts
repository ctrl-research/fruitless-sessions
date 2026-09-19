// Where do the legs and wings end up? Run: node --experimental-strip-types scripts/pose-check.ts
import * as THREE from 'three'
import { FlyBody, idlePose } from '../src/body/fly.ts'

const body = new FlyBody(1)
body.apply(idlePose(), 0)
body.group.updateMatrixWorld(true)
const tips = (body as unknown as { legs: { tarsusTip: THREE.Object3D; femur: THREE.Object3D; tibia: THREE.Object3D }[] }).legs
const names = ['fl_L', 'ml_L', 'hl_L', 'fl_R', 'ml_R', 'hl_R']
const v = new THREE.Vector3()
console.log('body centre y ≈ 0.75; leg tips should be at y ≈ 0 (the ground) and |x| > 0.3 (outside the body)')
tips.forEach((L, i) => {
  L.tarsusTip.getWorldPosition(v)
  const knee = new THREE.Vector3(); L.tibia.getWorldPosition(knee)
  console.log(`${names[i]}  tip x ${v.x.toFixed(2)} y ${v.y.toFixed(2)} z ${v.z.toFixed(2)}   knee x ${knee.x.toFixed(2)} y ${knee.y.toFixed(2)}`)
})
for (const w of ['wingL', 'wingR']) {
  const hinge = (body as unknown as Record<string, THREE.Group>)[w]
  hinge.getWorldPosition(v)
  console.log(`${w} hinge y ${v.y.toFixed(2)} (should be above the body centre, ~1.1)`)
}
