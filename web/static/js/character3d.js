// Little people and pets for the house and for Scam Road, all built from simple shapes (no model files). buildCharacter() makes the chibi human from a look
// (the tables below mirror core/domain/characters.py), buildPet() makes the twelve animals, and buildDriver() makes whoever sits in the toy car.
// Everything faces +z with its origin on the floor, and has userData.tick(t, dt, state) for a little life (blinking, breathing, walking, waving).
import { THREE, mat } from "./house_kit.js";

// ---- the look tables: keep these exactly as in core/domain/characters.py (a test compares them)
export const LOOK_TABLES = {
  SKINS: ["#FBE0C8", "#F5CFA8", "#E8B98A", "#D29B6B", "#B87B50", "#946038", "#6F4528", "#4A2E1B"],
  HAIR_STYLES: ["short", "bob", "long", "ponytail", "bun", "curly", "buzz", "bald", "tudung", "sidepart", "spiky"],
  HAIR_COLORS: ["#1F1A1A", "#3B2A20", "#6B4A2F", "#A0522D", "#D8B66A", "#A7A7A7", "#7A5CD0", "#2BA3A3", "#E26BA6", "#2D3070"],
  OUTFIT_STYLES: ["tee", "hoodie", "shirt", "kurung", "jacket", "polo", "kurta"],
  OUTFIT_COLORS: ["#7A5CD0", "#E5546B", "#F08A4B", "#E3B23C", "#33B27C", "#3FA7E8", "#2D3070", "#F3F0FA", "#3B3B4F", "#E26BA6"],
  ACCESSORIES: ["none", "glasses", "round", "songkok", "cap", "flower"],
  FACES: ["soft", "plain", "stubble", "moustache", "goatee", "beard"],
};
const { SKINS, HAIR_STYLES, HAIR_COLORS, OUTFIT_STYLES, OUTFIT_COLORS, ACCESSORIES, FACES } = LOOK_TABLES;
const NATURAL_HAIR = 6;   // the first six hair colours are natural: brows and facial hair never take the others
export const HATS = ["none", "cap", "shades", "party", "scarf", "crown"];
export const PET_IDS = ["pet-fish", "pet-fox", "pet-panda", "pet-tiger", "pet-frog", "pet-owl", "pet-octopus", "pet-turtle", "pet-unicorn", "pet-cat", "pet-penguin", "pet-lion"];

// ---- small helpers
const PI = Math.PI, TAU = PI * 2;
const Z_AXIS = new THREE.Vector3(0, 0, 1);
const lerp = (a, b, k) => a + (b - a) * k;
const col = (c) => new THREE.Color(c);
const mix = (a, b, k) => "#" + col(a).lerp(col(b), k).getHexString();
const shade = (c, k) => mix(c, k < 0 ? "#000000" : "#ffffff", Math.abs(k));
const lum = (c) => { const x = col(c); return 0.2126 * x.r + 0.7152 * x.g + 0.0722 * x.b; };
const isHex = (s) => typeof s === "string" && /^#[0-9a-fA-F]{6}$/.test(s);

const sphereGeos = new Map();
function sphereGeo(seg) {
  if (!sphereGeos.has(seg)) sphereGeos.set(seg, new THREE.SphereGeometry(1, seg, Math.max(8, Math.round(seg * 0.72))));
  return sphereGeos.get(seg);
}
function finish(m, x = 0, y = 0, z = 0) { m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; return m; }
/** An ellipsoid with radii rx, ry, rz and its middle at (x, y, z). */
function ball(color, rx, ry = rx, rz = rx, x = 0, y = 0, z = 0, seg = 16, opts) {
  const m = finish(new THREE.Mesh(sphereGeo(seg), mat(color, opts)), x, y, z);
  m.scale.set(rx, ry, rz);
  return m;
}
/** A cylinder (or frustum) whose middle is at (x, y, z). */
function rod(color, rTop, rBot, h, x = 0, y = 0, z = 0, seg = 14, opts) {
  return finish(new THREE.Mesh(new THREE.CylinderGeometry(rTop, rBot, h, seg), mat(color, opts)), x, y, z);
}
function slab(color, w, h, d, x = 0, y = 0, z = 0, opts) {
  return finish(new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color, opts)), x, y, z);
}
/** A cone with its middle at (x, y, z). */
function spike(color, r, h, x = 0, y = 0, z = 0, seg = 12, opts) {
  return finish(new THREE.Mesh(new THREE.ConeGeometry(r, h, seg), mat(color, opts)), x, y, z);
}
/** A ring (torus) lying in the x/y plane; `arc` makes it a partial ring starting at angle 0. */
function ring(color, R, r, arc = TAU, seg = 20, tseg = 8, opts) {
  return finish(new THREE.Mesh(new THREE.TorusGeometry(R, r, tseg, seg, arc), mat(color, opts)));
}
/** A piece of an ellipsoid (a cap, a bowl, a curtain). theta runs from the +y pole, phi around y (0 is -x, a quarter turn on is +z). Seen from both sides. */
function shell(color, rx, ry, rz, thetaStart, thetaLength, phiStart = 0, phiLength = TAU, seg = 20, opts) {
  const g = new THREE.SphereGeometry(1, seg, Math.max(8, Math.round(seg * 0.7)), phiStart, phiLength, thetaStart, thetaLength);
  const m = finish(new THREE.Mesh(g, mat(color, { side: THREE.DoubleSide, ...opts })));
  m.scale.set(rx, ry, rz);
  return m;
}
/** A body of revolution from a profile of [radius, y] points (bottom to top), smoothed. sz squashes it front to back. */
function lathe(color, prof, { seg = 20, sz = 1, steps = 26, double = false } = {}) {
  const pts = new THREE.SplineCurve(prof.map(([r, y]) => new THREE.Vector2(r, y))).getPoints(steps).map((p) => new THREE.Vector2(Math.max(0, p.x), p.y));
  const m = finish(new THREE.Mesh(new THREE.LatheGeometry(pts, seg), mat(color, double ? { side: THREE.DoubleSide } : undefined)));
  m.scale.z = sz;
  return m;
}
/** A soft tapered tube along a curve of [x, y, z] points; rf(u) gives the radius along it (u from 0 to 1). u0..u1 draws just a piece of it. */
function limb(color, pts, rf, { u0 = 0, u1 = 1, seg = 16, rad = 8 } = {}) {
  let curve = new THREE.CatmullRomCurve3(pts.map((p) => new THREE.Vector3(p[0], p[1], p[2])));
  if (u0 > 0 || u1 < 1) {
    const sub = [];
    for (let i = 0; i <= 5; i++) sub.push(curve.getPointAt(lerp(u0, u1, i / 5)));
    curve = new THREE.CatmullRomCurve3(sub);
  }
  const g = new THREE.TubeGeometry(curve, seg, 1, rad, false), pos = g.attributes.position;
  for (let i = 0; i <= seg; i++) {
    const c = curve.getPointAt(i / seg), r = rf(lerp(u0, u1, i / seg));
    for (let j = 0; j <= rad; j++) {
      const k = i * (rad + 1) + j;
      pos.setXYZ(k, c.x + (pos.getX(k) - c.x) * r, c.y + (pos.getY(k) - c.y) * r, c.z + (pos.getZ(k) - c.z) * r);
    }
  }
  pos.needsUpdate = true;
  const m = finish(new THREE.Mesh(g, mat(color)));
  m.userData.end = curve.getPointAt(1);
  m.userData.start = curve.getPointAt(0);
  return m;
}
const grp = (x = 0, y = 0, z = 0) => { const g = new THREE.Group(); g.position.set(x, y, z); return g; };
const add = (parent, ...kids) => { for (const k of kids.flat()) if (k) parent.add(k); return parent; };
function rot(o, x = 0, y = 0, z = 0) { o.rotation.set(x, y, z); return o; }
/** Mark a mesh as see-through: no shadow, no depth writes. */
function see(m, order = 2) { m.castShadow = false; m.receiveShadow = false; m.renderOrder = order; return m; }
const glassMat = (color, opacity, both = false) => ({ transparent: true, opacity, depthWrite: false, side: both ? THREE.DoubleSide : THREE.FrontSide });

/** Put a thing on the skin of an ellipsoid (radii rx, ry, rz around the origin) at (x, y), turned to face outward. */
function onSurface(obj, rx, ry, rz, x, y, lift = 0) {
  const z = rz * Math.sqrt(Math.max(0.02, 1 - (x / rx) ** 2 - (y / ry) ** 2));
  const n = new THREE.Vector3(x / (rx * rx), y / (ry * ry), z / (rz * rz)).normalize();
  obj.position.set(x + n.x * lift, y + n.y * lift, z + n.z * lift);
  obj.quaternion.setFromUnitVectors(Z_AXIS, n);
  return obj;
}
/** The same, from a direction away from the middle of an ellipsoid centred on c. */
function onBody(obj, c, r, dx, dy, dz, lift = 0, spin = 0) {
  const d = new THREE.Vector3(dx, dy, dz).normalize();
  const p = new THREE.Vector3(c[0] + d.x * r[0], c[1] + d.y * r[1], c[2] + d.z * r[2]);
  const n = new THREE.Vector3(d.x / r[0], d.y / r[1], d.z / r[2]).normalize();
  obj.position.set(p.x + n.x * lift, p.y + n.y * lift, p.z + n.z * lift);
  obj.quaternion.setFromUnitVectors(Z_AXIS, n);
  if (spin) obj.rotateZ(spin);
  return obj;
}
function blinkK(t, seed = 0, every = 4.1) {
  const p = (t + seed) % every;
  if (p < 0.13) return 1 - 0.93 * Math.sin((p / 0.13) * PI);
  const q = (t + seed + 1.7) % (every * 2.3);
  return q < 0.11 ? 1 - 0.93 * Math.sin((q / 0.11) * PI) : 1;
}

// ---- looks
function lookFromCode(code) {
  if (typeof code !== "string" || !/^p(?:\.\d{1,2}){6,7}$/.test(code)) return null;
  const n = code.split(".").slice(1).map(Number);
  while (n.length < 7) n.push(0);   // a six-number code, from before the faces, has rosy cheeks
  const sizes = [SKINS.length, HAIR_STYLES.length, HAIR_COLORS.length, OUTFIT_STYLES.length, OUTFIT_COLORS.length, ACCESSORIES.length, FACES.length];
  if (n.some((v, i) => v >= sizes[i])) return null;
  return { skin: SKINS[n[0]], hair: HAIR_STYLES[n[1]], hairColor: HAIR_COLORS[n[2]], outfit: OUTFIT_STYLES[n[3]], outfitColor: OUTFIT_COLORS[n[4]], accessory: ACCESSORIES[n[5]], face: FACES[n[6]] };
}
function cleanLook(look) {
  const l = look && typeof look === "object" ? look : {};
  return {
    skin: isHex(l.skin) ? l.skin : SKINS[2],
    hair: HAIR_STYLES.includes(l.hair) ? l.hair : "short",
    hairColor: isHex(l.hairColor) ? l.hairColor : HAIR_COLORS[1],
    outfit: OUTFIT_STYLES.includes(l.outfit) ? l.outfit : "tee",
    outfitColor: isHex(l.outfitColor) ? l.outfitColor : OUTFIT_COLORS[0],
    accessory: ACCESSORIES.includes(l.accessory) ? l.accessory : "none",
    face: FACES.includes(l.face) ? l.face : "soft",
  };
}

// ---- the head: a wide, friendly ellipsoid. Everything on it is placed in head space (origin at the middle of the head, +z is the face).
const HX = 0.34, HY = 0.3, HZ = 0.31;
const onHead = (obj, x, y, lift = 0) => onSurface(obj, HX, HY, HZ, x, y, lift);

function shinyEye(r, color = "#2B1B33", squash = 1.12) {
  const g = new THREE.Group();
  add(g, ball(color, r, r * squash, r * 0.7, 0, 0, 0, 14), ball("#FFFFFF", r * 0.33, r * 0.33, r * 0.22, r * 0.34, r * 0.42, r * 0.55, 8), ball("#FFFFFF", r * 0.16, r * 0.16, r * 0.11, -r * 0.34, -r * 0.34, r * 0.6, 6));
  return g;
}

// ---- hair: every style is built in head space and returns { g, vol (how far it stands off the head on top), ears (whether it hides the ears) }
function hairCap(color, k, thetaLen, tilt) {
  const s = shell(color, HX * k, HY * k, HZ * k, 0, thetaLen, 0, TAU, 22);
  s.rotation.x = tilt;
  return s;
}
function tuft(color, x, y, size, spin = 0, flat = 0.7) {
  return onHead(ball(color, size, size * flat, size * 0.62, 0, 0, 0, 12), x, y, 0.004).rotateZ(spin);
}
function fringe(g, color, kind) {
  if (kind === "swept") {
    for (const [x, y, s, sp] of [[-0.2, 0.15, 0.09, 0.9], [-0.1, 0.2, 0.1, 0.75], [0.02, 0.225, 0.105, 0.55], [0.13, 0.205, 0.1, 0.35], [0.22, 0.15, 0.085, 0.1]]) g.add(tuft(color, x, y, s, sp));
  } else if (kind === "straight") {
    for (const [x, y, s] of [[-0.21, 0.15, 0.085], [-0.105, 0.17, 0.09], [0, 0.18, 0.09], [0.105, 0.17, 0.09], [0.21, 0.15, 0.085]]) g.add(tuft(color, x, y, s, 0, 0.62));
  } else if (kind === "curly") {
    for (const [x, y, s] of [[-0.16, 0.2, 0.075], [-0.04, 0.24, 0.08], [0.09, 0.235, 0.08], [0.19, 0.19, 0.07]]) g.add(ball(color, s, s, s, ...surfXY(x, y, 1.04)));
  }
}
function surfXY(x, y, k = 1) {
  const z = HZ * Math.sqrt(Math.max(0.02, 1 - (x / HX) ** 2 - (y / HY) ** 2));
  return [x * k, y * k, z * k];
}
function curlPositions() {
  const out = [[0, 1, 0, 0.15]];
  const ring = (elev, azs, r) => azs.forEach((a) => { const e = elev * PI / 180, az = a * PI / 180; out.push([Math.sin(az) * Math.cos(e), Math.sin(e), Math.cos(az) * Math.cos(e), r]); });
  ring(66, [20, 110, 200, 290], 0.14);
  ring(38, [60, 120, 190, 245, 305], 0.145);
  ring(8, [95, 150, 215, 265], 0.13);
  return out;
}

function buildHair(style, color, S) {
  const g = new THREE.Group();
  const hat = S.hat !== "none" || S.capOn;
  const fr = (kind) => { if (!S.capOn) fringe(g, color, kind); };
  let vol = 1.06, ears = true;
  if (style === "short") {
    add(g, hairCap(color, 1.055, PI / 2 + 0.04, -0.5));
    fr("swept");
    add(g, ball(color, 0.05, 0.1, 0.06, 0.305, 0.02, -0.02, 10), ball(color, 0.05, 0.1, 0.06, -0.305, 0.02, -0.02, 10));
  } else if (style === "bob") {
    add(g, hairCap(color, 1.06, PI / 2 + 0.1, -0.4));
    add(g, shell(color, HX * 1.09, HY * 1.04, HZ * 1.09, 0.35, PI * 0.78 - 0.35, PI / 2 + 0.78, TAU - 1.56, 22));
    add(g, ball(color, 0.11, 0.07, 0.07, -0.24, -0.21, 0.13, 10), ball(color, 0.11, 0.07, 0.07, 0.24, -0.21, 0.13, 10));
    fr("straight");
    vol = 1.09; ears = false;
  } else if (style === "long") {
    add(g, hairCap(color, 1.06, PI / 2 + 0.1, -0.4));
    add(g, shell(color, HX * 1.1, HY * 1.05, HZ * 1.1, 0.35, PI * 0.8 - 0.35, PI / 2 + 0.8, TAU - 1.6, 22));
    add(g, ball(color, 0.33, 0.3, 0.15, 0, -0.33, -0.17, 16));
    add(g, ball(color, 0.075, 0.2, 0.085, -0.31, -0.3, 0.1, 12), ball(color, 0.075, 0.2, 0.085, 0.31, -0.3, 0.1, 12));
    fr("swept");
    vol = 1.09; ears = false;
  } else if (style === "ponytail") {
    add(g, hairCap(color, 1.055, PI / 2 + 0.06, -0.5));
    fr("swept");
    const pony = grp(0, 0.13, -0.33);
    add(pony, ball("#E5546B", 0.075, 0.05, 0.075, 0, 0, 0, 10));
    add(pony, limb(color, [[0, 0, -0.02], [0, 0.0, -0.17], [0, -0.1, -0.26], [0, -0.3, -0.27], [0, -0.46, -0.2]], (u) => 0.1 * (1 - u * 0.75) + 0.045 * Math.sin(u * PI)));
    add(pony, ball(color, 0.04, 0.05, 0.04, 0, -0.5, -0.19, 8));
    g.add(pony); g.userData.pony = pony;
    add(g, ball(color, 0.05, 0.1, 0.06, 0.305, 0.02, -0.02, 10), ball(color, 0.05, 0.1, 0.06, -0.305, 0.02, -0.02, 10));
  } else if (style === "bun") {
    add(g, hairCap(color, 1.055, PI / 2 + 0.06, -0.5));
    fr("swept");
    const up = !hat;
    const bun = grp(0, up ? 0.35 : 0.2, up ? -0.06 : -0.32);
    add(bun, ball(color, 0.14, 0.13, 0.14, 0, 0, 0, 14), rot(ring("#E5546B", 0.1, 0.022, TAU, 16, 6), up ? PI / 2 : 0.25, 0, 0));
    bun.children[1].position.y = -0.09;
    g.add(bun);
    vol = 1.06;
  } else if (style === "curly") {
    add(g, hairCap(color, 1.07, PI / 2 + 0.06, -0.5));
    for (const [dx, dy, dz, r] of curlPositions()) {
      if (S.capOn && dy > 0.3 && !(dz < -0.3)) continue;   // under a cap only the curls at the back and the sides show
      add(g, ball(color, r, r * 0.95, r, dx * HX * 1.0, dy * HY * 1.0, dz * HZ * 1.0, 12));
    }
    vol = S.capOn ? 1.16 : 1.4;
  } else if (style === "buzz") {
    add(g, hairCap(color, 1.02, PI / 2 + 0.02, -0.55));
    vol = 1.03;
  } else if (style === "sidepart") {
    add(g, hairCap(color, 1.055, PI / 2 + 0.04, -0.5));
    if (!S.capOn) {   // a neat fringe combed over to one side, with the parting showing
      for (const [x, y, s, sp] of [[-0.215, 0.14, 0.085, -0.25], [-0.13, 0.185, 0.1, -0.45], [-0.02, 0.215, 0.105, -0.7], [0.1, 0.2, 0.1, -0.95], [0.21, 0.15, 0.085, -1.15]]) g.add(tuft(color, x, y, s, sp));
      add(g, onHead(slab(shade(color, -0.35), 0.012, 0.13, 0.01), -0.115, 0.215, 0.0));
    }
    add(g, ball(color, 0.05, 0.1, 0.06, 0.305, 0.02, -0.02, 10), ball(color, 0.05, 0.1, 0.06, -0.305, 0.02, -0.02, 10));
  } else if (style === "spiky") {
    add(g, hairCap(color, 1.04, PI / 2 + 0.02, -0.5));
    const up = new THREE.Vector3(0, 1, 0);
    for (const [az, el, len, r] of [[0, 84, 0.2, 0.065], [40, 66, 0.2, 0.06], [-40, 66, 0.2, 0.06], [100, 62, 0.18, 0.06], [-100, 62, 0.18, 0.06], [165, 60, 0.18, 0.06], [-165, 60, 0.18, 0.06], [0, 54, 0.17, 0.06], [70, 40, 0.15, 0.055], [-70, 40, 0.15, 0.055], [130, 38, 0.15, 0.055], [-130, 38, 0.15, 0.055]]) {
      if (S.capOn && el < 70) continue;
      const a = az * PI / 180, e = el * PI / 180, d = new THREE.Vector3(Math.sin(a) * Math.cos(e), Math.sin(e), Math.cos(a) * Math.cos(e)).normalize();
      const sp = spike(color, r, len, d.x * HX * 1.0 + d.x * len * 0.32, d.y * HY * 1.0 + d.y * len * 0.32, d.z * HZ * 1.0 + d.z * len * 0.32, 10);
      sp.quaternion.setFromUnitVectors(up, d);
      g.add(sp);
    }
    vol = S.capOn ? 1.14 : 1.42;
  } else if (style === "tudung") {
    ears = false; vol = 1.2;
    const rimR = 0.235;
    const hood = lathe(color, [[0, -0.38], [0.13, -0.37], [0.26, -0.32], [0.34, -0.22], [0.365, -0.06], [0.35, 0.08], [0.3, 0.17], [rimR + 0.02, 0.212], [rimR, 0.208]], { seg: 24, double: true });
    hood.rotation.x = PI / 2;   // the lathe is drawn along its y axis; turned so that the axis points at the face
    g.add(hood);
    const rim = ring(shade(color, -0.1), rimR, 0.032, TAU, 28, 8); rim.position.z = 0.215;
    g.add(rim);
  }
  g.userData.vol = vol; g.userData.ears = ears;
  return g;
}

// ---- hats and head things worn on top: S describes the head (radii rx, ry, rz; eyeX, eyeY, faceZ for shades; vol for how much hair is on top)
function makeHat(kind, S) {
  const g = new THREE.Group();
  const k = Math.max(1.12, (S.vol || 1.06) + 0.05), sx = S.rx, sy = S.ry, sz = S.rz;
  if (kind === "cap") {
    const c = S.capColor || "#E5546B";
    const dome = shell(c, sx * k, sy * k, sz * k, 0, PI / 2 + 0.12, 0, TAU, 22); dome.rotation.x = -0.5;
    const brim = ball(shade(c, -0.18), sx * 0.58, sy * 0.07, sz * 0.46, 0, sy * 0.36, sz * 1.1 * Math.max(1, k / 1.12), 16);
    brim.rotation.x = 0.16;
    add(g, dome, brim, ball(shade(c, -0.1), sx * 0.07, sx * 0.07, sx * 0.07, 0, sy * k * 0.87, -sz * k * 0.17, 8));
  } else if (kind === "party") {
    const h = sy * 1.55, r0 = sx * 0.5, y0 = sy * (0.78 + ((S.vol || 1.06) - 1.06) * 0.9);
    const cone = grp(sx * 0.1, y0, 0); cone.rotation.z = -0.18; cone.rotation.x = -0.08;
    const bands = [["#E26BA6", 0, 0.34], ["#E3B23C", 0.34, 0.67], ["#E26BA6", 0.67, 1]];
    for (const [c, a, b] of bands) cone.add(rod(c, r0 * (1 - b), r0 * (1 - a), h * (b - a), 0, h * (a + b) / 2, 0, 16));
    add(cone, ball("#E3B23C", sx * 0.1, sx * 0.1, sx * 0.1, 0, h + 0.01, 0, 10));
    add(g, cone);
  } else if (kind === "crown") {
    const r = sx * 0.6, y0 = sy * (0.74 + ((S.vol || 1.06) - 1.06)), gold = "#E3B23C";
    const crown = grp(0, y0, 0); crown.rotation.x = -0.1;
    add(crown, rod(gold, r, r * 1.02, sy * 0.24, 0, sy * 0.12, 0, 18, { side: THREE.DoubleSide }), ball("#3FA7E8", sx * 0.05, sx * 0.05, sx * 0.04, 0, sy * 0.12, r * 1.02, 8));
    for (let i = 0; i < 5; i++) {
      const a = (i / 5) * TAU, x = Math.sin(a) * r, z = Math.cos(a) * r;
      add(crown, spike(gold, sx * 0.1, sy * 0.36, x, sy * 0.4, z, 8), ball(i % 2 ? "#FFE08A" : "#E5546B", sx * 0.045, sx * 0.045, sx * 0.045, x, sy * 0.6, z, 8));
    }
    add(g, crown);
  } else if (kind === "shades") {
    const ex = S.eyeX, ey = S.eyeY, fz = S.faceZ, dark = "#1F1A1A";
    for (const sd of [-1, 1]) {
      add(g, ball(dark, ex * 0.62, ex * 0.46, sx * 0.045, sd * ex, ey, fz, 14), ball("#9CC9F5", ex * 0.13, ex * 0.09, sx * 0.03, sd * ex - ex * 0.28, ey + ex * 0.22, fz + sx * 0.04, 8));
      const a = slab(dark, sx * 0.04, sx * 0.04, sz * 0.9, sd * (ex + ex * 0.58), ey + ex * 0.1, fz - sz * 0.45);
      a.rotation.y = sd * 0.1;
      g.add(a);
    }
    add(g, slab(dark, ex * 0.6, sx * 0.04, sx * 0.04, 0, ey + ex * 0.1, fz));
  }
  return g;
}
function makeScarf(R, tube) {
  const g = new THREE.Group();
  const red = "#E5546B", white = "#F7F4FF";
  const band = rot(ring(red, R, tube, TAU, 22, 8), PI / 2, 0, 0); band.scale.set(1, 0.84, 1);
  const stripe = rot(ring(white, R + tube * 0.04, tube * 0.45, TAU, 22, 6), PI / 2, 0, 0); stripe.position.y = tube * 0.2; stripe.scale.set(1, 0.84, 1);
  add(g, band, stripe);
  const tail = grp(R * 0.62, -tube * 0.5, R * 0.86); tail.rotation.z = 0.12;
  add(tail, ball(red, tube * 1.1, tube * 1.0, tube * 1.05, 0, 0, 0, 10), slab(red, tube * 1.7, tube * 5.2, tube * 0.6, 0.01, -tube * 2.9, 0.01), slab(white, tube * 1.74, tube * 0.55, tube * 0.64, 0.01, -tube * 3.7, 0.012), slab(white, tube * 1.74, tube * 0.55, tube * 0.64, 0.01, -tube * 4.6, 0.012));
  g.add(tail);
  return g;
}

// ---- accessories on the face and the hair
function makeGlasses(kind, S) {
  const g = new THREE.Group(), ex = S.eyeX, ey = S.eyeY, fz = S.faceZ + 0.02;
  const c = kind === "round" ? "#E3B23C" : S.darkSkin ? "#F7F4FF" : "#2B1B55";
  for (const sd of [-1, 1]) {
    if (kind === "round") {
      const r = ring(c, 0.068, 0.0105, TAU, 22, 6); r.position.set(sd * ex, ey, fz); g.add(r);
    } else {
      const w = 0.062, h = 0.052, t = 0.0115;
      add(g, slab(c, w * 2 + t, t, t, sd * ex, ey + h, fz), slab(c, w * 2 + t, t, t, sd * ex, ey - h, fz), slab(c, t, h * 2, t, sd * ex - w, ey, fz), slab(c, t, h * 2, t, sd * ex + w, ey, fz));
    }
    const ax = sd * (ex + 0.07), len = 0.3;
    const a = slab(c, 0.011, 0.011, len, ax + sd * 0.06, ey + 0.01, fz - len / 2 + 0.01);
    a.rotation.y = sd * 0.2;
    g.add(a);
  }
  add(g, slab(c, ex - 0.07, 0.012, 0.012, 0, ey + 0.02, fz));
  return g;
}
function makeSongkok() {
  const g = grp(0, 0.2, -0.015); g.rotation.x = -0.16;
  add(g, rod("#1F1A1A", 0.205, 0.27, 0.2, 0, 0.1, 0, 22), ball("#1F1A1A", 0.205, 0.015, 0.205, 0, 0.2, 0, 18));
  return g;
}
function makeFlower(petal, S) {
  const g = new THREE.Group();
  const f = grp();
  for (let i = 0; i < 5; i++) { const a = (i / 5) * TAU + 0.3; add(f, ball(petal, 0.05, 0.05, 0.028, Math.cos(a) * 0.062, Math.sin(a) * 0.062, 0, 10)); }
  add(f, ball("#E3B23C", 0.04, 0.04, 0.032, 0, 0, 0.012, 10));
  onSurface(f, S.rx * 1.05, S.ry * 1.05, S.rz * 1.05, 0.255, 0.2, 0.0);
  g.add(f);
  return g;
}

// ---- the human
function pantsFor(outfitColor) {
  if (lum(outfitColor) < 0.05) return "#B79F7C";
  const hsl = {}; col(outfitColor).getHSL(hsl);
  if (hsl.h > 0.5 && hsl.h < 0.75 && hsl.s > 0.3) return "#4A4F63";
  return "#4B6BA8";
}
function capColorFor(outfitColor) {
  const c = col(outfitColor);
  let best = "#E5546B", bd = -1;
  for (const o of ["#E5546B", "#3FA7E8", "#F08A4B", "#33B27C", "#7A5CD0"]) { const q = col(o), d = Math.hypot(c.r - q.r, c.g - q.g, c.b - q.b); if (d > bd) { bd = d; best = o; } }
  return best;
}
function torsoProfile(style) {
  const kurung = style === "kurung", kurta = style === "kurta", k = style === "hoodie" ? 1.07 : style === "jacket" ? 1.035 : 1;
  const raw = kurung
    ? [[0, 0.25], [0.3, 0.25], [0.305, 0.3], [0.285, 0.43], [0.25, 0.57], [0.226, 0.7], [0.18, 0.8], [0.105, 0.855], [0, 0.865]]
    : kurta
      ? [[0, 0.29], [0.262, 0.29], [0.266, 0.35], [0.258, 0.5], [0.242, 0.62], [0.22, 0.73], [0.175, 0.81], [0.105, 0.855], [0, 0.865]]   // a straight tunic to the thigh
      : [[0, 0.355], [0.19, 0.355], [0.235, 0.4], [0.248, 0.5], [0.238, 0.62], [0.218, 0.73], [0.175, 0.81], [0.105, 0.855], [0, 0.865]];
  return raw.map(([r, y]) => [r * (y > 0.85 ? 1 : k), y]);
}
function profileAt(style, y) {
  const p = torsoProfile(style);
  for (let i = 1; i < p.length; i++) if (y <= p[i][1] && p[i][1] - p[i - 1][1] > 1e-6) { const a = p[i - 1], b = p[i], k = (y - a[1]) / (b[1] - a[1]); return lerp(a[0], b[0], k); }
  return p[p.length - 1][0];
}
/** A band hugging the body between two heights (a hem, a trim). */
function bodyBand(style, color, y0, y1, grow = 0.008, sz = 0.76) {
  const prof = [];
  for (let i = 0; i <= 5; i++) { const y = lerp(y0, y1, i / 5); prof.push([profileAt(style, y) + grow, y]); }
  const pts = prof.map(([r, y]) => new THREE.Vector2(r, y));
  const m = finish(new THREE.Mesh(new THREE.LatheGeometry(pts, 22), mat(color, { side: THREE.DoubleSide })));
  m.scale.z = sz;
  return m;
}

function trimFor(color) {
  const hsl = {}; col(color).getHSL(hsl);
  return hsl.h > 0.04 && hsl.h < 0.18 && hsl.s > 0.4 ? "#FFF3D6" : "#E3B23C";
}
function buildTorso(style, color, skin) {
  const g = new THREE.Group(), kurung = style === "kurung";
  const sz = kurung ? 0.8 : 0.76;
  add(g, lathe(color, torsoProfile(style), { sz }));
  const dark = shade(color, -0.2), light = lum(color) > 0.6 ? shade(color, -0.1) : shade(color, 0.28);
  const neckRing = (c, R, t) => { const r = rot(ring(c, R, t, TAU, 20, 6), PI / 2, 0, 0); r.scale.set(1, 0.86, 1); r.position.y = 0.862; return r; };
  if (style === "tee") {
    g.add(neckRing(dark, 0.1, 0.016));
  } else if (style === "hoodie") {
    const hoodC = shade(color, -0.14);
    const bunch = rot(ring(hoodC, 0.15, 0.06, TAU, 22, 8), PI / 2, 0, 0); bunch.scale.set(1, 0.9, 1); bunch.position.y = 0.845;
    const back = ball(hoodC, 0.15, 0.1, 0.1, 0, 0.83, -0.14, 14);
    add(g, bunch, back, rbox(0.25, 0.12, 0.05, 0.04, hoodC, 0, 0.44, 0.165));
    add(g, rod("#F7F4FF", 0.009, 0.009, 0.1, -0.05, 0.78, 0.2, 6), rod("#F7F4FF", 0.009, 0.009, 0.1, 0.05, 0.78, 0.2, 6));
    add(g, ball("#F7F4FF", 0.014, 0.014, 0.014, -0.05, 0.725, 0.2, 6), ball("#F7F4FF", 0.014, 0.014, 0.014, 0.05, 0.725, 0.2, 6));
  } else if (style === "shirt") {
    const w = "#F7F4FF", cw = lum(color) > 0.6 ? shade(color, -0.12) : w;
    for (const sd of [-1, 1]) {
      const c = slab(cw, 0.1, 0.02, 0.09, sd * 0.062, 0.862, 0.095); c.rotation.set(0.55, sd * -0.5, sd * 0.35); g.add(c);
    }
    for (let i = 0; i < 4; i++) g.add(ball(w, 0.014, 0.014, 0.01, 0, 0.78 - i * 0.12, 0.181 - i * 0.012, 8));
    g.add(slab(shade(color, -0.1), 0.08, 0.07, 0.012, -0.12, 0.62, 0.178));
  } else if (style === "jacket") {
    const inner = lum(color) > 0.6 ? "#7A5CD0" : "#F7F4FF";
    add(g, slab(inner, 0.12, 0.13, 0.02, 0, 0.8, 0.16));
    for (const sd of [-1, 1]) {
      const l = slab(shade(color, -0.22), 0.1, 0.16, 0.025, sd * 0.07, 0.775, 0.172); l.rotation.set(0.1, 0, sd * -0.32); g.add(l);
    }
    add(g, slab("#D9D6E2", 0.012, 0.42, 0.012, 0, 0.58, 0.19), slab("#A7A7A7", 0.03, 0.04, 0.016, 0.0, 0.76, 0.19));
    g.add(bodyBand(style, shade(color, -0.2), 0.355, 0.4, 0.006));
  } else if (style === "polo") {
    const cw = lum(color) > 0.6 ? shade(color, -0.12) : shade(color, 0.22);
    for (const sd of [-1, 1]) {
      const c = slab(cw, 0.1, 0.02, 0.09, sd * 0.062, 0.862, 0.095); c.rotation.set(0.55, sd * -0.5, sd * 0.35); g.add(c);
    }
    add(g, slab(shade(color, -0.18), 0.04, 0.16, 0.01, 0, 0.76, 0.182), ball("#F7F4FF", 0.012, 0.012, 0.009, 0, 0.8, 0.19, 8), ball("#F7F4FF", 0.012, 0.012, 0.009, 0, 0.74, 0.19, 8));
  } else if (style === "kurta") {
    const gold = trimFor(color), w = "#F7F4FF";
    g.add(neckRing(gold, 0.108, 0.026));   // a stand-up (mandarin) collar
    add(g, slab(shade(color, -0.12), 0.07, 0.5, 0.012, 0, 0.58, 0.19));
    for (let i = 0; i < 4; i++) add(g, ball(i % 2 ? gold : w, 0.014, 0.014, 0.01, 0, 0.8 - i * 0.11, 0.2, 8));
    g.add(bodyBand(style, gold, 0.29, 0.325, 0.006, 0.76));
  } else if (kurung) {
    const gold = trimFor(color);
    g.add(neckRing(gold, 0.108, 0.018));
    g.add(bodyBand(style, gold, 0.25, 0.31, 0.007, 0.8));
    add(g, slab(gold, 0.012, 0.15, 0.01, 0, 0.77, 0.18), ball(gold, 0.017, 0.017, 0.012, 0, 0.82, 0.178, 8), ball(gold, 0.017, 0.017, 0.012, 0, 0.73, 0.185, 8));
  }
  return g;
}
function rbox(w, h, d, r, color, x, y, z) {
  const s = new THREE.Shape(), rr = Math.min(r, w / 2 - 0.001, h / 2 - 0.001), hw = w / 2, hh = h / 2;
  s.moveTo(-hw + rr, -hh); s.lineTo(hw - rr, -hh); s.quadraticCurveTo(hw, -hh, hw, -hh + rr); s.lineTo(hw, hh - rr); s.quadraticCurveTo(hw, hh, hw - rr, hh);
  s.lineTo(-hw + rr, hh); s.quadraticCurveTo(-hw, hh, -hw, hh - rr); s.lineTo(-hw, -hh + rr); s.quadraticCurveTo(-hw, -hh, -hw + rr, -hh);
  const g = new THREE.ExtrudeGeometry(s, { depth: d, bevelEnabled: false, curveSegments: 4 });
  g.translate(0, 0, -d / 2);
  return finish(new THREE.Mesh(g, mat(color)), x, y, z);
}

function buildArm(side, style, color, skin) {
  const g = new THREE.Group(), long = style !== "tee" && style !== "polo";
  const sleeveC = color;
  add(g, rod(skin, 0.064, 0.058, 0.3, 0, -0.17, 0, 12), ball(skin, 0.068, 0.068, 0.068, 0, -0.34, 0, 12));
  const sl = long ? 0.27 : 0.125;
  add(g, rod(sleeveC, 0.078, long ? 0.075 : 0.083, sl, 0, -0.02 - sl / 2, 0, 14));
  add(g, ball(sleeveC, 0.078, 0.078, 0.078, 0, 0, 0, 14));
  if (long) {
    const cuff = style === "kurung" || style === "kurta" ? trimFor(color) : style === "shirt" ? "#F7F4FF" : shade(color, -0.2);
    add(g, rod(cuff, 0.08, 0.08, 0.032, 0, -0.02 - sl, 0, 14));
  }
  if (style === "kurung") add(g, rod(trimFor(color), 0.0795, 0.0795, 0.02, 0, -0.02 - sl * 0.55, 0, 14));
  g.position.set(side * 0.262, 0.79, 0);
  g.rotation.z = side * 0.1;
  return g;
}
function buildLeg(side, pants, shoes, kurung) {
  const g = new THREE.Group();
  add(g, rod(pants, 0.088, kurung ? 0.105 : 0.084, 0.34, 0, -0.17, 0, 14), ball(pants, 0.088, 0.07, 0.088, 0, 0, 0, 12));
  add(g, ball(shoes, 0.09, 0.055, 0.125, 0, -0.372, 0.03, 14), ball(shade(shoes, shoes === "#F7F4FF" ? -0.12 : 0.12), 0.092, 0.018, 0.127, 0, -0.405, 0.03, 12));
  g.position.set(side * 0.105, 0.42, 0);
  return g;
}

let fadeMap = null;
/** The shadow of a day's beard on the lower face: a thin shell whose opacity fades in from nothing at the top edge (an alpha map), so there is no line. */
function stubble(color) {
  if (!fadeMap) {
    const c = document.createElement("canvas"); c.width = 4; c.height = 64;
    const g2 = c.getContext("2d"), grad = g2.createLinearGradient(0, 0, 0, 64);
    grad.addColorStop(0, "#000"); grad.addColorStop(0.55, "#9a9a9a"); grad.addColorStop(1, "#fff");
    g2.fillStyle = grad; g2.fillRect(0, 0, 4, 64);
    fadeMap = new THREE.CanvasTexture(c);
  }
  const geo = new THREE.SphereGeometry(1, 24, 16, 0.12, PI - 0.24, 1.78, 1.12);   // from just under the nose to under the chin, ear to ear
  const m = new THREE.Mesh(geo, new THREE.MeshLambertMaterial({ color, transparent: true, alphaMap: fadeMap, opacity: 0.85, depthWrite: false, side: THREE.DoubleSide }));
  m.scale.set(HX * 1.012, HY * 1.012, HZ * 1.012); m.renderOrder = 1;
  return m;
}
function buildFace(skin, hairColor, bare, face = "soft", natural = hairColor) {
  const g = new THREE.Group(), eyeC = "#2A1B26", soft = face === "soft";
  const dark = lum(skin) < 0.25;
  const blush = dark ? mix(skin, "#E0606A", 0.4) : mix(skin, "#F0607A", 0.5);
  const mouthC = dark ? mix(skin, "#F08A93", 0.5) : mix(skin, "#6B2230", 0.7);
  const browC = soft ? (bare ? shade(skin, -0.6) : shade(hairColor, lum(hairColor) > 0.3 ? -0.45 : 0.0)) : shade(natural, lum(natural) > 0.3 ? -0.45 : 0.0);
  const eyes = [];
  for (const sd of [-1, 1]) {
    const e = shinyEye(0.036, eyeC, 1.3); onHead(e, sd * 0.125, -0.02, 0.002); g.add(e); eyes.push(e);
    if (soft) g.add(onHead(ball(blush, 0.058, 0.036, 0.012, 0, 0, 0, 10), sd * 0.205, -0.088, -0.004));
    const b = onHead(soft ? ball(browC, 0.043, 0.0095, 0.012, 0, 0, 0, 8) : ball(browC, 0.052, 0.019, 0.014, 0, 0, 0, 8), sd * 0.125, soft ? 0.054 : 0.058, 0.0); b.rotateZ(sd * (soft ? -0.1 : -0.17)); g.add(b);
  }
  const mouth = new THREE.Group(); mouth.add(rot(ring(mouthC, 0.043, 0.0105, 2.2, 12, 6), 0, 0, -PI / 2 - 1.1));
  mouth.children[0].castShadow = false;
  onHead(mouth, 0, -0.078, 0.004); g.add(mouth);
  g.add(onHead(ball(shade(skin, -0.09), 0.024, 0.017, 0.016, 0, 0, 0, 10), 0, -0.057, 0.0));
  if (face === "moustache" || face === "goatee" || face === "beard") {
    for (const sd of [-1, 1]) { const m = onHead(ball(natural, 0.066, 0.02, 0.024, 0, 0, 0, 10), sd * 0.05, -0.066, 0.006); m.rotateZ(sd * 0.2); g.add(m); }
  }
  if (face === "goatee") g.add(onHead(ball(natural, 0.052, 0.05, 0.03, 0, 0, 0, 10), 0, -0.205, 0.0));
  if (face === "beard") {
    g.add(shell(natural, HX * 1.04, HY * 1.035, HZ * 1.04, 2.06, 0.66, 0.12, PI - 0.24, 24));                         // along the jaw, from ear to ear, under the mouth
    for (const sd of [-1, 1]) g.add(onHead(ball(natural, 0.05, 0.09, 0.04, 0, 0, 0, 10), sd * 0.262, -0.14, 0.002));  // the sides of the cheeks
    g.add(onHead(ball(natural, 0.1, 0.06, 0.04, 0, 0, 0, 12), 0, -0.2, 0.002));                                        // and the chin
  }
  if (face === "stubble") g.add(stubble(natural));
  g.userData.eyes = eyes;
  return g;
}

export function buildCharacter(look, opts = {}) {
  const L = cleanLook(look);
  const hat = HATS.includes(opts && opts.hat) ? opts.hat : "none";
  const seated = !!(opts && opts.seated);
  const skin = L.skin, tudung = L.hair === "tudung";
  let acc = L.accessory;
  if (tudung && (acc === "songkok" || acc === "cap")) acc = "none";
  if ((hat === "cap" || hat === "party" || hat === "crown") && (acc === "songkok" || acc === "cap")) acc = "none";
  if (hat === "shades" && (acc === "glasses" || acc === "round")) acc = "none";

  const root = new THREE.Group(); root.name = "character";
  const inner = new THREE.Group(); root.add(inner);
  const body = new THREE.Group(); inner.add(body);

  // body
  const torso = grp(0, 0.36, 0);
  const torsoShape = buildTorso(L.outfit, L.outfitColor, skin); torsoShape.position.y = -0.36;
  torso.add(torsoShape);
  const neck = rod(skin, 0.075, 0.08, 0.1, 0, 0.88, 0, 12);
  body.add(torso, neck);
  const armL = buildArm(1, L.outfit, L.outfitColor, skin), armR = buildArm(-1, L.outfit, L.outfitColor, skin);
  body.add(armL, armR);
  let legL = null, legR = null;
  if (!seated) {
    const kurung = L.outfit === "kurung";
    const pants = kurung ? shade(L.outfitColor, -0.12) : pantsFor(L.outfitColor);
    const shoes = lum(pants) > 0.3 || kurung ? "#3B3B4F" : "#F7F4FF";
    legL = buildLeg(1, pants, shoes, kurung); legR = buildLeg(-1, pants, shoes, kurung);
    body.add(legL, legR);
  }
  // head
  const headPivot = grp(0, 0.9, 0), head = grp(0, 0.3, 0);
  headPivot.add(head); body.add(headPivot);
  add(head, ball(skin, HX, HY, HZ, 0, 0, 0, 24));
  const capOn = hat === "cap" || acc === "cap" || acc === "songkok";
  const S = { rx: HX, ry: HY, rz: HZ, eyeX: 0.125, eyeY: -0.02, faceZ: 0.31, hat, capOn, darkSkin: lum(skin) < 0.2 };
  const hair = buildHair(L.hair, L.hairColor, S);
  S.vol = hair.userData.vol;
  const bare = L.hair === "bald" || tudung;
  const natural = HAIR_COLORS.indexOf(L.hairColor) >= NATURAL_HAIR ? HAIR_COLORS[1] : L.hairColor;   // (a purple beard is a step too far)
  const face = buildFace(skin, L.hairColor, bare, L.face, natural);
  head.add(face, hair);
  if (hair.userData.ears) for (const sd of [-1, 1]) head.add(ball(skin, 0.04, 0.062, 0.04, sd * 0.335, -0.03, -0.01, 10), ball(shade(skin, -0.1), 0.02, 0.036, 0.02, sd * 0.352, -0.03, -0.005, 8));
  if (acc === "glasses" || acc === "round") head.add(makeGlasses(acc, S));
  if (acc === "songkok") head.add(makeSongkok());
  if (acc === "cap") head.add(makeHat("cap", { ...S, capColor: capColorFor(L.outfitColor) }));
  if (acc === "flower") head.add(makeFlower(lum(L.hairColor) > 0.5 || lum(L.hairColor) < 0.02 ? "#FFD2E6" : "#FFFFFF", { rx: HX * S.vol, ry: HY * S.vol, rz: HZ * S.vol }));
  if (hat === "cap" || hat === "party" || hat === "crown" || hat === "shades") head.add(makeHat(hat, S));
  if (hat === "scarf") { const sc = makeScarf(0.17, 0.052); sc.position.y = 0.865; body.add(sc); }
  if (tudung) {
    const cape = lathe(L.hairColor, [[0, 0.52], [0.2, 0.53], [0.29, 0.6], [0.31, 0.7], [0.29, 0.8], [0.23, 0.9], [0.17, 0.96]], { seg: 24, sz: 0.72, double: true });
    body.add(cape);
  }

  // the seated half-figure: no legs, a little smaller, the head a touch bigger
  if (seated) {
    inner.scale.setScalar(0.85); inner.position.y = -0.36 * 0.85;
    head.scale.setScalar(1.08);
  }
  root.userData.kind = "character";

  // ---- life
  let walk = 0, phase = 0, clock = 0;
  const baseHeadY = head.position.y;
  const pony = hair.userData.pony;
  root.userData.tick = (t, dt, state) => {
    const d = typeof dt === "number" && dt > 0 && dt < 0.5 ? dt : 1 / 60;
    clock += d;
    const tt = typeof t === "number" && isFinite(t) ? t : clock;
    const moving = !seated && !!(state && state.moving);
    walk += ((moving ? 1 : 0) - walk) * Math.min(1, d * 9);
    phase += d * 9;
    const s = Math.sin(phase) * walk;
    // breathing and a gentle head tilt
    const br = Math.sin(tt * 2.3);
    torso.scale.set(1 + br * 0.008, 1 + br * 0.018, 1 + br * 0.008);
    headPivot.rotation.z = Math.sin(tt * 0.8) * 0.045 + Math.sin(tt * 0.31) * 0.02;
    headPivot.rotation.y = Math.sin(tt * 0.55) * 0.09 * (1 - walk * 0.6);
    headPivot.rotation.x = Math.sin(tt * 0.7) * 0.02 + walk * Math.abs(s) * 0.05;
    head.position.y = baseHeadY + br * 0.004;
    const k = blinkK(tt, 0.4);
    for (const e of face.userData.eyes) e.scale.y = k;
    body.position.y = Math.abs(s) * 0.04;
    body.rotation.z = s * 0.025;
    body.rotation.y = s * 0.07;
    if (legL) { legL.rotation.x = s * 0.7; legR.rotation.x = -s * 0.7; }
    if (seated) {
      armR.rotation.z = -(2.3 + Math.sin(tt * 6.5) * 0.3);
      armR.rotation.x = 0.1;
      armL.rotation.z = 0.12 + Math.sin(tt * 1.7) * 0.03;
      headPivot.rotation.z += -0.06;
      body.rotation.z = Math.sin(tt * 1.3) * 0.02;
    } else {
      armL.rotation.x = -s * 0.6; armR.rotation.x = s * 0.6;
      armL.rotation.z = 0.1 + Math.sin(tt * 1.7) * 0.02 * (1 - walk);
      armR.rotation.z = -0.1 - Math.sin(tt * 1.7 + 1) * 0.02 * (1 - walk);
    }
    if (pony) { pony.rotation.x = Math.sin(tt * 1.4) * 0.05 + walk * (Math.sin(phase * 2) * 0.12 + 0.12); pony.rotation.z = Math.sin(tt * 0.9) * 0.04; }
  };
  return root;
}

// =====================================================================================================================================================
// ---- pets: cute animals sitting on the floor, in a 1 x 1 cell, facing +z
const eyeDot = (r, c) => shinyEye(r, c || "#2B1B33", 1.15);
/** A shiny eye sitting on the skin of the head (radii R) at (x, y). */
function eyeOn(parent, R, x, y, r, c) { const e = eyeDot(r, c); onSurface(e, R[0], R[1], R[2], x, y, -r * 0.2); parent.add(e); return e; }
function cheekOn(parent, R, x, y, s = 0.05, c = "#FF9EB8") { const m = onSurface(ball(c, s, s * 0.62, s * 0.22, 0, 0, 0, 8), R[0], R[1], R[2], x, y, -0.006); parent.add(m); return m; }
function smile(color, r, x, y, z, arc = 2.2, tube = 0.011) {
  const w = grp(x, y, z);
  const m = rot(ring(color, r, tube, arc, 14, 5), 0, 0, -PI / 2 - arc / 2); m.castShadow = false;
  w.add(m);
  return w;
}
/** Finish a pet: records where the head is (so a hat can sit on it). */
function sat(g, extra) {
  Object.assign(g.userData, extra);
  g.userData.kind = "pet";
  return g;
}
const pairs = (f) => [-1, 1].map(f);

function petFish() {
  const g = new THREE.Group();
  const wood = "#C9A27A", woodDark = "#A97C50";
  const yc = 0.52, R = 0.4, Ri = R - 0.025;
  add(g, rod(wood, 0.3, 0.34, 0.1, 0, 0.05, 0, 24), rod(woodDark, 0.31, 0.31, 0.03, 0, 0.115, 0, 24));
  const cradle = rot(ring(woodDark, 0.2, 0.04, TAU, 24, 8), PI / 2, 0, 0); cradle.position.y = 0.14; g.add(cradle);
  // sand, a pebble and a little weed on the bottom of the bowl
  add(g, ball("#F0DDB0", 0.25, 0.045, 0.25, 0, yc - R + 0.065, 0, 16), ball("#D9C79A", 0.045, 0.03, 0.04, 0.13, yc - R + 0.11, 0.1, 8));
  const weed = grp(-0.17, yc - R + 0.09, -0.1);
  add(weed, spike("#4FB477", 0.04, 0.26, 0, 0.13, 0, 8), spike("#8AD4A1", 0.035, 0.2, 0.05, 0.1, 0.02, 8), spike("#4FB477", 0.03, 0.18, -0.05, 0.09, 0.02, 8));
  weed.children[1].rotation.z = -0.3; weed.children[2].rotation.z = 0.3;
  g.add(weed);
  // Finn: a round purple fish with big eyes, pink cheeks and a little shield with a check on each side
  const finn = new THREE.Group(), sw = new THREE.Group(); finn.add(sw); finn.scale.setScalar(1.3);
  const body = "#B7A0F3", fin = "#8D70DA", belly = "#EDE5FD";
  add(sw, ball(body, 0.15, 0.145, 0.2, 0, 0, 0, 18), ball(belly, 0.105, 0.065, 0.15, 0, -0.085, 0.04, 12));
  const tail = grp(0, 0, -0.17);
  add(tail, ball(fin, 0.014, 0.07, 0.085, 0, 0.04, -0.05, 10), ball(fin, 0.014, 0.07, 0.085, 0, -0.04, -0.05, 10));
  tail.children[0].rotation.x = -0.5; tail.children[1].rotation.x = 0.5;
  const dorsal = ball(fin, 0.014, 0.075, 0.1, 0, 0.15, -0.03, 10); dorsal.rotation.x = -0.35;
  const pecs = pairs((sd) => { const p = grp(sd * 0.14, -0.04, 0.05); p.add(ball(fin, 0.07, 0.014, 0.045, sd * 0.05, 0, -0.01, 8)); return p; });
  add(sw, tail, dorsal, ...pecs);
  const eyes = [];
  for (const sd of [-1, 1]) {
    const e = new THREE.Group();
    add(e, ball("#FFFFFF", 0.062, 0.066, 0.045, 0, 0, 0, 14), ball("#2B1B55", 0.041, 0.047, 0.03, 0, -0.004, 0.026, 12), ball("#FFFFFF", 0.015, 0.015, 0.012, 0.014, 0.018, 0.048, 6), ball("#FFFFFF", 0.008, 0.008, 0.006, -0.012, -0.014, 0.05, 6));
    e.position.set(sd * 0.085, 0.055, 0.155); e.rotation.y = sd * 0.5; sw.add(e); eyes.push(e);
    sw.add(ball("#FF9EB8", 0.04, 0.025, 0.014, sd * 0.125, -0.025, 0.14, 8));
    const sh = grp(sd * 0.148, 0.0, -0.005); sh.rotation.y = sd * PI / 2; sh.scale.setScalar(1.25);
    const shape = new THREE.Shape(); shape.moveTo(-0.05, 0.06); shape.lineTo(0.05, 0.06); shape.lineTo(0.05, -0.01); shape.quadraticCurveTo(0.05, -0.065, 0, -0.085); shape.quadraticCurveTo(-0.05, -0.065, -0.05, -0.01); shape.lineTo(-0.05, 0.06);
    const sm = finish(new THREE.Mesh(new THREE.ExtrudeGeometry(shape, { depth: 0.012, bevelEnabled: false }), mat("#F7F4FF"))); sm.position.z = -0.002;
    const c1 = slab("#5B3FB0", 0.012, 0.042, 0.008, -0.016, -0.004, 0.016), c2 = slab("#5B3FB0", 0.012, 0.066, 0.008, 0.012, 0.008, 0.016);
    c1.rotation.z = 0.8; c2.rotation.z = -0.7;
    add(sh, sm, c1, c2);
    sw.add(sh);
  }
  sw.add(smile("#5B3FB0", 0.032, 0, -0.04, 0.2, 2.0, 0.008));
  g.add(finn);
  // the bowl: a glass cup with a rim, and the water
  const wl = 0.22;
  const glass = see(shell("#DDF1FA", R, R, R, 0.5, PI - 0.5, 0, TAU, 28, glassMat("#DDF1FA", 0.35, true)), 4); glass.position.y = yc; g.add(glass);
  const rim = rot(ring("#E6F4FB", R * Math.sin(0.5), 0.014, TAU, 28, 6, { transparent: true, opacity: 0.7 }), PI / 2, 0, 0); rim.position.y = yc + R * Math.cos(0.5); see(rim, 4); g.add(rim);
  const th = Math.acos(wl / Ri);
  const water = see(shell("#7FD0EE", Ri, Ri, Ri, th, PI - th, 0, TAU, 28, glassMat("#8FD8F0", 0.14)), 3); water.position.y = yc; g.add(water);
  const top = see(new THREE.Mesh(new THREE.CircleGeometry(Ri * Math.sin(th), 28), mat("#A9E2F5", glassMat("#A9E2F5", 0.3))), 3); top.rotation.x = -PI / 2; top.position.y = yc + wl; g.add(top);
  const bubbles = [];
  for (let i = 0; i < 4; i++) { const b = see(ball("#FFFFFF", 1, 1, 1, 0, 0, 0, 10, { transparent: true, opacity: 0.6, depthWrite: false }), 5); g.add(b); bubbles.push(b); }
  const hl = see(ball("#FFFFFF", 0.04, 0.11, 0.02, -0.26, yc + 0.1, 0.27, 8, { transparent: true, opacity: 0.5, depthWrite: false }), 5); hl.rotation.z = 0.45; hl.rotation.y = -0.7; g.add(hl);
  g.userData.tick = (t) => {
    const a = t * 0.55;
    finn.position.set(Math.sin(a) * 0.04, yc - 0.06 + Math.sin(t * 1.3) * 0.02, Math.sin(a * 0.7 + 1) * 0.04);
    finn.rotation.y = -0.35 + Math.cos(a) * 0.5;
    sw.rotation.z = Math.sin(t * 1.3) * 0.05;
    tail.rotation.y = Math.sin(t * 6) * 0.45;
    pecs.forEach((p, i) => { p.rotation.z = Math.sin(t * 4 + i * PI) * 0.35 * (i ? 1 : -1); });
    const k = blinkK(t, 0.9); eyes.forEach((e) => { e.scale.y = k; });
    bubbles.forEach((b, i) => { const u = (t * 0.22 + i * 0.27) % 1; b.position.set(Math.sin(t * 0.8 + i * 2) * 0.05 + (i - 1.5) * 0.07, yc - 0.1 + u * 0.3, 0.14 + Math.cos(i * 1.7) * 0.06); b.scale.setScalar((0.03 - i * 0.004) * (u < 0.1 ? u * 10 : 1)); });
    weed.rotation.z = Math.sin(t * 1.1) * 0.06;
  };
  g.userData.tick(0.0);
  return sat(g, { noHat: true });
}

function petFox() {
  const g = new THREE.Group(), O = "#EE8A3A", W = "#FFF4E6", D = "#3B2A20", R = [0.34, 0.27, 0.28];
  const bodyG = new THREE.Group(); g.add(bodyG);
  add(bodyG, ball(O, 0.25, 0.27, 0.23, 0, 0.27, -0.02, 18), ball(W, 0.15, 0.2, 0.1, 0, 0.26, 0.15, 14));
  for (const sd of [-1, 1]) add(bodyG, ball(O, 0.11, 0.11, 0.15, sd * 0.2, 0.11, 0.0, 12), ball(D, 0.07, 0.12, 0.07, sd * 0.1, 0.1, 0.2, 12), ball(D, 0.075, 0.04, 0.09, sd * 0.1, 0.035, 0.225, 10));
  const head = grp(0, 0.64, 0.03); bodyG.add(head);
  add(head, ball(O, ...R, 0, 0, 0, 22), ball(W, 0.26, 0.15, 0.2, 0, -0.1, 0.07, 16));
  for (const sd of [-1, 1]) { const tf = spike(W, 0.07, 0.17, sd * 0.3, -0.1, 0.08, 10); tf.rotation.z = -sd * (PI / 2 + 0.4); head.add(tf); }
  add(head, ball(W, 0.1, 0.085, 0.14, 0, -0.06, 0.24, 14), ball("#2B1B33", 0.04, 0.03, 0.03, 0, -0.01, 0.375, 10));
  head.add(smile("#5A3B2E", 0.04, 0, -0.07, 0.345, 2.0, 0.008));
  const eyes = [eyeOn(head, R, -0.125, 0.045, 0.045), eyeOn(head, R, 0.125, 0.045, 0.045)];
  cheekOn(head, R, -0.2, -0.04, 0.045); cheekOn(head, R, 0.2, -0.04, 0.045);
  const ears = pairs((sd) => {
    const e = grp(sd * 0.2, 0.2, 0.0); e.rotation.z = -sd * 0.25;
    add(e, spike(O, 0.11, 0.22, 0, 0.11, 0, 12), spike(D, 0.052, 0.105, 0, 0.1725, 0, 10), spike("#FFE3D0", 0.065, 0.15, 0, 0.085, 0.04, 10));
    head.add(e); return e;
  });
  const tail = grp(0.1, 0.14, -0.18);
  const tl = limb(O, [[0, 0, 0], [0.1, 0.0, -0.16], [0.26, 0.02, -0.17], [0.34, 0.04, -0.03]], (u) => 0.075 + 0.085 * Math.sin(Math.min(1, u * 1.15) * PI * 0.85));
  const end = tl.userData.end;
  add(tail, tl, ball(W, 0.1, 0.1, 0.1, end.x, end.y, end.z, 12));
  bodyG.add(tail);
  g.userData.tick = (t) => {
    bodyG.scale.y = 1 + Math.sin(t * 2.1) * 0.014;
    head.rotation.z = Math.sin(t * 0.8) * 0.05; head.rotation.y = Math.sin(t * 0.5) * 0.12;
    const k = blinkK(t, 0.3); eyes.forEach((e) => { e.scale.y = k; });
    tail.rotation.y = Math.sin(t * 2.6) * 0.3;
    const tw = (t + 1.3) % 5; ears[0].rotation.x = tw < 0.25 ? Math.sin((tw / 0.25) * PI) * 0.35 : 0;
  };
  return sat(g, { head: { y: 0.64, z: 0.03, rx: R[0], ry: R[1], rz: R[2] } });
}

function petPanda() {
  const g = new THREE.Group(), W = "#FBF8FF", B = "#2A2630", R = [0.36, 0.3, 0.3];
  const bodyG = new THREE.Group(); g.add(bodyG);
  add(bodyG, ball(W, 0.28, 0.27, 0.25, 0, 0.27, -0.02, 18), ball("#F0EAF8", 0.18, 0.2, 0.1, 0, 0.26, 0.16, 14));
  const arms = pairs((sd) => { const a = grp(sd * 0.25, 0.4, 0.08); a.add(ball(B, 0.09, 0.17, 0.095, 0, -0.14, 0.02, 14)); a.rotation.z = sd * 0.35; a.rotation.x = -0.15; bodyG.add(a); return a; });
  for (const sd of [-1, 1]) add(bodyG, ball(B, 0.12, 0.1, 0.15, sd * 0.2, 0.1, 0.12, 14));
  add(bodyG, ball(W, 0.07, 0.07, 0.07, 0, 0.16, -0.26, 10));
  const head = grp(0, 0.66, 0.03); bodyG.add(head);
  add(head, ball(W, ...R, 0, 0, 0, 22), ball(B, 0.1, 0.1, 0.07, -0.25, 0.26, -0.02, 12), ball(B, 0.1, 0.1, 0.07, 0.25, 0.26, -0.02, 12));
  const eyes = [];
  for (const sd of [-1, 1]) {
    const p = onSurface(ball(B, 0.082, 0.108, 0.03, 0, 0, 0, 14), R[0], R[1], R[2], sd * 0.14, 0.0, 0.0); p.rotateZ(sd * 0.5); head.add(p);
    eyes.push(eyeOn(head, R, sd * 0.14, 0.0, 0.038, "#14101A"));
    cheekOn(head, R, sd * 0.255, -0.1, 0.05);
  }
  const nose = onSurface(ball(B, 0.05, 0.036, 0.034, 0, 0, 0, 12), R[0], R[1], R[2], 0, -0.065, 0.0);
  head.add(nose, smile(B, 0.035, 0, -0.09, 0.3, 2.0, 0.008));
  g.userData.tick = (t) => {
    bodyG.scale.y = 1 + Math.sin(t * 1.9) * 0.015;
    head.rotation.z = Math.sin(t * 0.7) * 0.06; head.rotation.y = Math.sin(t * 0.45) * 0.12;
    const k = blinkK(t, 0.6); eyes.forEach((e) => { e.scale.y = k; });
    arms[0].rotation.x = -0.15 + Math.sin(t * 1.9) * 0.04; arms[1].rotation.x = -0.15 + Math.sin(t * 1.9 + 1) * 0.04;
  };
  return sat(g, { head: { y: 0.66, z: 0.03, rx: R[0], ry: R[1], rz: R[2] } });
}

function petTiger() {
  const g = new THREE.Group(), O = "#F29A38", W = "#FFF6E8", D = "#2A1F26", R = [0.35, 0.28, 0.29];
  const bodyG = new THREE.Group(); g.add(bodyG);
  const bc = [0, 0.27, -0.02], br = [0.25, 0.27, 0.23];
  add(bodyG, ball(O, ...br, ...bc, 18), ball(W, 0.15, 0.2, 0.1, 0, 0.26, 0.15, 14));
  for (const sd of [-1, 1]) add(bodyG, ball(O, 0.11, 0.11, 0.15, sd * 0.2, 0.11, 0.0, 12), ball(O, 0.07, 0.12, 0.07, sd * 0.1, 0.1, 0.2, 12), ball(W, 0.075, 0.045, 0.09, sd * 0.1, 0.04, 0.225, 10));
  for (const [dx, dy, dz, sp] of [[0.95, 0.4, -0.1, 0.1], [0.98, -0.05, -0.1, 0.0], [-0.95, 0.4, -0.1, -0.1], [-0.98, -0.05, -0.1, 0.0], [0.0, 0.5, -0.9, 0], [0.0, -0.1, -1, 0]]) {
    bodyG.add(onBody(ball(D, 0.03, 0.095, 0.01, 0, 0, 0, 8), bc, br, dx, dy, dz, -0.002, Math.abs(dx) > 0.5 ? PI / 2 + sp : 0));
  }
  const head = grp(0, 0.66, 0.03); bodyG.add(head);
  add(head, ball(O, ...R, 0, 0, 0, 22));
  add(head, ball(W, 0.1, 0.085, 0.085, -0.075, -0.1, 0.21, 14), ball(W, 0.1, 0.085, 0.085, 0.075, -0.1, 0.21, 14));
  for (const sd of [-1, 1]) {
    const ear = grp(sd * 0.25, 0.23, 0.0); ear.rotation.z = -sd * 0.3;
    add(ear, ball(O, 0.1, 0.1, 0.06, 0, 0.05, 0, 12), ball("#FFD3C0", 0.06, 0.06, 0.03, 0, 0.045, 0.04, 10));
    head.add(ear);
    const cs = onSurface(ball(D, 0.055, 0.012, 0.01, 0, 0, 0, 8), R[0], R[1], R[2], sd * 0.3, -0.02, 0.0); cs.rotateZ(sd * 0.15); head.add(cs);
    const st = onSurface(ball(D, 0.016, 0.07, 0.01, 0, 0, 0, 8), R[0], R[1], R[2], sd * 0.1, 0.2, -0.002); st.rotateZ(sd * 0.25); head.add(st);
    cheekOn(head, R, sd * 0.235, -0.07, 0.045);
  }
  head.add(onSurface(ball(D, 0.016, 0.075, 0.01, 0, 0, 0, 8), R[0], R[1], R[2], 0, 0.21, -0.002));
  add(head, ball("#E8748F", 0.04, 0.03, 0.03, 0, -0.045, 0.295, 10));
  head.add(smile(D, 0.04, 0, -0.1, 0.28, 2.0, 0.008));
  const eyes = [eyeOn(head, R, -0.125, 0.04, 0.043), eyeOn(head, R, 0.125, 0.04, 0.043)];
  const tail = grp(0.1, 0.14, -0.2); bodyG.add(tail);
  const pts = [[0, 0, 0], [0.12, 0.0, -0.12], [0.26, 0.04, -0.1], [0.31, 0.2, -0.02], [0.26, 0.34, 0.02]];
  add(tail, limb(O, pts, () => 0.052, { u0: 0, u1: 0.3 }), limb(D, pts, () => 0.056, { u0: 0.3, u1: 0.42 }), limb(O, pts, () => 0.052, { u0: 0.42, u1: 0.62 }), limb(D, pts, () => 0.056, { u0: 0.62, u1: 0.76 }), limb(O, pts, () => 0.052, { u0: 0.76, u1: 0.9 }));
  const lt = new THREE.CatmullRomCurve3(pts.map((p) => new THREE.Vector3(...p))).getPointAt(1);
  add(tail, ball(D, 0.058, 0.058, 0.058, lt.x, lt.y, lt.z, 10));
  g.userData.tick = (t) => {
    bodyG.scale.y = 1 + Math.sin(t * 2.2) * 0.014;
    head.rotation.z = Math.sin(t * 0.8) * 0.05; head.rotation.y = Math.sin(t * 0.5) * 0.12;
    const k = blinkK(t, 0.2); eyes.forEach((e) => { e.scale.y = k; });
    tail.rotation.y = Math.sin(t * 2.8) * 0.35;
  };
  return sat(g, { head: { y: 0.66, z: 0.03, rx: R[0], ry: R[1], rz: R[2] } });
}

function petFrog() {
  const g = new THREE.Group(), G = "#5DBB63", GL = "#C6EC9B", GD = "#3E9B4F", R = [0.37, 0.22, 0.3];
  add(g, rod("#3FA06A", 0.43, 0.43, 0.035, 0, 0.0175, 0, 28));
  const bodyG = new THREE.Group(); bodyG.position.y = 0.03; g.add(bodyG);
  const belly = ball(GL, 0.23, 0.18, 0.12, 0, 0.2, 0.19, 14);
  add(bodyG, ball(G, 0.33, 0.26, 0.3, 0, 0.26, -0.02, 20), ball(G, ...R, 0, 0.45, 0.04, 20), belly);
  for (const sd of [-1, 1]) {
    add(bodyG, ball(G, 0.14, 0.17, 0.2, sd * 0.3, 0.17, -0.02, 14), ball(G, 0.11, 0.028, 0.14, sd * 0.31, 0.03, 0.2, 12), ball(G, 0.065, 0.13, 0.07, sd * 0.19, 0.11, 0.28, 12), ball(G, 0.1, 0.03, 0.09, sd * 0.2, 0.025, 0.35, 12));
    bodyG.add(ball("#FF9EB8", 0.05, 0.03, 0.012, sd * 0.27, 0.4, 0.25, 8));
  }
  const eyes = [];
  for (const sd of [-1, 1]) {
    const e = new THREE.Group(); e.position.set(sd * 0.2, 0.66, 0.05);
    add(e, ball(G, 0.125, 0.115, 0.125, 0, -0.02, -0.01, 16), ball("#FFFFFF", 0.1, 0.1, 0.1, 0, 0.0, 0.03, 14), ball("#2B1B33", 0.066, 0.075, 0.04, 0, -0.005, 0.1, 12), ball("#FFFFFF", 0.022, 0.022, 0.016, 0.022, 0.024, 0.138, 6));
    e.rotation.y = sd * 0.3; bodyG.add(e); eyes.push(e);
  }
  bodyG.add(smile("#2F6F3C", 0.17, 0, 0.5, 0.316, 2.0, 0.014));
  add(bodyG, ball(GD, 0.014, 0.014, 0.01, -0.06, 0.56, 0.33, 6), ball(GD, 0.014, 0.014, 0.01, 0.06, 0.56, 0.33, 6));
  g.userData.tick = (t) => {
    const b = Math.sin(t * 2.6);
    belly.scale.set(0.23 * (1 + b * 0.04), 0.18 * (1 + b * 0.06), 0.12);
    bodyG.scale.y = 1 + b * 0.012;
    const k = blinkK(t, 1.1); eyes.forEach((e) => { e.scale.y = k; });
    const hp = t % 6;
    bodyG.position.y = 0.03 + (hp < 0.4 ? Math.sin((hp / 0.4) * PI) * 0.05 : 0);
  };
  return sat(g, { head: { y: 0.5, z: 0.04, rx: R[0], ry: R[1], rz: R[2], base: 0.03 } });
}

function petOwl() {
  const g = new THREE.Group(), B = "#9B6B43", BD = "#6E4829", C = "#F1DDB8";
  const bodyG = new THREE.Group(); g.add(bodyG);
  add(bodyG, ball(B, 0.33, 0.4, 0.29, 0, 0.4, -0.02, 22), ball(C, 0.21, 0.26, 0.1, 0, 0.3, 0.2, 16));
  for (const [x, y] of [[-0.1, 0.07], [0.1, 0.07], [0, 0.0], [-0.12, -0.12], [0.12, -0.12], [0, -0.2]]) {
    bodyG.add(onBody(ball(BD, 0.04, 0.025, 0.012, 0, 0, 0, 8), [0, 0.3, 0.2], [0.21, 0.26, 0.1], x * 3, y * 3 + 0.2, 1.4, 0.0, 0));
  }
  const wings = pairs((sd) => { const w = grp(sd * 0.3, 0.5, -0.02); w.add(ball(BD, 0.075, 0.27, 0.17, 0, -0.18, 0, 14)); w.rotation.z = sd * 0.12; bodyG.add(w); return w; });
  for (const sd of [-1, 1]) add(bodyG, ball("#F2A33B", 0.06, 0.025, 0.09, sd * 0.1, 0.025, 0.2, 10), ball("#F2A33B", 0.03, 0.02, 0.05, sd * 0.1 - 0.05, 0.022, 0.24, 8), ball("#F2A33B", 0.03, 0.02, 0.05, sd * 0.1 + 0.05, 0.022, 0.24, 8));
  const head = grp(0, 0.66, 0.0); bodyG.add(head);
  const eyes = [];
  for (const sd of [-1, 1]) {
    add(head, ball(C, 0.15, 0.15, 0.04, sd * 0.14, 0.0, 0.245, 18));
    const e = new THREE.Group(); e.position.set(sd * 0.14, 0.0, 0.265);
    add(e, ball("#FFF3C2", 0.095, 0.095, 0.04, 0, 0, 0, 16), ball("#2B1B33", 0.058, 0.062, 0.03, 0, 0, 0.02, 14), ball("#FFFFFF", 0.02, 0.02, 0.015, 0.02, 0.022, 0.04, 6));
    head.add(e); eyes.push(e);
    const tuft = spike(BD, 0.075, 0.17, sd * 0.2, 0.2, -0.02, 10); tuft.rotation.z = -sd * 0.4; head.add(tuft);
  }
  const beak = spike("#F2A33B", 0.05, 0.11, 0, -0.065, 0.31, 10); beak.rotation.x = PI / 2 + 0.25; head.add(beak);
  g.userData.tick = (t) => {
    bodyG.scale.y = 1 + Math.sin(t * 1.8) * 0.014;
    head.rotation.z = Math.sin(t * 0.6) * 0.09; head.rotation.y = Math.sin(t * 0.4) * 0.2;
    const k = blinkK(t, 0.5, 3.6); eyes.forEach((e) => { e.scale.y = k; });
    wings[0].rotation.z = -0.12 - Math.max(0, Math.sin(t * 1.3)) * 0.06; wings[1].rotation.z = 0.12 + Math.max(0, Math.sin(t * 1.3)) * 0.06;
  };
  return sat(g, { head: { y: 0.66, z: 0.0, rx: 0.3, ry: 0.2, rz: 0.26 } });
}

function petOctopus() {
  const g = new THREE.Group(), P = "#B88BF0", T = "#D79BE8", R = [0.34, 0.37, 0.32];
  const bodyG = new THREE.Group(); g.add(bodyG);
  const head = grp(0, 0.55, 0); bodyG.add(head);
  add(head, ball(P, ...R, 0, 0, 0, 22));
  for (const [x, y, s] of [[-0.12, 0.3, 0.07], [0.12, 0.28, 0.06], [0.0, 0.2, 0.05]]) head.add(onSurface(ball("#E5A8F2", s, s, s * 0.3, 0, 0, 0, 10), R[0], R[1], R[2], x, y, -0.004));
  const eyes = [eyeOn(head, R, -0.14, -0.04, 0.066), eyeOn(head, R, 0.14, -0.04, 0.066)];
  cheekOn(head, R, -0.235, -0.12, 0.055); cheekOn(head, R, 0.235, -0.12, 0.055);
  head.add(smile("#6B3C8A", 0.04, 0, -0.07, 0.32, 2.0, 0.01));
  const tents = [];
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * TAU + 0.2, sc = 0.93, sgn = i % 2 ? 1 : -1;
    const pts = [[0.08, 0.27, 0], [0.2, 0.13, 0.03 * sgn], [0.33, 0.06, 0.0], [0.41, 0.09, -0.03 * sgn], [0.43, 0.17, 0.0], [0.38, 0.22, 0.03]].map(([x, y, z]) => [x * sc, y, z * sc]);
    const tg = grp(); tg.rotation.y = a;
    const c = i % 2 ? T : shade(T, 0.05);
    const tube = limb(c, pts, (u) => 0.078 - 0.05 * u, { seg: 20, rad: 7 });
    const e = tube.userData.end;
    add(tg, tube, ball(c, 0.03, 0.03, 0.03, e.x, e.y, e.z, 8));
    bodyG.add(tg); tents.push(tg);
  }
  g.userData.tick = (t) => {
    head.position.y = 0.55 + Math.sin(t * 1.6) * 0.012;
    head.rotation.z = Math.sin(t * 0.9) * 0.04;
    const k = blinkK(t, 0.7); eyes.forEach((e) => { e.scale.y = k; });
    tents.forEach((tg, i) => { tg.rotation.z = Math.sin(t * 1.8 + i * 0.9) * 0.07; tg.rotation.x = Math.cos(t * 1.4 + i * 1.3) * 0.04; });
  };
  return sat(g, { head: { y: 0.55, z: 0.0, rx: R[0], ry: R[1], rz: R[2] } });
}

function petTurtle() {
  const g = new THREE.Group(), SK = "#9BD27A", SH = "#4F9F5B", PL = "#6FC06F", SR = [0.4, 0.44, 0.33];
  const bodyG = new THREE.Group(); g.add(bodyG);
  add(bodyG, ball(SK, 0.3, 0.1, 0.3, 0, 0.12, -0.06, 16));
  const shellG = grp(0, 0.1, -0.06); bodyG.add(shellG);
  shellG.add(shell(SH, SR[0], SR[1], SR[2], 0, PI / 2, 0, TAU, 22));
  const rim = rot(ring("#E9D8A6", 1, 0.045, TAU, 28, 8), PI / 2, 0, 0); rim.scale.set(0.395, 0.33, 0.325); shellG.add(rim);
  const pl = (dx, dy, dz, s, c, spin) => shellG.add(onBody(ball(c, s, s * 0.95, 0.02, 0, 0, 0, 8), [0, 0, 0], SR, dx, dy, dz, -0.004, spin));
  pl(0, 1, 0, 0.11, PL, 0);
  for (let i = 0; i < 6; i++) { const a = (i / 6) * TAU + 0.5; pl(Math.sin(a) * 0.8, 0.62, Math.cos(a) * 0.8, 0.08, i % 2 ? PL : "#5CB065", -a); }
  for (const sd of [-1, 1]) add(bodyG, ball(SK, 0.09, 0.075, 0.1, sd * 0.27, 0.07, 0.12, 12), ball(SK, 0.09, 0.075, 0.1, sd * 0.25, 0.07, -0.25, 12));
  const tailC = spike(SK, 0.05, 0.12, 0, 0.1, -0.4, 8); tailC.rotation.x = -PI / 2 - 0.2; bodyG.add(tailC);
  const neck = grp(0, 0.2, 0.2); bodyG.add(neck);
  add(neck, ball(SK, 0.09, 0.09, 0.14, 0, -0.03, 0.0, 12));
  const head = grp(0, 0.05, 0.12); neck.add(head);
  const HR = [0.17, 0.15, 0.16];
  add(head, ball(SK, ...HR, 0, 0, 0, 18));
  const eyes = [eyeOn(head, HR, -0.075, 0.03, 0.032), eyeOn(head, HR, 0.075, 0.03, 0.032)];
  cheekOn(head, HR, -0.125, -0.04, 0.03); cheekOn(head, HR, 0.125, -0.04, 0.03);
  head.add(smile("#3E6B3A", 0.03, 0, -0.025, 0.155, 2.0, 0.007));
  g.userData.tick = (t) => {
    bodyG.scale.y = 1 + Math.sin(t * 1.5) * 0.012;
    neck.position.z = 0.2 + Math.sin(t * 0.7) * 0.025; head.rotation.x = Math.sin(t * 0.7 + 1) * 0.08; head.rotation.y = Math.sin(t * 0.5) * 0.18;
    const k = blinkK(t, 0.8, 4.6); eyes.forEach((e) => { e.scale.y = k; });
  };
  return sat(g, { noHat: true });
}

function petUnicorn() {
  const g = new THREE.Group(), W = "#FFF8FC", PK = "#F9C6DA", GOLD = "#E3B23C", R = [0.32, 0.27, 0.28];
  const rainbow = ["#E5546B", "#F08A4B", "#E3B23C", "#33B27C", "#3FA7E8", "#7A5CD0"];
  const bodyG = new THREE.Group(); g.add(bodyG);
  add(bodyG, ball(W, 0.26, 0.28, 0.24, 0, 0.26, -0.04, 18));
  for (const sd of [-1, 1]) add(bodyG, ball(W, 0.12, 0.12, 0.16, sd * 0.2, 0.12, 0.0, 12), ball(W, 0.07, 0.14, 0.075, sd * 0.1, 0.11, 0.2, 12), ball(PK, 0.08, 0.045, 0.085, sd * 0.1, 0.04, 0.215, 10), ball(PK, 0.07, 0.04, 0.08, sd * 0.2, 0.04, 0.1, 10));
  const head = grp(0, 0.56, 0.04); bodyG.add(head);
  add(head, ball(W, ...R, 0, 0, 0, 22), ball(PK, 0.095, 0.068, 0.085, 0, -0.115, 0.2, 16));
  add(head, ball("#E87FA5", 0.013, 0.01, 0.01, -0.035, -0.105, 0.28, 6), ball("#E87FA5", 0.013, 0.01, 0.01, 0.035, -0.105, 0.28, 6));
  head.add(smile("#B4467A", 0.03, 0, -0.085, 0.285, 2.0, 0.008));
  const horn = grp(0, 0.24, 0.16); horn.rotation.x = 0.5; head.add(horn);
  horn.add(spike(GOLD, 0.062, 0.27, 0, 0.135, 0, 12));
  for (let i = 0; i < 3; i++) { const rr = 0.05 - i * 0.0135, r = rot(ring("#B8841B", rr, 0.009, TAU, 12, 4), PI / 2, 0, 0); r.position.y = 0.05 + i * 0.07; horn.add(r); }
  const eyes = [eyeOn(head, R, -0.13, 0.03, 0.052, "#3B2A60"), eyeOn(head, R, 0.13, 0.03, 0.052, "#3B2A60")];
  cheekOn(head, R, -0.225, -0.07, 0.05); cheekOn(head, R, 0.225, -0.07, 0.05);
  for (const sd of [-1, 1]) {
    const ear = grp(sd * 0.19, 0.2, -0.03); ear.rotation.z = -sd * 0.3; add(ear, spike(W, 0.07, 0.17, 0, 0.08, 0, 10), spike(PK, 0.04, 0.11, 0, 0.07, 0.03, 8)); head.add(ear);
  }
  // a rainbow fringe over the forehead, a mane down the back of the neck, and a rainbow tail
  [[-0.2, 0.15, 0.1], [-0.13, 0.2, 0.13], [-0.06, 0.225, 0.14], [0.06, 0.225, 0.14], [0.13, 0.2, 0.13], [0.2, 0.15, 0.1]].forEach(([x, y, z], i) => head.add(ball(rainbow[i], 0.07, 0.075, 0.06, x, y, z, 12)));
  [[0, 0.2, -0.17, 0.1], [0, 0.07, -0.27, 0.1], [0, -0.07, -0.31, 0.1], [0, -0.21, -0.29, 0.095], [0, -0.33, -0.25, 0.085]].forEach(([x, y, z, r], i) => head.add(ball(rainbow[i], r, r * 1.05, r, x, y, z, 12)));
  const tail = grp(0, 0.2, -0.25); bodyG.add(tail);
  [[0, 0.0, -0.05, 0.1], [0.04, 0.08, -0.14, 0.09], [0.1, 0.17, -0.19, 0.085], [0.17, 0.27, -0.18, 0.075], [0.2, 0.36, -0.12, 0.062]].forEach(([x, y, z, r], i) => tail.add(ball(rainbow[(i + 3) % 6], r, r, r, x, y, z, 12)));
  g.userData.tick = (t) => {
    bodyG.scale.y = 1 + Math.sin(t * 2.0) * 0.014;
    head.rotation.z = Math.sin(t * 0.75) * 0.05; head.rotation.y = Math.sin(t * 0.5) * 0.12;
    const k = blinkK(t, 0.15); eyes.forEach((e) => { e.scale.y = k; });
    tail.rotation.y = Math.sin(t * 2.4) * 0.28;
  };
  return sat(g, { head: { y: 0.56, z: 0.04, rx: R[0], ry: R[1], rz: R[2] } });
}

function petCat() {
  const g = new THREE.Group(), GR = "#9A9AAE", W = "#FDFBFF", D = "#6E6E86", R = [0.33, 0.28, 0.27];
  const bodyG = new THREE.Group(); g.add(bodyG);
  add(bodyG, ball(GR, 0.25, 0.28, 0.23, 0, 0.28, -0.02, 18), ball(W, 0.15, 0.2, 0.1, 0, 0.26, 0.16, 14));
  for (const sd of [-1, 1]) add(bodyG, ball(GR, 0.11, 0.12, 0.15, sd * 0.2, 0.12, 0.02, 12), ball(GR, 0.07, 0.13, 0.07, sd * 0.1, 0.11, 0.2, 12), ball(W, 0.075, 0.045, 0.09, sd * 0.1, 0.04, 0.225, 10));
  const head = grp(0, 0.66, 0.03); bodyG.add(head);
  add(head, ball(GR, ...R, 0, 0, 0, 22), ball(W, 0.12, 0.09, 0.09, 0, -0.1, 0.2, 14));
  add(head, ball("#F08AA8", 0.036, 0.026, 0.02, 0, -0.045, 0.285, 10));
  for (const sd of [-1, 1]) {
    head.add(smile(D, 0.025, sd * 0.026, -0.09, 0.275, 2.4, 0.007));
    const ear = grp(sd * 0.21, 0.22, 0.0); ear.rotation.z = -sd * 0.22;
    add(ear, spike(GR, 0.11, 0.2, 0, 0.1, 0, 4), spike("#F7B3C8", 0.065, 0.13, 0, 0.085, 0.045, 4));
    ear.children[0].rotation.y = PI / 4; ear.children[1].rotation.y = PI / 4;
    head.add(ear);
    cheekOn(head, R, sd * 0.235, -0.06, 0.05);
    for (let i = 0; i < 3; i++) { const w = rod("#FFFFFF", 0.004, 0.004, 0.22, 0, 0, 0, 4); w.position.set(sd * 0.22, -0.07 - (i - 1) * 0.026, 0.22); w.rotation.z = PI / 2 + sd * (i - 1) * -0.18; w.rotation.y = sd * 0.5; head.add(w); }
  }
  for (const [x, h] of [[-0.07, 0.07], [0, 0.085], [0.07, 0.07]]) head.add(onSurface(ball(D, 0.014, h, 0.01, 0, 0, 0, 8), R[0], R[1], R[2], x, 0.2, -0.002));
  const eyes = [eyeOn(head, R, -0.12, 0.04, 0.045, "#2B3B3B"), eyeOn(head, R, 0.12, 0.04, 0.045, "#2B3B3B")];
  const tail = grp(0.1, 0.12, -0.2); bodyG.add(tail);
  const pts = [[0, 0, 0], [0.12, 0.0, -0.12], [0.25, 0.03, -0.1], [0.31, 0.18, -0.04], [0.27, 0.33, 0.04], [0.19, 0.37, 0.02]];
  const tl = limb(GR, pts, (u) => 0.062 - 0.016 * u, { seg: 20 });
  const e = tl.userData.end;
  add(tail, tl, ball(W, 0.05, 0.05, 0.05, e.x, e.y, e.z, 10));
  g.userData.tick = (t) => {
    bodyG.scale.y = 1 + Math.sin(t * 2.4) * 0.016;
    head.rotation.z = Math.sin(t * 0.8) * 0.06; head.rotation.y = Math.sin(t * 0.5) * 0.14;
    const k = blinkK(t, 0.35); eyes.forEach((x) => { x.scale.y = k; });
    tail.rotation.y = Math.sin(t * 1.7) * 0.25;
  };
  return sat(g, { head: { y: 0.66, z: 0.03, rx: R[0], ry: R[1], rz: R[2] } });
}

function petPenguin() {
  const g = new THREE.Group(), BK = "#34305A", W = "#FDFBFF", OR = "#F2A33B", R = [0.29, 0.25, 0.26];
  const bodyG = new THREE.Group(); g.add(bodyG);
  add(bodyG, ball(BK, 0.31, 0.4, 0.28, 0, 0.4, -0.01, 22), ball(W, 0.22, 0.31, 0.12, 0, 0.35, 0.17, 16));
  for (const sd of [-1, 1]) add(bodyG, ball(OR, 0.1, 0.03, 0.13, sd * 0.12, 0.03, 0.2, 12));
  const flips = pairs((sd) => { const f = grp(sd * 0.3, 0.55, 0.0); f.add(ball(shade(BK, 0.03), 0.05, 0.2, 0.11, sd * 0.03, -0.15, 0, 12)); f.rotation.z = sd * 0.22; bodyG.add(f); return f; });
  const head = grp(0, 0.7, 0.01); bodyG.add(head);
  add(head, ball(BK, ...R, 0, 0, 0, 20), ball(W, 0.115, 0.125, 0.07, -0.13, -0.04, 0.19, 12), ball(W, 0.115, 0.125, 0.07, 0.13, -0.04, 0.19, 12));
  const eyes = [eyeOn(head, R, -0.125, 0.0, 0.04), eyeOn(head, R, 0.125, 0.0, 0.04)];
  cheekOn(head, R, -0.2, -0.08, 0.05); cheekOn(head, R, 0.2, -0.08, 0.05);
  add(head, ball(OR, 0.075, 0.04, 0.09, 0, -0.06, 0.275, 12), ball(shade(OR, -0.1), 0.06, 0.025, 0.07, 0, -0.095, 0.27, 10));
  g.userData.tick = (t) => {
    bodyG.scale.y = 1 + Math.sin(t * 2.0) * 0.014;
    head.rotation.z = Math.sin(t * 0.7) * 0.07; head.rotation.y = Math.sin(t * 0.45) * 0.14;
    const k = blinkK(t, 0.55); eyes.forEach((e) => { e.scale.y = k; });
    const fl = Math.max(0, Math.sin(t * 1.1)) ** 6;
    flips[0].rotation.z = -0.22 - fl * 0.45; flips[1].rotation.z = 0.22 + fl * 0.45;
  };
  return sat(g, { head: { y: 0.7, z: 0.01, rx: R[0], ry: R[1], rz: R[2] } });
}

function petLion() {
  const g = new THREE.Group(), GD = "#F0B24B", GL = "#FBE3B0", M1 = "#B8641F", M2 = "#9E4F16", R = [0.27, 0.25, 0.24];
  const bodyG = new THREE.Group(); g.add(bodyG);
  add(bodyG, ball(GD, 0.25, 0.27, 0.23, 0, 0.27, -0.02, 18), ball(GL, 0.15, 0.2, 0.1, 0, 0.26, 0.15, 14));
  for (const sd of [-1, 1]) add(bodyG, ball(GD, 0.11, 0.11, 0.15, sd * 0.2, 0.11, 0.0, 12), ball(GD, 0.07, 0.12, 0.07, sd * 0.1, 0.1, 0.2, 12), ball(GL, 0.075, 0.045, 0.09, sd * 0.1, 0.04, 0.225, 10));
  const head = grp(0, 0.58, 0.02); bodyG.add(head);
  for (let i = 0; i < 12; i++) { const a = (i / 12) * TAU; head.add(ball(i % 2 ? M1 : M2, 0.1, 0.1, 0.09, Math.sin(a) * 0.335, Math.cos(a) * 0.3, -0.07, 12)); }
  add(head, ball(M1, 0.36, 0.33, 0.14, 0, 0, -0.07, 16));
  add(head, ball(GD, ...R, 0, 0, 0.04, 20), ball(GL, 0.14, 0.1, 0.1, 0, -0.1, 0.21, 14), ball("#6B3A2A", 0.04, 0.03, 0.026, 0, -0.045, 0.3, 10));
  head.add(smile("#6B3A2A", 0.028, -0.028, -0.09, 0.3, 2.4, 0.007), smile("#6B3A2A", 0.028, 0.028, -0.09, 0.3, 2.4, 0.007));
  const eyes = [];
  for (const sd of [-1, 1]) {
    const e = eyeDot(0.042); e.position.set(sd * 0.115, 0.04, 0.245); e.rotation.y = sd * 0.25; head.add(e); eyes.push(e); head.add(ball("#FF9EB8", 0.05, 0.03, 0.012, sd * 0.2, -0.06, 0.19, 8));
    add(head, ball(GD, 0.07, 0.07, 0.04, sd * 0.2, 0.2, 0.09, 12), ball("#F7B3A0", 0.04, 0.04, 0.02, sd * 0.2, 0.2, 0.125, 8));
  }
  const tail = grp(0.1, 0.12, -0.2); bodyG.add(tail);
  const tl = limb(GD, [[0, 0, 0], [0.12, 0.0, -0.1], [0.26, 0.04, -0.09], [0.33, 0.17, -0.03], [0.3, 0.29, 0.03]], (u) => 0.042 - 0.008 * u);
  const e = tl.userData.end;
  add(tail, tl, ball(M1, 0.07, 0.085, 0.07, e.x, e.y + 0.03, e.z, 12));
  g.userData.tick = (t) => {
    bodyG.scale.y = 1 + Math.sin(t * 2.0) * 0.014;
    head.rotation.z = Math.sin(t * 0.7) * 0.05; head.rotation.y = Math.sin(t * 0.45) * 0.12;
    const k = blinkK(t, 0.25); eyes.forEach((x) => { x.scale.y = k; });
    tail.rotation.y = Math.sin(t * 2.3) * 0.3;
  };
  return sat(g, { head: { y: 0.58, z: 0.04, rx: 0.34, ry: 0.3, rz: 0.26 } });
}

const PET_BUILDERS = { fish: petFish, fox: petFox, panda: petPanda, tiger: petTiger, frog: petFrog, owl: petOwl, octopus: petOctopus, turtle: petTurtle, unicorn: petUnicorn, cat: petCat, penguin: petPenguin, lion: petLion };
const petKey = (id) => String(id || "").toLowerCase().replace(/^pet-/, "");

/** Wrap a pet so that it stands in the middle of its cell and fits inside 0.9 x 0.9 and 1.0 tall (smaller ones are left alone). */
function fitPet(pet) {
  pet.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(pet, true);
  const cx = (box.min.x + box.max.x) / 2, cz = (box.min.z + box.max.z) / 2;
  const loose = new THREE.Box3().setFromObject(pet);   // the plain box (what a quick size check measures) is a little bigger than the exact one
  const hw = Math.max(loose.max.x - cx, cx - loose.min.x), hd = Math.max(loose.max.z - cz, cz - loose.min.z);
  const s = Math.min(1, 0.445 / hw, 0.445 / hd, 0.99 / Math.max(0.01, loose.max.y - Math.min(0, loose.min.y)));
  const root = new THREE.Group();
  pet.scale.multiplyScalar(s);
  pet.position.set(-cx * s, box.min.y < 0 ? -box.min.y * s : 0, -cz * s);
  root.add(pet);
  const inner = pet.userData.tick;
  let clock = 0;
  root.userData = {
    kind: "pet", content: pet, head: pet.userData.head, noHat: pet.userData.noHat, scale: s,
    tick: (t, dt) => { clock += typeof dt === "number" && dt > 0 && dt < 0.5 ? dt : 1 / 60; if (inner) inner(typeof t === "number" && isFinite(t) ? t : clock, dt); },
  };
  return root;
}
export function buildPet(id) {
  const make = PET_BUILDERS[petKey(id)] || petFish;
  const root = fitPet(make());
  root.name = "pet";
  return root;
}

// ---- the driver: whoever sits in the toy car, waving
function petHat(pet, hat) {
  const h = pet.userData.head;
  if (!h || pet.userData.noHat || !HATS.includes(hat) || hat === "none") return null;
  const g = grp(0, h.y + (h.base || 0), h.z);
  if (hat === "scarf") {
    const sc = makeScarf(h.rx * 0.68, h.rx * 0.2); sc.position.y = -h.ry * 0.85; g.add(sc);
  } else {
    g.add(makeHat(hat, { rx: h.rx, ry: h.ry, rz: h.rz, vol: 1.0, eyeX: h.rx * 0.4, eyeY: h.ry * 0.12, faceZ: h.rz * 0.86, capColor: "#E5546B" }));
  }
  return g;
}

export function buildDriver(avatar, hat = "none") {
  const look = lookFromCode(avatar);
  if (look) return buildCharacter(look, { hat, seated: true });
  const pet = buildPet(avatar);
  const hg = petHat(pet, hat);
  if (hg) pet.userData.content.add(hg);
  const root = new THREE.Group(); root.name = "driver";
  const holder = new THREE.Group(); holder.scale.setScalar(0.7); holder.add(pet); root.add(holder);
  const inner = pet.userData.tick;
  root.userData.kind = "driver";
  let clock = 0;
  root.userData.tick = (t, dt, state) => {
    clock += typeof dt === "number" && dt > 0 && dt < 0.5 ? dt : 1 / 60;
    if (!(typeof t === "number" && isFinite(t))) t = clock;
    if (inner) inner(t, dt, state);
    holder.rotation.z = Math.sin(t * 3.2) * 0.05;
    holder.position.y = Math.max(0, Math.sin(t * 6.4)) * 0.025;
  };
  return root;
}
