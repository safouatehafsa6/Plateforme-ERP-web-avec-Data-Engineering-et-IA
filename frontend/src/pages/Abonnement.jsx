import { useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { apiPost } from "../api/config";
import ReseauDecoratif from "../components/ReseauDecoratif";

const PLANS = [
  {
    id: "standard",
    nom: "Standard",
    prix: "299 MAD / mois",
    avantages: [
      "Accès illimité à la plateforme",
      "Tous les modules ERP cœur",
      "Support par email",
    ],
  },
  {
    id: "premium",
    nom: "Premium",
    prix: "699 MAD / mois",
    avantages: [
      "Tout le contenu du plan Standard",
      "Module Data Engineering et tableaux de bord avancés",
      "Assistant IA et automatisation documentaire",
      "Support prioritaire",
    ],
  },
];

export default function Abonnement() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const emailInitial = params.get("email") || "";

  const [email, setEmail] = useState(emailInitial);
  const [planChoisi, setPlanChoisi] = useState(null);
  const [enCours, setEnCours] = useState(false);
  const [erreur, setErreur] = useState("");
  const [succes, setSucces] = useState(false);

  async function gererSouscription(plan) {
    if (!email.trim()) {
      setErreur("Merci de renseigner l'adresse email associée à votre compte.");
      return;
    }
    setErreur("");
    setEnCours(true);
    setPlanChoisi(plan.id);
    try {
      // Paiement volontairement simplifié/simulé à ce stade du projet :
      // dans une version de production, une étape de paiement réelle
      // (carte bancaire, virement) interviendrait avant l'activation.
      await apiPost("/entreprises/souscrire", { email: email.trim().toLowerCase(), plan: plan.id });
      setSucces(true);
      setTimeout(() => navigate("/"), 2000);
    } catch (err) {
      setErreur(err.data?.message || "Une erreur est survenue.");
    } finally {
      setEnCours(false);
    }
  }

  return (
    <div className="connexion-layout">
      <aside className="connexion-marque">
        <ReseauDecoratif />
        <div className="connexion-marque__corps">
          <h1 className="connexion-marque__titre">Passez à un abonnement</h1>
          <p className="connexion-marque__texte">
            Continuez à utiliser votre environnement ERP sans limite, avec
            l'ensemble de vos données déjà créées, conservées intactes.
          </p>
        </div>
        <div className="connexion-marque__pied">© 2026 — Plateforme ERP SaaS</div>
      </aside>

      <div className="connexion-formulaire-zone">
        <div className="connexion-formulaire" style={{ maxWidth: "480px" }}>
          {erreur && <div className="erreur-message">{erreur}</div>}

          {succes ? (
            <div className="confirmation-finale">
              <CheckCircle2 size={32} strokeWidth={1.75} />
              <h1>Abonnement activé</h1>
              <p className="connexion-formulaire__soustitre">
                Redirection vers la page de connexion...
              </p>
            </div>
          ) : (
            <>
              <h1>Choisissez votre abonnement</h1>
              <p className="connexion-formulaire__soustitre">
                Toutes vos données restent disponibles, quel que soit le plan choisi.
              </p>

              <div className="champ">
                <label>Adresse email de votre compte</label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                />
              </div>

              <div className="plans-grille" style={{ gridTemplateColumns: "1fr", gap: "0.75rem" }}>
                {PLANS.map((plan) => (
                  <div key={plan.id} className="plan-carte" style={{ textAlign: "left" }}>
                    <div className="plan-carte__nom">{plan.nom}</div>
                    <div className="plan-carte__prix">{plan.prix}</div>
                    <ul style={{ margin: "0.6rem 0", paddingLeft: "1.1rem", fontSize: "0.85rem" }}>
                      {plan.avantages.map((a) => (
                        <li key={a}>{a}</li>
                      ))}
                    </ul>
                    <button
                      type="button"
                      className="bouton-principal"
                      onClick={() => gererSouscription(plan)}
                      disabled={enCours}
                    >
                      {enCours && planChoisi === plan.id ? "..." : `Souscrire à ${plan.nom}`}
                    </button>
                  </div>
                ))}
              </div>

              <Link className="lien-secondaire" to="/" style={{ display: "block", marginTop: "1rem" }}>
                Retour à la connexion
              </Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
