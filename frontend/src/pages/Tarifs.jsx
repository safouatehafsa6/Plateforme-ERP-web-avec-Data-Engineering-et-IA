import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";
import FondAnime from "../components/FondAnime";
import Apparition from "../components/Apparition";

function suivreSouris(e) {
  const r = e.currentTarget.getBoundingClientRect();
  e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
  e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
}

// Page publique : réutilise les plans et prix déjà définis pour l'inscription
// (clés plan_*), afin qu'il n'y ait qu'une seule source de vérité.
export default function Tarifs() {
  const { t } = useTranslation();
  const plans = [
    { id: "essai", nom: t("plan_essai_nom"), prix: "0 MAD", duree: t("plan_essai_duree"), avantage: t("plan_essai_avantage") },
    { id: "standard", nom: t("plan_standard_nom"), prix: t("plan_standard_prix"), duree: t("plan_standard_duree"), avantage: t("plan_standard_avantage"), vedette: true },
    { id: "premium", nom: t("plan_premium_nom"), prix: t("plan_premium_prix"), duree: t("plan_premium_duree"), avantage: t("plan_premium_avantage") },
  ];
  return (
    <div className="vitrine-page">
      <FondAnime />
      <main className="vitrine">
        <h1 className="vitrine__titre vitrine__titre--anime">{t("tarifs_titre")}</h1>
        <p className="vitrine__intro vitrine__intro--anime">{t("tarifs_intro")}</p>

        <div className="vitrine-plans">
          {plans.map((plan, i) => (
            <Apparition key={plan.id} delai={i * 120}>
              <section
                className={`vitrine-plan vitrine-plan--anime ${plan.vedette ? "vitrine-plan--vedette" : ""}`}
                onMouseMove={suivreSouris}
              >
                {plan.vedette && <span className="vitrine-plan__badge">{t("tarifs_populaire")}</span>}
                <h2>{plan.nom}</h2>
                <p className="vitrine-plan__prix">{plan.prix}</p>
                <p className="vitrine-plan__duree">{plan.duree}</p>
                <p className="vitrine-plan__avantage"><Check size={16} /> {plan.avantage}</p>
                <Link to="/inscription" className="vitrine__bouton vitrine__bouton--anime">{t("tarifs_cta")}</Link>
              </section>
            </Apparition>
          ))}
        </div>
      </main>
    </div>
  );
}
