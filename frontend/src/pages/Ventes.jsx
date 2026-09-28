import { useEffect, useMemo, useState } from "react";
import { Bell, FilePlus2, Plus, Search, Trash2, X } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

const TABS = [
  ["devis", "Devis"],
  ["commandes", "Commandes"],
  ["livraisons", "Bons de livraison"],
  ["factures", "Factures"],
];

function headersAuth() {
  return { Authorization: `Bearer ${localStorage.getItem("token")}`, "Content-Type": "application/json" };
}

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}/ventes${path}`, { ...options, headers: { ...headersAuth(), ...(options.headers || {}) } });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Une erreur est survenue.");
  return data;
}

function argent(v) {
  return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "MAD" }).format(Number(v || 0));
}

function dateCourte(v) {
  if (!v) return "—";
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" }).format(new Date(v));
}

function Badge({ statut }) {
  return <span className={`ventes-badge ventes-badge--${String(statut).replaceAll("_", "-")}`}>{statut}</span>;
}

function LignesForm({ lignes, setLignes, produits }) {
  function changer(i, champ, valeur) {
    const copie = [...lignes];
    copie[i] = { ...copie[i], [champ]: valeur };
    if (champ === "produitId") {
      const p = produits.find((x) => x.id === Number(valeur));
      if (p) copie[i].prixUnitaire = String(p.prix_unitaire);
    }
    setLignes(copie);
  }
  function ajouter() { setLignes([...lignes, { produitId: "", quantite: 1, prixUnitaire: "", remisePct: 0 }]); }
  function retirer(i) { setLignes(lignes.filter((_, index) => index !== i)); }

  return (
    <div className="ventes-lignes">
      <div className="ventes-lignes__titre"><strong>Lignes</strong><button type="button" className="ventes-btn-lien" onClick={ajouter}><Plus size={15}/> Ajouter</button></div>
      {lignes.map((l, i) => (
        <div className="ventes-ligne" key={i}>
          <select value={l.produitId} onChange={(e) => changer(i, "produitId", e.target.value)} required>
            <option value="">Produit…</option>
            {produits.map((p) => <option key={p.id} value={p.id}>{p.reference} — {p.nom}</option>)}
          </select>
          <input type="number" min="1" value={l.quantite} onChange={(e) => changer(i, "quantite", e.target.value)} placeholder="Qté" required />
          <input type="number" min="0" step="0.01" value={l.prixUnitaire} onChange={(e) => changer(i, "prixUnitaire", e.target.value)} placeholder="Prix" required />
          <input type="number" min="0" max="100" step="0.01" value={l.remisePct} onChange={(e) => changer(i, "remisePct", e.target.value)} placeholder="Remise %" />
          <strong>{argent(Number(l.quantite || 0) * Number(l.prixUnitaire || 0) * (1 - Number(l.remisePct || 0) / 100))}</strong>
          <button type="button" className="ventes-icon-btn" onClick={() => retirer(i)} disabled={lignes.length === 1}><Trash2 size={15}/></button>
        </div>
      ))}
    </div>
  );
}

function DocumentForm({ type, clients, produits, initial, onClose, onSaved }) {
  const [clientId, setClientId] = useState(initial?.client_id || "");
  const [dateValidite, setDateValidite] = useState(initial?.date_validite?.slice?.(0, 10) || "");
  const [notes, setNotes] = useState(initial?.notes || "");
  const [lignes, setLignes] = useState(initial?.lignes?.map((l) => ({ produitId: l.produit_id, quantite: l.quantite, prixUnitaire: String(l.prix_unitaire), remisePct: String(l.remise_pct || 0) })) || [{ produitId: "", quantite: 1, prixUnitaire: "", remisePct: 0 }]);
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState("");
  const total = useMemo(() => lignes.reduce((s, l) => s + Number(l.quantite || 0) * Number(l.prixUnitaire || 0) * (1 - Number(l.remisePct || 0) / 100), 0), [lignes]);

  async function soumettre(e) {
    e.preventDefault(); setEnCours(true); setErreur("");
    try {
      const body = { clientId: Number(clientId), notes: notes || null, lignes: lignes.map((l) => ({ produitId: Number(l.produitId), quantite: Number(l.quantite), prixUnitaire: Number(l.prixUnitaire), remisePct: Number(l.remisePct || 0) })) };
      if (type === "devis") body.dateValidite = dateValidite || null;
      const path = initial ? `/devis/${initial.id}` : type === "devis" ? "/devis" : "/commandes";
      await api(path, { method: initial ? "PUT" : "POST", body: JSON.stringify(body) });
      onSaved();
    } catch (e2) { setErreur(e2.message); } finally { setEnCours(false); }
  }

  return (
    <form className="panel ventes-form" onSubmit={soumettre}>
      <div className="ventes-form__entete"><h3>{initial ? `Modifier ${initial.numero}` : type === "devis" ? "Nouveau devis" : "Nouvelle commande"}</h3><button type="button" className="ventes-icon-btn" onClick={onClose}><X size={18}/></button></div>
      {erreur && <div className="erreur-message">{erreur}</div>}
      <div className="champ-ligne">
        <div className="champ"><label>Client</label><select value={clientId} onChange={(e) => setClientId(e.target.value)} required><option value="">Choisir…</option>{clients.map((c) => <option key={c.id} value={c.id}>{c.nom}</option>)}</select></div>
        {type === "devis" && <div className="champ"><label>Valable jusqu'au</label><input type="date" value={dateValidite} onChange={(e) => setDateValidite(e.target.value)} /></div>}
      </div>
      <LignesForm lignes={lignes} setLignes={setLignes} produits={produits}/>
      <div className="champ"><label>Notes</label><textarea rows="2" value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      <div className="ventes-form__pied"><strong>Total : {argent(total)}</strong><div><button type="button" className="bouton-secondaire-large" onClick={onClose}>Annuler</button><button className="bouton-principal ventes-btn-auto" disabled={enCours}>{enCours ? "Enregistrement…" : "Enregistrer"}</button></div></div>
    </form>
  );
}

export default function Ventes() {
  const [tab, setTab] = useState("devis");
  const [refs, setRefs] = useState({ clients: [], produits: [] });
  const [data, setData] = useState({ devis: [], commandes: [], livraisons: [], factures: [] });
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [form, setForm] = useState(null);
  const [recherche, setRecherche] = useState("");

  async function charger() {
    setChargement(true); setErreur("");
    try {
      const [r, d, c, b, f] = await Promise.all([api("/references"), api("/devis"), api("/commandes"), api("/bons-livraison"), api("/factures")]);
      setRefs(r); setData({ devis: d.devis, commandes: c.commandes, livraisons: b.bonsLivraison, factures: f.factures });
    } catch (e) { setErreur(e.message); } finally { setChargement(false); }
  }
  useEffect(() => { charger(); }, []);

  async function action(path, method = "POST", body) {
    setErreur("");
    try { await api(path, { method, body: body ? JSON.stringify(body) : undefined }); await charger(); }
    catch (e) { setErreur(e.message); }
  }

  const liste = data[tab].filter((d) => `${d.numero || ""} ${d.client_nom || ""} ${d.commande_numero || ""}`.toLowerCase().includes(recherche.toLowerCase()));

  return (
    <div className="app-layout">
      <Sidebar/>
      <div className="app-contenu">
        <header className="app-topbar"><div className="app-topbar__recherche"><Search size={16}/><input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Rechercher un document ou un client"/></div><div className="app-topbar__droite"><Bell size={18}/><div className="app-topbar__avatar">A</div></div></header>
        <main className="app-main">
          <div className="ventes-entete"><div><h1 className="app-main__titre">Ventes</h1><p className="ventes-sous-titre">Devis, commandes clients, livraisons et factures.</p></div>{(tab === "devis" || tab === "commandes") && <button className="bouton-principal ventes-btn-auto" onClick={() => setForm({ type: tab === "devis" ? "devis" : "commande" })}><FilePlus2 size={16}/> {tab === "devis" ? "Nouveau devis" : "Nouvelle commande"}</button>}</div>
          <div className="ventes-tabs">{TABS.map(([k, label]) => <button key={k} className={tab === k ? "actif" : ""} onClick={() => { setTab(k); setForm(null); }}>{label}<span>{data[k].length}</span></button>)}</div>
          {erreur && <div className="erreur-message">{erreur}</div>}
          {form && <DocumentForm type={form.type} initial={form.initial} clients={refs.clients} produits={refs.produits} onClose={() => setForm(null)} onSaved={() => { setForm(null); charger(); }}/>} 
          {chargement ? <p>Chargement…</p> : <div className="table-module ventes-table"><table><thead><tr><th>Numéro</th><th>Date</th><th>Client</th><th>Source</th><th>Statut</th><th>Montant</th><th>Actions</th></tr></thead><tbody>
            {liste.map((d) => <tr key={d.id}>
              <td><strong>{d.numero}</strong></td><td>{dateCourte(d.date_devis || d.date_commande || d.date_livraison || d.date_facture)}</td><td>{d.client_nom || "—"}</td><td>{d.devis_numero || d.commande_numero || "—"}</td><td><Badge statut={d.statut}/></td><td>{tab === "livraisons" ? "—" : argent(d.montant_total)}</td>
              <td><div className="ventes-actions">
                {tab === "devis" && ["brouillon", "envoye"].includes(d.statut) && <button onClick={() => setForm({ type: "devis", initial: d })}>Modifier</button>}
                {tab === "devis" && d.statut === "brouillon" && <button onClick={() => action(`/devis/${d.id}/statut`, "PATCH", { statut: "envoye" })}>Envoyer</button>}
                {tab === "devis" && ["envoye", "accepte"].includes(d.statut) && !d.commande_id && <button onClick={() => action(`/devis/${d.id}/convertir`)}>Convertir</button>}
                {tab === "commandes" && d.statut !== "annulee" && <button onClick={() => action(`/commandes/${d.id}/livrer`, "POST", { adresseLivraison: null, notes: null })}>Créer BL</button>}
                {tab === "commandes" && d.statut !== "annulee" && <button onClick={() => action(`/commandes/${d.id}/facturer`)}>Facturer</button>}
                {tab === "factures" && d.statut === "impayee" && <button onClick={() => action(`/factures/${d.id}/statut`, "PATCH", { statut: "payee" })}>Marquer payée</button>}
                {tab === "livraisons" && <span className="ventes-muted">{d.lignes?.length || 0} ligne(s)</span>}
              </div></td>
            </tr>)}
            {liste.length === 0 && <tr><td colSpan="7">Aucun document.</td></tr>}
          </tbody></table></div>}
        </main>
      </div>
    </div>
  );
}
