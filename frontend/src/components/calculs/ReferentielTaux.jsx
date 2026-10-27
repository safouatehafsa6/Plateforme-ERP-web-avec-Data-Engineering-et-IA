import { useCallback, useEffect, useMemo, useState } from "react";
import { AlertTriangle, Pencil, Plus, Trash2 } from "lucide-react";
import { apiCalculs, fmtDate, fmtTaux } from "../../api/calculs";

const VIDE = { dateDebut: "", dateFin: "", taux: "" };

// Administration des périodes et des taux (réservée aux administrateurs).
export default function ReferentielTaux() {
  const [baremes, setBaremes] = useState([]);
  const [baremeId, setBaremeId] = useState(null);
  const [periodes, setPeriodes] = useState([]);
  const [archivees, setArchivees] = useState(false);
  const [form, setForm] = useState(VIDE);
  const [edition, setEdition] = useState(null);
  const [nouveau, setNouveau] = useState(null);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");

  const chargerBaremes = useCallback(async (choisir) => {
    try {
      const r = await apiCalculs("/referentiel/baremes");
      setBaremes(r.baremes || []);
      setBaremeId((courant) => choisir ?? courant ?? r.baremes?.[0]?.id ?? null);
    } catch (e) { setErreur(e.message); }
  }, []);
  const chargerPeriodes = useCallback(async () => {
    if (!baremeId) return;
    try { setPeriodes((await apiCalculs(`/referentiel/baremes/${baremeId}/periodes?archivees=${archivees}`)).periodes || []); } catch (e) { setErreur(e.message); }
  }, [baremeId, archivees]);

  useEffect(() => { chargerBaremes(); }, [chargerBaremes]);
  useEffect(() => { chargerPeriodes(); }, [chargerPeriodes]);

  // Trous entre deux périodes actives consécutives : un calcul qui les traverse serait refusé.
  const trous = useMemo(() => {
    const actives = periodes.filter((p) => p.actif).sort((a, b) => a.dateDebut.localeCompare(b.dateDebut));
    const resultat = {};
    for (let i = 1; i < actives.length; i++) {
      const finPrec = new Date(`${actives[i - 1].dateFin}T00:00:00`);
      const debut = new Date(`${actives[i].dateDebut}T00:00:00`);
      if ((debut - finPrec) / 86400000 > 1) resultat[actives[i].id] = [new Date(finPrec.getTime() + 86400000), new Date(debut.getTime() - 86400000)];
    }
    return resultat;
  }, [periodes]);

  async function enregistrer(e) {
    e.preventDefault(); setErreur(""); setMessage("");
    try {
      const corps = JSON.stringify({ dateDebut: form.dateDebut, dateFin: form.dateFin, taux: form.taux });
      if (edition) await apiCalculs(`/referentiel/periodes/${edition}`, { method: "PUT", body: corps });
      else await apiCalculs(`/referentiel/baremes/${baremeId}/periodes`, { method: "POST", body: corps });
      setMessage(edition ? "Période modifiée : elle sera appliquée aux nouveaux calculs." : "Période ajoutée.");
      setForm(VIDE); setEdition(null);
      await Promise.all([chargerPeriodes(), chargerBaremes()]);
    } catch (err) { setErreur(err.message); }
  }
  async function supprimer(p) {
    if (!window.confirm(`Supprimer la période du ${fmtDate(p.dateDebut)} au ${fmtDate(p.dateFin)} (${fmtTaux(p.taux)}) ?`)) return;
    setErreur(""); setMessage("");
    try { setMessage((await apiCalculs(`/referentiel/periodes/${p.id}`, { method: "DELETE" })).message); await Promise.all([chargerPeriodes(), chargerBaremes()]); }
    catch (err) { setErreur(err.message); }
  }
  async function creerBareme(e) {
    e.preventDefault(); setErreur(""); setMessage("");
    try {
      const r = await apiCalculs("/referentiel/baremes", { method: "POST", body: JSON.stringify(nouveau) });
      setNouveau(null); setMessage("Barème créé."); await chargerBaremes(r.id);
    } catch (err) { setErreur(err.message); }
  }
  function modifier(p) {
    setEdition(p.id); setForm({ dateDebut: p.dateDebut, dateFin: p.dateFin, taux: p.taux }); setMessage(""); window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const bareme = baremes.find((b) => b.id === baremeId);
  return (
    <div className="calculs-referentiel">
      {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
      {message && <div className="support-succes" role="status">{message}</div>}

      <div className="panel calculs-baremes">
        <div className="champ"><label htmlFor="r-bareme">Barème de taux</label>
          <select id="r-bareme" value={baremeId || ""} onChange={(e) => { setBaremeId(Number(e.target.value)); setEdition(null); setForm(VIDE); }}>
            {baremes.map((b) => <option key={b.id} value={b.id}>{b.libelle} — {b.nbPeriodes} période{b.nbPeriodes > 1 ? "s" : ""}{b.actif ? "" : " (inactif)"}</option>)}
          </select></div>
        <button type="button" className="bouton-secondaire-large calculs-btn" onClick={() => setNouveau(nouveau ? null : { code: "", libelle: "", description: "" })}><Plus size={16} /> Nouveau barème</button>
      </div>
      {nouveau && (
        <form className="panel calculs-form" onSubmit={creerBareme}>
          <h3>Nouveau barème</h3>
          <div className="calculs-grille">
            <div className="champ"><label htmlFor="nb-code">Code *</label><input id="nb-code" value={nouveau.code} onChange={(e) => setNouveau({ ...nouveau, code: e.target.value })} required minLength={2} maxLength={40} pattern="[A-Za-z0-9_\-]+" placeholder="EX. TMM" /></div>
            <div className="champ"><label htmlFor="nb-lib">Libellé *</label><input id="nb-lib" value={nouveau.libelle} onChange={(e) => setNouveau({ ...nouveau, libelle: e.target.value })} required minLength={2} maxLength={150} /></div>
            <div className="champ calculs-large"><label htmlFor="nb-desc">Description</label><input id="nb-desc" value={nouveau.description} onChange={(e) => setNouveau({ ...nouveau, description: e.target.value })} maxLength={1000} /></div>
          </div>
          <div className="calculs-actions"><button className="bouton-principal calculs-btn">Créer le barème</button></div>
        </form>
      )}

      {bareme && (
        <>
          <form className="panel calculs-form" onSubmit={enregistrer}>
            <h3>{edition ? "Modifier la période" : "Ajouter une période"}</h3>
            <div className="calculs-grille">
              <div className="champ"><label htmlFor="p-debut">Début *</label><input id="p-debut" type="date" required value={form.dateDebut} onChange={(e) => setForm({ ...form, dateDebut: e.target.value })} /></div>
              <div className="champ"><label htmlFor="p-fin">Fin *</label><input id="p-fin" type="date" required min={form.dateDebut || undefined} value={form.dateFin} onChange={(e) => setForm({ ...form, dateFin: e.target.value })} /></div>
              <div className="champ"><label htmlFor="p-taux">Taux (%) *</label><input id="p-taux" type="number" min="0" max="100" step="0.0001" required value={form.taux} onChange={(e) => setForm({ ...form, taux: e.target.value })} inputMode="decimal" /></div>
            </div>
            <p className="calculs-muted">Les bornes de début et de fin sont incluses. Deux périodes d'un même barème ne peuvent pas se chevaucher. Toute modification est appliquée aux nouveaux calculs ; les calculs déjà enregistrés ne changent pas.</p>
            <div className="calculs-actions">
              <button className="bouton-principal calculs-btn">{edition ? "Enregistrer" : <><Plus size={16} /> Ajouter</>}</button>
              {edition && <button type="button" className="bouton-secondaire-large calculs-btn" onClick={() => { setEdition(null); setForm(VIDE); }}>Annuler</button>}
            </div>
          </form>

          <label className="calculs-case calculs-case--simple"><input type="checkbox" checked={archivees} onChange={(e) => setArchivees(e.target.checked)} /><span>Afficher les périodes archivées</span></label>
          <div className="table-module calculs-table">
            <table>
              <thead><tr><th>Début</th><th>Fin</th><th className="num">Taux</th><th>Statut</th><th>Dernière modification</th><th>Actions</th></tr></thead>
              <tbody>
                {periodes.length === 0 && <tr><td colSpan="6">Aucune période dans ce barème.</td></tr>}
                {periodes.map((p) => (
                  <>
                    {trous[p.id] && (
                      <tr key={`t${p.id}`} className="calculs-trou"><td colSpan="6"><AlertTriangle size={14} /> Aucun taux du {trous[p.id][0].toLocaleDateString("fr-FR")} au {trous[p.id][1].toLocaleDateString("fr-FR")} : un calcul sur cette période sera refusé.</td></tr>
                    )}
                    <tr key={p.id} className={p.actif ? "" : "calculs-archive"}>
                      <td>{fmtDate(p.dateDebut)}</td><td>{fmtDate(p.dateFin)}</td><td className="num"><strong>{fmtTaux(p.taux)}</strong></td>
                      <td>{p.actif ? "Active" : "Archivée"}</td>
                      <td><small className="calculs-muted">{p.modifiePar || p.creePar || "—"}</small></td>
                      <td>{p.actif && <div className="achats-actions">
                        <button type="button" onClick={() => modifier(p)}><Pencil size={14} /> Modifier</button>
                        <button type="button" onClick={() => supprimer(p)}><Trash2 size={14} /> Supprimer</button>
                      </div>}</td>
                    </tr>
                  </>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
