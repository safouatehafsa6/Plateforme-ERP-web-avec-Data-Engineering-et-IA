import { useEffect, useRef, useState } from "react";
import Sidebar from "../components/Sidebar";
import { API_BASE_URL } from "../api/config";

const ETAPES_INITIALES = [
  { id: "extract_raw", label: "Extraction des données", state: "none" },
  { id: "transform_staging", label: "Transformation en Parquet", state: "none" },
  { id: "build_curated", label: "Préparation des données finales", state: "none" },
  { id: "quality_gate", label: "Contrôle de qualité", state: "none" },
];

async function api(chemin, options = {}) {
  const res = await fetch(`${API_BASE_URL}/pipeline${chemin}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${localStorage.getItem("token")}`,
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || "Une erreur est survenue.");
  return data;
}

function symbole(state) {
  if (state === "success") return "✓";
  if (state === "failed" || state === "upstream_failed") return "✗";
  if (state === "running" || state === "up_for_retry") return "⏳";
  return "○";
}

function dateLongue(v) {
  if (!v) return "—";
  return new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(v));
}

export default function DashboardData() {
  const [phase, setPhase] = useState("demarrage"); // demarrage | en_cours | pret | echec
  const [taches, setTaches] = useState(ETAPES_INITIALES);
  const [message, setMessage] = useState("");
  const [url, setUrl] = useState("");
  const [majLe, setMajLe] = useState(null);
  const dejaLance = useRef(false);
  const minuteur = useRef(null);

  function arreterSondage() {
    if (minuteur.current) {
      clearInterval(minuteur.current);
      minuteur.current = null;
    }
  }

  async function afficher() {
    const [jeton, derniere] = await Promise.all([
      api("/dashboard-token", { method: "POST" }),
      api("/latest"),
    ]);
    setUrl(jeton.url);
    setMajLe(derniere.publishedAt || null);
    setPhase("pret");
  }

  function surveiller(runId) {
    arreterSondage();
    minuteur.current = setInterval(async () => {
      try {
        const etat = await api(`/status/${encodeURIComponent(runId)}`);
        setTaches(etat.tasks || ETAPES_INITIALES);
        if (etat.status === "success") {
          arreterSondage();
          await afficher();
        } else if (etat.status === "failed") {
          arreterSondage();
          setMessage(etat.message || "Le traitement a échoué.");
          setPhase("echec");
        }
      } catch (e) {
        arreterSondage();
        setMessage(e.message);
        setPhase("echec");
      }
    }, 3000);
  }

  async function lancer(force) {
    setPhase("en_cours");
    setMessage("");
    setUrl("");
    setTaches(ETAPES_INITIALES);
    try {
      const run = await api("/run", { method: "POST", body: JSON.stringify({ force }) });
      if (run.status === "success") {
        await afficher();
      } else {
        surveiller(run.runId);
      }
    } catch (e) {
      setMessage(e.message);
      setPhase("echec");
    }
  }

  useEffect(() => {
    // Le clic sur "Dashboard" ouvre cette page : on lance (ou on reutilise) le traitement.
    if (!dejaLance.current) {
      dejaLance.current = true;
      lancer(false);
    }
    return arreterSondage;
  }, []);

  return (
    <div className="app-layout">
      <Sidebar />
      <div className="app-contenu">
        <main className="app-main">
          <div className="dd-entete">
            <h1 className="app-main__titre">Dashboard</h1>
            <div className="dd-actions">
              {majLe && phase === "pret" && <span className="dd-maj">Données validées le {dateLongue(majLe)}</span>}
              <button type="button" className="dd-bouton" onClick={() => lancer(true)} disabled={phase === "en_cours" || phase === "demarrage"}>
                Actualiser
              </button>
            </div>
          </div>

          {(phase === "demarrage" || phase === "en_cours") && (
            <div className="dd-carte">
              <h2 className="dd-sous-titre">Préparation de vos données…</h2>
              <ul className="dd-etapes">
                {taches.map((t) => (
                  <li key={t.id} className={`dd-etape dd-etape--${t.state}`}>
                    <span className="dd-etape__symbole">{symbole(t.state)}</span>
                    {t.label}
                  </li>
                ))}
              </ul>
              <p className="dd-aide">Cela peut prendre quelques minutes. Vous pouvez rester sur cette page.</p>
            </div>
          )}

          {phase === "echec" && (
            <div className="dd-carte dd-carte--erreur">
              <h2 className="dd-sous-titre">Dashboard indisponible</h2>
              <p>{message}</p>
              <button type="button" className="dd-bouton" onClick={() => lancer(false)}>Réessayer</button>
            </div>
          )}

          {phase === "pret" && url && (
            <iframe className="dd-iframe" title="Dashboard" src={url} />
          )}
        </main>
      </div>
    </div>
  );
}
