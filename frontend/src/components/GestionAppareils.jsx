import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Monitor, Smartphone, ShieldAlert } from "lucide-react";
import {
  actionAppareil,
  actionAppareilEntreprise,
  listerAppareilsEntreprise,
  listerMesAppareils,
  supprimerAppareil,
  supprimerAppareilEntreprise,
} from "../api/sessionsApi";

const LIBELLES_STATUT = {
  autorise: "Autorisé",
  bloque: "Bloqué",
  en_attente: "En attente",
};

function formaterDate(iso) {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

// Gestion des appareils connus : les miens (admin = false) ou ceux de toute
// l'entreprise (admin = true, réservé à l'administrateur). Toutes les règles
// sont revérifiées côté serveur.
export default function GestionAppareils({ admin = false }) {
  const navigate = useNavigate();
  const [appareils, setAppareils] = useState([]);
  const [erreur, setErreur] = useState("");
  const [info, setInfo] = useState("");

  const charger = useCallback(async () => {
    try {
      const data = admin ? await listerAppareilsEntreprise() : await listerMesAppareils();
      setAppareils(data.appareils);
      setErreur("");
    } catch (e) {
      if (e.status === 401) navigate("/");
      else setErreur(e.message);
    }
  }, [admin, navigate]);

  useEffect(() => {
    charger();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function agir(appareil, action, confirmation) {
    if (confirmation && !window.confirm(confirmation)) return;
    setErreur("");
    setInfo("");
    try {
      let rep;
      if (action === "supprimer") {
        rep = await (admin ? supprimerAppareilEntreprise : supprimerAppareil)(appareil.id);
      } else {
        rep = await (admin ? actionAppareilEntreprise : actionAppareil)(appareil.id, action);
      }
      setInfo(rep.message);
      await charger();
    } catch (e) {
      if (e.status === 401) navigate("/");
      else setErreur(e.message);
    }
  }

  return (
    <section className="panel appareils-section">
      <div className="appareils-section__entete">
        <h2>
          <ShieldAlert size={18} /> {admin ? "Appareils de l’entreprise" : "Appareils enregistrés"}
        </h2>
      </div>
      <p className="parametres-muted">
        {admin
          ? "Tous les appareils connus des collaborateurs et utilisateurs externes. Bloquer un appareil ferme immédiatement ses sessions."
          : "Les appareils depuis lesquels votre compte s’est connecté. Bloquez ceux que vous ne reconnaissez pas."}
      </p>

      {erreur && <div className="erreur-message">{erreur}</div>}
      {info && <div className="appareils-info">{info}</div>}
      {appareils.length === 0 && !erreur && <p className="parametres-muted">Aucun appareil enregistré.</p>}

      <ul className="appareils-liste">
        {appareils.map((a) => (
          <li key={a.id} className="appareils-item">
            {a.typeAppareil === "mobile" ? <Smartphone size={22} /> : <Monitor size={22} />}
            <div className="appareils-item__corps">
              <strong>
                {admin ? `${a.email} · ` : ""}
                {a.nom}
                {a.courant && <span className="appareils-badge">Cet appareil</span>}
                <span
                  className="appareils-badge appareils-badge--neutre"
                  style={a.statut === "bloque" ? { background: "#fde2e2", color: "#a61b1b" } : undefined}
                >
                  {LIBELLES_STATUT[a.statut] || a.statut}
                </span>
              </strong>
              <span>
                IP {a.adresseIp || "inconnue"} · vu pour la première fois le {formaterDate(a.premiereVue)}
              </span>
              <span>
                Dernière connexion : {formaterDate(a.derniereVue)} · {a.sessionsActives} session(s) active(s)
              </span>
            </div>
            <div className="appareils-actions">
              {a.statut === "en_attente" && (
                <button type="button" className="appareils-bouton" onClick={() => agir(a, "autoriser")}>
                  Autoriser
                </button>
              )}
              {a.statut === "bloque" && (
                <button type="button" className="appareils-bouton" onClick={() => agir(a, "reactiver")}>
                  Réactiver
                </button>
              )}
              {!a.courant && a.statut !== "bloque" && (
                <button
                  type="button"
                  className="appareils-bouton"
                  disabled={a.sessionsActives === 0}
                  onClick={() => agir(a, "deconnecter", "Déconnecter cet appareil à distance ?")}
                >
                  Déconnecter
                </button>
              )}
              {!a.courant && a.statut !== "bloque" && (
                <button
                  type="button"
                  className="appareils-bouton appareils-bouton--danger"
                  onClick={() => agir(a, "bloquer", "Bloquer cet appareil ? Ses sessions seront fermées et il ne pourra plus se connecter.")}
                >
                  Bloquer
                </button>
              )}
              {!a.courant && (
                <button
                  type="button"
                  className="appareils-bouton"
                  onClick={() => agir(a, "supprimer", "Supprimer cet appareil de la liste ? Ses sessions seront fermées.")}
                >
                  Supprimer
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
