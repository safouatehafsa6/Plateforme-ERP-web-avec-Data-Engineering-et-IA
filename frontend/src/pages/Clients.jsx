import { useEffect, useMemo, useState } from "react";
import { Search, Plus, Pencil, X, Users, Eye, Mail, Phone, MapPin, Sparkles, AlertTriangle } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";
import { normaliserClient, validerClient, suggererCorrectionEmail } from "../validation/client";

async function api(endpoint, options = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = data?.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => item?.msg || "Donnée invalide.").join(" ")
      : detail || data?.message || `Erreur ${res.status}`;
    throw new Error(typeof message === "string" ? message : `Erreur ${res.status}`);
  }
  return data;
}

const empty = { nom: "", email: "", telephone: "", adresse: "" };

function ClientForm({ initial, onClose, onSaved }) {
  const [form, setForm] = useState(() => normaliserClient(initial || empty));
  const [erreur, setErreur] = useState("");
  const [saving, setSaving] = useState(false);
  const [touched, setTouched] = useState({});
  const [tentativeEnvoi, setTentativeEnvoi] = useState(false);
  const [avertissementDoublon, setAvertissementDoublon] = useState("");
  const erreursChamps = validerClient(form);
  const suggestionEmail = suggererCorrectionEmail(form.email);

  function change(e) {
    const { name, value } = e.target;
    setForm((f) => ({ ...f, [name]: value }));
    setErreur("");
    setAvertissementDoublon("");
  }

  function afficherErreur(champ) {
    return (touched[champ] || tentativeEnvoi) ? erreursChamps[champ] : "";
  }

  function propsValidation(champ, aideId) {
    const message = afficherErreur(champ);
    return { "aria-invalid": Boolean(message), "aria-describedby": message ? `client-${champ}-erreur` : aideId };
  }

  async function submit(e) {
    e.preventDefault();
    setTentativeEnvoi(true);
    setErreur("");
    setAvertissementDoublon("");

    const erreurs = validerClient(form);
    if (Object.keys(erreurs).length > 0) {
      document.getElementById(`client-${Object.keys(erreurs)[0]}`)?.focus();
      return;
    }

    setSaving(true);
    try {
      // Vérification côté serveur avant l'enregistrement, puis contrôle de sécurité dans POST/PATCH.
      const params = new URLSearchParams();
      if (form.email) params.set("email", form.email.trim());
      if (form.telephone) params.set("telephone", form.telephone.trim());
      if (initial?.id) params.set("exclure_id", String(initial.id));
      if (params.toString()) {
        const verification = await api(`/clients/verification-doublon?${params.toString()}`);
        if (verification.doublons?.length) {
          const premier = verification.doublons[0];
          const champ = premier.champ === "email" ? "adresse e-mail" : "numéro de téléphone";
          setAvertissementDoublon(`Un client existe déjà avec ce ${champ} : ${premier.nom}. Vérifiez les informations avant de continuer.`);
          return;
        }
      }
      const endpoint = initial?.id ? `/clients/${initial.id}` : "/clients";
      await api(endpoint, { method: initial?.id ? "PATCH" : "POST", body: JSON.stringify(normaliserClient(form)) });
      onSaved();
    } catch (err) {
      setErreur(err.message);
    } finally {
      setSaving(false);
    }
  }

  const erreursVisibles = Object.keys(erreursChamps).filter((champ) => afficherErreur(champ));

  return (
    <form className="panel achats-form clients-form" onSubmit={submit} noValidate>
      <div className="achats-form__entete">
        <h3>{initial?.id ? "Modifier le client" : "Nouveau client"}</h3>
        <button type="button" className="achats-icon-btn" onClick={onClose} aria-label="Fermer le formulaire"><X size={18} /></button>
      </div>

      {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
      {avertissementDoublon && <div className="clients-warning" role="alert"><AlertTriangle size={18} /><span>{avertissementDoublon}</span></div>}
      {tentativeEnvoi && erreursVisibles.length > 0 && <div className="erreur-message" role="alert">Veuillez corriger les champs signalés avant d’enregistrer le client.</div>}

      <div className="champ">
        <label htmlFor="client-nom">Nom *</label>
        <input id="client-nom" name="nom" value={form.nom} onChange={change} onBlur={() => setTouched((t) => ({ ...t, nom: true }))} required maxLength={150} autoComplete="organization" {...propsValidation("nom")} />
        {afficherErreur("nom") && <p className="champ-erreur" id="client-nom-erreur">{erreursChamps.nom}</p>}
      </div>

      <div className="achats-form-grid">
        <div className="champ">
          <label htmlFor="client-email">Email</label>
          <input id="client-email" type="email" name="email" value={form.email ?? ""} onChange={change} onBlur={() => setTouched((t) => ({ ...t, email: true }))} maxLength={150} autoComplete="email" placeholder="nom@entreprise.com" {...propsValidation("email")} />
          {afficherErreur("email") && <p className="champ-erreur" id="client-email-erreur">{erreursChamps.email}</p>}
          {suggestionEmail && !erreursChamps.email && <div className="clients-suggestion"><Sparkles size={15} /><span>Vouliez-vous écrire <strong>{suggestionEmail}</strong> ?</span><button type="button" onClick={() => { setForm((f) => ({ ...f, email: suggestionEmail })); setAvertissementDoublon(""); }}>Utiliser</button></div>}
        </div>
        <div className="champ">
          <label htmlFor="client-telephone">Téléphone</label>
          <input id="client-telephone" type="tel" name="telephone" value={form.telephone ?? ""} onChange={change} onBlur={() => setTouched((t) => ({ ...t, telephone: true }))} maxLength={30} autoComplete="tel" placeholder="+212 6 12 34 56 78" {...propsValidation("telephone", "client-telephone-aide")} />
          {afficherErreur("telephone") ? <p className="champ-erreur" id="client-telephone-erreur">{erreursChamps.telephone}</p> : <p className="champ-aide" id="client-telephone-aide">Indicatif international facultatif ; 7 à 15 chiffres si le numéro est renseigné.</p>}
        </div>
      </div>

      <div className="champ">
        <label htmlFor="client-adresse">Adresse</label>
        <textarea id="client-adresse" name="adresse" rows={3} value={form.adresse ?? ""} onChange={change} onBlur={() => setTouched((t) => ({ ...t, adresse: true }))} maxLength={1000} {...propsValidation("adresse", "client-adresse-aide")} />
        {afficherErreur("adresse") && <p className="champ-erreur" id="client-adresse-erreur">{erreursChamps.adresse}</p>}
        <p className="champ-aide" id="client-adresse-aide">{(form.adresse ?? "").length}/1000 caractères maximum.</p>
      </div>

      <div className="achats-form__pied">
        <span className="achats-muted">Vérification des champs et détection des doublons avant enregistrement.</span>
        <div><button type="button" className="bouton-secondaire-large" onClick={onClose} disabled={saving}>Annuler</button><button className="bouton-principal achats-btn-auto" disabled={saving}>{saving ? "Vérification…" : "Enregistrer"}</button></div>
      </div>
    </form>
  );
}

function FicheClient({ client, onClose, onModifier }) {
  if (!client) return null;
  return (
    <div className="clients-overlay" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <section className="panel clients-fiche" role="dialog" aria-modal="true" aria-labelledby="fiche-client-titre">
        <div className="clients-fiche__header"><div className="clients-avatar"><Users size={24} /></div><div className="clients-fiche__heading"><p className="clients-eyebrow">FICHE CLIENT</p><h2 id="fiche-client-titre">{client.nom}</h2><p>Identifiant client : {client.id}</p></div><button type="button" className="achats-icon-btn" onClick={onClose} aria-label="Fermer la fiche"><X size={18} /></button></div>
        <div className="clients-fiche__grid">
          <div className="clients-info-item"><Mail size={18} /><div><span>Adresse e-mail</span><strong>{client.email || "Non renseignée"}</strong></div></div>
          <div className="clients-info-item"><Phone size={18} /><div><span>Téléphone</span><strong>{client.telephone || "Non renseigné"}</strong></div></div>
          <div className="clients-info-item clients-info-item--wide"><MapPin size={18} /><div><span>Adresse</span><strong>{client.adresse || "Non renseignée"}</strong></div></div>
          <div className="clients-info-item clients-info-item--wide"><Users size={18} /><div><span>Commandes associées</span><strong>{client.nombre_commandes ?? 0}</strong></div></div>
        </div>
        <div className="clients-fiche__footer"><button type="button" className="bouton-secondaire-large" onClick={onClose}>Fermer</button><button type="button" className="bouton-principal achats-btn-auto" onClick={() => onModifier(client)}><Pencil size={15} /> Modifier le client</button></div>
      </section>
    </div>
  );
}

export default function Clients() {
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState("");
  const [form, setForm] = useState(null);
  const [fiche, setFiche] = useState(null);
  const [chargementFiche, setChargementFiche] = useState(false);

  async function charger() {
    setLoading(true); setErreur("");
    try { const r = await api("/clients"); setItems(r.clients || []); }
    catch (e) { setErreur(e.message); } finally { setLoading(false); }
  }
  useEffect(() => { charger(); }, []);

  const filtered = useMemo(() => items.filter((f) => `${f.nom} ${f.email || ""} ${f.telephone || ""} ${f.adresse || ""}`.toLowerCase().includes(search.toLowerCase())), [items, search]);

  async function ouvrirFiche(client) {
    setChargementFiche(true);
    try { setFiche(await api(`/clients/${client.id}`)); }
    catch (e) { setErreur(e.message); }
    finally { setChargementFiche(false); }
  }

  function modifierDepuisFiche(client) { setFiche(null); setForm(client); }

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-contenu">
        <header className="app-topbar"><div className="app-topbar__recherche"><Search size={16}/><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Rechercher un client" /></div><div className="app-topbar__droite"><Users size={18}/><div className="app-topbar__avatar">A</div></div></header>
        <main className="app-main">
          <div className="achats-entete"><div><h1 className="app-main__titre">Clients</h1><p className="achats-sous-titre">Gestion des clients utilisés dans les commandes et bons de commande.</p></div><button className="bouton-principal achats-btn-auto" onClick={() => setForm({})}><Plus size={16}/> Nouveau client</button></div>
          <div className="clients-feature-note"><Sparkles size={17}/><span>Assistance à la saisie, contrôle des doublons et fiches clients détaillées.</span></div>
          {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
          {form && <ClientForm key={form.id || "nouveau-client"} initial={form.id ? form : null} onClose={() => setForm(null)} onSaved={() => { setForm(null); charger(); }} />}
          {loading ? <p>Chargement…</p> : <div className="table-module achats-table"><table><thead><tr><th>Nom</th><th>Email</th><th>Téléphone</th><th>Adresse</th><th>Commandes</th><th>Actions</th></tr></thead><tbody>
            {filtered.map((f) => <tr key={f.id}><td><strong>{f.nom}</strong></td><td>{f.email || "—"}</td><td>{f.telephone || "—"}</td><td>{f.adresse || "—"}</td><td>{f.nombre_commandes ?? 0}</td><td><div className="achats-actions clients-row-actions"><button type="button" onClick={() => ouvrirFiche(f)}><Eye size={14}/> Fiche</button><button type="button" onClick={() => setForm(f)}><Pencil size={14}/> Modifier</button></div></td></tr>)}
            {filtered.length === 0 && <tr><td colSpan="6">Aucun client.</td></tr>}
          </tbody></table></div>}
          {chargementFiche && <p className="achats-muted">Chargement de la fiche client…</p>}
        </main>
      </div>
      <FicheClient client={fiche} onClose={() => setFiche(null)} onModifier={modifierDepuisFiche} />
    </div>
  );
}
