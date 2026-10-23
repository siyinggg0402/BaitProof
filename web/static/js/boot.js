document.documentElement.classList.add("js");
try { if (localStorage.getItem("bp-big") === "1") document.documentElement.classList.add("big"); } catch (_) {}

// Translation for the scripts: the server embeds {lang, speech, dict} as <script type="application/json" id="i18n"> on Chinese and Malay pages (not on English ones).
// The function t takes the English text (and an object of values) and gives the text in the page's language (English is the key and the fallback), filling in each {name}.
const I18N = (() => {
  try { return Object.assign({ lang: "en", speech: "en", dict: {} }, JSON.parse(document.getElementById("i18n").textContent)); }
  catch (_) { return { lang: "en", speech: "en", dict: {} }; }
})();
function t(text, vars) {
  const out = Object.prototype.hasOwnProperty.call(I18N.dict, text) ? I18N.dict[text] : text;
  return vars ? out.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m)) : out;
}
// Icons: the site's drawings (web/icons.py) come with every page as an inline sprite, and an icon is a <use> that points into it, so it takes the text's colour.
const SVG_NS = "http://www.w3.org/2000/svg";
function icon(name, cls) {
  const svg = document.createElementNS(SVG_NS, "svg"), use = document.createElementNS(SVG_NS, "use");
  svg.setAttribute("class", "ic" + (cls ? " " + cls : "")); svg.setAttribute("viewBox", "0 0 24 24"); svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
  use.setAttribute("href", "#i-" + name); svg.append(use);
  return svg;
}
// A profile picture: the animal's face in a soft circle (a name the sprite does not know becomes the fish).
function avatarEl(name, cls) {
  const w = document.createElement("span");
  w.className = "avt" + (cls ? " " + cls : "");
  w.append(icon("av-" + (document.getElementById("i-av-" + name) ? name : "fish")));
  return w;
}
// What goes in a leaderboard's rank cell: a medal for the first three, a number after that.
function rankMark(rank) {
  if (rank >= 1 && rank <= 3) {
    const sr = document.createElement("span"); sr.className = "sr"; sr.textContent = String(rank);
    return [icon("medal", ["m-gold", "m-silver", "m-bronze"][rank - 1]), sr];
  }
  return [rank ? String(rank) : "–"];
}
// Lives as hearts: filled for the ones left, faint for the ones lost.
function heartIcons(now, total) {
  return Array.from({ length: total }, (_, i) => (i < now ? icon("heart-fill") : icon("heart", "off")));
}
// The drawing's path data, for scenes drawn on a canvas (Scam Road): [{d, fill}].
function iconPaths(name) {
  const sym = document.getElementById("i-" + name);
  return sym ? [...sym.querySelectorAll("path")].map((p) => ({ d: p.getAttribute("d"), fill: p.hasAttribute("fill") })) : [];
}

// The voice for read-aloud: Chinese text is read by a Chinese voice (Traditional on a Traditional page), a Malay page by a Malay voice, everything else by an English one.
function speechLang(text) {
  if (/[㐀-鿿]/.test(text)) return I18N.speech.startsWith("zh") ? I18N.speech : "zh-CN";
  return I18N.lang === "ms" ? I18N.speech : "en";
}
function say(text) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = speechLang(text);
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}
