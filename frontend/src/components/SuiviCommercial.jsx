import { useState } from "react";
import { MessageSquarePlus } from "lucide-react";
import {
  LIBELLES_EVENEMENTS, TYPES_SUIVI, formaterDateHeure, resumeEvenement, validerSuivi, versIsoUtc,
} from "../validation/prospect";

const VIDE = { type_evenement: "appel", contenu: "", date_evenement: "", prochaine_relance: "" };

/** Historique commercial daté (le plus récent d'abord) + formulaire d'ajout. L'historique n'est jamais modifiable. */
export default function SuiviCommercial({ historique = [], peutAjouter = false, avecRelance = false, contexteClient = false, onAjouter }) {
  const [form, setForm] = useState(VIDE);
  const [erreurs, setErreurs] = useState({});
  const [erreurServeur, setErreurServeur] = useState("");
  const [envoi, setEnvoi] = useState(false);

  function change(e) {
    setForm((f) => ({ ...f, [e.target.name]: e.target.value }));
    setErreurs((er) => ({ ...er, [e.target.name]: undefined }));
    setErreurServeur("");
  }

  async function envoyer(e) {
    e.preventDefault();
    const problemes = validerSuivi(form);
    if (Object.keys(problemes).length) { setErreurs(problemes); return; }
    setEnvoi(true);
    try {
      await onAjouter({
        type_evenement: form.type_evenement,
        contenu: form.contenu.trim(),
        date_evenement: versIsoUtc(form.date_evenement),
        ...(avecRelance && form.prochaine_relance ? { prochaine_relance: form.prochaine_relance } : {}),
      });
      setForm(VIDE);
    } catch (err) { setErreurServeur(err.message); }
    finally { setEnvoi(false); }
  }

  return (
    <section className="suivi" aria-label="Suivi commercial">
      <h3 className="suivi__titre">Suivi commercial</h3>
      {peutAjouter && (
        <form className="suivi__form" onSubmit={envoyer} noValidate>
          {erreurServeur && <div className="erreur-message" role="alert">{erreurServeur}</div>}
          <div className="achats-form-grid">
            <div className="champ">
              <label htmlFor="suivi-type">Type</label>
              <select id="suivi-type" name="type_evenement" value={form.type_evenement} onChange={change}>
                {Object.entries(TYPES_SUIVI).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
              </select>
            </div>
            <div className="champ">
              <label htmlFor="suivi-date">Date et heure (par défaut : maintenant)</label>
              <input id="suivi-date" type="datetime-local" name="date_evenement" value={form.date_evenement} onChange={change} aria-invalid={Boolean(erreurs.date_evenement)} />
              {erreurs.date_evenement && <p className="champ-erreur">{erreurs.date_evenement}</p>}
            </div>
          </div>
          <div className="champ">
            <label htmlFor="suivi-contenu">Compte rendu *</label>
            <textarea id="suivi-contenu" name="contenu" rows={3} maxLength={4000} value={form.contenu} onChange={change} aria-invalid={Boolean(erreurs.contenu)} />
            {erreurs.contenu && <p className="champ-erreur">{erreurs.contenu}</p>}
          </div>
          {avecRelance && (
            <div className="champ">
              <label htmlFor="suivi-relance">Prochaine relance (facultatif)</label>
              <input id="suivi-relance" type="date" name="prochaine_relance" value={form.prochaine_relance} onChange={change} aria-invalid={Boolean(erreurs.prochaine_relance)} />
              {erreurs.prochaine_relance && <p className="champ-erreur">{erreurs.prochaine_relance}</p>}
            </div>
          )}
          <button className="bouton-principal achats-btn-auto" disabled={envoi}><MessageSquarePlus size={15} /> {envoi ? "Enregistrement…" : "Ajouter au suivi"}</button>
        </form>
      )}

      {historique.length === 0 ? <p className="achats-muted">Aucun événement.</p> : (
        <ol className="suivi__liste">
          {historique.map((e) => (
            <li key={e.id} className={`suivi__item suivi__item--${e.type_evenement}`}>
              <div className="suivi__entete">
                <strong>{LIBELLES_EVENEMENTS[e.type_evenement] ?? e.type_evenement}</strong>
                {contexteClient && e.entite_type === "prospect" && <span className="achats-badge">Avant conversion</span>}
                <time dateTime={e.date_evenement}>{formaterDateHeure(e.date_evenement)}</time>
              </div>
              {resumeEvenement(e) && <p className="suivi__texte">{resumeEvenement(e)}</p>}
              <p className="suivi__auteur">{e.auteur_nom ? `Par ${e.auteur_nom}` : ""}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
