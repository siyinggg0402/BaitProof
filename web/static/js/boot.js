document.documentElement.classList.add("js");
try { if (localStorage.getItem("bp-big") === "1") document.documentElement.classList.add("big"); } catch (_) {}
