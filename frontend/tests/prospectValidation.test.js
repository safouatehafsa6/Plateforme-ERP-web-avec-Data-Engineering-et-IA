import test from "node:test";
import assert from "node:assert/strict";
import {
  actionsDisponibles, analyserConflitDoublon, libelleDoublon, normaliserProspect, peutFaire, resumeEvenement,
  transitionsPossibles, validerChangementStatut, validerMotifArchivage, validerProspect, validerSuivi, versIsoUtc,
} from "../src/validation/prospect.js";

test("un prospect exige un nom ET au moins un moyen de contact", () => {
  assert.match(validerProspect({ nom: "Atlas" }).moyen_contact, /e-mail ou un numéro/i);
  assert.match(validerProspect({ nom: " ", email: "a@atlas.tn" }).nom, /obligatoire/i);
  assert.deepEqual(validerProspect({ nom: "Atlas", telephone: "+216 12 345 678" }), {});
  assert.deepEqual(validerProspect({ nom: "Atlas", email: "a@atlas.tn" }), {});
});

test("les contrôles de format du client s'appliquent aussi au prospect", () => {
  assert.match(validerProspect({ nom: "Atlas", email: "pas-un-email" }).email, /e-mail valide/i);
  assert.match(validerProspect({ nom: "Atlas", telephone: "06ABC123" }).telephone, /caractères|chiffres/i);
  assert.match(validerProspect({ nom: "Atlas", email: "a@atlas.tn", besoin: "x".repeat(2001) }).besoin, /2000/);
});

test("la normalisation nettoie les champs et corrige une origine inconnue", () => {
  assert.deepEqual(normaliserProspect({ nom: " Atlas ", contact: "  ", email: " a@atlas.tn ", source: "inconnue", besoin: " Devis " }), {
    nom: "Atlas", contact: null, email: "a@atlas.tn", telephone: null, adresse: null, source: "autre", besoin: "Devis",
  });
});

test("workflow des statuts : transitions autorisées uniquement", () => {
  assert.deepEqual(transitionsPossibles("nouveau"), ["contacte", "qualifie", "perdu"]);
  assert.ok(!transitionsPossibles("contacte").includes("nouveau"));
  assert.deepEqual(transitionsPossibles("converti"), []);
  assert.deepEqual(transitionsPossibles("inconnu"), []);
});

test("un motif est obligatoire pour déclarer un prospect perdu", () => {
  assert.match(validerChangementStatut({ statut: "perdu", commentaire: "  " }).commentaire, /motif/i);
  assert.deepEqual(validerChangementStatut({ statut: "perdu", commentaire: "Prix trop élevé" }), {});
  assert.deepEqual(validerChangementStatut({ statut: "contacte" }), {});
  assert.ok(validerChangementStatut({}).statut);
});

test("le motif d'archivage doit contenir au moins 3 caractères", () => {
  assert.ok(validerMotifArchivage(" a "));
  assert.equal(validerMotifArchivage("Inactif"), "");
});

test("un suivi exige un texte, un type valide et une date non future", () => {
  const maintenant = new Date("2026-03-10T12:00:00");
  assert.ok(validerSuivi({ type_evenement: "appel", contenu: "  " }, maintenant).contenu);
  assert.ok(validerSuivi({ type_evenement: "creation", contenu: "x" }, maintenant).type_evenement);
  assert.deepEqual(validerSuivi({ type_evenement: "appel", contenu: "Rappelé", date_evenement: "2026-03-09T09:00" }, maintenant), {});
  assert.match(validerSuivi({ type_evenement: "appel", contenu: "x", date_evenement: "2026-03-11T09:00" }, maintenant).date_evenement, /futur/i);
  assert.ok(validerSuivi({ type_evenement: "appel", contenu: "x", date_evenement: "n'importe quoi" }, maintenant).date_evenement);
});

test("la relance ne peut pas précéder la date du suivi", () => {
  const maintenant = new Date("2026-03-10T12:00:00");
  const base = { type_evenement: "appel", contenu: "x", date_evenement: "2026-03-09T09:00" };
  assert.match(validerSuivi({ ...base, prochaine_relance: "2026-03-08" }, maintenant).prochaine_relance, /précéder/i);
  assert.deepEqual(validerSuivi({ ...base, prochaine_relance: "2026-03-09" }, maintenant), {});
  assert.deepEqual(validerSuivi({ ...base, prochaine_relance: "2026-04-01" }, maintenant), {});
});

test("conversion de la date locale en ISO UTC", () => {
  assert.equal(versIsoUtc(""), null);
  assert.equal(versIsoUtc("pas une date"), null);
  assert.match(versIsoUtc("2026-03-04T10:30"), /^2026-03-04T\d{2}:30:00\.000Z$/);
});

test("les opérations proposées suivent l'état du prospect ET les permissions", () => {
  const tous = ["consulter", "creer", "modifier", "valider", "supprimer"];
  const actif = { statut: "qualifie", archive: false };

  assert.deepEqual(actionsDisponibles(actif, tous), { modifier: true, changerStatut: true, ajouterSuivi: true, convertir: true, archiver: true, reactiver: false });
  // lecteur : rien à faire en dehors de la consultation
  assert.ok(Object.values(actionsDisponibles(actif, ["consulter"])).every((v) => v === false));
  // modificateur : ne peut ni convertir ni archiver
  const modif = actionsDisponibles(actif, ["consulter", "modifier"]);
  assert.equal(modif.modifier, true); assert.equal(modif.convertir, false); assert.equal(modif.archiver, false); assert.equal(modif.ajouterSuivi, false);
  // archivé : lecture seule, seule la réactivation reste possible
  const archive = actionsDisponibles({ statut: "qualifie", archive: true }, tous);
  assert.deepEqual(archive, { modifier: false, changerStatut: false, ajouterSuivi: false, convertir: false, archiver: false, reactiver: true });
  // converti : plus de modification ni de nouvelle conversion
  const converti = actionsDisponibles({ statut: "converti", archive: false }, tous);
  assert.equal(converti.modifier, false); assert.equal(converti.convertir, false); assert.equal(converti.archiver, true);
  // perdu : à rouvrir avant conversion
  assert.equal(actionsDisponibles({ statut: "perdu", archive: false }, tous).convertir, false);
  assert.deepEqual(actionsDisponibles(null, tous), {});
  assert.equal(peutFaire(undefined, "creer"), false);
});

test("analyse d'un conflit de doublon renvoyé par l'API", () => {
  const fort = { status: 409, data: { detail: "Doublon", code: "DOUBLON_FORT", confirmable: false, doublons: [{ entite: "client", id: 3, nom: "Atlas", motifs: ["email"], niveau: "fort", archive: false }] } };
  const c = analyserConflitDoublon(fort);
  assert.equal(c.confirmable, false);
  assert.equal(c.clients.length, 1);
  const possible = analyserConflitDoublon({ status: 409, data: { detail: "d", code: "DOUBLON_POSSIBLE", confirmable: true, doublons: [{ entite: "prospect", id: 1, nom: "A", motifs: ["nom_similaire"], archive: true }] } });
  assert.equal(possible.confirmable, true);
  assert.equal(possible.archives.length, 1);
  assert.equal(possible.clients.length, 0);
  assert.equal(analyserConflitDoublon({ status: 409, data: { detail: "Client archivé" } }), null);
  assert.equal(analyserConflitDoublon({ status: 500, data: { doublons: [] } }), null);
  assert.equal(analyserConflitDoublon(new Error("réseau")), null);
});

test("libellés lisibles pour les doublons et les événements", () => {
  assert.equal(libelleDoublon({ entite: "prospect", archive: true, nom: "Atlas", motifs: ["email", "telephone"] }), "Prospect archivé « Atlas » — même e-mail, même téléphone");
  assert.equal(resumeEvenement({ type_evenement: "statut", details: { avant: "nouveau", apres: "perdu" }, contenu: "Prix" }), "Nouveau → Perdu — Prix");
  assert.equal(resumeEvenement({ type_evenement: "modification", details: { changements: { nom: {}, email: {} } } }), "Champs modifiés : nom, email");
  assert.equal(resumeEvenement({ type_evenement: "appel", contenu: "RDV fixé" }), "RDV fixé");
});
