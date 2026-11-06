import { useState } from "react";
import { X } from "lucide-react";
import { validerMotifArchivage } from "../validation/prospect";

/** Demande le motif d'un archivage. L'archivage est logique : l'historique reste intact et la fiche peut être réactivée. */
export default function ArchivageDialog({ titre, onClose, onConfirmer }) {
  const [motif, setMotif] = useState("");
  const [erreur, setErreur] = useState("");
  const [envoi, setEnvoi] = useState(false);

  async function valider(e) {
    e.preventDefault();
    const probleme = validerMotifArchivage(motif);
    if (probleme) { setErreur(probleme); return; }
    setEnvoi(true);
    try { await onConfirmer(motif.trim()); }
    catch (err) { setErreur(err.message); setEnvoi(false); }
  }

  return (
    <div className="clients-overlay" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }} style={{ zIndex: 1300 }}>
      <form className="panel clients-fiche" role="dialog" aria-modal="true" aria-labelledby="archivage-titre" onSubmit={valider} noValidate style={{ maxWidth: 480 }}>
        <div className="achats-form__entete">
          <h3 id="archivage-titre">{titre}</h3>
          <button type="button" className="achats-icon-btn" onClick={onClose} aria-label="Fermer"><X size={18} /></button>
        </div>
        <p className="achats-muted">L'historique est conservé. Vous pourrez réactiver la fiche à tout moment.</p>
        {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
        <div className="champ">
          <label htmlFor="archivage-motif">Motif *</label>
          <textarea id="archivage-motif" rows={3} value={motif} maxLength={1000} onChange={(e) => { setMotif(e.target.value); setErreur(""); }} autoFocus />
        </div>
        <div className="clients-fiche__footer">
          <button type="button" className="bouton-secondaire-large" onClick={onClose} disabled={envoi}>Annuler</button>
          <button className="bouton-principal achats-btn-auto" disabled={envoi}>{envoi ? "Archivage…" : "Archiver"}</button>
        </div>
      </form>
    </div>
  );
}
