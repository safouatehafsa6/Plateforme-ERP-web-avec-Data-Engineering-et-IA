import { useEffect, useState } from "react";
import { Search, Bell, Plus, Save } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

function headersAuth() {
  const token = localStorage.getItem("token");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

const LABELS_ACTION = {
  consultation: "Consultation",
  creation: "Création",
  modification: "Modification",
  suppression: "Suppression",
  validation: "Validation",
  export: "Export",
};

export default function RolesPermissions() {
  const [roles, setRoles] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [roleSelectionne, setRoleSelectionne] = useState(null);
  const [permissionsCochees, setPermissionsCochees] = useState(new Set());
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [message, setMessage] = useState("");
  const [enregistrement, setEnregistrement] = useState(false);

  const [afficherFormulaireRole, setAfficherFormulaireRole] = useState(false);
  const [nouveauRoleNom, setNouveauRoleNom] = useState("");

  async function chargerDonnees() {
    setChargement(true);
    setErreur("");
    try {
      const [resRoles, resPermissions] = await Promise.all([
        fetch(`${API_BASE_URL}/roles`, { headers: headersAuth() }),
        fetch(`${API_BASE_URL}/roles/permissions-disponibles`, { headers: headersAuth() }),
      ]);
      if (!resRoles.ok || !resPermissions.ok) throw new Error("Impossible de charger les rôles et permissions.");
      const dataRoles = await resRoles.json();
      const dataPermissions = await resPermissions.json();
      setRoles(dataRoles.roles);
      setPermissions(dataPermissions.permissions);
      if (dataRoles.roles.length > 0) {
        selectionnerRole(dataRoles.roles[0]);
      }
    } catch (e) {
      setErreur(e.message);
    } finally {
      setChargement(false);
    }
  }

  useEffect(() => {
    chargerDonnees();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function selectionnerRole(role) {
    setRoleSelectionne(role);
    setPermissionsCochees(new Set(role.permissionIds));
    setMessage("");
  }

  function basculerPermission(id) {
    setPermissionsCochees((prev) => {
      const suivant = new Set(prev);
      if (suivant.has(id)) suivant.delete(id);
      else suivant.add(id);
      return suivant;
    });
  }

  async function enregistrerPermissions() {
    setEnregistrement(true);
    setErreur("");
    setMessage("");
    try {
      const res = await fetch(`${API_BASE_URL}/roles/${roleSelectionne.id}/permissions`, {
        method: "PUT",
        headers: headersAuth(),
        body: JSON.stringify({ permissionIds: Array.from(permissionsCochees) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Erreur lors de l'enregistrement.");
      setMessage("Permissions enregistrées avec succès.");
      chargerDonnees();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnregistrement(false);
    }
  }

  async function gererCreationRole(e) {
    e.preventDefault();
    setErreur("");
    try {
      const res = await fetch(`${API_BASE_URL}/roles`, {
        method: "POST",
        headers: headersAuth(),
        body: JSON.stringify({ nom: nouveauRoleNom }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Erreur lors de la création du rôle.");
      setNouveauRoleNom("");
      setAfficherFormulaireRole(false);
      chargerDonnees();
    } catch (e) {
      setErreur(e.message);
    }
  }

  // Regroupe les permissions par module, pour construire les lignes de la matrice.
  const modules = [...new Set(permissions.map((p) => p.module))];
  const estRoleAdmin = roleSelectionne?.nom === "Admin";

  return (
    <div className="app-layout">
      <Sidebar />

      <div className="app-contenu">
        <header className="app-topbar">
          <div className="app-topbar__recherche">
            <Search size={16} strokeWidth={1.75} />
            <input type="text" placeholder="Rechercher" />
          </div>
          <div className="app-topbar__droite">
            <Bell size={18} strokeWidth={1.75} />
            <div className="app-topbar__avatar">A</div>
          </div>
        </header>

        <main className="app-main">
          <h1 className="app-main__titre">Rôles et permissions</h1>

          {erreur && <div className="erreur-message">{erreur}</div>}
          {message && <div className="succes-message">{message}</div>}

          {chargement ? (
            <p>Chargement...</p>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "220px 1fr", gap: "1.25rem" }}>
              {/* Liste des rôles */}
              <div className="panel">
                <h3>Rôles</h3>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.3rem" }}>
                  {roles.map((role) => (
                    <button
                      key={role.id}
                      onClick={() => selectionnerRole(role)}
                      className="bouton-secondaire-large"
                      style={{
                        textAlign: "left",
                        border: roleSelectionne?.id === role.id ? "2px solid var(--color-primary, #1F4A4D)" : "1px solid var(--paper-line, #ddd)",
                      }}
                    >
                      {role.nom}
                    </button>
                  ))}
                </div>

                {afficherFormulaireRole ? (
                  <form onSubmit={gererCreationRole} style={{ marginTop: "0.8rem" }}>
                    <input
                      value={nouveauRoleNom}
                      onChange={(e) => setNouveauRoleNom(e.target.value)}
                      placeholder="Nom du rôle"
                      required
                      style={{ width: "100%", marginBottom: "0.4rem" }}
                    />
                    <button className="bouton-principal" type="submit" style={{ width: "100%" }}>Créer</button>
                  </form>
                ) : (
                  <button
                    className="bouton-secondaire-large"
                    style={{ marginTop: "0.8rem", width: "100%", display: "inline-flex", alignItems: "center", justifyContent: "center", gap: "0.3rem" }}
                    onClick={() => setAfficherFormulaireRole(true)}
                  >
                    <Plus size={14} /> Nouveau rôle
                  </button>
                )}
              </div>

              {/* Matrice de permissions */}
              <div className="panel">
                {roleSelectionne ? (
                  <>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                      <h3>Permissions — {roleSelectionne.nom}</h3>
                      {!estRoleAdmin && (
                        <button
                          className="bouton-principal"
                          style={{ width: "auto", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
                          onClick={enregistrerPermissions}
                          disabled={enregistrement}
                        >
                          <Save size={15} /> {enregistrement ? "..." : "Enregistrer"}
                        </button>
                      )}
                    </div>

                    {estRoleAdmin && (
                      <p className="app-page-note">
                        Le rôle Admin dispose de tous les droits par défaut et ne peut pas être restreint.
                      </p>
                    )}

                    <div className="table-module">
                      <table>
                        <thead>
                          <tr>
                            <th>Module</th>
                            {Object.values(LABELS_ACTION).map((label) => (
                              <th key={label} style={{ textAlign: "center" }}>{label}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody>
                          {modules.map((module) => (
                            <tr key={module}>
                              <td style={{ textTransform: "capitalize", fontWeight: 600 }}>{module}</td>
                              {Object.keys(LABELS_ACTION).map((action) => {
                                const perm = permissions.find((p) => p.module === module && p.action === action);
                                if (!perm) return <td key={action}></td>;
                                return (
                                  <td key={action} style={{ textAlign: "center" }}>
                                    <input
                                      type="checkbox"
                                      disabled={estRoleAdmin}
                                      checked={estRoleAdmin || permissionsCochees.has(perm.id)}
                                      onChange={() => basculerPermission(perm.id)}
                                    />
                                  </td>
                                );
                              })}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : (
                  <p>Aucun rôle disponible.</p>
                )}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
