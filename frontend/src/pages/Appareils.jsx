import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Monitor, Smartphone, ShieldCheck, LogOut, Users } from "lucide-react";
import { estAdminEntreprise, lireSession } from "../api/session";
import {
  deconnecter,
  fermerLesAutresSessions,
  fermerMaSession,
  fermerSessionEntreprise,
  fermerSessionsUtilisateur,
  listerMesSessions,
  listerSessionsEntreprise,
} from "../api/sessionsApi";
import ActiviteRecente from "../components/ActiviteRecente";

function formaterDate(iso) {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function IconeAppareil({ appareil }) {
  return appareil === "mobile" ? <Smartphone size={22} /> : <Monitor size={22} />;
}

export default function Appareils() {
  const navigate = useNavigate();
  const session = lireSession();
  const admin = estAdminEntreprise(session);

  const [mesSessions, setMesSessions] = useState([]);
  const [sessionsEntreprise, setSessionsEntreprise] = useState([]);
  const [erreur, setErreur] = useState("");
  const [info, setInfo] = useState("");
  const [chargement, setChargement] = useState(true);

  const charger = useCallback(async () => {
    try {
      const mes = await listerMesSessions();
      setMesSessions(mes.sessions);
      if (admin) {
        const ent = await listerSessionsEntreprise();
        setSessionsEntreprise(ent.sessions);
      }
      setErreur("");
    } catch (e) {
      if (e.status === 401) {
        navigate("/");
        return;
      }
      setErreur(e.message);
    } finally {
      setChargement(false);
    }
  }, [admin, navigate]);

  useEffect(() => {
    if (!session) {
      navigate("/");
      return;
    }
    charger();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function executer(action, confirmation, messageSucces) {
    if (confirmation && !window.confirm(confirmation)) return;
    setErreur("");
    setInfo("");
    try {
      await action();
      if (messageSucces) setInfo(messageSucces);
      await charger();
    } catch (e) {
      if (e.status === 401) navigate("/");
      else setErreur(e.message);
    }
  }

  async function fermerMienne(s) {
    if (s.courante) {
      if (!window.confirm("Fermer la session de cet appareil vous déconnectera. Continuer ?")) return;
      await deconnecter();
      navigate("/");
      return;
    }
    executer(() => fermerMaSession(s.id), null, "Session fermée.");
  }

  return (
    <main className="page-shell appareils-page">
      <div className="page-head">
        <div>
          <h1><ShieldCheck size={24} /> Mes appareils</h1>
          <p>Les appareils actuellement connectés à votre compte. Fermez ceux que vous ne reconnaissez pas.</p>
        </div>
      </div>

      {erreur && <div className="erreur-message">{erreur}</div>}
      {info && <div className="appareils-info">{info}</div>}

      <section className="panel appareils-section">
        <div className="appareils-section__entete">
          <h2>Sessions actives</h2>
          {mesSessions.length > 1 && (
            <button
              type="button"
              className="appareils-bouton"
              onClick={() =>
                executer(
                  fermerLesAutresSessions,
                  "Fermer toutes les autres sessions ?",
                  "Les autres sessions ont été fermées."
                )
              }
            >
              <LogOut size={16} /> Fermer toutes les autres
            </button>
          )}
        </div>

        {chargement && <p className="parametres-muted">Chargement…</p>}
        {!chargement && mesSessions.length === 0 && <p className="parametres-muted">Aucune session active.</p>}

        <ul className="appareils-liste">
          {mesSessions.map((s) => (
            <li key={s.id} className="appareils-item">
              <IconeAppareil appareil={s.appareil} />
              <div className="appareils-item__corps">
                <strong>
                  {s.navigateur} sur {s.systeme}
                  {s.courante && <span className="appareils-badge">Cet appareil</span>}
                </strong>
                <span>IP {s.adresseIp || "inconnue"} · connecté le {formaterDate(s.creeLe)}</span>
                <span>Dernière activité : {formaterDate(s.derniereActivite)}</span>
              </div>
              <button type="button" className="appareils-bouton" onClick={() => fermerMienne(s)}>
                {s.courante ? "Se déconnecter" : "Fermer"}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <ActiviteRecente />
      {admin && <ActiviteRecente admin />}

      {admin && (
        <section className="panel appareils-section">
          <div className="appareils-section__entete">
            <h2><Users size={18} /> Sessions de l’entreprise</h2>
          </div>
          <p className="parametres-muted">
            Toutes les sessions actives des collaborateurs et utilisateurs externes de votre entreprise.
          </p>

          {sessionsEntreprise.length === 0 && <p className="parametres-muted">Aucune session active.</p>}

          <ul className="appareils-liste">
            {sessionsEntreprise.map((s) => (
              <li key={s.id} className="appareils-item">
                <IconeAppareil appareil={s.appareil} />
                <div className="appareils-item__corps">
                  <strong>
                    {s.email}
                    <span className="appareils-badge appareils-badge--neutre">
                      {s.typeCompte === "externe" ? "Externe" : "Interne"}
                    </span>
                    {s.courante && <span className="appareils-badge">Vous</span>}
                  </strong>
                  <span>{s.navigateur} sur {s.systeme} · IP {s.adresseIp || "inconnue"}</span>
                  <span>Dernière activité : {formaterDate(s.derniereActivite)}</span>
                </div>
                <div className="appareils-actions">
                  <button
                    type="button"
                    className="appareils-bouton"
                    onClick={() =>
                      executer(() => fermerSessionEntreprise(s.id), null, "Session fermée.")
                    }
                  >
                    Fermer
                  </button>
                  <button
                    type="button"
                    className="appareils-bouton appareils-bouton--danger"
                    onClick={() =>
                      executer(
                        () => fermerSessionsUtilisateur(s.utilisateurId, s.typeCompte),
                        `Fermer toutes les sessions de ${s.email} ?`,
                        "Toutes les sessions de cet utilisateur ont été fermées."
                      )
                    }
                  >
                    Tout fermer
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
