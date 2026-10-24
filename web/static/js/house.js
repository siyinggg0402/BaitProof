// The house: a toy room you decorate with the XP you earn. Tap a thing to pick it, drag it to move it, turn it, or put it away; buy new things in the shop.
// The server owns the rules (what you own, what it costs, what fits where, core/game/house.py) and checks every layout; this file draws the room and edits the layout.
// The same page, read-only, is a friend's house. Text on screen is real HTML over the canvas.
// On the Train page the same code draws a small read-only preview of your own room (data-mode="preview"): you can tap the floor to make your character walk, nothing else.
import * as THREE from "../vendor/three.module.min.js";
import { MODELS, buildCharacter } from "./house_models.js";
import { box, rbox, mat } from "./house_kit.js";

const $ = (id) => document.getElementById(id);
const rootEl = $("house"), VISIT = rootEl.dataset.visit || "", PREVIEW = rootEl.dataset.mode === "preview", READONLY = !!VISIT || PREVIEW;
const on = (id, type, fn, opts) => $(id)?.addEventListener(type, fn, opts);
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const WALL_H = 4.2;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

let renderer;
try { renderer = new THREE.WebGLRenderer({ canvas: $("scene"), antialias: true, alpha: true, powerPreference: "high-performance" }); } catch (_) { renderer = null; }
if (!renderer) { $("nogl").hidden = false; throw new Error("no WebGL"); }
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, PREVIEW ? 1.5 : 1.75));
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
$("scene").addEventListener("webglcontextlost", (e) => { e.preventDefault(); $("nogl").hidden = false; });

// ------------------------------------------------------------------------------------------------ state
const H = { view: null, W: 12, D: 10, placed: [], uid: 0, sel: null, drag: null, char: null, look: "", savedLook: "", tab: "plants", busy: false, walk: null };
const defs = new Map();            // item id -> the shop's description of it (name, price, size, kind, how many you own)
let saveTimer = 0, msgTimer = 0;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(27, 1, 0.5, 220);
scene.add(new THREE.HemisphereLight(0xffffff, 0xd9ccf5, 1.9));
const sun = new THREE.DirectionalLight(0xfff4e6, 1.3);
sun.castShadow = true; sun.shadow.mapSize.set(PREVIEW ? 1024 : 2048, PREVIEW ? 1024 : 2048); sun.shadow.bias = -0.0006; sun.shadow.normalBias = 0.03;
Object.assign(sun.shadow.camera, { left: -16, right: 16, top: 16, bottom: -16, near: 1, far: 70 });
scene.add(sun, sun.target);
const roomGroup = new THREE.Group(), itemsGroup = new THREE.Group();
scene.add(roomGroup, itemsGroup);
const marker = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ color: "#7A5CD0", transparent: true, opacity: 0.34, depthWrite: false, side: THREE.DoubleSide }));
marker.visible = false; marker.renderOrder = 5; scene.add(marker);

// ------------------------------------------------------------------------------------------------ the room itself
function canvasTex(w, h, draw, repeat) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const tx = new THREE.CanvasTexture(c);
  tx.colorSpace = THREE.SRGBColorSpace; tx.anisotropy = 4; tx.wrapS = tx.wrapT = THREE.RepeatWrapping;
  if (repeat) tx.repeat.set(repeat[0], repeat[1]);
  return tx;
}
function shade(hex, k) {
  const c = new THREE.Color(hex);
  c.multiplyScalar(k);
  return "#" + c.getHexString();
}
function seeded(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
function floorTexture(id, color) {
  const rnd = seeded([...id].reduce((a, ch) => a * 31 + ch.charCodeAt(0), 7));
  const repeat = [H.W / 4, H.D / 4];
  return canvasTex(256, 256, (g, w, h) => {
    g.fillStyle = color; g.fillRect(0, 0, w, h);
    if (id === "wood" || id === "oak") {
      for (let i = 0; i < 8; i++) {                      // eight planks, each a little different
        g.fillStyle = shade(color, 0.92 + rnd() * 0.14); g.fillRect(0, i * 32, w, 32);
        g.fillStyle = "rgba(60,30,10,.18)"; g.fillRect(0, i * 32, w, 2);
        const cut = rnd() * w; g.fillRect(cut, i * 32, 2, 32);
      }
    } else if (id === "tile") {
      for (let y = 0; y < 4; y++) for (let x = 0; x < 4; x++) { g.fillStyle = (x + y) % 2 ? shade(color, 0.96) : shade(color, 1.03); g.fillRect(x * 64, y * 64, 64, 64); }
      g.strokeStyle = "rgba(90,80,120,.25)"; g.lineWidth = 2; for (let i = 0; i <= 4; i++) { g.beginPath(); g.moveTo(i * 64, 0); g.lineTo(i * 64, h); g.moveTo(0, i * 64); g.lineTo(w, i * 64); g.stroke(); }
    } else if (id === "carpet") {
      for (let i = 0; i < 1400; i++) { g.fillStyle = rnd() > 0.5 ? "rgba(255,255,255,.16)" : "rgba(80,60,140,.12)"; g.fillRect(rnd() * w, rnd() * h, 3, 3); }
    } else {
      for (let i = 0; i < 700; i++) { g.fillStyle = rnd() > 0.5 ? "rgba(255,255,255,.2)" : "rgba(60,50,80,.14)"; g.beginPath(); g.arc(rnd() * w, rnd() * h, 1 + rnd() * 3, 0, 6.3); g.fill(); }
      g.strokeStyle = "rgba(60,50,80,.18)"; g.lineWidth = 2; g.strokeRect(1, 1, w - 2, h - 2);
    }
  }, repeat);
}
const floorMat = new THREE.MeshLambertMaterial({ color: "#ffffff" });
const wallMat = new THREE.MeshLambertMaterial({ color: "#E3DAF7" }), dadoMat = new THREE.MeshLambertMaterial({ color: "#CFC3EE" });
function buildRoom() {
  roomGroup.clear();
  const { W, D } = H;
  const slab = box(W + 0.8, 0.7, D + 0.8, "#7D6AA8", W / 2 + 0.2, -0.7, D / 2 + 0.2);
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(W, D), floorMat);
  floor.rotation.x = -Math.PI / 2; floor.position.set(W / 2, 0.002, D / 2); floor.receiveShadow = true;
  const back = new THREE.Mesh(new THREE.BoxGeometry(W + 0.4, WALL_H, 0.4), wallMat); back.position.set(W / 2 - 0.2, WALL_H / 2, -0.2);
  const left = new THREE.Mesh(new THREE.BoxGeometry(0.4, WALL_H, D), wallMat); left.position.set(-0.2, WALL_H / 2, D / 2);
  for (const m of [back, left]) m.receiveShadow = true;   // (walls take shadows but do not cast them: they would shade their own faces)
  const dadoB = new THREE.Mesh(new THREE.BoxGeometry(W, 1.05, 0.06), dadoMat); dadoB.position.set(W / 2, 0.525, 0.03);
  const dadoL = new THREE.Mesh(new THREE.BoxGeometry(0.06, 1.05, D), dadoMat); dadoL.position.set(0.03, 0.525, D / 2);
  const railB = box(W, 0.08, 0.1, "#FFFFFF", W / 2, 1.05, 0.05), railL = box(0.1, 0.08, D, "#FFFFFF", 0.05, 1.05, D / 2);
  const capB = box(W + 0.4, 0.12, 0.5, "#F4F0FF", W / 2 - 0.2, WALL_H, -0.2), capL = box(0.5, 0.12, D, "#F4F0FF", -0.2, WALL_H, D / 2);
  roomGroup.add(slab, floor, back, left, dadoB, dadoL, railB, railL, capB, capL);
  sun.position.set(W * 1.3, 12.5, D * 1.45); sun.target.position.set(W * 0.4, 0, D * 0.4);
}
function applyStyles() {
  const f = H.view.styles.floor.find((s) => s.id === H.view.floor) || H.view.styles.floor[0], w = H.view.styles.wall.find((s) => s.id === H.view.wall) || H.view.styles.wall[0];
  if (floorMat.map) floorMat.map.dispose();
  floorMat.map = floorTexture(f.id, f.color); floorMat.needsUpdate = true;
  wallMat.color.set(w.color); dadoMat.color.set(shade(w.color, 0.93));
}

// ------------------------------------------------------------------------------------------------ the camera
const cam = { zoom: 1, shopW: 0, shopH: 0 };
function frame() {
  const w = rootEl.clientWidth, h = rootEl.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  const shopRect = $("shop") && getComputedStyle($("shop")).display !== "none" ? $("shop").getBoundingClientRect() : null;
  const wide = shopRect && shopRect.left > w * 0.4;   // the shop beside the room (a big screen) or under it (a phone)
  cam.shopW = wide ? shopRect.width + 12 : 0; cam.shopH = shopRect && !wide ? shopRect.height + 8 : 0;
  const hud = PREVIEW ? 0 : 56, usableW = w - cam.shopW, usableH = h - cam.shopH - hud;
  const az = THREE.MathUtils.degToRad(42), el = THREE.MathUtils.degToRad(34);
  const target = new THREE.Vector3(H.W * 0.5, 1.1, H.D * 0.5);
  // far enough away that the room fits the space that is left (the picture is the whole canvas, shifted, so that space is a part of it)
  const spanH = H.W * Math.cos(az) + H.D * Math.sin(az) + 1.6, spanV = (H.W * Math.sin(az) + H.D * Math.cos(az)) * Math.sin(el) + WALL_H * Math.cos(el) + 1.2;
  const tanV = Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2), tanH = tanV * camera.aspect;
  const dist = Math.max(spanH / 2 / tanH * (w / usableW), spanV / 2 / tanV * (h / usableH)) * (PREVIEW ? 1.18 : 1) / cam.zoom;   // (a preview keeps a little air round the room)
  camera.position.set(target.x + dist * Math.sin(az) * Math.cos(el), target.y + dist * Math.sin(el), target.z + dist * Math.cos(az) * Math.cos(el));
  camera.lookAt(target);
  camera.setViewOffset(w, h, cam.shopW / 2, cam.shopH / 2 - hud / 2, w, h);
  camera.updateProjectionMatrix();
}
new ResizeObserver(frame).observe(rootEl);
on("zoom-in", "click", () => { cam.zoom = clamp(cam.zoom * 1.18, 0.7, 2); frame(); });
on("zoom-out", "click", () => { cam.zoom = clamp(cam.zoom / 1.18, 0.7, 2); frame(); });
if (!PREVIEW) $("scene").addEventListener("wheel", (e) => { e.preventDefault(); cam.zoom = clamp(cam.zoom * (e.deltaY < 0 ? 1.08 : 1 / 1.08), 0.7, 2); frame(); }, { passive: false });   // (a preview never traps the page's own scrolling)

// ------------------------------------------------------------------------------------------------ the rules the server keeps (mirrored here so the room can show what fits)
const dimsOf = (def, r) => (def.kind === "wall" ? { w: def.w, d: 1 } : r % 2 ? { w: def.d, d: def.w } : { w: def.w, d: def.d });
function cellsOf(ent) {
  const def = defs.get(ent.id), out = [];
  if (def.kind === "wall") { for (let k = 0; k < def.w; k++) out.push(`${ent.wall}:${ent.x + k}`); return out; }
  const { w, d } = dimsOf(def, ent.r);
  for (let i = 0; i < w; i++) for (let j = 0; j < d; j++) out.push(`${ent.x + i},${ent.z + j}`);
  return out;
}
function fits(ent, ignore) {
  const def = defs.get(ent.id);
  if (def.kind === "wall") {
    const len = ent.wall === "back" ? H.W : H.D;
    if (ent.x < 0 || ent.x + def.w > len) return false;
  } else {
    const { w, d } = dimsOf(def, ent.r);
    if (ent.x < 0 || ent.z < 0 || ent.x + w > H.W || ent.z + d > H.D) return false;
  }
  const mine = new Set(cellsOf(ent));
  for (const o of H.placed) {
    if (o === ignore || o === ent) continue;
    const od = defs.get(o.id);
    if ((od.kind === "wall") !== (def.kind === "wall") || (od.kind === "rug") !== (def.kind === "rug")) continue;   // floor things may stand on rugs
    if (cellsOf(o).some((c) => mine.has(c))) return false;
  }
  return true;
}
const placedCount = (id) => H.placed.filter((e) => e.id === id).length;
const spare = (id) => (defs.get(id)?.owned || 0) - placedCount(id);

// ------------------------------------------------------------------------------------------------ things in the room
function placeholder(def) {
  const g = new THREE.Group();
  g.add(rbox(Math.max(0.3, def.w - 0.2), 0.7, Math.max(0.3, def.d - 0.2), 0.1, "#B7A0F3"));
  return g;
}
function makeModel(id) {
  const def = defs.get(id);
  try { const m = (MODELS[id] || (() => placeholder(def)))(); return m; } catch (_) { return placeholder(def); }
}
function transform(ent) {
  const def = defs.get(ent.id), o = ent.obj;
  if (def.kind === "wall") {
    if (ent.wall === "back") { o.position.set(ent.x + def.w / 2, 0, 0); o.rotation.y = 0; } else { o.position.set(0, 0, ent.x + def.w / 2); o.rotation.y = Math.PI / 2; }
  } else {
    const { w, d } = dimsOf(def, ent.r);
    o.position.set(ent.x + w / 2, 0, ent.z + d / 2); o.rotation.y = (ent.r * Math.PI) / 2;
  }
  if (ent.follow) { ent.pos = o.position.clone(); ent.path = []; }     // (a pet that follows you starts from where it was put down)
}
function addEntity(entry) {
  const ent = { uid: ++H.uid, id: entry.item, x: entry.x, z: entry.z || 0, r: entry.r || 0, wall: entry.wall || "back", obj: null, follow: !!entry.follow, pos: null, path: [], pathFor: "" };
  ent.obj = makeModel(ent.id); ent.obj.userData.uid = ent.uid;
  transform(ent); itemsGroup.add(ent.obj); H.placed.push(ent);
  return ent;
}
function clearEntities() { for (const e of H.placed) itemsGroup.remove(e.obj); H.placed = []; H.sel = null; }
const toEntry = (e) => (defs.get(e.id).kind === "wall" ? { item: e.id, wall: e.wall, x: e.x } : { item: e.id, x: e.x, z: e.z, r: e.r, ...(e.follow ? { follow: true } : {}) });

function say(text, kind = "") {
  const m = $("msg"); if (!m) return;
  m.textContent = text; m.className = "hh-msg " + kind; m.hidden = !text;
  clearTimeout(msgTimer); if (text) msgTimer = setTimeout(() => { m.hidden = true; }, 3800);
}
async function api(path, body) {
  const r = await fetch(path, body === undefined ? undefined : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof data.detail === "string" ? data.detail : "http " + r.status);
  return data;
}
function scheduleSave() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(async () => {
    try { H.view = await api("/api/house/layout", { layout: H.placed.map(toEntry) }); syncDefs(); refreshPoints(); }
    catch (e) { say(e.message, "bad"); await load(); }      // the server did not like it: show what it has
  }, 250);
}

// ------------------------------------------------------------------------------------------------ choosing, moving, turning
function paintFollow() {
  const pressed = !!(H.sel && H.sel.follow);
  $("t-follow").setAttribute("aria-pressed", String(pressed)); $("t-follow").classList.toggle("on", pressed);
}
function marker3(ent, ok) {
  if (!ent || ent.follow) { marker.visible = false; return; }
  const def = defs.get(ent.id);
  marker.material.color.set(ok === false ? "#E5546B" : "#7A5CD0");
  marker.visible = true;
  if (def.kind === "wall") {
    marker.scale.set(def.w, 1.6, 1);
    if (ent.wall === "back") { marker.position.set(ent.x + def.w / 2, 2.4, 0.04); marker.rotation.set(0, 0, 0); } else { marker.position.set(0.04, 2.4, ent.x + def.w / 2); marker.rotation.set(0, Math.PI / 2, 0); }
  } else {
    const { w, d } = dimsOf(def, ent.r);
    marker.scale.set(w, d, 1); marker.position.set(ent.x + w / 2, 0.05, ent.z + d / 2); marker.rotation.set(-Math.PI / 2, 0, 0);
  }
}
function select(ent) {
  H.sel = ent || null;
  if (READONLY) return;
  $("tools").hidden = !ent;
  if (ent) { const def = defs.get(ent.id); $("tool-name").textContent = def.name; $("t-rotate").hidden = def.kind === "wall"; $("t-follow").hidden = def.cat !== "pets" ; paintFollow(); }
  marker3(ent, true);
  paintShop();
}
function turn() {
  const e = H.sel; if (!e || defs.get(e.id).kind === "wall") return;
  const next = { ...e, r: (e.r + 1) % 4 };
  // turning swaps the sides, so keep the item inside the room: slide it back if it would stick out
  const { w, d } = dimsOf(defs.get(e.id), next.r);
  next.x = clamp(next.x, 0, H.W - w); next.z = clamp(next.z, 0, H.D - d);
  if (!fits(next, e)) { say(t("That doesn't fit there."), "warn"); return; }
  Object.assign(e, { r: next.r, x: next.x, z: next.z }); transform(e); marker3(e, true); scheduleSave();
}
function putAway() {
  const e = H.sel; if (!e) return;
  itemsGroup.remove(e.obj); H.placed = H.placed.filter((x) => x !== e); select(null); keepCharacterOut(); scheduleSave(); paintShop();
}
function nudge(dx, dz) {
  const e = H.sel; if (!e) return;
  const def = defs.get(e.id), next = { ...e };
  if (def.kind === "wall") next.x = e.x + dx + dz; else { next.x = e.x + dx; next.z = e.z + dz; }
  if (!fits(next, e)) return;
  Object.assign(e, { x: next.x, z: next.z }); transform(e); marker3(e, true); keepCharacterOut(); scheduleSave();
}
// where a new thing goes: the nearest free spot to the middle of the room (a wall thing: the first free stretch of wall)
function autoPlace(id) {
  const def = defs.get(id);
  if (def.kind === "wall") {
    for (const wall of ["back", "left"]) for (let x = 0; x <= (wall === "back" ? H.W : H.D) - def.w; x++) if (fits({ id, wall, x }, null)) return { wall, x };
    return null;
  }
  let best = null, bestD = 1e9;
  for (let r = 0; r < 2; r++) {
    const { w, d } = dimsOf(def, r);
    for (let x = 0; x <= H.W - w; x++) for (let z = 0; z <= H.D - d; z++) {
      const dd = Math.hypot(x + w / 2 - H.W / 2, z + d / 2 - H.D * 0.58) + r * 0.3;
      if (dd < bestD && fits({ id, x, z, r }, null)) { best = { x, z, r }; bestD = dd; }
    }
  }
  return best;
}
function placeNew(id) {
  if (spare(id) <= 0) return;
  if (H.placed.length >= H.view.max_placed) { say(t("Your house is full."), "warn"); return; }
  const spot = autoPlace(id);
  if (!spot) { say(t("There is no room left for that."), "warn"); return; }
  const ent = addEntity({ item: id, ...spot });
  select(ent); keepCharacterOut(); scheduleSave(); say(defs.get(id).cat === "pets" ? t("Placed. Tap Follow me and it will walk with you.") : t("Placed. Drag it to move it."), "good");
}

// ------------------------------------------------------------------------------------------------ pointer: pick, drag, walk
const ray = new THREE.Raycaster(), ndc = new THREE.Vector2(), plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), hit = new THREE.Vector3();
function aim(e) {
  const r = $("scene").getBoundingClientRect();
  ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -(((e.clientY - r.top) / r.height) * 2 - 1));
  ray.setFromCamera(ndc, camera);
}
function floorAt(e) { aim(e); return ray.ray.intersectPlane(plane, hit) ? hit.clone() : null; }
function wallAt(e) {
  aim(e);
  let best = null;
  for (const [wall, n, c] of [["back", new THREE.Vector3(0, 0, 1), 0], ["left", new THREE.Vector3(1, 0, 0), 0]]) {
    const p = new THREE.Vector3();
    if (!ray.ray.intersectPlane(new THREE.Plane(n, -c), p)) continue;
    const along = wall === "back" ? p.x : p.z, len = wall === "back" ? H.W : H.D;
    if (along < -0.5 || along > len + 0.5 || p.y < 0 || p.y > WALL_H) continue;
    const dist = ray.ray.origin.distanceTo(p);
    if (!best || dist < best.dist) best = { wall, along, dist };
  }
  return best;
}
function pickEntity(e) {
  aim(e);
  const hits = ray.intersectObjects(itemsGroup.children, true);
  for (const h of hits) { let o = h.object; while (o && o.userData.uid === undefined) o = o.parent; if (o) return H.placed.find((x) => x.uid === o.userData.uid) || null; }
  return null;
}
let down = null;
$("scene").addEventListener("pointerdown", (e) => {
  if (e.button > 0) return;
  $("scene").setPointerCapture(e.pointerId);
  down = { x: e.clientX, y: e.clientY, ent: READONLY ? null : pickEntity(e), moved: false, orig: null };
  if (down.ent) { select(down.ent); down.orig = { x: down.ent.x, z: down.ent.z, r: down.ent.r, wall: down.ent.wall }; }
});
let hoverAt = 0;
$("scene").addEventListener("pointermove", (e) => {
  if (down || READONLY || e.pointerType === "touch") return;
  const now = performance.now(); if (now - hoverAt < 70) return; hoverAt = now;
  $("scene").classList.toggle("over", !!pickEntity(e));        // (a hand over things you can pick up)
});
$("scene").addEventListener("pointermove", (e) => {
  if (!down || !down.ent) return;
  if (!down.moved && Math.hypot(e.clientX - down.x, e.clientY - down.y) < 7) return;
  down.moved = true; $("scene").classList.add("grab");
  const ent = down.ent, def = defs.get(ent.id), next = { ...ent };
  if (def.kind === "wall") {
    const w = wallAt(e); if (!w) return;
    next.wall = w.wall; next.x = clamp(Math.round(w.along - def.w / 2), 0, (w.wall === "back" ? H.W : H.D) - def.w);
  } else {
    const p = floorAt(e); if (!p) return;
    const { w, d } = dimsOf(def, ent.r);
    next.x = clamp(Math.round(p.x - w / 2), 0, H.W - w); next.z = clamp(Math.round(p.z - d / 2), 0, H.D - d);
  }
  const ok = fits(next, ent);
  Object.assign(ent, { x: next.x, z: next.z, wall: next.wall }); transform(ent);
  ent.obj.position.y = 0.12; marker3(ent, ok);
  down.ok = ok;
});
$("scene").addEventListener("pointerup", (e) => {
  const d = down; down = null; $("scene").classList.remove("grab");
  if (!d) return;
  if (d.ent) {
    if (d.moved) {
      if (d.ok === false) { Object.assign(d.ent, d.orig); say(t("That doesn't fit there."), "warn"); } else scheduleSave();
      transform(d.ent); marker3(d.ent, true); keepCharacterOut();
    }
    return;
  }
  if (Math.hypot(e.clientX - d.x, e.clientY - d.y) > 8) return;
  const p = floorAt(e);
  select(null);
  if (p && p.x >= 0 && p.x <= H.W && p.z >= 0 && p.z <= H.D) walkTo(Math.floor(p.x), Math.floor(p.z));
});
$("scene").addEventListener("pointercancel", () => { down = null; });
addEventListener("keydown", (e) => {
  if (e.target.closest("input, textarea, select") || e.ctrlKey || e.metaKey) return;
  if (e.key === "r" || e.key === "R") turn();
  else if (e.key === "Delete" || e.key === "Backspace") { if (H.sel) { e.preventDefault(); putAway(); } }
  else if (e.key === "Escape") select(null);
  else if (e.key.startsWith("Arrow") && H.sel) { e.preventDefault(); nudge(e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0, e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0); }
});

// ------------------------------------------------------------------------------------------------ the character who lives here
function blockedCells() {
  const s = new Set();
  for (const e of H.placed) if (defs.get(e.id).kind === "floor" && !e.follow) for (const c of cellsOf(e)) s.add(c);    // (a pet that is out walking leaves its spot free)
  return s;
}
function findPath(from, to) {
  const blocked = blockedCells(), key = (x, z) => `${x},${z}`;
  if (blocked.has(key(to.x, to.z))) return null;
  const prev = new Map([[key(from.x, from.z), null]]), queue = [from];
  while (queue.length) {
    const c = queue.shift();
    if (c.x === to.x && c.z === to.z) { const path = []; let cur = c; while (cur) { path.unshift({ x: cur.x, z: cur.z }); cur = prev.get(key(cur.x, cur.z)); } return path.slice(1); }
    for (const [dx, dz] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const n = { x: c.x + dx, z: c.z + dz }, k = key(n.x, n.z);
      if (n.x < 0 || n.z < 0 || n.x >= H.W || n.z >= H.D || prev.has(k) || blocked.has(k)) continue;
      prev.set(k, c); queue.push(n);
    }
  }
  return null;
}
function placeCharacter() {
  if (H.char) scene.remove(H.char.obj);
  const look = parseLook(H.look) || parseLook("p.2.0.1.0.0.0");
  const obj = buildCharacter(look, { hat: "none" });
  obj.traverse((o) => { if (o.isMesh) { o.castShadow = true; } });
  H.char = { obj, cell: H.char ? H.char.cell : freeCell(), path: [], pos: null, heading: 0 };
  H.char.pos = new THREE.Vector3(H.char.cell.x + 0.5, 0, H.char.cell.z + 0.5);
  obj.position.copy(H.char.pos); scene.add(obj);
}
function freeCell() {
  const blocked = blockedCells();
  let best = null, bestD = 1e9;
  for (let x = 0; x < H.W; x++) for (let z = 0; z < H.D; z++) {
    if (blocked.has(`${x},${z}`)) continue;
    const d = Math.hypot(x + 0.5 - H.W * 0.55, z + 0.5 - H.D * 0.7);
    if (d < bestD) { best = { x, z }; bestD = d; }
  }
  return best || { x: 0, z: 0 };
}
function walkTo(x, z) {
  const c = H.char; if (!c) return;
  const here = { x: Math.floor(c.pos.x), z: Math.floor(c.pos.z) };
  const path = findPath(here, { x, z });
  if (path) c.path = path;
}
// something was put down on the character: step to the nearest free cell
function keepCharacterOut() {
  const c = H.char; if (!c) return;
  const cx = Math.floor(c.pos.x), cz = Math.floor(c.pos.z);
  if (!blockedCells().has(`${cx},${cz}`)) return;
  const cell = freeCell(); c.path = []; c.pos.set(cell.x + 0.5, 0, cell.z + 0.5); c.obj.position.copy(c.pos);
}
function stepCharacter(dt) {
  const c = H.char; if (!c) return;
  let moving = false;
  if (c.path.length) {
    const goal = new THREE.Vector3(c.path[0].x + 0.5, 0, c.path[0].z + 0.5), delta = goal.clone().sub(c.pos), len = delta.length(), step = 2.6 * dt;
    moving = true;
    c.heading = Math.atan2(delta.x, delta.z);
    if (len <= step) { c.pos.copy(goal); c.path.shift(); } else c.pos.addScaledVector(delta.normalize(), step);
    c.obj.position.copy(c.pos);
  }
  let dy = c.heading - c.obj.rotation.y; dy = Math.atan2(Math.sin(dy), Math.cos(dy));
  c.obj.rotation.y += dy * Math.min(1, dt * 10);
  c.obj.position.y = 0;
}

// pets that follow their owner: each walks the same free cells the character does, to a place behind them
const FOLLOW_GAP = [1.5, 2.4, 3.3];
const cellOf = (v) => ({ x: clamp(Math.floor(v.x), 0, H.W - 1), z: clamp(Math.floor(v.z), 0, H.D - 1) });
const followers = () => H.placed.filter((e) => e.follow);
function stepFollowers(dt, now) {
  const c = H.char; if (!c) return;
  followers().forEach((e, i) => {
    if (down && down.ent === e) { e.pos = e.obj.position.clone(); return; }     // being carried
    if (!e.pos) e.pos = e.obj.position.clone();
    const gap = FOLLOW_GAP[Math.min(i, FOLLOW_GAP.length - 1)], dx = c.pos.x - e.pos.x, dz = c.pos.z - e.pos.z, dist = Math.hypot(dx, dz);
    const cell = `${Math.floor(c.pos.x)},${Math.floor(c.pos.z)}`;
    let moving = false;
    if (dist > gap) {
      if (e.pathFor !== cell || !e.path.length) { e.path = findPath(cellOf(e.pos), cellOf(c.pos)) || []; e.pathFor = cell; }
      const goal = e.path.length ? new THREE.Vector3(e.path[0].x + 0.5, 0, e.path[0].z + 0.5) : null;
      if (goal) {
        const delta = goal.clone().sub(e.pos), len = delta.length(), step = 3 * dt;
        e.heading = Math.atan2(delta.x, delta.z); moving = true;
        if (len <= step) { e.pos.copy(goal); e.path.shift(); } else e.pos.addScaledVector(delta.normalize(), step);
      }
    } else e.path = [];
    if (e.heading !== undefined) { let d = e.heading - e.obj.rotation.y; d = Math.atan2(Math.sin(d), Math.cos(d)); e.obj.rotation.y += d * Math.min(1, dt * 10); }
    e.obj.position.set(e.pos.x, moving && !reduceMotion ? Math.abs(Math.sin(now * 11 + i)) * 0.09 : 0, e.pos.z);
  });
}
function toggleFollow() {
  const e = H.sel; if (!e || defs.get(e.id).cat !== "pets") return;
  if (!e.follow) {
    if (followers().length >= H.view.max_followers) { say(t("Only three pets can follow you at once."), "warn"); return; }
    e.follow = true; e.pos = e.obj.position.clone(); e.path = []; e.pathFor = "";
    say(t("{name} will follow you around.", { name: defs.get(e.id).name }), "good");
  } else {                                                                // it stops where it is: that cell (or the nearest free one) becomes its place
    e.follow = false;
    const spot = nearestFree(e, Math.floor(e.obj.position.x), Math.floor(e.obj.position.z));
    Object.assign(e, spot); transform(e);
  }
  paintFollow(); marker3(e, true); scheduleSave();
}
function nearestFree(e, x0, z0) {
  let best = { x: clamp(x0, 0, H.W - 1), z: clamp(z0, 0, H.D - 1) }, bestD = 1e9;
  for (let x = 0; x < H.W; x++) for (let z = 0; z < H.D; z++) {
    const d = Math.hypot(x - x0, z - z0);
    if (d < bestD && fits({ ...e, x, z, follow: false }, e)) { best = { x, z }; bestD = d; }
  }
  return best;
}

// ------------------------------------------------------------------------------------------------ the shop
const thumbs = new Map();
let thumbRenderer = null;
function thumbnail(id) {
  if (thumbs.has(id)) return thumbs.get(id);
  try {
    if (!thumbRenderer) { thumbRenderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true }); thumbRenderer.setSize(120, 120, false); thumbRenderer.setPixelRatio(1); }
    const s = new THREE.Scene(), def = defs.get(id);
    s.add(new THREE.HemisphereLight(0xffffff, 0xcdbff0, 1.2)); const l = new THREE.DirectionalLight(0xffffff, 0.8); l.position.set(5, 9, 7); s.add(l);
    const m = makeModel(id);
    if (def.kind === "wall") m.position.z = 0; s.add(m); m.updateMatrixWorld(true);
    const bb = new THREE.Box3().setFromObject(m), size = bb.getSize(new THREE.Vector3()), mid = bb.getCenter(new THREE.Vector3());
    const cm = new THREE.PerspectiveCamera(30, 1, 0.1, 100), r = Math.max(size.x, size.y, size.z) * 0.5 + 0.2, dist = r / Math.tan(THREE.MathUtils.degToRad(15)) * 1.15;
    const az = THREE.MathUtils.degToRad(def.kind === "wall" ? 18 : 40), el = THREE.MathUtils.degToRad(def.kind === "wall" ? 8 : 28);
    cm.position.set(mid.x + dist * Math.sin(az) * Math.cos(el), mid.y + dist * Math.sin(el), mid.z + dist * Math.cos(az) * Math.cos(el)); cm.lookAt(mid);
    thumbRenderer.render(s, cm);
    const c = document.createElement("canvas"); c.width = c.height = 120; c.getContext("2d").drawImage(thumbRenderer.domElement, 0, 0);
    thumbs.set(id, c); return c;
  } catch (_) { thumbs.set(id, null); return null; }
}
function refreshPoints() { if ($("points-n")) $("points-n").textContent = String(H.view.balance); }
function setTab(id) { H.tab = id; paintShop(); }
function paintTabs() {
  const tabs = [...H.view.categories, { id: "styles", name: t("Floors and walls") }];
  $("tabs").replaceChildren(...tabs.map((c) => {
    const b = document.createElement("button");
    b.type = "button"; b.className = "hh-tab"; b.setAttribute("role", "tab"); b.setAttribute("aria-selected", String(H.tab === c.id)); b.textContent = c.name;
    b.addEventListener("click", () => setTab(c.id));
    return b;
  }));
}
function priceTag(n) { const s = document.createElement("span"); s.className = "hh-price"; s.append(icon("star"), String(n)); return s; }
function button(label, onclick, opts = {}) {
  const b = document.createElement("button");
  b.type = "button"; b.className = "hh-buy" + (opts.alt ? " alt" : ""); b.textContent = label; b.disabled = !!opts.disabled; if (opts.title) b.title = opts.title;
  b.addEventListener("click", onclick);
  return b;
}
async function buy(id) {
  if (H.busy) return; H.busy = true;
  try {
    H.view = await api("/api/house/buy", { item: id }); syncDefs(); refreshPoints();
    placeNew(id); paintShop();
  } catch (e) { say(e.message, "warn"); } finally { H.busy = false; }
}
async function buyStyle(part, id) {
  if (H.busy) return; H.busy = true;
  try { H.view = await api("/api/house/style", { part, style: id }); syncDefs(); applyStyles(); refreshPoints(); paintShop(); }
  catch (e) { say(e.message, "warn"); } finally { H.busy = false; }
}
function paintShop() {
  if (READONLY) return;
  paintTabs();
  const list = $("list");
  if (H.tab === "styles") {
    const rows = [];
    for (const [part, label] of [["floor", t("Floors")], ["wall", t("Walls")]]) {
      const h = document.createElement("h3"); h.className = "hh-sub"; h.textContent = label; rows.push(h);
      for (const s of H.view.styles[part]) {
        const card = document.createElement("div"); card.className = "hh-card style";
        const sw = document.createElement("span"); sw.className = "hh-swatch"; sw.style.background = s.color;
        const using = H.view[part] === s.id, can = s.owned || H.view.balance >= s.price;
        card.append(sw, Object.assign(document.createElement("b"), { textContent: s.name }), s.owned ? document.createElement("span") : priceTag(s.price),
          button(using ? t("In use") : s.owned ? t("Use") : t("Buy"), () => buyStyle(part, s.id), { disabled: using || !can, title: !can ? t("Not enough XP yet.") : "" }));
        rows.push(card);
      }
    }
    list.replaceChildren(...rows); list.classList.add("styles");
    return;
  }
  list.classList.remove("styles");
  const items = H.view.items.filter((i) => i.cat === H.tab);
  list.replaceChildren(...items.map((it) => {
    const card = document.createElement("div"); card.className = "hh-card" + (H.sel && H.sel.id === it.id ? " sel" : "");
    const thumb = document.createElement("canvas"); thumb.width = thumb.height = 120; thumb.className = "hh-thumb"; thumb.setAttribute("aria-hidden", "true");
    const src = thumbnail(it.id); if (src) thumb.getContext("2d").drawImage(src, 0, 0);
    const free = spare(it.id), locked = !it.open && it.owned === 0, afford = H.view.balance >= it.price;
    const buttons = document.createElement("div"); buttons.className = "hh-btns";
    if (free > 0) buttons.append(button(t("Place"), () => placeNew(it.id), { alt: true }));
    if (!locked) buttons.append(button(t("Buy"), () => buy(it.id), { disabled: !afford || !it.open, title: !afford ? t("Not enough XP yet.") : "" }));
    const note = locked ? t("Only at {festival}", { festival: it.festival_name }) : it.owned ? t("{n} owned", { n: it.owned }) : "";
    card.append(thumb, Object.assign(document.createElement("b"), { textContent: it.name }), locked ? Object.assign(document.createElement("span"), { className: "hh-note", textContent: note }) : priceTag(it.price),
      ...(!locked && note ? [Object.assign(document.createElement("span"), { className: "hh-note", textContent: note })] : []), buttons);
    return card;
  }));
}

// ------------------------------------------------------------------------------------------------ loading
function syncDefs() { defs.clear(); for (const it of H.view.items) defs.set(it.id, it); }
async function load() {
  try {
    H.view = await api(VISIT ? `/api/house/visit/${VISIT}` : "/api/house");
  } catch (_) { $("lost").hidden = false; return; }
  $("lost").hidden = true;
  H.W = H.view.room.w; H.D = H.view.room.d;
  syncDefs();
  clearEntities(); buildRoom(); applyStyles(); frame();
  for (const p of H.view.layout) if (defs.has(p.item)) addEntity(p);
  H.look = H.savedLook = H.view.look;
  placeCharacter(); keepCharacterOut();
  select(null); refreshPoints(); paintShop();
  if (!READONLY && !H.view.has_character) say(t("Make your character: tap My character."), "good");
}
on("retry", "click", load);
if (!READONLY) {
  $("t-rotate").addEventListener("click", turn); $("t-follow").addEventListener("click", toggleFollow); $("t-pick").addEventListener("click", putAway); $("t-done").addEventListener("click", () => select(null));
  const sheet = $("char-sheet"), creator = sheet.querySelector("[data-creator]");
  $("open-char").addEventListener("click", () => { creator.setLook(H.look); sheet.hidden = false; sheet.querySelector(".cr-opt[aria-pressed=true]")?.focus(); });
  creator.addEventListener("look", (e) => { H.look = e.detail; placeCharacter(); });                     // (you see the change at once; Save keeps it)
  $("char-close").addEventListener("click", () => { H.look = H.savedLook; placeCharacter(); sheet.hidden = true; });
  $("char-save").addEventListener("click", async () => {
    try { H.view = await api("/api/house/look", { look: H.look }); H.savedLook = H.look; sheet.hidden = true; say(t("Saved. That's you!"), "good"); }
    catch (e) { say(e.message, "warn"); }
  });
}

// ------------------------------------------------------------------------------------------------ the loop
const clock = new THREE.Clock();
let raf = 0, firstFrame = true;
function tick() {
  const dt = Math.min(clock.getDelta(), 0.05), now = clock.elapsedTime;
  if (!reduceMotion) {
    for (const e of H.placed) e.obj.userData.tick?.(now, dt);
    if (H.char) H.char.obj.userData.tick?.(now, dt, { moving: H.char.path.length > 0 });
  }
  stepCharacter(dt); stepFollowers(dt, now);
  renderer.render(scene, camera);
  if (firstFrame) { firstFrame = false; rootEl.classList.add("ready"); }      // (the picture is there: the page can drop its stand-in)
  raf = requestAnimationFrame(tick);
}
function play(go) {
  if (go && !raf) { clock.getDelta(); raf = requestAnimationFrame(tick); }
  else if (!go && raf) { cancelAnimationFrame(raf); raf = 0; }
}
if (PREVIEW) {         // a preview only runs while you can see it
  let seen = true;
  const sync = () => play(seen && !document.hidden);
  new IntersectionObserver((entries) => { seen = entries[entries.length - 1].isIntersecting; sync(); }).observe(rootEl);
  document.addEventListener("visibilitychange", sync);
}
load().then(() => { frame(); play(true); });

// a hook for the browser test (and for anyone curious): where things are on the screen, and whether every model fits its footprint
window.__house = {
  state: H,
  screenOf(x, z, y = 0) { const v = new THREE.Vector3(x, y, z).project(camera), r = $("scene").getBoundingClientRect(); return { x: r.left + ((v.x + 1) / 2) * r.width, y: r.top + ((1 - v.y) / 2) * r.height }; },
  entity(i) { const e = H.placed[i]; if (!e) return null; const def = defs.get(e.id), b = new THREE.Box3().setFromObject(e.obj), c = b.getCenter(new THREE.Vector3()); return { id: e.id, x: e.x, z: e.z, r: e.r, wall: e.wall, center: this.screenOf(c.x, c.z, c.y), kind: def.kind }; },
  checkModels() {
    const bad = [];
    for (const [id, def] of defs) {
      let m; try { m = (MODELS[id] || (() => null))(); } catch (e) { bad.push([id, "throws " + e.message]); continue; }
      if (!m) { bad.push([id, "missing"]); continue; }
      m.updateMatrixWorld(true);
      const s = new THREE.Box3().setFromObject(m).getSize(new THREE.Vector3());
      if (def.kind === "wall" ? s.x > def.w + 0.01 : s.x > def.w - 0.02 || s.z > def.d - 0.02) bad.push([id, [+s.x.toFixed(2), +s.z.toFixed(2)]]);
    }
    return bad;
  },
};
