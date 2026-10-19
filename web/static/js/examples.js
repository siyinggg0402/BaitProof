document.querySelectorAll("[data-example]").forEach((b) =>
  b.addEventListener("click", () => {
    const t = document.getElementById("message");
    t.value = b.dataset.example;
    t.focus();
  })
);
