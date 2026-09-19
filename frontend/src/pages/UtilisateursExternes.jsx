import { useEffect, useState } from "react";
import { Search, Bell, X } from "lucide-react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

function headersAuth() {
  const token = localStorage.getItem("token");
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

export default function UtilisateursExternes() {
  const [utilisateurs, setUtilisateurs] = useState([]);
  const [clients, setClients] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [afficherFormulaire, setAfficherFormulaire] = useState(false);
  const [enCours, setEnCours] = useState(false);
  const [motDePasseGenere, setMotDePasseGenere] = useState(null);

  const [clientExistant, setClientExistant] = useState(true);
  const [nouveau, setNouveau] = useState({
    email: "", clientId: "", clientNom: "", clientEmail: "", clientTelephone: "",
  });

  async function chargerDonnees() {
    setChargement(true);
    setErreur("");
    try {
      const [resUtilisateurs, resClients] = await Promise.all([
        fetch(`${API_BASE_URL}/utilisateurs-externes`, { headers: headersAuth() }),
        fetch(`${API_BASE_URL}/utilisateurs-externes/clients`, { headers: headersAuth() }),
      ]);
      if (!resUtilisateurs.ok || !resClients.ok) {
        throw new Error("Impossible de charger les données. Vérifiez que vous êtes bien connectée en tant qu'administrateur.");
      }
      const dataUtilisateurs = await resUtilisateurs.json();
      const dataClients = await resClients.json();
      setUtilisateurs(dataUtilisateurs.utilisateursExternes);
      setClients(dataClients.clients);
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
      const corps = { email: nouveau.email };
      if (clientExistant) {
        corps.clientId = Number(nouveau.clientId);
      } else {
        corps.clientNom = nouveau.clientNom;
        corps.clientEmail = nouveau.clientEmail || undefined;
        corps.clientTelephone = nouveau.clientTelephone || undefined;
      }

      const res = await fetch(`${API_BASE_URL}/utilisateurs-externes`, {
        method: "POST",
        headers: headersAuth(),
        body: JSON.stringify(corps),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Erreur lors de la création.");
      setMotDePasseGenere({ email: data.email, motDePasse: data.motDePasseTemporaire });
      setNouveau({ email: "", clientId: "", clientNom: "", clientEmail: "", clientTelephone: "" });
      setAfficherFormulaire(false);
      chargerDonnees();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setEnCours(false);
    }
  }

  async function basculerActif(id, actif) {
    await fetch(`${API_BASE_URL}/utilisateurs-externes/${id}/actif`, {
      method: "PATCH",
      headers: headersAuth(),
      body: JSON.stringify({ actif: !actif }),
    });
    chargerDonnees();
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
          </div>
        </header>

        <main className="app-main">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <h1 className="app-main__titre">Utilisateurs Externes</h1>
            <button className="bouton-principal" style={{ width: "auto" }} onClick={() => setAfficherFormulaire(true)}>
              + Nouveau compte externe
            </button>
          </div>

          {erreur && <div className="erreur-message">{erreur}</div>}

          {motDePasseGenere && (
            <div className="succes-message">
              Compte externe <strong>{motDePasseGenere.email}</strong> créé. Mot de passe
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
              <h3>Nouveau compte externe</h3>

              <div className="champ">
                <label>Email</label>
                <input type="email" required value={nouveau.email} onChange={(e) => setNouveau({ ...nouveau, email: e.target.value })} />
              </div>

              <div className="champ" style={{ display: "flex", gap: "1.2rem" }}>
                <label style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <input type="radio" checked={clientExistant} onChange={() => setClientExistant(true)} /> Client existant
                </label>
                <label style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <input type="radio" checked={!clientExistant} onChange={() => setClientExistant(false)} /> Nouveau client
                </label>
              </div>

              {clientExistant ? (
                <div className="champ">
                  <label>Client</label>
                  <select required value={nouveau.clientId} onChange={(e) => setNouveau({ ...nouveau, clientId: e.target.value })}>
                    <option value="">-- Choisir un client --</option>
                    {clients.map((c) => <option key={c.id} value={c.id}>{c.nom}</option>)}
                  </select>
                </div>
              ) : (
                <div className="champ-ligne">
                  <div className="champ">
                    <label>Nom du client</label>
                    <input required value={nouveau.clientNom} onChange={(e) => setNouveau({ ...nouveau, clientNom: e.target.value })} />
                  </div>
                  <div className="champ">
                    <label>Téléphone (optionnel)</label>
                    <input value={nouveau.clientTelephone} onChange={(e) => setNouveau({ ...nouveau, clientTelephone: e.target.value })} />
                  </div>
                </div>
              )}

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
                    <th>Client</th>
                    <th>Email</th>
                    <th>Statut</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {utilisateurs.map((u) => (
                    <tr key={u.id}>
                      <td>{u.client_nom}</td>
                      <td>{u.email}</td>
                      <td>
                        <span className={`badge-statut badge-statut--${u.actif ? "actif" : "suspendu"}`}>
                          {u.actif ? "Actif" : "Inactif"}
                        </span>
                      </td>
                      <td>
                        <button className="bouton-mini" onClick={() => basculerActif(u.id, u.actif)}>
                          {u.actif ? "Désactiver" : "Activer"}
                        </button>
                      </td>
                    </tr>
                  ))}
                  {utilisateurs.length === 0 && (
                    <tr><td colSpan={4}>Aucun compte externe pour le moment.</td></tr>
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
