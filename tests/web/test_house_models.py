"""The house's 3D models are code, not files. What can be checked without a browser (the browser test draws every one and checks it fits its footprint): every item in the
shop has a model, no model is for something that is not sold, the pieces are wired together, and the character tables in the 3D file are the server's.
The model files are plain modules, so these read them by running them in Node (skipped where Node is not installed)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from core.domain import characters as ch
from core.game import house

JS = Path(__file__).resolve().parents[2] / "web" / "static" / "js"
node = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")


def run_js(code: str):
    out = subprocess.run(["node", "--input-type=module", "-e", code], cwd=JS, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    return json.loads(out.stdout)


@node
def test_every_item_in_the_shop_has_exactly_one_model_and_every_model_is_for_sale():
    keys = run_js('import { MODELS as A } from "./house_models_a.js"; import { MODELS as B } from "./house_models_b.js"; console.log(JSON.stringify([Object.keys(A), Object.keys(B)]));')
    a, b = keys
    assert len(a) == len(set(a)) and len(b) == len(set(b)) and not set(a) & set(b), "no item has two models"
    pets = {i.id for i in house.CATALOG.values() if i.cat == "pets"}
    assert set(a) | set(b) | pets == set(house.CATALOG), (sorted(set(house.CATALOG) - set(a) - set(b) - pets), sorted((set(a) | set(b)) - set(house.CATALOG)))
    assert len(a) + len(b) + len(pets) == len(house.CATALOG)
    assert not set(a) & pets and not set(b) & pets


@node
def test_the_wired_up_models_cover_the_whole_catalogue_and_the_pets_are_buildable():
    ids = run_js('import { MODELS } from "./house_models.js"; console.log(JSON.stringify(Object.keys(MODELS)));')
    assert sorted(ids) == sorted(house.CATALOG)


@node
def test_a_model_builds_for_every_item_and_for_every_kind_of_character():
    """Run every builder (no WebGL needed to build): each gives a group with something in it, and the characters build for every hair style, outfit and accessory."""
    out = run_js('''
      import { MODELS, buildCharacter, buildDriver } from "./house_models.js";
      const empty = [], count = (g) => { let n = 0; g.traverse((o) => { if (o.isMesh) n++; }); return n; };
      for (const [id, make] of Object.entries(MODELS)) { const g = make(); if (!g || count(g) < 3) empty.push(id); }
      const T = { skins: 8, hair: ["short","bob","long","ponytail","bun","curly","buzz","bald","tudung"], outfits: ["tee","hoodie","shirt","kurung","jacket"], acc: ["none","glasses","round","songkok","cap","flower"] };
      const bad = [];
      for (const hair of T.hair) for (const outfit of T.outfits) for (const accessory of T.acc) for (const seated of [false, true]) {
        const g = buildCharacter({ skin: "#D29B6B", hair, hairColor: "#3B2A20", outfit, outfitColor: "#7A5CD0", accessory }, { hat: "none", seated });
        if (count(g) < 8 || typeof g.userData.tick !== "function") bad.push([hair, outfit, accessory, seated]);
      }
      for (const hat of ["none","cap","shades","party","scarf","crown"]) if (count(buildDriver("p.2.0.1.0.0.0", hat)) < 8) bad.push(["hat", hat]);
      for (const a of ["fish","fox","panda","tiger","frog","owl","octopus","turtle","unicorn","cat","penguin","lion"]) if (count(buildDriver(a, "none")) < 5) bad.push(["animal", a]);
      console.log(JSON.stringify({ empty, bad }));
    ''')
    assert out == {"empty": [], "bad": []}


@node
def test_the_3d_characters_use_the_same_tables_as_the_server():
    t = run_js('import { LOOK_TABLES } from "./character3d.js"; console.log(JSON.stringify(LOOK_TABLES));')
    assert [c.upper() for c in t["SKINS"]] == list(ch.SKINS) and [c.upper() for c in t["HAIR_COLORS"]] == list(ch.HAIR_COLORS) and [c.upper() for c in t["OUTFIT_COLORS"]] == list(ch.OUTFIT_COLORS)
    assert t["HAIR_STYLES"] == list(ch.HAIR_STYLES) and t["OUTFIT_STYLES"] == list(ch.OUTFIT_STYLES) and t["ACCESSORIES"] == list(ch.ACCESSORIES) and t["FACES"] == list(ch.FACES)


def test_the_pieces_are_wired_together():
    models = (JS / "house_models.js").read_text()
    assert "house_models_a.js" in models and "house_models_b.js" in models and "character3d.js" in models
    pets = re.search(r"const PETS = \[(.*?)\]", models, flags=re.S).group(1)
    assert set(re.findall(r'"(\w+)"', pets)) == {i.id[4:] for i in house.CATALOG.values() if i.cat == "pets"}
    assert 'from "./house_models.js"' in (JS / "house.js").read_text() and 'import("./character3d.js")' in (JS / "road.js").read_text()
