import { useCallback, useEffect, useState } from "react";
import { Eye, Pencil, Search, Trash2, X } from "lucide-react";
import { MODES, apiCalculs, fmtDate, fmtMontant } from "../../api/calculs";
import ResultatCalcul from "./ResultatCalcul";

const PAR_PAGE = 15;

export default function Historique({ modules, onModifier }) {
  const [filtres, setFiltres] = useState({ q: "", mode: "", moduleSource: "", du: "", au: "" });
  const [page, setPage] = useState(0);
  const [donnees, setDonnees] = useState({ total: 0, calculs: [] });
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");
  const [vu, setVu] = useState(null);

  const charger = useCallback(async () => {
    setChargement(true); setErreur("");
    const params = new URLSearchParams({ limit: PAR_PAGE, offset: page * PAR_PAGE });
    Object.entries(filtres).forEach(([k, v]) => v && params.set(k, v));
    try { setDonnees(await apiCalculs(`?${params}`)); } catch (e) { setErreur(e.message); } finally { setChargement(false); }
  }, [filtres, page]);

  useEffect(() => { const t = setTimeout(charger, 250); return () => clearTimeout(t); }, [charger]);

  const maj = (nom) => (e) => { setPage(0); setFiltres((f) => ({ ...f, [nom]: e.target.value })); };

  async function voir(id) {
    setErreur("");
    try { setVu(await apiCalculs(`/${id}`)); window.scrollTo({ top: 0, behavior: "smooth" }); } catch (e) { setErreur(e.message); }
  }
  async function modifier(id) {
    setErreur("");
    try { onModifier(await apiCalculs(`/${id}`)); } catch (e) { setErreur(e.message); }
  }
  async function supprimer(c) {
    if (!window.confirm(`Supprimer définitivement le calcul ${c.reference} ?`)) return;
    setErreur(""); setMessage("");
    try {
      await apiCalculs(`/${c.id}`, { method: "DELETE" });
      setMessage(`Calcul ${c.reference} supprimé.`);
      if (vu?.id === c.id) setVu(null);
      charger();
    } catch (e) { setErreur(e.message); }
  }

  const pages = Math.max(1, Math.ceil(donnees.total / PAR_PAGE));
  return (
    <div className="calculs-historique">
      {vu && (
        <div className="calculs-vue">
          <button type="button" className="calculs-fermer" onClick={() => setVu(null)} aria-label="Fermer le détail"><X size={18} /></button>
          <ResultatCalcul calcul={vu} modules={modules} />
        </div>
      )}
      <div className="panel calculs-filtres">
        <div className="calculs-recherche"><Search size={16} />
          <input value={filtres.q} onChange={maj("q")} placeholder="Rechercher (référence, objet, auteur)" aria-label="Rechercher un calcul" /></div>
        <select value={filtres.mode} onChange={maj("mode")} aria-label="Type de calcul"><option value="">Tous les types</option>{Object.entries(MODES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
        <select value={filtres.moduleSource} onChange={maj("moduleSource")} aria-label="Module"><option value="">Tous les modules</option>{modules.map((m) => <option key={m.code} value={m.code}>{m.libelle}</option>)}</select>
        <label>Du <input type="date" value={filtres.du} onChange={maj("du")} /></label>
        <label>au <input type="date" value={filtres.au} onChange={maj("au")} /></label>
      </div>
      {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
      {message && <div className="support-succes" role="status">{message}</div>}
      <div className="table-module calculs-table">
        <table>
          <thead><tr><th>Référence</th><th>Type</th><th>Objet</th><th className="num">Montant</th><th>Période</th><th className="num">Résultat</th><th>Actions</th></tr></thead>
          <tbody>
            {chargement && <tr><td colSpan="7">Chargement…</td></tr>}
            {!chargement && donnees.calculs.length === 0 && <tr><td colSpan="7">Aucun calcul trouvé.</td></tr>}
            {!chargement && donnees.calculs.map((c) => (
              <tr key={c.id}>
                <td><strong>{c.reference}</strong><br /><small className="calculs-muted">{c.creePar}</small></td>
                <td>{MODES[c.mode]}</td>
                <td>{c.libelle || "—"}</td>
                <td className="num">{fmtMontant(c.montant)} {c.devise}</td>
                <td>{fmtDate(c.dateDebut)} → {fmtDate(c.dateFin)}<br /><small className="calculs-muted">{c.nombreJours} jours</small></td>
                <td className="num"><strong>{fmtMontant(c.resultat)} {c.devise}</strong></td>
                <td><div className="achats-actions">
                  <button type="button" onClick={() => voir(c.id)}><Eye size={14} /> Voir</button>
                  <button type="button" onClick={() => modifier(c.id)}><Pencil size={14} /> Modifier</button>
                  <button type="button" onClick={() => supprimer(c)}><Trash2 size={14} /> Supprimer</button>
                </div></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="calculs-pagination">
        <button type="button" className="bouton-secondaire-large calculs-btn" disabled={page === 0} onClick={() => setPage(page - 1)}>Précédent</button>
        <span>Page {page + 1} / {pages} · {donnees.total} calcul{donnees.total > 1 ? "s" : ""}</span>
        <button type="button" className="bouton-secondaire-large calculs-btn" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Suivant</button>
      </div>
    </div>
  );
}
