/** Set dressing: a walnut stage and red velvet curtains, all procedural canvas textures. */

import * as THREE from 'three'

function canvas(size: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement('canvas')
  c.width = c.height = size
  return [c, c.getContext('2d')!]
}

/** Seeded value noise, smooth enough for grain and pleats. */
function noise1d(seed: number): (x: number) => number {
  const grid: number[] = []
  let s = seed
  const rnd = () => { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296 }
  for (let i = 0; i < 512; i++) grid.push(rnd())
  return (x: number) => {
    const i = Math.floor(x), f = x - i, a = grid[i & 511], b = grid[(i + 1) & 511]
    const t = f * f * (3 - 2 * f)
    return a + (b - a) * t
  }
}

/** Walnut: dark brown with lighter growth rings running across, warped by low-frequency noise. */
export function walnutTexture(size = 1024): THREE.CanvasTexture {
  const [c, ctx] = canvas(size)
  const img = ctx.createImageData(size, size)
  const warp = noise1d(7), fine = noise1d(11), knots = noise1d(23)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const u = x / size, v = y / size
      const w = (warp(v * 6) - 0.5) * 0.12 + (knots(u * 3 + v * 2) - 0.5) * 0.05
      const ring = Math.sin((u + w) * Math.PI * 2 * 22 + fine(v * 40) * 1.5)
      const g = 0.5 + 0.5 * ring
      const streak = fine(u * 200 + v * 3) * 0.12
      // walnut palette: from #3a2416 to #6b4a2e
      const r = 58 + (107 - 58) * (g * 0.8 + streak)
      const gg = 36 + (74 - 36) * (g * 0.8 + streak)
      const b = 22 + (46 - 22) * (g * 0.8 + streak)
      const i = (y * size + x) * 4
      img.data[i] = r; img.data[i + 1] = gg; img.data[i + 2] = b; img.data[i + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
  const tex = new THREE.CanvasTexture(c)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  return tex
}

/** Velvet: deep red with soft vertical pleats (shaded folds), a little nap noise. */
export function velvetTexture(size = 1024, pleats = 14): THREE.CanvasTexture {
  const [c, ctx] = canvas(size)
  const img = ctx.createImageData(size, size)
  const nap = noise1d(5), sway = noise1d(17)
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const u = x / size, v = y / size
      const fold = 0.5 + 0.5 * Math.cos((u * pleats + (sway(v * 3) - 0.5) * 0.15) * Math.PI * 2)
      const shade = 0.35 + 0.65 * Math.pow(fold, 1.6)          // deep shadow in the folds
      const n = 0.92 + 0.08 * nap(u * 300 + v * 900)
      const i = (y * size + x) * 4
      img.data[i] = 128 * shade * n
      img.data[i + 1] = 14 * shade * n
      img.data[i + 2] = 22 * shade * n
      img.data[i + 3] = 255
    }
  }
  ctx.putImageData(img, 0, 0)
  const tex = new THREE.CanvasTexture(c)
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping
  tex.colorSpace = THREE.SRGBColorSpace
  return tex
}

export function walnutMaterial(): THREE.MeshStandardMaterial {
  const map = walnutTexture()
  map.repeat.set(3, 3)
  return new THREE.MeshStandardMaterial({ map, roughness: 0.45, metalness: 0.05 })
}

/** A curved curtain wall behind the stage with a valance across the top. */
export function curtains(radius: number, height: number): THREE.Group {
  const g = new THREE.Group()
  const tex = velvetTexture(1024, 14)
  tex.repeat.set(4, 1)
  const velvet = new THREE.MeshStandardMaterial({
    map: tex, roughness: 0.95, metalness: 0.0, side: THREE.DoubleSide,
    emissive: new THREE.Color(0x2a0508), emissiveIntensity: 0.35,   // velvet reads as soft, never black
  })
  // the back wall: an arc of about 200° facing the audience
  const arc = new THREE.CylinderGeometry(radius, radius, height, 96, 1, true, -Math.PI * 0.55, Math.PI * 1.1)
  const wall = new THREE.Mesh(arc, velvet)
  wall.position.y = height / 2
  wall.rotation.y = Math.PI   // opening toward +Z, the audience
  g.add(wall)
  // valance: a shallow band along the top with tighter pleats
  const vtex = velvetTexture(512, 36)
  vtex.repeat.set(6, 1)
  const valance = new THREE.Mesh(
    new THREE.CylinderGeometry(radius * 0.985, radius * 0.985, height * 0.12, 96, 1, true, -Math.PI * 0.55, Math.PI * 1.1),
    new THREE.MeshStandardMaterial({ map: vtex, roughness: 0.95, side: THREE.DoubleSide, emissive: new THREE.Color(0x2a0508), emissiveIntensity: 0.35 }),
  )
  valance.position.y = height * 0.94
  valance.rotation.y = Math.PI
  g.add(valance)
  return g
}

/** An audience of fruit fly silhouettes: one FlyBody baked into a single geometry and drawn as
 *  an InstancedMesh, dark and unlit, facing the stage. No brains, no motion. */
export function audience(
  bodyFactory: () => THREE.Object3D, count: number, area: { xHalf: number; zNear: number; zFar: number },
  scale: number, floorY: number, seed = 3,
): THREE.InstancedMesh {
  const template = bodyFactory()
  template.updateMatrixWorld(true)
  const parts: THREE.BufferGeometry[] = []
  template.traverse(o => {
    const m = o as THREE.Mesh
    if (!m.isMesh || !m.geometry) return
    const g = (m.geometry.index ? m.geometry.toNonIndexed() : m.geometry.clone())
    for (const name of Object.keys(g.attributes)) if (name !== 'position') g.deleteAttribute(name)
    g.applyMatrix4(m.matrixWorld)
    parts.push(g)
  })
  // merge by hand: positions only
  let total = 0
  for (const g of parts) total += g.attributes.position.count
  const pos = new Float32Array(total * 3)
  let off = 0
  for (const g of parts) { pos.set(g.attributes.position.array as Float32Array, off); off += g.attributes.position.array.length }
  const merged = new THREE.BufferGeometry()
  merged.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  // per-instance greys so the crowd has some texture; the material's colour is the multiplier
  const mat = new THREE.MeshBasicMaterial({ color: 0xffffff })
  const mesh = new THREE.InstancedMesh(merged, mat, count)
  let s = seed
  const rnd = () => { s = (s * 1664525 + 1013904223) % 4294967296; return s / 4294967296 }
  const rows = Math.max(1, Math.round(Math.sqrt(count / 2.2)))
  const perRow = Math.ceil(count / rows)
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), v = new THREE.Vector3(), sc = new THREE.Vector3()
  const rest: { pos: THREE.Vector3; quat: THREE.Quaternion; scale: number; phase: number; every: number; amp: number }[] = []
  let i = 0
  for (let r = 0; r < rows && i < count; r++) {
    const z = area.zNear + (area.zFar - area.zNear) * (r + 0.5) / rows
    for (let c = 0; c < perRow && i < count; c++) {
      const x = -area.xHalf + (2 * area.xHalf) * (c + 0.5 + (r % 2) * 0.5) / (perRow + 0.5) + (rnd() - 0.5) * area.xHalf * 0.12
      const k = scale * (0.85 + rnd() * 0.3)
      v.set(x, floorY, z + (rnd() - 0.5) * (area.zFar - area.zNear) * 0.15)
      q.setFromEuler(new THREE.Euler(0, Math.PI + (rnd() - 0.5) * 0.5, 0))   // facing the stage
      sc.set(k, k, k)
      m4.compose(v, q, sc)
      mesh.setMatrixAt(i, m4)
      rest.push({ pos: v.clone(), quat: q.clone(), scale: k, phase: rnd(), every: rnd() < 0.5 ? 1 : 2, amp: 0.04 + rnd() * 0.06 })
      // nearer rows darker, with a spread of greys within each row
      const depth = (r + 0.5) / rows
      // shades of grey in sRGB up to a cap of #808080: the front row, nearest the lit stage, is
      // brightest and the rows fall off toward the back of the house
      const grey = Math.min(0.5, 0.5 - 0.4 * depth + (rnd() - 0.5) * 0.08)
      mesh.setColorAt(i, new THREE.Color().setRGB(grey, grey, grey, THREE.SRGBColorSpace))
      i++
    }
  }
  mesh.count = i
  mesh.instanceMatrix.needsUpdate = true
  if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  mesh.userData.rest = rest
  mesh.userData.unit = scale
  return mesh
}

/** Bob the crowd: each fly hops a few percent of a body on its own beats (every beat or every
 *  other), a sharp little jump rather than a sway. Call with the current time in beats. */
export function bobAudience(mesh: THREE.InstancedMesh, beats: number): void {
  const rest = mesh.userData.rest as { pos: THREE.Vector3; quat: THREE.Quaternion; scale: number; phase: number; every: number; amp: number }[] | undefined
  if (!rest) return
  const unit = mesh.userData.unit as number
  const m4 = new THREE.Matrix4(), v = new THREE.Vector3(), sc = new THREE.Vector3()
  for (let i = 0; i < rest.length; i++) {
    const r = rest[i]
    const b = beats + r.phase
    const hopBeat = Math.floor(b)
    const frac = b - hopBeat
    const hop = hopBeat % r.every === 0 && frac < 0.35 ? Math.sin((frac / 0.35) * Math.PI) : 0
    v.copy(r.pos); v.y += hop * r.amp * unit
    sc.setScalar(r.scale)
    m4.compose(v, r.quat, sc)
    mesh.setMatrixAt(i, m4)
  }
  mesh.instanceMatrix.needsUpdate = true
}
