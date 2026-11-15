import test from "node:test";
import assert from "node:assert/strict";
import { interpreter, normaliserCommande } from "../src/validation/commandesVocales.js";

const nav = (texte) => interpreter(texte)?.chemin;

test("navigation en français, avec accents, politesse et articles", () => {
  assert.equal(nav("Ouvre les ventes"), "/ventes");
  assert.equal(nav("ouvrir le module achats"), "/achats");
  assert.equal(nav("Va dans la comptabilité, s'il te plaît"), "/comptabilite");
  assert.equal(nav("Affiche le tableau de bord"), "/dashboard");
  assert.equal(nav("ouvre room live"), "/room-live");
});

test("navigation en anglais et en arabe", () => {
  assert.equal(nav("open sales"), "/ventes");
  assert.equal(nav("please go to the inventory"), "/stock");
  assert.equal(nav("افتح المبيعات"), "/ventes");
  assert.equal(nav("افتح المشتريات من فضلك"), "/achats");
  assert.equal(nav("اذهب إلى المخزون"), "/stock");
});

test("le module le plus spécifique l'emporte : documents IA vs documents", () => {
  assert.equal(nav("ouvre documents ia"), "/documents-ia");
  assert.equal(nav("open smart documents"), "/documents-ia");
  assert.equal(interpreter("ouvre les documents").type, "documents");
});

test("une vraie question n'est jamais prise pour une commande", () => {
  for (const q of ["quelles sont les ventes du mois", "ouvre une commande de vente pour le client atlas",
    "ventes", "combien de clients ai-je", "what are my sales this month", "كم عدد المبيعات هذا الشهر"]) {
    assert.equal(interpreter(q), null, q);
  }
});

test("notifications", () => {
  assert.equal(interpreter("lis mes notifications").type, "notifications");
  assert.equal(interpreter("read notifications").type, "notifications");
  assert.equal(interpreter("اقرا الاشعارات").type, "notifications");
});

test("la déconnexion est une action sensible qui exige une confirmation", () => {
  const c = interpreter("déconnecte-moi");
  assert.equal(c.type, "deconnexion");
  assert.equal(c.sensible, true);
  assert.equal(interpreter("oui", { confirmationEnAttente: false }), null);          // pas de confirmation attendue
  assert.equal(interpreter("oui", { confirmationEnAttente: true }).type, "confirmer");
  assert.equal(interpreter("non merci", { confirmationEnAttente: true }).type, "annuler");
  assert.equal(interpreter("نعم", { confirmationEnAttente: true }).type, "confirmer");
  assert.equal(interpreter("yes please", { confirmationEnAttente: true }).type, "confirmer");
});

test("mode conversation mains libres", () => {
  assert.deepEqual(interpreter("active le mode conversation"), { type: "conversation", actif: true });
  assert.deepEqual(interpreter("arrête la conversation"), { type: "conversation", actif: false });
  assert.deepEqual(interpreter("conversation mode"), { type: "conversation", actif: true });
});

test("normalisation : accents, ponctuation, tashkeel arabe", () => {
  assert.equal(normaliserCommande("  Déconnecte-MOI !  "), "deconnecte moi");
  assert.equal(normaliserCommande("افْتَحْ الْمُبِيعَات"), normaliserCommande("افتح المبيعات"));
  assert.equal(interpreter("", {}), null);
});
