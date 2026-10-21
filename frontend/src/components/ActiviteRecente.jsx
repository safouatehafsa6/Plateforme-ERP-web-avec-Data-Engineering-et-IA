import { useEffect, useState } from "react";
import { History } from "lucide-react";
import { listerMesEvenements, listerEvenementsEntreprise } from "../api/sessionsApi";

const LIBELLES = {
  connexion_reussie: "Connexion r\u00e9ussie",
  connexion_echouee: "Connexion \u00e9chou\u00e9e",
  deconnexion: "D\u00e9connexion",
  session_revoquee: "Session ferm\u00e9e",
  mdp_reinitialise: "Mot de passe r\u00e9initialis\u00e9",
  action_admin: "Action d\u2019administrateur",
};

function formaterDate(iso) {
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

export default function ActiviteRecente({ admin = false }) {
  const [evenements, setEvenements] = useState([]);
  const [erreur, setErreur] = useState("");

  useEffect(() => {
    let actif = true;
    (admin ? listerEvenementsEntreprise() : listerMesEvenements())
      .then((d) => { if (actif) setEvenements(d.evenements || []); })
      .catch((e) => { if (actif) setErreur(e.message); });
    return () => { actif = false; };
  }, [admin]);

  const titre = admin ? "Journal de s\u00e9curit\u00e9 de l\u2019entreprise" : "Activit\u00e9 r\u00e9cente";

  return (
    <section className="panel appareils-section">
      <div className="appareils-section__entete">
        <h2><History size={18} /> {titre}</h2>
      </div>
      {erreur && <div className="erreur-message">{erreur}</div>}
      {!erreur && evenements.length === 0 && <p className="parametres-muted">{"Aucun \u00e9v\u00e9nement."}</p>}
      <ul className="activite-liste">
        {evenements.map((e) => (
          <li key={e.id} className="activite-item">
            <span className="activite-date">{formaterDate(e.creeLe)}</span>
            <strong className={"activite-gravite--" + e.gravite}>{LIBELLES[e.type] || e.type}</strong>
            {admin && e.email && <span>{e.email}</span>}
            {e.acteur && <span>{"par " + e.acteur}</span>}
            <span className="parametres-muted">
              {(e.navigateur || "") + (e.systeme ? " / " + e.systeme : "") + (e.adresseIp ? " / IP " + e.adresseIp : "")}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}