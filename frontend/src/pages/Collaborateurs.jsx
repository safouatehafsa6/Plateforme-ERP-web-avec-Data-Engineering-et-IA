import { useEffect, useState } from "react";
import { Search, Bell, UserPlus, X } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

function headersAuth() {
  const token = localStorage.getItem("token");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

export default function Collaborateurs() {
  const [utilisateurs, setUtilisateurs] = useState([]);
  const [roles, setRoles] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [afficherFormulaire, setAfficherFormulaire] = useState(false);

  const [nouveau, setNouveau] = useState({ nom: "", prenom: "", email: "", roleId: "" });
  const [motDePasseGenere, setMotDePasseGenere] = useState(null);
  const [enCours, setEnCours] = useState(false);

  async function chargerDonnees() {
    setChargement(true);
    setErreur("");
    try {
      const [resUtilisateurs, resRoles] = await Promise.all([
        fetch(`${API_BASE_URL}/utilisateurs`, { headers: headersAuth() }),
        fetch(`${API_BASE_URL}/utilisateurs/roles`, { headers: headersAuth() }),
      ]);
      if (!resUtilisateurs.ok || !resRoles.ok) throw new Error("Impossible de charger les données. Vérifiez que vous êtes bien connectée en tant qu'administrateur.");
      const dataUtilisateurs = await resUtilisateurs.json();
      const dataRoles = await resRoles.json();
      setUtilisateurs(dataUtilisateurs.utilisateurs);
      setRoles(dataRoles.roles);
    } catch (e) {
      setErreur(e.message);
    } finally {
      setChargement(false);
    }
  }

  useEffect(() => {
    chargerDonnees();
  }, []);

  async function gererCreation(e) {
    e.preventDefault();
    setErreur("");
    setEnCours(true);
    try {
      const res = await fetch(`${API_BASE_URL}/utilisateurs`, {
        method: "POST",
        headers: headersAuth(),
        body: JSON.stringify({ ...nouveau, roleId: Number(nouveau.roleId) }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Erreur lors de la création.");
      setMotDePasseGenere({ email: data.email, motDePasse: data.motDePasseTemporaire });
      setNouveau({ nom: "", prenom: "", email: "", roleId: "" });
      setAfficherFormulaire(false);
      chargerDonnees();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnCours(false);
    }
  }

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
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h1 className="app-main__titre">Collaborateurs</h1>
            <button
              className="bouton-principal"
              style={{ width: "auto", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
              onClick={() => setAfficherFormulaire((v) => !v)}
            >
              <UserPlus size={16} strokeWidth={2} /> Ajouter un collaborateur
            </button>
          </div>

          {erreur && <div className="erreur-message">{erreur}</div>}

          {motDePasseGenere && (
            <div className="succes-message">
              Collaborateur <strong>{motDePasseGenere.email}</strong> créé. Mot de passe
              temporaire (à communiquer de façon sécurisée, ne sera plus jamais
              affiché) : <code style={{ fontWeight: 700 }}>{motDePasseGenere.motDePasse}</code>
              <button
                onClick={() => setMotDePasseGenere(null)}
                style={{ marginLeft: "0.8rem", background: "none", border: "none", cursor: "pointer" }}
              >
                <X size={14} />
              </button>
            </div>
          )}

          {afficherFormulaire && (
            <form onSubmit={gererCreation} className="panel" style={{ marginBottom: "1.25rem" }}>
              <h3>Nouveau collaborateur</h3>
              <div className="champ-ligne">
                <div className="champ">
                  <label>Prénom</label>
                  <input value={nouveau.prenom} onChange={(e) => setNouveau({ ...nouveau, prenom: e.target.value })} required />
                </div>
                <div className="champ">
                  <label>Nom</label>
                  <input value={nouveau.nom} onChange={(e) => setNouveau({ ...nouveau, nom: e.target.value })} required />
                </div>
              </div>
              <div className="champ">
                <label>Email</label>
                <input type="email" value={nouveau.email} onChange={(e) => setNouveau({ ...nouveau, email: e.target.value })} required />
              </div>
              <div className="champ">
                <label>Rôle</label>
                <select value={nouveau.roleId} onChange={(e) => setNouveau({ ...nouveau, roleId: e.target.value })} required>
                  <option value="">-- Choisir un rôle --</option>
                  {roles.map((r) => (
                    <option key={r.id} value={r.id}>{r.nom}</option>
                  ))}
                </select>
              </div>
              <div style={{ display: "flex", gap: "0.6rem" }}>
                <button className="bouton-principal" type="submit" disabled={enCours} style={{ width: "auto" }}>
                  {enCours ? "..." : "Créer"}
                </button>
                <button type="button" className="bouton-secondaire-large" onClick={() => setAfficherFormulaire(false)}>
                  Annuler
                </button>
              </div>
            </form>
          )}

          {chargement ? (
            <p>Chargement...</p>
          ) : (
            <div className="table-module">
              <table>
                <thead>
                  <tr>
                    <th>Nom</th>
                    <th>Email</th>
                    <th>Rôle</th>
                    <th>Département</th>
                    <th>Statut</th>
                  </tr>
                </thead>
                <tbody>
                  {utilisateurs.map((u) => (
                    <tr key={u.id}>
                      <td>{u.prenom} {u.nom}</td>
                      <td>{u.email}</td>
                      <td>{u.role_nom || "—"}</td>
                      <td>{u.departement_nom || "—"}</td>
                      <td>{u.actif ? "Actif" : "Inactif"}</td>
                    </tr>
                  ))}
                  {utilisateurs.length === 0 && (
                    <tr><td colSpan={5}>Aucun collaborateur pour le moment.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
