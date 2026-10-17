import test from "node:test";
import assert from "node:assert/strict";
import { normaliserClient, validerClient, suggererCorrectionEmail } from "../src/validation/client.js";

test("un nom valide suffit ; les champs facultatifs peuvent être vides", () => {
  assert.deepEqual(validerClient({ nom: " Société Atlas " }), {});
  assert.deepEqual(normaliserClient({ nom: " Société Atlas ", email: " ", telephone: "", adresse: " " }), {
    nom: "Société Atlas", email: null, telephone: null, adresse: null,
  });
});

test("un nom vide ou composé uniquement d'espaces est refusé", () => {
  assert.match(validerClient({ nom: "   " }).nom, /obligatoire/i);
});

test("une adresse e-mail mal formée est refusée et une adresse valide est acceptée", () => {
  assert.match(validerClient({ nom: "Atlas", email: "pas-une-adresse" }).email, /e-mail valide/i);
  assert.deepEqual(validerClient({ nom: "Atlas", email: "contact@atlas.example" }), {});
});

test("un téléphone international valide est accepté", () => {
  assert.deepEqual(validerClient({ nom: "Atlas", telephone: "+212 6 12 34 56 78" }), {});
});

test("un téléphone contenant des lettres ou trop peu de chiffres est refusé", () => {
  assert.match(validerClient({ nom: "Atlas", telephone: "06ABC123" }).telephone, /caractères|chiffres/i);
  assert.match(validerClient({ nom: "Atlas", telephone: "12345" }).telephone, /7 et 15 chiffres/i);
});

test("les champs respectent leurs limites de longueur", () => {
  assert.match(validerClient({ nom: "N".repeat(151) }).nom, /150 caractères/i);
  assert.match(validerClient({ nom: "Atlas", adresse: "A".repeat(1001) }).adresse, /1000 caractères/i);
});


test("l'assistance propose une correction pour quelques fautes courantes de domaine e-mail", () => {
  assert.equal(suggererCorrectionEmail("contact@gmal.com"), "contact@gmail.com");
  assert.equal(suggererCorrectionEmail("contact@entreprise.com"), null);
  assert.equal(suggererCorrectionEmail("adresse-invalide"), null);
});
