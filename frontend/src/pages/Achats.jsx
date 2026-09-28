import { useEffect, useMemo, useState } from "react";
import { Bell, FilePlus2, Plus, Search, Trash2, X } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

const TABS = [
  ["demandes", "Demandes d'achat"],
  ["commandes", "Bons de commande"],
  ["receptions", "Réceptions"],
];

function headersAuth() {
  return { Authorization: `Bearer ${localStorage.getItem("token")}`, "Content-Type": "application/json" };
}

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}/achats${path}`, { ...options, headers: { ...headersAuth(), ...(options.headers || {}) } });
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
  return <span className={`achats-badge achats-badge--${String(statut).replaceAll("_", "-")}`}>{statut}</span>;
}

function LignesForm({ lignes, setLignes, produits, demande = false }) {
  function changer(i, champ, valeur) {
    const copie = [...lignes];
    copie[i] = { ...copie[i], [champ]: valeur };
    if (champ === "produitId") {
      const p = produits.find((x) => x.id === Number(valeur));
      if (p && !demande) copie[i].prixUnitaire = String(p.prix_unitaire);
      if (p && demande && !copie[i].prixEstime) copie[i].prixEstime = String(p.prix_unitaire);
    }
    setLignes(copie);
  }
  function ajouter() {
    setLignes([...lignes, demande ? { produitId: "", quantite: 1, prixEstime: "" } : { produitId: "", quantite: 1, prixUnitaire: "" }]);
  }
  function retirer(i) { setLignes(lignes.filter((_, index) => index !== i)); }

  return (
    <div className="achats-lignes">
      <div className="achats-lignes__titre"><strong>Lignes</strong><button type="button" className="achats-btn-lien" onClick={ajouter}><Plus size={15}/> Ajouter</button></div>
      {lignes.map((l, i) => (
        <div className="achats-ligne" key={i}>
          <select value={l.produitId} onChange={(e) => changer(i, "produitId", e.target.value)} required>
            <option value="">Produit…</option>
            {produits.map((p) => <option key={p.id} value={p.id}>{p.reference} — {p.nom}</option>)}
          </select>
          <input type="number" min="1" value={l.quantite} onChange={(e) => changer(i, "quantite", e.target.value)} placeholder="Qté" required />
          <input type="number" min="0" step="0.01" value={demande ? l.prixEstime : l.prixUnitaire} onChange={(e) => changer(i, demande ? "prixEstime" : "prixUnitaire", e.target.value)} placeholder={demande ? "Prix estimé" : "Prix achat"} required />
          <strong>{argent(Number(l.quantite || 0) * Number(demande ? l.prixEstime : l.prixUnitaire || 0))}</strong>
          <button type="button" className="achats-icon-btn" onClick={() => retirer(i)} disabled={lignes.length === 1}><Trash2 size={15}/></button>
        </div>
      ))}
    </div>
  );
}

function DemandeForm({ produits, initial, onClose, onSaved }) {
  const [notes, setNotes] = useState(initial?.notes || "");
  const [lignes, setLignes] = useState(initial?.lignes?.map((l) => ({ produitId: l.produit_id, quantite: l.quantite, prixEstime: String(l.prix_unitaire || 0) })) || [{ produitId: "", quantite: 1, prixEstime: "" }]);
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);
  const total = useMemo(() => lignes.reduce((s, l) => s + Number(l.quantite || 0) * Number(l.prixEstime || 0), 0), [lignes]);

  async function soumettre(e) {
    e.preventDefault(); setEnCours(true); setErreur("");
    try {
      const body = { notes: notes || null, lignes: lignes.map((l) => ({ produitId: Number(l.produitId), quantite: Number(l.quantite), prixEstime: Number(l.prixEstime || 0) })) };
      await api("/demandes", { method: "POST", body: JSON.stringify(body) });
      onSaved();
    } catch (e2) { setErreur(e2.message); } finally { setEnCours(false); }
  }

  return (
    <form className="panel achats-form" onSubmit={soumettre}>
      <div className="achats-form__entete"><h3>{initial ? `Demande ${initial.numero}` : "Nouvelle demande d'achat"}</h3><button type="button" className="achats-icon-btn" onClick={onClose}><X size={18}/></button></div>
      {erreur && <div className="erreur-message">{erreur}</div>}
      <LignesForm lignes={lignes} setLignes={setLignes} produits={produits} demande />
      <div className="champ"><label>Notes</label><textarea rows="2" value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      <div className="achats-form__pied"><strong>Total estimé : {argent(total)}</strong><div><button type="button" className="bouton-secondaire-large" onClick={onClose}>Annuler</button><button className="bouton-principal achats-btn-auto" disabled={enCours}>{enCours ? "Enregistrement…" : "Enregistrer"}</button></div></div>
    </form>
  );
}

function BonCommandeForm({ fournisseurs, produits, demandeInitiale, onClose, onSaved }) {
  const [fournisseurId, setFournisseurId] = useState("");
  const [notes, setNotes] = useState(demandeInitiale?.notes || "");
  const [lignes, setLignes] = useState(demandeInitiale?.lignes?.map((l) => ({ produitId: l.produit_id, quantite: l.quantite, prixUnitaire: String(l.prix_unitaire || 0) })) || [{ produitId: "", quantite: 1, prixUnitaire: "" }]);
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);
  const total = useMemo(() => lignes.reduce((s, l) => s + Number(l.quantite || 0) * Number(l.prixUnitaire || 0), 0), [lignes]);

  async function soumettre(e) {
    e.preventDefault(); setEnCours(true); setErreur("");
    try {
      const body = { fournisseurId: Number(fournisseurId), demandeId: demandeInitiale?.id || null, notes: notes || null, lignes: lignes.map((l) => ({ produitId: Number(l.produitId), quantite: Number(l.quantite), prixUnitaire: Number(l.prixUnitaire) })) };
      await api("/bons-commande", { method: "POST", body: JSON.stringify(body) });
      onSaved();
    } catch (e2) { setErreur(e2.message); } finally { setEnCours(false); }
  }

  return (
    <form className="panel achats-form" onSubmit={soumettre}>
      <div className="achats-form__entete"><h3>{demandeInitiale ? `Convertir ${demandeInitiale.numero}` : "Nouveau bon de commande fournisseur"}</h3><button type="button" className="achats-icon-btn" onClick={onClose}><X size={18}/></button></div>
      {erreur && <div className="erreur-message">{erreur}</div>}
      <div className="champ"><label>Fournisseur</label><select value={fournisseurId} onChange={(e) => setFournisseurId(e.target.value)} required><option value="">Choisir…</option>{fournisseurs.map((f) => <option key={f.id} value={f.id}>{f.nom}</option>)}</select></div>
      <LignesForm lignes={lignes} setLignes={setLignes} produits={produits}/>
      <div className="champ"><label>Notes</label><textarea rows="2" value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      <div className="achats-form__pied"><strong>Total : {argent(total)}</strong><div><button type="button" className="bouton-secondaire-large" onClick={onClose}>Annuler</button><button className="bouton-principal achats-btn-auto" disabled={enCours}>{enCours ? "Enregistrement…" : "Créer le bon"}</button></div></div>
    </form>
  );
}

function ReceptionForm({ commande, onClose, onSaved }) {
  const [lignes, setLignes] = useState(commande.lignes.map((l) => ({ produitId: l.produit_id, produitNom: l.produit_nom, commande: Number(l.quantite), dejaRecu: Number(l.quantite_recue || 0), quantite: Math.max(0, Number(l.quantite) - Number(l.quantite_recue || 0)) })));
  const [notes, setNotes] = useState("");
  const [erreur, setErreur] = useState("");
  const [enCours, setEnCours] = useState(false);
  const total = lignes.reduce((s, l) => s + Number(l.quantite || 0), 0);

  async function soumettre(e) {
    e.preventDefault(); setEnCours(true); setErreur("");
    try {
      await api(`/bons-commande/${commande.id}/receptionner`, { method: "POST", body: JSON.stringify({ notes: notes || null, lignes: lignes.filter((l) => Number(l.quantite) > 0).map((l) => ({ produitId: l.produitId, quantite: Number(l.quantite) })) }) });
      onSaved();
    } catch (e2) { setErreur(e2.message); } finally { setEnCours(false); }
  }

  return (
    <form className="panel achats-form" onSubmit={soumettre}>
      <div className="achats-form__entete"><h3>Réception — {commande.numero}</h3><button type="button" className="achats-icon-btn" onClick={onClose}><X size={18}/></button></div>
      {erreur && <div className="erreur-message">{erreur}</div>}
      <p className="achats-muted">Indiquez les quantités réellement reçues. Une réception peut être partielle.</p>
      <div className="achats-reception-lignes">
        {lignes.map((l, i) => <div className="achats-reception-ligne" key={l.produitId}><span><strong>{l.produitNom}</strong><small>Commandé : {l.commande} · Déjà reçu : {l.dejaRecu} · Restant : {l.commande - l.dejaRecu}</small></span><input type="number" min="0" max={Math.max(0, l.commande - l.dejaRecu)} value={l.quantite} onChange={(e) => { const copy = [...lignes]; copy[i] = { ...copy[i], quantite: e.target.value }; setLignes(copy); }} /></div>)}
      </div>
      <div className="champ"><label>Notes</label><textarea rows="2" value={notes} onChange={(e) => setNotes(e.target.value)} /></div>
      <div className="achats-form__pied"><strong>{total} unité(s) reçue(s)</strong><div><button type="button" className="bouton-secondaire-large" onClick={onClose}>Annuler</button><button className="bouton-principal achats-btn-auto" disabled={enCours}>{enCours ? "Enregistrement…" : "Enregistrer la réception"}</button></div></div>
    </form>
  );
}

export default function Achats() {
  const [tab, setTab] = useState("demandes");
  const [refs, setRefs] = useState({ fournisseurs: [], produits: [] });
  const [data, setData] = useState({ demandes: [], commandes: [], receptions: [] });
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [form, setForm] = useState(null);
  const [recherche, setRecherche] = useState("");

  async function charger() {
    setChargement(true); setErreur("");
    try {
      const [r, d, c, rec] = await Promise.all([api("/references"), api("/demandes"), api("/bons-commande"), api("/receptions")]);
      setRefs(r); setData({ demandes: d.demandes, commandes: c.bonsCommande, receptions: rec.receptions });
    } catch (e) { setErreur(e.message); } finally { setChargement(false); }
  }
  useEffect(() => { charger(); }, []);

  async function action(path, method = "POST", body) {
    setErreur("");
    try { await api(path, { method, body: body ? JSON.stringify(body) : undefined }); await charger(); }
    catch (e) { setErreur(e.message); }
  }

  const liste = data[tab].filter((d) => `${d.numero || ""} ${d.fournisseur_nom || ""} ${d.demandeur_nom || ""} ${d.achat_numero || ""}`.toLowerCase().includes(recherche.toLowerCase()));

  return (
    <div className="app-layout">
      <Sidebar/>
      <div className="app-contenu">
        <header className="app-topbar"><div className="app-topbar__recherche"><Search size={16}/><input value={recherche} onChange={(e) => setRecherche(e.target.value)} placeholder="Rechercher un achat, fournisseur ou référence"/></div><div className="app-topbar__droite"><Bell size={18}/><div className="app-topbar__avatar">A</div></div></header>
        <main className="app-main">
          <div className="achats-entete"><div><h1 className="app-main__titre">Achats</h1><p className="achats-sous-titre">Demandes d'achat, bons de commande fournisseurs et réceptions.</p></div>{tab === "demandes" && <button className="bouton-principal achats-btn-auto" onClick={() => setForm({ type: "demande" })}><FilePlus2 size={16}/> Nouvelle demande</button>}{tab === "commandes" && <button className="bouton-principal achats-btn-auto" onClick={() => setForm({ type: "commande" })}><FilePlus2 size={16}/> Nouveau bon de commande</button>}</div>
          <div className="achats-tabs">{TABS.map(([k, label]) => <button key={k} className={tab === k ? "actif" : ""} onClick={() => { setTab(k); setForm(null); }}>{label}<span>{data[k].length}</span></button>)}</div>
          {erreur && <div className="erreur-message">{erreur}</div>}
          {form?.type === "demande" && <DemandeForm produits={refs.produits} onClose={() => setForm(null)} onSaved={() => { setForm(null); charger(); }}/>} 
          {form?.type === "commande" && <BonCommandeForm fournisseurs={refs.fournisseurs} produits={refs.produits} onClose={() => setForm(null)} onSaved={() => { setForm(null); charger(); }}/>} 
          {form?.type === "convertir" && <BonCommandeForm fournisseurs={refs.fournisseurs} produits={refs.produits} demandeInitiale={form.demande} onClose={() => setForm(null)} onSaved={() => { setForm(null); charger(); }}/>} 
          {form?.type === "reception" && <ReceptionForm commande={form.commande} onClose={() => setForm(null)} onSaved={() => { setForm(null); charger(); }}/>} 
          {chargement ? <p>Chargement…</p> : <div className="table-module achats-table"><table><thead><tr><th>Numéro</th><th>Date</th><th>Tiers</th><th>Source</th><th>Statut</th><th>Montant</th><th>Actions</th></tr></thead><tbody>
            {liste.map((d) => <tr key={d.id}>
              <td><strong>{d.numero}</strong></td><td>{dateCourte(d.date_demande || d.date_achat || d.date_reception)}</td><td>{d.fournisseur_nom || d.demandeur_nom || "—"}</td><td>{d.demande_numero || d.achat_numero || "—"}</td><td><Badge statut={d.statut}/></td><td>{tab === "receptions" ? "—" : argent(d.montant_estime ?? d.montant_total)}</td>
              <td><div className="achats-actions">
                {tab === "demandes" && d.statut === "brouillon" && <button onClick={() => action(`/demandes/${d.id}/statut`, "PATCH", { statut: "soumise" })}>Soumettre</button>}
                {tab === "demandes" && d.statut === "soumise" && <button onClick={() => setForm({ type: "convertir", demande: d })}>Convertir en bon</button>}
                {tab === "demandes" && d.statut === "soumise" && <button onClick={() => action(`/demandes/${d.id}/statut`, "PATCH", { statut: "annulee" })}>Annuler</button>}
                {tab === "commandes" && ["commande", "reception_partielle"].includes(d.statut) && <button onClick={() => setForm({ type: "reception", commande: d })}>Réceptionner</button>}
                {tab === "commandes" && d.statut === "commande" && <button onClick={() => action(`/bons-commande/${d.id}/statut`, "PATCH", { statut: "annulee" })}>Annuler</button>}
                {tab === "receptions" && <span className="achats-muted">{d.lignes?.length || 0} ligne(s)</span>}
              </div></td>
            </tr>)}
            {liste.length === 0 && <tr><td colSpan="7">Aucun document.</td></tr>}
          </tbody></table></div>}
        </main>
      </div>
    </div>
  );
}
