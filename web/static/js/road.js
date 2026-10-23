// Scam Road: a little car with Finn in the back window drives a three-lane road. A message is on the sign ahead; the lane you drive through is your answer.
// The server deals the messages and grades every lane (so the answer is never in the page), and adds up the distance. This file draws and drives.
// three.js is vendored (no CDN: the page's security policy only allows our own scripts). Text on screen is real HTML on top of the canvas.
// Everything you hear is made on the spot with the Web Audio API (no sound files), and every effect has an off switch.
import * as THREE from "../vendor/three.module.min.js";

const $ = (id) => document.getElementById(id);
const LANE_X = [-3, 0, 3];
const GATE_VIS = 110;          // metres of road between two signs (the server scores 80 per right answer; this is only how far apart they look)
const FIRST_GATE = 130;
const SEE = 190;               // how far ahead a sign appears
const ROAD_LEN = 420, TILE_M = 48;
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
const LANE_COLORS = ["#E5546B", "#E9A23B", "#33B27C"];
const rand = (a, b) => a + Math.random() * (b - a);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const ease = (x) => 1 - Math.pow(1 - x, 3);
const pill = (g, x, y, w, h, r) => { g.beginPath(); if (g.roundRect) g.roundRect(x, y, w, h, r); else g.rect(x, y, w, h); };   // (older browsers have no roundRect: square corners there)
const pref = {
  get(k, d) { try { const v = localStorage.getItem("bp-road-" + k); return v === null ? d : v; } catch (_) { return d; } },
  set(k, v) { try { localStorage.setItem("bp-road-" + k, String(v)); } catch (_) { /* no storage: it just forgets */ } },
};

// ------------------------------------------------------------------------------------------------ the game's own state
const G = {
  state: "intro",      // intro | driving | crash | why | paused | over | lost
  mode: "road", run: "", gates: [], cur: 0, answered: 0, T: 0, S: 0, Sshown: 0, Tlast: 0, lives: 3, combo: 0, lane: 1, laneX: 0, clock: 0,
  limit: 0, speedCfg: { base: 14, step: 0.4, max: 26 }, gateScore: 80, ghosts: [], replays: [], easy: pref.get("easy", "0") === "1", best: 0, account: false, ramp: 1, crashT: 0, pending: [], over: false, shake: 0, passedFlags: new Set(),
  skin: { color: "#7A5CD0", hat: "none", car: "plum" }, theme: pref.get("theme", "auto"), cars: {}, themeKey: "day",
};
$("easy").checked = G.easy;
let SEASON = null;       // the festival that is on today, if any (the server reads the calendar): {id, name, emoji, greeting}
try { SEASON = JSON.parse($("road").dataset.season || "{}"); if (!SEASON.id) SEASON = null; } catch (_) { SEASON = null; }
const previewTheme = /[?&]theme=([a-z]+)/.exec(location.search);   // ?theme=deepavali shows a look without waiting for the festival (and is not remembered)
if (previewTheme) G.theme = previewTheme[1];

// ------------------------------------------------------------------------------------------------ scene
let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas: $("scene"), antialias: true, alpha: false, powerPreference: "high-performance" });
} catch (_) { renderer = null; }
if (!renderer) { $("intro").hidden = true; $("nogl").hidden = false; throw new Error("no WebGL"); }
renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.75));
$("scene").addEventListener("webglcontextlost", (e) => { e.preventDefault(); G.state = "paused"; $("nogl").hidden = false; });

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(58, 1, 0.1, 460);
scene.fog = new THREE.Fog(new THREE.Color("#F2D4EE"), 45, 250);

function canvasTex(w, h, draw, repeat = false) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  draw(c.getContext("2d"), w, h);
  const tx = new THREE.CanvasTexture(c);
  tx.colorSpace = THREE.SRGBColorSpace; tx.anisotropy = 4;
  if (repeat) tx.wrapS = tx.wrapT = THREE.RepeatWrapping;
  return tx;
}
const EMOJI_FONT = "'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji',sans-serif";
const TEXT_FONT = "system-ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Noto Sans CJK SC', sans-serif";

const skyCanvas = document.createElement("canvas"); skyCanvas.width = 4; skyCanvas.height = 256;
const skyTex = new THREE.CanvasTexture(skyCanvas); skyTex.colorSpace = THREE.SRGBColorSpace;
scene.background = skyTex;

const hemi = new THREE.HemisphereLight(0xfff0fb, 0x8a78c4, 1.05); scene.add(hemi);
const sun = new THREE.DirectionalLight(0xffffff, 0.95); sun.position.set(-6, 12, 8); scene.add(sun);

// the road, with dashes that scroll
const roadTex = canvasTex(256, 512, (g, w, h) => {
  g.fillStyle = "#463F66"; g.fillRect(0, 0, w, h);
  g.fillStyle = "#F7F2FF"; g.fillRect(5, 0, 7, h); g.fillRect(w - 12, 0, 7, h);
  for (const x of [w / 3, (2 * w) / 3]) for (let y = 0; y < h; y += 128) g.fillRect(x - 4, y + 16, 8, 64);
}, true);
roadTex.repeat.set(1, ROAD_LEN / TILE_M);
const roadMat = new THREE.MeshLambertMaterial({ map: roadTex });
const road = new THREE.Mesh(new THREE.PlaneGeometry(9.4, ROAD_LEN), roadMat);
road.rotation.x = -Math.PI / 2; road.position.set(0, 0, -ROAD_LEN / 2 + 28); scene.add(road);

const grassTex = canvasTex(64, 256, (g, w, h) => { g.fillStyle = "#9ADCB0"; g.fillRect(0, 0, w, h); g.fillStyle = "#8ED3A6"; g.fillRect(0, 0, w, h / 2); }, true);
grassTex.repeat.set(8, ROAD_LEN / 16);
const grassMat = new THREE.MeshLambertMaterial({ map: grassTex });
const grass = new THREE.Mesh(new THREE.PlaneGeometry(220, ROAD_LEN), grassMat);
grass.rotation.x = -Math.PI / 2; grass.position.set(0, -0.03, -ROAD_LEN / 2 + 28); scene.add(grass);

// far away: a low sun (or a moon), soft hills, clouds, and stars for the night
const sunMat = new THREE.MeshBasicMaterial({ color: 0xffe9b8, fog: false });
const sunDisc = new THREE.Mesh(new THREE.CircleGeometry(26, 40), sunMat);
sunDisc.position.set(-30, 46, -330); scene.add(sunDisc);
const hillMat = new THREE.MeshLambertMaterial({ color: 0xc3b1f0 });
for (const [x, s] of [[-120, 1.3], [-40, 0.8], [60, 1.1], [150, 1.5]]) {
  const hill = new THREE.Mesh(new THREE.ConeGeometry(60 * s, 55 * s, 7), hillMat); hill.position.set(x, 20 * s, -340); scene.add(hill);
}
const clouds = [];
const cloudMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.92, fog: false });
for (let i = 0; i < 7; i++) {
  const c = new THREE.Group();
  for (let j = 0; j < 3; j++) { const b = new THREE.Mesh(new THREE.SphereGeometry(rand(5, 8), 10, 8), cloudMat); b.position.set(j * 7 - 7, rand(-1, 1), rand(-1, 1)); b.scale.y = 0.6; c.add(b); }
  c.position.set(rand(-150, 150), rand(34, 62), -rand(120, 330)); c.userData.v = rand(1.5, 4); scene.add(c); clouds.push(c);
}
const starGeo = new THREE.BufferGeometry(), starPos = new Float32Array(140 * 3);
for (let i = 0; i < 140; i++) starPos.set([rand(-260, 260), rand(40, 150), -rand(200, 360)], i * 3);
starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
const stars = new THREE.Points(starGeo, new THREE.PointsMaterial({ color: 0xffffff, size: 2.2, sizeAttenuation: false, fog: false, transparent: true, opacity: 0.9 })); stars.visible = false; scene.add(stars);

// roadside: trees, buildings and lamps that wrap around as they pass
const trunkG = new THREE.CylinderGeometry(0.3, 0.4, 1.8, 6), coneG = new THREE.ConeGeometry(1.6, 3.2, 7);
const trunkM = new THREE.MeshLambertMaterial({ color: 0x8b6b7a });
const leafMs = [0x6fcf9f, 0x86dcae, 0xa6e8c0].map((c) => new THREE.MeshLambertMaterial({ color: c }));
const winTex = (lit) => canvasTex(64, 128, (g, w, h) => {
  g.fillStyle = lit; g.fillRect(0, 0, w, h);
  for (let y = 10; y < h - 10; y += 22) for (let x = 8; x < w - 8; x += 20) { g.fillStyle = Math.random() < 0.55 ? "#FFF2B8" : "#8F82C8"; g.fillRect(x, y, 11, 13); }
});
const buildingMs = ["#C9B8F5", "#F3B9D4", "#B6D7F5", "#F7D7A8"].map((c) => new THREE.MeshLambertMaterial({ map: winTex(c) }));
const poleG = new THREE.CylinderGeometry(0.08, 0.1, 5.4, 6), bulbG = new THREE.SphereGeometry(0.34, 8, 6), lanternG = new THREE.SphereGeometry(0.5, 10, 8);
const capG = new THREE.ConeGeometry(0.66, 1.1, 7), capM = new THREE.MeshLambertMaterial({ color: 0xffffff });
const dishG = new THREE.CylinderGeometry(0.34, 0.22, 0.16, 10), flameG = new THREE.SphereGeometry(0.17, 8, 6);
const dishM = new THREE.MeshLambertMaterial({ color: 0xb4532a }), flameM = new THREE.MeshBasicMaterial({ color: 0xffb02e });
const poleM = new THREE.MeshLambertMaterial({ color: 0x5b4f85 }), bulbM = new THREE.MeshBasicMaterial({ color: 0xfff3b0 }), lanternM = new THREE.MeshBasicMaterial({ color: 0xe63946 });
function makeProp(kind) {
  const g = new THREE.Group();
  if (kind === "tree") {
    const t = new THREE.Mesh(trunkG, trunkM); t.position.y = 0.9; g.add(t);
    const m = leafMs[(Math.random() * leafMs.length) | 0];
    const a = new THREE.Mesh(coneG, m); a.position.y = 3.2; g.add(a);
    const b = new THREE.Mesh(coneG, m); b.position.y = 4.7; b.scale.setScalar(0.72); g.add(b);
    const cap = new THREE.Mesh(capG, capM); cap.position.y = 5.45; cap.visible = false; g.add(cap); g.userData.cap = cap;   // snow on top, at Christmas
  } else if (kind === "building") {
    const h = rand(7, 22), w = rand(5, 9), d = rand(5, 9);
    const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), buildingMs[(Math.random() * buildingMs.length) | 0]); m.position.y = h / 2; g.add(m);
  } else {
    const p = new THREE.Mesh(poleG, poleM); p.position.y = 2.7; g.add(p);
    const b = new THREE.Mesh(bulbG, bulbM); b.position.y = 5.5; g.add(b);
    const l = new THREE.Mesh(lanternG, lanternM); l.position.y = 5.2; l.scale.y = 1.25; l.visible = false; g.add(l); g.userData.lantern = l;   // for the festive roads
    const diya = new THREE.Group(); const dish = new THREE.Mesh(dishG, dishM); const flame = new THREE.Mesh(flameG, flameM); flame.position.y = 0.2; flame.scale.y = 1.5; diya.add(dish, flame);
    diya.position.set(0.9, 0.1, 0.6); diya.visible = false; g.add(diya); g.userData.diya = diya;   // a little oil lamp at the foot of the post, for Deepavali
  }
  g.userData.kind = kind;
  return g;
}
const props = [];
function placeProp(p, far) {
  const side = Math.random() < 0.5 ? -1 : 1;
  const k = p.userData.kind;
  const x = k === "lamp" ? side * 5.6 : k === "building" ? side * rand(15, 38) : side * rand(7.5, 26);
  p.position.set(x, 0, far ? -rand(8, 300) : -rand(250, 320));
  p.rotation.y = rand(0, 6.28); p.scale.setScalar(k === "tree" ? rand(0.8, 1.5) : 1);
}
for (let i = 0; i < 46; i++) { const kind = i % 10 < 6 ? "tree" : i % 10 < 8 ? "building" : "lamp"; const p = makeProp(kind); placeProp(p, true); scene.add(p); props.push(p); }

// a car, with Finn peeking over the back window (the player's own, and see-through ones for friends' ghosts)
function buildCar(colorHex, ghost) {
  const car = new THREE.Group(), mats = {};
  const mk = (color) => new THREE.MeshLambertMaterial(ghost ? { color, transparent: true, opacity: 0.5 } : { color });
  mats.body = mk(colorHex); mats.cabin = mk(0xd8cbfb); mats.glass = new THREE.MeshLambertMaterial({ color: 0x7fd0ee, transparent: true, opacity: ghost ? 0.4 : 0.88 });
  mats.tyre = mk(0x2b2347); mats.hub = mk(0xbfb3ee);
  const head = new THREE.MeshBasicMaterial({ color: 0xfff3b0 }), tail = new THREE.MeshBasicMaterial({ color: 0xff6b8b });
  const body = new THREE.Mesh(new THREE.BoxGeometry(2.1, 0.8, 4.2), mats.body); body.position.y = 0.85; car.add(body);
  const cabin = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.78, 2.1), mats.cabin); cabin.position.set(0, 1.62, 0.25); car.add(cabin);
  const rear = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.5, 0.06), mats.glass); rear.position.set(0, 1.62, 1.31); car.add(rear);
  const front = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.5, 0.06), mats.glass); front.position.set(0, 1.62, -0.82); car.add(front);
  for (const x of [-0.7, 0.7]) {
    const hl = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.22, 0.06), head); hl.position.set(x, 0.95, -2.12); car.add(hl);
    const tl = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.22, 0.06), tail); tl.position.set(x, 0.95, 2.12); car.add(tl);
  }
  const wheels = [];
  for (const [x, z] of [[-1.1, -1.4], [1.1, -1.4], [-1.1, 1.4], [1.1, 1.4]]) {
    const w = new THREE.Group();
    const t = new THREE.Mesh(new THREE.CylinderGeometry(0.46, 0.46, 0.38, 18), mats.tyre); t.rotation.z = Math.PI / 2; w.add(t);
    const h = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.4, 10), mats.hub); h.rotation.z = Math.PI / 2; w.add(h);
    w.position.set(x, 0.46, z); car.add(w); wheels.push(w);
  }
  if (!ghost) {
    const shadow = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 4.8), new THREE.MeshBasicMaterial({ color: 0x1c1038, transparent: true, opacity: 0.28 }));
    shadow.rotation.x = -Math.PI / 2; shadow.position.y = 0.02; car.add(shadow);
  }
  return { car, mats, wheels };
}
const player = buildCar(0x7a5cd0, false);
const car = player.car, carMats = player.mats, wheels = player.wheels;
scene.add(car);

// Finn: the picture, with a hat drawn on it when one is chosen
const FINN_W = 640, FINN_H = 520, OY = 106;
const finnCanvas = document.createElement("canvas"); finnCanvas.width = FINN_W; finnCanvas.height = FINN_H;
const finnTex = new THREE.CanvasTexture(finnCanvas); finnTex.colorSpace = THREE.SRGBColorSpace;
const finnImg = new Image();
let finnReady = false;
function drawFinn(hat) {
  if (!finnReady) return;
  const g = finnCanvas.getContext("2d"), Y = (y) => y + OY;
  g.clearRect(0, 0, FINN_W, FINN_H); g.drawImage(finnImg, 0, OY);
  g.lineJoin = "round"; g.lineCap = "round";
  if (hat === "crown") {
    g.fillStyle = "#F5C542"; g.strokeStyle = "#B8860B"; g.lineWidth = 6;
    g.beginPath(); g.moveTo(300, Y(88)); g.lineTo(296, Y(18)); g.lineTo(344, Y(52)); g.lineTo(386, Y(2)); g.lineTo(428, Y(52)); g.lineTo(476, Y(18)); g.lineTo(472, Y(88)); g.closePath(); g.fill(); g.stroke();
    g.fillStyle = "#E5546B"; for (const x of [344, 386, 428]) { g.beginPath(); g.arc(x, Y(70), 9, 0, 6.3); g.fill(); }
  } else if (hat === "party") {
    g.fillStyle = "#6C8CF5"; g.strokeStyle = "#2D3E9E"; g.lineWidth = 6;
    g.beginPath(); g.moveTo(318, Y(96)); g.lineTo(452, Y(96)); g.lineTo(386, Y(-52)); g.closePath(); g.fill(); g.stroke();
    g.strokeStyle = "#FFE08A"; g.lineWidth = 9; g.beginPath(); g.moveTo(340, Y(58)); g.lineTo(430, Y(58)); g.moveTo(358, Y(16)); g.lineTo(414, Y(16)); g.stroke();
    g.fillStyle = "#F5C542"; g.beginPath(); g.arc(386, Y(-54), 16, 0, 6.3); g.fill();
  } else if (hat === "cap") {
    g.fillStyle = "#E5546B"; g.strokeStyle = "#8E2236"; g.lineWidth = 6;
    g.beginPath(); g.ellipse(380, Y(96), 98, 74, 0, Math.PI, 0); g.closePath(); g.fill(); g.stroke();
    g.fillStyle = "#C93A52"; g.beginPath(); g.ellipse(486, Y(98), 84, 15, 0, 0, 6.3); g.fill(); g.stroke();
    g.fillStyle = "#fff"; g.beginPath(); g.arc(380, Y(26), 11, 0, 6.3); g.fill();
  } else if (hat === "shades") {
    g.fillStyle = "#1E1633"; g.strokeStyle = "#0E0A1E"; g.lineWidth = 6;
    pill(g, 342, Y(146), 112, 62, 24); g.fill(); g.stroke(); pill(g, 456, Y(146), 112, 62, 24); g.fill(); g.stroke();
    g.strokeStyle = "rgba(255,255,255,.55)"; g.lineWidth = 7; g.beginPath(); g.moveTo(362, Y(160)); g.lineTo(392, Y(160)); g.moveTo(476, Y(160)); g.lineTo(506, Y(160)); g.stroke();
  } else if (hat === "scarf") {
    g.strokeStyle = "#E5546B"; g.lineWidth = 48; g.beginPath(); g.moveTo(262, Y(168)); g.quadraticCurveTo(214, Y(238), 262, Y(318)); g.stroke();
    g.strokeStyle = "#FFE08A"; g.lineWidth = 10; g.beginPath(); g.moveTo(246, Y(196)); g.quadraticCurveTo(214, Y(238), 250, Y(296)); g.stroke();
    g.fillStyle = "#E5546B"; g.strokeStyle = "#8E2236"; g.lineWidth = 4; g.fillRect(236, Y(306), 40, 84); g.strokeRect(236, Y(306), 40, 84);
  }
  finnTex.needsUpdate = true;
}
finnImg.onload = () => { finnReady = true; drawFinn(G.skin.hat); };
finnImg.src = "/static/img/finn.png";
const finn = new THREE.Sprite(new THREE.SpriteMaterial({ map: finnTex, transparent: true }));
finn.scale.set(2.3, 2.3 * FINN_H / FINN_W, 1); finn.position.set(0, 2.6, 0.9); car.add(finn);

// the signs over the road: three lanes, three colours
function signTexture(emoji, label, color) {
  return canvasTex(256, 140, (g, w, h) => {
    g.fillStyle = color; pill(g, 4, 4, w - 8, h - 8, 26); g.fill();
    g.strokeStyle = "rgba(255,255,255,.85)"; g.lineWidth = 6; g.stroke();
    g.fillStyle = "#fff"; g.textAlign = "center"; g.textBaseline = "middle";
    g.font = `54px ${EMOJI_FONT}`; g.fillText(emoji, w / 2, 48);
    g.font = `800 34px ${TEXT_FONT}`; g.fillText(label, w / 2, 104, w - 24);
  });
}
const signTexs = [signTexture("🚨", t("Scam"), LANE_COLORS[0]), signTexture("🤔", t("Check first"), LANE_COLORS[1]), signTexture("✅", t("Looks fine"), LANE_COLORS[2])];
const postM = new THREE.MeshLambertMaterial({ color: 0x5b4f85 });
function makeGate() {
  const g = new THREE.Group();
  for (const x of [-5.4, 5.4]) { const p = new THREE.Mesh(new THREE.BoxGeometry(0.6, 9.2, 0.6), postM); p.position.set(x, 4.6, 0); g.add(p); }
  const beam = new THREE.Mesh(new THREE.BoxGeometry(11.8, 0.7, 0.7), postM); beam.position.y = 9.2; g.add(beam);
  g.userData.signs = []; g.userData.glows = [];
  LANE_X.forEach((x, i) => {
    const s = new THREE.Mesh(new THREE.PlaneGeometry(3.0, 1.64), new THREE.MeshBasicMaterial({ map: signTexs[i], transparent: true })); s.position.set(x, 7.9, 0.4); g.add(s); g.userData.signs.push(s);
    const gl = new THREE.Mesh(new THREE.PlaneGeometry(2.9, 22), new THREE.MeshBasicMaterial({ color: LANE_COLORS[i], transparent: true, opacity: 0.2, depthWrite: false }));
    gl.rotation.x = -Math.PI / 2; gl.position.set(x, 0.04, 11); g.add(gl); g.userData.glows.push(gl);
  });
  g.visible = false; scene.add(g);
  return g;
}
const gantries = [makeGate(), makeGate(), makeGate()];

// a soft round dot for sparks, fireworks and snow (a point is a square unless it has a picture)
const dotTex = canvasTex(64, 64, (g, w, h) => { const r = g.createRadialGradient(w / 2, h / 2, 2, w / 2, h / 2, w / 2); r.addColorStop(0, "rgba(255,255,255,1)"); r.addColorStop(0.45, "rgba(255,255,255,.85)"); r.addColorStop(1, "rgba(255,255,255,0)"); g.fillStyle = r; g.fillRect(0, 0, w, h); });
// sparks, confetti and smoke
const NP = 200;
const pGeo = new THREE.BufferGeometry(), pPos = new Float32Array(NP * 3), pCol = new Float32Array(NP * 3), pVel = new Float32Array(NP * 3), pLife = new Float32Array(NP);
pGeo.setAttribute("position", new THREE.BufferAttribute(pPos, 3)); pGeo.setAttribute("color", new THREE.BufferAttribute(pCol, 3));
const pts = new THREE.Points(pGeo, new THREE.PointsMaterial({ size: 0.7, map: dotTex, vertexColors: true, transparent: true, depthWrite: false, opacity: 0.95 }));
pts.frustumCulled = false; scene.add(pts);
let pNext = 0;
function emit(x, y, z, n, color, spread, up) {
  const c = new THREE.Color(color);
  for (let i = 0; i < n; i++) {
    const k = pNext++ % NP;
    pPos.set([x, y, z], k * 3); pCol.set([c.r, c.g, c.b], k * 3);
    pVel.set([rand(-spread, spread), rand(0.3, 1) * up, rand(-spread, spread)], k * 3); pLife[k] = rand(0.6, 1.2);
  }
}
function stepParticles(dt, dz) {
  for (let k = 0; k < NP; k++) {
    if (pLife[k] <= 0) { pPos[k * 3 + 1] = -50; continue; }
    pLife[k] -= dt; pVel[k * 3 + 1] -= 14 * dt;
    pPos[k * 3] += pVel[k * 3] * dt; pPos[k * 3 + 1] = Math.max(0.05, pPos[k * 3 + 1] + pVel[k * 3 + 1] * dt); pPos[k * 3 + 2] += pVel[k * 3 + 2] * dt + dz;
  }
  pGeo.attributes.position.needsUpdate = true; pGeo.attributes.color.needsUpdate = true;
}

// rain, only on a rainy road: short streaks that fall and wrap
const NR = 360, rainPos = new Float32Array(NR * 6), rainGeo = new THREE.BufferGeometry();
for (let i = 0; i < NR; i++) { const x = rand(-24, 24), y = rand(0, 30), z = rand(-120, 14); rainPos.set([x, y, z, x, y - 1.3, z], i * 6); }
rainGeo.setAttribute("position", new THREE.BufferAttribute(rainPos, 3));
const rain = new THREE.LineSegments(rainGeo, new THREE.LineBasicMaterial({ color: 0xdfe6ff, transparent: true, opacity: 0.55 })); rain.visible = false; rain.frustumCulled = false; scene.add(rain);
function stepRain(dt, dz) {
  for (let i = 0; i < NR; i++) {
    const o = i * 6; let y = rainPos[o + 1] - 38 * dt, z = rainPos[o + 2] + dz;
    if (y < 0 || z > 14) { y = rand(22, 32); z = rand(-120, -20); rainPos[o] = rainPos[o + 3] = rand(-24, 24); }
    rainPos[o + 1] = y; rainPos[o + 4] = y - 1.3; rainPos[o + 2] = rainPos[o + 5] = z;
  }
  rainGeo.attributes.position.needsUpdate = true;
}
// fireworks: bursts of glowing points high over the road (additive, so they fade to nothing as they cool)
const NF = 420, fwPos = new Float32Array(NF * 3), fwCol = new Float32Array(NF * 3), fwBase = new Float32Array(NF * 3), fwVel = new Float32Array(NF * 3), fwLife = new Float32Array(NF), fwGeo = new THREE.BufferGeometry();
fwGeo.setAttribute("position", new THREE.BufferAttribute(fwPos, 3)); fwGeo.setAttribute("color", new THREE.BufferAttribute(fwCol, 3));
const fw = new THREE.Points(fwGeo, new THREE.PointsMaterial({ size: 3.4, map: dotTex, vertexColors: true, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
fw.visible = false; fw.frustumCulled = false; scene.add(fw);
let fwNext = 0, fwTimer = 1;
function burst(colors) {
  const cx = rand(-48, 48), cy = rand(24, 44), cz = -rand(85, 150), c = new THREE.Color(colors[(Math.random() * colors.length) | 0]);
  for (let i = 0; i < 80; i++) {
    const k = fwNext++ % NF, th = rand(0, 6.283), ph = Math.acos(rand(-1, 1)), sp = rand(9, 16);
    fwPos.set([cx, cy, cz], k * 3); fwBase.set([c.r, c.g, c.b], k * 3); fwVel.set([sp * Math.sin(ph) * Math.cos(th), sp * Math.cos(ph), sp * Math.sin(ph) * Math.sin(th)], k * 3); fwLife[k] = rand(1.1, 1.8);
  }
}
function stepFireworks(dt, dz) {
  for (let k = 0; k < NF; k++) {
    if (fwLife[k] <= 0) { fwPos[k * 3 + 1] = -200; continue; }
    fwLife[k] -= dt; fwVel[k * 3 + 1] -= 5 * dt;
    fwPos[k * 3] += fwVel[k * 3] * dt; fwPos[k * 3 + 1] += fwVel[k * 3 + 1] * dt; fwPos[k * 3 + 2] += fwVel[k * 3 + 2] * dt + dz;
    const f = clamp(fwLife[k] / 1.1, 0, 1);
    fwCol[k * 3] = fwBase[k * 3] * f; fwCol[k * 3 + 1] = fwBase[k * 3 + 1] * f; fwCol[k * 3 + 2] = fwBase[k * 3 + 2] * f;
  }
  fwGeo.attributes.position.needsUpdate = true; fwGeo.attributes.color.needsUpdate = true;
}
// snow, for Christmas
const NS = 280, snowPos = new Float32Array(NS * 3), snowGeo = new THREE.BufferGeometry();
for (let i = 0; i < NS; i++) snowPos.set([rand(-24, 24), rand(0, 26), rand(-110, 12)], i * 3);
snowGeo.setAttribute("position", new THREE.BufferAttribute(snowPos, 3));
const snow = new THREE.Points(snowGeo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.42, map: dotTex, transparent: true, opacity: 0.95, depthWrite: false })); snow.visible = false; snow.frustumCulled = false; scene.add(snow);
function stepSnow(dt, dz) {
  for (let i = 0; i < NS; i++) {
    const o = i * 3; snowPos[o + 1] -= 2.3 * dt; snowPos[o] += Math.sin(performance.now() / 900 + i) * 0.6 * dt; snowPos[o + 2] += dz;
    if (snowPos[o + 1] < 0 || snowPos[o + 2] > 12) { snowPos[o] = rand(-24, 24); snowPos[o + 1] = rand(18, 28); snowPos[o + 2] = rand(-110, -10); }
  }
  snowGeo.attributes.position.needsUpdate = true;
}
// a crescent moon (Hari Raya)
const crescent = new THREE.Mesh(new THREE.PlaneGeometry(46, 46), new THREE.MeshBasicMaterial({ transparent: true, fog: false, map: canvasTex(256, 256, (g, w, h) => {
  g.fillStyle = "#FFF1B8"; g.beginPath(); g.arc(w / 2, h / 2, 100, 0, 6.283); g.fill();
  g.globalCompositeOperation = "destination-out"; g.beginPath(); g.arc(w / 2 + 52, h / 2 - 26, 88, 0, 6.283); g.fill();
}) }));
crescent.position.set(-45, 56, -328); crescent.visible = false; scene.add(crescent);
// lanterns floating over the road (Mid-Autumn)
const floaters = new THREE.Group(), floatCols = [0xffb347, 0xff7a8a, 0xffd86b, 0xff9a5a];
for (let i = 0; i < 16; i++) { const m = new THREE.Mesh(new THREE.SphereGeometry(rand(0.5, 0.8), 10, 8), new THREE.MeshBasicMaterial({ color: floatCols[i % 4] })); m.scale.y = 1.3; m.position.set(rand(-15, 15), rand(6, 16), -rand(5, 200)); floaters.add(m); }
floaters.visible = false; scene.add(floaters);
function stepFloaters(dz) { for (const m of floaters.children) { m.position.z += dz; m.position.y += Math.sin(performance.now() / 700 + m.position.x) * 0.01; if (m.position.z > 12) { m.position.z = -rand(160, 210); m.position.x = rand(-15, 15); } } }
const headlight = new THREE.SpotLight(0xfff1c8, 0, 60, 0.5, 0.6, 1.2); headlight.position.set(0, 1.2, -2); headlight.target.position.set(0, 0, -30); car.add(headlight); car.add(headlight.target);

// ------------------------------------------------------------------------------------------------ themes: day, night, rain, festive
const THEMES = {
  day:     { sky: ["#9C86F2", "#D9B8F3", "#F6D2EA", "#FFE3D0"], fog: "#F2D4EE", near: 45, far: 250, hemi: [0xfff0fb, 0x8a78c4, 1.05], sun: 0.95, grass: ["#9ADCB0", "#8ED3A6"], road: 0xffffff, hill: 0xc3b1f0, disc: 0xffe9b8, discX: -30, cloud: 0.92, lit: false },
  night:   { sky: ["#0B0826", "#20165A", "#4A2E8A", "#9A4F95"], fog: "#33225F", near: 35, far: 210, hemi: [0x7b72d8, 0x1e1648, 0.9], sun: 0.2, grass: ["#2C5C5C", "#244E50"], road: 0xb8b0e0, hill: 0x453a8f, disc: 0xf4f1ff, discX: 40, cloud: 0.25, lit: true, stars: true, lights: true },
  rain:    { sky: ["#5E6788", "#7F88A6", "#A5AABF", "#C4C6D4"], fog: "#A3A8BF", near: 25, far: 170, hemi: [0xdfe3f5, 0x6d7194, 0.95], sun: 0.35, grass: ["#6FA58C", "#689E86"], road: 0xcfd0e6, hill: 0x8e8cb4, disc: 0xd9dbe8, discX: -30, cloud: 0.95, lit: false, rain: true },
  festive: { sky: ["#7D2152", "#C93B67", "#F28A63", "#FFD48A"], fog: "#F3A97E", near: 45, far: 250, hemi: [0xfff0e6, 0xb2587a, 1.05], sun: 0.9, grass: ["#8FD3A0", "#84C998"], road: 0xffffff, hill: 0xd9608a, disc: 0xffd36e, discX: -30, cloud: 0.8, lit: false, lanterns: 0xe63946, confetti: true, pole: 0xa3283a },
  // the festivals (the server says which is on today; ?theme=raya previews one)
  cny:       { sky: ["#6E0F1F", "#B3202F", "#F0603E", "#FFD27A"], fog: "#EF8B62", near: 45, far: 250, hemi: [0xfff0e4, 0xa83a48, 1.05], sun: 0.85, grass: ["#86C98C", "#7DC083"], road: 0xffffff, hill: 0xc23b4b, disc: 0xffd36e, discX: -30, cloud: 0.7, lit: false, lanterns: 0xe5232f, confetti: true, pole: 0xa3283a, fireworks: ["#FFD36E", "#FF4B4B", "#FFFFFF"] },
  raya:      { sky: ["#052018", "#0E5A43", "#2E9C72", "#EFD98B"], fog: "#1E6D54", near: 40, far: 230, hemi: [0xd8ffee, 0x1c5a45, 0.95], sun: 0.3, grass: ["#2F8260", "#2A7653"], road: 0xcfe3d8, hill: 0x1d6a51, disc: 0xfff1b8, discX: -40, cloud: 0.3, lit: true, stars: true, crescent: true, lanterns: 0xf5c542, pole: 0x2a6b4f, fireworks: ["#F5C542", "#7CF0B8", "#FFFFFF"] },
  deepavali: { sky: ["#25104A", "#7B2A6E", "#E8733A", "#FFD27A"], fog: "#C45B46", near: 40, far: 240, hemi: [0xfff0d8, 0x7a3a60, 1.0], sun: 0.7, grass: ["#6F9A62", "#668F5B"], road: 0xffe9d6, hill: 0x8c3f6f, disc: 0xffb84a, discX: -30, cloud: 0.55, lit: false, diya: true, lanterns: 0xff9f1c, pole: 0x6a3a22, fireworks: ["#FFB84A", "#FF6B8B", "#B48CFF", "#FFFFFF"] },
  midautumn: { sky: ["#0E0828", "#33206B", "#774A98", "#F0A36B"], fog: "#46297A", near: 38, far: 230, hemi: [0xe9defc, 0x2c2060, 0.9], sun: 0.25, grass: ["#3C6E62", "#35665A"], road: 0xc9c2e8, hill: 0x4a3c8f, disc: 0xfff3c4, discX: -20, cloud: 0.3, lit: true, stars: true, bigMoon: true, floaters: true, pole: 0x6a3a22 },
  christmas: { sky: ["#34466E", "#7487AE", "#C0CEE4", "#EDF2F9"], fog: "#D5DFEE", near: 30, far: 210, hemi: [0xf4f8ff, 0x7f8fb3, 1.05], sun: 0.8, grass: ["#EAF2FB", "#DDE8F5"], road: 0xd8dcf0, hill: 0xc9d6ea, disc: 0xfff7d6, discX: -30, cloud: 0.9, lit: false, snow: true, lanterns: 0xe63946, pole: 0x8a2a33 },
  national:  { sky: ["#A8222B", "#E0525A", "#F8B7AF", "#FFF2EE"], fog: "#F5C8C2", near: 45, far: 250, hemi: [0xfff4f0, 0xc77a80, 1.05], sun: 0.85, grass: ["#9AD7A6", "#90CF9C"], road: 0xffffff, hill: 0xe06a72, disc: 0xfff2ec, discX: -30, cloud: 0.85, lit: false, lanterns: 0xffffff, confetti: true, pole: 0xb02a33, fireworks: ["#FFFFFF", "#FF4B4B", "#FFD3D3"] },
  merdeka:   { sky: ["#122F7A", "#3E69C9", "#F6E17B", "#FFF5C8"], fog: "#CFE0F7", near: 45, far: 250, hemi: [0xf5f8ff, 0x6f87c8, 1.05], sun: 0.9, grass: ["#8DD39C", "#83C993"], road: 0xffffff, hill: 0x4a73c9, disc: 0xffe27a, discX: -30, cloud: 0.85, lit: false, lanterns: 0xe63946, confetti: true, pole: 0x24408f, fireworks: ["#E63946", "#FFFFFF", "#2D5BD6", "#F5C542"] },
};
function themeFor(name) {
  const season = SEASON && THEMES[SEASON.id] ? SEASON.id : "";
  if (name === "auto") { if (season) return season; const h = new Date().getHours(); return h >= 19 || h < 6 ? "night" : "day"; }
  if (name === "festive") return season || "festive";     // "Festive" means the festival that is on, or a general one
  return THEMES[name] ? name : "day";
}
function applyTheme(name) {
  const key = themeFor(name), th = THEMES[key];
  const g = skyCanvas.getContext("2d"), grad = g.createLinearGradient(0, 0, 0, skyCanvas.height);
  th.sky.forEach((c, i) => grad.addColorStop([0, 0.55, 0.86, 1][i], c));
  g.fillStyle = grad; g.fillRect(0, 0, skyCanvas.width, skyCanvas.height); skyTex.needsUpdate = true;
  scene.fog.color.set(th.fog); scene.fog.near = th.near; scene.fog.far = th.far;
  hemi.color.set(th.hemi[0]); hemi.groundColor.set(th.hemi[1]); hemi.intensity = th.hemi[2]; sun.intensity = th.sun;
  const gc = grassTex.image.getContext("2d");
  gc.fillStyle = th.grass[0]; gc.fillRect(0, 0, 64, 256); gc.fillStyle = th.grass[1]; gc.fillRect(0, 0, 64, 128); grassTex.needsUpdate = true;
  roadMat.color.set(th.road); hillMat.color.set(th.hill); sunMat.color.set(th.disc); sunDisc.position.x = th.discX; cloudMat.opacity = th.cloud;
  stars.visible = !!th.stars; rain.visible = !!th.rain; headlight.intensity = th.lights ? 3.2 : 0;
  fw.visible = !!th.fireworks; snow.visible = !!th.snow; crescent.visible = !!th.crescent; floaters.visible = !!th.floaters; sunDisc.visible = !th.crescent; sunDisc.scale.setScalar(th.bigMoon ? 1.7 : 1);
  G.fireworkColors = th.fireworks || null; G.confetti = !!th.confetti;
  for (const m of buildingMs) { m.emissive.set(th.lit ? 0xffffff : 0x000000); m.emissiveMap = th.lit ? m.map : null; m.emissiveIntensity = th.lit ? 0.85 : 0; m.color.set(th.lit ? 0x6a6a9a : 0xffffff); m.needsUpdate = true; }
  bulbM.color.set(th.lit ? 0xffe27a : 0xfff3b0);
  lanternM.color.set(th.lanterns || 0xe63946);
  for (const p of props) { if (p.userData.lantern) p.userData.lantern.visible = !!th.lanterns; if (p.userData.diya) p.userData.diya.visible = !!th.diya; if (p.userData.cap) p.userData.cap.visible = !!th.snow; }
  poleM.color.set(th.pole || 0x5b4f85);
  G.themeKey = key;
}

// the friends' flags (the free drive): each stands where that friend's best distance would be
function flagTexture(g2) {
  return canvasTex(256, 112, (g, w, h) => {
    g.fillStyle = "rgba(60,36,130,.9)"; pill(g, 3, 3, w - 6, h - 6, 22); g.fill();
    g.strokeStyle = "#fff"; g.lineWidth = 4; g.stroke();
    g.textBaseline = "middle"; g.textAlign = "left"; g.font = `46px ${EMOJI_FONT}`; g.fillStyle = "#fff"; g.fillText(g2.avatar, 16, h / 2 + 2);
    g.font = `800 28px ${TEXT_FONT}`; g.fillText(g2.nickname, 78, 38, w - 90);
    g.font = "700 24px ui-monospace, Menlo, monospace"; g.fillStyle = "#FFE3A3"; g.fillText(t("{n} m", { n: g2.best }), 78, 78, w - 90);
  });
}
const flags = [];
function buildFlags() {
  flags.forEach((f) => scene.remove(f.obj)); flags.length = 0;
  G.ghosts.slice(0, 10).forEach((gh, i) => {
    const grp = new THREE.Group();
    const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 6.6, 6), postM); pole.position.y = 3.3; grp.add(pole);
    const ban = new THREE.Mesh(new THREE.PlaneGeometry(4.2, 1.84), new THREE.MeshBasicMaterial({ map: flagTexture(gh), transparent: true })); ban.position.set(0, 5.6, 0.15); grp.add(ban);
    const side = i % 2 ? 1 : -1; grp.position.x = side * 7.4; grp.visible = false; scene.add(grp);
    flags.push({ obj: grp, gh });
  });
}

// ------------------------------------------------------------------------------------------------ ghosts: friends' drives from today, replayed at their own pace beside the road
const GHOST_PENALTY = 1.6;    // seconds a crash costs a ghost, about what it costs a person
const ghosts = [];
function ghostLabel(avatar, name) {
  return canvasTex(256, 90, (g, w, h) => {
    g.fillStyle = "rgba(60,36,130,.88)"; pill(g, 3, 3, w - 6, h - 6, 24); g.fill(); g.strokeStyle = "#fff"; g.lineWidth = 4; g.stroke();
    g.textBaseline = "middle"; g.textAlign = "left"; g.font = `44px ${EMOJI_FONT}`; g.fillStyle = "#fff"; g.fillText(avatar, 14, h / 2 + 2);
    g.font = `800 30px ${TEXT_FONT}`; g.fillText(name, 72, h / 2 + 1, w - 84);
  });
}
const speedAt = (k) => Math.min(G.speedCfg.max, G.speedCfg.base + G.speedCfg.step * k);
function ghostTimeline(rp) {
  // the time at which a ghost reaches each gate: the real answer times in a live race, otherwise an estimate from the pace (a crash holds it up for a moment)
  const path = rp.path;
  if (rp.times && rp.times.length && rp.times.length === path.length) return rp.times.slice();
  const out = []; let t0 = 0;
  for (let k = 0; k < path.length; k++) {
    t0 += (k === 0 ? FIRST_GATE : GATE_VIS) / speedAt(k);
    out.push(t0);
    if (path[k] === "w") t0 += GHOST_PENALTY;
  }
  return out;
}
function buildGhosts() {
  ghosts.forEach((gh) => scene.remove(gh.obj)); ghosts.length = 0;
  G.replays.slice(0, 4).forEach((rp, i) => {
    const colour = G.cars[rp.car] && G.cars[rp.car] !== "rainbow" ? G.cars[rp.car] : "#7A5CD0";
    const b = buildCar(rp.you ? "#9FB4FF" : colour, true);
    const label = new THREE.Sprite(new THREE.SpriteMaterial({ map: ghostLabel(rp.avatar, rp.you ? t("You (best today)") : rp.nickname), transparent: true, depthTest: false }));
    label.scale.set(4.4, 1.55, 1); label.position.y = 4.3; b.car.add(label);
    b.car.visible = false; scene.add(b.car);
    ghosts.push({ rp, obj: b.car, wheels: b.wheels, tl: ghostTimeline(rp), side: i % 2 ? 1 : -1, slot: Math.floor(i / 2), crashed: new Set(), score: 0, wasAhead: true, spin: 0 });
  });
}
function ghostState(gh, clock) {
  // how far along the road this ghost is at `clock` seconds of driving, and how many metres it has earned by then
  const { tl, rp } = gh, n = tl.length, gateT = (j) => FIRST_GATE + j * GATE_VIS;
  let k = 0; while (k < n && tl[k] <= clock) k++;       // gates passed so far
  const done = k >= n && rp.finished !== false;     // (a rival still driving a live race is heading for the next gate; a recorded drive has ended)
  const from = k === 0 ? 0 : tl[k - 1] + (rp.path[k - 1] === "w" ? GHOST_PENALTY : 0);
  const T = done ? gateT(Math.max(0, n - 1)) : Math.min(gateT(k), (k === 0 ? 0 : gateT(k - 1)) + Math.max(0, clock - from) * speedAt(k));
  return { k, T, done, score: [...rp.path.slice(0, k)].filter((c) => c === "c").length * G.gateScore };
}
function stepGhosts(dt) {
  for (const gh of ghosts) {
    const st = ghostState(gh, G.clock), z = -(st.T - G.T);
    for (let j = 0; j < st.k; j++) {      // a crash at a gate: the ghost spins out in a puff of smoke, once
      if (gh.rp.path[j] === "w" && !gh.crashed.has(j)) { gh.crashed.add(j); gh.spin = 0.9; emit(gh.obj.position.x, 1.2, gh.obj.position.z, 24, "#6B6485", 2.5, 5); }
    }
    gh.obj.position.set(gh.side * (7.4 + gh.slot * 3.6), 0, z);
    gh.spin = Math.max(0, gh.spin - dt); gh.obj.rotation.y = gh.spin ? (1 - gh.spin / 0.9) * Math.PI * 2 : 0;
    gh.obj.visible = G.state !== "intro" && z > -SEE && z < 6 && !(st.done && G.clock > (gh.tl[gh.tl.length - 1] || 0) + 1.5);
    for (const w of gh.wheels) w.rotation.x -= (G.state === "driving" ? speedNow() * dt : 0) * 2.0;
    const ahead = st.T > G.T;
    if (gh.wasAhead && !ahead && G.state === "driving") { toast("🏁 " + t("You passed {name}'s best!", { name: gh.rp.you ? t("You (best today)") : gh.rp.nickname }), "good", 3000); emit(0, 3, -2, 30, "#FFE08A", 5, 8); Snd.passed(); }
    gh.wasAhead = ahead; gh.score = st.score;
  }
}

// ------------------------------------------------------------------------------------------------ sound: all of it is made here, and none of it plays unless it is on
const Snd = {
  ctx: null, master: null, engine: null, engineGain: null, musicTimer: 0, step: 0,
  on: pref.get("sound", "1") === "1", music: pref.get("music", "0") === "1", vibe: pref.get("vibe", "1") === "1",
  start() {
    if (this.ctx) { if (this.ctx.state === "suspended" && this.on) this.ctx.resume(); return; }
    try {
      const AC = window.AudioContext || window.webkitAudioContext; if (!AC) return;
      this.ctx = new AC(); this.master = this.ctx.createGain(); this.master.gain.value = this.on ? 0.6 : 0; this.master.connect(this.ctx.destination);
      const o = this.ctx.createOscillator(), f = this.ctx.createBiquadFilter(), g = this.ctx.createGain();
      o.type = "sawtooth"; o.frequency.value = 55; f.type = "lowpass"; f.frequency.value = 260; g.gain.value = 0; o.connect(f); f.connect(g); g.connect(this.master); o.start();
      this.engine = o; this.engineGain = g;
      this.musicLoop();
    } catch (_) { this.ctx = null; }
  },
  suspend() { try { if (this.ctx && this.ctx.state === "running") this.ctx.suspend(); } catch (_) { /* fine */ } },
  resume() { try { if (this.ctx && this.ctx.state === "suspended" && this.on) this.ctx.resume(); } catch (_) { /* fine */ } },
  setOn(v) { this.on = v; pref.set("sound", v ? "1" : "0"); if (this.master) this.master.gain.value = v ? 0.6 : 0; if (v) this.start(); },
  setMusic(v) { this.music = v; pref.set("music", v ? "1" : "0"); if (v) this.start(); },
  setVibe(v) { this.vibe = v; pref.set("vibe", v ? "1" : "0"); },
  tone(freq, dur = 0.16, type = "sine", vol = 0.2, delay = 0, slide = 0) {
    if (!this.ctx || !this.on) return;
    const t0 = this.ctx.currentTime + delay, o = this.ctx.createOscillator(), g = this.ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t0); if (slide) o.frequency.exponentialRampToValueAtTime(Math.max(30, freq + slide), t0 + dur);
    g.gain.setValueAtTime(0.0001, t0); g.gain.exponentialRampToValueAtTime(vol, t0 + 0.012); g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
    o.connect(g); g.connect(this.master); o.start(t0); o.stop(t0 + dur + 0.05);
  },
  noise(dur = 0.4, vol = 0.25, cutoff = 900) {
    if (!this.ctx || !this.on) return;
    const n = Math.floor(this.ctx.sampleRate * dur), buf = this.ctx.createBuffer(1, n, this.ctx.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / n);
    const s = this.ctx.createBufferSource(), f = this.ctx.createBiquadFilter(), g = this.ctx.createGain();
    f.type = "lowpass"; f.frequency.value = cutoff; g.gain.value = vol; s.buffer = buf; s.connect(f); f.connect(g); g.connect(this.master); s.start();
  },
  buzz(pattern) { if (this.vibe && this.on && navigator.vibrate) { try { navigator.vibrate(pattern); } catch (_) { /* some browsers refuse */ } } },
  right() { this.tone(660, 0.12, "triangle", 0.22); this.tone(990, 0.2, "triangle", 0.2, 0.09); this.buzz(25); },
  careful() { this.tone(330, 0.22, "sine", 0.18); },
  wrong() { this.noise(0.45, 0.35, 700); this.tone(220, 0.5, "sawtooth", 0.18, 0, -150); this.buzz([90, 50, 120]); },
  passed() { [523, 659, 784, 1047].forEach((f, i) => this.tone(f, 0.18, "triangle", 0.2, i * 0.08)); this.buzz([30, 30, 60]); },
  over() { [523, 440, 349, 262].forEach((f, i) => this.tone(f, 0.3, "triangle", 0.2, i * 0.16)); },
  unlock() { [784, 988, 1175, 1568].forEach((f, i) => this.tone(f, 0.16, "sine", 0.18, i * 0.07)); },
  // a gentle loop: a pentatonic arpeggio over four chords, in a soft triangle wave
  musicLoop() {
    clearInterval(this.musicTimer);
    const chords = [[0, 4, 7], [5, 9, 12], [3, 7, 10], [7, 11, 14]], base = 196;
    this.musicTimer = setInterval(() => {
      if (!this.ctx || !this.on || !this.music || this.ctx.state !== "running") return;
      const chord = chords[Math.floor(this.step / 8) % 4], note = chord[[0, 1, 2, 1, 2, 1, 0, 2][this.step % 8]];
      this.tone(base * Math.pow(2, note / 12), 0.34, "triangle", 0.07);
      if (this.step % 8 === 0) this.tone(base * Math.pow(2, chord[0] / 12) / 2, 0.9, "sine", 0.09);
      this.step++;
    }, 260);
  },
  drive(speed, moving) {
    if (!this.engineGain || !this.ctx) return;
    const now = this.ctx.currentTime;
    this.engine.frequency.setTargetAtTime(48 + speed * 2.6, now, 0.12);
    this.engineGain.gain.setTargetAtTime(this.on && moving ? 0.06 : 0, now, 0.15);
  },
};

// ------------------------------------------------------------------------------------------------ helpers for the page
function resize() {
  const r = $("road").getBoundingClientRect();
  renderer.setSize(r.width, r.height, false);
  camera.aspect = r.width / Math.max(1, r.height); camera.fov = camera.aspect < 0.8 ? 70 : 58; camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe($("road")); resize();

function speedNow() { return speedAt(G.answered) * (G.easy ? 0.7 : 1); }
const hearts = () => "❤️".repeat(Math.max(0, G.lives)) + "🖤".repeat(Math.max(0, 3 - G.lives));
function paintHud() {
  $("hearts").textContent = hearts(); $("hearts").setAttribute("aria-label", t("{n} lives left", { n: G.lives }));
  $("odo").textContent = t("{n} m", { n: Math.round(G.Sshown) });
  $("combo").hidden = G.combo < 2; $("combo").textContent = t("Combo x{n}", { n: G.combo });
  $("mode-chip").hidden = G.mode === "road";
  $("mode-chip").textContent = G.mode === "duel" ? t("Gate {n} of {m}", { n: Math.min(G.answered + 1, G.limit || 12), m: G.limit || 12 }) : t("Daily Road");
}
let toastTimer = 0;
function toast(text, kind = "", ms = 3600) {
  const el = $("toast"); el.textContent = text; el.className = "toast " + kind; el.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, ms);
}
function showMessage() {
  const g = G.gates[G.cur];
  $("msg").hidden = !g;
  if (g) {
    $("msg-text").textContent = g.text;
    const from = g.family ? "👪 " + t("From your family") : g.yours ? "📥 " + t("From your own inbox") : "";
    $("msg-from").textContent = from; $("msg-from").hidden = !from;
  }
}
function setLane(i) {
  if (G.state !== "driving") return;
  G.lane = clamp(i, 0, 2);
  document.querySelectorAll("#lanes button").forEach((b) => b.setAttribute("aria-pressed", String(+b.dataset.lane === G.lane)));
}

// the strip under the HUD: you, and who you are racing. In the Daily Road that is today's drives of you and your friends, live; in the free drive, each friend's best.
const raceMarks = [];
function raceList() {
  if (G.mode === "daily" || G.mode === "duel") return ghosts.map((gh) => ({ avatar: gh.rp.avatar, nickname: gh.rp.you ? t("You (best today)") : gh.rp.nickname, at: gh.score }));
  return G.ghosts.map((gh) => ({ avatar: gh.avatar, nickname: gh.nickname, at: gh.best }));
}
function buildRace() {
  const track = $("track"); track.querySelectorAll(".mk:not(.you)").forEach((n) => n.remove()); raceMarks.length = 0;
  for (let i = 0; i < raceList().length; i++) { const mk = document.createElement("i"); mk.className = "mk"; track.append(mk); raceMarks.push(mk); }
  G.raceText = "";
}
function race() {
  const S = G.S, list = raceList();
  $("you-marker").style.left = "10%";
  let ahead = null;
  list.forEach((gh, i) => {
    const mk = raceMarks[i]; if (!mk) return;
    const pos = 10 + ((gh.at - S) / 900) * 85;
    mk.textContent = gh.avatar; mk.style.left = clamp(pos, 4, 95) + "%"; mk.classList.toggle("far", pos > 95 || pos < 4);
    if (gh.at > S && (!ahead || gh.at < ahead.at)) ahead = gh;
  });
  const text = !list.length ? (G.mode === "daily" ? t("Nobody has driven today's road yet. Be the first!") : t("Add friends to race their best.")) :
    ahead ? t("{name} is {n} m ahead", { name: ahead.nickname, n: Math.round((ahead.at - S) / 10) * 10 }) : t("You are ahead of your friends!");
  if (text !== G.raceText) { G.raceText = text; $("race-text").textContent = text; }    // (only when it changes, to the nearest 10 m)
}

// ------------------------------------------------------------------------------------------------ the garage, themes and settings on the first screen
const drawer = { catalog: null };
function chip(label, pressed, onclick, extra = {}) {
  const b = Object.assign(document.createElement("button"), { type: "button", className: "opt-chip", textContent: label, ...extra });
  b.setAttribute("aria-pressed", String(!!pressed)); b.addEventListener("click", onclick); return b;
}
async function loadGarage() {
  try {
    const r = await fetch("/api/road/garage"); if (!r.ok) return;
    drawer.catalog = await r.json(); paintGarage();
  } catch (_) { /* the garage is a bonus: the game works without it */ }
}
function paintGarage() {
  const c = drawer.catalog; if (!c) return;
  G.cars = Object.fromEntries(c.cars.map((x) => [x.id, x.color]));
  const label = (x) => (x.unlocked ? x.name : `${x.name}: ${t("Locked: {need}", { need: x.need })}`);
  $("garage-cars").replaceChildren(...c.cars.map((x) => {
    const b = chip("", c.selected.car === x.id, () => pick(x.id, c.selected.hat), { title: label(x) });
    b.classList.add("swatch"); b.style.setProperty("--c", x.color === "rainbow" ? "conic-gradient(#e5546b,#e9a23b,#f5d742,#33b27c,#3fa7e8,#7a5cd0,#e5546b)" : x.color);
    b.disabled = !x.unlocked; b.setAttribute("aria-label", label(x)); b.append(Object.assign(document.createElement("span"), { textContent: x.unlocked ? "" : "🔒" }));
    return b;
  }));
  const hatIcon = { none: "🚫", cap: "🧢", shades: "🕶️", party: "🥳", scarf: "🧣", crown: "👑" };
  $("garage-hats").replaceChildren(...c.hats.map((x) => {
    const b = chip(x.unlocked ? hatIcon[x.id] : "🔒", c.selected.hat === x.id, () => pick(c.selected.car, x.id), { title: label(x) });
    b.disabled = !x.unlocked; b.setAttribute("aria-label", label(x));
    return b;
  }));
  const next = [...c.cars, ...c.hats].find((x) => !x.unlocked);
  $("garage-note").textContent = next ? t("Next to unlock: {name}. {need}", { name: next.name, need: next.need }) : t("You have everything. Nice driving!");
  applySkin(c.selected.car, c.selected.hat);
}
async function pick(car, hat) {
  try {
    const r = await fetch("/api/road/garage", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ car, hat }) });
    if (r.ok) { drawer.catalog = await r.json(); paintGarage(); }
  } catch (_) { /* keep what was chosen before */ }
}
function applySkin(carId, hat) {
  G.skin = { car: carId, hat, color: G.cars[carId] || "#7A5CD0" };
  if (G.skin.color !== "rainbow") carMats.body.color.set(G.skin.color);
  drawFinn(hat);
}
function paintThemes() {
  $("themes").replaceChildren(...[["auto", t("Auto")], ["day", t("Day")], ["night", t("Night")], ["rain", t("Rain")], ["festive", t("Festive")]].map(([id, label]) =>
    chip(label, G.theme === id, () => { G.theme = id; pref.set("theme", id); applyTheme(id); paintThemes(); })));
}
function paintSound() {
  $("sound").setAttribute("aria-pressed", String(Snd.on)); $("sound").textContent = Snd.on ? "🔊" : "🔇";
  $("sound").setAttribute("aria-label", Snd.on ? t("Sound is on") : t("Sound is off"));
  $("opt-sound").checked = Snd.on; $("opt-music").checked = Snd.music; $("opt-vibe").checked = Snd.vibe;
  $("opt-vibe").closest("label").hidden = !navigator.vibrate;
}

// ------------------------------------------------------------------------------------------------ talking to the server
async function api(path, body) {
  const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });
  if (!r.ok) { const e = new Error("http " + r.status); e.status = r.status; throw e; }
  return r.json();
}
function lost() { G.state = "lost"; $("lost").hidden = false; }

async function begin(mode = G.mode) {
  $("go").disabled = $("go-daily").disabled = true;
  Snd.start();
  try {
    const r = await api("/api/road/start", { mode });
    G.mode = r.mode; G.run = r.run; G.gates = r.items.slice(); G.cur = 0; G.answered = 0; G.T = 0; G.S = 0; G.Sshown = 0; G.Tlast = 0; G.clock = 0; G.lives = r.lives; G.combo = 0; G.lane = 1; G.over = false; G.pending = [];
    G.speedCfg = r.speed; G.gateScore = r.gate; G.ghosts = r.ghosts; G.replays = r.replays; G.best = r.best; G.account = r.account; G.ramp = 0; G.passedFlags = new Set(); G.shake = 0;
    gantries.forEach((g) => { g.visible = false; g.userData.k = -1; }); buildFlags(); buildGhosts(); buildRace(); car.rotation.set(0, 0, 0); G.laneX = 0;
    applySkin(r.skin.car, r.skin.hat); G.skin.color = r.skin.color; if (r.skin.color !== "rainbow") carMats.body.color.set(r.skin.color);
    ["intro", "end", "why", "pause-sheet", "lost"].forEach((id) => { $(id).hidden = true; });
    ["hud", "race", "lanes"].forEach((id) => { $(id).hidden = false; });
    $("toast").hidden = true; setLane(1); showMessage(); paintHud(); race(); G.state = "driving";
    if (SEASON && G.themeKey === SEASON.id) toast(SEASON.emoji + " " + SEASON.greeting, "good", 3600);
  } catch (e) {
    $("intro").hidden = true; lost();
  } finally { $("go").disabled = $("go-daily").disabled = false; }
}

async function submit(k, lane) {
  const gate = G.gates[k];
  const entry = { k, lane, res: null };
  G.pending.push(entry);
  try { entry.res = await api("/api/road/answer", { run: G.run, gate: gate.id, lane }); }
  catch (e) { lost(); return; }
  settle();
}
function settle() {
  while (G.pending.length && G.pending[0].res) {      // answers are shown in the order they were given
    const { res, lane } = G.pending.shift();
    applyResult(res, lane);
  }
}
function applyResult(res, lane) {
  if (res.next && res.next.length) G.gates.push(...res.next);
  G.answered += 1; G.lives = res.lives; G.combo = res.combo;
  const ok = res.outcome === "correct";
  if (ok) G.S = res.distance;
  G.Tlast = G.T;
  gantryEffect(lane, res);
  const x = LANE_X[lane];
  if (ok) {
    emit(x, 2, -4, 36, "#FFE08A", 4, 7); emit(x, 2, -4, 24, "#8CF0B8", 3, 6); Snd.right();
    toast("✅ " + (res.tell ? t("Right! {tell}", { tell: res.tell }) : t("Right!")), "good", 4200);
  } else if (res.outcome === "partial") {
    Snd.careful();
    toast("🤔 " + t("Careful, but that goes nowhere. This one was {what}.", { what: res.truth === "scam" ? t("a scam") : t("fine") }), "warn", 4200);
  } else {
    crash(res, lane);
  }
  paintHud(); race();
  if (res.over && res.outcome !== "wrong") { G.over = true; finishDrive(); }     // (the last gate of a race)
}
function gantryEffect(lane, res) {
  const g = gantries.find((x) => x.userData.k === G.answered - 1);
  if (!g) return;
  g.userData.flash = { lane, right: res.lane, t: 0 };
}
function crash(res, lane) {
  G.state = "crash"; G.crashT = 0; G.shake = reduceMotion ? 0.15 : 1; G.over = res.over; G.crashRes = res; Snd.wrong();
  emit(LANE_X[lane], 1.2, -3, 50, "#6B6485", 3, 6); emit(LANE_X[lane], 1.2, -3, 30, "#FF8A9B", 4, 8);
}
function showWhy(res) {
  const what = res.truth === "scam" ? t("That one was a scam.") : res.truth === "safe" ? t("That one was fine.") : t("That one was hard to tell. Checking first was right.");
  $("why-title").textContent = "💥 " + what;
  for (const [id, text] of [["why-tell", res.tell], ["why-action", res.action]]) { $(id).textContent = text || ""; $(id).parentElement.hidden = !text; }   // (a genuine message has nothing to "do")
  $("why-tricks").replaceChildren(...(res.tricks || []).map((n) => Object.assign(document.createElement("span"), { className: "chip", textContent: n })));
  $("why-go").textContent = res.over ? t("See my result") : t("Keep driving");
  $("why").hidden = false; G.state = "why"; $("why-go").focus();
  clearTimeout(G.whyTimer);
  if (G.mode === "duel") G.whyTimer = setTimeout(() => { if (!$("why").hidden) $("why-go").click(); }, 6000);
}

async function finishDrive() {
  if (G.mode === "duel") return finishRaceDrive();
  G.state = "over"; Snd.drive(0, false);
  ["hud", "race", "lanes", "msg", "toast"].forEach((id) => { $(id).hidden = true; });
  try {
    const s = await api("/api/road/finish", { run: G.run });
    $("end-title").textContent = s.mode === "daily" ? t("Daily Road done") : t("Drive over");
    $("end-dist").textContent = t("{n} m", { n: s.distance });
    $("end-best").hidden = !s.new_best;
    $("end-stats").replaceChildren(...[
      t("{n} right", { n: s.correct }), t("Best combo x{n}", { n: s.best_combo }), t("+{n} XP", { n: s.xp_gained }),
    ].map((x) => Object.assign(document.createElement("li"), { textContent: x })));
    const passed = $("end-passed");
    passed.hidden = !s.passed.length;
    if (s.passed.length) passed.textContent = "🏁 " + t("You passed {names}!", { names: s.passed.map((p) => `${p.avatar} ${p.nickname}`).join(", ") });
    $("end-badges").replaceChildren(...s.badges_new.map((b) => Object.assign(document.createElement("span"), { className: "chip", textContent: "🏅 " + b.title })),
      ...s.unlocked.map((u) => Object.assign(document.createElement("span"), { className: "chip unlock", textContent: (u.kind === "car" ? "🚗 " : "🎩 ") + t("Unlocked: {name}", { name: u.name }) })));
    const board = $("end-board"); board.hidden = !s.board.length;
    board.replaceChildren(...s.board.map((r) => {
      const li = document.createElement("li"); if (r.you) li.className = "you"; if (!r.runs) li.className += " idle";
      const rank = document.createElement("span"); rank.className = "rank"; rank.textContent = r.rank === 1 ? "🥇" : r.rank === 2 ? "🥈" : r.rank === 3 ? "🥉" : r.rank ? String(r.rank) : "–";
      const who = document.createElement("span"); who.className = "who"; who.textContent = `${r.avatar} ${r.nickname}`;
      const far = document.createElement("span"); far.className = "far"; far.textContent = r.runs ? t("{n} m", { n: r.best }) : "–";
      li.append(rank, who, far); return li;
    }));
    $("end-login").hidden = s.account;
    if (s.new_best || s.passed.length) Snd.passed(); else Snd.over();
    if (s.unlocked.length) setTimeout(() => Snd.unlock(), 700);
    loadGarage();
    $("end").hidden = false; $("again").focus();
  } catch (e) { lost(); }
}

// ------------------------------------------------------------------------------------------------ a live race: lobby, countdown, rivals as live ghosts, results
const DUEL = $("road").dataset.duel || "";
const Dl = { view: null, offset: 0, timer: 0, setup: false, busy: false, shown: false };
const serverNow = () => Date.now() / 1000 + Dl.offset;
async function duelCall(path, method = "GET") {
  const r = await fetch(path, { method, headers: { "Content-Type": "application/json" } });
  if (!r.ok) { let detail = ""; try { detail = (await r.json()).detail || ""; } catch (_) { /* no detail */ } const e = new Error(detail); e.status = r.status; throw e; }
  return r.json();
}
const SHEETS = ["lobby", "count", "duel-wait", "duel-end", "duel-gone", "why", "pause-sheet", "intro", "end", "lost"];
function sheetsOff() { SHEETS.forEach((id) => { const n = $(id); if (n) n.hidden = true; }); }
function gone(title, note) {
  clearInterval(Dl.timer); sheetsOff(); ["hud", "race", "lanes", "msg", "toast"].forEach((id) => { $(id).hidden = true; });
  $("duel-gone-title").textContent = title; $("duel-gone-note").textContent = note || ""; $("duel-gone").hidden = false; G.state = "over";
}
function li(cls, ...kids) { const n = document.createElement("li"); n.className = cls || ""; n.append(...kids); return n; }
function span(cls, text) { const n = document.createElement("span"); n.className = cls; n.textContent = text; return n; }
const medal = (r) => (r === 1 ? "🥇" : r === 2 ? "🥈" : r === 3 ? "🥉" : String(r));
function recordText(p) { return p.record && (p.record[0] || p.record[1]) ? t("you {w}–{l}", { w: p.record[0], l: p.record[1] }) : ""; }

function paintLobby(v) {
  sheetsOff(); $("lobby").hidden = false; G.state = "intro";
  $("lobby-players").replaceChildren(...v.players.map((p) => li("", span("who", `${p.avatar} ${p.nickname}${p.host ? " 👑" : ""}${p.you ? " " + t("(you)") : ""}`), span("muted", recordText(p)))));
  $("lobby-start").hidden = !v.can_start;
  $("lobby-note").textContent = v.you_host ? (v.can_start ? t("Ready when you are.") : t("Waiting for friends to join…")) : t("Waiting for the host to start…");
}
function rivalsFrom(v) {
  return v.players.filter((p) => !p.you).map((p) => ({ pub: p.pub, nickname: p.nickname, avatar: p.avatar, car: p.car, hat: p.hat, you: false, path: (p.progress || {}).path || "", times: (p.progress || {}).times || [], finished: !!(p.progress || {}).finished }));
}
function setupRace(v) {
  const r = v.you_run; Dl.setup = true;
  G.mode = "duel"; G.run = r.run; G.gates = r.items.slice(); G.limit = r.limit; G.cur = 0; G.answered = 0; G.T = 0; G.S = 0; G.Sshown = 0; G.Tlast = 0; G.clock = 0; G.lives = r.lives; G.combo = 0; G.lane = 1; G.over = false; G.pending = [];
  G.speedCfg = r.speed; G.gateScore = r.gate; G.ghosts = []; G.replays = rivalsFrom(v); G.best = 0; G.account = true; G.ramp = 0; G.passedFlags = new Set(); G.shake = 0;
  gantries.forEach((g) => { g.visible = false; g.userData.k = -1; }); buildFlags(); buildGhosts(); buildRace(); car.rotation.set(0, 0, 0); G.laneX = 0;
  applySkin(r.skin.car, r.skin.hat); G.skin.color = r.skin.color; if (r.skin.color !== "rainbow") carMats.body.color.set(r.skin.color);
  sheetsOff(); ["hud", "race", "lanes"].forEach((id) => { $(id).hidden = false; }); $("msg").hidden = true; $("pause").hidden = true; setLane(1); paintHud(); race();
  $("count").hidden = false; G.state = "countdown";
}
function countdownTick() {
  const left = Dl.view.start_at - serverNow();
  $("count-num").textContent = left > 0 ? String(Math.ceil(left)) : t("Go!");
  if (left <= 0) {
    G.state = "driving"; G.ramp = 0; G.clock = 0; showMessage(); toast("🏁 " + t("Go!"), "good", 1500); Snd.passed();
    setTimeout(() => { $("count").hidden = true; }, 600);
  } else if (Math.ceil(left) !== G.lastTick) { G.lastTick = Math.ceil(left); Snd.careful(); }
}
function updateRivals(v) {
  rivalsFrom(v).forEach((rp, i) => { const gh = ghosts[i]; if (!gh) return; Object.assign(gh.rp, rp); gh.tl = ghostTimeline(gh.rp); });
}
function paintLive(v) {
  $("duel-live").replaceChildren(...v.players.map((p) => { const pr = p.progress || {}; return li(p.you ? "you" : "", span("rank", pr.finished ? "🏁" : "🚗"), span("who", `${p.avatar} ${p.nickname}`), span("far", t("{n} right", { n: pr.correct || 0 }))); }));
}
function showRaceResult(v) {
  if (Dl.shown) return; Dl.shown = true; clearInterval(Dl.timer); sheetsOff();
  const res = v.result, me = res.you;
  $("duel-won").hidden = !me.won; $("duel-title").textContent = me.won ? t("You won the race!") : t("Race over");
  $("duel-board").replaceChildren(...res.ranking.map((r) => li(r.pub === Dl.me.pub ? "you" : "", span("rank", medal(r.rank)), span("who", `${r.avatar} ${r.nickname}`), span("far", r.forfeit ? t("left the race") : t("{n} right", { n: r.correct })))));
  $("duel-chips").replaceChildren(...[`+${me.xp} XP`].concat(me.badges.map((b) => "🏅 " + b.title)).map((x) => Object.assign(document.createElement("span"), { className: "chip", textContent: x })));
  $("duel-record").textContent = v.players.filter((p) => !p.you && p.record).map((p) => t("You and {name}: {w}–{l}", { name: p.nickname, w: p.record[0], l: p.record[1] })).join(" · ");
  $("duel-end").hidden = false; $("duel-rematch").focus();
  if (me.won) { Snd.passed(); emit(0, 3, -2, 50, "#FFE08A", 5, 8); } else Snd.over();
}
async function finishRaceDrive() {
  G.state = "over"; Snd.drive(0, false);
  ["hud", "race", "lanes", "msg", "toast"].forEach((id) => { $(id).hidden = true; }); $("pause").hidden = true;
  try { await api("/api/road/finish", { run: G.run }); } catch (_) { /* the race itself is settled by the server */ }
  if (!Dl.shown) { sheetsOff(); $("duel-wait").hidden = false; if (Dl.view) paintLive(Dl.view); }
}
function applyDuel(v) {
  Dl.view = v; Dl.offset = v.now - Date.now() / 1000; Dl.me = v.players.find((p) => p.you);
  if (v.state === "closed") return gone(t("This race isn't open any more"), t("The host closed it."));
  if (v.state === "lobby") return paintLobby(v);
  if (!Dl.setup) {
    if (!v.you_run) return;                                  // (asked for again with the next poll)
    if (Dl.me.progress && Dl.me.progress.n > 0) { duelCall(`/api/duel/${DUEL}/leave`, "POST").catch(() => {}); return gone(t("You left this race"), t("A race can't be picked up again once the page is reloaded.")); }
    setupRace(v);
  }
  updateRivals(v);
  if (G.state === "over" && !Dl.shown) paintLive(v);
  if (v.state === "done" && G.state === "over") showRaceResult(v);
}
async function duelPoll() {
  if (Dl.busy || Dl.shown) return; Dl.busy = true;
  try { applyDuel(await duelCall(`/api/duel/${DUEL}${Dl.setup ? "" : "?run=1"}`)); }
  catch (e) { if (e.status === 404 || e.status === 403) gone(t("This race isn't open any more"), e.message); }
  finally { Dl.busy = false; }
}
async function duelBoot() {
  sheetsOff();
  try { applyDuel(await duelCall(`/api/duel/${DUEL}/join`, "POST")); Dl.timer = setInterval(duelPoll, 1000); }
  catch (e) { gone(t("You can't join this race"), e.message || t("Make a profile first to race.")); }
}
if (DUEL) {
  $("lobby-start").addEventListener("click", async () => { $("lobby-start").disabled = true; try { applyDuel(await duelCall(`/api/duel/${DUEL}/start`, "POST")); } catch (e) { $("lobby-note").textContent = e.message; } finally { $("lobby-start").disabled = false; } });
  $("lobby-leave").addEventListener("click", async () => { try { await duelCall(`/api/duel/${DUEL}/leave`, "POST"); } finally { location.href = "/duel"; } });
  $("duel-rematch").addEventListener("click", async () => { try { const r = await duelCall(`/api/duel/${DUEL}/rematch`, "POST"); location.href = "/duel/" + r.code; } catch (e) { $("duel-record").textContent = e.message; } });
  duelBoot();
}

// ------------------------------------------------------------------------------------------------ the loop
let last = 0, slow = 0, frames = 0, hudTick = 0, hue = 0;
function frame(ts) {
  requestAnimationFrame(frame);
  const dt = clamp((ts - last) / 1000 || 0.016, 0.001, 0.05); last = ts;
  update(dt);
  renderer.render(scene, camera);
  frames++; slow = slow * 0.95 + (dt > 0.034 ? 0.05 : 0);
  if (frames === 150 && slow > 0.6) { renderer.setPixelRatio(1); resize(); }   // a slow device draws fewer pixels
}
function update(dt) {
  let dz = 0;
  if (G.state === "driving") {
    G.ramp = Math.min(1, G.ramp + dt * 0.9);
    dz = speedNow() * G.ramp * dt; G.T += dz; G.clock += dt;
  } else if (G.state === "intro" || G.state === "countdown") dz = 6 * dt;
  else if (G.state === "crash") dz = Math.max(0, 1 - G.crashT / 0.7) * speedNow() * 0.5 * dt;
  scrollWorld(dz);
  Snd.drive(speedNow() * G.ramp, G.state === "driving");

  // the next sign: shown while we are close, answered the moment the car passes it
  if (G.state === "driving") {
    const k = G.cur, gT = FIRST_GATE + k * GATE_VIS;
    if (G.gates[k] && G.T >= gT) { G.cur += 1; submit(k, G.lane); showMessage(); }
  }
  if (G.mode === "duel" && Dl.view && (G.state === "driving" || G.state === "crash" || G.state === "why" || G.state === "over")) G.clock = Math.max(0, serverNow() - Dl.view.start_at);   // one clock for everyone in the race
  if (G.state === "countdown") countdownTick();
  placeGantries();
  placeFlags();
  if (G.mode === "daily" || G.mode === "duel") stepGhosts(dt); else for (const gh of ghosts) gh.obj.visible = false;

  // the car
  G.laneX += (LANE_X[G.lane] - G.laneX) * Math.min(1, dt * 9);
  const vx = (LANE_X[G.lane] - G.laneX);
  let spin = 0, bob = Math.sin(performance.now() / 160) * 0.03 * (dz > 0 ? 1 : 0);
  if (G.state === "crash") {
    G.crashT += dt; const p = clamp(G.crashT / 0.9, 0, 1);
    spin = reduceMotion ? 0 : ease(p) * Math.PI * 2; bob = Math.sin(p * Math.PI) * 0.5;
    if (G.crashT > 1.0) { showWhy(G.crashRes); }
  }
  car.position.set(G.laneX, bob, 0);
  car.rotation.y = spin; car.rotation.z = -vx * 0.09 + (G.state === "crash" ? Math.sin(G.crashT * 22) * 0.06 : 0);
  for (const w of wheels) w.rotation.x -= dz * 2.2;
  finn.position.y = 2.6 + Math.sin(performance.now() / 260) * 0.05;
  if (G.skin.color === "rainbow") { hue = (hue + dt * 0.35) % 1; carMats.body.color.setHSL(hue, 0.7, 0.62); }

  // the camera follows from behind and a little above
  G.shake = Math.max(0, G.shake - dt * 1.6);
  const sh = G.shake * 0.35;
  const tall = camera.aspect < 0.8;     // a phone held upright: further back and level, so the signs sit lower on the screen, under the message
  camera.position.set(G.laneX * 0.45 + rand(-sh, sh), (tall ? 5.5 : 5.0) + rand(-sh, sh) * 0.6, tall ? 11.6 : 9.8);
  camera.lookAt(G.laneX * 0.25, tall ? 2.3 : 1.0, -14);

  stepParticles(dt, dz);
  if (rain.visible) stepRain(dt, dz);
  if (snow.visible) stepSnow(dt, dz);
  if (floaters.visible) stepFloaters(dz);
  if (fw.visible) { fwTimer -= dt; if (fwTimer <= 0 && G.fireworkColors) { burst(G.fireworkColors); fwTimer = rand(0.8, 2.0); } stepFireworks(dt, dz); }
  if (G.confetti && Math.random() < dt * 14) emit(rand(-12, 12), rand(10, 18), -rand(5, 60), 1, ["#FFD36E", "#FF6B8B", "#8CF0B8", "#FFFFFF"][(Math.random() * 4) | 0], 0.4, -1);
  for (const c of clouds) { c.position.x += c.userData.v * dt; if (c.position.x > 170) c.position.x = -170; }

  // the odometer counts up to the server's distance; the race strip refreshes a few times a second
  G.Sshown += (G.S - G.Sshown) * Math.min(1, dt * 5);
  if (Math.abs(G.S - G.Sshown) < 0.5) G.Sshown = G.S;
  hudTick += dt;
  if (hudTick > 0.2 && G.state === "driving") {
    hudTick = 0; paintHud();
    if (G.mode === "daily" || G.mode === "duel") race();
    const g = G.gates[G.cur]; if (g) $("msg-gate").textContent = t("{n} m to the sign", { n: Math.max(0, Math.round(FIRST_GATE + G.cur * GATE_VIS - G.T)) });
  }
}
function scrollWorld(dz) {
  if (!dz) return;
  roadTex.offset.y += dz / TILE_M; grassTex.offset.y += dz / 16;
  for (const p of props) { p.position.z += dz; if (p.position.z > 14) placeProp(p, false); }
}
function placeGantries() {
  // give each sign that is within sight a gantry; free the ones we have passed
  for (const g of gantries) if (g.userData.k >= 0 && FIRST_GATE + g.userData.k * GATE_VIS - G.T < -8) { g.visible = false; g.userData.k = -1; }
  const want = [];
  for (let k = Math.max(0, G.cur - 1); k < G.gates.length && FIRST_GATE + k * GATE_VIS - G.T < SEE; k++) want.push(k);
  for (const k of want) {
    let g = gantries.find((x) => x.userData.k === k);
    if (!g) {
      g = gantries.find((x) => x.userData.k === -1 || x.userData.k === undefined); if (!g) continue;
      g.userData.k = k; g.userData.flash = null; g.visible = true;
      g.userData.signs.forEach((s) => s.scale.setScalar(1)); g.userData.glows.forEach((gl) => { gl.material.opacity = 0.2; });
    }
    g.position.z = -(FIRST_GATE + k * GATE_VIS - G.T);
    g.visible = g.position.z < 6;     // (once it is behind the car it would only swamp the camera)
    const f = g.userData.flash;
    if (f) {
      f.t += 0.016;
      g.userData.signs.forEach((s, i) => { s.scale.setScalar(i === f.right ? 1 + 0.25 * Math.sin(Math.min(1, f.t * 2) * Math.PI) : 1); });
      g.userData.glows.forEach((gl, i) => { gl.material.opacity = i === f.right ? 0.55 : i === f.lane ? 0.4 : 0.1; });
    } else {
      const pulse = 0.18 + 0.06 * Math.sin(performance.now() / 300);
      g.userData.glows.forEach((gl) => { gl.material.opacity = pulse; });
    }
  }
}
function placeFlags() {
  const k = GATE_VIS / G.gateScore;
  const sNow = G.S + (G.T - G.Tlast) / k;     // where the score would be if this stretch is driven right (so the flags glide smoothly)
  for (const f of flags) {
    const z = -(f.gh.best - sNow) * k;
    f.obj.visible = G.mode === "road" && z > -SEE && z < 16 && G.state !== "intro";
    f.obj.position.z = z;
    if (z > 4 && !G.passedFlags.has(f.gh.nickname + f.gh.best) && G.state === "driving" && G.mode === "road") {
      G.passedFlags.add(f.gh.nickname + f.gh.best);
      toast("🏁 " + t("You passed {name}'s best!", { name: f.gh.nickname }), "good", 3200);
      emit(0, 3, -2, 40, "#FFE08A", 5, 8); Snd.passed();
    }
  }
}

// ------------------------------------------------------------------------------------------------ controls
function pause() { if (G.state !== "driving" || G.mode === "duel") return; G.state = "paused"; Snd.drive(0, false); $("pause-sheet").hidden = false; $("resume").focus(); }
function resume() { if (G.state !== "paused") return; $("pause-sheet").hidden = true; G.state = "driving"; G.ramp = 0; Snd.resume(); }
addEventListener("keydown", (e) => {
  if (G.state === "driving") {
    const key = e.key;
    if (key === "ArrowLeft" || key === "a" || key === "A") { setLane(G.lane - 1); e.preventDefault(); }
    else if (key === "ArrowRight" || key === "d" || key === "D") { setLane(G.lane + 1); e.preventDefault(); }
    else if (key === "1" || key === "2" || key === "3") { setLane(+key - 1); e.preventDefault(); }
    else if (key === "Escape" || key === "p" || key === "P" || key === " ") { pause(); e.preventDefault(); }
    else if (key === "m" || key === "M") { Snd.setOn(!Snd.on); paintSound(); }
  } else if (G.state === "paused" && (e.key === "Escape" || e.key === "p")) resume();
});
document.querySelectorAll("#lanes button").forEach((b) => b.addEventListener("click", () => setLane(+b.dataset.lane)));
let sx = null;      // a swipe on the road moves one lane
$("scene").addEventListener("pointerdown", (e) => { sx = e.clientX; });
$("scene").addEventListener("pointerup", (e) => { if (sx !== null && Math.abs(e.clientX - sx) > 36) setLane(G.lane + (e.clientX > sx ? 1 : -1)); sx = null; });
document.addEventListener("visibilitychange", () => { if (document.hidden) { pause(); if (G.mode !== "duel") Snd.suspend(); } else Snd.resume(); });
$("go").addEventListener("click", () => begin("road"));
$("go-daily").addEventListener("click", () => begin("daily"));
$("again").addEventListener("click", () => { $("end").hidden = true; begin(G.mode); });
$("pause").addEventListener("click", pause);
$("resume").addEventListener("click", resume);
$("quit").addEventListener("click", () => { $("pause-sheet").hidden = true; finishDrive(); });
$("why-go").addEventListener("click", () => { clearTimeout(G.whyTimer); $("why").hidden = true; if (G.over) finishDrive(); else { G.state = "driving"; G.ramp = 0; } });
$("retry").addEventListener("click", () => { $("lost").hidden = true; $("intro").hidden = false; G.state = "intro"; });
$("easy").addEventListener("change", (e) => { G.easy = e.target.checked; pref.set("easy", G.easy ? "1" : "0"); });
$("sound").addEventListener("click", () => { Snd.setOn(!Snd.on); paintSound(); });
$("opt-sound").addEventListener("change", (e) => { Snd.setOn(e.target.checked); paintSound(); });
$("opt-music").addEventListener("change", (e) => { Snd.setMusic(e.target.checked); paintSound(); });
$("opt-vibe").addEventListener("change", (e) => { Snd.setVibe(e.target.checked); });

applyTheme(G.theme); paintThemes(); paintSound(); loadGarage();
if (/[?&]daily=1\b/.test(location.search)) $("go-daily").classList.add("hot");

// a hook for the browser tests: the score is the server's, so moving the car along faster than real time cannot change it
window.__road = { get state() { return G.state; }, get lives() { return G.lives; }, get distance() { return G.S; }, get answered() { return G.answered; }, get lane() { return G.lane; }, get gateAhead() { return FIRST_GATE + G.cur * GATE_VIS - G.T; },
  advance(m) { G.T += m; G.clock += m / Math.max(8, speedNow()); }, get text() { return (G.gates[G.cur] || {}).text || ""; }, get mode() { return G.mode; }, get theme() { return G.themeKey; }, get season() { return SEASON && SEASON.id; }, get duel() { return Dl.view; },
  get skin() { return G.skin; }, drawHat(h) { drawFinn(h); }, get ghosts() { return ghosts.length; }, get sound() { return Snd.on; }, get audio() { return Snd.ctx ? Snd.ctx.state : "none"; } };

requestAnimationFrame(frame);
