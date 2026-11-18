import { useState } from "react";
import { Database, Download, FileUp, ShieldCheck, RefreshCw } from "lucide-react";
import { API_BASE_URL } from "../api/config";

const TABLES = ["client","fournisseur","produit","commande","achat","bon_livraison","devis","facture","ligne_achat","ligne_bon_livraison","ligne_commande","ligne_devis","ligne_facture","mouvement_stock","paiement","departement"];
const FORMATS = ["csv","xlsx","ods","json","xml","yaml","dbf","sqlite","rtf","odt","zip","tar","gz"];

function authHeaders(extra={}) {
  return { Authorization: `Bearer ${localStorage.getItem("token")}`, ...extra };
}

export default function Transferts() {
  const [table,setTable]=useState("client");
  const [format,setFormat]=useState("csv");
  const [dateDebut,setDateDebut]=useState("");
  const [dateFin,setDateFin]=useState("");
  const [categorie,setCategorie]=useState("");
  const [fichier,setFichier]=useState(null);
  const [message,setMessage]=useState("");
  const [busy,setBusy]=useState(false);
  const [backup,setBackup]=useState(null);
  const [restoreName,setRestoreName]=useState("");
  const [confirmation,setConfirmation]=useState("");

  async function exporter() {
    setBusy(true); setMessage("");
    try {
      const params=new URLSearchParams({format});
      if(dateDebut) params.set("date_debut",dateDebut);
      if(dateFin) params.set("date_fin",dateFin);
      if(categorie) params.set("categorie",categorie);
      const res=await fetch(`${API_BASE_URL}/transferts/export/${encodeURIComponent(table)}?${params}`,{headers:authHeaders()});
      if(!res.ok) { const d=await res.json().catch(()=>({})); throw new Error(d.detail||`Erreur ${res.status}`); }
      const blob=await res.blob(); const url=URL.createObjectURL(blob);
      const a=document.createElement("a"); a.href=url; a.download=`${table}_export.${format}`; a.click(); URL.revokeObjectURL(url);
      setMessage("Export généré et téléchargé.");
    } catch(e) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function importer() {
    if(!fichier) { setMessage("Sélectionnez un fichier à importer."); return; }
    setBusy(true); setMessage("");
    try {
      const body=new FormData(); body.append("fichier",fichier);
      const res=await fetch(`${API_BASE_URL}/transferts/import/${encodeURIComponent(table)}`,{method:"POST",headers:authHeaders(),body});
      const d=await res.json().catch(()=>({}));
      if(!res.ok) throw new Error(d.detail||`Erreur ${res.status}`);
      setMessage(`${d.message} ${d.lignes_importees} ligne(s) importée(s) dans ${d.table}.`);
    } catch(e) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function creerBackup() {
    setBusy(true); setMessage("");
    try {
      const res=await fetch(`${API_BASE_URL}/securite/sauvegardes`,{method:"POST",headers:authHeaders()});
      const d=await res.json().catch(()=>({}));
      if(!res.ok) throw new Error(d.detail||`Erreur ${res.status}`);
      setBackup(d); setRestoreName(d.fichier); setConfirmation(`RESTAURER ${d.base}`); setMessage(`Sauvegarde chiffrée créée : ${d.fichier}`);
    } catch(e) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function telechargerBackup() {
    setBusy(true); setMessage("");
    try {
      const res=await fetch(`${API_BASE_URL}/securite/sauvegardes/${encodeURIComponent(restoreName)}`,{headers:authHeaders()});
      if(!res.ok) { const d=await res.json().catch(()=>({})); throw new Error(d.detail||`Erreur ${res.status}`); }
      const blob=await res.blob(); const url=URL.createObjectURL(blob);
      const a=document.createElement("a"); a.href=url; a.download=`${restoreName}.zip`; a.click(); URL.revokeObjectURL(url);
      setMessage("Sauvegarde chiffrée téléchargée.");
    } catch(e) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function verifierBackup() {
    setBusy(true); setMessage("");
    try {
      const res=await fetch(`${API_BASE_URL}/securite/sauvegardes/verifier`,{method:"POST",headers:{...authHeaders(),"Content-Type":"application/json"},body:JSON.stringify({fichier:restoreName,confirmation:"VERIFIER"})});
      const d=await res.json().catch(()=>({}));
      if(!res.ok) throw new Error(d.detail||`Erreur ${res.status}`);
      setMessage(`Vérification réussie : intégrité ${d.integrite}, déchiffrement ${d.dechiffrement}.`);
    } catch(e) { setMessage(e.message); } finally { setBusy(false); }
  }

  async function restaurerBackup() {
    if(!window.confirm("La restauration remplacera les données de la base actuelle. Continuer ?")) return;
    setBusy(true); setMessage("");
    try {
      const res=await fetch(`${API_BASE_URL}/securite/sauvegardes/restaurer`,{method:"POST",headers:{...authHeaders(),"Content-Type":"application/json"},body:JSON.stringify({fichier:restoreName,confirmation})});
      const d=await res.json().catch(()=>({}));
      if(!res.ok) throw new Error(d.detail||`Erreur ${res.status}`);
      setMessage(`Restauration terminée pour ${d.base}.`);
    } catch(e) { setMessage(e.message); } finally { setBusy(false); }
  }

  return (
    <main className="page-shell">
      <div className="page-head"><div><h1><Database size={24}/> Importation, exportation et sécurité</h1>
        <p>Transfert contrôlé des données métier et protection des sauvegardes PostgreSQL.</p></div></div>

      <section className="panel parametres-section">
        <h2><Download size={19}/> Exportation des données</h2>
        <div className="parametres-grid">
          <label>Table métier<select value={table} onChange={e=>setTable(e.target.value)}>{TABLES.map(t=><option key={t}>{t}</option>)}</select></label>
          <label>Format<select value={format} onChange={e=>setFormat(e.target.value)}>{FORMATS.map(f=><option key={f} value={f}>{f.toUpperCase()}</option>)}</select></label>
          <label>Date de début<input type="date" value={dateDebut} onChange={e=>setDateDebut(e.target.value)}/></label>
          <label>Date de fin<input type="date" value={dateFin} onChange={e=>setDateFin(e.target.value)}/></label>
          <label>Catégorie / identifiant de catégorie<input value={categorie} onChange={e=>setCategorie(e.target.value)} placeholder="Facultatif"/></label>
        </div>
        <button className="app-header__bouton app-header__bouton--primaire" disabled={busy} onClick={exporter}><Download size={16}/> Exporter</button>
      </section>

      <section className="panel parametres-section">
        <h2><FileUp size={19}/> Importation en masse</h2>
        <p>Formats d'import actuellement acceptés : CSV, XLSX, JSON, XML, YAML, SQLite et DBF. Maximum 25 Mo et 10 000 lignes par import. L'import est exécuté dans une transaction.</p>
        <div className="parametres-grid">
          <label>Table de destination<select value={table} onChange={e=>setTable(e.target.value)}>{TABLES.map(t=><option key={t}>{t}</option>)}</select></label>
          <label>Fichier à importer<input type="file" accept=".csv,.xlsx,.ods,.json,.xml,.yaml,.yml,.sqlite,.db,.dbf,.zip,.tar,.gz" onChange={e=>setFichier(e.target.files?.[0]||null)}/></label>
        </div>
        <button className="app-header__bouton app-header__bouton--primaire" disabled={busy} onClick={importer}><FileUp size={16}/> Importer les données</button>
      </section>

      <section className="panel parametres-section">
        <h2><ShieldCheck size={19}/> Sauvegardes chiffrées et restauration</h2>
        <p>Les sauvegardes PostgreSQL utilisent pg_dump, AES-256-GCM et une signature HMAC-SHA-256. La restauration vérifie d'abord l'intégrité et le format du dump.</p>
        <button className="app-header__bouton app-header__bouton--primaire" disabled={busy} onClick={creerBackup}><Database size={16}/> Créer une sauvegarde chiffrée</button>
        {backup && <p><strong>Fichier :</strong> {backup.fichier}<br/><strong>Chiffrement :</strong> AES-256-GCM<br/><strong>Signature :</strong> HMAC-SHA-256</p>}
        <div style={{display:"flex",gap:10,flexWrap:"wrap",marginTop:10}}>
          <button className="app-header__bouton app-header__bouton--secondaire" disabled={busy||!restoreName} onClick={telechargerBackup}><Download size={16}/> Télécharger le paquet chiffré + signature</button>
        </div>
        <div className="parametres-grid">
          <label>Fichier de sauvegarde<input value={restoreName} onChange={e=>setRestoreName(e.target.value)} placeholder="nom.bak.enc"/></label>
          <label>Confirmation exacte pour restaurer<input value={confirmation} onChange={e=>setConfirmation(e.target.value)} placeholder="RESTAURER nom_de_base"/></label>
        </div>
        <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
          <button className="app-header__bouton app-header__bouton--secondaire" disabled={busy||!restoreName} onClick={verifierBackup}><ShieldCheck size={16}/> Vérifier la sauvegarde</button>
          <button className="app-header__bouton app-header__bouton--secondaire" disabled={busy||!restoreName||!confirmation} onClick={restaurerBackup}><RefreshCw size={16}/> Restaurer</button>
        </div>
        <p><strong>Attention :</strong> la restauration remplace les données de la base entreprise courante. Une sauvegarde préalable et une fenêtre de maintenance sont recommandées.</p>
      </section>
      {message && <p role="status" className="panel">{message}</p>}
    </main>
  );
}
