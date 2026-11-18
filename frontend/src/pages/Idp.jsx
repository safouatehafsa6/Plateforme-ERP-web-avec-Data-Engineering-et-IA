import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  UploadCloud, FileText, CheckCircle2, XCircle, AlertTriangle, Download, Save, Sparkles, Plus, ScanText, Database, ShoppingCart,
} from "lucide-react";
import Sidebar from "../components/Sidebar";
import DictationInput from "../components/DictationInput";
import { lireSession, estAdminEntreprise } from "../api/session";
import {
  deposerDocument, listerDocuments, detailDocument, corrigerDocument, validerDocument, rejeterDocument,
  champsPersonnalises, telechargerOriginal, propositionIntegration, integrerDocument,
} from "../api/idpApi";
import "./idp.css";

const ACCEPT = ".pdf,.docx,.xlsx,.ods,.pptx,.csv,.xml,.json,.txt,.jpg,.jpeg,.png,.tif,.tiff,.bmp,.gif";
const MODULES = {
  documents: "Documents", ressources_humaines: "Ressources humaines", achats: "Achats", ventes: "Ventes",
  comptabilite_fiscalite: "Comptabilité et fiscalité", projets: "Gestion de projets",
  administration: "Gestion administrative", autre: "Autre",
};
const TYPES = ["texte", "nombre", "montant", "date", "booleen", "liste"];
const STATUTS = { brouillon: "À vérifier", valide: "Validé", rejete: "Rejeté" };
const VERIF = {
  source_trouvee: { texte: "Source trouvée", classe: "ok" },
  valeur_trouvee: { texte: "Valeur trouvée", classe: "ok" },
  a_verifier: { texte: "À vérifier", classe: "alerte" },
  corrige: { texte: "Corrigé", classe: "neutre" },
};
const CHAMPS_STANDARD = [
  ["numero", "Numéro"], ["date", "Date"], ["date_echeance", "Échéance"], ["devise", "Devise"],
  ["total_ht", "Total HT"], ["total_tva", "Total TVA"], ["total_ttc", "Total TTC"], ["taux_tva", "Taux TVA (%)"],
];

const STATUTS_ACHAT = { facture: "Facturé", commande: "Commandé", en_cours: "En cours (devis)" };

const texteValeur = (valeur) => (Array.isArray(valeur) ? valeur.join("; ") : valeur === true ? "oui" : valeur === false ? "non" : valeur ?? "");

export default function Idp() {
  const admin = useMemo(() => estAdminEntreprise(lireSession()), []);
  const [documents, setDocuments] = useState([]);
  const [filtre, setFiltre] = useState("");
  const [courant, setCourant] = useState(null);       // détail du document ouvert
  const [standard, setStandard] = useState({});       // champs standard édités
  const [libre, setLibre] = useState(null);           // structure libre éditée
  const [fournisseur, setFournisseur] = useState("");
  const [modifie, setModifie] = useState(false);
  const [occupe, setOccupe] = useState(false);
  const [survol, setSurvol] = useState(false);
  const [message, setMessage] = useState("");
  const [erreur, setErreur] = useState("");
  const [registre, setRegistre] = useState(null);
  const entree = useRef(null);
  const [secondes, setSecondes] = useState(0);        // durée de l'analyse en cours
  const navigate = useNavigate();
  const [proposition, setProposition] = useState(null);   // intégration possible dans Achats (document validé)
  const [integrationOuverte, setIntegrationOuverte] = useState(false);
  const [choixFournisseur, setChoixFournisseur] = useState({ mode: "existant", id: "" });
  const [choixLignes, setChoixLignes] = useState({});     // index de ligne -> { mode, produit_id }

  useEffect(() => {
    if (!occupe) { setSecondes(0); return undefined; }
    const minuteur = setInterval(() => setSecondes((n) => n + 1), 1000);
    return () => clearInterval(minuteur);
  }, [occupe]);

  const charger = useCallback(async () => {
    try { setDocuments(await listerDocuments(filtre)); } catch (e) { setErreur(e.message); }
  }, [filtre]);
  useEffect(() => { charger(); }, [charger]);

  useEffect(() => {
    let annule = false;
    setProposition(null);
    if (courant?.statut === "valide") {
      propositionIntegration(courant.id).then((p) => { if (!annule) setProposition(p); }).catch(() => {});
    }
    return () => { annule = true; };
  }, [courant?.id, courant?.statut]);

  const ouvrir = useCallback((doc) => {
    setCourant(doc);
    const donnees = doc.donnees || {};
    setStandard(Object.fromEntries(CHAMPS_STANDARD.map(([cle]) => [cle, donnees[cle] ?? ""])));
    setFournisseur(donnees.fournisseur?.nom ?? "");
    setLibre(donnees.structure_libre ? JSON.parse(JSON.stringify(donnees.structure_libre)) : null);
    setModifie(false);
  }, []);

  const selectionner = async (id) => {
    setErreur(""); setMessage("");
    try { ouvrir(await detailDocument(id)); } catch (e) { setErreur(e.message); }
  };

  async function deposer(fichier) {
    if (!fichier) return;
    setOccupe(true); setErreur(""); setMessage("");
    try {
      const depot = await deposerDocument(fichier);
      await charger();
      ouvrir(await detailDocument(depot.id));
      setMessage(depot.doublons?.length
        ? `Document analysé. Attention : ${depot.doublons.length} doublon(s) possible(s) détecté(s).`
        : "Document analysé. Vérifiez les informations avant validation.");
    } catch (e) { setErreur(e.message); } finally { setOccupe(false); if (entree.current) entree.current.value = ""; }
  }

  const modifierStandard = (cle, valeur) => { setStandard((s) => ({ ...s, [cle]: valeur })); setModifie(true); };
  const modifierChamp = (iSection, iChamp, valeur) => {
    setLibre((l) => {
      const copie = JSON.parse(JSON.stringify(l));
      const champ = copie.sections[iSection].champs[iChamp];
      champ.valeur = champ.type === "liste" ? String(valeur).split(";").map((x) => x.trim()).filter(Boolean) : valeur;
      return copie;
    });
    setModifie(true);
  };
  const ajouterChamp = (iSection) => {
    const libelle = window.prompt("Nom du nouveau champ (ex. Date de signature) :");
    if (!libelle || !libelle.trim()) return;
    setLibre((l) => {
      const copie = JSON.parse(JSON.stringify(l));
      copie.sections[iSection].champs.push({
        cle: libelle.trim().toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || `champ_${Date.now()}`,
        libelle: libelle.trim(), type: "texte", valeur: "", source: null, verification: "corrige", nouveau: true, origine: "utilisateur",
      });
      return copie;
    });
    setModifie(true);
  };
  const changerModule = (valeur) => { setLibre((l) => ({ ...l, module_suggere: valeur })); setModifie(true); };

  async function enregistrer() {
    setOccupe(true); setErreur(""); setMessage("");
    try {
      const corrections = { ...standard };
      for (const cle of Object.keys(corrections)) if (corrections[cle] === "") corrections[cle] = null;
      corrections.fournisseur = { nom: fournisseur || null };
      if (libre) {
        // Les champs laissés vides sont retirés : le serveur ignore de toute façon les champs sans valeur.
        corrections.structure_libre = libre;
      }
      const reponse = await corrigerDocument(courant.id, corrections);
      ouvrir({ ...courant, donnees: reponse.donnees, anomalies: reponse.anomalies });
      await charger();
      setMessage("Corrections enregistrées, contrôles refaits.");
    } catch (e) { setErreur(e.message); } finally { setOccupe(false); }
  }

  async function valider() {
    if (modifie && !window.confirm("Des modifications ne sont pas enregistrées. Valider quand même la version enregistrée ?")) return;
    setOccupe(true); setErreur(""); setMessage("");
    try {
      const retour = await validerDocument(courant.id);
      ouvrir(await detailDocument(courant.id)); await charger();
      setMessage(retour.champs_personnalises?.length
        ? `Document validé. ${retour.champs_personnalises.length} nouveau(x) champ(s) ajouté(s) au vocabulaire de l'entreprise.`
        : "Document validé.");
    } catch (e) { setErreur(e.message); } finally { setOccupe(false); }
  }

  async function rejeter() {
    const motif = window.prompt("Motif du rejet :");
    if (!motif || !motif.trim()) return;
    setOccupe(true); setErreur("");
    try { await rejeterDocument(courant.id, motif.trim()); ouvrir(await detailDocument(courant.id)); await charger(); setMessage("Document rejeté."); }
    catch (e) { setErreur(e.message); } finally { setOccupe(false); }
  }

  function ouvrirIntegration() {
    const f = proposition.fournisseur;
    setChoixFournisseur(f.statut === "a_creer" ? { mode: f.nom_document ? "creer" : "existant", id: "" } : { mode: "existant", id: String(f.id) });
    setChoixLignes(Object.fromEntries(proposition.lignes.map((l) => [l.index,
      l.produit.statut === "a_creer" ? { mode: "creer", produit_id: "" } : { mode: "existant", produit_id: String(l.produit.id) }])));
    setErreur(""); setIntegrationOuverte(true);
  }

  const integrationComplete = proposition?.eligible
    && (choixFournisseur.mode === "creer" ? Boolean(proposition.fournisseur.nom_document) : Boolean(choixFournisseur.id))
    && proposition.lignes.every((l) => l.problemes.length === 0
      && (choixLignes[l.index]?.mode === "creer" || Boolean(choixLignes[l.index]?.produit_id)));

  async function confirmerIntegration() {
    setOccupe(true); setErreur("");
    try {
      const choix = {
        fournisseur_id: choixFournisseur.mode === "existant" ? Number(choixFournisseur.id) : null,
        creer_fournisseur: choixFournisseur.mode === "creer",
        lignes: proposition.lignes.map((l) => (choixLignes[l.index]?.mode === "creer"
          ? { index: l.index, creer: true } : { index: l.index, produit_id: Number(choixLignes[l.index].produit_id) })),
      };
      const retour = await integrerDocument(courant.id, choix);
      setIntegrationOuverte(false);
      setMessage(`${retour.message} Total TTC : ${retour.montant_ttc}${retour.produits_crees ? ` · ${retour.produits_crees} produit(s) créé(s)` : ""}.`);
      setProposition(await propositionIntegration(courant.id));
      ouvrir(await detailDocument(courant.id));
    } catch (e) { setErreur(e.message); } finally { setOccupe(false); }
  }

  async function voirRegistre() {
    try { setRegistre(await champsPersonnalises()); } catch (e) { setErreur(e.message); }
  }

  const editable = courant?.statut === "brouillon";
  const erreurs = (courant?.anomalies || []).filter((a) => a.gravite === "erreur");

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-contenu">
        <header className="app-topbar"><div className="app-topbar__droite"><ScanText size={18} /></div></header>
        <main className="app-main idp-page">
          <div className="achats-entete">
            <div>
              <h1 className="app-main__titre"><ScanText size={22} /> Documents intelligents (IDP)</h1>
              <p className="achats-sous-titre">Importez un document : l'IA le lit (OCR arabe, français, anglais), découvre ses champs, puis vous vérifiez et validez.</p>
            </div>
            <button className="bouton-secondaire-large" onClick={voirRegistre}><Database size={16} /> Champs personnalisés</button>
          </div>

          {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
          {message && <div className="idp-message" role="status">{message}</div>}

          <div
            className={`idp-depot ${survol ? "is-survol" : ""}`}
            onDragOver={(e) => { e.preventDefault(); setSurvol(true); }}
            onDragLeave={() => setSurvol(false)}
            onDrop={(e) => { e.preventDefault(); setSurvol(false); deposer(e.dataTransfer.files?.[0]); }}
          >
            <UploadCloud size={30} />
            <p><strong>Glissez un document ici</strong> ou</p>
            <button className="bouton-principal" disabled={occupe} onClick={() => entree.current?.click()}>
              {occupe ? `Analyse en cours… ${secondes} s` : "Choisir un fichier"}
            </button>
            <input ref={entree} type="file" accept={ACCEPT} hidden onChange={(e) => deposer(e.target.files?.[0])} />
            {occupe && <small role="status">L'IA lit le document, puis découvre ses champs : cela peut prendre une à plusieurs minutes avec un modèle local. Ne fermez pas la page.</small>}
            <small>PDF (numérique ou scanné), Word, Excel (XLSX/ODS), PowerPoint, images JPG/PNG/TIFF, CSV, XML, JSON, texte · 20 Mo maximum.</small>
          </div>

          <div className="idp-grille">
            <section className="idp-liste" aria-label="Documents">
              <div className="idp-liste__tete">
                <h2>Documents</h2>
                <select value={filtre} onChange={(e) => setFiltre(e.target.value)} aria-label="Filtrer par statut">
                  <option value="">Tous</option>
                  {Object.entries(STATUTS).map(([cle, libelle]) => <option key={cle} value={cle}>{libelle}</option>)}
                </select>
              </div>
              {documents.length === 0 && <p className="idp-vide">Aucun document pour le moment.</p>}
              {documents.map((d) => (
                <button key={d.id} className={`idp-ligne ${courant?.id === d.id ? "is-actif" : ""}`} onClick={() => selectionner(d.id)}>
                  <FileText size={18} />
                  <span className="idp-ligne__nom">{d.nom_fichier || `Document ${d.id}`}<small>{new Date(d.depose_le).toLocaleString()}</small></span>
                  {d.nb_erreurs > 0 && <span className="idp-pastille idp-pastille--alerte" title="Erreurs bloquantes">{d.nb_erreurs}</span>}
                  <span className={`idp-statut idp-statut--${d.statut}`}>{STATUTS[d.statut]}</span>
                </button>
              ))}
            </section>

            <section className="idp-detail" aria-live="polite">
              {!courant && <p className="idp-vide">Sélectionnez ou importez un document pour voir les informations extraites.</p>}
              {courant && (
                <>
                  <div className="idp-detail__tete">
                    <div>
                      <h2>{courant.nom_fichier || `Document ${courant.id}`}</h2>
                      <small>
                        {courant.format?.toUpperCase()} · {courant.ocr_utilise ? "lu par OCR" : "texte natif"} · modèle {courant.modele || "?"}
                        {courant.statut === "rejete" && courant.motif_rejet ? ` · motif : ${courant.motif_rejet}` : ""}
                      </small>
                    </div>
                    <span className={`idp-statut idp-statut--${courant.statut}`}>{STATUTS[courant.statut]}</span>
                  </div>

                  {(courant.avertissements || []).map((a, i) => <div key={i} className="idp-alerte"><AlertTriangle size={15} /> {a}</div>)}
                  {(courant.anomalies || []).length > 0 && (
                    <div className="idp-anomalies">
                      <h3>Contrôles de cohérence</h3>
                      {courant.anomalies.map((a, i) => (
                        <div key={i} className={`idp-anomalie idp-anomalie--${a.gravite}`}>
                          {a.gravite === "erreur" ? <XCircle size={15} /> : <AlertTriangle size={15} />}
                          <span>{a.message}{a.attendu ? ` (attendu ${a.attendu}, trouvé ${a.trouve})` : ""}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  <h3>Informations standard</h3>
                  <div className="idp-champs">
                    <div className="idp-champ"><span>Fournisseur / émetteur</span>
                      <DictationInput value={fournisseur} disabled={!editable} onChange={(v) => { setFournisseur(v); setModifie(true); }} /></div>
                    {CHAMPS_STANDARD.map(([cle, libelle]) => (
                      <label key={cle} className="idp-champ"><span>{libelle}</span>
                        <input value={standard[cle] ?? ""} disabled={!editable} onChange={(e) => modifierStandard(cle, e.target.value)} /></label>
                    ))}
                  </div>

                  {libre && (
                    <>
                      <div className="idp-libre__tete">
                        <h3><Sparkles size={16} /> Structure découverte par l'IA</h3>
                        <label className="idp-module">Module proposé
                          <select value={libre.module_suggere || "autre"} disabled={!editable} onChange={(e) => changerModule(e.target.value)}>
                            {Object.entries(MODULES).map(([cle, libelle]) => <option key={cle} value={cle}>{libelle}</option>)}
                          </select></label>
                      </div>
                      {(libre.nature_document || libre.resume) && (
                        <p className="idp-resume"><strong>{libre.nature_document}</strong>{libre.resume ? ` — ${libre.resume}` : ""}</p>
                      )}
                      {libre.sections.map((section, iS) => (
                        <fieldset key={section.cle} className="idp-section">
                          <legend>{section.nom}</legend>
                          {section.champs.map((champ, iC) => {
                            const verif = VERIF[champ.verification] || VERIF.corrige;
                            return (
                              <div key={champ.cle} className="idp-champ">
                                <span>
                                  {champ.libelle}
                                  {champ.nouveau && <em className="idp-badge idp-badge--nouveau">Nouveau champ</em>}
                                  <em className={`idp-badge idp-badge--${verif.classe}`} title={champ.source ? `Extrait du document : « ${champ.source} »` : "Aucune source citée"}>{verif.texte}</em>
                                </span>
                                {champ.type === "texte"
                                  ? <DictationInput value={texteValeur(champ.valeur)} disabled={!editable} onChange={(v) => modifierChamp(iS, iC, v)} />
                                  : <input value={texteValeur(champ.valeur)} disabled={!editable} onChange={(e) => modifierChamp(iS, iC, e.target.value)} />}
                                <small className="idp-type">{champ.type}</small>
                              </div>
                            );
                          })}
                          {editable && <button type="button" className="bouton-mini" onClick={() => ajouterChamp(iS)}><Plus size={13} /> Ajouter un champ</button>}
                        </fieldset>
                      ))}
                      {libre.tableaux.map((t) => (
                        <div key={t.cle} className="idp-tableau">
                          <h4>{t.nom}</h4>
                          <div className="idp-tableau__defilement">
                            <table><thead><tr>{t.colonnes.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
                              <tbody>{t.lignes.map((l, i) => <tr key={i}>{l.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table>
                          </div>
                        </div>
                      ))}
                      {libre.relations.length > 0 && (
                        <div className="idp-relations"><h4>Relations identifiées</h4>
                          <ul>{libre.relations.map((r, i) => <li key={i}><code>{r.de}</code> — {r.nature} → <code>{r.vers}</code></li>)}</ul></div>
                      )}
                    </>
                  )}

                  {courant.statut === "valide" && proposition?.deja_integre && (
                    <div className="idp-integre"><CheckCircle2 size={16} /> Intégré dans Achats : <strong>{proposition.deja_integre.numero}</strong>
                      <button type="button" className="bouton-mini" onClick={() => navigate("/achats")}>Ouvrir Achats</button></div>
                  )}
                  {courant.statut === "valide" && proposition?.eligible && (
                    <div className="idp-integration">
                      <div><strong>Prêt pour Achats.</strong> Le fournisseur et les produits sont rapprochés automatiquement ; vous confirmez avant toute création.</div>
                      <button type="button" className="bouton-principal" onClick={ouvrirIntegration}><ShoppingCart size={16} /> Intégrer dans Achats</button>
                    </div>
                  )}
                  {courant.statut === "valide" && proposition && !proposition.eligible && !proposition.deja_integre && proposition.raison && (
                    <p className="idp-vide">Intégration dans Achats impossible : {proposition.raison}</p>
                  )}
                  <div className="idp-actions">
                    <button className="bouton-secondaire-large" onClick={() => telechargerOriginal(courant.id, courant.nom_fichier).catch((e) => setErreur(e.message))}>
                      <Download size={16} /> Document original
                    </button>
                    {editable && <button className="bouton-secondaire-large" disabled={occupe || !modifie} onClick={enregistrer}><Save size={16} /> Enregistrer les corrections</button>}
                    {editable && admin && <button className="bouton-secondaire-large idp-rejet" disabled={occupe} onClick={rejeter}><XCircle size={16} /> Rejeter</button>}
                    {editable && admin && <button className="bouton-principal" disabled={occupe || erreurs.length > 0} onClick={valider}
                      title={erreurs.length ? "Corrigez d'abord les erreurs bloquantes" : ""}><CheckCircle2 size={16} /> Valider</button>}
                  </div>
                  {editable && !admin && <p className="idp-vide">La validation est réservée à l'administrateur de l'entreprise.</p>}
                  {(courant.evenements || []).length > 0 && (
                    <details className="idp-historique"><summary>Historique et traçabilité</summary>
                      <ul>{courant.evenements.map((e, i) => <li key={i}>{new Date(e.date).toLocaleString()} — {e.evenement}{e.acteur ? ` (utilisateur ${e.acteur})` : ""}</li>)}</ul></details>
                  )}
                </>
              )}
            </section>
          </div>

          {integrationOuverte && proposition?.eligible && (
            <div className="clients-overlay" role="dialog" aria-modal="true" aria-labelledby="idp-integ-titre">
              <div className="clients-fiche idp-modale">
                <h2 id="idp-integ-titre">Intégrer dans Achats</h2>
                <p className="idp-vide">Document « {courant.nom_fichier} » → bon d'achat au statut <strong>{STATUTS_ACHAT[proposition.statut_cible]}</strong>.
                  Le stock n'est pas modifié : il l'est par la réception.</p>
                {erreur && <div className="erreur-message" role="alert">{erreur}</div>}

                <h3>Fournisseur</h3>
                <p className="idp-vide">Dans le document : <strong>{proposition.fournisseur.nom_document || "non précisé"}</strong></p>
                <div className="idp-choix">
                  <label><input type="radio" checked={choixFournisseur.mode === "existant"} onChange={() => setChoixFournisseur((c) => ({ ...c, mode: "existant" }))} /> Fournisseur existant</label>
                  <select value={choixFournisseur.id} disabled={choixFournisseur.mode !== "existant"} onChange={(e) => setChoixFournisseur({ mode: "existant", id: e.target.value })}>
                    <option value="">— choisir —</option>
                    {proposition.fournisseurs.map((f) => <option key={f.id} value={f.id}>{f.nom}</option>)}
                  </select>
                  {proposition.fournisseur.statut === "suggere" && <small className="idp-badge idp-badge--alerte">Correspondance approchée : à vérifier</small>}
                </div>
                <div className="idp-choix">
                  <label><input type="radio" disabled={!proposition.fournisseur.nom_document} checked={choixFournisseur.mode === "creer"} onChange={() => setChoixFournisseur({ mode: "creer", id: "" })} /> Créer « {proposition.fournisseur.nom_document || "—"} »</label>
                </div>

                <h3>Lignes</h3>
                <div className="idp-tableau__defilement">
                  <table className="idp-registre">
                    <thead><tr><th>Désignation</th><th>Qté</th><th>Prix</th><th>Produit</th></tr></thead>
                    <tbody>
                      {proposition.lignes.map((l) => (
                        <tr key={l.index}>
                          <td>{l.designation}{l.problemes.map((p, i) => <div key={i} className="idp-anomalie idp-anomalie--erreur">{p}</div>)}</td>
                          <td>{l.quantite ?? "?"}</td><td>{l.prix_unitaire ?? "?"}</td>
                          <td>
                            <select value={choixLignes[l.index]?.mode === "creer" ? "creer" : choixLignes[l.index]?.produit_id || ""}
                              onChange={(e) => setChoixLignes((c) => ({ ...c, [l.index]: e.target.value === "creer" ? { mode: "creer", produit_id: "" } : { mode: "existant", produit_id: e.target.value } }))}>
                              <option value="">— choisir —</option>
                              <option value="creer">➕ Créer un nouveau produit</option>
                              {proposition.produits.map((p) => <option key={p.id} value={p.id}>{p.reference} — {p.nom}</option>)}
                            </select>
                            {l.produit.statut === "suggere" && <small className="idp-badge idp-badge--alerte">Suggestion : à vérifier</small>}
                            {l.produit.statut === "trouve" && <small className="idp-badge idp-badge--ok">Trouvé</small>}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                <div className="idp-actions">
                  <button className="bouton-secondaire-large" onClick={() => setIntegrationOuverte(false)}>Annuler</button>
                  <button className="bouton-principal" disabled={occupe || !integrationComplete} onClick={confirmerIntegration}>
                    <CheckCircle2 size={16} /> {occupe ? "Création…" : "Confirmer l'intégration"}
                  </button>
                </div>
              </div>
            </div>
          )}

          {registre && (
            <div className="clients-overlay" role="dialog" aria-modal="true" onClick={() => setRegistre(null)}>
              <div className="clients-fiche" onClick={(e) => e.stopPropagation()}>
                <h2>Champs personnalisés de l'entreprise</h2>
                <p className="idp-vide">Champs découverts par l'IA dans des documents validés ; ils sont réutilisés pour les prochains documents.</p>
                {registre.length === 0 ? <p>Aucun champ pour l'instant.</p> : (
                  <table className="idp-registre"><thead><tr><th>Champ</th><th>Type</th><th>Section</th><th>Module</th><th>Utilisé</th></tr></thead>
                    <tbody>{registre.map((c) => <tr key={c.cle}><td>{c.libelle}<br /><code>{c.cle}</code></td><td>{c.type}</td><td>{c.section}</td><td>{MODULES[c.module] || c.module}</td><td>{c.occurrences}×</td></tr>)}</tbody></table>
                )}
                <button className="bouton-secondaire-large" onClick={() => setRegistre(null)}>Fermer</button>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
