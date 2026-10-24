// House models, part A: plants, furniture and decor, each built in code from simple shapes (no model files, no images).
// Every model is a function that returns a THREE.Group. Its origin is the middle of its footprint on the floor (y = 0 is the floor), its front faces +z, and it
// stays inside the w x d cells the catalog gives it (core/game/house.py) with a small margin. A model may set group.userData.tick = (t, dt) => {} for tiny life.
import { THREE, PAL, mat, box, cyl, cone, sphere, rbox, group, glow, pot } from "./house_kit.js";

const TAU = Math.PI * 2;
const gcache = new Map();
const geo = (key, make) => { let g = gcache.get(key); if (!g) { g = make(); gcache.set(key, g); } return g; };
const vec = (x, y, z) => new THREE.Vector3(x, y, z);
const UP = vec(0, 1, 0);
const bmats = new Map();
/** A material that ignores light (screens, glows) so it looks lit from inside. */
const bmat = (color, opts = {}) => { const k = color + JSON.stringify(opts); if (!bmats.has(k)) bmats.set(k, new THREE.MeshBasicMaterial({ color, ...opts })); return bmats.get(k); };
const seeded = (s) => () => { s = (s + 0x6D2B79F5) | 0; let t = Math.imul(s ^ (s >>> 15), 1 | s); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };

function put(m, x = 0, y = 0, z = 0) { m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; return m; }
const mesh = (g, color, x, y, z, opts) => put(new THREE.Mesh(g, mat(color, opts)), x, y, z);
/** A flat, self-lit mesh (no shadows): the picture on a screen, an LED. */
function lit(g, color, x = 0, y = 0, z = 0, opts) { const m = new THREE.Mesh(g, bmat(color, opts)); m.position.set(x, y, z); return m; }
/** A pane of glass or water: see-through, casts no shadow. */
function pane(w, h, d, color, opacity, x = 0, y = 0, z = 0) {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color, { transparent: true, opacity, depthWrite: false }));
  m.position.set(x, y + h / 2, z); m.receiveShadow = true; return m;
}
/** An egg or ball (radii rx, ry, rz) whose middle is at y. */
function blob(rx, ry, rz, color, x = 0, y = 0, z = 0, opts) {
  const small = Math.max(rx, ry, rz) < 0.1;
  const m = mesh(small ? geo("ballLow", () => new THREE.SphereGeometry(1, 10, 7)) : geo("ball", () => new THREE.SphereGeometry(1, 14, 10)), color, x, y, z, opts);
  m.scale.set(rx, ry, rz); return m;
}
/** The top half of an egg, flat underneath, standing on y. */
function dome(rx, ry, rz, color, x = 0, y = 0, z = 0, opts) {
  const m = mesh(geo("dome", () => new THREE.SphereGeometry(1, 16, 8, 0, TAU, 0, Math.PI / 2)), color, x, y, z, opts);
  m.scale.set(rx, ry, rz); return m;
}
/** A ring in the x/y plane (turn it with rx, ry, rz). */
function torus(R, r, color, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0, opts) {
  const m = mesh(geo(`tor${R}_${r}`, () => new THREE.TorusGeometry(R, r, 8, 24)), color, x, y, z, opts);
  m.rotation.set(rx, ry, rz); return m;
}
/** A stick from point a to point b ([x, y, z] each); rEnd is the radius at b. */
function rod(a, b, r, color, rEnd = r, seg = 8) {
  const A = vec(...a), B = vec(...b), d = B.clone().sub(A), len = d.length();
  const m = mesh(new THREE.CylinderGeometry(rEnd, r, len, seg), color);
  m.position.copy(A).add(B).multiplyScalar(0.5);
  m.quaternion.setFromUnitVectors(UP, d.normalize());
  return m;
}
/** A group at (x, y, z), turned by ry (around y) and then rx (leaning toward +z) and rz; the pivot for leaves, fronds and lids. */
function rig(x, y, z, ry, rx, kids, rz = 0) {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  g.rotation.order = "YXZ";
  g.rotation.set(rx, ry, rz);
  for (const k of [].concat(kids)) if (k) g.add(k);
  return g;
}
/** A turned vase or bowl from a [radius, height] profile. */
function lathe(profile, color, x = 0, y = 0, z = 0, seg = 20) {
  return mesh(new THREE.LatheGeometry(profile.map(([r, h]) => new THREE.Vector2(r, h)), seg), color, x, y, z, { side: THREE.DoubleSide });
}
const turn = (m, rx = 0, ry = 0, rz = 0) => { m.rotation.set(rx, ry, rz); return m; };
function extrude(shp, depth, color, x = 0, y = 0, z = 0, bevel = 0, opts) {
  const g = new THREE.ExtrudeGeometry(shp, { depth, bevelEnabled: bevel > 0, bevelSize: bevel, bevelThickness: bevel, bevelSegments: 1, curveSegments: 8 });
  return mesh(g, color, x, y, z, opts);
}
/** A pointed leaf in the x/y plane: base at the origin, tip at (0, len), half-width about wid. */
const leafGeo = (len, wid, depth = 0.02) => geo(`leaf${len}_${wid}_${depth}`, () => {
  const s = new THREE.Shape();
  s.moveTo(0, 0); s.quadraticCurveTo(wid * 2, len * 0.45, 0, len); s.quadraticCurveTo(-wid * 2, len * 0.45, 0, 0);
  return new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: false, curveSegments: 6 });
});
/** A feathery frond with a saw-tooth edge, pointing up the y axis. */
const frondGeo = (len, wid, teeth, depth = 0.016) => geo(`frond${len}_${wid}_${teeth}_${depth}`, () => {
  const prof = (t) => wid * (1 - t * t) * Math.min(1, 0.35 + 3 * t);
  const right = [];
  for (let i = 0; i < teeth; i++) { const t0 = i / teeth, t1 = (i + 0.75) / teeth; right.push([prof(t0) * 0.3, len * t0], [prof(t1), len * t1]); }
  const pts = [...right, [0, len], ...right.slice().reverse().map(([x, y]) => [-x, y])];
  const s = new THREE.Shape(pts.map(([x, y]) => new THREE.Vector2(x, y)));
  return new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: false });
});
/** A leaf that bends: two parts, the second leaning further out (t2 more than t1). Pivot at its base, standing in the x/y plane leaning toward +z. */
function arch(kind, len, wid, t1, t2, color, teeth = 5) {
  const mk = (l, w) => (kind === "frond" ? frondGeo(l, w, teeth) : leafGeo(l, w));
  const seg2 = rig(0, len * 0.5, 0, 0, t2 - t1, mesh(mk(len * 0.5, wid * 0.85), color));
  return rig(0, 0, 0, 0, t1, [mesh(mk(len * 0.52, wid), color), seg2]);
}
/** Let the green part of a plant sway a few degrees. */
function sway(root, part, amp = 0.03, speed = 1.3) {
  const ph = Math.random() * TAU;
  root.userData.tick = (t) => { part.rotation.z = Math.sin(t * speed + ph) * amp; part.rotation.x = Math.cos(t * speed * 0.8 + ph) * amp * 0.6; };
}
function mug(color, x, y, z, ry = 0) {
  return rig(x, y, z, ry, 0, [cyl(0.065, 0.055, 0.11, color), cyl(0.05, 0.05, 0.01, "#5B3B2A", 0, 0.1), torus(0.038, 0.012, color, 0.075, 0.055, 0)]);
}
const BOOKS = [PAL.plum, PAL.red, PAL.teal, PAL.yellow, PAL.blue, PAL.orange, PAL.green, PAL.pink, PAL.navy, PAL.plumLight];

// ---------------------------------------------------------------------------------------------------------------- plants (1 x 1)

function succulent() {
  const top = 0.25, f = new THREE.Group();
  f.position.y = top;
  const rings = [[10, 1.15, 0.2, 0.08, PAL.leaf, 0.09, 0.02], [8, 0.82, 0.2, 0.075, PAL.leafLight, 0.06, 0.05], [6, 0.5, 0.18, 0.07, PAL.leaf, 0.035, 0.08], [4, 0.2, 0.15, 0.06, PAL.leafLight, 0.015, 0.1]];
  rings.forEach(([n, tilt, len, w, col, r, y], k) => {
    for (let i = 0; i < n; i++) {
      const a = ((i + (k % 2) * 0.5) / n) * TAU;
      f.add(rig(Math.sin(a) * r, y, Math.cos(a) * r, a, tilt, blob(w, len / 2, w * 0.55, col, 0, len / 2, 0)));
    }
  });
  const bloom = new THREE.Group();
  bloom.position.set(0.02, 0.38, 0);
  bloom.add(sphere(0.03, PAL.yellow, 0, 0, 0, 1, 10));
  for (let i = 0; i < 5; i++) { const a = (i / 5) * TAU; bloom.add(blob(0.04, 0.022, 0.04, PAL.pink, Math.sin(a) * 0.05, -0.005, Math.cos(a) * 0.05)); }
  f.add(rod([0, 0.1, 0], [0.02, 0.37, 0], 0.012, PAL.leafDark), bloom);
  const root = group(pot(PAL.potLight, 0.25, top), f);
  sway(root, f, 0.025);
  return root;
}

function fern() {
  const top = 0.27, f = new THREE.Group();
  f.position.y = top;
  const cols = [PAL.leaf, PAL.leafDark, PAL.leafLight];
  for (let i = 0; i < 9; i++) {
    const a = (i / 9) * TAU + (i % 2) * 0.12;
    f.add(rig(0, 0.04, 0, a, 0, arch("frond", 0.5 + (i % 3) * 0.04, 0.1, i % 2 ? 0.75 : 0.45, i % 2 ? 1.5 : 1.25, cols[i % 3], 6)));
  }
  for (let i = 0; i < 4; i++) f.add(rig(0, 0.05, 0, 1 + i * 1.6, 0, arch("frond", 0.5, 0.08, 0.2, 0.55, i % 2 ? PAL.leafLight : PAL.leaf, 6)));
  f.add(blob(0.13, 0.1, 0.13, PAL.leafDark, 0, 0.1, 0));
  const root = group(pot(PAL.pot, 0.25, top), f);
  sway(root, f, 0.03);
  return root;
}

function bamboo() {
  const top = 0.3, f = new THREE.Group();
  f.position.y = top;
  const stalks = [[0.0, 0.0, 1.35, 0.0, 0.0], [0.1, 0.05, 1.05, 0.05, 0.03], [-0.1, 0.04, 1.2, -0.07, 0.03], [0.03, -0.1, 0.85, 0.02, -0.06], [-0.04, 0.11, 0.7, -0.03, 0.08]];
  stalks.forEach(([x, z, h, dx, dz], k) => {
    const A = [x, 0, z], B = [x + dx, h, z + dz];
    f.add(rod(A, B, 0.04, k % 2 ? PAL.leaf : PAL.leafLight, 0.032));
    for (let n = 1; n * 0.22 < h - 0.05; n++) { const t = (n * 0.22) / h; f.add(blob(0.05, 0.016, 0.05, PAL.leafDark, x + dx * t, n * 0.22, z + dz * t)); }
    if (k < 3) for (let j = 0; j < 3; j++) f.add(rig(x + dx, h - 0.02, z + dz, (j / 3) * TAU + k, 1.0 + j * 0.15, mesh(leafGeo(0.3, 0.05, 0.012), j % 2 ? PAL.leaf : PAL.leafDark)));
  });
  f.add(torus(0.13, 0.02, PAL.red, 0, 0.45, 0, Math.PI / 2, 0, 0));
  f.add(blob(0.04, 0.03, 0.025, PAL.red, 0.1, 0.45, 0.09), turn(blob(0.06, 0.016, 0.02, PAL.red, 0.17, 0.4, 0.1), 0, 0, 0.7), turn(blob(0.06, 0.016, 0.02, PAL.red, 0.14, 0.38, 0.14), 0, 0, -0.5));
  const base = group(cyl(0.22, 0.18, 0.28, PAL.white), cyl(0.25, 0.22, 0.05, PAL.lilac, 0, 0.26), torus(0.19, 0.01, PAL.plumLight, 0, 0.14, 0, Math.PI / 2, 0, 0), cyl(0.21, 0.21, 0.02, "#5B3B2A", 0, 0.29));
  const root = group(base, f);
  const rn = seeded(3);
  for (let i = 0; i < 9; i++) { const a = rn() * TAU, r = 0.08 + rn() * 0.12; root.add(blob(0.04, 0.025, 0.04, i % 3 ? PAL.white : PAL.greyLight, Math.sin(a) * r, 0.31, Math.cos(a) * r)); }
  sway(root, f, 0.02);
  return root;
}

const monsteraLeaf = (s) => geo(`monstera${s}`, () => {
  const sh = new THREE.Shape();
  sh.moveTo(0, 0.04); sh.bezierCurveTo(0.08, -0.06, 0.27, 0.0, 0.27, 0.2); sh.bezierCurveTo(0.27, 0.4, 0.1, 0.5, 0, 0.58);
  sh.bezierCurveTo(-0.1, 0.5, -0.27, 0.4, -0.27, 0.2); sh.bezierCurveTo(-0.27, 0.0, -0.08, -0.06, 0, 0.04);
  for (const sx of [-1, 1]) for (const [hx, hy, hr] of [[0.13, 0.13, 0.04], [0.15, 0.28, 0.04], [0.09, 0.42, 0.03]]) {
    const h = new THREE.Path(); h.absellipse(sx * hx, hy, hr, hr * 1.4, 0, TAU, false, sx * 0.5); sh.holes.push(h);
  }
  const g = new THREE.ExtrudeGeometry(sh, { depth: 0.02, bevelEnabled: false, curveSegments: 8 });
  g.scale(s, s, 1);
  return g;
});

function monstera() {
  const top = 0.27, f = new THREE.Group();
  f.position.y = top;
  // yaw, lean from upright, size, how far out the stalk ends, how high, colour
  const leaves = [[0.35, 1.3, 0.62, 0.07, 0.5, PAL.leaf], [1.65, 1.38, 0.6, 0.06, 0.74, PAL.leafDark], [2.85, 1.25, 0.62, 0.07, 0.4, PAL.leafLight], [3.95, 1.4, 0.58, 0.06, 0.66, PAL.leaf], [5.15, 1.3, 0.6, 0.06, 0.9, PAL.leafDark], [0.9, 0.55, 0.5, 0.02, 0.95, PAL.leafLight]];
  for (const [yaw, tilt, s, rr, hy, col] of leaves) {
    const bx = Math.sin(yaw) * rr, bz = Math.cos(yaw) * rr;
    f.add(rod([0, 0, 0], [bx, hy, bz], 0.024, PAL.leafDark, 0.016));
    f.add(rig(bx, hy, bz, yaw, tilt, [mesh(monsteraLeaf(s), col, 0, 0, -0.01), box(0.014, 0.52 * s, 0.03, PAL.leafDark, 0, 0.04, -0.005)]));
  }
  const root = group(pot(PAL.plumLight, 0.25, top), f);
  sway(root, f, 0.02);
  return root;
}

function orchid() {
  const top = 0.24, f = new THREE.Group();
  f.position.y = top;
  const cols = [PAL.leaf, PAL.leafDark, PAL.leaf, PAL.leafDark];
  for (let i = 0; i < 4; i++) f.add(rig(0, 0.03, 0, i * 1.6 + 0.4, 0, arch("leaf", 0.5, 0.072, 0.95, 1.65, cols[i])));
  const curve = new THREE.CatmullRomCurve3([vec(0, 0.02, 0), vec(0, 0.4, 0), vec(0.03, 0.7, 0.01), vec(0.12, 0.96, 0.03), vec(0.26, 1.08, 0.05), vec(0.38, 1.05, 0.05)]);
  const pts = curve.getPoints(8);
  for (let i = 0; i < pts.length - 1; i++) f.add(rod(pts[i].toArray(), pts[i + 1].toArray(), 0.014, PAL.leafDark));
  for (const t of [0.42, 0.57, 0.72, 0.88]) {
    const p = curve.getPoint(t), s = 0.8 + (1 - t) * 0.7;
    const fl = new THREE.Group();
    fl.position.set(p.x, p.y, p.z + 0.02);
    fl.rotation.set(-0.35, 0.25, 0);
    fl.scale.setScalar(s);
    const petal = "#F4B3D2";
    fl.add(blob(0.075, 0.065, 0.012, petal, 0.065, 0.01, 0), blob(0.075, 0.065, 0.012, petal, -0.065, 0.01, 0), blob(0.045, 0.07, 0.012, PAL.white, 0, 0.065, -0.004));
    fl.add(turn(blob(0.04, 0.065, 0.012, PAL.white, 0.045, -0.055, -0.004), 0, 0, 0.5), turn(blob(0.04, 0.065, 0.012, PAL.white, -0.045, -0.055, -0.004), 0, 0, -0.5));
    fl.add(blob(0.032, 0.04, 0.016, PAL.pink, 0, -0.015, 0.012), sphere(0.014, PAL.yellow, 0, 0.01, 0.022, 1, 8));
    f.add(fl);
  }
  f.add(sphere(0.035, PAL.pink, 0.4, 1.02, 0.05, 1.3, 8), sphere(0.025, PAL.leafLight, 0.43, 0.97, 0.05, 1.3, 8));
  const root = group(pot(PAL.white, 0.2, 0.24), cyl(0.2, 0.2, 0.012, PAL.plumLight, 0, 0.12), f);
  sway(root, f, 0.025);
  return root;
}

function palm() {
  const top = 0.32;
  const root = group(pot(PAL.clay, 0.27, top));
  const plant = new THREE.Group();
  plant.position.y = top - 0.02;
  const n = 5;
  for (let i = 0; i < n; i++) {
    const y = i * 0.19;
    plant.add(cyl(0.075 - i * 0.004, 0.085 - i * 0.004, 0.21, i % 2 ? PAL.wood : PAL.woodDark, Math.sin(i * 0.6) * 0.04, y, 0, 10));
  }
  const crown = new THREE.Group();
  crown.position.set(Math.sin(n * 0.6) * 0.04, n * 0.19, 0);
  const tilts = [0.35, 0.95, 0.65, 1.0, 0.45, 0.8, 0.6, 1.05, 0.5, 0.85];
  for (let i = 0; i < 10; i++) {
    const t = tilts[i];
    crown.add(rig(0, 0, 0, (i / 10) * TAU, 0, arch("frond", 0.47, 0.15, t, t + 0.5, i % 3 === 1 ? PAL.leafDark : i % 3 === 2 ? PAL.leafLight : PAL.leaf, 7)));
  }
  for (let i = 0; i < 4; i++) crown.add(rig(0, 0, 0, i * 1.6 + 0.5, 0, arch("frond", 0.5, 0.11, 0.1, 0.3, i % 2 ? PAL.leaf : PAL.leafLight, 6)));
  for (let i = 0; i < 3; i++) crown.add(sphere(0.07, i === 1 ? PAL.wood : PAL.woodDark, Math.sin(i * 2.1 + 0.5) * 0.1, -0.05, Math.cos(i * 2.1 + 0.5) * 0.1, 1, 10));
  plant.add(crown);
  root.add(plant);
  sway(root, plant, 0.012, 1.0);
  return root;
}

function bonsai() {
  const root = group(rbox(0.74, 0.1, 0.52, 0.04, PAL.woodDark), box(0.6, 0.04, 0.38, PAL.wood, 0, 0.1));
  root.add(rbox(0.7, 0.16, 0.48, 0.07, PAL.teal, 0, 0.1), rbox(0.74, 0.04, 0.52, 0.02, PAL.teal, 0, 0.24), box(0.62, 0.02, 0.4, "#5B3B2A", 0, 0.27));
  const f = new THREE.Group();
  f.position.y = 0.28;
  f.add(dome(0.34, 0.015, 0.2, PAL.leafLight, -0.04, 0, 0.02));
  f.add(cone(0.13, 0.14, PAL.woodDark, 0, 0, 0, 10));
  const spine = [[0, 0.05, 0], [-0.05, 0.2, 0.02], [0.03, 0.35, -0.02], [-0.02, 0.5, 0.0]];
  for (let i = 0; i < spine.length - 1; i++) f.add(rod(spine[i], spine[i + 1], 0.062 - i * 0.012, i % 2 ? PAL.wood : PAL.woodDark, 0.05 - i * 0.012));
  f.add(rod([0.0, 0.3, 0], [0.2, 0.34, 0.07], 0.03, PAL.woodDark, 0.022), rod([-0.04, 0.22, 0], [-0.2, 0.28, -0.04], 0.028, PAL.woodDark, 0.02));
  f.add(blob(0.3, 0.14, 0.25, PAL.leaf, -0.02, 0.58, 0), blob(0.22, 0.1, 0.2, PAL.leafDark, 0.24, 0.42, 0.07), blob(0.18, 0.09, 0.16, PAL.leafDark, -0.24, 0.36, -0.04));
  f.add(blob(0.2, 0.08, 0.18, PAL.leafLight, 0.0, 0.7, 0.03), blob(0.13, 0.06, 0.12, PAL.leaf, 0.26, 0.5, 0.1), blob(0.11, 0.05, 0.1, PAL.leaf, -0.25, 0.43, -0.02));
  for (const [x, y, z] of [[0.1, 0.66, 0.2], [-0.2, 0.62, 0.14], [0.3, 0.46, 0.18], [-0.05, 0.78, 0.1], [-0.3, 0.4, 0.07]]) f.add(sphere(0.03, PAL.pink, x, y, z, 1, 8));
  f.add(blob(0.07, 0.05, 0.06, PAL.grey, 0.25, 0.02, 0.12), blob(0.04, 0.03, 0.04, PAL.greyLight, 0.31, 0.02, 0.05));
  root.add(f);
  sway(root, f, 0.015, 0.9);
  return root;
}

// ---------------------------------------------------------------------------------------------------------------- furniture

const FEET = [[1, 1], [-1, 1], [1, -1], [-1, -1]];

function stool() {
  const seatY = 0.36, g = group();
  for (const [sx, sz] of FEET) g.add(rod([sx * 0.22, 0, sz * 0.22], [sx * 0.15, seatY, sz * 0.15], 0.04, PAL.wood, 0.032));
  g.add(torus(0.185, 0.02, PAL.woodDark, 0, 0.16, 0, Math.PI / 2));
  g.add(cyl(0.3, 0.28, 0.06, PAL.woodDark, 0, seatY - 0.03), cyl(0.29, 0.3, 0.1, PAL.plum, 0, seatY + 0.03), dome(0.29, 0.07, 0.29, PAL.plumLight, 0, seatY + 0.13), sphere(0.025, PAL.plumDark, 0, seatY + 0.2, 0, 1, 8));
  return g;
}

function beanbag() {
  const c = PAL.teal, light = "#3DBDBD", dark = "#238A8A";
  const g = group(dome(0.44, 0.28, 0.42, c), blob(0.38, 0.34, 0.22, c, 0, 0.32, -0.2), blob(0.3, 0.14, 0.26, light, 0, 0.3, 0.06));
  g.add(torus(0.06, 0.014, dark, 0, 0.67, -0.24, 0.35), turn(rbox(0.26, 0.26, 0.1, 0.1, PAL.yellow, 0.14, 0.4, -0.02), -0.45, 0.15, 0.25));
  return g;
}

function armchair() {
  const c = PAL.yellow, c2 = PAL.cream, g = group();
  for (const [sx, sz] of FEET) g.add(cyl(0.06, 0.04, 0.16, PAL.woodDark, sx * 0.7, 0, sz * 0.7, 10));
  g.add(rbox(1.8, 0.36, 1.76, 0.12, c, 0, 0.14, 0), rbox(1.8, 1.0, 0.5, 0.22, c, 0, 0.14, -0.65));
  for (const sx of [-1, 1]) g.add(rbox(0.38, 0.62, 1.5, 0.17, c, sx * 0.71, 0.14, 0.12));
  g.add(rbox(1.0, 0.24, 1.06, 0.1, c2, 0, 0.48, 0.2), turn(rbox(1.0, 0.62, 0.26, 0.12, c2, 0, 0.52, -0.28), -0.2, 0, 0));
  g.add(turn(rbox(0.44, 0.44, 0.15, 0.15, PAL.plum, 0.3, 0.62, -0.1), 0.1, 0.3, 0.35));
  return g;
}

function sofa() {
  const c = PAL.plum, c2 = PAL.plumLight, g = group();
  for (const [sx, sz] of FEET) g.add(cyl(0.07, 0.05, 0.16, PAL.woodDark, sx * 1.72, 0, sz * 0.66, 10));
  g.add(rbox(3.84, 0.36, 1.74, 0.12, c, 0, 0.14, 0.03), rbox(3.84, 1.0, 0.5, 0.22, c, 0, 0.14, -0.66));
  for (const sx of [-1, 1]) g.add(rbox(0.4, 0.64, 1.5, 0.17, c, sx * 1.72, 0.14, 0.14));
  for (const sx of [-1, 1]) {
    g.add(rbox(1.5, 0.26, 1.1, 0.11, c2, sx * 0.77, 0.48, 0.18));
    g.add(turn(rbox(1.5, 0.64, 0.28, 0.12, c2, sx * 0.77, 0.52, -0.3), -0.2, 0, 0));
  }
  g.add(turn(rbox(0.46, 0.46, 0.15, 0.15, PAL.yellow, -1.2, 0.62, -0.02), 0.15, 0.35, 0.3), turn(rbox(0.46, 0.46, 0.15, 0.15, PAL.teal, 1.2, 0.62, -0.02), 0.15, -0.3, -0.25));
  return g;
}

function coffeeTable() {
  const g = group();
  g.add(rbox(1.8, 0.09, 0.86, 0.04, PAL.woodLight, 0, 0.4, 0), box(1.5, 0.035, 0.5, PAL.wood, 0, 0.12, 0));
  for (const [sx, sz] of FEET) g.add(box(0.1, 0.4, 0.1, PAL.woodDark, sx * 0.78, 0, sz * 0.3));
  g.add(turn(rbox(0.5, 0.06, 0.34, 0.03, PAL.pink, -0.3, 0.155, 0), 0, 0.12, 0), turn(rbox(0.46, 0.06, 0.32, 0.03, PAL.plumLight, -0.3, 0.215, 0), 0, -0.1, 0));
  g.add(turn(rbox(0.46, 0.06, 0.32, 0.02, PAL.plum, -0.55, 0.49, 0), 0, 0.2, 0), turn(rbox(0.4, 0.05, 0.3, 0.02, PAL.yellow, -0.55, 0.55, 0), 0, -0.15, 0), turn(rbox(0.32, 0.045, 0.24, 0.02, PAL.cream, -0.55, 0.6, 0), 0, 0.3, 0));
  g.add(mug(PAL.red, 0.15, 0.49, 0.14, 0.5));
  g.add(rig(0.6, 0.49, -0.04, 0, 0, [pot(PAL.potLight, 0.11, 0.1), dome(0.1, 0.1, 0.1, PAL.leaf, 0, 0.1), dome(0.06, 0.08, 0.06, PAL.leafLight, 0.02, 0.15), sphere(0.025, PAL.pink, 0.02, 0.255, 0.02, 1, 8)]));
  return g;
}

function chair(x, z, ry, seat) {
  const g = rig(x, 0, z, ry, 0, [rbox(0.5, 0.09, 0.5, 0.04, seat, 0, 0.36, 0), rbox(0.5, 0.5, 0.07, 0.05, PAL.wood, 0, 0.45, -0.22)]);
  for (const [sx, sz] of FEET) g.add(box(0.06, 0.36, 0.06, PAL.woodDark, sx * 0.2, 0, sz * 0.2));
  return g;
}

function diningTable() {
  const g = group();
  g.add(rbox(2.0, 0.1, 1.2, 0.04, PAL.wood, 0, 0.68, 0));
  for (const [sx, sz] of FEET) g.add(box(0.13, 0.68, 0.13, PAL.woodDark, sx * 0.86, 0, sz * 0.46));
  g.add(box(1.7, 0.012, 0.34, PAL.plum, 0, 0.78, 0));
  g.add(cyl(0.2, 0.12, 0.1, PAL.teal, 0, 0.79));
  for (const [x, y, z, c] of [[-0.06, 0.93, 0.02, PAL.red], [0.07, 0.93, -0.03, PAL.orange], [0.0, 0.92, 0.08, PAL.yellow], [0.02, 1.0, -0.01, PAL.green]]) g.add(sphere(0.075, c, x, y, z, 1, 12));
  for (const sx of [-1, 1]) { g.add(cyl(0.15, 0.14, 0.018, PAL.white, sx * 0.55, 0.78, -0.3), cyl(0.09, 0.09, 0.02, PAL.cream, sx * 0.55, 0.796, -0.3)); g.add(mug(sx > 0 ? PAL.blue : PAL.orange, sx * 0.78, 0.78, -0.3, sx)); }
  g.add(chair(-0.48, -0.7, 0, PAL.plumLight), chair(0.48, -0.7, 0, PAL.plumLight), chair(-1.2, 0, Math.PI / 2, PAL.plum), chair(1.2, 0, -Math.PI / 2, PAL.plum));
  return g;
}

function desk() {
  const g = group();
  g.add(rbox(2.84, 0.1, 0.84, 0.04, PAL.woodLight, 0, 0.7, 0), rbox(0.8, 0.7, 0.76, 0.05, PAL.wood, -1.0, 0, 0), box(0.1, 0.7, 0.76, PAL.wood, 1.32, 0, 0), box(1.5, 0.4, 0.04, PAL.woodDark, 0.1, 0.3, -0.34));
  [0.07, 0.29, 0.51].forEach((y, i) => g.add(box(0.7, 0.19, 0.02, PAL.cream, -1.0, y + 0.02, 0.38), box(0.2, 0.03, 0.04, i % 2 ? PAL.plum : PAL.gold, -1.0, y + 0.1, 0.4)));
  // laptop
  g.add(rbox(0.62, 0.04, 0.42, 0.02, PAL.greyLight, 0.35, 0.8, 0.02));
  const lid = rig(0.35, 0.84, -0.17, 0, -0.28, [rbox(0.62, 0.42, 0.03, 0.03, PAL.charcoal, 0, 0, 0), lit(new THREE.PlaneGeometry(0.54, 0.34), "#BFE3F5", 0, 0.21, 0.017), lit(new THREE.PlaneGeometry(0.54, 0.05), PAL.plumLight, 0, 0.355, 0.019), lit(new THREE.PlaneGeometry(0.3, 0.04), PAL.plum, -0.09, 0.22, 0.019), lit(new THREE.PlaneGeometry(0.4, 0.04), PAL.green, -0.04, 0.12, 0.019)]);
  g.add(lid);
  g.add(mug(PAL.pink, -0.35, 0.8, 0.12, 0.6), turn(box(0.34, 0.025, 0.44, PAL.plum, 0.0, 0.8, 0.0), 0, 0.2, 0));
  g.add(turn(box(0.3, 0.02, 0.4, PAL.cream, 0.0, 0.825, 0.0), 0, 0.2, 0), turn(box(0.2, 0.014, 0.014, PAL.yellow, 0.0, 0.85, 0.04), 0, 0.5, 0));
  // desk lamp
  g.add(cyl(0.1, 0.11, 0.03, PAL.plum, 1.08, 0.8, -0.2), rod([1.08, 0.83, -0.2], [1.0, 1.1, -0.2], 0.018, PAL.plumDark), rod([1.0, 1.1, -0.2], [1.12, 1.28, -0.2], 0.018, PAL.plumDark));
  g.add(rig(1.12, 1.28, -0.2, 0, 0, turn(cyl(0.03, 0.11, 0.13, PAL.yellow, 0, -0.1, 0), 0, 0, 0.3)), glow(0.05, "#FFF1B8", 1.1, 1.14, -0.2, 0.8));
  return g;
}

function shelfBooks(g, x0, y, specs, z = 0.03) {
  let x = x0;
  for (const [w, h, c, lean = 0] of specs) {
    x += w / 2;
    g.add(rig(x, y, z, 0, 0, box(w, h, 0.34, c, 0, 0, 0), lean));
    x += w / 2 + 0.008 + (lean ? Math.abs(Math.sin(lean)) * h * 0.55 : 0);
  }
  return x;
}

function bookshelf() {
  const g = group(), W = 1.9, D = 0.5, H = 2.2, T = 0.07;
  for (const sx of [-1, 1]) g.add(box(T, H, D, PAL.woodDark, sx * (W / 2 - T / 2), 0, 0));
  g.add(box(W + 0.02, T, D + 0.02, PAL.wood, 0, H - T, 0), box(W - 2 * T, 0.12, D - 0.02, PAL.woodDark, 0, 0, 0), box(W - 2 * T, H - 0.14, 0.03, PAL.plumLight, 0, 0.1, -D / 2 + 0.02));
  const boards = [0.12, 0.54, 0.96, 1.38, 1.8];
  for (const y of boards) g.add(box(W - 2 * T, 0.045, D - 0.04, PAL.wood, 0, y, 0.0));
  const y0 = boards.map((y) => y + 0.045), L = -0.86;
  const [P, R, T2, Y, B, O, Gn, Pk, N, PL] = BOOKS;
  shelfBooks(g, L, y0[0], [[0.1, 0.32, P], [0.08, 0.28, Y], [0.12, 0.33, T2], [0.1, 0.3, B]]);
  g.add(rbox(0.5, 0.22, 0.36, 0.06, PAL.woodLight, 0.58, y0[0], 0.03), box(0.4, 0.012, 0.28, "#5B3B2A", 0.58, y0[0] + 0.21, 0.03));
  g.add(rig(-0.62, y0[1], 0.03, 0, 0, [pot(PAL.potLight, 0.1, 0.12), dome(0.11, 0.1, 0.11, PAL.leaf, 0, 0.12), dome(0.07, 0.1, 0.07, PAL.leafLight, 0.03, 0.17)]));
  shelfBooks(g, -0.32, y0[1], [[0.09, 0.3, N], [0.12, 0.33, Gn], [0.1, 0.31, PL], [0.09, 0.3, R], [0.1, 0.28, T2, -0.3]]);
  g.add(rbox(0.52, 0.07, 0.3, 0.02, P, -0.58, y0[2], 0.03), turn(rbox(0.48, 0.07, 0.29, 0.02, Y, -0.58, y0[2] + 0.07, 0.03), 0, 0.15, 0), rbox(0.44, 0.07, 0.28, 0.02, T2, -0.58, y0[2] + 0.14, 0.03));
  shelfBooks(g, -0.2, y0[2], [[0.1, 0.33, Pk], [0.07, 0.29, B], [0.12, 0.34, N], [0.1, 0.27, P], [0.1, 0.3, O, -0.28]]);
  g.add(box(0.34, 0.4, 0.03, PAL.woodDark, 0.55, y0[2] - 0.0, 0.0), box(0.26, 0.32, 0.034, PAL.cream, 0.55, y0[2] + 0.04, 0.0), box(0.2, 0.16, 0.038, PAL.leafLight, 0.55, y0[2] + 0.12, 0.0));
  shelfBooks(g, -0.84, y0[3], [[0.1, 0.32, O], [0.08, 0.3, PL], [0.12, 0.34, P], [0.1, 0.33, Pk], [0.09, 0.3, B]]);
  g.add(cyl(0.08, 0.08, 0.13, PAL.yellow, 0.35, y0[3], 0.03), glow(0.04, "#FFE6A0", 0.35, y0[3] + 0.17, 0.03, 0.8), cyl(0.07, 0.07, 0.1, PAL.teal, 0.6, y0[3], 0.03), cyl(0.05, 0.05, 0.06, PAL.cream, 0.6, y0[3] + 0.1, 0.03));
  shelfBooks(g, -0.84, y0[4], [[0.1, 0.25, T2], [0.08, 0.22, R], [0.12, 0.26, N], [0.1, 0.25, PL], [0.11, 0.26, P]]);
  g.add(turn(box(0.42, 0.05, 0.28, PAL.pink, 0.5, y0[4], 0.03), 0, 0.2, 0), turn(box(0.36, 0.05, 0.26, PAL.cream, 0.5, y0[4] + 0.05, 0.03), 0, -0.15, 0));
  return g;
}

function cabinet() {
  const g = group();
  for (const [sx, sz] of FEET) g.add(cyl(0.05, 0.035, 0.2, PAL.woodDark, sx * 0.82, 0, sz * 0.3, 10));
  g.add(rbox(1.9, 0.82, 0.8, 0.07, PAL.cream, 0, 0.2, 0), rbox(1.94, 0.07, 0.86, 0.03, PAL.wood, 0, 1.02, 0));
  for (const sx of [-1, 1]) {
    g.add(box(0.84, 0.66, 0.02, PAL.lilac, sx * 0.47, 0.28, 0.4), box(0.66, 0.48, 0.02, PAL.plumLight, sx * 0.47, 0.37, 0.415), sphere(0.04, PAL.gold, sx * 0.14, 0.62, 0.43, 1, 10));
  }
  g.add(box(0.02, 0.7, 0.03, PAL.woodDark, 0, 0.26, 0.41));
  // on top: lamp, vase, frame, books
  g.add(cyl(0.1, 0.11, 0.03, PAL.plum, -0.6, 1.09), cyl(0.025, 0.025, 0.28, PAL.plumDark, -0.6, 1.12), cyl(0.09, 0.16, 0.2, PAL.cream, -0.6, 1.36, 0, 16, { emissive: "#FFE9A8", emissiveIntensity: 0.4 }), glow(0.09, "#FFF1B8", -0.6, 1.44, 0, 0.5));
  g.add(lathe([[0, 0], [0.08, 0], [0.1, 0.06], [0.09, 0.14], [0.05, 0.19], [0.06, 0.24]], PAL.teal, 0.1, 1.09, -0.05), rod([0.1, 1.3, -0.05], [0.04, 1.5, -0.04], 0.01, PAL.leafDark), rod([0.1, 1.3, -0.05], [0.16, 1.48, -0.06], 0.01, PAL.leafDark), sphere(0.05, PAL.pink, 0.04, 1.52, -0.04, 1, 10), sphere(0.05, PAL.yellow, 0.16, 1.5, -0.06, 1, 10));
  g.add(rig(0.5, 1.09, -0.12, -0.2, 0, [box(0.34, 0.4, 0.03, PAL.woodDark, 0, 0, 0), box(0.26, 0.32, 0.034, PAL.cream, 0, 0.04, 0), box(0.2, 0.16, 0.038, PAL.blue, 0, 0.12, 0), box(0.2, 0.08, 0.04, PAL.leaf, 0, 0.04, 0), box(0.04, 0.2, 0.03, PAL.woodDark, 0, 0, -0.04)]));
  g.add(turn(rbox(0.34, 0.06, 0.26, 0.02, PAL.red, 0.7, 1.09, 0.18), 0, 0.3, 0), turn(rbox(0.28, 0.05, 0.22, 0.02, PAL.yellow, 0.7, 1.15, 0.18), 0, -0.2, 0));
  return g;
}

const halfDisc = () => geo("halfdisc", () => { const s = new THREE.Shape(); s.absellipse(0, 0, 1, 1, 0, Math.PI, false, 0); s.closePath(); return new THREE.ShapeGeometry(s, 20); });

function tvStand() {
  const g = group(), wood = PAL.woodDark;
  for (const [sx, sz] of FEET) g.add(cyl(0.05, 0.04, 0.12, PAL.charcoal, sx * 1.3, 0, sz * 0.3, 10));
  g.add(box(2.84, 0.05, 0.8, wood, 0, 0.12, 0), rbox(2.88, 0.07, 0.82, 0.03, PAL.wood, 0, 0.57, 0), box(0.06, 0.4, 0.8, wood, -1.39, 0.17, 0), box(0.06, 0.4, 0.8, wood, 1.39, 0.17, 0));
  g.add(box(0.05, 0.4, 0.78, wood, -0.5, 0.17, 0), box(0.05, 0.4, 0.78, wood, 0.5, 0.17, 0), box(2.8, 0.4, 0.03, PAL.charcoal, 0, 0.17, -0.38));
  for (const sx of [-1, 1]) g.add(box(0.84, 0.36, 0.03, PAL.woodLight, sx * 0.95, 0.19, 0.4), box(0.04, 0.12, 0.03, PAL.gold, sx * 0.62, 0.31, 0.43));
  g.add(rbox(0.7, 0.09, 0.4, 0.03, PAL.greyLight, 0, 0.17, 0.0), box(0.12, 0.012, 0.01, PAL.charcoal, -0.1, 0.22, 0.2), glow(0.02, "#5CE08A", 0.2, 0.2, 0.21, 1));
  g.add(rbox(0.22, 0.05, 0.14, 0.02, PAL.plum, -0.15, 0.26, 0.0), rbox(0.2, 0.05, 0.14, 0.02, PAL.teal, 0.15, 0.26, 0.0));
  // the television
  g.add(box(0.7, 0.04, 0.3, PAL.charcoal, 0, 0.64, 0), box(0.14, 0.12, 0.06, PAL.charcoal, 0, 0.68, 0), rbox(2.0, 1.12, 0.08, 0.05, PAL.charcoal, 0, 0.78, 0));
  const tv = new THREE.Group();
  tv.position.set(0, 0.78 + 0.56, 0.045);
  tv.add(lit(new THREE.PlaneGeometry(1.88, 1.0), "#8FD3F5", 0, 0, 0));
  const sun = lit(new THREE.CircleGeometry(0.15, 20), "#FFD76A", 0.55, 0.25, 0.004);
  const far = lit(halfDisc(), "#6FCF97", -0.4, -0.5, 0.004); far.scale.set(0.52, 0.42, 1);
  const near = lit(halfDisc(), PAL.green, 0.28, -0.5, 0.008); near.scale.set(0.64, 0.26, 1);
  const cloud = new THREE.Group(); cloud.position.set(-0.4, 0.28, 0.006);
  for (const [x, y, r] of [[0, 0, 0.09], [0.11, 0.02, 0.11], [0.23, 0, 0.08]]) cloud.add(lit(new THREE.CircleGeometry(r, 14), "#FFFFFF", x, y, 0));
  tv.add(sun, far, near, cloud);
  g.add(tv, glow(0.025, "#FF7A7A", 0.86, 0.8, 0.045, 1));
  g.add(rbox(0.26, 0.5, 0.26, 0.04, PAL.charcoal, -1.2, 0.64, 0.05), rbox(0.26, 0.5, 0.26, 0.04, PAL.charcoal, 1.2, 0.64, 0.05), turn(cyl(0.07, 0.07, 0.02, PAL.grey, -1.2, 0.8, 0.185), Math.PI / 2), turn(cyl(0.07, 0.07, 0.02, PAL.grey, 1.2, 0.8, 0.185), Math.PI / 2));
  g.userData.tick = (t) => { cloud.position.x = -0.4 + Math.sin(t * 0.35) * 0.3; };
  return g;
}

function bed() {
  const g = group(), frame = PAL.woodDark;
  for (const [sx, sz] of FEET) g.add(cyl(0.08, 0.06, 0.14, frame, sx * 1.35, 0, sz * 1.8, 10));
  g.add(rbox(2.9, 0.36, 3.88, 0.1, PAL.wood, 0, 0.12, 0), rbox(2.66, 0.3, 3.5, 0.14, PAL.white, 0, 0.46, 0.06));
  g.add(rbox(2.86, 1.2, 0.2, 0.12, frame, 0, 0.12, -1.82), rbox(2.86, 0.58, 0.16, 0.07, frame, 0, 0.12, 1.84));
  g.add(rbox(2.78, 0.14, 2.3, 0.07, PAL.plum, 0, 0.7, 0.66), rbox(2.78, 0.16, 0.5, 0.07, PAL.plumLight, 0, 0.72, -0.3));
  for (const z of [0.55, 1.15, 1.75]) g.add(box(2.7, 0.012, 0.12, PAL.lilac, 0, 0.84, z));
  for (const sx of [-1, 1]) g.add(rbox(0.1, 0.5, 2.2, 0.05, PAL.plum, sx * 1.37, 0.36, 0.66));
  for (const sx of [-1, 1]) g.add(turn(rbox(1.04, 0.22, 0.62, 0.11, PAL.paper, sx * 0.62, 0.74, -1.3), -0.18, sx * 0.05, 0));
  const heart = new THREE.Shape();
  heart.moveTo(0, -0.12); heart.bezierCurveTo(-0.2, 0.0, -0.14, 0.14, 0, 0.06); heart.bezierCurveTo(0.14, 0.14, 0.2, 0.0, 0, -0.12);
  g.add(turn(extrude(heart, 0.06, PAL.pink, 0.55, 0.86, 0.35, 0.03), -Math.PI / 2, 0, 0.3));
  g.add(turn(rbox(0.44, 0.14, 0.44, 0.06, PAL.yellow, -0.85, 0.84, 0.8), 0, 0.5, 0));
  return g;
}

function floorLamp() {
  const g = group(), shadeMat = { emissive: "#FFE08A", emissiveIntensity: 0.35 };
  const pool = new THREE.Mesh(new THREE.CircleGeometry(0.44, 24), bmat("#FFE9A8", { transparent: true, opacity: 0.2, depthWrite: false }));
  pool.rotation.x = -Math.PI / 2; pool.position.y = 0.012;
  g.add(pool, cyl(0.24, 0.27, 0.05, PAL.plumDark), cyl(0.18, 0.24, 0.04, PAL.plum, 0, 0.05), cyl(0.03, 0.03, 1.5, PAL.plumDark, 0, 0.09), sphere(0.05, PAL.gold, 0, 0.78, 0, 1, 10));
  g.add(cyl(0.2, 0.33, 0.42, PAL.cream, 0, 1.46, 0, 18, shadeMat), torus(0.2, 0.012, PAL.gold, 0, 1.88, 0, Math.PI / 2), torus(0.33, 0.012, PAL.gold, 0, 1.46, 0, Math.PI / 2), sphere(0.045, PAL.gold, 0, 1.93, 0, 1, 10));
  const light = glow(0.2, "#FFE9A8", 0, 1.67, 0, 0.55);
  g.add(light);
  g.userData.tick = (t) => { light.material.opacity = 0.5 + Math.sin(t * 2.2) * 0.07; pool.material.opacity = 0.19 + Math.sin(t * 2.2) * 0.03; };
  return g;
}

// ---------------------------------------------------------------------------------------------------------------- decor

function profileRadius(profile, y) {
  for (let i = 0; i < profile.length - 1; i++) {
    const [r0, y0] = profile[i], [r1, y1] = profile[i + 1];
    if (y >= y0 && y <= y1) return r0 + ((r1 - r0) * (y - y0)) / (y1 - y0 || 1);
  }
  return profile[profile.length - 1][0];
}

function daisy(petal, x, y, z, dir, s = 1) {
  const g = new THREE.Group();
  g.position.set(x, y, z);
  g.quaternion.setFromUnitVectors(UP, dir.clone().normalize());
  g.scale.setScalar(s);
  g.add(sphere(0.035, PAL.yellow, 0, 0.012, 0, 0.8, 8));
  for (let i = 0; i < 6; i++) { const a = (i / 6) * TAU; g.add(turn(blob(0.05, 0.014, 0.028, petal, Math.sin(a) * 0.065, 0, Math.cos(a) * 0.065), 0, a - Math.PI / 2, 0)); }
  return g;
}

function vase() {
  const prof = [[0, 0], [0.15, 0], [0.2, 0.05], [0.23, 0.18], [0.2, 0.32], [0.11, 0.42], [0.1, 0.5], [0.15, 0.56]];
  const g = group(lathe(prof, PAL.plumLight));
  for (const [y, c] of [[0.13, PAL.plum], [0.2, PAL.cream], [0.27, PAL.plum]]) g.add(torus(profileRadius(prof, y) + 0.004, 0.014, c, 0, y, 0, Math.PI / 2));
  g.add(cyl(0.095, 0.095, 0.01, "#3B2A5C", 0, 0.47));
  const top = [0, 0.5, 0];
  const stems = [[-0.2, 0.98, 0.04, PAL.white, 0], [0.2, 1.0, -0.03, PAL.pink, 0], [0.02, 1.14, 0.1, PAL.orange, 0]];
  for (const [x, y, z, c] of stems) { g.add(rod(top, [x, y - 0.02, z], 0.012, PAL.leafDark), daisy(c, x, y, z, vec(x * 1.2, 1, z * 2 + 0.1))); }
  for (const [x, y, z, c] of [[-0.07, 0.93, -0.13, PAL.red], [0.1, 0.9, 0.15, PAL.pink]]) g.add(rod(top, [x, y - 0.05, z], 0.012, PAL.leafDark), blob(0.055, 0.08, 0.055, c, x, y, z), blob(0.04, 0.06, 0.03, PAL.white, x, y - 0.01, z + 0.03));
  for (let i = 0; i < 3; i++) g.add(rig(0, 0.52, 0, i * 2.1 + 0.8, 0.95, mesh(leafGeo(0.26, 0.04, 0.012), i % 2 ? PAL.leaf : PAL.leafDark)));
  g.userData.tick = (t) => { g.rotation.z = Math.sin(t * 0.9) * 0.012; };
  return g;
}

function globe() {
  const R = 0.3, g = group(cyl(0.27, 0.3, 0.05, PAL.woodDark), cyl(0.2, 0.27, 0.05, PAL.wood, 0, 0.05), cyl(0.04, 0.05, 0.42, PAL.wood, 0, 0.1));
  const tilt = rig(0, 0.9, 0, 0, 0, [], -0.41), spin = new THREE.Group();
  const deg = Math.PI / 180;
  const land = (lat, lon, rw, rh, color, roll = 0) => {
    const d = vec(Math.cos(lat * deg) * Math.sin(lon * deg), Math.sin(lat * deg), Math.cos(lat * deg) * Math.cos(lon * deg));
    const m = blob(rw, rh, 0.02, color, d.x * R, d.y * R, d.z * R);
    m.quaternion.setFromUnitVectors(vec(0, 0, 1), d);
    m.rotateZ(roll);
    return m;
  };
  spin.add(sphere(R, PAL.blue, 0, 0, 0, 1, 18));
  // continents: a few overlapping patches each
  spin.add(land(8, 20, 0.08, 0.12, PAL.leaf), land(-10, 28, 0.06, 0.09, PAL.leaf, 0.3), land(42, 15, 0.08, 0.05, PAL.leafLight), land(40, 85, 0.14, 0.07, PAL.leafLight), land(22, 95, 0.07, 0.08, PAL.leaf));
  spin.add(land(30, -100, 0.1, 0.07, PAL.leaf), land(-5, -70, 0.05, 0.12, PAL.leafLight, 0.2), land(-26, 135, 0.06, 0.045, PAL.leaf));
  spin.add(land(86, 0, 0.09, 0.09, PAL.white), land(-86, 0, 0.1, 0.1, PAL.white));
  tilt.add(spin, rod([0, -R - 0.06, 0], [0, R + 0.06, 0], 0.012, PAL.gold), sphere(0.03, PAL.gold, 0, R + 0.06, 0, 1, 8), sphere(0.03, PAL.gold, 0, -R - 0.06, 0, 1, 8));
  g.add(tilt, torus(R + 0.06, 0.02, PAL.gold, 0, 0.9, 0));
  g.userData.tick = (t, dt) => { spin.rotation.y += dt * 0.5; };
  return g;
}

function heartShape(s) {
  const h = new THREE.Shape();
  h.moveTo(0, -0.12 * s); h.bezierCurveTo(-0.2 * s, 0.0, -0.14 * s, 0.14 * s, 0, 0.06 * s); h.bezierCurveTo(0.14 * s, 0.14 * s, 0.2 * s, 0.0, 0, -0.12 * s);
  return h;
}

function teddy() {
  const fur = PAL.woodDark, light = PAL.wood, g = group();
  g.add(blob(0.25, 0.28, 0.22, fur, 0, 0.3, -0.02), blob(0.16, 0.19, 0.08, light, 0, 0.27, 0.17), sphere(0.06, fur, 0, 0.2, -0.24, 1, 10));
  for (const sx of [-1, 1]) {
    g.add(blob(0.11, 0.1, 0.19, fur, sx * 0.16, 0.1, 0.2), blob(0.07, 0.07, 0.02, light, sx * 0.16, 0.11, 0.395));
    g.add(turn(blob(0.075, 0.16, 0.08, fur, sx * 0.28, 0.36, 0.1), 0, 0, sx * 0.55), sphere(0.05, light, sx * 0.34, 0.25, 0.14, 1, 8));
  }
  g.add(extrude(heartShape(1), 0.04, PAL.red, 0, 0.3, 0.255, 0.012));
  const head = new THREE.Group();
  head.position.set(0, 0.66, 0.02);
  head.add(sphere(0.21, fur, 0, 0.0, 0, 1, 16), blob(0.1, 0.075, 0.07, light, 0, -0.045, 0.17), blob(0.035, 0.025, 0.025, PAL.black, 0, -0.01, 0.235));
  for (const sx of [-1, 1]) head.add(sphere(0.03, PAL.black, sx * 0.08, 0.05, 0.18, 1, 8), sphere(0.012, PAL.white, sx * 0.075, 0.06, 0.205, 1, 6), sphere(0.08, fur, sx * 0.15, 0.17, -0.01, 1, 10), blob(0.05, 0.05, 0.03, PAL.pink, sx * 0.15, 0.17, 0.045), blob(0.03, 0.02, 0.01, PAL.red, sx * 0.1, -0.03, 0.2));
  head.add(rod([-0.02, -0.095, 0.21], [0.0, -0.1, 0.22], 0.008, PAL.black), rod([0.02, -0.095, 0.21], [0.0, -0.1, 0.22], 0.008, PAL.black));
  g.add(head);
  // a little bow tie
  g.add(rig(0, 0.5, 0.15, 0, 0, [turn(cone(0.05, 0.1, PAL.plum, -0.06, -0.05, 0, 8), 0, 0, -Math.PI / 2), turn(cone(0.05, 0.1, PAL.plum, 0.06, -0.05, 0, 8), 0, 0, Math.PI / 2), sphere(0.03, PAL.plumDark, 0, 0, 0.01, 1, 8)]));
  g.userData.tick = (t) => { head.rotation.z = Math.sin(t * 1.1) * 0.06; head.rotation.y = Math.sin(t * 0.7) * 0.1; };
  return g;
}

function safe() {
  const steel = "#7D7A99", door = "#B8B4CF", g = group();
  for (const [sx, sz] of FEET) g.add(box(0.1, 0.06, 0.1, PAL.charcoal, sx * 0.3, 0, sz * 0.28 - 0.04));
  g.add(rbox(0.82, 0.9, 0.76, 0.08, steel, 0, 0.06, -0.04), rbox(0.68, 0.76, 0.06, 0.07, door, 0, 0.13, 0.35), rbox(0.58, 0.6, 0.02, 0.05, "#CFCBE2", 0, 0.21, 0.4));
  for (const [x, y] of [[-0.27, 0.18], [0.27, 0.18], [-0.27, 0.8], [0.27, 0.8]]) g.add(sphere(0.026, PAL.charcoal, x, y, 0.4, 1, 8));
  for (const y of [0.3, 0.68]) g.add(cyl(0.035, 0.035, 0.14, PAL.charcoal, -0.375, y - 0.07, 0.34, 10));
  const dial = rig(0, 0.62, 0.41, 0, 0, [turn(cyl(0.15, 0.15, 0.05, PAL.charcoal, 0, -0.025, 0, 20), Math.PI / 2, 0, 0), torus(0.15, 0.014, PAL.gold, 0, 0, 0.025), turn(cyl(0.05, 0.05, 0.03, PAL.gold, 0, -0.015, 0.03, 12), Math.PI / 2, 0, 0)]);
  for (let i = 0; i < 12; i++) { const a = (i / 12) * TAU; dial.add(turn(box(0.012, i % 3 ? 0.025 : 0.04, 0.01, PAL.white, Math.sin(a) * 0.112, -0.01 + Math.cos(a) * 0.112, 0.027), 0, 0, -a)); }
  dial.add(turn(box(0.018, 0.06, 0.012, PAL.red, 0.0, 0.065, 0.034), 0, 0, 0.5));
  g.add(dial);
  g.add(rod([-0.17, 0.3, 0.44], [0.17, 0.3, 0.44], 0.022, PAL.gold), sphere(0.04, PAL.gold, -0.18, 0.3, 0.44, 1, 10), sphere(0.04, PAL.gold, 0.18, 0.3, 0.44, 1, 10), turn(cyl(0.06, 0.06, 0.05, PAL.gold, 0, 0.275, 0.42, 12), Math.PI / 2, 0, 0));
  g.add(glow(0.028, "#5CE08A", 0.24, 0.84, 0.405, 1), rbox(0.2, 0.05, 0.02, 0.01, PAL.charcoal, 0.0, 0.84, 0.395));
  return g;
}

function shieldShape(w, h) {
  const s = new THREE.Shape();
  s.moveTo(0, h * 0.5); s.lineTo(w / 2, h * 0.33); s.lineTo(w / 2, h * 0.03); s.bezierCurveTo(w / 2, -h * 0.26, w * 0.2, -h * 0.4, 0, -h * 0.5);
  s.bezierCurveTo(-w * 0.2, -h * 0.4, -w / 2, -h * 0.26, -w / 2, h * 0.03); s.lineTo(-w / 2, h * 0.33); s.closePath();
  return s;
}

function shieldTrophy() {
  const g = group(rbox(0.86, 0.12, 0.86, 0.05, PAL.plumDark), rbox(0.6, 0.46, 0.6, 0.08, PAL.plum, 0, 0.12), box(0.36, 0.14, 0.03, PAL.gold, 0, 0.28, 0.3), rbox(0.74, 0.08, 0.74, 0.04, PAL.plumDark, 0, 0.58), cyl(0.17, 0.22, 0.1, PAL.gold, 0, 0.66, 0, 16));
  const sh = new THREE.Group();
  sh.position.set(0, 0.76 + 0.38 - 0.03, 0);
  sh.rotation.x = -0.06;
  sh.add(extrude(shieldShape(0.64, 0.78), 0.06, PAL.gold, 0, 0, -0.03, 0.02), extrude(shieldShape(0.5, 0.64), 0.05, PAL.yellow, 0, -0.0, 0.04, 0.012));
  const check = new THREE.Group();
  check.position.set(0, 0.01, 0.105);
  check.add(turn(box(0.15, 0.07, 0.05, PAL.plum, -0.1, -0.035, 0), 0, 0, -Math.PI / 4), turn(box(0.34, 0.07, 0.05, PAL.plum, 0.06, -0.015, 0), 0, 0, Math.PI / 4), turn(cyl(0.036, 0.036, 0.05, PAL.plum, -0.04, -0.095, 0, 10), Math.PI / 2, 0, 0));
  sh.add(check);
  g.add(sh);
  const stars = [], oct = new THREE.OctahedronGeometry(0.045);
  for (const [x, y, z] of [[-0.4, 1.3, 0.1], [0.4, 0.98, 0.12], [0.32, 1.52, 0.0]]) { const m = mesh(oct, PAL.gold, x, y, z); m.castShadow = false; g.add(m); stars.push(m); }
  g.userData.tick = (t) => { stars.forEach((m, i) => { const k = 0.8 + 0.35 * Math.sin(t * 2.4 + i * 2.1); m.scale.setScalar(k); m.rotation.y = t * 1.5 + i; }); };
  return g;
}

function fishBody(body, fin, stripe) {
  const f = new THREE.Group();
  const tail = rig(-0.1, 0, 0, 0, 0, []);
  const tc = mesh(geo("tail", () => new THREE.ConeGeometry(0.075, 0.13, 10)), fin, -0.065, 0, 0);
  tc.rotation.z = Math.PI / 2; tc.scale.set(1, 1, 0.3); tail.add(tc);
  f.add(blob(0.12, 0.075, 0.05, body), tail, blob(0.05, 0.04, 0.012, fin, -0.01, 0.075, 0), blob(0.035, 0.025, 0.01, fin, 0.01, -0.07, 0.01));
  if (stripe) f.add(blob(0.018, 0.075, 0.052, stripe, 0.03, 0, 0));
  for (const sz of [-1, 1]) f.add(sphere(0.016, PAL.black, 0.075, 0.018, sz * 0.04, 1, 8));
  f.userData.tail = tail;
  return f;
}

function fishTank() {
  const g = group(), sand = PAL.woodLight, dark = PAL.charcoal;
  g.add(box(1.9, 0.1, 0.86, PAL.woodDark, 0, 0, 0), rbox(1.9, 0.42, 0.86, 0.05, PAL.wood, 0, 0.1, 0), box(1.84, 0.04, 0.8, dark, 0, 0.6, 0));
  for (const sx of [-1, 1]) g.add(box(0.8, 0.32, 0.02, PAL.woodLight, sx * 0.45, 0.16, 0.435), sphere(0.025, PAL.gold, sx * 0.1, 0.3, 0.45, 1, 8));
  g.add(box(1.74, 0.07, 0.7, sand, 0, 0.64));
  const rn = seeded(11);
  for (let i = 0; i < 4; i++) g.add(blob(0.04, 0.025, 0.04, [PAL.white, PAL.pink, PAL.lilac, PAL.cream][i], (rn() - 0.5) * 1.5, 0.71, (rn() - 0.5) * 0.55));
  g.add(blob(0.15, 0.1, 0.12, PAL.grey, -0.58, 0.72, -0.12), blob(0.09, 0.07, 0.08, PAL.greyLight, -0.4, 0.71, 0.06));
  g.add(cone(0.05, 0.28, PAL.orange, 0.62, 0.7, -0.15, 8), cone(0.04, 0.2, PAL.pink, 0.72, 0.7, -0.05, 8), cone(0.035, 0.16, PAL.orange, 0.55, 0.7, 0.0, 8));
  // a little castle
  g.add(box(0.26, 0.16, 0.14, PAL.plumLight, 0.18, 0.71, -0.2), cyl(0.05, 0.05, 0.3, PAL.plum, 0.06, 0.71, -0.2, 10), cone(0.065, 0.1, PAL.red, 0.06, 1.01, -0.2, 10));
  const weeds = [];
  [[-0.2, -0.2, 0.34, PAL.leaf], [-0.12, -0.25, 0.44, PAL.leafDark], [-0.28, -0.12, 0.28, PAL.leafLight]].forEach(([x, z, h, c], i) => {
    const w = new THREE.Group(); w.position.set(x, 0.7, z);
    const n = Math.round(h / 0.1);
    for (let k = 0; k < n; k++) w.add(blob(0.045, 0.08, 0.02, c, Math.sin(k * 1.3 + i) * 0.03, k * 0.1 + 0.07, 0));
    g.add(w); weeds.push(w);
  });
  const bub = [];
  for (let i = 0; i < 3; i++) { const b = new THREE.Mesh(new THREE.SphereGeometry(0.022 + i * 0.006, 8, 6), mat(PAL.white, { transparent: true, opacity: 0.75 })); g.add(b); bub.push(b); }
  g.add(pane(1.74, 0.68, 0.7, "#5CC8F2", 0.32, 0, 0.64, 0));
  const f1 = fishBody(PAL.orange, PAL.yellow, PAL.white), f2 = fishBody(PAL.pink, PAL.plumLight, null);
  f2.scale.setScalar(0.85);
  g.add(f1, f2);
  g.add(pane(1.8, 0.85, 0.76, PAL.glass, 0.18, 0, 0.64, 0));
  for (const [sx, sz] of FEET) g.add(box(0.045, 0.85, 0.045, dark, sx * 0.9, 0.64, sz * 0.38));
  g.add(box(1.86, 0.06, 0.82, dark, 0, 1.49, 0), lit(new THREE.BoxGeometry(1.5, 0.012, 0.03), "#FFF3C4", 0, 1.485, 0.34), box(1.0, 0.03, 0.4, PAL.greyLight, -0.2, 1.55, 0));
  const fishes = [[f1, 0.55, 0.62, 0.0, 1.06, 0.12, 0.7], [f2, 0.42, 0.9, 2.0, 1.22, -0.12, 0.5]];
  const update = (t, dt) => {
    for (const [f, A, w, ph, y, z, bob] of fishes) {
      const a = w * t + ph, v = Math.cos(a);
      f.position.set(A * Math.sin(a), y + Math.sin(t * 1.3 + ph * 2) * 0.03 * bob, z);
      const target = v > 0 ? 0 : Math.PI;
      f.rotation.y += (target - f.rotation.y) * Math.min(1, dt * 5);
      f.userData.tail.rotation.y = Math.sin(t * 9 + ph) * 0.45;
    }
    weeds.forEach((w, i) => { w.rotation.z = Math.sin(t * 1.4 + i * 1.7) * 0.14; });
    bub.forEach((b, i) => { const k = (t * 0.35 + i * 0.33) % 1; b.position.set(0.82 - 0.02 * i + Math.sin(t * 3 + i) * 0.015, 0.76 + k * 0.52, 0.28); b.visible = true; });
  };
  update(0, 0.016);
  g.userData.tick = update;
  return g;
}

function wheel(x) {
  const R = 0.36, w = new THREE.Group();
  w.position.set(x, 0.4, 0);
  w.add(torus(R, 0.04, PAL.charcoal), torus(R - 0.05, 0.012, PAL.greyLight), turn(cyl(0.045, 0.045, 0.1, PAL.grey, 0, -0.05, 0, 10), Math.PI / 2, 0, 0));
  for (let i = 0; i < 3; i++) w.add(turn(box(2 * (R - 0.05), 0.012, 0.012, PAL.grey, 0, -0.006, 0), 0, 0, (i * Math.PI) / 3));
  return w;
}

function bike() {
  const c = PAL.red, g = group(wheel(-0.54), wheel(0.54));
  const BB = [-0.08, 0.28, 0], S = [-0.26, 0.86, 0], H = [0.4, 0.84, 0], H2 = [0.45, 0.7, 0], rear = [-0.54, 0.4], front = [0.54, 0.4];
  g.add(rod(BB, S, 0.03, c), rod(S, H, 0.03, c), rod(BB, H2, 0.034, c), rod(H, H2, 0.04, PAL.charcoal));
  for (const z of [-0.06, 0.06]) g.add(rod([BB[0], BB[1], z], [rear[0], rear[1], z], 0.022, c), rod([S[0], S[1], z * 0.3], [rear[0], rear[1], z], 0.022, c), rod([H2[0], H2[1], z], [front[0], front[1], z], 0.025, c));
  g.add(rod([0.4, 0.84, 0], [0.36, 1.04, 0], 0.025, PAL.charcoal), rod([0.36, 1.04, -0.26], [0.36, 1.04, 0.26], 0.022, PAL.charcoal));
  for (const sz of [-1, 1]) g.add(turn(cyl(0.034, 0.034, 0.12, PAL.cream, 0.36, 0.98, sz * 0.27, 10), Math.PI / 2, 0, 0));
  g.add(sphere(0.04, PAL.gold, 0.36, 1.09, 0.1, 1, 10), rod(S, [-0.27, 0.98, 0], 0.022, PAL.grey), rbox(0.3, 0.07, 0.16, 0.03, PAL.plum, -0.29, 0.97, 0));
  g.add(torus(0.1, 0.014, PAL.charcoal, BB[0], BB[1], 0.05), rod([BB[0], BB[1], 0.05], [BB[0] + 0.02, BB[1] - 0.15, 0.06], 0.016, PAL.grey), rod([BB[0], BB[1], -0.05], [BB[0] - 0.02, BB[1] + 0.15, -0.06], 0.016, PAL.grey), box(0.11, 0.025, 0.07, PAL.charcoal, BB[0] + 0.02, BB[1] - 0.17, 0.1), box(0.11, 0.025, 0.07, PAL.charcoal, BB[0] - 0.02, BB[1] + 0.15, -0.1));
  // basket with flowers
  g.add(rod([0.38, 0.98, 0], [0.5, 0.88, 0], 0.02, PAL.grey), rbox(0.3, 0.2, 0.34, 0.05, PAL.woodLight, 0.64, 0.84, 0), box(0.26, 0.012, 0.3, PAL.woodDark, 0.64, 1.035, 0));
  g.add(sphere(0.06, PAL.pink, 0.6, 1.1, 0.05, 1, 10), sphere(0.055, PAL.yellow, 0.68, 1.12, -0.05, 1, 10), sphere(0.05, PAL.white, 0.64, 1.14, 0.1, 1, 10), blob(0.07, 0.03, 0.03, PAL.leaf, 0.7, 1.06, 0.09), blob(0.07, 0.03, 0.03, PAL.leafDark, 0.58, 1.06, -0.08));
  return g;
}

function piano() {
  const body = PAL.ink, trim = PAL.plum, g = group();
  g.add(rbox(2.84, 0.18, 0.8, 0.05, PAL.charcoal, 0, 0, -0.565), rbox(2.84, 1.12, 0.78, 0.06, body, 0, 0.18, -0.57), rbox(2.9, 0.08, 0.82, 0.035, trim, 0, 1.3, -0.565));
  g.add(box(2.74, 0.1, 0.36, body, 0, 0.66, -0.0), box(0.2, 0.48, 0.36, body, -1.27, 0.18, 0.0), box(0.2, 0.48, 0.36, body, 1.27, 0.18, 0.0));
  g.add(box(2.5, 0.04, 0.3, PAL.paper, 0, 0.76, 0.0));
  const wk = 2.5 / 21;
  for (let o = 0; o < 3; o++) for (const b of [1, 2, 4, 5, 6]) g.add(box(0.07, 0.05, 0.18, PAL.black, -1.25 + (o * 7 + b) * wk, 0.8, -0.06));
  g.add(box(2.7, 0.025, 0.02, PAL.gold, 0, 0.95, -0.17), box(2.7, 0.025, 0.02, PAL.gold, 0, 1.2, -0.17));
  g.add(box(1.4, 0.03, 0.14, body, 0, 1.0, -0.12), rig(-0.3, 1.03, -0.15, 0, -0.18, box(0.6, 0.38, 0.014, PAL.paper, 0, 0, 0)), rig(0.35, 1.03, -0.15, 0, -0.18, box(0.6, 0.38, 0.014, PAL.paper, 0, 0, 0)));
  for (const x of [-0.15, 0, 0.15]) g.add(box(0.1, 0.03, 0.2, PAL.gold, x, 0.05, 0.0));
  // stool
  for (const a of [0.5, 2.6, 4.7]) g.add(rod([Math.sin(a) * 0.2, 0, 0.66 + Math.cos(a) * 0.2], [Math.sin(a) * 0.14, 0.4, 0.66 + Math.cos(a) * 0.14], 0.03, PAL.woodDark));
  g.add(cyl(0.27, 0.27, 0.1, PAL.plum, 0, 0.38, 0.66, 18), dome(0.26, 0.05, 0.26, PAL.plumLight, 0, 0.48, 0.66));
  // metronome
  const pend = rig(0.0, 0.0, 0.0, 0, 0, [rod([0, 0, 0], [0, 0.2, 0], 0.008, PAL.gold), sphere(0.02, PAL.gold, 0, 0.15, 0, 1, 8)]);
  const metro = rig(1.05, 1.38, -0.6, 0.4, 0, [box(0.2, 0.03, 0.16, PAL.woodDark), cyl(0.04, 0.09, 0.26, PAL.wood, 0, 0.03, 0, 4).rotateY(Math.PI / 4)]);
  pend.position.set(0, 0.06, 0.09);
  metro.add(pend);
  g.add(metro);
  // floating notes
  const notes = [];
  [[-0.95, 1.75, -0.4, PAL.plumLight], [-0.55, 1.95, -0.5, PAL.pink]].forEach(([x, y, z, c], i) => {
    const n = rig(x, y, z, 0.3, 0, [blob(0.055, 0.04, 0.03, c, 0, 0, 0).rotateZ(0.4), box(0.015, 0.2, 0.015, c, 0.045, 0.0, 0), box(0.07, 0.03, 0.015, c, 0.075, 0.18, 0).rotateZ(-0.5)]);
    n.userData.base = y; n.userData.i = i; g.add(n); notes.push(n);
  });
  g.userData.tick = (t) => { pend.rotation.z = Math.sin(t * 3.4) * 0.5; notes.forEach((n) => { n.position.y = n.userData.base + Math.sin(t * 1.6 + n.userData.i * 2) * 0.06; n.rotation.z = Math.sin(t * 1.1 + n.userData.i) * 0.1; }); };
  return g;
}

function rugRound() {
  const g = group(), n = 18;
  for (let i = 0; i < n; i++) { const a = (i / n) * TAU; g.add(cyl(0.17, 0.17, 0.044, i % 2 ? PAL.pink : PAL.plumLight, Math.sin(a) * 1.25, 0, Math.cos(a) * 1.25, 14)); }
  g.add(cyl(1.28, 1.28, 0.05, PAL.plum, 0, 0, 0, 36), cyl(1.12, 1.12, 0.056, PAL.cream, 0, 0, 0, 36), cyl(0.96, 0.96, 0.062, PAL.lilac, 0, 0, 0, 36));
  for (let i = 0; i < 12; i++) { const a = (i / 12) * TAU; g.add(cyl(0.045, 0.045, 0.064, i % 2 ? PAL.plumLight : PAL.plum, Math.sin(a) * 1.04, 0, Math.cos(a) * 1.04, 8)); }
  for (let i = 0; i < 8; i++) { const a = (i / 8) * TAU; g.add(cyl(0.17, 0.17, 0.068, i % 2 ? PAL.orange : PAL.pink, Math.sin(a) * 0.46, 0, Math.cos(a) * 0.46, 14)); }
  g.add(cyl(0.26, 0.26, 0.072, PAL.yellow, 0, 0, 0, 18), cyl(0.13, 0.13, 0.078, PAL.gold, 0, 0, 0, 14));
  g.scale.set(1.03, 1, 1.03);
  return g;
}

function rugRect() {
  const g = group();
  g.add(box(3.7, 0.05, 2.9, PAL.plumDark), box(3.4, 0.056, 2.6, PAL.cream), box(3.2, 0.062, 2.4, PAL.plumLight));
  for (const z of [-0.95, -0.7, 0.7, 0.95]) g.add(box(3.1, 0.066, 0.06, z % 0.5 ? PAL.cream : PAL.yellow, 0, 0, z));
  const d1 = turn(box(1.5, 0.066, 1.5, PAL.plum), 0, Math.PI / 4, 0), d2 = turn(box(1.0, 0.07, 1.0, PAL.cream), 0, Math.PI / 4, 0), d3 = turn(box(0.55, 0.074, 0.55, PAL.yellow), 0, Math.PI / 4, 0);
  g.add(d1, d2, d3, cyl(0.12, 0.12, 0.078, PAL.red, 0, 0, 0, 12));
  for (const [x, z] of [[-1.35, -0.85], [1.35, -0.85], [-1.35, 0.85], [1.35, 0.85]]) g.add(turn(box(0.3, 0.066, 0.3, PAL.plum, x, 0, z), 0, Math.PI / 4, 0), cyl(0.07, 0.07, 0.07, PAL.yellow, x, 0, z, 10));
  for (const sx of [-1, 1]) for (let i = 0; i < 9; i++) g.add(box(0.12, 0.03, 0.06, i % 2 ? PAL.cream : PAL.greyLight, sx * 1.88, 0, -1.2 + i * 0.3));
  return g;
}

// @@MORE@@

export const MODELS = {
  succulent, fern, bamboo, monstera, orchid, palm, bonsai,
  stool, beanbag, armchair, sofa, "coffee-table": coffeeTable, "dining-table": diningTable, desk, bookshelf, cabinet, "tv-stand": tvStand, bed, "floor-lamp": floorLamp,
  vase, globe, teddy, safe, "shield-trophy": shieldTrophy, "fish-tank": fishTank, bike, piano, "rug-round": rugRound, "rug-rect": rugRect,
};
