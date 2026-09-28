import { useEffect, useState } from "react";
import { Wallet, Bell } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";
function money(v){return new Intl.NumberFormat("fr-FR",{style:"currency",currency:"MAD"}).format(Number(v||0));}
export default function Comptabilite(){
 const [data,setData]=useState(null),[error,setError]=useState("");
 useEffect(()=>{(async()=>{try{const r=await fetch(`${API_BASE_URL}/comptabilite/synthese`,{headers:{Authorization:`Bearer ${localStorage.getItem("token")}`}});const d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.detail||"Impossible de charger la synthèse comptable.");setData(d);}catch(e){setError(e.message);}})();},[]);
 return <div className="app-layout"><Sidebar/><div className="app-contenu"><header className="app-topbar"><div></div><div className="app-topbar__droite"><Bell size={18}/><div className="app-topbar__avatar">A</div></div></header><main className="app-main"><div className="ventes-entete"><div><h1 className="app-main__titre"><Wallet size={24}/> Comptabilité</h1><p className="ventes-sous-titre">Synthèse des flux issus des ventes, factures et achats.</p></div></div>{error&&<div className="erreur-message">{error}</div>}{data&&<div className="kpi-grille"><div className="panel"><strong>Factures payées</strong><h2>{money(data.factures_payees)}</h2></div><div className="panel"><strong>Factures impayées</strong><h2>{money(data.factures_impayees)}</h2></div><div className="panel"><strong>Total achats</strong><h2>{money(data.total_achats)}</h2></div><div className="panel"><strong>Solde commercial</strong><h2>{money(Number(data.factures_payees)-Number(data.total_achats))}</h2></div></div>}</main></div></div>;
}
