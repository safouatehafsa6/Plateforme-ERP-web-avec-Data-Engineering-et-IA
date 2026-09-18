import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Check, Trash2, Plus } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

const LABELS_ACTIONS = {
  consulter: "Consulter",
  creer: "Créer",
  modifier: "Modifier",
  supprimer: "Supprimer",
  valider: "Valider",
  exporter: "Exporter",
};

function enTete(token) {
  return { Authorization: `Bearer ${token}` };
}

export default function RolesPermissions() {
  const { t } = useTranslation();
  const token = localStorage.getItem("token");

  const [roles, setRoles] = useState([]);
  const [roleSelectionne, setRoleSelectionne] = useState(null);
  const [matrice, setMatrice] = useState(null);
  const [accordees, setAccordees] = useState(new Set());
  const [chargement, setChargement] = useState(true);
  const [enregistrement, setEnregistrement] = useState(false);
  const [message, setMessage] = useState("");
  const [nouveauNomRole, setNouveauNomRole] = useState("");

  async function chargerRoles() {
    setChargement(true);
    try {
      const res = await fetch(`${API_BASE_URL}/roles`, { headers: enTete(token) });
      if (!res.ok) throw new Error("Impossible de charger les rôles.");
      const data = await res.json();
      setRoles(data.roles || []);
      if (data.roles?.length && !roleSelectionne) {
        setRoleSelectionne(data.roles[0].id);
      }
    } catch (err) {
      setMessage(err.message);
    } finally {
      setChargement(false);
    }
  }

  async function chargerMatrice(roleId) {
    if (!roleId) return;
    const res = await fetch(`${API_BASE_URL}/roles/${roleId}/permissions`, { headers: enTete(token) });
    const data = await res.json();
    setMatrice(data);
    setAccordees(new Set(data.permissions.filter((p) => p.accordee).map((p) => p.id)));
  }

  useEffect(() => { chargerRoles(); }, []);
  useEffect(() => { chargerMatrice(roleSelectionne); }, [roleSelectionne]);

  function basculer(permissionId) {
    setAccordees((prec) => {
      const copie = new Set(prec);
      if (copie.has(permissionId)) copie.delete(permissionId);
      else copie.add(permissionId);
      return copie;
    });
  }

  async function enregistrer() {
    setEnregistrement(true);
    setMessage("");
    try {
      await fetch(`${API_BASE_URL}/roles/${roleSelectionne}/permissions`, {
        method: "PUT",
        headers: { ...enTete(token), "Content-Type": "application/json" },
        body: JSON.stringify({ permissionIds: [...accordees] }),
      });
      setMessage(t("permissions_enregistrees"));
    } finally {
      setEnregistrement(false);
    }
  }

  async function creerRole(e) {
    e.preventDefault();
    if (!nouveauNomRole.trim()) return;
    const res = await fetch(`${API_BASE_URL}/roles`, {
      method: "POST",
      headers: { ...enTete(token), "Content-Type": "application/json" },
      body: JSON.stringify({ nom: nouveauNomRole }),
    });
    if (res.ok) {
      setNouveauNomRole("");
      await chargerRoles();
    }
  }

  async function supprimerRole(roleId) {
    const res = await fetch(`${API_BASE_URL}/roles/${roleId}`, {
      method: "DELETE",
      headers: enTete(token),
    });
    if (res.ok) {
      if (roleSelectionne === roleId) setRoleSelectionne(null);
      chargerRoles();
    } else {
      const data = await res.json().catch(() => ({}));
      setMessage(data.detail || t("erreur_suppression_role"));
    }
  }

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-contenu">
        <header className="app-topbar">
          <h1 className="app-main__titre" style={{ margin: 0 }}>{t("roles_permissions_titre")}</h1>
        </header>
        <main className="app-main">
          <div className="rbac-mise-en-page">
            <aside className="rbac-liste-roles">
              <form onSubmit={creerRole} className="rbac-nouveau-role">
                <input
                  placeholder={t("nom_nouveau_role")}
                  value={nouveauNomRole}
                  onChange={(e) => setNouveauNomRole(e.target.value)}
                />
                <button type="submit" className="bouton-mini" aria-label={t("creer_role")}>
                  <Plus size={15} />
                </button>
              </form>

              {chargement ? (
                <p>{t("chargement")}</p>
              ) : (
                <ul className="rbac-roles">
                  {roles.map((r) => (
                    <li key={r.id}>
                      <button
                        className={`rbac-role-item${roleSelectionne === r.id ? " rbac-role-item--actif" : ""}`}
                        onClick={() => setRoleSelectionne(r.id)}
                      >
                        <span>{r.nom}</span>
                        <span className="rbac-role-item__compteur">{r.nb_utilisateurs}</span>
                      </button>
                      {r.nom !== "Admin" && (
                        <button
                          className="rbac-role-supprimer"
                          onClick={() => supprimerRole(r.id)}
                          aria-label={t("supprimer_role")}
                          title={t("supprimer_role")}
                        >
                          <Trash2 size={14} />
                        </button>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </aside>

            <section className="rbac-matrice-zone">
              {message && <div className="info-message">{message}</div>}

              {matrice && (
                <>
                  <table className="table-matrice">
                    <thead>
                      <tr>
                        <th>{t("colonne_module")}</th>
                        {matrice.actions.map((a) => (
                          <th key={a}>{LABELS_ACTIONS[a] || a}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {matrice.modules.map((module) => (
                        <tr key={module}>
                          <td className="table-matrice__module">{module}</td>
                          {matrice.actions.map((action) => {
                            const perm = matrice.permissions.find((p) => p.module === module && p.action === action);
                            if (!perm) return <td key={action}>—</td>;
                            const coche = accordees.has(perm.id);
                            return (
                              <td key={action}>
                                <button
                                  type="button"
                                  className={`rbac-case${coche ? " rbac-case--coche" : ""}`}
                                  onClick={() => basculer(perm.id)}
                                  aria-pressed={coche}
                                  aria-label={`${module} — ${action}`}
                                >
                                  {coche && <Check size={13} strokeWidth={3} />}
                                </button>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  <button className="bouton-principal" style={{ marginTop: "1.2rem", maxWidth: "220px" }} onClick={enregistrer} disabled={enregistrement}>
                    {enregistrement ? "..." : t("bouton_enregistrer")}
                  </button>
                </>
              )}
            </section>
          </div>
        </main>
      </div>
    </div>
  );
}
