import { useEffect, useMemo, useState } from "react";
import { Search, Plus, Pencil, X, Truck } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

async function api(endpoint, options = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE_URL}${endpoint}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) },
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail || data?.message || `Erreur ${res.status}`);
  return data;
}

const empty = { nom: "", email: "", telephone: "", adresse: "" };

function FournisseurForm({ initial, onClose, onSaved }) {
  const [form, setForm] = useState(initial || empty);
  const [erreur, setErreur] = useState("");
  const [saving, setSaving] = useState(false);

  function change(e) { setForm((f) => ({ ...f, [e.target.name]: e.target.value })); }

  async function submit(e) {
    e.preventDefault(); setSaving(true); setErreur("");
    try {
      const endpoint = initial?.id ? `/fournisseurs/${initial.id}` : "/fournisseurs";
      const method = initial?.id ? "PATCH" : "POST";
      await api(endpoint, { method, body: JSON.stringify({ ...form, email: form.email || null, telephone: form.telephone || null, adresse: form.adresse || null }) });
      onSaved();
    } catch (err) { setErreur(err.message); } finally { setSaving(false); }
  }

  return (
    <form className="panel achats-form" onSubmit={submit}>
      <div className="achats-form__entete"><h3>{initial?.id ? "Modifier le fournisseur" : "Nouveau fournisseur"}</h3><button type="button" className="achats-icon-btn" onClick={onClose}><X size={18}/></button></div>
      {erreur && <div className="erreur-message">{erreur}</div>}
      <div className="champ"><label>Nom *</label><input name="nom" value={form.nom} onChange={change} required maxLength="150" /></div>
      <div className="achats-form-grid">
        <div className="champ"><label>Email</label><input type="email" name="email" value={form.email} onChange={change} /></div>
        <div className="champ"><label>Téléphone</label><input name="telephone" value={form.telephone} onChange={change} /></div>
      </div>
      <div className="champ"><label>Adresse</label><textarea name="adresse" rows="3" value={form.adresse} onChange={change} /></div>
      <div className="achats-form__pied"><span className="achats-muted">Les données sont enregistrées dans la base de l’entreprise.</span><div><button type="button" className="bouton-secondaire-large" onClick={onClose}>Annuler</button><button className="bouton-principal achats-btn-auto" disabled={saving}>{saving ? "Enregistrement…" : "Enregistrer"}</button></div></div>
    </form>
  );
}

export default function Fournisseurs() {
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [erreur, setErreur] = useState("");
  const [form, setForm] = useState(null);

  async function charger() {
    setLoading(true); setErreur("");
    try { const r = await api("/fournisseurs"); setItems(r.fournisseurs || []); }
    catch (e) { setErreur(e.message); } finally { setLoading(false); }
  }
  useEffect(() => { charger(); }, []);

  const filtered = useMemo(() => items.filter((f) => `${f.nom} ${f.email || ""} ${f.telephone || ""} ${f.adresse || ""}`.toLowerCase().includes(search.toLowerCase())), [items, search]);

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-contenu">
        <header className="app-topbar"><div className="app-topbar__recherche"><Search size={16}/><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Rechercher un fournisseur" /></div><div className="app-topbar__droite"><Truck size={18}/><div className="app-topbar__avatar">A</div></div></header>
        <main className="app-main">
          <div className="achats-entete"><div><h1 className="app-main__titre">Fournisseurs</h1><p className="achats-sous-titre">Gestion des fournisseurs utilisés dans les achats et bons de commande.</p></div><button className="bouton-principal achats-btn-auto" onClick={() => setForm({})}><Plus size={16}/> Nouveau fournisseur</button></div>
          {erreur && <div className="erreur-message">{erreur}</div>}
          {form && <FournisseurForm initial={form.id ? form : null} onClose={() => setForm(null)} onSaved={() => { setForm(null); charger(); }} />}
          {loading ? <p>Chargement…</p> : <div className="table-module achats-table"><table><thead><tr><th>Nom</th><th>Email</th><th>Téléphone</th><th>Adresse</th><th>Achats</th><th>Actions</th></tr></thead><tbody>
            {filtered.map((f) => <tr key={f.id}><td><strong>{f.nom}</strong></td><td>{f.email || "—"}</td><td>{f.telephone || "—"}</td><td>{f.adresse || "—"}</td><td>{f.nombre_achats}</td><td><div className="achats-actions"><button onClick={() => setForm(f)}><Pencil size={14}/> Modifier</button></div></td></tr>)}
            {filtered.length === 0 && <tr><td colSpan="6">Aucun fournisseur.</td></tr>}
          </tbody></table></div>}
        </main>
      </div>
    </div>
  );
}
