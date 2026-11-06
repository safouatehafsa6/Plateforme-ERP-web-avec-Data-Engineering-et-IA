import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Search, Plus, Pencil, X, Eye, Mail, Phone, MapPin, UserPlus, AlertTriangle, Archive, RotateCcw, UserCheck, Bell,
} from "lucide-react";
import Sidebar from "../components/Sidebar";
import SuiviCommercial from "../components/SuiviCommercial";
import ArchivageDialog from "../components/ArchivageDialog";
import { api } from "../api/http";
import {
  STATUTS, SOURCES, actionsDisponibles, analyserConflitDoublon, formaterDateHeure, libelleDoublon,
  normaliserProspect, transitionsPossibles, validerChangementStatut, validerProspect,
} from "../validation/prospect";

const VIDE = { nom: "", contact: "", email: "", telephone: "", adresse: "", source: "autre", besoin: "" };

function Doublons({ conflit, onForcer, onRattacher, libelleForcer = "Enregistrer quand même" }) {
  if (!conflit) return null;
  return (
    <div className="clients-warning prospects-doublons" role="alert">
      <AlertTriangle size={18} />
      <div>
        <strong>{conflit.message}</strong>
        <ul>
          {conflit.doublons.map((d) => (
            <li key={`${d.entite}-${d.id}`}>
              {libelleDoublon(d)}
              {onRattacher && d.entite === "client" && !d.archive && (
                <button type="button" className="prospects-lien" onClick={() => onRattacher(d)}>Rattacher à ce client</button>
              )}
            </li>
          ))}
        </ul>
        {conflit.archives.length > 0 && <p>Une fiche archivée correspond : réactivez-la plutôt que d'en créer une nouvelle.</p>}
        {conflit.confirmable && onForcer
          ? <button type="button" className="bouton-secondaire-large" onClick={onForcer}>{libelleForcer}</button>
          : !conflit.confirmable && <p>Ce doublon ne peut pas être contourné : corrigez les coordonnées ou utilisez la fiche existante.</p>}
      </div>
    </div>
  );
}

function ProspectForm({ initial, onClose, onSaved }) {
  const [form, setForm] = useState(() => ({ ...VIDE, ...normaliserProspect(initial || VIDE) }));
  const [erreur, setErreur] = useState("");
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState({});
  const [tentative, setTentative] = useState(false);
  const [conflit, setConflit] = useState(null);
  const [apercu, setApercu] = useState(null);
  const erreurs = validerProspect(form);
  const minuteur = useRef(null);

  // Contrôle en direct des doublons pendant la saisie (indicatif ; le serveur recontrôle toujours à l'enregistrement).
  useEffect(() => {
    clearTimeout(minuteur.current);
    if (!form.email && !form.telephone && form.nom.trim().length < 3) { setApercu(null); return undefined; }
    minuteur.current = setTimeout(async () => {
      const params = new URLSearchParams();
      if (form.nom.trim().length >= 3) params.set("nom", form.nom.trim());
      if (form.email && !erreurs.email) params.set("email", form.email.trim());
      if (form.telephone && !erreurs.telephone) params.set("telephone", form.telephone.trim());
      if (initial?.id) params.set("exclure_id", String(initial.id));
      try {
        const r = await api(`/prospects/verification-doublon?${params}`);
        setApercu(r.doublons?.length ? r.doublons : null);
      } catch { setApercu(null); }
    }, 500);
    return () => clearTimeout(minuteur.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.nom, form.email, form.telephone]);

  function change(e) {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
    setErreur(""); setConflit(null);
  }
  const afficher = (champ) => ((touched[champ] || tentative) ? erreurs[champ] : "");
  const blur = (champ) => () => setTouched((t) => ({ ...t, [champ]: true }));

  async function enregistrer(confirmer = false) {
    setTentative(true); setErreur(""); setConflit(null);
    if (Object.keys(erreurs).length) {
      document.getElementById(`prospect-${Object.keys(erreurs)[0] === "moyen_contact" ? "email" : Object.keys(erreurs)[0]}`)?.focus();
      return;
    }
    setSaving(true);
    try {
      await api(initial?.id ? `/prospects/${initial.id}` : "/prospects", {
        method: initial?.id ? "PATCH" : "POST",
        body: JSON.stringify({ ...normaliserProspect(form), confirmer_doublon: confirmer }),
      });
      onSaved();
    } catch (err) {
      const c = analyserConflitDoublon(err);
      if (c) setConflit(c); else setErreur(err.message);
    } finally { setSaving(false); }
  }

  const doublonsApercu = apercu && !conflit ? { message: "Des fiches existantes ressemblent à cette saisie.", doublons: apercu, confirmable: true, archives: apercu.filter((d) => d.archive) } : null;

  return (
    <form className="panel achats-form clients-form" onSubmit={(e) => { e.preventDefault(); enregistrer(false); }} noValidate>
      <div className="achats-form__entete">
        <h3>{initial?.id ? "Modifier le prospect" : "Nouveau prospect"}</h3>
        <button type="button" className="achats-icon-btn" onClick={onClose} aria-label="Fermer le formulaire"><X size={18} /></button>
      </div>
      {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
      <Doublons conflit={conflit} onForcer={() => enregistrer(true)} />
      {doublonsApercu && <Doublons conflit={doublonsApercu} />}
      {tentative && erreurs.moyen_contact && <div className="erreur-message" role="alert">{erreurs.moyen_contact}</div>}

      <div className="achats-form-grid">
        <div className="champ">
          <label htmlFor="prospect-nom">Nom / société *</label>
          <input id="prospect-nom" name="nom" value={form.nom} onChange={change} onBlur={blur("nom")} maxLength={150} aria-invalid={Boolean(afficher("nom"))} />
          {afficher("nom") && <p className="champ-erreur">{erreurs.nom}</p>}
        </div>
        <div className="champ">
          <label htmlFor="prospect-contact">Personne à contacter</label>
          <input id="prospect-contact" name="contact" value={form.contact ?? ""} onChange={change} onBlur={blur("contact")} maxLength={150} />
          {afficher("contact") && <p className="champ-erreur">{erreurs.contact}</p>}
        </div>
      </div>
      <div className="achats-form-grid">
        <div className="champ">
          <label htmlFor="prospect-email">E-mail</label>
          <input id="prospect-email" type="email" name="email" value={form.email ?? ""} onChange={change} onBlur={blur("email")} maxLength={150} placeholder="nom@entreprise.com" aria-invalid={Boolean(afficher("email"))} />
          {afficher("email") && <p className="champ-erreur">{erreurs.email}</p>}
        </div>
        <div className="champ">
          <label htmlFor="prospect-telephone">Téléphone</label>
          <input id="prospect-telephone" type="tel" name="telephone" value={form.telephone ?? ""} onChange={change} onBlur={blur("telephone")} maxLength={30} placeholder="+216 12 345 678" aria-invalid={Boolean(afficher("telephone"))} />
          {afficher("telephone") ? <p className="champ-erreur">{erreurs.telephone}</p> : <p className="champ-aide">E-mail ou téléphone obligatoire (au moins un).</p>}
        </div>
      </div>
      <div className="achats-form-grid">
        <div className="champ">
          <label htmlFor="prospect-source">Origine du prospect</label>
          <select id="prospect-source" name="source" value={form.source} onChange={change}>
            {Object.entries(SOURCES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </div>
        <div className="champ">
          <label htmlFor="prospect-adresse">Adresse</label>
          <input id="prospect-adresse" name="adresse" value={form.adresse ?? ""} onChange={change} onBlur={blur("adresse")} maxLength={1000} />
          {afficher("adresse") && <p className="champ-erreur">{erreurs.adresse}</p>}
        </div>
      </div>
      <div className="champ">
        <label htmlFor="prospect-besoin">Besoin exprimé</label>
        <textarea id="prospect-besoin" name="besoin" rows={3} value={form.besoin ?? ""} onChange={change} onBlur={blur("besoin")} maxLength={2000} />
        {afficher("besoin") && <p className="champ-erreur">{erreurs.besoin}</p>}
      </div>
      <div className="achats-form__pied">
        <span className="achats-muted">Les doublons (prospects et clients) sont contrôlés avant enregistrement.</span>
        <div>
          <button type="button" className="bouton-secondaire-large" onClick={onClose} disabled={saving}>Annuler</button>
          <button className="bouton-principal achats-btn-auto" disabled={saving}>{saving ? "Vérification…" : "Enregistrer"}</button>
        </div>
      </div>
    </form>
  );
}

function BadgeStatut({ prospect }) {
  return (
    <>
      <span className={`achats-badge prospects-statut prospects-statut--${prospect.statut}`}>{STATUTS[prospect.statut] ?? prospect.statut}</span>
      {prospect.archive && <span className="achats-badge prospects-statut--archive">Archivé</span>}
    </>
  );
}

function FicheProspect({ id, droits, onClose, onModifier, onChange }) {
  const [prospect, setProspect] = useState(null);
  const [historique, setHistorique] = useState([]);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");
  const [statut, setStatut] = useState({ statut: "", commentaire: "" });
  const [erreursStatut, setErreursStatut] = useState({});
  const [conflitConversion, setConflitConversion] = useState(null);
  const [archivage, setArchivage] = useState(false);

  const charger = useCallback(async () => {
    try {
      const [p, h] = await Promise.all([api(`/prospects/${id}`), api(`/prospects/${id}/historique`)]);
      setProspect(p); setHistorique(h.historique || []);
    } catch (e) { setErreur(e.message); }
  }, [id]);
  useEffect(() => { charger(); }, [charger]);

  const actions = actionsDisponibles(prospect, droits);

  async function executer(fn, succes) {
    setErreur(""); setMessage("");
    try { const r = await fn(); setMessage(succes ?? r?.message ?? ""); await charger(); onChange(); return r; }
    catch (e) { setErreur(e.message); return null; }
  }

  async function changerStatut(e) {
    e.preventDefault();
    const problemes = validerChangementStatut(statut);
    setErreursStatut(problemes);
    if (Object.keys(problemes).length) return;
    const r = await executer(() => api(`/prospects/${id}/statut`, { method: "POST", body: JSON.stringify({ statut: statut.statut, commentaire: statut.commentaire.trim() || null }) }));
    if (r) setStatut({ statut: "", commentaire: "" });
  }

  async function convertir(options = {}) {
    setErreur(""); setMessage(""); setConflitConversion(null);
    try {
      const r = await api(`/prospects/${id}/convertir`, { method: "POST", body: JSON.stringify(options) });
      setMessage(r.message); await charger(); onChange();
    } catch (e) {
      const c = analyserConflitDoublon(e);
      if (c) setConflitConversion(c); else setErreur(e.message);
    }
  }

  if (!prospect && !erreur) return null;
  const options = prospect ? transitionsPossibles(prospect.statut) : [];

  return (
    <div className="clients-overlay" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <section className="panel clients-fiche prospects-fiche" role="dialog" aria-modal="true" aria-labelledby="fiche-prospect-titre">
        <div className="clients-fiche__header">
          <div className="clients-avatar"><UserPlus size={24} /></div>
          <div className="clients-fiche__heading">
            <p className="clients-eyebrow">FICHE PROSPECT</p>
            <h2 id="fiche-prospect-titre">{prospect?.nom ?? "Prospect"}</h2>
            {prospect && <p><BadgeStatut prospect={prospect} /> {prospect.contact && <>· {prospect.contact}</>}</p>}
          </div>
          <button type="button" className="achats-icon-btn" onClick={onClose} aria-label="Fermer la fiche"><X size={18} /></button>
        </div>
        {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
        {message && <div className="prospects-succes" role="status">{message}</div>}
        {prospect && (
          <>
            {prospect.archive && <div className="clients-warning"><Archive size={18} /><span>Archivé le {formaterDateHeure(prospect.archive_le)} — {prospect.archive_motif}. La fiche est en lecture seule.</span></div>}
            {prospect.client_id && <div className="prospects-succes">Converti en client : <strong>{prospect.client_nom}</strong> (le suivi se poursuit sur la fiche client).</div>}
            <div className="clients-fiche__grid">
              <div className="clients-info-item"><Mail size={18} /><div><span>E-mail</span><strong>{prospect.email || "Non renseigné"}</strong></div></div>
              <div className="clients-info-item"><Phone size={18} /><div><span>Téléphone</span><strong>{prospect.telephone || "Non renseigné"}</strong></div></div>
              <div className="clients-info-item"><MapPin size={18} /><div><span>Adresse</span><strong>{prospect.adresse || "Non renseignée"}</strong></div></div>
              <div className="clients-info-item"><UserCheck size={18} /><div><span>Responsable</span><strong>{prospect.responsable_nom || "Non attribué"}</strong></div></div>
              <div className="clients-info-item"><Bell size={18} /><div><span>Prochaine relance</span><strong className={prospect.relance_en_retard ? "prospects-retard" : ""}>{prospect.prochaine_relance_le ? new Date(`${prospect.prochaine_relance_le}T00:00:00`).toLocaleDateString("fr-FR") : "—"}{prospect.relance_en_retard ? " (en retard)" : ""}</strong></div></div>
              <div className="clients-info-item"><Eye size={18} /><div><span>Origine</span><strong>{SOURCES[prospect.source] ?? prospect.source}</strong></div></div>
              {prospect.besoin && <div className="clients-info-item clients-info-item--wide"><Pencil size={18} /><div><span>Besoin exprimé</span><strong>{prospect.besoin}</strong></div></div>}
            </div>

            {actions.changerStatut && options.length > 0 && (
              <form className="prospects-statut-form" onSubmit={changerStatut} noValidate>
                <label htmlFor="nouveau-statut">Changer le statut</label>
                <select id="nouveau-statut" value={statut.statut} onChange={(e) => { setStatut((s) => ({ ...s, statut: e.target.value })); setErreursStatut({}); }}>
                  <option value="">— Choisir —</option>
                  {options.map((s) => <option key={s} value={s}>{STATUTS[s]}</option>)}
                </select>
                <input value={statut.commentaire} onChange={(e) => { setStatut((s) => ({ ...s, commentaire: e.target.value })); setErreursStatut({}); }} placeholder={statut.statut === "perdu" ? "Motif de la perte (obligatoire)" : "Commentaire (facultatif)"} maxLength={2000} aria-label="Commentaire" />
                <button className="bouton-secondaire-large">Appliquer</button>
                {(erreursStatut.statut || erreursStatut.commentaire) && <p className="champ-erreur">{erreursStatut.statut || erreursStatut.commentaire}</p>}
              </form>
            )}

            <Doublons conflit={conflitConversion} libelleForcer="Convertir quand même"
              onForcer={() => convertir({ confirmer_doublon: true })}
              onRattacher={(client) => convertir({ client_existant_id: client.id })} />

            <div className="clients-fiche__footer prospects-actions">
              {actions.modifier && <button type="button" className="bouton-secondaire-large" onClick={() => onModifier(prospect)}><Pencil size={15} /> Modifier</button>}
              {actions.archiver && <button type="button" className="bouton-secondaire-large" onClick={() => setArchivage(true)}><Archive size={15} /> Archiver</button>}
              {actions.reactiver && <button type="button" className="bouton-principal achats-btn-auto" onClick={() => executer(() => api(`/prospects/${id}/reactiver`, { method: "POST" }))}><RotateCcw size={15} /> Réactiver</button>}
              {actions.convertir && <button type="button" className="bouton-principal achats-btn-auto" onClick={() => convertir({})}><UserCheck size={15} /> Convertir en client</button>}
            </div>

            <SuiviCommercial historique={historique} avecRelance peutAjouter={actions.ajouterSuivi}
              onAjouter={async (payload) => { await api(`/prospects/${id}/suivis`, { method: "POST", body: JSON.stringify(payload) }); setMessage("Suivi enregistré."); await charger(); onChange(); }} />
          </>
        )}
      </section>
      {archivage && (
        <ArchivageDialog titre="Archiver le prospect" onClose={() => setArchivage(false)}
          onConfirmer={async (motif) => { await api(`/prospects/${id}/archiver`, { method: "POST", body: JSON.stringify({ motif }) }); setArchivage(false); setMessage("Prospect archivé."); await charger(); onChange(); }} />
      )}
    </div>
  );
}

export default function Prospects() {
  const [items, setItems] = useState([]);
  const [droits, setDroits] = useState([]);
  const [recherche, setRecherche] = useState("");
  const [filtreStatut, setFiltreStatut] = useState("");
  const [archives, setArchives] = useState("actifs");
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [form, setForm] = useState(null);
  const [ficheId, setFicheId] = useState(null);

  const charger = useCallback(async () => {
    setChargement(true); setErreur("");
    try {
      const params = new URLSearchParams({ archives });
      if (filtreStatut) params.set("statut", filtreStatut);
      const r = await api(`/prospects?${params}`);
      setItems(r.prospects || []);
    } catch (e) { setErreur(e.message); } finally { setChargement(false); }
  }, [archives, filtreStatut]);

  useEffect(() => { charger(); }, [charger]);
  useEffect(() => { api("/prospects/permissions").then((r) => setDroits(r.actions || [])).catch(() => setDroits([])); }, []);

  const filtres = useMemo(() => {
    const q = recherche.trim().toLowerCase();
    return q ? items.filter((p) => `${p.nom} ${p.contact || ""} ${p.email || ""} ${p.telephone || ""}`.toLowerCase().includes(q)) : items;
  }, [items, recherche]);

  const peutCreer = droits.includes("creer");

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-contenu">
        <header className="app-topbar">
          <div className="app-topbar__recherche"><Search size={16} /><input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Rechercher un prospect" aria-label="Rechercher un prospect" /></div>
          <div className="app-topbar__droite"><UserPlus size={18} /></div>
        </header>
        <main className="app-main">
          <div className="achats-entete">
            <div><h1 className="app-main__titre">Prospects</h1><p className="achats-sous-titre">Suivi commercial avant conversion en client, avec historique daté.</p></div>
            {peutCreer && <button className="bouton-principal achats-btn-auto" onClick={() => setForm({})}><Plus size={16} /> Nouveau prospect</button>}
          </div>
          {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
          {form && <ProspectForm key={form.id || "nouveau"} initial={form.id ? form : null} onClose={() => setForm(null)} onSaved={() => { setForm(null); setFicheId(null); charger(); }} />}

          <div className="prospects-filtres">
            <label>Statut
              <select value={filtreStatut} onChange={(e) => setFiltreStatut(e.target.value)}>
                <option value="">Tous</option>
                {Object.entries(STATUTS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </label>
            <label>Affichage
              <select value={archives} onChange={(e) => setArchives(e.target.value)}>
                <option value="actifs">Prospects actifs</option>
                <option value="archives">Archivés</option>
                <option value="tous">Tous</option>
              </select>
            </label>
          </div>

          {chargement ? <p>Chargement…</p> : (
            <div className="table-module achats-table">
              <table>
                <thead><tr><th>Prospect</th><th>Contact</th><th>Origine</th><th>Statut</th><th>Responsable</th><th>Relance</th><th>Actions</th></tr></thead>
                <tbody>
                  {filtres.map((p) => (
                    <tr key={p.id} className={p.archive ? "prospects-ligne--archive" : ""}>
                      <td><strong>{p.nom}</strong>{p.contact && <div className="achats-muted">{p.contact}</div>}</td>
                      <td>{p.email || "—"}<div className="achats-muted">{p.telephone || ""}</div></td>
                      <td>{SOURCES[p.source] ?? p.source}</td>
                      <td><BadgeStatut prospect={p} /></td>
                      <td>{p.responsable_nom || "—"}</td>
                      <td className={p.relance_en_retard ? "prospects-retard" : ""}>{p.prochaine_relance_le ? new Date(`${p.prochaine_relance_le}T00:00:00`).toLocaleDateString("fr-FR") : "—"}</td>
                      <td><div className="achats-actions clients-row-actions">
                        <button type="button" onClick={() => setFicheId(p.id)}><Eye size={14} /> Fiche</button>
                        {actionsDisponibles(p, droits).modifier && <button type="button" onClick={() => setForm(p)}><Pencil size={14} /> Modifier</button>}
                      </div></td>
                    </tr>
                  ))}
                  {filtres.length === 0 && <tr><td colSpan="7">Aucun prospect.</td></tr>}
                </tbody>
              </table>
            </div>
          )}
        </main>
      </div>
      {ficheId && <FicheProspect id={ficheId} droits={droits} onClose={() => setFicheId(null)} onChange={charger} onModifier={(p) => { setFicheId(null); setForm(p); }} />}
    </div>
  );
}
