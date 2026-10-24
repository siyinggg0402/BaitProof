// A living background: a soft colour field that ripples where you move, tap or click, like touching water.
// WebGL draws it (one small fragment shader at reduced resolution); where WebGL is missing a 2D canvas draws plain rings instead.
// It never takes part in the page: no pointer events, hidden from screen readers, paused when the tab is hidden, off for "reduce motion",
// and it switches itself off if the device cannot keep up. The page looks and works the same without it (the CSS glow stays).
(() => {
  if (document.body && document.body.dataset.game) return; // a game page (the 3D road) draws its own scene: no second WebGL canvas, no flying fish over the play area
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  // a small, modest device (or one asked to save data) gets the plain page
  const nav = navigator, conn = nav.connection || {};
  if (conn.saveData || (nav.deviceMemory && nav.deviceMemory <= 2) || (nav.hardwareConcurrency && nav.hardwareConcurrency <= 2)) return;
  const MAX = 8, LIFE = 3.0, AWAKE = 20000, CALM = 0.5; // ripples alive at once, how long one lasts (seconds), how long the water stays lively after the last touch (ms), and how strong a ripple is (1 = the first version)

  const canvas = document.createElement("canvas");
  canvas.className = "fx";
  canvas.setAttribute("aria-hidden", "true");
  document.body.prepend(canvas);

  // ---- colours from the page's own tokens, so the water follows the theme
  const css = (name, fallback) => {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(v);
    if (!m) return fallback;
    const h = m[1].length === 3 ? m[1].replace(/./g, "$&$&") : m[1];
    return [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
  };
  const palette = () => {
    const base = css("--bg", [0.98, 0.98, 0.99]);
    return { base, c0: css("--brand", [0.15, 0.39, 0.92]), c1: css("--violet", [0.49, 0.23, 0.93]), c2: css("--cyan", [0.02, 0.71, 0.83]), dark: (base[0] * 0.3 + base[1] * 0.6 + base[2] * 0.1) < 0.3 };
  };
  let pal = palette();
  matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => { pal = palette(); });

  // ---- the ripples: x, y (in the shader's units), age in seconds (-1 = free), strength
  const R = new Float32Array(MAX * 4).fill(0);
  const born = new Float64Array(MAX).fill(-1);
  for (let i = 0; i < MAX; i++) R[i * 4 + 2] = -1;
  let first = true, woke = performance.now(), next = 0, W = 1, H = 1, scale = 0.5, running = false, raf = 0, last = 0, ema = 16, frames = 0, dead = false;
  const pt = { x: 0.5, y: 0.5, sx: 0.5, sy: 0.5, s: 0, seen: 0, on: false };

  function drop(clientX, clientY, amp) {
    const i = next; next = (next + 1) % MAX;
    R[i * 4] = (clientX / innerWidth) * (W / H);
    R[i * 4 + 1] = 1 - clientY / innerHeight;
    R[i * 4 + 3] = amp * CALM;
    born[i] = performance.now();
    R[i * 4 + 2] = 0;
    wake();
  }
  window.bpSplash = (x, y, amp = 1) => { if (!dead) drop(x, y, amp); };

  // ---- WebGL
  const VERT = "attribute vec2 a;void main(){gl_Position=vec4(a,0.,1.);}";
  const FRAG = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
uniform vec2 uRes; uniform float uTime; uniform float uAsp; uniform vec4 uR[${MAX}];
uniform vec3 uBase; uniform vec3 uC0; uniform vec3 uC1; uniform vec3 uC2; uniform float uDark; uniform vec3 uM;
void main(){
  vec2 p = gl_FragCoord.xy / uRes.y;
  float h = 0.0; vec2 g = vec2(0.0);
  for (int i = 0; i < ${MAX}; i++) {
    vec4 r = uR[i];
    if (r.z >= 0.0) {
      vec2 d = p - r.xy; float dist = length(d) + 1e-4;
      float w = dist - r.z * 0.40;                       // the wave front travels outward
      float env = exp(-w * w * 24.0);                    // a soft ring, not a sheet
      float ph = w * 34.0, o = cos(ph);
      float fade = r.w * exp(-r.z * 1.25) * smoothstep(0.0, 0.08, r.z) / (1.0 + dist * 1.8);
      h += env * o * fade;
      g += (d / dist) * ((-48.0 * w * env * o - 34.0 * env * sin(ph)) * fade);
    }
  }
  vec2 q = p + g * 0.0038;                               // the colours bend through the water
  float t = uTime * 0.045;
  vec3 col = uBase;
  float k = uDark > 0.5 ? 0.38 : 0.34;
  col = mix(col, uC0, smoothstep(0.70, 0.0, distance(q, vec2(uAsp * (0.16 + 0.10 * sin(t * 1.7)), 0.82 + 0.08 * cos(t * 1.3)))) * k);
  col = mix(col, uC1, smoothstep(0.62, 0.0, distance(q, vec2(uAsp * (0.56 + 0.12 * cos(t * 1.1)), 1.00 + 0.06 * sin(t * 1.9)))) * k * 0.8);
  col = mix(col, uC2, smoothstep(0.66, 0.0, distance(q, vec2(uAsp * (0.92 + 0.06 * sin(t * 1.5)), 0.74 + 0.10 * cos(t * 0.9)))) * k * 0.8);
  col = mix(col, uC1, smoothstep(0.60, 0.0, distance(q, vec2(uAsp * (0.30 + 0.20 * sin(t)), 0.10 + 0.10 * cos(t * 1.4)))) * k * 0.45);
  float a = clamp(abs(h) * 1.2, 0.0, 1.0);
  vec3 tint = mix(uC0, uC2, 0.5 + 0.5 * sin(h * 5.0 + uTime * 0.4));
  vec3 n = normalize(vec3(-g * 0.011, 1.0));
  float spec = pow(max(dot(reflect(-normalize(vec3(-0.45, 0.55, 0.75)), n), vec3(0.0, 0.0, 1.0)), 0.0), 16.0);
  if (uDark > 0.5) col += tint * a * 0.30 + spec * 0.08;
  else { col = mix(col, tint, a * 0.40); col -= h * 0.05; col += spec * 0.05; }
  float m = smoothstep(0.40, 0.0, distance(p, uM.xy)) * uM.z;   // a soft light that follows the pointer
  col = mix(col, uC1, m * (uDark > 0.5 ? 0.20 : 0.12));
  col += (fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) - 0.5) / 255.0;
  gl_FragColor = vec4(col, 1.0);
}`;
  let gl = null, prog = null, U = {}, ctx2d = null;
  try {
    gl = canvas.getContext("webgl", { antialias: false, alpha: false, depth: false, stencil: false, powerPreference: "low-power", preserveDrawingBuffer: false });
    if (gl) {
      const dbg = gl.getExtension("WEBGL_debug_renderer_info"), renderer = dbg ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL)) : "";
      if (/swiftshader|llvmpipe|softpipe|software|basic render|mesa offscreen/i.test(renderer)) { canvas.remove(); return; } // drawing in software would be slow: leave the page plain, and show no switch for something that cannot run
      const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error("shader"); return s; };
      prog = gl.createProgram();
      gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT)); gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG));
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) throw new Error("link");
      gl.useProgram(prog);
      const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW); // one big triangle
      const loc = gl.getAttribLocation(prog, "a"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
      for (const n of ["uRes", "uTime", "uAsp", "uR", "uBase", "uC0", "uC1", "uC2", "uDark", "uM"]) U[n] = gl.getUniformLocation(prog, n);
      canvas.addEventListener("webglcontextlost", (e) => { e.preventDefault(); stop(); });
    }
  } catch (e) { gl = null; }
  if (!gl) { try { ctx2d = canvas.getContext("2d", { alpha: false }); } catch (e) { ctx2d = null; } }
  if (!gl && !ctx2d) { canvas.remove(); return; }
  document.documentElement.classList.add("fx-on");

  function resize() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    W = Math.max(2, Math.floor(innerWidth * dpr * scale)); H = Math.max(2, Math.floor(innerHeight * dpr * scale));
    if (canvas.width !== W) canvas.width = W;
    if (canvas.height !== H) canvas.height = H;
    if (gl) gl.viewport(0, 0, W, H);
  }

  function frame(now) {
    raf = 0;
    if (dead || document.hidden) { running = false; return; }
    const dt = last ? now - last : 16; last = now;
    if (dt < 100) { // a pause between slow idle frames says nothing about speed
      ema = ema * 0.9 + dt * 0.1; frames += 1;
      if (frames % 24 === 0 && ema > 24) { // cannot keep up: shrink the picture, and give up if it still struggles
        if (scale > 0.22) { scale *= 0.65; resize(); ema = 16; } else { retire(); return; }
      }
    }
    let live = false;
    for (let i = 0; i < MAX; i++) {
      if (born[i] < 0) continue;
      const age = (now - born[i]) / 1000;
      if (age > LIFE) { born[i] = -1; R[i * 4 + 2] = -1; } else { R[i * 4 + 2] = age; live = true; }
    }
    // the pointer light eases toward the pointer, and dims when it has been still for a while
    const idle = now - pt.seen;
    pt.sx += (pt.x - pt.sx) * 0.1; pt.sy += (pt.y - pt.sy) * 0.1;
    const want = pt.on && idle < 2500 ? 1 : 0;
    pt.s += (want - pt.s) * 0.06;
    if (gl) draw(now / 1000); else draw2d(now);
    // the slow drift still moves, so keep going, but at half speed when nothing is rippling
    if (live || pt.s > 0.02) { raf = requestAnimationFrame(frame); }
    else if (now - woke < AWAKE) { running = true; raf = setTimeout(() => requestAnimationFrame(frame), 110); } // a slow drift while you are around
    else { running = false; raf = 0; } // nobody has touched the page for a while: hold the picture still until they do
  }
  function draw(t) {
    gl.uniform2f(U.uRes, W, H); gl.uniform1f(U.uTime, t % 3600); gl.uniform1f(U.uAsp, W / H);
    gl.uniform4fv(U.uR, R);
    gl.uniform3fv(U.uBase, pal.base); gl.uniform3fv(U.uC0, pal.c0); gl.uniform3fv(U.uC1, pal.c1); gl.uniform3fv(U.uC2, pal.c2);
    gl.uniform1f(U.uDark, pal.dark ? 1 : 0); gl.uniform3f(U.uM, pt.sx * (W / H), 1 - pt.sy, pt.s);
    const t0 = first ? performance.now() : 0;
    gl.drawArrays(gl.TRIANGLES, 0, 3);
    if (first) { // the very first frame includes compiling the shader: if that alone stalls the page, give up at once
      first = false; gl.finish();
      if (performance.now() - t0 > 160) retire();
    }
  }
  function draw2d(now) { // the plain version: a tinted background and expanding rings
    const c = ctx2d, rgb = (v, a) => `rgba(${v.map((x) => Math.round(x * 255)).join(",")},${a})`;
    c.fillStyle = rgb(pal.base, 1); c.fillRect(0, 0, W, H);
    const blob = (x, y, r, col, a) => { const g = c.createRadialGradient(x, y, 0, x, y, r); g.addColorStop(0, rgb(col, a)); g.addColorStop(1, rgb(col, 0)); c.fillStyle = g; c.fillRect(0, 0, W, H); };
    const k = pal.dark ? 0.4 : 0.28;
    blob(W * 0.15, H * 0.2, H * 0.7, pal.c0, k); blob(W * 0.6, H * 0.05, H * 0.6, pal.c1, k * 0.8); blob(W * 0.92, H * 0.28, H * 0.6, pal.c2, k * 0.8);
    for (let i = 0; i < MAX; i++) {
      if (born[i] < 0) continue;
      const age = (now - born[i]) / 1000, x = (R[i * 4] / (W / H)) * W, y = (1 - R[i * 4 + 1]) * H, a = R[i * 4 + 3] * Math.exp(-age * 1.1) * 0.5;
      for (let j = 0; j < 3; j++) { c.beginPath(); c.arc(x, y, Math.max(1, (age * 0.46 - j * 0.05) * H), 0, 6.2832); c.strokeStyle = rgb(j % 2 ? pal.c2 : pal.c0, Math.max(0, a - j * 0.1)); c.lineWidth = 2; c.stroke(); }
    }
  }
  function touched() { woke = performance.now(); }
  function wake() { if (!raf && !dead && !document.hidden) { raf = requestAnimationFrame(frame); running = true; } }
  function stop() { if (raf) { cancelAnimationFrame(raf); clearTimeout(raf); raf = 0; } running = false; }
  function retire() { dead = true; stop(); canvas.remove(); document.documentElement.classList.remove("fx-on"); }

  // ---- pointer: a ripple as it moves (more when it moves fast), a bigger one for a tap or click
  let lx = -999, ly = -999, lt = 0;
  addEventListener("pointermove", (e) => {
    const x = e.clientX, y = e.clientY, now = performance.now();
    touched(); pt.x = x / innerWidth; pt.y = y / innerHeight; pt.seen = now; pt.on = true;
    if (!pt.s) pt.sx = pt.x, pt.sy = pt.y;
    const d = Math.hypot(x - lx, y - ly), dt = now - lt;
    if (d > 150 && dt > 240) { drop(x, y, Math.min(0.6, 0.2 + (d / Math.max(dt, 1)) * 0.15)); lx = x; ly = y; lt = now; } else wake();   // (a ripple as you move, but not for every flick of the mouse)
  }, { passive: true });
  addEventListener("pointerdown", (e) => { touched(); drop(e.clientX, e.clientY, 0.9); lx = e.clientX; ly = e.clientY; lt = performance.now(); pt.seen = lt; }, { passive: true });
  document.addEventListener("pointerout", (e) => { if (!e.relatedTarget) pt.on = false; }, { passive: true }); // the pointer left the window
  addEventListener("resize", () => { resize(); wake(); }, { passive: true });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stop(); else { last = 0; touched(); wake(); } });
  addEventListener("scroll", () => { touched(); wake(); }, { passive: true });
  addEventListener("keydown", () => { touched(); wake(); }, { passive: true });

  // a drop now and then, so it feels alive even with no pointer (a phone, or a hand off the mouse)
  const ambient = () => {
    if (!dead && !document.hidden && performance.now() - pt.seen > 2600 && performance.now() - woke < AWAKE) drop(innerWidth * (0.1 + Math.random() * 0.8), innerHeight * (0.1 + Math.random() * 0.8), 0.3);
    setTimeout(ambient, 7000 + Math.random() * 5000);
  };
  setTimeout(ambient, 1200);

  resize();
  wake();
})();
