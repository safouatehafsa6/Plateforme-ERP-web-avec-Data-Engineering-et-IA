import { useEffect, useMemo, useState } from "react";
import { Calculator } from "lucide-react";
import Sidebar from "../components/Sidebar";
import FormulaireCalcul from "../components/calculs/FormulaireCalcul";
import Historique from "../components/calculs/Historique";
import ReferentielTaux from "../components/calculs/ReferentielTaux";
import { apiCalculs } from "../api/calculs";
import { estAdminEntreprise, lireSession } from "../api/session";

// Moteur de calcul métier centralisé : calculs basés sur une période et un taux (%).
export default function Calculs() {
  const session = useMemo(() => lireSession(), []);
  const admin = estAdminEntreprise(session);
  const [onglet, setOnglet] = useState("unique");
  const [edition, setEdition] = useState(null);
  const [modules, setModules] = useState([{ code: "general", libelle: "Général" }]);
  const [devises, setDevises] = useState(["MAD", "DT", "EUR", "USD"]);
  const [erreur, setErreur] = useState("");

  useEffect(() => {
    apiCalculs("/modules").then((r) => { setModules(r.modules); setDevises(r.devises); }).catch((e) => setErreur(e.message));
  }, []);

  const onglets = [
    { id: "unique", label: "Taux unique" },
    { id: "variable", label: "Taux variables" },
    { id: "historique", label: "Historique" },
    ...(admin ? [{ id: "referentiel", label: "Périodes et taux" }] : []),
  ];

  function modifier(calcul) {
    setEdition(calcul);
    setOnglet(calcul.mode === "taux_unique" ? "unique" : "variable");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
  function changerOnglet(id) { setEdition(null); setOnglet(id); }

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-contenu">
        <main className="app-main calculs-page">
          <h1 className="app-main__titre"><Calculator size={26} /> Calculs</h1>
          <p className="calculs-muted">Calculs basés sur une période et un taux (%), réutilisables par tous les modules. Chaque calcul est enregistré avec son détail complet.</p>
          {erreur && <div className="erreur-message" role="alert">{erreur}</div>}
          <div className="support-onglets" role="tablist">
            {onglets.map((o) => <button key={o.id} type="button" role="tab" aria-selected={onglet === o.id} onClick={() => changerOnglet(o.id)}>{o.label}</button>)}
          </div>

          {onglet === "unique" && <FormulaireCalcul key={edition?.id ? `e${edition.id}` : "u"} mode="taux_unique" initial={edition} modules={modules} devises={devises}
            onSaved={() => {}} onAnnuler={edition ? () => { setEdition(null); setOnglet("historique"); } : null} />}
          {onglet === "variable" && <FormulaireCalcul key={edition?.id ? `e${edition.id}` : "v"} mode="taux_variable" initial={edition} modules={modules} devises={devises}
            onSaved={() => {}} onAnnuler={edition ? () => { setEdition(null); setOnglet("historique"); } : null} />}
          {onglet === "historique" && <Historique modules={modules} onModifier={modifier} />}
          {onglet === "referentiel" && admin && <ReferentielTaux />}
        </main>
      </div>
    </div>
  );
}
