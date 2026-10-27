import { useState } from "react";
import { FileDown, FileText, LoaderCircle } from "lucide-react";
import { MODES, fmtDate, fmtDateHeure, fmtMontant, fmtTaux, telechargerRapport } from "../../api/calculs";

// Affiche le détail d'un calcul et propose les exports PDF / Word.
export default function ResultatCalcul({ calcul, modules = [] }) {
  const [type, setType] = useState("detaille");
  const [export_, setExport] = useState("");
  const [erreur, setErreur] = useState("");
  const variable = calcul.mode === "taux_variable";
  const module = modules.find((m) => m.code === calcul.moduleSource)?.libelle || calcul.moduleSource;

  async function exporter(format) {
    setErreur(""); setExport(format);
    try { await telechargerRapport(calcul.id, format, type); } catch (e) { setErreur(e.message); } finally { setExport(""); }
  }

  return (
    <section className="panel calculs-resultat" aria-live="polite">
      <header className="calculs-resultat__entete">
        <div>
          <span className="calculs-etiquette">{MODES[calcul.mode]}</span>
          <h3>{calcul.reference}{calcul.libelle ? ` — ${calcul.libelle}` : ""}</h3>
          <p className="calculs-muted">{module} · établi par {calcul.creePar} le {fmtDateHeure(calcul.creeLe)}{calcul.modifieLe ? ` · modifié par ${calcul.modifiePar} le ${fmtDateHeure(calcul.modifieLe)}` : ""}</p>
        </div>
        <div className="calculs-total"><span>Résultat</span><strong>{fmtMontant(calcul.resultat)} {calcul.devise}</strong></div>
      </header>

      <dl className="calculs-infos">
        <div><dt>Montant</dt><dd>{fmtMontant(calcul.montant)} {calcul.devise}</dd></div>
        <div><dt>Période</dt><dd>du {fmtDate(calcul.dateDebut)} au {fmtDate(calcul.dateFin)}</dd></div>
        <div><dt>Nombre de jours</dt><dd>{calcul.nombreJours}</dd></div>
        {!variable && <div><dt>Taux</dt><dd>{fmtTaux(calcul.taux)}</dd></div>}
        {variable && <div><dt>Barème</dt><dd>{calcul.baremeLibelle || "—"}</dd></div>}
      </dl>

      {variable ? (
        <div className="table-module calculs-table">
          <table>
            <thead><tr><th>Période</th><th className="num">Jours</th><th className="num">Taux</th><th className="num">Résultat ({calcul.devise})</th></tr></thead>
            <tbody>
              {(calcul.details || []).map((d, i) => (
                <tr key={i}><td>{fmtDate(d.debut)} → {fmtDate(d.fin)}</td><td className="num">{d.jours}</td><td className="num">{fmtTaux(d.taux)}</td><td className="num">{fmtMontant(d.resultat)}</td></tr>
              ))}
            </tbody>
            <tfoot><tr><td>Total</td><td className="num">{calcul.nombreJours}</td><td /><td className="num">{fmtMontant(calcul.resultat)}</td></tr></tfoot>
          </table>
        </div>
      ) : (
        <p className="calculs-formule">
          Résultat = Montant × (Taux / 100) × (Jours / {calcul.baseJours}) = {fmtMontant(calcul.montant)} × ({new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 4 }).format(Number(calcul.taux))} / 100) × ({calcul.nombreJours} / {calcul.baseJours})
        </p>
      )}

      {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
      <div className="calculs-export">
        {variable && (
          <label className="calculs-type">Rapport
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <option value="detaille">Détaillé (périodes, jours, taux, résultats)</option>
              <option value="simplifie">Simplifié (résultat final)</option>
            </select>
          </label>
        )}
        <button type="button" className="bouton-secondaire-large calculs-btn" onClick={() => exporter("pdf")} disabled={Boolean(export_)}>
          {export_ === "pdf" ? <LoaderCircle size={16} className="boutons-flottants__spinner" /> : <FileDown size={16} />} PDF
        </button>
        <button type="button" className="bouton-secondaire-large calculs-btn" onClick={() => exporter("docx")} disabled={Boolean(export_)}>
          {export_ === "docx" ? <LoaderCircle size={16} className="boutons-flottants__spinner" /> : <FileText size={16} />} Word
        </button>
      </div>
    </section>
  );
}
