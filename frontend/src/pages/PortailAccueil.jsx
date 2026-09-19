import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut } from "lucide-react";
import { API_BASE_URL } from "../api/config";

function headersAuth() {
  const token = localStorage.getItem("token");
  return { Authorization: `Bearer ${token}` };
}

function formatMontant(montant) {
  return new Intl.NumberFormat("fr-MA", { minimumFractionDigits: 2 }).format(montant || 0) + " MAD";
}

function formatDate(valeur) {
  if (!valeur) return "—";
  return new Date(valeur).toLocaleDateString("fr-FR");
}

// Espace personnel du portail Utilisateurs externes (clients/partenaires) :
// consultation en temps réel de ses propres commandes et factures.
// Le téléchargement PDF avec QR code et le paiement en ligne mentionnés
// dans la lettre de cadrage sont une prochaine étape, non couverts ici.
export default function PortailAccueil() {
  const navigate = useNavigate();
  const [profil, setProfil] = useState(null);
  const [commandes, setCommandes] = useState([]);
  const [factures, setFactures] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");

  useEffect(() => {
    async function charger() {
      setChargement(true);
      setErreur("");
      try {
        const [resProfil, resDocuments] = await Promise.all([
          fetch(`${API_BASE_URL}/portail/moi`, { headers: headersAuth() }),
          fetch(`${API_BASE_URL}/portail/mes-documents`, { headers: headersAuth() }),
        ]);
        if (!resProfil.ok || !resDocuments.ok) {
          throw new Error("Impossible de charger votre espace. Merci de vous reconnecter.");
        }
        setProfil(await resProfil.json());
        const documents = await resDocuments.json();
        setCommandes(documents.commandes);
        setFactures(documents.factures);
      } catch (e) {
        setErreur(e.message);
      } finally {
        setChargement(false);
      }
    }
    charger();
  }, []);

  function deconnexion() {
    localStorage.removeItem("token");
    navigate("/");
  }

  return (
    <div className="portail-layout">
      <header className="portail-topbar">
        <div className="portail-topbar__marque">BENJEDDOU ERP — Espace Client</div>
        <button className="portail-topbar__deconnexion" onClick={deconnexion}>
          <LogOut size={15} strokeWidth={1.75} /> Déconnexion
        </button>
      </header>

      <main className="portail-main">
        {erreur && <div className="erreur-message">{erreur}</div>}

        {!chargement && profil && (
          <div className="portail-carte">
            <h1 style={{ marginTop: 0 }}>Bonjour, {profil.nom || "—"}</h1>
            <p style={{ color: "var(--text-muted)", margin: 0 }}>{profil.email}</p>
          </div>
        )}

        {chargement ? (
          <p>Chargement...</p>
        ) : (
          <>
            <div className="portail-carte">
              <h2 style={{ marginTop: 0 }}>Mes commandes et devis</h2>
              <div className="table-module">
                <table>
                  <thead>
                    <tr>
                      <th>Date</th>
                      <th>Statut</th>
                      <th>Montant</th>
                    </tr>
                  </thead>
                  <tbody>
                    {commandes.map((c) => (
                      <tr key={c.id}>
                        <td>{formatDate(c.date_commande)}</td>
                        <td><span className="badge-statut badge-statut--actif">{c.statut}</span></td>
                        <td>{formatMontant(c.montant_total)}</td>
                      </tr>
                    ))}
                    {commandes.length === 0 && (
                      <tr><td colSpan={3}>Aucune commande pour le moment.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="portail-carte">
              <h2 style={{ marginTop: 0 }}>Mes factures</h2>
              <div className="table-module">
                <table>
                  <thead>
                    <tr>
                      <th>Numéro</th>
                      <th>Date</th>
                      <th>Statut</th>
                      <th>Montant</th>
                    </tr>
                  </thead>
                  <tbody>
                    {factures.map((f) => (
                      <tr key={f.id}>
                        <td>{f.numero}</td>
                        <td>{formatDate(f.date_facture)}</td>
                        <td>
                          <span className={`badge-statut badge-statut--${f.statut === "payee" ? "actif" : "suspendu"}`}>
                            {f.statut}
                          </span>
                        </td>
                        <td>{formatMontant(f.montant_total)}</td>
                      </tr>
                    ))}
                    {factures.length === 0 && (
                      <tr><td colSpan={4}>Aucune facture pour le moment.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
