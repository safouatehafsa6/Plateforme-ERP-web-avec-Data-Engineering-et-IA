import { useEffect, useMemo, useState } from "react";
import { Search, Plus, Pencil, X, Boxes, ArrowDownToLine, ArrowUpFromLine, RefreshCw } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

async function api(endpoint, options = {}) {
  const token = localStorage.getItem("token");
  const res = await fetch(`${API_BASE_URL}${endpoint}`, { ...options, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(options.headers || {}) } });
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error(data?.detail || data?.message || `Erreur ${res.status}`);
  return data;
}
const empty = { reference: "", nom: "", categorie: "", prixUnitaire: "" };

function ProduitForm({ initial, onClose, onSaved }) {
  const [form, setForm] = useState(initial ? { reference: initial.reference, nom: initial.nom, categorie: initial.categorie || "", prixUnitaire: initial.prix_unitaire } : empty);
  const [erreur, setErreur] = useState(""); const [saving, setSaving] = useState(false);
  function change(e) { setForm(f => ({...f, [e.target.name]: e.target.value})); }
  async function submit(e) { e.preventDefault(); setSaving(true); setErreur(""); try { await api(initial?.id ? `/stock/produits/${initial.id}` : "/stock/produits", { method: initial?.id ? "PATCH":"POST", body: JSON.stringify({...form, prixUnitaire: Number(form.prixUnitaire)}) }); onSaved(); } catch(e) { setErreur(e.message); } finally { setSaving(false); } }
  return <form className="panel achats-form" onSubmit={submit}>
    <div className="achats-form__entete"><h3>{initial?.id ? "Modifier le produit" : "Nouveau produit"}</h3><button type="button" className="achats-icon-btn" onClick={onClose}><X size={18}/></button></div>
    {erreur && <div className="erreur-message">{erreur}</div>}
    <div className="achats-form-grid"><div className="champ"><label>Référence *</label><input name="reference" value={form.reference} onChange={change} required /></div><div className="champ"><label>Nom *</label><input name="nom" value={form.nom} onChange={change} required /></div><div className="champ"><label>Catégorie</label><input name="categorie" value={form.categorie} onChange={change} /></div><div className="champ"><label>Prix unitaire *</label><input type="number" min="0" step="0.01" name="prixUnitaire" value={form.prixUnitaire} onChange={change} required /></div></div>
    <div className="achats-form__pied"><button type="button" className="bouton-secondaire-large" onClick={onClose}>Annuler</button><button className="bouton-principal achats-btn-auto" disabled={saving}>{saving ? "Enregistrement…":"Enregistrer"}</button></div>
  </form>;
}

function MouvementForm({ produit, onClose, onSaved }) {
  const [type, setType] = useState("entree"); const [quantite, setQuantite] = useState(1); const [referenceDoc, setReferenceDoc] = useState(""); const [erreur, setErreur] = useState(""); const [saving, setSaving] = useState(false);
  async function submit(e) { e.preventDefault(); setSaving(true); setErreur(""); try { await api("/stock/mouvements", { method:"POST", body: JSON.stringify({ produitId: produit.id, typeMouvement:type, quantite:Number(quantite), referenceDoc:referenceDoc || null }) }); onSaved(); } catch(e) { setErreur(e.message); } finally { setSaving(false); } }
  return <form className="panel achats-form" onSubmit={submit}><div className="achats-form__entete"><h3>Mouvement – {produit.nom}</h3><button type="button" className="achats-icon-btn" onClick={onClose}><X size={18}/></button></div>{erreur && <div className="erreur-message">{erreur}</div>}<p className="achats-muted">Stock actuel : <strong>{produit.stock_actuel}</strong></p><div className="achats-form-grid"><div className="champ"><label>Type</label><select value={type} onChange={e=>setType(e.target.value)}><option value="entree">Entrée</option><option value="sortie">Sortie</option><option value="ajustement">Ajustement</option></select></div><div className="champ"><label>Quantité *</label><input type="number" min="1" value={quantite} onChange={e=>setQuantite(e.target.value)} required /></div></div><div className="champ"><label>Référence document</label><input value={referenceDoc} onChange={e=>setReferenceDoc(e.target.value)} placeholder="Ex. BR-001" /></div><div className="achats-form__pied"><button type="button" className="bouton-secondaire-large" onClick={onClose}>Annuler</button><button className="bouton-principal achats-btn-auto" disabled={saving}>{saving ? "Enregistrement…":"Enregistrer le mouvement"}</button></div></form>;
}

export default function Stock() {
  const [items,setItems]=useState([]); const [search,setSearch]=useState(""); const [loading,setLoading]=useState(true); const [erreur,setErreur]=useState(""); const [form,setForm]=useState(null); const [mouvement,setMouvement]=useState(null);
  async function charger(){setLoading(true);setErreur("");try{const r=await api("/stock");setItems(r.produits||[])}catch(e){setErreur(e.message)}finally{setLoading(false)}}
  useEffect(()=>{charger()},[]);
  const filtered=useMemo(()=>items.filter(p=>`${p.reference} ${p.nom} ${p.categorie||""}`.toLowerCase().includes(search.toLowerCase())),[items,search]);
  return <div className="app-layout"><Sidebar/><div className="app-contenu"><header className="app-topbar"><div className="app-topbar__recherche"><Search size={16}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Rechercher un produit"/></div><div className="app-topbar__droite"><Boxes size={18}/><div className="app-topbar__avatar">A</div></div></header><main className="app-main"><div className="achats-entete"><div><h1 className="app-main__titre">Stock</h1><p className="achats-sous-titre">Gestion des produits, quantités disponibles et mouvements de stock.</p></div><div><button className="bouton-principal achats-btn-auto" onClick={()=>setForm({})}><Plus size={16}/> Nouveau produit</button></div></div>{erreur&&<div className="erreur-message">{erreur}</div>}{form&&<ProduitForm initial={form.id?form:null} onClose={()=>setForm(null)} onSaved={()=>{setForm(null);charger()}}/>}{mouvement&&<MouvementForm produit={mouvement} onClose={()=>setMouvement(null)} onSaved={()=>{setMouvement(null);charger()}}/>}{loading?<p>Chargement…</p>:<div className="table-module achats-table"><table><thead><tr><th>Référence</th><th>Produit</th><th>Catégorie</th><th>Prix unitaire</th><th>Stock actuel</th><th>Mouvements</th><th>Actions</th></tr></thead><tbody>{filtered.map(p=><tr key={p.id}><td><strong>{p.reference}</strong></td><td>{p.nom}</td><td>{p.categorie||"—"}</td><td>{Number(p.prix_unitaire).toFixed(2)}</td><td><strong>{p.stock_actuel}</strong></td><td>{p.nombre_mouvements}</td><td><div className="achats-actions"><button onClick={()=>setMouvement(p)}><RefreshCw size={14}/> Mouvement</button><button onClick={()=>setForm(p)}><Pencil size={14}/> Modifier</button></div></td></tr>)}{filtered.length===0&&<tr><td colSpan="7">Aucun produit.</td></tr>}</tbody></table></div>}</main></div></div>;
}
