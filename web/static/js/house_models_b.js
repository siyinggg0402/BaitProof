// House models, part B: things that hang on the wall (posters, clocks, bunting, flags) and the festival pieces (lanterns, lamps, trees, the Merlion, a rangoli rug).
// Every model is a function that returns a THREE.Group, built from simple shapes (no model files, no images).
//  - Floor items and rugs: the origin is the middle of the footprint on the floor (y = 0), the front faces +z, and the model stays inside its w x d cells.
//  - Wall items: the origin is the middle of the item's span along the wall and ON the wall surface (the back sits at z = 0, the model comes out toward +z);
//    y is the absolute height above the floor (the wall is 4.2 tall). The width never goes past the catalog w.
// A model may set group.userData.tick = (t, dt) => {} for tiny life (flames, flags, clock hands).
import { THREE, PAL, mat, cyl, cone, sphere, group, glow, pot } from "./house_kit.js";

const PI = Math.PI, TAU = Math.PI * 2;
const RED_CNY = "#DD2A3C", GOLD = "#E8B230", GOLD_DARK = "#C48A12";

// ------------------------------------------------------------------------------------------------ small helpers
function at(m, x = 0, y = 0, z = 0) { m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; return m; }
const mesh = (geo, color, x = 0, y = 0, z = 0, opts) => {
  const m = at(new THREE.Mesh(geo, mat(color, opts)), x, y, z);
  if (opts && opts.transparent) m.castShadow = false;       // see-through bits (glass sheen, water) cast no shadow
  return m;
};
const glowOpts = (color, k = 0.6) => ({ emissive: color, emissiveIntensity: k });
const poly = (pts) => new THREE.Shape(pts.map(([x, y]) => new THREE.Vector2(x, y)));
const v3 = (x, y, z) => new THREE.Vector3(x, y, z);

/** A ball or egg with its own radius on each axis, middle at (x, y, z). */
function ell(rx, ry, rz, color, x = 0, y = 0, z = 0, opts, seg = 16) {
  const m = mesh(new THREE.SphereGeometry(1, seg, Math.max(8, seg - 4)), color, x, y, z, opts);
  m.scale.set(rx, ry, rz);
  return m;
}
/** A ring in the x/y plane; turn it with rx / ry. */
function torus(R, r, color, x = 0, y = 0, z = 0, rx = 0, ry = 0, seg = 18, opts) {
  const m = mesh(new THREE.TorusGeometry(R, r, 6, seg), color, x, y, z, opts);
  m.rotation.set(rx, ry, 0);
  return m;
}
/** A rectangle with rounded corners (rt on the top corners, rb on the bottom ones), centred on 0, as a Shape. */
function roundedShape(w, h, rt, rb = rt) {
  const hw = w / 2, hh = h / 2;
  rt = Math.min(rt, hw, hh); rb = Math.min(rb, hw, hh);
  const s = new THREE.Shape();
  s.moveTo(-hw + rb, -hh);
  s.lineTo(hw - rb, -hh);
  if (rb > 0.001) s.absarc(hw - rb, -hh + rb, rb, -PI / 2, 0, false);
  s.lineTo(hw, hh - rt);
  if (rt > 0.001) s.absarc(hw - rt, hh - rt, rt, 0, PI / 2, false);
  s.lineTo(-hw + rt, hh);
  if (rt > 0.001) s.absarc(-hw + rt, hh - rt, rt, PI / 2, PI, false);
  s.lineTo(-hw, -hh + rb);
  if (rb > 0.001) s.absarc(-hw + rb, -hh + rb, rb, PI, PI * 1.5, false);
  return s;
}
/** A picture frame: a rounded rectangle with a hole, border t wide. */
function frameShape(w, h, t, r = 0.04) {
  const s = roundedShape(w, h, r);
  s.holes.push(roundedShape(w - 2 * t, h - 2 * t, Math.max(0.008, r - t * 0.5)));
  return s;
}
/** A shield: flat top, rounded shoulders, a soft point at the bottom. */
function shieldShape(w, h) {
  const a = w / 2, b = h / 2, s = new THREE.Shape();
  s.moveTo(-a * 0.8, b);
  s.lineTo(a * 0.8, b);
  s.quadraticCurveTo(a, b, a, b * 0.72);
  s.lineTo(a, b * 0.05);
  s.bezierCurveTo(a, -b * 0.5, a * 0.5, -b * 0.8, 0, -b);
  s.bezierCurveTo(-a * 0.5, -b * 0.8, -a, -b * 0.5, -a, b * 0.05);
  s.lineTo(-a, b * 0.72);
  s.quadraticCurveTo(-a, b, -a * 0.8, b);
  return s;
}
function heartShape(s) {
  const h = new THREE.Shape();
  h.moveTo(0, -0.5 * s);
  h.bezierCurveTo(-0.6 * s, -0.08 * s, -0.5 * s, 0.42 * s, -0.25 * s, 0.42 * s);
  h.bezierCurveTo(-0.08 * s, 0.42 * s, 0, 0.3 * s, 0, 0.2 * s);
  h.bezierCurveTo(0, 0.3 * s, 0.08 * s, 0.42 * s, 0.25 * s, 0.42 * s);
  h.bezierCurveTo(0.5 * s, 0.42 * s, 0.6 * s, -0.08 * s, 0, -0.5 * s);
  return h;
}
/** Points of a star with n tips (outer radius ro, inner radius ri); the first tip points at angle rot. */
function starPts(n, ro, ri, rot = PI / 2) {
  const pts = [];
  for (let i = 0; i < n * 2; i++) { const r = i % 2 ? ri : ro, a = rot + (i * PI) / n; pts.push([Math.cos(a) * r, Math.sin(a) * r]); }
  return pts;
}
/** A crescent (outer circle R, inner circle r pushed d to the right), opening toward +x. */
function crescentPts(R, r, d, seg = 28) {
  const xs = (R * R - r * r + d * d) / (2 * d), ys = Math.sqrt(Math.max(0, R * R - xs * xs));
  const a0 = Math.atan2(ys, xs), b0 = Math.atan2(ys, xs - d), pts = [];
  for (let i = 0; i <= seg; i++) { const a = a0 + ((TAU - 2 * a0) * i) / seg; pts.push([R * Math.cos(a), R * Math.sin(a)]); }
  for (let i = 0; i <= seg; i++) { const b = TAU - b0 - ((TAU - 2 * b0) * i) / seg; pts.push([d + r * Math.cos(b), r * Math.sin(b)]); }
  return pts;
}
/** A leaf / petal: pointed at both ends, length L, half-width hw, base at the origin pointing up (+y). */
function leafShape(L, hw) {
  const s = new THREE.Shape();
  s.moveTo(0, 0);
  s.quadraticCurveTo(hw * 2, L * 0.5, 0, L);
  s.quadraticCurveTo(-hw * 2, L * 0.5, 0, 0);
  return s;
}
const scalePts = (pts, k, cx = 0, cy = 0) => pts.map(([x, y]) => [cx + (x - cx) * k, cy + (y - cy) * k]);

/** A shape pushed out d deep with its back at z0, its middle (the shape's own origin) at (x, y). */
function slab(shp, d, color, x = 0, y = 0, z0 = 0, opts) {
  return mesh(new THREE.ExtrudeGeometry(shp, { depth: d, bevelEnabled: false, curveSegments: 10 }), color, x, y, z0, opts);
}
const rslab = (w, h, r, d, color, x = 0, y = 0, z0 = 0, opts) => slab(roundedShape(w, h, r), d, color, x, y, z0, opts);
/** A box centred on (x, y) with its back at z0. */
const plate = (w, h, d, color, x = 0, y = 0, z0 = 0, opts) => mesh(new THREE.BoxGeometry(w, h, d), color, x, y, z0 + d / 2, opts);
/** A round disc facing +z (back at z0). */
function disc(r, d, color, x = 0, y = 0, z0 = 0, seg = 20, opts) {
  const g = new THREE.CylinderGeometry(r, r, d, seg);
  g.rotateX(PI / 2);
  return mesh(g, color, x, y, z0 + d / 2, opts);
}
/** A flat stick with round ends from (x1, y1) to (x2, y2), thickness t. */
function bar(x1, y1, x2, y2, t, d, color, z0 = 0) {
  const len = Math.hypot(x2 - x1, y2 - y1) + t;
  const m = rslab(len, t, t / 2, d, color, (x1 + x2) / 2, (y1 + y2) / 2, z0);
  m.rotation.z = Math.atan2(y2 - y1, x2 - x1);
  return m;
}
/** A thin round cord between two points in the wall plane. */
function cord(x1, y1, x2, y2, r, color, z = 0.03) {
  const len = Math.hypot(x2 - x1, y2 - y1);
  const m = mesh(new THREE.CylinderGeometry(r, r, len, 6), color, (x1 + x2) / 2, (y1 + y2) / 2, z);
  m.rotation.z = Math.atan2(y2 - y1, x2 - x1) - PI / 2;
  return m;
}
const tubeAlong = (curve, r, color, seg = 24, radial = 5) => mesh(new THREE.TubeGeometry(curve, seg, r, radial, false), color);
const nailAt = (x, y, z = 0.035, r = 0.032) => ell(r, r, r * 0.8, PAL.gold, x, y, z, undefined, 10);

const MX = (x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0, sx = 1, sy = sx, sz = sx) =>
  new THREE.Matrix4().compose(v3(x, y, z), new THREE.Quaternion().setFromEuler(new THREE.Euler(rx, ry, rz)), v3(sx, sy, sz));
/** Many small pieces as one geometry: parts are [geometry, matrix] pairs. */
function mergeGeo(parts) {
  const ps = [], ns = [];
  let n = 0;
  for (const [g0, m] of parts) {
    const g = g0.index ? g0.toNonIndexed() : g0.clone();
    if (m) g.applyMatrix4(m);
    ps.push(g.attributes.position.array); ns.push(g.attributes.normal.array); n += g.attributes.position.array.length;
  }
  const pos = new Float32Array(n), nor = new Float32Array(n);
  let o = 0;
  ps.forEach((a, i) => { pos.set(a, o); nor.set(ns[i], o); o += a.length; });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
  return geo;
}
const BALL = new THREE.SphereGeometry(1, 10, 8);
/** A part for merged(): a ball/egg with radii (rx, ry, rz) at (x, y, z), optionally turned. */
const blob = (x, y, z, rx, ry = rx, rz = rx, rot = 0, yaw = 0) => [BALL, MX(x, y, z, 0, yaw, rot, rx, ry, rz)];
/** The same, as a single Lambert mesh of one colour. */
const merged = (parts, color, opts) => mesh(mergeGeo(parts), color, 0, 0, 0, opts);

/** The Baitproof mark: a purple shield with a white check mark. Back at z0, middle at (x, y). */
function emblem(w, h, z0, x, y, dark = PAL.plumDark, mid = PAL.plum, light = PAL.plumLight) {
  const g = group();
  g.add(slab(shieldShape(w, h), 0.022, dark, x, y, z0));
  g.add(slab(shieldShape(w * 0.84, h * 0.84), 0.022, mid, x, y - h * 0.004, z0 + 0.022));
  const s = w, cx = x, cy = y + h * 0.02, zc = z0 + 0.048;
  g.add(bar(cx - 0.2 * s, cy, cx - 0.06 * s, cy - 0.14 * s, 0.115 * s, 0.02, "#FFFFFF", zc));
  g.add(bar(cx - 0.06 * s, cy - 0.14 * s, cx + 0.22 * s, cy + 0.16 * s, 0.115 * s, 0.02, "#FFFFFF", zc));
  return g;
}

/** A ball lantern's meridian rib: a thin tube over the ellipsoid surface at azimuth phi (PI/2 is straight at the viewer). */
function rib(rx, ry, rz, phi, color, tube = 0.012, k = 1.02) {
  const pts = [];
  for (let i = 0; i <= 14; i++) {
    const th = 0.12 + ((PI - 0.24) * i) / 14;
    pts.push(v3(rx * k * Math.sin(th) * Math.cos(phi), ry * k * Math.cos(th), rz * k * Math.sin(th) * Math.sin(phi)));
  }
  return mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts), 14, tube, 4, false), color);
}
const RIB_PHIS = [PI / 2, PI / 2 - 0.62, PI / 2 + 0.62, PI / 2 - 1.2, PI / 2 + 1.2];

/** A glowing paper ball lantern (middle at the origin, a little flat toward the wall). Hangs from a cord that the caller adds. */
function ballLantern(r, color, ribColor, capColor = GOLD, flat = 0.78) {
  const g = group(), ry = r * 0.92, rz = r * flat;
  g.add(ell(r, ry, rz, color, 0, 0, 0, glowOpts(color, 0.55), 22));
  for (const p of RIB_PHIS) g.add(rib(r, ry, rz, p, ribColor, r * 0.045));
  g.add(cyl(r * 0.3, r * 0.34, r * 0.16, capColor, 0, ry - r * 0.05));
  g.add(cyl(r * 0.34, r * 0.28, r * 0.16, capColor, 0, -ry - r * 0.11));
  g.add(torus(r * 0.12, r * 0.035, capColor, 0, ry + r * 0.22, 0, 0, 0, 12));
  // tassel
  g.add(cyl(0.01, 0.01, r * 0.5, capColor, 0, -ry - r * 0.6));
  g.add(cyl(0.012, r * 0.2, r * 0.7, color, 0, -ry - r * 1.3));
  const halo = glow(r * 1.3, "#FFC76B", 0, 0, 0, 0.1);
  halo.scale.z = 0.45;
  g.add(halo);
  return g;
}

// ------------------------------------------------------------------------------------------------ wall: everyday things
function posterShield() {
  const g = group(), W = 0.86, H = 1.26, cy = 2.4;
  g.add(slab(roundedShape(W, H, 0.06), 0.06, PAL.plumDark, 0, cy, 0));
  g.add(slab(roundedShape(W - 0.1, H - 0.1, 0.035), 0.016, PAL.paper, 0, cy, 0.06));
  g.add(emblem(0.56, 0.64, 0.076, 0, cy + 0.17));
  g.add(bar(-0.18, cy - 0.37, 0.18, cy - 0.37, 0.07, 0.014, PAL.plum, 0.076));
  g.add(bar(-0.12, cy - 0.5, 0.12, cy - 0.5, 0.045, 0.014, PAL.plumLight, 0.076));
  for (const [sx, sy, k] of [[-0.29, 0.5, 1], [0.3, 0.46, 0.75], [0.27, -0.2, 0.55]]) g.add(slab(poly(starPts(4, 0.06 * k, 0.017 * k)), 0.014, PAL.yellow, sx, cy + sy, 0.076));
  g.add(nailAt(0, cy + H / 2 + 0.02));
  return g;
}

function calendar() {
  const g = group(), W = 0.82, H = 0.96, cy = 2.5;
  g.add(slab(roundedShape(W, H, 0.05), 0.045, PAL.paper, 0, cy, 0));
  g.add(slab(roundedShape(W, 0.27, 0.05, 0), 0.02, PAL.plum, 0, cy + H / 2 - 0.135, 0.045));
  g.add(bar(-0.17, cy + 0.335, 0.17, cy + 0.335, 0.07, 0.014, "#FFFFFF", 0.065));
  g.add(bar(-0.1, cy + 0.255, 0.1, cy + 0.255, 0.035, 0.014, PAL.plumLight, 0.065));
  for (const x of [-0.22, 0.22]) g.add(torus(0.036, 0.013, GOLD, x, cy + H / 2 - 0.01, 0.06, 0, 0, 12));
  g.add(nailAt(0, cy + H / 2 + 0.05, 0.03));
  // weekday letters (little pills), then the date squares: a month that starts on a Wednesday
  const cellX = 0.098, cellY = 0.1, x0 = -3 * cellX, yTop = cy + 0.08, zc = 0.045;
  g.add(merged(Array.from({ length: 7 }, (_, i) => [new THREE.BoxGeometry(0.05, 0.022, 0.012), MX(x0 + i * cellX, cy + 0.17, zc + 0.006)]), PAL.plumLight));
  const week = [], end = [];
  const hi = { 16: PAL.red, 7: PAL.yellow, 24: PAL.teal };
  for (let i = 3; i <= 33; i++) {
    const col = i % 7, row = Math.floor(i / 7), x = x0 + col * cellX, y = yTop - row * cellY;
    if (hi[i]) { g.add(slab(roundedShape(0.086, 0.086, 0.025), 0.022, hi[i], x, y, zc)); continue; }
    (col === 0 || col === 6 ? end : week).push([new THREE.BoxGeometry(0.076, 0.076, 0.012), MX(x, y, zc + 0.006)]);
  }
  g.add(merged(week, "#D3C8F2"));
  g.add(merged(end, "#F3C3D5"));
  return g;
}

function clock() {
  const g = group(), cy = 3.0, R = 0.44;
  g.add(disc(R, 0.07, PAL.plum, 0, cy, 0, 28));
  g.add(disc(R - 0.035, 0.014, PAL.plumLight, 0, cy, 0.07, 28));
  g.add(disc(R - 0.075, 0.014, PAL.paper, 0, cy, 0.084, 28));
  for (let i = 0; i < 12; i++) {
    const a = (i * TAU) / 12, big = i % 3 === 0, rr = big ? 0.285 : 0.3;
    const t = plate(big ? 0.045 : 0.026, big ? 0.085 : 0.05, 0.01, big ? PAL.plumDark : PAL.plumLight, Math.sin(a) * rr, cy + Math.cos(a) * rr, 0.098);
    t.rotation.z = -a;
    g.add(t);
  }
  const hand = (len, w, color, z) => {
    const p = new THREE.Group();
    p.position.set(0, cy, z);
    p.add(slab(roundedShape(w, len + 0.05, w / 2), 0.01, color, 0, len / 2 - 0.025, 0));
    g.add(p);
    return p;
  };
  const hourP = hand(0.2, 0.05, PAL.ink, 0.11), minP = hand(0.29, 0.038, PAL.plumDark, 0.122), secP = hand(0.32, 0.014, PAL.red, 0.134);
  g.add(ell(0.04, 0.04, 0.025, GOLD, 0, cy, 0.14, undefined, 12));
  // feet: two little ears on top make it look like a friendly alarm clock
  g.add(ell(0.075, 0.075, 0.05, PAL.plumDark, -0.3, cy + 0.33, 0.05, undefined, 12));
  g.add(ell(0.075, 0.075, 0.05, PAL.plumDark, 0.3, cy + 0.33, 0.05, undefined, 12));
  const set = () => {
    const d = new Date(), s = d.getSeconds() + d.getMilliseconds() / 1000, m = d.getMinutes() + s / 60, h = (d.getHours() % 12) + m / 60;
    hourP.rotation.z = -(h / 12) * TAU; minP.rotation.z = -(m / 60) * TAU; secP.rotation.z = -(s / 60) * TAU;
  };
  set();
  g.userData.tick = set;
  return g;
}

function mirror() {
  const g = group(), W = 0.82, H = 1.3, cy = 2.5, t = 0.075;
  g.add(slab(roundedShape(W + 0.03, H + 0.03, W / 2 + 0.015, 0.1), 0.05, PAL.woodDark, 0, cy, 0));
  g.add(slab(roundedShape(W, H, W / 2, 0.09), 0.075, PAL.wood, 0, cy, 0));
  g.add(slab(roundedShape(W - 2 * t, H - 2 * t, W / 2 - t, 0.05), 0.04, PAL.glass, 0, cy, 0.04));
  // glass sheen: two soft diagonal strips and a sparkle
  const sheen = { transparent: true, opacity: 0.5 };
  g.add(slab(poly([[-0.2, -0.45], [-0.09, -0.45], [0.2, 0.12], [0.09, 0.12]]), 0.006, "#FFFFFF", 0, cy, 0.082, sheen));
  g.add(slab(poly([[-0.02, -0.45], [0.03, -0.45], [0.22, -0.08], [0.17, -0.08]]), 0.006, "#FFFFFF", 0, cy, 0.082, sheen));
  g.add(slab(poly(starPts(4, 0.07, 0.016)), 0.006, "#FFFFFF", 0.17, cy + 0.38, 0.082, { transparent: true, opacity: 0.85 }));
  // a little bow of gold at the top and tiny feet-like studs on the frame
  g.add(ell(0.05, 0.05, 0.035, GOLD, 0, cy + H / 2 - 0.02, 0.08, undefined, 12));
  for (const y of [-0.52, 0.0]) for (const s of [-1, 1]) g.add(ell(0.022, 0.022, 0.02, PAL.woodLight, s * (W / 2 - t / 2), cy + y, 0.078, undefined, 8));
  return g;
}

function painting() {
  const g = group(), W = 1.7, H = 1.1, cy = 2.5, cw = W - 0.2, ch = H - 0.2, hx = cw / 2, hy = ch / 2;
  g.add(slab(frameShape(W, H, 0.1, 0.05), 0.09, PAL.woodDark, 0, cy, 0));
  g.add(slab(frameShape(W - 0.2, H - 0.2, 0.025, 0.02), 0.055, PAL.woodLight, 0, cy, 0.0));
  // canvas: sky in two bands
  g.add(plate(cw, ch, 0.03, "#8DCDF1", 0, cy, 0));
  g.add(plate(cw, ch * 0.4, 0.034, "#BFE6F6", 0, cy - ch * 0.3, 0));
  let z = 0.034;
  g.add(disc(0.2, 0.01, "#FFE9A6", 0.38, cy + 0.2, z, 22));
  g.add(disc(0.135, 0.016, PAL.yellow, 0.38, cy + 0.2, z, 22));
  for (const [x, y, r] of [[-0.45, 0.24, 0.07], [-0.37, 0.27, 0.09], [-0.28, 0.24, 0.065], [0.0, 0.31, 0.05], [0.07, 0.33, 0.065], [0.14, 0.31, 0.045]]) g.add(disc(r, 0.014, "#FFFFFF", x, cy + y, z, 14));
  const base = -hy;
  const hill = (xl, xr, yl, yr, peak, color, zz) => {
    const s = new THREE.Shape();
    s.moveTo(xl, base);
    if (yl > base + 0.001) s.lineTo(xl, yl);
    s.bezierCurveTo(xl + (xr - xl) * 0.3, peak, xl + (xr - xl) * 0.7, peak, xr, yr);
    if (yr > base + 0.001) s.lineTo(xr, base);
    s.closePath();
    return slab(s, 0.012, color, 0, cy, zz);
  };
  g.add(hill(-hx, hx, -0.02, -0.14, 0.2, "#9CDAB0", z));
  g.add(hill(-0.25, hx, base, -0.18, 0.02, PAL.leafLight, z + 0.012));
  g.add(hill(-hx, 0.2, -0.16, base, 0.0, PAL.leaf, z + 0.024));
  g.add(hill(0.1, hx, base, -0.3, -0.18, PAL.leafDark, z + 0.036));
  // a tiny red-roofed house and two round trees
  const zt = z + 0.036;
  g.add(plate(0.16, 0.11, 0.014, PAL.cream, -0.3, cy - 0.15, zt));
  g.add(slab(poly([[-0.1, 0], [0.1, 0], [0, 0.09]]), 0.016, PAL.red, -0.3, cy - 0.095, zt));
  g.add(plate(0.035, 0.06, 0.016, PAL.woodDark, -0.3, cy - 0.175, zt));
  for (const [x, y, r] of [[0.1, -0.1, 0.09], [0.28, -0.14, 0.07]]) {
    g.add(plate(0.03, 0.12, 0.014, "#7B5333", x, cy + y - r * 0.9, zt));
    g.add(disc(r, 0.018, PAL.leafDark, x, cy + y, zt, 16));
    g.add(disc(r * 0.6, 0.02, PAL.leaf, x - r * 0.15, cy + y + r * 0.1, zt, 12));
  }
  // a brass plate under the frame
  g.add(rslab(0.3, 0.06, 0.02, 0.02, GOLD, 0, cy - H / 2 - 0.05, 0.02));
  return g;
}

function photoFrames() {
  const g = group();
  const frame = (w, h, col, x, y, tilt, paint) => {
    const f = new THREE.Group();
    f.position.set(x, y, 0);
    f.rotation.z = tilt;
    const t = 0.055;
    f.add(slab(frameShape(w, h, t, 0.035), 0.06, col, 0, 0, 0));
    f.add(plate(w - 2 * t + 0.01, h - 2 * t + 0.01, 0.03, "#FFFFFF", 0, 0, 0));
    paint(f, w - 2 * t, h - 2 * t);
    f.add(nailAt(0, h / 2 + 0.03, 0.03, 0.022));
    g.add(f);
  };
  // A: a portrait of a happy little person
  frame(0.66, 0.9, PAL.plum, -0.58, 2.46, 0.04, (f, w, h) => {
    f.add(plate(w, h, 0.034, "#FBD7E6", 0, 0, 0));
    f.add(slab(poly(Array.from({ length: 21 }, (_, i) => [Math.cos((i / 20) * PI) * w * 0.42, Math.sin((i / 20) * PI) * h * 0.2 - h / 2])), 0.012, PAL.teal, 0, 0, 0.034));
    f.add(disc(0.135, 0.014, "#5B3B2A", 0, 0.1, 0.034, 16));
    f.add(disc(0.115, 0.016, PAL.skin, 0, 0.07, 0.048, 16));
    f.add(slab(poly([[-0.125, 0.02], [0.125, 0.02], [0.1, 0.17], [0, 0.22], [-0.1, 0.17]]), 0.012, "#5B3B2A", 0, 0.07, 0.058));
    for (const s of [-1, 1]) { f.add(disc(0.014, 0.01, PAL.ink, s * 0.045, 0.07, 0.06, 8)); f.add(disc(0.022, 0.008, "#F5A3B8", s * 0.075, 0.035, 0.058, 8)); }
    f.add(bar(-0.025, 0.02, 0.025, 0.02, 0.014, 0.01, PAL.redDark, 0.06));
  });
  // B: a sunny landscape
  frame(0.88, 0.62, PAL.woodDark, 0.34, 2.9, -0.03, (f, w, h) => {
    f.add(plate(w, h, 0.034, "#9AD6F2", 0, 0, 0));
    f.add(disc(0.07, 0.012, PAL.yellow, 0.22, 0.1, 0.034, 14));
    const s = new THREE.Shape();
    s.moveTo(-w / 2, -h / 2); s.lineTo(-w / 2, -0.06); s.bezierCurveTo(-0.15, 0.2, 0.15, 0.1, w / 2, -0.1); s.lineTo(w / 2, -h / 2); s.closePath();
    f.add(slab(s, 0.012, PAL.leaf, 0, 0, 0.034));
    const s2 = new THREE.Shape();
    s2.moveTo(-0.1, -h / 2); s2.bezierCurveTo(-0.05, -0.1, 0.2, -0.12, w / 2, -0.18); s2.lineTo(w / 2, -h / 2); s2.closePath();
    f.add(slab(s2, 0.012, PAL.leafDark, 0, 0, 0.046));
    f.add(disc(0.05, 0.012, "#FFFFFF", -0.22, 0.14, 0.034, 10));
    f.add(disc(0.04, 0.012, "#FFFFFF", -0.16, 0.12, 0.034, 10));
  });
  // C: a heart on a warm card
  frame(0.52, 0.52, PAL.red, 0.52, 2.12, 0.07, (f, w, h) => {
    f.add(plate(w, h, 0.034, "#FFF0C9", 0, 0, 0));
    f.add(slab(heartShape(0.3), 0.016, PAL.red, 0, 0.0, 0.034));
    f.add(slab(poly(starPts(4, 0.05, 0.014)), 0.012, PAL.yellow, 0.14, 0.13, 0.034));
  });
  return g;
}

function wallShelf() {
  const g = group(), T = 2.45;       // top of the board
  g.add(plate(1.8, 0.08, 0.38, PAL.wood, 0, T - 0.04, 0));
  g.add(plate(1.8, 0.03, 0.02, PAL.woodDark, 0, T - 0.095, 0.0));
  for (const x of [-0.62, 0.62]) {
    const tri = new THREE.ExtrudeGeometry(poly([[0, -0.3], [0, 0], [0.3, 0]]), { depth: 0.05, bevelEnabled: false });
    tri.rotateY(-PI / 2);
    g.add(mesh(tri, PAL.woodDark, x + 0.025, T - 0.08, 0));
  }
  // the things on the shelf, drawn small and then scaled up a little so they read from afar
  const it = new THREE.Group();
  it.position.set(0, T, 0);
  it.scale.setScalar(1.2);
  const p = pot(PAL.pot, 0.12, 0.15, 0);
  p.position.set(-0.55, 0, 0.17);
  it.add(p);
  it.add(ell(0.1, 0.1, 0.1, PAL.leaf, -0.55, 0.26, 0.17, undefined, 12));
  it.add(ell(0.07, 0.08, 0.07, PAL.leafLight, -0.47, 0.31, 0.18, undefined, 12));
  it.add(ell(0.07, 0.08, 0.07, PAL.leafDark, -0.64, 0.3, 0.16, undefined, 12));
  it.add(ell(0.04, 0.04, 0.04, PAL.pink, -0.55, 0.4, 0.18, undefined, 8));
  // books: a row standing up, one leaning
  const books = [[0.07, 0.3, PAL.plum], [0.06, 0.25, PAL.red], [0.075, 0.33, PAL.teal], [0.06, 0.27, PAL.yellow]];
  let x = -0.24;
  for (const [w, h, c] of books) { it.add(plate(w, h, 0.2, c, x + w / 2, h / 2, 0.02)); it.add(plate(w + 0.004, 0.02, 0.202, "#FFFFFF", x + w / 2, h * 0.75, 0.019)); x += w + 0.004; }
  const lean = plate(0.06, 0.28, 0.18, PAL.orange, x + 0.12, 0.135, 0.03);
  lean.rotation.z = -0.28;
  it.add(lean);
  // a flat pair of books
  it.add(plate(0.3, 0.05, 0.2, PAL.plumLight, 0.42, 0.025, 0.02));
  it.add(plate(0.27, 0.045, 0.18, PAL.blue, 0.42, 0.075, 0.025));
  // a mug
  it.add(cyl(0.065, 0.058, 0.13, "#FFFFFF", 0.62, 0, 0.17, 16));
  it.add(cyl(0.056, 0.056, 0.01, "#6B4226", 0.62, 0.125, 0.17, 16));
  it.add(torus(0.04, 0.012, "#FFFFFF", 0.695, 0.065, 0.17, 0, 0, 12));
  it.add(ell(0.02, 0.02, 0.02, PAL.red, 0.62, 0.07, 0.232, undefined, 8));
  g.add(it);
  return g;
}

function safeHomeSign() {
  const g = group(), W = 1.7, H = 0.84, cy = 2.7;
  // hanging cords to a nail
  g.add(cord(-0.6, cy + H / 2 - 0.02, 0, cy + H / 2 + 0.55, 0.014, PAL.woodDark, 0.02));
  g.add(cord(0.6, cy + H / 2 - 0.02, 0, cy + H / 2 + 0.55, 0.014, PAL.woodDark, 0.02));
  g.add(nailAt(0, cy + H / 2 + 0.56, 0.03, 0.04));
  g.add(slab(roundedShape(W, H, 0.12), 0.07, PAL.woodDark, 0, cy, 0));
  g.add(slab(roundedShape(W - 0.12, H - 0.12, 0.08), 0.02, PAL.woodLight, 0, cy, 0.07));
  // wood grain
  for (const [y, w, x] of [[0.3, 1.1, 0.1], [-0.32, 0.9, -0.2], [0.12, 0.4, -0.45]]) g.add(bar(x - w / 2, cy + y, x + w / 2, cy + y, 0.012, 0.004, "#D9BC8E", 0.09));
  g.add(emblem(0.54, 0.62, 0.09, -0.52, cy + 0.02, PAL.plumDark, PAL.plum));
  // "words": pills in a row, a bold line and two soft ones
  const words = (y, t, color, list) => { let x = -0.14; for (const w of list) { g.add(bar(x, cy + y, x + w, cy + y, t, 0.012, color, 0.09)); x += w + t + 0.05; } };
  words(0.2, 0.1, PAL.ink, [0.14, 0.22, 0.1]);
  words(0.02, 0.06, PAL.woodDark, [0.2, 0.12, 0.2]);
  words(-0.13, 0.06, PAL.woodDark, [0.12, 0.22]);
  g.add(slab(heartShape(0.1), 0.014, PAL.red, 0.64, cy - 0.12, 0.09));
  for (const sx of [-1, 1]) for (const sy of [-1, 1]) g.add(ell(0.025, 0.025, 0.02, GOLD, sx * (W / 2 - 0.07), cy + sy * (H / 2 - 0.07), 0.075, undefined, 8));
  return g;
}

function bunting() {
  const g = group();
  const P0 = v3(-1.34, 4.08, 0.04), P1 = v3(0, 3.5, 0.04), P2 = v3(1.34, 4.08, 0.04);
  const curve = new THREE.QuadraticBezierCurve3(P0, P1, P2);
  g.add(tubeAlong(curve, 0.016, PAL.woodDark, 32));
  g.add(nailAt(P0.x, P0.y, 0.04, 0.045), nailAt(P2.x, P2.y, 0.04, 0.045));
  const cols = [PAL.plum, PAL.pink, PAL.yellow, PAL.teal, PAL.orange, PAL.blue, PAL.red, PAL.green];
  const dots = ["#FFFFFF", "#FFF0C9", "#FFFFFF", "#FFF0C9", "#FFFFFF", "#FFF0C9", "#FFFFFF", "#FFF0C9"];
  for (let i = 0; i < 8; i++) {
    const t = (i + 0.5) / 8, p = curve.getPoint(t), tan = curve.getTangent(t), a = Math.atan2(tan.y, tan.x);
    const f = new THREE.Group();
    f.position.set(p.x, p.y, 0.02);
    f.rotation.z = a;
    f.add(slab(poly([[-0.17, 0], [0.17, 0], [0, -0.46]]), 0.016, cols[i], 0, 0, 0));
    f.add(disc(0.04, 0.012, dots[i], 0, -0.12, 0.016, 12));
    f.add(slab(poly([[-0.06, -0.21], [0.06, -0.21], [0, -0.3]]), 0.012, dots[i], 0, 0, 0.016));
    g.add(f);
  }
  return g;
}

// ------------------------------------------------------------------------------------------------ festivals on the wall
function cnyLanterns() {
  const g = group();
  const lantern = (x, y, k = 1) => {
    const l = group(), rx = 0.3 * k, ry = 0.25 * k, rz = 0.2 * k;
    l.add(ell(rx, ry, rz, RED_CNY, 0, 0, 0, glowOpts("#C21C2E", 0.35), 22));
    for (const p of RIB_PHIS) l.add(rib(rx, ry, rz, p, GOLD, 0.011 * k));
    l.add(cyl(0.12 * k, 0.1 * k, 0.075 * k, GOLD, 0, ry - 0.025 * k));
    l.add(cyl(0.1 * k, 0.12 * k, 0.075 * k, GOLD, 0, -ry - 0.05 * k));
    l.add(torus(0.035 * k, 0.012 * k, GOLD, 0, ry + 0.095 * k, 0, 0, 0, 12));
    l.add(cyl(0.008, 0.008, 0.09 * k, GOLD, 0, -ry - 0.14 * k));
    l.add(ell(0.035 * k, 0.035 * k, 0.035 * k, GOLD, 0, -ry - 0.17 * k, 0, undefined, 10));
    l.add(cyl(0.012, 0.055 * k, 0.22 * k, RED_CNY, 0, -ry - 0.4 * k));
    l.add(cyl(0.056 * k, 0.056 * k, 0.018 * k, GOLD, 0, -ry - 0.4 * k));
    l.position.set(x, y, 0.2 * k);
    g.add(l);
    g.add(cord(x, y + ry + 0.11 * k, x, 4.14, 0.009, GOLD_DARK, 0.2 * k));
  };
  lantern(-0.62, 3.3);
  lantern(0.62, 3.3);
  // a gold fu-style diamond between them
  const d = group();
  d.add(slab(roundedShape(0.28, 0.28, 0.035), 0.03, GOLD, 0, 0, 0));
  d.add(slab(roundedShape(0.22, 0.22, 0.025), 0.02, RED_CNY, 0, 0, 0.03));
  d.add(slab(roundedShape(0.12, 0.12, 0.02), 0.014, GOLD, 0, 0, 0.05));
  for (const [x, y] of [[0, 0.065], [0, -0.065], [0.065, 0], [-0.065, 0]]) d.add(disc(0.014, 0.01, RED_CNY, x, y, 0.064, 8));
  d.rotation.z = PI / 4;
  d.position.set(0, 3.42, 0.04);
  g.add(d);
  g.add(cord(0, 3.62, 0, 4.14, 0.009, GOLD_DARK, 0.06));
  g.add(cord(0, 3.28, 0, 3.12, 0.008, GOLD_DARK, 0.06));
  g.add(cyl(0.01, 0.04, 0.16, RED_CNY, 0, 2.97, 0.06));
  return g;
}

function ketupat() {
  const g = group(), cy = 3.15, D = 0.12;
  const body = new THREE.Group();
  body.position.set(0, cy, D / 2 + 0.02);
  body.rotation.z = PI / 4;
  const S = 0.58;
  body.add(mesh(new THREE.BoxGeometry(S, S, D), "#2F8F58"));      // the woven pillow
  body.children[0].geometry.translate(0, 0, 0);
  // weave: light strips one way, mid strips the other, with the over/under done by little patches
  const z1 = D / 2 + 0.006, z2 = D / 2 + 0.014, off = [-0.19, 0, 0.19];
  for (const o of off) {
    body.add(mesh(new THREE.BoxGeometry(S + 0.004, 0.1, 0.012), "#8AD4A1", 0, o, z1));
    body.add(mesh(new THREE.BoxGeometry(0.1, S + 0.004, 0.012), "#4FB477", o, 0, z1 + 0.0));
  }
  off.forEach((ox, i) => off.forEach((oy, j) => { if ((i + j) % 2 === 0) body.add(mesh(new THREE.BoxGeometry(0.1, 0.1, 0.012), "#4FB477", ox, oy, z2)); else body.add(mesh(new THREE.BoxGeometry(0.1, 0.1, 0.012), "#8AD4A1", ox, oy, z2)); }));
  g.add(body);
  // cord, knot and tassels
  g.add(cord(0, cy + 0.42, 0, 4.14, 0.011, PAL.woodDark, 0.08));
  g.add(ell(0.045, 0.05, 0.04, PAL.red, 0, cy + 0.44, 0.08, undefined, 10));
  g.add(ell(0.04, 0.04, 0.035, PAL.yellow, 0, cy - 0.41, 0.08, undefined, 10));
  [[-0.07, PAL.red, 0.2], [0, PAL.yellow, 0.26], [0.07, PAL.pink, 0.2]].forEach(([x, c, len]) => {
    g.add(cyl(0.006, 0.006, len, c, x, cy - 0.41 - len, 0.08, 5));
    g.add(ell(0.025, 0.03, 0.025, c, x, cy - 0.41 - len, 0.08, undefined, 8));
  });
  return g;
}

function moonLanterns() {
  const g = group();
  const P0 = v3(-1.4, 4.05, 0.04), P1 = v3(0, 3.55, 0.04), P2 = v3(1.4, 4.05, 0.04);
  const curve = new THREE.QuadraticBezierCurve3(P0, P1, P2);
  g.add(tubeAlong(curve, 0.014, PAL.woodDark, 32));
  g.add(nailAt(P0.x, P0.y, 0.04, 0.045), nailAt(P2.x, P2.y, 0.04, 0.045));
  const specs = [[0.17, 0.33, "#F59A3B", "#FFE2A8", 0.16], [0.5, 0.37, "#F7C94A", "#FFF1C2", 0.2], [0.83, 0.33, "#EE6A5B", "#FFD1B8", 0.16]];
  for (const [t, r, c, rc, drop] of specs) {
    const p = curve.getPoint(t);
    const l = ballLantern(r, c, rc, GOLD_DARK, 0.62);
    l.position.set(p.x, p.y - drop - r * 1.06, 0.24);
    g.add(l);
    g.add(cord(p.x, p.y, p.x, p.y - drop - r * 0.7, 0.01, GOLD_DARK, 0.24));
  }
  return g;
}

function wreath() {
  const g = group(), cy = 2.8, R = 0.3;
  g.add(torus(R, 0.09, PAL.leafDark, 0, cy, 0.1, 0, 0, 28));
  const leafCols = [PAL.leaf, PAL.leafLight, PAL.leafDark, "#3A9E64"], leaves = [[], [], [], []], berries = [];
  for (let i = 0; i < 24; i++) {
    const a = (i / 24) * TAU, rr = R + (i % 2 ? 0.06 : -0.06) * 0.7;
    leaves[i % 4].push(blob(Math.cos(a) * rr, cy + Math.sin(a) * rr, 0.1 + (i % 3) * 0.015, 0.1, 0.034, 0.03, a + PI / 2 + (i % 2 ? 0.5 : -0.5)));
  }
  leaves.forEach((l, i) => g.add(merged(l, leafCols[i])));
  for (let i = 0; i < 9; i++) { const a = 0.5 + (i / 9) * TAU, rr = R + (i % 2 ? 0.03 : -0.03); berries.push(blob(Math.cos(a) * rr, cy + Math.sin(a) * rr, 0.2, 0.032)); }
  g.add(merged(berries, PAL.red));
  for (const a of [1.2, 3.5]) g.add(ell(0.04, 0.04, 0.04, GOLD, Math.cos(a) * (R - 0.01), cy + Math.sin(a) * (R - 0.01), 0.21, undefined, 10));
  // ribbon bow at the bottom
  const bx = 0, by = cy - R - 0.01, bz = 0.2;
  for (const s of [-1, 1]) {
    const loop = ell(0.1, 0.06, 0.03, PAL.red, bx + s * 0.095, by + 0.03, bz, undefined, 12);
    loop.rotation.z = s * 0.4;
    g.add(loop);
    const tail = slab(poly([[-0.035, 0], [0.035, 0], [0.05, -0.2], [0, -0.16], [-0.05, -0.2]]), 0.016, s > 0 ? PAL.redDark : PAL.red, bx + s * 0.05, by - 0.0, bz - 0.01);
    tail.rotation.z = s * 0.22;
    g.add(tail);
  }
  g.add(ell(0.05, 0.05, 0.04, PAL.redDark, bx, by + 0.02, bz + 0.03, undefined, 12));
  g.add(cord(0, cy + R + 0.09, 0, cy + R + 0.3, 0.01, PAL.red, 0.08));
  return g;
}

// ------------------------------------------------------------------------------------------------ flags
/** A bit of cloth that ripples: planes whose vertices are pushed in z by a travelling wave, and flat marks that ride on it. u is the distance from the pole. */
function makeCloth(into, base, length) {
  const planes = [], marks = [];
  const wave = (u, t) => 0.07 * (u / length) * Math.sin(u * 5.4 - t * 2.4);
  const slope = (u, t) => (wave(u + 0.02, t) - wave(u - 0.02, t)) / 0.04;
  return {
    /** A rectangle u0..u0+w across and v0..v0+h down from the top. */
    plane(u0, v0, w, h, color, dz = 0, sx = 12) {
      const geo = new THREE.PlaneGeometry(w, h, sx, 1);
      geo.translate(base.x + u0 + w / 2, base.y - v0 - h / 2, 0);
      const pos = geo.attributes.position, us = new Float32Array(pos.count);
      for (let i = 0; i < pos.count; i++) us[i] = pos.getX(i) - base.x;
      const m = mesh(geo, color, 0, 0, base.z + dz, { side: THREE.DoubleSide, emissive: color, emissiveIntensity: 0.3 });
      m.receiveShadow = false;
      planes.push({ m, us });
      into.add(m);
      return m;
    },
    /** A flat shape (points around its own middle) centred at (u, v) on the cloth. */
    mark(points, color, u, v, dz) {
      const m = mesh(new THREE.ShapeGeometry(poly(points)), color, base.x + u, base.y - v, base.z + dz, { side: THREE.DoubleSide, emissive: color, emissiveIntensity: 0.3 });
      m.castShadow = false; m.receiveShadow = false;
      marks.push({ m, u, dz });
      into.add(m);
      return m;
    },
    tick(t) {
      for (const { m, us } of planes) {
        const pos = m.geometry.attributes.position;
        for (let i = 0; i < pos.count; i++) pos.setZ(i, wave(us[i], t));
        pos.needsUpdate = true;
        m.geometry.computeVertexNormals();
      }
      for (const k of marks) { k.m.position.z = base.z + k.dz + wave(k.u, t); k.m.rotation.y = -Math.atan(slope(k.u, t)); }
    },
  };
}
/** A wall-mounted pole with a gold ball on top and two brackets to the wall. */
function flagPole(x, y0, y1) {
  const g = group();
  g.add(cyl(0.024, 0.024, y1 - y0, "#8B6B4A", x, y0, 0.13, 10));
  g.add(ell(0.05, 0.05, 0.05, GOLD, x, y1 + 0.03, 0.13, undefined, 12));
  for (const y of [y0 + 0.2, y1 - 0.2]) {
    g.add(plate(0.05, 0.05, 0.13, PAL.woodDark, x, y, 0));
    g.add(disc(0.055, 0.02, GOLD_DARK, x, y, 0, 12));
  }
  return g;
}

function sgFlag() {
  const g = group(), W = 1.62, H = 1.08, poleX = -0.92, top = 3.45, k = W / 1.5;
  g.add(flagPole(poleX, 2.1, 3.7));
  const cloth = makeCloth(g, v3(poleX + 0.03, top, 0.13), W);
  const RED = "#EF3340", WHITE = "#FFFFFF";
  cloth.plane(0, 0, W, H / 2, RED);
  cloth.plane(0, H / 2, W, H / 2, WHITE);
  // the white crescent and five white stars sit in the upper left of the red band
  const cv = H / 4, R = 0.17 * k, r = 0.14 * k, d = 0.07 * k, cu = 0.31 * k;
  cloth.mark(crescentPts(R, r, d), WHITE, cu, cv, 0.012);
  const sc = cu + d + 0.01, ringR = 0.078 * k;
  for (let i = 0; i < 5; i++) {
    const a = PI / 2 + (i * TAU) / 5;
    cloth.mark(starPts(5, 0.04 * k, 0.016 * k, a).map(([x, y]) => [x + Math.cos(a) * ringR, y + Math.sin(a) * ringR]), WHITE, sc, cv, 0.012);
  }
  cloth.tick(0);
  g.userData.tick = (t) => cloth.tick(t);
  return g;
}

function myFlag() {
  const g = group(), W = 1.62, H = 0.81, poleX = -0.92, top = 3.35;
  g.add(flagPole(poleX, 2.2, 3.57));
  const cloth = makeCloth(g, v3(poleX + 0.03, top, 0.13), W);
  const RED = "#CC0001", WHITE = "#FFFFFF", BLUE = "#010066", YEL = "#FFCC00", sh = H / 14;
  for (let i = 0; i < 14; i++) cloth.plane(0, i * sh, W, sh, i % 2 ? WHITE : RED);
  // the dark-blue canton covers the top eight stripes and half the length
  const cw = W / 2, chh = sh * 8;
  cloth.plane(0, 0, cw, chh, BLUE, 0.008, 8);
  // yellow crescent (opening to the right) with a 14-point star in its mouth
  const R = 0.175, r = 0.143, d = 0.07, cu = cw / 2 - 0.05, cv = chh / 2;
  cloth.mark(crescentPts(R, r, d), YEL, cu, cv, 0.016);
  cloth.mark(starPts(14, 0.105, 0.052), YEL, cu + d + 0.04, cv, 0.016);
  cloth.tick(0);
  g.userData.tick = (t) => cloth.tick(t);
  return g;
}

/** Wau bulan: a traditional Malay moon kite. A dome of bright layered wings, a crescent (the moon) beneath, a long tail of ribbons. */
function wau() {
  const g = group();
  const RED = "#D42A3A", YEL = "#F7C531", GRN = "#2FA36B", BLU = "#2E5FC8", PINK = "#F06A9F", CREAM = "#FFF7E6";
  const outline = [];
  for (let i = 0; i <= 28; i++) {
    const th = PI - (PI * i) / 28, x = 0.8 * Math.cos(th);
    outline.push([x, 3.08 + 0.62 * Math.pow(Math.max(0, Math.sin(th)), 0.8) + 0.14 * Math.pow(Math.max(0, 1 - Math.abs(x) / 0.28), 1.4)]);
  }
  outline.push([0.93, 3.17], [0.86, 3.0], [0.7, 2.95], [0.45, 2.9], [0.2, 2.87], [0, 2.86], [-0.2, 2.87], [-0.45, 2.9], [-0.7, 2.95], [-0.86, 3.0], [-0.93, 3.17]);
  const cx = 0, cy = 3.28;
  g.add(slab(poly(outline), 0.03, RED, 0, 0, 0));
  g.add(slab(poly(scalePts(outline, 0.9, cx, cy)), 0.02, YEL, 0, 0, 0.03));
  g.add(slab(poly(scalePts(outline, 0.8, cx, cy)), 0.02, BLU, 0, 0, 0.05));
  g.add(slab(poly(scalePts(outline, 0.62, cx, cy + 0.03)), 0.02, GRN, 0, 0, 0.07));
  // a big flower in the middle, small leaves and dots on either side
  for (let i = 0; i < 8; i++) {
    const a = (i * TAU) / 8, p = slab(leafShape(0.25, 0.06), 0.016, i % 2 ? PINK : CREAM, Math.cos(a) * 0.04, 3.3 + Math.sin(a) * 0.04, 0.09);
    p.rotation.z = a - PI / 2;
    g.add(p);
  }
  g.add(disc(0.085, 0.02, YEL, 0, 3.3, 0.09, 16));
  g.add(disc(0.04, 0.02, RED, 0, 3.3, 0.108, 12));
  for (const s of [-1, 1]) {
    for (let j = 0; j < 3; j++) {
      const l = slab(leafShape(0.2, 0.045), 0.014, j === 1 ? YEL : CREAM, s * (0.4 + j * 0.08), 3.12 + j * 0.1, 0.09);
      l.rotation.z = -s * (0.9 + j * 0.25);
      g.add(l);
    }
    g.add(disc(0.05, 0.016, PINK, s * 0.6, 3.5, 0.09, 12));
    g.add(disc(0.026, 0.018, CREAM, s * 0.6, 3.5, 0.106, 10));
    g.add(ell(0.04, 0.04, 0.04, PINK, s * 0.92, 3.1, 0.045, undefined, 10));
  }
  // the crescent moon (bulan) under the wings: opens upward
  const cc = 2.55, moon = crescentPts(0.58, 0.49, 0.12).map(([x, y]) => [-y, x]);
  g.add(slab(poly(moon), 0.03, GRN, 0, cc, 0.0));
  g.add(slab(poly(scalePts(moon, 0.82, 0, 0.1)), 0.02, RED, 0, cc, 0.03));
  g.add(slab(poly(scalePts(moon, 0.6, 0, 0.18)), 0.02, YEL, 0, cc, 0.05));
  for (let i = 0; i < 5; i++) { const a = (215 + i * 27.5) * (PI / 180); g.add(disc(0.034, 0.016, CREAM, Math.cos(a) * 0.535, cc + Math.sin(a) * 0.535, 0.04, 10)); }
  // the spine: a bamboo stick down the middle, with a gold tip
  g.add(bar(0, 3.82, 0, 1.97, 0.04, 0.02, PAL.woodDark, 0.0));
  g.add(ell(0.05, 0.05, 0.05, GOLD, 0, 3.92, 0.055, undefined, 12));
  // the tail: a wavy cord with ribbons that sway
  const curve = new THREE.CatmullRomCurve3([v3(0, 1.97, 0.03), v3(0.1, 1.84, 0.04), v3(-0.09, 1.7, 0.04), v3(0.09, 1.56, 0.04), v3(-0.07, 1.45, 0.04), v3(0.03, 1.34, 0.04)]);
  g.add(tubeAlong(curve, 0.014, PAL.woodDark, 28));
  const ribbons = [];
  const rc = [PINK, YEL, GRN, BLU, RED];
  for (let i = 0; i < 5; i++) {
    const p = curve.getPoint(0.08 + (i / 4) * 0.9), pivot = new THREE.Group(), side = i % 2 ? 1 : -1;
    pivot.position.set(p.x, p.y, 0.06);
    pivot.add(slab(poly([[-0.065, 0], [0.065, 0], [0.065, -0.3], [0, -0.22], [-0.065, -0.3]]), 0.014, rc[i], side * 0.09, 0, 0));
    pivot.add(bar(0, -0.01, side * 0.09, -0.01, 0.022, 0.012, PAL.woodDark, 0.0));
    g.add(pivot);
    ribbons.push(pivot);
  }
  g.userData.tick = (t) => ribbons.forEach((r, i) => { r.rotation.z = 0.16 * Math.sin(t * 1.7 + i * 0.9); });
  return g;
}

// ------------------------------------------------------------------------------------------------ festivals on the floor
/** A teardrop flame (outer orange, inner yellow, plus a soft halo). Its origin is the middle of the flame's round part. */
function flame(s, halo = true) {
  const f = new THREE.Group(), body = new THREE.SphereGeometry(1, 10, 8), tip = new THREE.ConeGeometry(1, 1, 10);
  const mk = (k, color) => {
    const geo = mergeGeo([[body, MX(0, 0, 0, 0, 0, 0, 0.42 * k)], [tip, MX(0, 0.5 * k, 0, 0, 0, 0, 0.4 * k, k, 0.4 * k)]]);
    return new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color }));
  };
  f.add(mk(s, "#FF9A2E"));
  const inner = mk(s * 0.55, "#FFE27A");
  inner.position.y = -0.03 * s;
  f.add(inner);
  const h = halo ? glow(1.45 * s, "#FFC56B", 0, 0.9 * s, 0, 0.1) : null;
  if (h) f.add(h);
  return { g: f, halo: h, base: s };
}
const flicker = (fl, t, ph) => {
  const s = 1 + 0.13 * Math.sin(t * 9 + ph) + 0.07 * Math.sin(t * 17 + ph * 2);
  fl.g.scale.set(1.04 - 0.4 * (s - 1), s, 1.04 - 0.4 * (s - 1));
  fl.g.rotation.z = 0.07 * Math.sin(t * 5.2 + ph);
  if (fl.halo) fl.halo.material.opacity = 0.1 + 0.035 * Math.sin(t * 7 + ph);
};

function mandarinTree() {
  const g = group(), ORANGE = "#F7881F";
  // a gold pot with a red ribbon and bow
  g.add(cyl(0.25, 0.19, 0.3, GOLD, 0, 0, 0, 20));
  g.add(cyl(0.28, 0.28, 0.05, "#F0C24C", 0, 0.27, 0, 20));
  g.add(cyl(0.245, 0.245, 0.02, "#5B3B2A", 0, 0.31, 0, 20));
  g.add(cyl(0.232, 0.218, 0.07, RED_CNY, 0, 0.11, 0, 20));
  for (const s of [-1, 1]) {
    const loop = ell(0.07, 0.045, 0.025, RED_CNY, s * 0.065, 0.16, 0.225, undefined, 10);
    loop.rotation.z = s * 0.45;
    g.add(loop);
    const tail = slab(poly([[-0.025, 0], [0.025, 0], [0.035, -0.12], [0, -0.09], [-0.035, -0.12]]), 0.014, PAL.redDark, s * 0.035, 0.14, 0.225);
    tail.rotation.z = s * 0.2;
    g.add(tail);
  }
  g.add(ell(0.033, 0.033, 0.03, PAL.redDark, 0, 0.16, 0.235, undefined, 10));
  // trunk and a round crown of leaves
  g.add(cyl(0.035, 0.05, 0.5, "#7B5333", 0, 0.3, 0, 8));
  const cy = 1.02;
  g.add(ell(0.38, 0.34, 0.38, PAL.leafDark, 0, cy, 0, undefined, 18));
  const bumps = [[-0.22, -0.06, 0.1, 0.22, PAL.leaf], [0.23, -0.04, 0.08, 0.22, PAL.leafDark], [0.0, 0.2, -0.12, 0.22, PAL.leaf], [-0.08, -0.12, 0.26, 0.2, PAL.leafDark], [0.12, 0.12, 0.2, 0.2, PAL.leaf], [-0.2, 0.14, -0.1, 0.2, PAL.leafDark], [0.2, 0.18, -0.08, 0.18, "#3FA566"]];
  for (const [x, y, z, r, c] of bumps) g.add(ell(r, r * 0.92, r, c, x, cy + y, z, undefined, 12));
  // mandarins: little orange balls all over the front and sides
  const N = 30, pts = [], fruit = [], stems = [];
  for (let i = 0; i < N; i++) {
    const y = 1 - (2 * (i + 0.5)) / N, rho = Math.sqrt(1 - y * y), th = i * 2.39996;
    pts.push([Math.cos(th) * rho, y, Math.sin(th) * rho]);
  }
  for (const [x, y, z] of pts) {
    if (y < -0.5 || z < -0.35) continue;
    fruit.push(blob(x * 0.39, cy + y * 0.35, z * 0.39, 0.068, 0.062, 0.068));
    stems.push(blob(x * 0.39, cy + y * 0.35 + 0.058, z * 0.39, 0.02, 0.012, 0.02));
  }
  g.add(merged(fruit, ORANGE), merged(stems, PAL.leaf));
  // lucky red packets hanging from the branches
  for (const [x, z] of [[-0.2, 0.25], [0.24, 0.2]]) {
    g.add(cyl(0.004, 0.004, 0.08, GOLD, x, cy - 0.34, z, 4));
    g.add(plate(0.09, 0.13, 0.016, RED_CNY, x, cy - 0.44, z - 0.008));
    g.add(disc(0.026, 0.012, GOLD, x, cy - 0.44, z + 0.006, 10));
  }
  return g;
}

function pelita() {
  const g = group(), flames = [];
  const BAMBOO = "#D8C874", NODE = "#A8964A";
  // a woven round mat for the lamps to stand on
  g.add(cyl(0.45, 0.45, 0.03, PAL.woodLight, 0, 0, 0, 24));
  g.add(cyl(0.45, 0.45, 0.012, PAL.woodDark, 0, 0.03, 0, 24));
  g.add(cyl(0.4, 0.4, 0.014, PAL.woodLight, 0, 0.03, 0, 24));
  const spots = [[0.0, -0.1, 0.52, 0.105, 0], [-0.24, 0.17, 0.36, 0.088, 2.1], [0.25, 0.14, 0.27, 0.082, 4.2]];
  for (const [x, z, h, r, ph] of spots) {
    const y0 = 0.044;
    g.add(cyl(r, r, h, BAMBOO, x, y0, z, 14));
    g.add(cyl(r * 1.1, r * 1.1, 0.025, NODE, x, y0 + h * 0.34, z, 14));
    g.add(cyl(r * 1.1, r * 1.1, 0.03, NODE, x, y0 + h - 0.03, z, 14));
    g.add(cyl(r * 1.1, r * 1.1, 0.025, NODE, x, y0, z, 14));
    g.add(cyl(r * 0.78, r * 0.78, 0.01, "#5A3A14", x, y0 + h, z, 12));
    g.add(cyl(0.009, 0.009, 0.06, "#2B2118", x, y0 + h, z, 5));
    const f = flame(0.11);
    f.g.position.set(x, y0 + h + 0.14, z);
    g.add(f.g);
    flames.push([f, ph]);
  }
  // a few red hibiscus petals and green leaves on the mat
  const petals = [], centres = [], leaves = [];
  for (const [x, z, a] of [[0.1, 0.33, 0.2], [0.33, -0.18, 1.2]]) {
    for (let i = 0; i < 5; i++) { const b = a + (i * TAU) / 5; petals.push(blob(x + Math.cos(b) * 0.04, 0.05, z + Math.sin(b) * 0.04, 0.04, 0.012, 0.028, 0, -b)); }
    centres.push(blob(x, 0.062, z, 0.014));
  }
  for (const [x, z, a] of [[-0.12, 0.34, 0.5], [0.0, 0.32, -0.3], [-0.34, -0.15, 1.4]]) leaves.push(blob(x, 0.047, z, 0.07, 0.01, 0.025, 0, a));
  g.add(merged(petals, PAL.red), merged(centres, PAL.yellow), merged(leaves, PAL.leaf));
  g.userData.tick = (t) => flames.forEach(([f, ph]) => flicker(f, t, ph));
  return g;
}

function diyaLamp(r, color = "#C9674A") {
  const g = group(), h = r * 0.55;
  const bowl = new THREE.Mesh(new THREE.SphereGeometry(1, 18, 8, 0, TAU, PI / 2, PI / 2), mat(color, { side: THREE.DoubleSide }));
  bowl.scale.set(r, h, r);
  bowl.position.y = h;
  bowl.castShadow = true; bowl.receiveShadow = true;
  g.add(bowl);
  g.add(cyl(r * 0.5, r * 0.58, 0.02, "#B2553B", 0, 0, 0, 14));
  g.add(torus(r * 0.99, 0.014, GOLD, 0, h, 0, PI / 2, 0, 22));
  g.add(cyl(r * 0.94, r * 0.94, 0.008, "#6B3F12", 0, h - 0.012, 0, 18));
  // the pinched spout where the wick rests
  const sp = cone(r * 0.3, r * 0.75, color, 0, 0, 0, 10);
  sp.rotation.x = PI / 2;
  sp.position.set(0, h - 0.02, r * 1.05);
  g.add(sp);
  g.add(ell(0.012, 0.012, 0.03, "#2B2118", 0, h + 0.005, r * 1.12, undefined, 6));
  // gold dots round the belly
  g.add(merged(Array.from({ length: 7 }, (_, i) => { const a = (i - 3) * 0.34; return blob(Math.sin(a) * r * 0.9, h * 0.62, Math.cos(a) * r * 0.9, 0.012); }), GOLD));
  return g;
}
function diyaSet() {
  const g = group(), flames = [];
  const spots = [[0.0, -0.13, 0.19, "#C9674A", 0.0], [-0.28, 0.14, 0.14, "#D4785A", 2.4], [0.28, 0.17, 0.13, "#B95B41", 4.4]];
  for (const [x, z, r, c, ph] of spots) {
    const d = diyaLamp(r, c);
    d.position.set(x, 0, z);
    g.add(d);
    const f = flame(r * 0.62);
    f.g.position.set(x, r * 0.55 + 0.11, z + r * 1.12);
    g.add(f.g);
    flames.push([f, ph]);
  }
  // marigold flowers and loose petals around the lamps
  const flowerA = [], flowerB = [], hearts = [];
  for (const [x, z, r] of [[-0.33, -0.22, 0.085], [0.33, -0.2, 0.075], [0.02, 0.38, 0.07], [-0.1, 0.3, 0.05]]) {
    for (let i = 0; i < 7; i++) { const a = (i * TAU) / 7; (i % 2 ? flowerA : flowerB).push(blob(x + Math.cos(a) * r * 0.62, r * 0.35, z + Math.sin(a) * r * 0.62, r * 0.55, r * 0.45, r * 0.55)); }
    hearts.push(blob(x, r * 0.5, z, r * 0.62, r * 0.55, r * 0.62));
  }
  g.add(merged(flowerA, "#F5A623"), merged(flowerB, "#FFC23A"), merged(hearts, "#EE7B12"));
  const loose = [[], [], []];
  for (let i = 0; i < 16; i++) {
    const a = i * 2.4, rad = 0.3 + ((i * 37) % 10) * 0.014;
    loose[i % 3].push(blob(Math.cos(a) * rad, 0.012, Math.sin(a) * rad * 0.95, 0.036, 0.01, 0.022, 0, a * 2));
  }
  g.add(merged(loose[0], PAL.yellow), merged(loose[1], "#F08A1F"), merged(loose[2], "#F5A623"));
  g.add(merged([[-0.36, 0.05, 0.4], [0.37, 0.0, -0.5], [-0.15, -0.35, 1.2], [0.15, -0.36, 1.9]].map(([x, z, a]) => blob(x, 0.012, z, 0.07, 0.012, 0.03, 0, a)), PAL.leaf));
  g.userData.tick = (t) => flames.forEach(([f, ph]) => flicker(f, t, ph));
  return g;
}

function rangoli() {
  const g = group();
  const parts = new Map();
  const add = (color, geo, m) => { if (!parts.has(color)) parts.set(color, []); parts.get(color).push([geo, m]); };
  const flat = (shp, d) => { const geo = new THREE.ExtrudeGeometry(shp, { depth: d, bevelEnabled: false, curveSegments: 8 }); geo.rotateX(-PI / 2); return geo; };
  const discAt = (r, y0, d, color, x = 0, z = 0) => add(color, new THREE.CylinderGeometry(r, r, d, r > 0.5 ? 64 : r > 0.2 ? 40 : 14), MX(x, y0 + d / 2, z));
  const ringAt = (rIn, rOut, y0, d, color) => {
    const s = new THREE.Shape(); s.absarc(0, 0, rOut, 0, TAU, false);
    const h = new THREE.Path(); h.absarc(0, 0, rIn, 0, TAU, true); s.holes.push(h);
    add(color, flat(s, d), MX(0, y0, 0));
  };
  const petals = (n, L, hw, r0, y0, d, color, off = 0) => {
    for (let i = 0; i < n; i++) { const geo = flat(leafShape(L, hw), d); geo.translate(0, 0, -r0); add(color, geo, MX(0, y0, 0, 0, off + (i * TAU) / n, 0)); }
  };
  const PURPLE = "#6B4BC0", ORANGE = "#F08A4B", PINK_ = "#E26BA6", YEL = "#F3C33C", WHITE = "#FFFDF7";
  const L1 = 0.016, L2 = 0.022, L3 = 0.028, L4 = 0.034, L5 = 0.039, L6 = 0.043, L7 = 0.047;
  discAt(0.94, 0, L1, PURPLE);
  ringAt(0.88, 0.925, L1, 0.006, WHITE);
  for (let i = 0; i < 32; i++) { const a = (i * TAU) / 32; discAt(0.021, L1, 0.006, YEL, Math.cos(a) * 0.835, Math.sin(a) * 0.835); }
  petals(16, 0.34, 0.075, 0.46, L1, 0.006, ORANGE);
  petals(16, 0.2, 0.045, 0.52, L1, 0.006, PINK_, PI / 16);
  ringAt(0.42, 0.5, L2, 0.006, YEL);
  petals(12, 0.27, 0.07, 0.25, L3, 0.006, PINK_);
  petals(12, 0.13, 0.03, 0.3, L3, 0.006, WHITE, PI / 12);
  for (let i = 0; i < 24; i++) { const a = (i * TAU) / 24; discAt(0.015, L2, 0.006, PINK_, Math.cos(a) * 0.46, Math.sin(a) * 0.46); }
  discAt(0.27, L3 + 0.006 - 0.001, 0.006, WHITE);
  { const s = poly(starPts(8, 0.24, 0.12)); add(PURPLE, flat(s, 0.005), MX(0, L5, 0)); }
  discAt(0.105, L5 + 0.005 - 0.001, 0.005, ORANGE);
  discAt(0.05, L6 + 0.005 - 0.001, 0.005, YEL);
  discAt(0.02, L7 - 0.001, 0.004, WHITE);
  for (const [color, list] of parts) g.add(merged(list, color));
  return g;
}

function lanternStand() {
  const g = group(), swing = [], top = 1.38;
  g.add(cyl(0.24, 0.28, 0.07, PAL.woodDark, 0, 0, 0, 18));
  g.add(cyl(0.17, 0.22, 0.06, PAL.wood, 0, 0.07, 0, 18));
  g.add(cyl(0.03, 0.042, 1.3, PAL.wood, 0, 0.1, 0, 10));
  g.add(cyl(0.052, 0.052, 0.04, GOLD, 0, 0.5, 0, 10));
  // a cross arm with gold tips
  const arm = mesh(new THREE.CylinderGeometry(0.022, 0.022, 0.8, 8), PAL.woodDark, 0, top, 0);
  arm.rotation.z = PI / 2;
  g.add(arm);
  for (const s of [-1, 1]) g.add(ell(0.04, 0.04, 0.04, GOLD, s * 0.41, top, 0, undefined, 10));
  g.add(ell(0.055, 0.055, 0.055, GOLD, 0, top + 0.07, 0, undefined, 10));
  // the round paper lantern, on the left
  const round = new THREE.Group();
  round.position.set(-0.23, top, 0);
  const lamp = ballLantern(0.17, "#F59A3B", "#FFE2A8", RED_CNY, 1);
  lamp.position.set(0, -0.36, 0);
  round.add(lamp);
  round.add(cyl(0.006, 0.006, 0.16, GOLD_DARK, 0, -0.17, 0, 4));
  g.add(round);
  // the rabbit lantern, on the right
  const rab = new THREE.Group();
  rab.position.set(0.23, top, 0);
  const R = new THREE.Group();
  R.position.set(0, -0.66, 0);
  R.scale.setScalar(1.08);
  const warm = glowOpts("#FFD9B0", 0.55), body = "#FFF3E6";
  R.add(ell(0.15, 0.13, 0.13, body, 0, 0, 0, warm, 16));
  R.add(ell(0.1, 0.095, 0.09, body, 0, 0.16, 0.06, warm, 14));
  for (const s of [-1, 1]) {
    const ear = ell(0.034, 0.14, 0.022, body, s * 0.055, 0.35, 0.05, warm, 10);
    ear.rotation.z = -s * 0.22;
    R.add(ear);
    const inner = ell(0.017, 0.1, 0.012, "#F7A8C0", s * 0.058, 0.35, 0.068, undefined, 8);
    inner.rotation.z = -s * 0.22;
    R.add(inner);
    R.add(ell(0.014, 0.018, 0.012, PAL.red, s * 0.04, 0.185, 0.14, undefined, 8));
    R.add(ell(0.03, 0.02, 0.012, "#F7A8C0", s * 0.07, 0.15, 0.13, undefined, 8));
    R.add(ell(0.04, 0.03, 0.04, body, s * 0.08, -0.12, 0.09, undefined, 8));
  }
  R.add(ell(0.014, 0.012, 0.012, "#F7A8C0", 0, 0.165, 0.152, undefined, 6));
  R.add(ell(0.05, 0.05, 0.05, "#FFFFFF", 0, -0.01, -0.14, undefined, 10));
  const halo = glow(0.2, "#FFC76B", 0, 0.08, 0, 0.1);
  halo.scale.z = 0.6;
  R.add(halo);
  rab.add(R);
  rab.add(cyl(0.006, 0.006, 0.42, GOLD_DARK, 0, -0.42, 0, 4));
  g.add(rab);
  swing.push([round, 0], [rab, 1.7]);
  g.userData.tick = (t) => swing.forEach(([o, ph]) => { o.rotation.z = 0.035 * Math.sin(t * 1.4 + ph); });
  return g;
}

function xmasTree() {
  const g = group();
  // red base, a gold band, and presents
  g.add(cyl(0.2, 0.17, 0.17, PAL.red, 0, 0, 0, 16));
  g.add(cyl(0.205, 0.205, 0.025, GOLD, 0, 0.1, 0, 16));
  g.add(cyl(0.05, 0.06, 0.2, "#7B5333", 0, 0.15, 0, 8));
  const tiers = [[0.44, 0.62, 0.22, "#2F8F58"], [0.35, 0.56, 0.6, "#3AA467"], [0.26, 0.5, 0.96, "#4FB477"], [0.16, 0.38, 1.3, "#62C48A"]];
  const bauble = [PAL.red, GOLD, PAL.blue, PAL.pink, "#FFFFFF"];
  let k = 0;
  tiers.forEach(([R, H, y0, c], ti) => {
    g.add(cone(R, H, c, 0, y0, 0, 16));
    const f = 0.3, gr = R * (1 - f) + 0.004;
    g.add(torus(gr, 0.014, "#FFE9A0", 0, y0 + H * f, 0, PI / 2, 0, 24));
    const n = ti === 3 ? 3 : 5;
    for (let i = 0; i < n; i++) {
      const a = (i * TAU) / n + ti * 0.9, ff = i % 2 ? 0.14 : 0.52, rad = R * (1 - ff) + 0.025;
      g.add(sphere(ti === 3 ? 0.038 : 0.05, bauble[k++ % 5], Math.cos(a) * rad, y0 + H * ff, Math.sin(a) * rad, 1, 12));
    }
  });
  const star = group(slab(poly(starPts(5, 0.14, 0.06)), 0.05, GOLD, 0, 0, -0.025));
  star.position.set(0, 1.78, 0);
  g.add(star);
  g.add(glow(0.2, "#FFE9A0", 0, 1.78, 0, 0.08));
  for (const [x, z, w, c, r] of [[0.3, 0.3, 0.15, PAL.plum, PAL.gold], [-0.32, 0.27, 0.12, PAL.teal, PAL.red]]) {
    const b = new THREE.Mesh(new THREE.BoxGeometry(w, w * 0.9, w), mat(c));
    at(b, x, w * 0.45, z);
    b.rotation.y = x > 0 ? 0.4 : -0.3;
    g.add(b);
    const rb = new THREE.Mesh(new THREE.BoxGeometry(w * 1.04, w * 0.14, w * 0.2), mat(r));
    at(rb, x, w * 0.45, z);
    rb.rotation.y = b.rotation.y;
    g.add(rb);
    const rb2 = new THREE.Mesh(new THREE.BoxGeometry(w * 0.2, w * 0.14, w * 1.04), mat(r));
    at(rb2, x, w * 0.45, z);
    rb2.rotation.y = b.rotation.y;
    g.add(rb2);
  }
  g.userData.tick = (t) => { star.rotation.y = 0.5 * Math.sin(t * 1.1); };
  return g;
}

function merlion() {
  const g = group(), zS = -0.08, WHITE = "#FFFFFF", MANE = "#DDD6F2", SCALE = "#A9C7EE", FIN = "#8FBBEA";
  const wh = (c) => glowOpts(c, 0.16);
  // the pool: a stone rim and blue water
  g.add(cyl(0.46, 0.46, 0.11, "#EFEAF8", 0, 0, 0, 28));
  g.add(cyl(0.41, 0.41, 0.012, "#5FB8EC", 0, 0.09, 0, 28));
  // a rocky plinth with foam
  g.add(cyl(0.2, 0.27, 0.26, "#B6B0C8", 0, 0.09, zS, 14));
  g.add(torus(0.28, 0.026, "#FFFFFF", 0, 0.105, zS, PI / 2, 0, 20));
  for (const [x, z, r] of [[-0.24, 0.02, 0.07], [0.24, 0.04, 0.06], [0.0, 0.17, 0.05]]) g.add(ell(r, r * 0.7, r, "#A39DB8", x, 0.12, z + zS, undefined, 8));
  // the fish body: fat, curving up from the plinth to the neck, with rows of blue scales
  const spine = new THREE.CatmullRomCurve3([v3(0, 0.42, zS + 0.0), v3(0, 0.55, zS + 0.05), v3(0, 0.7, zS + 0.08), v3(0, 0.84, zS + 0.07)]);
  const whites = [];
  for (let i = 0; i <= 7; i++) {
    const p = spine.getPoint(i / 7), r = 0.235 - i * 0.014;
    whites.push(blob(p.x, p.y, p.z, r, r * 0.92, r));
  }
  const sc = [], ball = new THREE.SphereGeometry(1, 8, 6);
  for (let row = 0; row < 5; row++) for (let c = -1; c <= 1; c++) {
    const p = spine.getPoint(0.04 + row * 0.2), r = 0.235 - (0.04 + row * 0.2) * 7 * 0.014, x = c * 0.09 + (row % 2) * 0.045 - 0.022;
    if (Math.abs(x) > 0.13) continue;
    const z = p.z + Math.sqrt(Math.max(0.0001, r * r - x * x)) * 0.99;
    sc.push([ball, MX(x, p.y, z, 0, Math.atan2(x, z - p.z), 0, 0.05, 0.036, 0.016)]);
  }
  g.add(merged(sc, SCALE));
  // the tail: curls up and round behind to one side, ending in a fan
  const tail = new THREE.CatmullRomCurve3([v3(0.0, 0.42, zS - 0.1), v3(0.1, 0.42, zS - 0.22), v3(0.22, 0.58, zS - 0.25), v3(0.27, 0.82, zS - 0.2), v3(0.25, 1.02, zS - 0.12)]);
  for (let i = 0; i <= 6; i++) { const p = tail.getPoint(i / 6), r = 0.14 - i * 0.016; whites.push(blob(p.x, p.y, p.z, r)); }
  g.add(merged(whites, WHITE, wh(WHITE)));
  const fin = new THREE.Shape();
  fin.moveTo(0, 0); fin.bezierCurveTo(-0.1, 0.05, -0.18, 0.2, -0.13, 0.31); fin.bezierCurveTo(-0.08, 0.25, -0.04, 0.27, 0, 0.36); fin.bezierCurveTo(0.04, 0.27, 0.08, 0.25, 0.13, 0.31); fin.bezierCurveTo(0.18, 0.2, 0.1, 0.05, 0, 0);
  const finM = slab(fin, 0.03, FIN, 0.25, 1.04, zS - 0.125);
  finM.rotation.z = -0.25;
  g.add(finM);
  // the lion head: big and friendly, with a ring of mane
  const hz = zS + 0.09, hy = 1.0;
  g.add(merged(Array.from({ length: 12 }, (_, i) => { const a = (i * TAU) / 12; return blob(Math.cos(a) * 0.225, hy + Math.sin(a) * 0.225, hz - 0.045, 0.08, 0.08, 0.07); }), MANE));
  g.add(ell(0.21, 0.2, 0.19, WHITE, 0, hy, hz, wh(WHITE), 18));
  for (const s of [-1, 1]) {
    g.add(ell(0.055, 0.055, 0.035, WHITE, s * 0.15, hy + 0.15, hz + 0.02, wh(WHITE), 10));
    g.add(ell(0.03, 0.03, 0.02, "#F7A8C0", s * 0.15, hy + 0.15, hz + 0.045, undefined, 8));
    g.add(ell(0.028, 0.034, 0.016, PAL.ink, s * 0.08, hy + 0.05, hz + 0.178, undefined, 8));
    g.add(ell(0.009, 0.009, 0.006, "#FFFFFF", s * 0.088, hy + 0.063, hz + 0.19, undefined, 6));
    g.add(ell(0.036, 0.022, 0.012, "#F7A8C0", s * 0.125, hy - 0.02, hz + 0.165, undefined, 8));
  }
  g.add(ell(0.1, 0.075, 0.085, WHITE, 0, hy - 0.06, hz + 0.14, wh(WHITE), 14));
  g.add(ell(0.032, 0.022, 0.02, PAL.ink, 0, hy - 0.015, hz + 0.215, undefined, 8));
  g.add(ell(0.05, 0.034, 0.03, "#8C2F45", 0, hy - 0.1, hz + 0.205, undefined, 10));
  g.add(ell(0.045, 0.02, 0.03, WHITE, 0, hy - 0.138, hz + 0.19, undefined, 8));
  // the water arc from the mouth into the pool
  const arc = new THREE.CatmullRomCurve3([v3(0, hy - 0.1, hz + 0.22), v3(0, hy - 0.08, hz + 0.27), v3(0, hy - 0.15, hz + 0.31), v3(0, 0.62, 0.325), v3(0, 0.38, 0.332), v3(0, 0.18, 0.335), v3(0, 0.105, 0.335)]);
  g.add(mesh(new THREE.TubeGeometry(arc, 26, 0.026, 6, false), "#8FD8FF", 0, 0, 0, { transparent: true, opacity: 0.9, ...glowOpts("#8FD8FF", 0.4) }));
  const ripples = [];
  for (let i = 0; i < 2; i++) {
    const m = new THREE.Mesh(new THREE.RingGeometry(0.05, 0.068, 20), new THREE.MeshBasicMaterial({ color: "#FFFFFF", transparent: true, opacity: 0.7, side: THREE.DoubleSide }));
    m.rotation.x = -PI / 2; m.position.set(0, 0.106, 0.335);
    g.add(m);
    ripples.push(m);
  }
  for (const [x, z] of [[-0.07, 0.36], [0.07, 0.36], [0.0, 0.29]]) g.add(ell(0.015, 0.015, 0.015, "#B5E6FF", x, 0.12, z, undefined, 6));
  g.userData.tick = (t) => ripples.forEach((m, i) => { const p = (t * 0.7 + i * 0.5) % 1; m.scale.setScalar(1 + p * 0.85); m.material.opacity = 0.7 * (1 - p); });
  return g;
}

export const MODELS = {
  "poster-shield": posterShield, calendar, clock, mirror, painting, "photo-frames": photoFrames, "wall-shelf": wallShelf, "safe-home-sign": safeHomeSign, bunting,
  "cny-lanterns": cnyLanterns, ketupat, "moon-lanterns": moonLanterns, wreath, "sg-flag": sgFlag, "my-flag": myFlag, wau,
  "mandarin-tree": mandarinTree, pelita, "diya-set": diyaSet, "lantern-stand": lanternStand, "xmas-tree": xmasTree, merlion, rangoli,
};
