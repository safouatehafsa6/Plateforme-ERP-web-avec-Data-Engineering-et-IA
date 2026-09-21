import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogOut, Download, CreditCard } from "lucide-react";
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
// consultation en temps réel de ses propres commandes et factures,
// téléchargement PDF avec QR code d'authenticité, et paiement en ligne
// (simulé — voir portail.py pour le détail de cette limitation).
export default function PortailAccueil() {
  const navigate = useNavigate();
  const [profil, setProfil] = useState(null);
  const [commandes, setCommandes] = useState([]);
  const [factures, setFactures] = useState([]);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState("");
  const [messageSucces, setMessageSucces] = useState("");
  const [actionEnCours, setActionEnCours] = useState(null); // id de la facture en cours de traitement

  async function chargerDocuments() {
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

  useEffect(() => {
    chargerDocuments();
  }, []);

  async function telechargerPdf(facture) {
    setErreur("");
    setActionEnCours(facture.id);
    try {
      const res = await fetch(`${API_BASE_URL}/portail/factures/${facture.id}/pdf`, { headers: headersAuth() });
      if (!res.ok) throw new Error("Impossible de générer le PDF de cette facture.");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const lien = document.createElement("a");
      lien.href = url;
      lien.download = `facture_${facture.numero}.pdf`;
      document.body.appendChild(lien);
      lien.click();
      lien.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      setErreur(e.message);
    } finally {
      setActionEnCours(null);
    }
  }

  async function payerFacture(facture) {
    setErreur("");
    setMessageSucces("");
    setActionEnCours(facture.id);
    try {
      const res = await fetch(`${API_BASE_URL}/portail/factures/${facture.id}/payer`, {
        method: "POST",
        headers: headersAuth(),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || "Le paiement a échoué.");
      setMessageSucces(data.message);
      await chargerDocuments();
    } catch (e) {
      setErreur(e.message);
    } finally {
      setActionEnCours(null);
    }
  }

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
        {messageSucces && <div className="succes-message">{messageSucces}</div>}

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
                      <th>Actions</th>
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
                        <td style={{ display: "flex", gap: "0.5rem" }}>
                          <button
                            className="bouton-mini"
                            disabled={actionEnCours === f.id}
                            onClick={() => telechargerPdf(f)}
                            title="Télécharger le PDF (avec QR code d'authenticité)"
                          >
                            <Download size={14} strokeWidth={2} /> PDF
                          </button>
                          {f.statut !== "payee" && (
                            <button
                              className="bouton-mini"
                              disabled={actionEnCours === f.id}
                              onClick={() => payerFacture(f)}
                              title="Payer cette facture (paiement simulé)"
                            >
                              <CreditCard size={14} strokeWidth={2} /> {actionEnCours === f.id ? "..." : "Payer"}
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                    {factures.length === 0 && (
                      <tr><td colSpan={5}>Aucune facture pour le moment.</td></tr>
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
