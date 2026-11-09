import { useCallback, useEffect, useState } from "react";
import { MousePointerClick, Plus, Pencil, Trash2, ChevronUp, ChevronDown, RotateCcw, X, Clock, Search } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { iconeBouton } from "../components/iconesBoutons";
import { api } from "../api/http";
import { lireSession, estSuperAdmin } from "../api/session";
import {
  ACTIONS, ACTIONS_INTEGREES, APPAREILS, AUDIENCES, ICONES, LANGUES, PAGES_CONNUES, POSITIONS, POSITIONS_PRINCIPAL, PROFILS, TAILLES,
  boutonVide, formDepuisBouton, listeDepuisTexte, payloadDepuisForm, resumeVisibilite, validerBouton,
} from "../validation/boutonsFlottants";

const DISPOSITION_POSITIONS = [["haut-gauche", null, "haut-droite"], ["milieu-gauche", null, "milieu-droite"], ["bas-gauche", null, "bas-droite"]];

// Prévient les pages ouvertes (dont celle-ci) qu'elles doivent relire la configuration.
const diffuser = () => window.dispatchEvent(new Event("erp:boutons-refresh"));

function Pastille({ icone, couleur, taille = 18 }) {
  const Icone = iconeBouton(icone);
  return <span className="bfadmin-pastille" style={couleur ? { "--bf-couleur": couleur } : undefined}><Icone size={taille} /></span>;
}

function SelecteurPosition({ valeur, onChange, avecAuto }) {
  return (
    <div>
      <div className="bfadmin-positions" role="group" aria-label="Position">
        {DISPOSITION_POSITIONS.flat().map((cle, i) => cle
          ? <button key={cle} type="button" className="bfadmin-position" aria-pressed={valeur === cle} onClick={() => onChange(cle)} title={POSITIONS[cle]} aria-label={POSITIONS[cle]}>{valeur === cle ? "●" : ""}</button>
          : <span key={`v${i}`} />)}
      </div>
      {avecAuto && <label className="bfadmin-interrupteur" style={{ marginTop: 8 }}><input type="radio" checked={valeur === "auto"} onChange={() => onChange("auto")} /> {POSITIONS_PRINCIPAL.auto}</label>}
    </div>
  );
}

function SelecteurIcone({ valeur, onChange }) {
  return (
    <div className="bfadmin-icones" role="group" aria-label="Icône">
      {ICONES.map((nom) => {
        const Icone = iconeBouton(nom);
        return <button key={nom} type="button" className="bfadmin-icone" aria-pressed={valeur === nom} onClick={() => onChange(nom)} title={nom} aria-label={nom}><Icone size={18} /></button>;
      })}
    </div>
  );
}

function Reglages({ config, onSaved, onErreur }) {
  const [form, setForm] = useState(config);
  const [envoi, setEnvoi] = useState(false);
  useEffect(() => setForm(config), [config]);

  async function enregistrer() {
    setEnvoi(true);
    try {
      const r = await api("/admin/boutons-flottants/config", { method: "PUT", body: JSON.stringify({ actif: form.actif, position: form.position, taille: form.taille, couleur: form.couleur || null, icone: form.icone }) });
      onSaved(r.message); diffuser();
    } catch (e) { onErreur(e.message); } finally { setEnvoi(false); }
  }

  return (
    <section className="panel bfadmin-carte" aria-labelledby="reglages-titre">
      <h3 id="reglages-titre">Bouton d'aide principal</h3>
      <div className="bfadmin-apercu"><Pastille icone={form.icone} couleur={form.couleur} taille={22} /><span>{form.actif ? "Affiché sur toutes les pages" : "Masqué partout (aucun bouton flottant)"}</span></div>
      <label className="bfadmin-interrupteur"><input type="checkbox" checked={form.actif} onChange={(e) => setForm({ ...form, actif: e.target.checked })} /> Activer les boutons flottants</label>
      <div className="champ"><label>Position</label><SelecteurPosition valeur={form.position} onChange={(position) => setForm({ ...form, position })} avecAuto /></div>
      <div className="bfadmin-ligne-flex">
        <div className="champ"><label htmlFor="bf-taille">Taille</label>
          <select id="bf-taille" value={form.taille} onChange={(e) => setForm({ ...form, taille: e.target.value })}>{Object.entries(TAILLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
        <div className="champ"><label htmlFor="bf-couleur">Couleur</label>
          <input id="bf-couleur" type="color" value={form.couleur || "#c98a3a"} onChange={(e) => setForm({ ...form, couleur: e.target.value })} /></div>
        <button type="button" className="bouton-secondaire-large" onClick={() => setForm({ ...form, couleur: null })} disabled={!form.couleur}>Couleur du thème</button>
      </div>
      <div className="champ"><label>Icône</label><SelecteurIcone valeur={form.icone} onChange={(icone) => setForm({ ...form, icone })} /></div>
      <button type="button" className="bouton-principal achats-btn-auto" onClick={enregistrer} disabled={envoi}>{envoi ? "Enregistrement…" : "Enregistrer les réglages"}</button>
    </section>
  );
}

function FormulaireBouton({ initial, options, onClose, onSaved }) {
  const [form, setForm] = useState(() => (initial ? formDepuisBouton(initial) : boutonVide()));
  const [erreurs, setErreurs] = useState({});
  const [tentative, setTentative] = useState(false);
  const [erreurServeur, setErreurServeur] = useState("");
  const [envoi, setEnvoi] = useState(false);
  const modifie = Boolean(initial);
  const integree = ACTIONS_INTEGREES.includes(form.action);

  const maj = (champ, valeur) => {
    setForm((f) => ({ ...f, [champ]: valeur }));
    setErreurServeur("");
  };
  useEffect(() => { setErreurs(validerBouton(form)); }, [form]);
  const vu = (champ) => (tentative ? erreurs[champ] : "");

  async function enregistrer(e) {
    e.preventDefault();
    setTentative(true);
    if (Object.keys(erreurs).length) return;
    setEnvoi(true);
    try {
      const corps = JSON.stringify(payloadDepuisForm(form));
      const r = modifie
        ? await api(`/admin/boutons-flottants/${initial.id}`, { method: "PUT", body: corps })
        : await api("/admin/boutons-flottants", { method: "POST", body: corps });
      onSaved(r.message); diffuser();
    } catch (err) { setErreurServeur(err.message); } finally { setEnvoi(false); }
  }

  const liste = (champ) => (form[champ] || []).join(", ");

  return (
    <div className="clients-overlay" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <form className="panel clients-fiche" role="dialog" aria-modal="true" aria-labelledby="bf-form-titre" onSubmit={enregistrer} noValidate style={{ width: "min(100%, 760px)" }}>
        <div className="achats-form__entete">
          <h3 id="bf-form-titre">{modifie ? `Modifier « ${initial.titres?.fr} »` : "Nouveau bouton"}</h3>
          <button type="button" className="achats-icon-btn" onClick={onClose} aria-label="Fermer"><X size={18} /></button>
        </div>
        {erreurServeur && <div className="erreur-message" role="alert">{erreurServeur}</div>}
        <div className="bfadmin-apercu"><Pastille icone={form.icone} couleur={form.couleur} taille={20} /><strong>{form.titres.fr || "Titre du bouton"}</strong>
          <span className="achats-muted">{ACTIONS[form.action]}</span></div>

        <fieldset className="champ"><legend>Titres *</legend>
          <div className="achats-form-grid">
            {Object.entries(LANGUES).map(([code, nom]) => (
              <div className="champ" key={code}><label htmlFor={`bf-titre-${code}`}>{nom}{code === "fr" ? " *" : ""}</label>
                <input id={`bf-titre-${code}`} dir={code === "ar" ? "rtl" : "ltr"} maxLength={40} value={form.titres[code] || ""} onChange={(e) => maj("titres", { ...form.titres, [code]: e.target.value })} aria-invalid={code === "fr" && Boolean(vu("titre"))} /></div>
            ))}
          </div>
          {vu("titre") && <p className="champ-erreur">{erreurs.titre}</p>}
          {form.action === "theme" && <p className="bfadmin-aide">Le libellé du thème s'adapte automatiquement (clair/sombre) dans la langue de l'utilisateur.</p>}
        </fieldset>

        <div className="champ"><label>Icône</label><SelecteurIcone valeur={form.icone} onChange={(v) => maj("icone", v)} /></div>

        <div className="achats-form-grid">
          <div className="champ"><label htmlFor="bf-action">Action *</label>
            <select id="bf-action" value={form.action} onChange={(e) => setForm((f) => ({ ...f, action: e.target.value, cible: "", nouvel_onglet: false }))}>
              {(options?.actions || Object.keys(ACTIONS)).map((a) => <option key={a} value={a}>{ACTIONS[a] || a}</option>)}</select></div>
          {!integree && (
            <div className="champ"><label htmlFor="bf-cible">{form.action === "route" ? "Page *" : form.action === "whatsapp" ? "Numéro (vide = numéro de la plateforme)" : "Lien *"}</label>
              <input id="bf-cible" value={form.cible} list={form.action === "route" ? "bf-pages" : undefined} onChange={(e) => maj("cible", e.target.value)}
                placeholder={form.action === "route" ? "/clients" : form.action === "whatsapp" ? "+216 12 345 678" : "https://…"} aria-invalid={Boolean(vu("cible"))} />
              {form.action === "route" && <datalist id="bf-pages">{PAGES_CONNUES.map(([chemin, nom]) => <option key={chemin} value={chemin}>{nom}</option>)}</datalist>}
              {vu("cible") && <p className="champ-erreur">{erreurs.cible}</p>}
            </div>
          )}
        </div>
        {(form.action === "url" || form.action === "whatsapp") && <label className="bfadmin-interrupteur"><input type="checkbox" checked={form.nouvel_onglet} onChange={(e) => maj("nouvel_onglet", e.target.checked)} /> Ouvrir dans un nouvel onglet</label>}

        <div className="achats-form-grid">
          <div className="champ"><label>Emplacement</label>
            <div className="bfadmin-choix">
              <label><input type="radio" checked={form.placement === "menu"} onChange={() => maj("placement", "menu")} /> Dans le menu d'aide</label>
              <label><input type="radio" checked={form.placement === "libre"} onChange={() => maj("placement", "libre")} /> Bouton isolé</label>
            </div></div>
          <div className="champ"><label htmlFor="bf-ordre">Ordre d'affichage</label>
            <input id="bf-ordre" type="number" min="0" max="9999" value={form.ordre} onChange={(e) => maj("ordre", e.target.value)} aria-invalid={Boolean(vu("ordre"))} />
            {vu("ordre") ? <p className="champ-erreur">{erreurs.ordre}</p> : <p className="bfadmin-aide">Plus petit = affiché en premier.</p>}</div>
        </div>
        {form.placement === "libre" && (
          <div className="bfadmin-ligne-flex">
            <div className="champ"><label>Position du bouton isolé</label><SelecteurPosition valeur={form.position} onChange={(v) => maj("position", v)} />{vu("position") && <p className="champ-erreur">{erreurs.position}</p>}</div>
            <div className="champ"><label htmlFor="bf-t">Taille</label><select id="bf-t" value={form.taille} onChange={(e) => maj("taille", e.target.value)}>{Object.entries(TAILLES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
          </div>
        )}
        <div className="bfadmin-ligne-flex">
          <div className="champ"><label htmlFor="bf-coul">Couleur</label><input id="bf-coul" type="color" value={form.couleur || "#c98a3a"} onChange={(e) => maj("couleur", e.target.value)} /></div>
          <button type="button" className="bouton-secondaire-large" onClick={() => maj("couleur", "")} disabled={!form.couleur}>Couleur du thème</button>
        </div>

        <fieldset className="champ"><legend>Conditions d'affichage</legend>
          <div className="achats-form-grid">
            <div className="champ"><label htmlFor="bf-aud">Public concerné</label>
              <select id="bf-aud" value={form.audience} onChange={(e) => maj("audience", e.target.value)}>{Object.entries(AUDIENCES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
              {vu("audience") && <p className="champ-erreur">{erreurs.audience}</p>}</div>
            <div className="champ"><label htmlFor="bf-app">Appareil</label>
              <select id="bf-app" value={form.appareils} onChange={(e) => maj("appareils", e.target.value)}>{Object.entries(APPAREILS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></div>
          </div>
          <div className="champ"><label>Profils (aucun coché = tous)</label>
            <div className="bfadmin-choix">{Object.entries(PROFILS).map(([k, v]) => (
              <label key={k}><input type="checkbox" checked={form.profils.includes(k)} onChange={(e) => maj("profils", e.target.checked ? [...form.profils, k] : form.profils.filter((p) => p !== k))} /> {v}</label>))}</div>
            {vu("profils") && <p className="champ-erreur">{erreurs.profils}</p>}</div>
          <div className="achats-form-grid">
            <div className="champ"><label htmlFor="bf-inc">Uniquement sur les pages</label>
              <input id="bf-inc" defaultValue={liste("routes_incluses")} onBlur={(e) => maj("routes_incluses", listeDepuisTexte(e.target.value))} placeholder="/clients, /ventes" />
              {vu("routes_incluses") ? <p className="champ-erreur">{erreurs.routes_incluses}</p> : <p className="bfadmin-aide">Vide = toutes les pages.</p>}</div>
            <div className="champ"><label htmlFor="bf-exc">Sauf sur les pages</label>
              <input id="bf-exc" defaultValue={liste("routes_exclues")} onBlur={(e) => maj("routes_exclues", listeDepuisTexte(e.target.value))} placeholder="/room-live" />
              {vu("routes_exclues") && <p className="champ-erreur">{erreurs.routes_exclues}</p>}</div>
          </div>
          <div className="achats-form-grid">
            <div className="champ"><label htmlFor="bf-du">Affiché à partir du</label><input id="bf-du" type="datetime-local" value={form.affiche_du} onChange={(e) => maj("affiche_du", e.target.value)} /></div>
            <div className="champ"><label htmlFor="bf-au">Jusqu'au</label><input id="bf-au" type="datetime-local" value={form.affiche_jusqu_au} onChange={(e) => maj("affiche_jusqu_au", e.target.value)} /></div>
          </div>
          {vu("dates") && <p className="champ-erreur">{erreurs.dates}</p>}
        </fieldset>

        <label className="bfadmin-interrupteur"><input type="checkbox" checked={form.actif} onChange={(e) => maj("actif", e.target.checked)} /> Bouton actif</label>
        <div className="clients-fiche__footer">
          <button type="button" className="bouton-secondaire-large" onClick={onClose} disabled={envoi}>Annuler</button>
          <button className="bouton-principal achats-btn-auto" disabled={envoi}>{envoi ? "Enregistrement…" : modifie ? "Enregistrer" : "Créer le bouton"}</button>
        </div>
      </form>
    </div>
  );
}

export default function AdminBoutons() {
  const session = lireSession();
  const [donnees, setDonnees] = useState(null);
  const [historique, setHistorique] = useState([]);
  const [erreur, setErreur] = useState("");
  const [info, setInfo] = useState("");
  const [formulaire, setFormulaire] = useState(null);
  const [recherche, setRecherche] = useState("");
  const autorise = estSuperAdmin(session);

  const charger = useCallback(async () => {
    try {
      const [d, h] = await Promise.all([api("/admin/boutons-flottants"), api("/admin/boutons-flottants/historique?limite=15")]);
      setDonnees(d); setHistorique(h.historique || []);
    } catch (e) { setErreur(e.message); }
  }, []);
  useEffect(() => { if (autorise) charger(); }, [autorise, charger]);

  async function executer(fn, succes) {
    setErreur(""); setInfo("");
    try { const r = await fn(); setInfo(succes ?? r?.message ?? ""); diffuser(); await charger(); }
    catch (e) { setErreur(e.message); }
  }

  const deplacer = (index, sens) => {
    const ids = donnees.boutons.map((b) => b.id);
    const cible = index + sens;
    if (cible < 0 || cible >= ids.length) return;
    [ids[index], ids[cible]] = [ids[cible], ids[index]];
    executer(() => api("/admin/boutons-flottants/ordre", { method: "PUT", body: JSON.stringify({ ids }) }));
  };
  const basculer = (b) => executer(() => api(`/admin/boutons-flottants/${b.id}/actif`, { method: "PATCH", body: JSON.stringify({ actif: !b.actif }) }));
  const supprimer = (b) => {
    if (window.confirm(`Supprimer définitivement le bouton « ${b.titres?.fr} » ?`)) executer(() => api(`/admin/boutons-flottants/${b.id}`, { method: "DELETE" }));
  };
  const restaurer = () => {
    if (window.confirm("Remettre les boutons d'origine et les réglages par défaut ? Vos modifications sur les boutons d'origine seront perdues (les boutons ajoutés sont conservés).")) {
      executer(() => api("/admin/boutons-flottants/restaurer", { method: "POST" }));
    }
  };

  const boutons = (donnees?.boutons || []).filter((b) => !recherche.trim() || `${b.titres?.fr} ${b.cle} ${b.action}`.toLowerCase().includes(recherche.trim().toLowerCase()));

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-contenu">
        <header className="app-topbar">
          <div className="app-topbar__recherche"><Search size={16} /><input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Rechercher un bouton" aria-label="Rechercher un bouton" /></div>
          <div className="app-topbar__droite"><MousePointerClick size={18} /></div>
        </header>
        <main className="app-main">
          <div className="achats-entete">
            <div><h1 className="app-main__titre">Boutons flottants</h1><p className="achats-sous-titre">Configurez les boutons d'aide de toute la plateforme, sans toucher au code.</p></div>
            {autorise && <div className="achats-actions-entete">
              <button type="button" className="bouton-secondaire-large" onClick={restaurer}><RotateCcw size={15} /> Restaurer les boutons d'origine</button>{" "}
              <button type="button" className="bouton-principal achats-btn-auto" onClick={() => setFormulaire({})}><Plus size={16} /> Nouveau bouton</button>
            </div>}
          </div>

          {!autorise ? <div className="erreur-message" role="alert">Cette page est réservée au Super Administrateur de la plateforme.</div> : <>
            {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
            {info && <div className="prospects-succes" role="status">{info}</div>}
            {!donnees ? <p>Chargement…</p> : <>
              <div className="bfadmin-grille">
                <Reglages config={donnees.config} onSaved={(m) => { setInfo(m); charger(); }} onErreur={setErreur} />
                <section className="panel bfadmin-carte" aria-labelledby="hist-titre">
                  <h3 id="hist-titre"><Clock size={15} /> Dernières modifications</h3>
                  {historique.length === 0 ? <p className="achats-muted">Aucune modification.</p> : (
                    <ul className="bfadmin-hist">{historique.map((h) => (
                      <li key={h.id}><strong>{h.operation}</strong>{h.cle ? ` · ${h.cle}` : ""} — {new Date(h.le).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })} <span className="achats-muted">{h.par_email}</span></li>))}</ul>)}
                </section>
              </div>

              <div className="table-module achats-table bfadmin-table">
                <table>
                  <thead><tr><th>Ordre</th><th>Bouton</th><th>Action</th><th>Visibilité</th><th>Actif</th><th>Actions</th></tr></thead>
                  <tbody>
                    {boutons.map((b) => {
                      const index = donnees.boutons.findIndex((x) => x.id === b.id);
                      return (
                        <tr key={b.id}>
                          <td><div className="bfadmin-ordre">
                            <button type="button" onClick={() => deplacer(index, -1)} disabled={index === 0 || Boolean(recherche.trim())} aria-label={`Monter ${b.titres?.fr}`}><ChevronUp size={13} /></button>
                            <button type="button" onClick={() => deplacer(index, 1)} disabled={index === donnees.boutons.length - 1 || Boolean(recherche.trim())} aria-label={`Descendre ${b.titres?.fr}`}><ChevronDown size={13} /></button></div></td>
                          <td><div className="bfadmin-ligne-flex" style={{ alignItems: "center" }}><Pastille icone={b.icone} couleur={b.couleur} />
                            <div><strong>{b.titres?.fr}</strong>{b.systeme && <span className="achats-badge" style={{ marginLeft: 6 }}>Origine</span>}
                              <div className="achats-muted">{b.placement === "libre" ? `Isolé · ${POSITIONS[b.position]}` : "Menu d'aide"}</div></div></div></td>
                          <td>{ACTIONS[b.action]}{b.cible && <div className="achats-muted">{b.cible}</div>}</td>
                          <td className="achats-muted">{resumeVisibilite(b)}</td>
                          <td><label className="bfadmin-interrupteur"><input type="checkbox" checked={b.actif} onChange={() => basculer(b)} aria-label={`Activer ${b.titres?.fr}`} /></label></td>
                          <td><div className="achats-actions clients-row-actions">
                            <button type="button" onClick={() => setFormulaire(b)}><Pencil size={14} /> Modifier</button>
                            {!b.systeme && <button type="button" onClick={() => supprimer(b)}><Trash2 size={14} /> Supprimer</button>}
                          </div></td>
                        </tr>
                      );
                    })}
                    {boutons.length === 0 && <tr><td colSpan="6">Aucun bouton.</td></tr>}
                  </tbody>
                </table>
              </div>
            </>}
          </>}
        </main>
      </div>
      {formulaire && <FormulaireBouton initial={formulaire.id ? formulaire : null} options={donnees?.options} onClose={() => setFormulaire(null)}
        onSaved={(m) => { setFormulaire(null); setInfo(m); charger(); }} />}
    </div>
  );
}
