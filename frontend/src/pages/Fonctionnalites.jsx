import { useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ShoppingCart, Truck, Boxes, FileCheck2, Sparkles, BarChart3, ShieldCheck, Users,
} from "lucide-react";
import FondAnime from "../components/FondAnime";
import Apparition from "../components/Apparition";

const FONCTIONNALITES = [
  { cle: "ventes", Icone: ShoppingCart },
  { cle: "achats", Icone: Truck },
  { cle: "stock", Icone: Boxes },
  { cle: "factures", Icone: FileCheck2 },
  { cle: "assistant", Icone: Sparkles },
  { cle: "data", Icone: BarChart3 },
  { cle: "roles", Icone: ShieldCheck },
  { cle: "portail", Icone: Users },
];

// Suit la souris pour éclairer la carte (variables CSS --mx / --my).
function suivreSouris(e) {
  const r = e.currentTarget.getBoundingClientRect();
  e.currentTarget.style.setProperty("--mx", `${e.clientX - r.left}px`);
  e.currentTarget.style.setProperty("--my", `${e.clientY - r.top}px`);
}

// Page publique : présente les modules réellement disponibles dans la plateforme.
export default function Fonctionnalites() {
  const { t } = useTranslation();
  const [actif, setActif] = useState("ventes");
  const courant = FONCTIONNALITES.find((f) => f.cle === actif);

  return (
    <div className="vitrine-page">
      <FondAnime />
      <main className="vitrine">
        <h1 className="vitrine__titre vitrine__titre--anime">{t("feat_titre")}</h1>
        <p className="vitrine__intro vitrine__intro--anime">{t("feat_intro")}</p>

        <div className="feat-grille">
          {FONCTIONNALITES.map(({ cle, Icone }, i) => (
            <Apparition key={cle} delai={i * 70}>
              <button
                type="button"
                className={`feat-carte ${actif === cle ? "feat-carte--active" : ""}`}
                aria-pressed={actif === cle}
                onClick={() => setActif(cle)}
                onMouseMove={suivreSouris}
              >
                <span className="feat-carte__icone"><Icone size={24} /></span>
                <span className="feat-carte__titre">{t(`feat_${cle}_t`)}</span>
              </button>
            </Apparition>
          ))}
        </div>

        <section className="feat-detail" key={actif} aria-live="polite">
          <div className="feat-detail__texte">
            <span className="feat-detail__icone"><courant.Icone size={34} /></span>
            <h2>{t(`feat_${actif}_t`)}</h2>
            <p>{t(`feat_${actif}_d`)}</p>
            <Link to="/inscription" className="vitrine__bouton vitrine__bouton--anime">
              {t("feat_cta")}
            </Link>
          </div>
          <div className="feat-detail__visuel" aria-hidden="true">
            {[55, 80, 40, 95, 65, 85].map((h, i) => (
              <span key={i} style={{ "--h": `${h}%`, animationDelay: `${i * 90}ms` }} />
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}
