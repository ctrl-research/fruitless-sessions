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
