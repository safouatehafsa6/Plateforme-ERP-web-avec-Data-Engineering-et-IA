import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

export default function AdminAbonnements() {
  const { t } = useTranslation();
  const [entreprises, setEntreprises] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");

  async function charger() {
    setChargement(true);
    setErreur("");
    try {
      const token = localStorage.getItem("token");
      const res = await fetch(`${API_BASE_URL}/admin/entreprises`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Impossible de charger les abonnements.");
      const data = await res.json();
      setEntreprises(data.entreprises);
    } catch (err) {
      setErreur(err.message);
    } finally {
      setChargement(false);
    }
  }

  useEffect(() => {
    charger();
  }, []);

  async function changerStatut(abonnementId, action) {
    const token = localStorage.getItem("token");
    await fetch(`${API_BASE_URL}/admin/abonnements/${abonnementId}/${action}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    charger();
  }

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-contenu">
        <header className="app-topbar">
          <h1 className="app-main__titre" style={{ margin: 0 }}>{t("admin_abonnements_titre")}</h1>
        </header>
        <main className="app-main">
          {erreur && <div className="erreur-message">{erreur}</div>}
          {chargement ? (
            <p>{t("chargement")}</p>
          ) : (
            <table className="table-admin">
              <thead>
                <tr>
                  <th>{t("colonne_entreprise")}</th>
                  <th>{t("colonne_type")}</th>
                  <th>{t("colonne_email")}</th>
                  <th>{t("colonne_plan")}</th>
                  <th>{t("colonne_statut_abonnement")}</th>
                  <th>{t("colonne_action")}</th>
                </tr>
              </thead>
              <tbody>
                {entreprises.map((e) => (
                  <tr key={e.id}>
                    <td>{e.nom}</td>
                    <td>{e.type_compte === "entreprise" ? t("type_entreprise") : t("type_personne_physique")}</td>
                    <td>{e.email_contact}</td>
                    <td>{e.type_plan || "—"}</td>
                    <td>
                      <span className={`badge-statut badge-statut--${e.statut_abonnement}`}>
                        {e.statut_abonnement || "—"}
                      </span>
                    </td>
                    <td>
                      {e.abonnement_id && (
                        e.statut_abonnement === "suspendu" ? (
                          <button className="bouton-mini" onClick={() => changerStatut(e.abonnement_id, "reactiver")}>
                            {t("bouton_reactiver")}
                          </button>
                        ) : (
                          <button className="bouton-mini bouton-mini--danger" onClick={() => changerStatut(e.abonnement_id, "suspendre")}>
                            {t("bouton_suspendre")}
                          </button>
                        )
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </main>
      </div>
    </div>
  );
}
