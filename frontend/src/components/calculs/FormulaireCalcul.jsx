import { useEffect, useMemo, useState } from "react";
import { Calculator, LoaderCircle } from "lucide-react";
import { apiCalculs, joursPrevus } from "../../api/calculs";
import ResultatCalcul from "./ResultatCalcul";

const aujourdhui = () => new Date().toISOString().slice(0, 10);

// Formulaire commun aux deux modes : « taux_unique » (taux saisi) et « taux_variable »
// (taux récupérés automatiquement dans le référentiel). Sert aussi à modifier un calcul.
export default function FormulaireCalcul({ mode, initial, modules, devises, onSaved, onAnnuler }) {
  const variable = mode === "taux_variable";
  const [form, setForm] = useState(() => ({
    libelle: initial?.libelle || "",
    moduleSource: initial?.moduleSource || "general",
    devise: initial?.devise || "MAD",
    montant: initial?.montant || "",
    dateDebut: initial?.dateDebut || "",
    dateFin: initial?.dateFin || "",
    taux: initial?.taux || "",
    baremeId: initial?.baremeId || "",
    inclureDernierJour: initial ? initial.inclureDernierJour : variable,
  }));
  const [baremes, setBaremes] = useState([]);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState("");
  const [resultat, setResultat] = useState(null);

  useEffect(() => {
    if (!variable) return;
    apiCalculs("/referentiel/baremes").then((r) => setBaremes((r.baremes || []).filter((b) => b.actif))).catch((e) => setErreur(e.message));
  }, [variable]);

  const jours = useMemo(() => joursPrevus(form.dateDebut, form.dateFin, form.inclureDernierJour), [form.dateDebut, form.dateFin, form.inclureDernierJour]);
  const change = (nom) => (e) => setForm((f) => ({ ...f, [nom]: e.target.type === "checkbox" ? e.target.checked : e.target.value }));

  async function soumettre(e) {
    e.preventDefault();
    setEnvoi(true); setErreur(""); setResultat(null);
    const corps = {
      montant: form.montant, dateDebut: form.dateDebut, dateFin: form.dateFin, libelle: form.libelle || null,
      moduleSource: form.moduleSource, devise: form.devise, inclureDernierJour: form.inclureDernierJour,
      ...(variable ? { baremeId: form.baremeId ? Number(form.baremeId) : null } : { taux: form.taux }),
    };
    try {
      const url = variable ? "/taux-variable" : "/taux-unique";
      const calcul = await apiCalculs(initial ? `${url}/${initial.id}` : url, { method: initial ? "PUT" : "POST", body: JSON.stringify(corps) });
      setResultat(calcul);
      onSaved?.(calcul);
    } catch (err) { setErreur(err.message); } finally { setEnvoi(false); }
  }

  return (
    <>
      <form className="panel calculs-form" onSubmit={soumettre}>
        <h2>{initial ? `Modifier le calcul ${initial.reference}` : variable ? "Calcul à taux variables" : "Calcul à taux unique"}</h2>
        <p className="calculs-muted">
          {variable
            ? "Saisissez le montant et la période globale : les périodes et les taux applicables sont récupérés automatiquement dans le référentiel, puis le calcul est découpé période par période."
            : "Résultat = Montant × (Taux / 100) × (Nombre de jours / 365)."}
        </p>
        {erreur && <div className="erreur-message" role="alert">{erreur}</div>}

        <div className="calculs-grille">
          <div className="champ calculs-large"><label htmlFor="c-libelle">Objet du calcul (facultatif)</label>
            <input id="c-libelle" value={form.libelle} onChange={change("libelle")} maxLength={200} placeholder="Ex. : intérêts sur avance client" /></div>
          <div className="champ"><label htmlFor="c-module">Module concerné</label>
            <select id="c-module" value={form.moduleSource} onChange={change("moduleSource")}>
              {modules.map((m) => <option key={m.code} value={m.code}>{m.libelle}</option>)}
            </select></div>
          <div className="champ"><label htmlFor="c-devise">Devise</label>
            <select id="c-devise" value={form.devise} onChange={change("devise")}>{devises.map((d) => <option key={d}>{d}</option>)}</select></div>
          <div className="champ"><label htmlFor="c-montant">Montant *</label>
            <input id="c-montant" type="number" min="0.01" step="0.01" required value={form.montant} onChange={change("montant")} inputMode="decimal" /></div>
          {!variable && (
            <div className="champ"><label htmlFor="c-taux">Taux (%) *</label>
              <input id="c-taux" type="number" min="0" max="100" step="0.0001" required value={form.taux} onChange={change("taux")} inputMode="decimal" /></div>
          )}
          {variable && (
            <div className="champ"><label htmlFor="c-bareme">Barème de taux</label>
              <select id="c-bareme" value={form.baremeId} onChange={change("baremeId")}>
                <option value="">Barème par défaut</option>
                {baremes.map((b) => <option key={b.id} value={b.id}>{b.libelle} ({b.nbPeriodes} périodes)</option>)}
              </select></div>
          )}
          <div className="champ"><label htmlFor="c-debut">Date de début *</label>
            <input id="c-debut" type="date" required value={form.dateDebut} max="2999-12-31" onChange={change("dateDebut")} /></div>
          <div className="champ"><label htmlFor="c-fin">Date de fin *</label>
            <input id="c-fin" type="date" required value={form.dateFin} min={form.dateDebut || undefined} max="2999-12-31" onChange={change("dateFin")} /></div>
        </div>

        <label className="calculs-case">
          <input type="checkbox" checked={form.inclureDernierJour} onChange={change("inclureDernierJour")} />
          <span>Inclure le dernier jour dans le calcul
            <small>Cochée : jours = fin − début + 1. Décochée : jours = fin − début.{jours ? ` Aperçu : ${jours} jour${jours > 1 ? "s" : ""}.` : ""}</small></span>
        </label>

        <div className="calculs-actions">
          <button className="bouton-principal calculs-btn" disabled={envoi}>
            {envoi ? <><LoaderCircle size={16} className="boutons-flottants__spinner" /> Calcul…</> : <><Calculator size={16} /> {initial ? "Enregistrer les modifications" : "Calculer et enregistrer"}</>}
          </button>
          {onAnnuler && <button type="button" className="bouton-secondaire-large calculs-btn" onClick={onAnnuler}>Annuler</button>}
        </div>
      </form>
      {resultat && <ResultatCalcul calcul={resultat} modules={modules} />}
    </>
  );
}
