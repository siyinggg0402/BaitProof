// The character creator: pick a skin tone, hair, outfit and extras and watch the portrait change. The chosen look is kept in the form's hidden "avatar" field,
// and a "look" event tells the page (the house saves it straight away). Without this script the form still sends the look the server picked.
(function () {
  const HAIR = [t("Short"), t("Bob"), t("Long"), t("Ponytail"), t("Bun"), t("Curly"), t("Buzz cut"), t("Bald"), t("Tudung"), t("Side part"), t("Spiky")];
  const OUTFIT = [t("T-shirt"), t("Hoodie"), t("Shirt"), t("Baju kurung"), t("Jacket"), t("Polo"), t("Kurta")];
  const EXTRA = [t("No accessory"), t("Glasses"), t("Round glasses"), t("Songkok"), t("Cap"), t("Flower")];
  const FACE = [t("Rosy cheeks"), t("Plain"), t("Stubble"), t("Moustache"), t("Goatee"), t("Beard")];
  if (!LOOK) return;

  function init(root) {
    const field = root.querySelector("input[name=avatar]"), groups = root.querySelector(".cr-groups"), preview = root.querySelector(".cr-preview"), random = root.querySelector(".cr-random");
    let nums = (parseLook(field.value) || parseLook(root.dataset.look) || parseLook("p.2.0.1.0.0.0")).nums.slice();
    const swatch = (colors, name) => ({ count: colors.length, name, color: (i) => colors[i] });
    const spec = [
      { label: t("Skin tone"), key: 0, ...swatch(LOOK.skins, (i) => t("Skin tone {n}", { n: i + 1 })) },
      { label: t("Hair"), key: 1, count: LOOK.hair.length, name: (i) => HAIR[i] },
      { label: t("Hair colour"), key: 2, ...swatch(LOOK.hair_colors, (i) => t("Hair colour {n}", { n: i + 1 })) },
      { label: t("Outfit"), key: 3, count: LOOK.outfits.length, name: (i) => OUTFIT[i] },
      { label: t("Outfit colour"), key: 4, ...swatch(LOOK.outfit_colors, (i) => t("Outfit colour {n}", { n: i + 1 })) },
      { label: t("Extras"), key: 5, count: LOOK.accessories.length, name: (i) => EXTRA[i] },
      { label: t("Face"), key: 6, count: LOOK.faces.length, name: (i) => FACE[i] },
    ];
    const tudung = () => LOOK.hair[nums[1]] === "tudung", hat = (i) => tudung() && (LOOK.accessories[i] === "songkok" || LOOK.accessories[i] === "cap");

    function set(key, value) {
      nums[key] = value;
      if (tudung() && hat(nums[5])) nums[5] = 0;   // a songkok or a cap does not go on a tudung
      draw(true);
    }
    function draw(changed) {
      const code = lookCode(nums);
      if (changed) { field.value = code; root.dispatchEvent(new CustomEvent("look", { detail: code, bubbles: true })); }
      if (changed || parseLook(field.value)) preview.replaceChildren(portraitEl(code, "big"));   // (an old animal picture stays until they change something)
      groups.replaceChildren(...spec.map((g) => {
        const block = document.createElement("div"), label = document.createElement("span"), row = document.createElement("div");
        block.className = "cr-block"; label.className = "cr-label"; label.textContent = g.label; label.setAttribute("aria-hidden", "true");
        row.className = "cr-group"; row.setAttribute("role", "group"); row.setAttribute("aria-label", g.label);
        for (let i = 0; i < g.count; i++) {
          const b = document.createElement("button");
          b.type = "button"; b.className = "cr-opt" + (g.color ? " sw" : ""); b.title = g.name(i); b.setAttribute("aria-label", g.name(i));
          b.setAttribute("aria-pressed", String(nums[g.key] === i));
          if (g.key === 5 && hat(i)) b.disabled = true;
          if (g.color) b.style.background = g.color(i);
          else b.append(portraitEl(lookCode(nums.map((v, k) => (k === g.key ? i : g.key === 3 && k === 1 && tudung() ? 0 : v)))));   // (a tudung would hide the outfits: show them on short hair)
          b.addEventListener("click", () => set(g.key, i));
          row.append(b);
        }
        block.append(label, row);
        return block;
      }));
    }
    if (random) {
      random.hidden = false;
      random.addEventListener("click", () => {
        const pick = (n) => Math.floor(Math.random() * n), one = (list) => list[pick(list.length)];
        nums = LOOK_SIZES().map(pick);
        nums[6] = one([0, 0, 1, 1, 2, 3, 4, 5]);                       // as on the server: about as many rosy and plain faces as faces with stubble, a moustache or a beard
        if (nums[6] >= 2) {                                           // ... and those do not come with a flower, a baju kurung or long hair
          if (!LOOK.masculine_hair.includes(LOOK.hair[nums[1]])) nums[1] = LOOK.hair.indexOf(one(LOOK.masculine_hair));
          if (!LOOK.masculine_outfits.includes(LOOK.outfits[nums[3]])) nums[3] = LOOK.outfits.indexOf(one(LOOK.masculine_outfits));
          if (LOOK.accessories[nums[5]] === "flower") nums[5] = 0;
        }
        if (tudung() && hat(nums[5])) nums[5] = 0;
        draw(true);
      });
    }
    root.setLook = (code) => { const p = parseLook(code); if (p) { nums = p.nums.slice(); draw(false); } };
    draw(false);
  }
  const LOOK_SIZES = () => [LOOK.skins.length, LOOK.hair.length, LOOK.hair_colors.length, LOOK.outfits.length, LOOK.outfit_colors.length, LOOK.accessories.length, LOOK.faces.length];
  document.querySelectorAll("[data-creator]").forEach(init);
})();
