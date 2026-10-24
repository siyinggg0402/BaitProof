// Characters on the page: the tables the server embeds (core/domain/characters.py: skin tones, hair, outfits, colours), a look code turned into its parts, the flat
// portrait beside a name, and a portrait drawn on a canvas (for the labels in Scam Road). The portrait layers come from the page's sprite (web/portrait.py).
const LOOK = (() => { try { return JSON.parse(document.getElementById("look-tables").textContent); } catch (_) { return null; } })();
const LOOK_RE = /^p(?:\.\d{1,2}){6,7}$/;   // six numbers (before the faces: rosy cheeks) or seven
const NATURAL_HAIR = 6;                    // the first six hair colours are natural: a beard or brows never take the others
const PORTRAIT_VIEW = [4, 5, 56];   // the part of the 64 x 64 drawing that is shown: x, y, size

function parseLook(code) {
  if (!LOOK || typeof code !== "string" || !LOOK_RE.test(code)) return null;
  const n = code.split(".").slice(1).map(Number);
  while (n.length < 7) n.push(0);
  const sizes = [LOOK.skins.length, LOOK.hair.length, LOOK.hair_colors.length, LOOK.outfits.length, LOOK.outfit_colors.length, LOOK.accessories.length, (LOOK.faces || ["soft"]).length];
  if (n.some((v, i) => v >= sizes[i])) return null;
  const natural = n[2] < NATURAL_HAIR ? LOOK.hair_colors[n[2]] : LOOK.hair_colors[1];
  return { skin: LOOK.skins[n[0]], hair: LOOK.hair[n[1]], hairColor: LOOK.hair_colors[n[2]], outfit: LOOK.outfits[n[3]], outfitColor: LOOK.outfit_colors[n[4]], accessory: LOOK.accessories[n[5]], face: (LOOK.faces || ["soft"])[n[6]], natural, nums: n };
}
const lookCode = (nums) => "p." + nums.join(".");

// The layers that draw a look, bottom first: [symbol id, fill or null (the layer brings its own colours)]. Mirrors layers_for in web/portrait.py.
function lookLayers(look) {
  const has = (id) => !!document.getElementById(id);
  const out = [];
  if (has("pt-hairb-" + look.hair)) out.push(["pt-hairb-" + look.hair, look.hairColor]);
  out.push(["pt-body", look.outfitColor], ["pt-det-" + look.outfit, null], ["pt-neck", look.skin], ["pt-head", look.skin], ["pt-face", null]);
  if (look.face === "soft") out.push(["pt-blush", null]);
  else { out.push(["pt-brows", look.natural]); if (look.face !== "plain") out.push(["pt-fh-" + look.face, look.natural]); }
  if (has("pt-hairf-" + look.hair)) out.push(["pt-hairf-" + look.hair, look.hairColor]);
  if (look.accessory !== "none" && !(look.hair === "tudung" && (look.accessory === "songkok" || look.accessory === "cap"))) out.push(["pt-acc-" + look.accessory, null]);
  return out;
}
function portraitSvg(code) {
  const look = parseLook(code), svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "pt"); svg.setAttribute("viewBox", PORTRAIT_VIEW.concat(PORTRAIT_VIEW[2]).join(" ")); svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
  for (const [id, fill] of look ? lookLayers(look) : []) {
    const use = document.createElementNS(SVG_NS, "use");
    use.setAttribute("href", "#" + id);
    if (fill) use.setAttribute("fill", fill);
    svg.append(use);
  }
  return svg;
}
// A character's portrait in a soft circle (the same thing the server draws with the avatar helper).
function portraitEl(code, cls) {
  const w = document.createElement("span");
  w.className = "avt" + (cls ? " " + cls : "");
  w.dataset.av = code;
  w.append(portraitSvg(code));
  return w;
}
// The portrait on a canvas, in a circle centred on (cx, cy), `size` pixels across.
function drawPortrait(g, code, cx, cy, size, bg = "#ECE6FB") {
  const look = parseLook(code);
  if (!look) return;
  g.save();
  g.beginPath(); g.arc(cx, cy, size / 2, 0, Math.PI * 2); g.clip();
  g.fillStyle = bg; g.fillRect(cx - size / 2, cy - size / 2, size, size);
  g.translate(cx - size / 2, cy - size / 2); g.scale(size / PORTRAIT_VIEW[2], size / PORTRAIT_VIEW[2]); g.translate(-PORTRAIT_VIEW[0], -PORTRAIT_VIEW[1]);
  g.lineCap = "round"; g.lineJoin = "round";
  for (const [id, fill] of lookLayers(look)) {
    const grp = document.getElementById(id);
    if (!grp) continue;
    for (const p of grp.querySelectorAll("path")) {
      const path = new Path2D(p.getAttribute("d")), f = p.getAttribute("fill") || fill, s = p.getAttribute("stroke");
      if (f && f !== "none") { g.globalAlpha = Number(p.getAttribute("fill-opacity") || 1); g.fillStyle = f; g.fill(path, p.getAttribute("fill-rule") === "evenodd" ? "evenodd" : "nonzero"); }
      if (s) { g.globalAlpha = Number(p.getAttribute("stroke-opacity") || 1); g.strokeStyle = s; g.lineWidth = Number(p.getAttribute("stroke-width") || 1); g.stroke(path); }
    }
  }
  g.restore();
}
