// A few helpers for building the house's furniture, plants and pets out of simple shapes (no model files): one palette, cached materials, boxes and
// cylinders placed by their bottom, and a rounded box for soft-looking furniture. Everything is flat-shaded (Lambert), like the Scam Road scene.
import * as THREE from "../vendor/three.module.min.js";

export { THREE };
export const PAL = {
  wood: "#C9A27A", woodDark: "#A97C50", woodLight: "#E4CBA3", cream: "#F6EBD6", white: "#F7F4FF", paper: "#FFFDF7",
  plum: "#7A5CD0", plumLight: "#B7A0F3", plumDark: "#5B3FB0", lilac: "#E3DAF7",
  leaf: "#4FB477", leafDark: "#2F8F58", leafLight: "#8AD4A1", pot: "#E07B5A", potLight: "#F0A387", clay: "#C9674A",
  red: "#E5546B", redDark: "#B73A4E", orange: "#F08A4B", yellow: "#E3B23C", gold: "#D9A21B", teal: "#2BA3A3", blue: "#3FA7E8", navy: "#2D3070", pink: "#E26BA6", green: "#33B27C",
  ink: "#2B1B55", grey: "#A7A7A7", greyLight: "#D9D6E2", charcoal: "#3B3B4F", glass: "#BFE3F5", black: "#1F1A1A", skin: "#F5CFA8",
};

const mats = new Map();
export function mat(color, opts = {}) {
  const key = color + JSON.stringify(opts);
  if (!mats.has(key)) mats.set(key, new THREE.MeshLambertMaterial({ color, ...opts }));
  return mats.get(key);
}
const place = (m, x, y, z) => { m.position.set(x, y, z); m.castShadow = true; m.receiveShadow = true; return m; };

/** A box w x h x d whose bottom is at y and whose middle (x, z) is where you say. */
export function box(w, h, d, color, x = 0, y = 0, z = 0, opts) {
  return place(new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color, opts)), x, y + h / 2, z);
}
/** A cylinder (or a cone-ish frustum) standing on y. */
export function cyl(rTop, rBottom, h, color, x = 0, y = 0, z = 0, seg = 18, opts) {
  return place(new THREE.Mesh(new THREE.CylinderGeometry(rTop, rBottom, h, seg), mat(color, opts)), x, y + h / 2, z);
}
export function cone(r, h, color, x = 0, y = 0, z = 0, seg = 14, opts) {
  return place(new THREE.Mesh(new THREE.ConeGeometry(r, h, seg), mat(color, opts)), x, y + h / 2, z);
}
/** A ball (or an egg: sy stretches it up) whose middle is at y. */
export function sphere(r, color, x = 0, y = 0, z = 0, sy = 1, seg = 16, opts) {
  const m = place(new THREE.Mesh(new THREE.SphereGeometry(r, seg, Math.max(8, seg - 4)), mat(color, opts)), x, y, z);
  m.scale.y = sy;
  return m;
}
/** A box with rounded corners (radius r on the width/height edges): sofas, cushions, cabinets. Bottom at y, middle at (x, z). */
export function rbox(w, h, d, r, color, x = 0, y = 0, z = 0, opts) {
  const b = Math.min(r * 0.45, w / 4, h / 4, d / 4), iw = w - 2 * b, ih = h - 2 * b, rr = Math.max(0.001, Math.min(r - b, iw / 2, ih / 2));
  const s = new THREE.Shape();
  s.moveTo(rr, 0); s.lineTo(iw - rr, 0); s.quadraticCurveTo(iw, 0, iw, rr); s.lineTo(iw, ih - rr); s.quadraticCurveTo(iw, ih, iw - rr, ih);
  s.lineTo(rr, ih); s.quadraticCurveTo(0, ih, 0, ih - rr); s.lineTo(0, rr); s.quadraticCurveTo(0, 0, rr, 0);
  const g = new THREE.ExtrudeGeometry(s, { depth: d - 2 * b, bevelEnabled: true, bevelSize: b, bevelThickness: b, bevelSegments: 2, curveSegments: 6 });
  g.translate(-iw / 2, -ih / 2, -(d - 2 * b) / 2);
  return place(new THREE.Mesh(g, mat(color, opts)), x, y + h / 2, z);
}
/** A flat shape from [x, y] points, extruded `depth` deep (for signs, flags, leaves). Lies in the x/y plane; its back is at z = 0 and it comes out toward +z. */
export function shape(points, depth, color, x = 0, y = 0, z = 0, opts) {
  const s = new THREE.Shape(points.map(([px, py]) => new THREE.Vector2(px, py)));
  const m = new THREE.Mesh(new THREE.ExtrudeGeometry(s, { depth, bevelEnabled: false }), mat(color, opts));
  return place(m, x, y, z);
}
/** A ring lying flat (a rug's border, a lamp's rim). */
export function ring(rIn, rOut, color, x = 0, y = 0, z = 0, seg = 32, opts) {
  const m = place(new THREE.Mesh(new THREE.RingGeometry(rIn, rOut, seg), mat(color, { side: THREE.DoubleSide, ...opts })), x, y, z);
  m.rotation.x = -Math.PI / 2;
  return m;
}
export function group(...kids) {
  const g = new THREE.Group();
  for (const k of kids.flat()) if (k) g.add(k);
  return g;
}
/** Soft glow for lamps and flames: it ignores light, so it looks lit. */
export function glow(r, color, x = 0, y = 0, z = 0, opacity = 0.9) {
  const m = new THREE.Mesh(new THREE.SphereGeometry(r, 14, 10), new THREE.MeshBasicMaterial({ color, transparent: true, opacity }));
  m.position.set(x, y, z);
  return m;
}
/** A little pot with a rim, for the plants. */
export function pot(color = PAL.pot, r = 0.22, h = 0.26, y = 0) {
  return group(cyl(r, r * 0.74, h, color, 0, y), cyl(r * 1.08, r * 1.08, 0.05, color, 0, y + h - 0.02), cyl(r * 0.92, r * 0.92, 0.02, "#5B3B2A", 0, y + h + 0.02));
}
