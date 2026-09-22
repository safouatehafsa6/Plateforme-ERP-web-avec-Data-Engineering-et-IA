import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { ShieldCheck, ShieldX } from "lucide-react";
import { API_BASE_URL } from "../api/config";

function formatMontant(montant) {
  return new Intl.NumberFormat("fr-MA", { minimumFractionDigits: 2 }).format(montant || 0) + " MAD";
}

function formatDate(valeur) {
  if (!valeur) return "—";
  return new Date(valeur).toLocaleDateString("fr-FR");
}

// Page PUBLIQUE (aucune connexion requise) : atteinte en scannant le QR
// code imprimé sur une facture PDF téléchargée depuis le portail. Voir
// backend/app/routers/verification.py pour la route correspondante.
export default function VerificationDocument() {
  const { nomBase, code } = useParams();
  const [resultat, setResultat] = useState(null);
  const [chargement, setChargement] = useState(true);

  useEffect(() => {
    async function verifier() {
      setChargement(true);
      try {
        const res = await fetch(`${API_BASE_URL}/verifier/${nomBase}/${code}`);
        if (!res.ok) {
          setResultat({ authentique: false });
        } else {
          setResultat(await res.json());
        }
      } catch {
        setResultat({ authentique: false });
      } finally {
        setChargement(false);
      }
    }
    verifier();
  }, [nomBase, code]);

  return (
    <div className="portail-layout">
      <header className="portail-topbar">
        <div className="portail-topbar__marque">BENJEDDOU ERP — Vérification de Document</div>
      </header>

      <main className="portail-main">
        <div className="portail-carte" style={{ textAlign: "center" }}>
          {chargement ? (
            <p>Vérification en cours...</p>
          ) : resultat?.authentique ? (
            <>
              <ShieldCheck size={48} color="var(--teal)" style={{ marginBottom: "0.5rem" }} />
              <h1 style={{ color: "var(--teal)" }}>Document authentique</h1>
              <p style={{ color: "var(--text-muted)" }}>
                Ce document a bien été émis par <strong>{resultat.entreprise}</strong>.
              </p>
              <table style={{ margin: "1.2rem auto 0", textAlign: "left" }}>
                <tbody>
                  <tr><td style={{ paddingRight: "1rem", color: "var(--text-muted)" }}>Numéro</td><td><strong>{resultat.numero}</strong></td></tr>
                  <tr><td style={{ paddingRight: "1rem", color: "var(--text-muted)" }}>Date</td><td>{formatDate(resultat.dateFacture)}</td></tr>
                  <tr><td style={{ paddingRight: "1rem", color: "var(--text-muted)" }}>Montant</td><td>{formatMontant(resultat.montantTotal)}</td></tr>
                  <tr><td style={{ paddingRight: "1rem", color: "var(--text-muted)" }}>Statut</td><td>{resultat.statut}</td></tr>
                </tbody>
              </table>
            </>
          ) : (
            <>
              <ShieldX size={48} color="var(--danger)" style={{ marginBottom: "0.5rem" }} />
              <h1 style={{ color: "var(--danger)" }}>Document non reconnu</h1>
              <p style={{ color: "var(--text-muted)" }}>
                Ce lien ne correspond à aucun document authentique de la plateforme.
              </p>
            </>
          )}
        </div>

        <p style={{ textAlign: "center" }}>
          <Link to="/" className="lien-secondaire">Retour à l'accueil</Link>
        </p>
      </main>
    </div>
  );
}
