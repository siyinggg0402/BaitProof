document.documentElement.classList.add("js");
try { if (localStorage.getItem("bp-big") === "1") document.documentElement.classList.add("big"); } catch (_) {}

// Translation for the scripts: the server embeds {lang, speech, dict} as <script type="application/json" id="i18n"> on Chinese pages only.
// The function t takes the English text (and an object of values) and gives the text in the page's language (English is the key and the fallback), filling in each {name}.
const I18N = (() => {
  try { return Object.assign({ lang: "en", speech: "en", dict: {} }, JSON.parse(document.getElementById("i18n").textContent)); }
  catch (_) { return { lang: "en", speech: "en", dict: {} }; }
})();
function t(text, vars) {
  const out = Object.prototype.hasOwnProperty.call(I18N.dict, text) ? I18N.dict[text] : text;
  return vars ? out.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m)) : out;
}
// The voice for read-aloud: Chinese text is read by a Chinese voice (Traditional on a Traditional page), everything else by an English one.
function speechLang(text) { return /[㐀-鿿]/.test(text) ? (I18N.speech !== "en" ? I18N.speech : "zh-CN") : "en"; }
function say(text) {
  if (!("speechSynthesis" in window)) return;
  const u = new SpeechSynthesisUtterance(text);
  u.lang = speechLang(text);
  speechSynthesis.cancel();
  speechSynthesis.speak(u);
}
