// Every 3D model the house needs, in one place: the furniture, plants and decor (house_models_a.js), the wall and festival items (house_models_b.js), the pets and the
// characters (character3d.js). MODELS[id]() builds a fresh model for a catalog item (core/game/house.py); the character builders are for the house and the road.
import { MODELS as A } from "./house_models_a.js";
import { MODELS as B } from "./house_models_b.js";
import { buildCharacter, buildDriver, buildPet } from "./character3d.js";

const PETS = ["fish", "fox", "panda", "tiger", "frog", "owl", "octopus", "turtle", "unicorn", "cat", "penguin", "lion"];
export const MODELS = { ...A, ...B, ...Object.fromEntries(PETS.map((p) => ["pet-" + p, () => buildPet("pet-" + p)])) };
export { buildCharacter, buildDriver, buildPet };
