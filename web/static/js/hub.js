// The Train page's house: a small live preview of your own room. The 3D code (house.js, three.js) is big, so it loads only when the room scrolls into view,
// and never on a device that asked to save data. Until it has drawn its first picture the page shows your character instead, and it keeps that if 3D cannot run.
(() => {
  const root = document.getElementById("house");
  if (!root) return;
  const conn = navigator.connection || {};
  if (conn.saveData) return;
  const load = () => import("/static/js/house.js").catch(() => { root.classList.add("flat"); });
  if (!("IntersectionObserver" in window)) { load(); return; }
  const io = new IntersectionObserver((entries) => {
    if (!entries.some((e) => e.isIntersecting)) return;
    io.disconnect(); load();
  }, { rootMargin: "200px" });
  io.observe(root);
})();
