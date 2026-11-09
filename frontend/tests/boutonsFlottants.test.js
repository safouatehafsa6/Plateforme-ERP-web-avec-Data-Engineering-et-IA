import test from "node:test";
import assert from "node:assert/strict";
import {
  CONFIG_PAR_DEFAUT, boutonVisible, correspondRoute, erreurCible, formDepuisBouton, listeDepuisTexte, payloadDepuisForm,
  positionEffective, profilsSession, resumeVisibilite, titreBouton, trierBoutons, validerBouton, boutonVide,
} from "../src/validation/boutonsFlottants.js";

const visiteur = null;
const collab = { id: 1, type: "interne", nomBase: "compte_x", role: "Commercial" };
const adminEntreprise = { id: 2, type: "interne", nomBase: "compte_x", role: "Admin" };
const superAdmin = { id: 3, type: "plateforme", role: "super_admin" };
const externe = { id: 4, type: "externe", nomBase: "compte_x", role: "client" };
const b = (extra) => ({ actif: true, audience: "tous", profils: [], appareils: "tous", routes_incluses: [], routes_exclues: [], action: "support", ...extra });

test("profils d'une session", () => {
  assert.deepEqual(profilsSession(visiteur), []);
  assert.deepEqual(profilsSession(collab), ["interne"]);
  assert.deepEqual(profilsSession(adminEntreprise), ["interne", "admin_entreprise"]);
  assert.deepEqual(profilsSession(superAdmin), ["plateforme"]);
  assert.deepEqual(profilsSession(externe), ["externe"]);
});

test("audience : visiteurs, connectés, tout le monde", () => {
  assert.equal(boutonVisible(b({ audience: "public", action: "route" }), { session: visiteur }), true);
  assert.equal(boutonVisible(b({ audience: "public", action: "route" }), { session: collab }), false);
  assert.equal(boutonVisible(b({ audience: "connecte" }), { session: visiteur }), false);
  assert.equal(boutonVisible(b({ audience: "connecte" }), { session: collab }), true);
  assert.equal(boutonVisible(b({}), { session: visiteur }) && boutonVisible(b({}), { session: collab }), true);
});

test("notifications et assistant exigent toujours une session", () => {
  for (const action of ["notifications", "assistant"]) assert.equal(boutonVisible(b({ action }), { session: visiteur }), false);
  assert.equal(boutonVisible(b({ action: "assistant" }), { session: collab }), true);
});

test("ciblage par profil", () => {
  const reserve = b({ profils: ["admin_entreprise", "plateforme"] });
  assert.equal(boutonVisible(reserve, { session: collab }), false);
  assert.equal(boutonVisible(reserve, { session: adminEntreprise }), true);
  assert.equal(boutonVisible(reserve, { session: superAdmin }), true);
  assert.equal(boutonVisible(reserve, { session: visiteur }), false);
});

test("ciblage par appareil", () => {
  assert.equal(boutonVisible(b({ appareils: "mobile" }), { mobile: true }), true);
  assert.equal(boutonVisible(b({ appareils: "mobile" }), { mobile: false }), false);
  assert.equal(boutonVisible(b({ appareils: "ordinateur" }), { mobile: true }), false);
  assert.equal(boutonVisible(b({ appareils: "ordinateur" }), { mobile: false }), true);
});

test("pages incluses / exclues avec frontière de segment", () => {
  assert.equal(correspondRoute("/clients", "/clients"), true);
  assert.equal(correspondRoute("/clients/12", "/clients"), true);
  assert.equal(correspondRoute("/clientele", "/clients"), false);
  assert.equal(correspondRoute("/clients", "/"), false);
  assert.equal(correspondRoute("/", "/"), true);
  const seulement = b({ routes_incluses: ["/clients", "/ventes"] });
  assert.equal(boutonVisible(seulement, { pathname: "/ventes" }), true);
  assert.equal(boutonVisible(seulement, { pathname: "/stock" }), false);
  const sauf = b({ routes_exclues: ["/room-live"] });
  assert.equal(boutonVisible(sauf, { pathname: "/room-live" }), false);
  assert.equal(boutonVisible(sauf, { pathname: "/clients" }), true);
});

test("période d'affichage", () => {
  const now = new Date("2026-06-15T12:00:00Z");
  assert.equal(boutonVisible(b({ affiche_du: "2026-06-16T00:00:00Z" }), { maintenant: now }), false);
  assert.equal(boutonVisible(b({ affiche_jusqu_au: "2026-06-15T12:00:00Z" }), { maintenant: now }), false);
  assert.equal(boutonVisible(b({ affiche_du: "2026-06-01T00:00:00Z", affiche_jusqu_au: "2026-07-01T00:00:00Z" }), { maintenant: now }), true);
  assert.equal(boutonVisible(b({ actif: false }), {}), false);
});

test("WhatsApp masqué sans numéro, affiché avec le numéro du bouton ou celui de la plateforme", () => {
  const wa = b({ action: "whatsapp", cible: null });
  assert.equal(boutonVisible(wa, { numeroWhatsapp: "" }), false);
  assert.equal(boutonVisible(wa, { numeroWhatsapp: "21612345678" }), true);
  assert.equal(boutonVisible(b({ action: "whatsapp", cible: "21699887766" }), { numeroWhatsapp: "" }), true);
});

test("la configuration d'origine reproduit le menu d'aide historique", () => {
  const visibles = (session, pathname = "/clients") => trierBoutons(CONFIG_PAR_DEFAUT.boutons)
    .filter((x) => boutonVisible(x, { session, pathname, numeroWhatsapp: "21612345678" })).map((x) => x.cle);
  assert.deepEqual(visibles(collab), ["notifications", "assistant", "support", "whatsapp", "theme", "langue"]);
  assert.deepEqual(visibles(visiteur, "/"), ["support", "whatsapp", "connexion", "inscription", "theme", "langue"]);
  assert.equal(CONFIG_PAR_DEFAUT.config.actif, true);
  assert.equal(CONFIG_PAR_DEFAUT.boutons.length, 8);
});

test("titre dans la langue de l'utilisateur, avec repli sur le français", () => {
  const x = { cle: "k", titres: { fr: "Aide", en: "Help" } };
  assert.equal(titreBouton(x, "en"), "Help");
  assert.equal(titreBouton(x, "ar"), "Aide");
  assert.equal(titreBouton({ cle: "k", titres: {} }, "fr"), "k");
});

test("tri par ordre puis identifiant ; position automatique selon la langue", () => {
  assert.deepEqual(trierBoutons([{ id: 3, ordre: 5 }, { id: 1, ordre: 20 }, { id: 2, ordre: 5 }]).map((x) => x.id), [2, 3, 1]);
  assert.equal(positionEffective("auto", false), "bas-droite");
  assert.equal(positionEffective("auto", true), "bas-gauche");
  assert.equal(positionEffective("haut-gauche", false), "haut-gauche");
});

test("cibles : liens sûrs uniquement", () => {
  assert.equal(erreurCible("route", "/clients"), "");
  for (const ko of ["clients", "//evil.tn", "/../x", "javascript:alert(1)"]) assert.notEqual(erreurCible("route", ko), "", ko);
  assert.equal(erreurCible("url", "https://exemple.tn"), "");
  for (const ko of ["http://exemple.tn", "javascript:alert(1)", "data:text/html,x", ""]) assert.notEqual(erreurCible("url", ko), "", ko);
  assert.equal(erreurCible("whatsapp", ""), "");
  assert.notEqual(erreurCible("whatsapp", "abc"), "");
  assert.notEqual(erreurCible("support", "/x"), "");
  assert.notEqual(erreurCible("route", "/clients", true), "");
});

test("validation du formulaire", () => {
  const ok = { ...boutonVide(), titres: { fr: "Promo", en: "", ar: "" }, cible: "/tarifs" };
  assert.deepEqual(validerBouton(ok), {});
  assert.ok(validerBouton({ ...ok, titres: { fr: " " } }).titre);
  assert.ok(validerBouton({ ...ok, titres: { fr: "x".repeat(41) } }).titre);
  assert.ok(validerBouton({ ...ok, couleur: "rouge" }).couleur);
  assert.ok(validerBouton({ ...ok, icone: "skull" }).icone);
  assert.ok(validerBouton({ ...ok, placement: "libre", position: "" }).position);
  assert.deepEqual(validerBouton({ ...ok, placement: "libre", position: "haut-gauche" }), {});
  assert.ok(validerBouton({ ...ok, ordre: -1 }).ordre);
  assert.ok(validerBouton({ ...ok, audience: "public", profils: ["interne"] }).profils);
  assert.ok(validerBouton({ ...ok, action: "notifications", cible: "", audience: "public" }).audience);
  assert.ok(validerBouton({ ...ok, routes_incluses: ["clients"] }).routes_incluses);
  assert.ok(validerBouton({ ...ok, affiche_du: "2026-02-01T00:00", affiche_jusqu_au: "2026-01-01T00:00" }).dates);
});

test("conversion formulaire ↔ API", () => {
  assert.deepEqual(listeDepuisTexte(" /a, /b\n/a ;/c "), ["/a", "/b", "/c"]);
  const f = { ...boutonVide(), titres: { fr: " Promo ", en: "", ar: "" }, cible: " /tarifs ", couleur: "", placement: "menu", position: "bas-droite", ordre: "30" };
  const p = payloadDepuisForm(f);
  assert.deepEqual(p.titres, { fr: "Promo" });
  assert.equal(p.cible, "/tarifs");
  assert.equal(p.couleur, null);
  assert.equal(p.position, null, "la position n'est envoyée que pour un bouton isolé");
  assert.equal(p.ordre, 30);
  assert.equal(payloadDepuisForm({ ...f, placement: "libre" }).position, "bas-droite");
  const retour = formDepuisBouton({ id: 5, cle: "promo", titres: { fr: "Promo" }, couleur: null, position: null, cible: null, affiche_du: null });
  assert.equal(retour.titres.en, "");
  assert.equal(retour.couleur, "");
  assert.equal(retour.cible, "");
});

test("résumé de visibilité lisible", () => {
  assert.equal(resumeVisibilite(b({ audience: "connecte" })), "Utilisateurs connectés");
  assert.match(resumeVisibilite(b({ profils: ["externe"], appareils: "mobile", routes_exclues: ["/stock"], affiche_du: "2026-01-01" })), /Utilisateur externe · Mobile.*sauf : \/stock · période limitée/);
});
