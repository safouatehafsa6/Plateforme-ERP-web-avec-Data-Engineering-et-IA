import { useEffect, useState } from "react";
import { FileText, Search, Bell, CheckCircle } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

function authHeaders() { return { Authorization: `Bearer ${localStorage.getItem("token")}` }; }
function argent(v) { return new Intl.NumberFormat("fr-FR", { style: "currency", currency: "MAD" }).format(Number(v || 0)); }
function dateCourte(v) { return v ? new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium" }).format(new Date(v)) : "—"; }

export default function Facturation() {
  const [factures, setFactures] = useState([]), [q, setQ] = useState(""), [loading, setLoading] = useState(true), [error, setError] = useState("");
  async function charger() {
    setLoading(true); setError("");
    try {
      const r = await fetch(`${API_BASE_URL}/ventes/factures`, { headers: authHeaders() });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || "Impossible de charger les factures.");
      setFactures(d.factures || []);
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  }
  useEffect(() => { charger(); }, []);
  async function payer(id) {
    setError("");
    try {
      const r = await fetch(`${API_BASE_URL}/ventes/factures/${id}/statut`, { method: "PATCH", headers: { ...authHeaders(), "Content-Type": "application/json" }, body: JSON.stringify({ statut: "payee" }) });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.detail || "Action impossible.");
      charger();
    } catch (e) { setError(e.message); }
  }
  const liste = factures.filter(f => `${f.numero} ${f.client_nom || ""} ${f.statut}`.toLowerCase().includes(q.toLowerCase()));
  return <div className="app-layout"><Sidebar/><div className="app-contenu">
    <header className="app-topbar"><div className="app-topbar__recherche"><Search size={16}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Rechercher une facture ou un client"/></div><div className="app-topbar__droite"><Bell size={18}/><div className="app-topbar__avatar">A</div></div></header>
    <main className="app-main"><div className="ventes-entete"><div><h1 className="app-main__titre"><FileText size={24}/> Facturation</h1><p className="ventes-sous-titre">Suivi des factures et de leur statut.</p></div></div>
      {error && <div className="erreur-message">{error}</div>}
      {loading ? <p>Chargement…</p> : <div className="table-module ventes-table"><table><thead><tr><th>Numéro</th><th>Date</th><th>Client</th><th>Commande</th><th>Statut</th><th>Montant</th><th>Action</th></tr></thead><tbody>
      {liste.map(f=><tr key={f.id}><td><strong>{f.numero}</strong></td><td>{dateCourte(f.date_facture)}</td><td>{f.client_nom || "—"}</td><td>{f.commande_numero || "—"}</td><td><span className={`ventes-badge ventes-badge--${String(f.statut).replaceAll("_","-")}`}>{f.statut}</span></td><td>{argent(f.montant_total)}</td><td>{f.statut === "impayee" ? <button onClick={()=>payer(f.id)}><CheckCircle size={14}/> Marquer payée</button> : "—"}</td></tr>)}
      {!liste.length && <tr><td colSpan="7">Aucune facture.</td></tr>}</tbody></table></div>}
    </main></div></div>;
}
