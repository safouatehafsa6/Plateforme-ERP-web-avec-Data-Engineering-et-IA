# installer-c1.ps1 - C1 : appareils reconnus (ASCII uniquement)
$ErrorActionPreference = 'Stop'
$racine = (Get-Location).Path
$utf8 = New-Object System.Text.UTF8Encoding($false)
$horo = Get-Date -Format 'yyyyMMdd-HHmmss'

function Ecrire($rel, $contenu) {
    $p = Join-Path $racine $rel
    $dir = Split-Path $p -Parent
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
    if (Test-Path $p) { Copy-Item $p "$p.$horo.bak" }
    [System.IO.File]::WriteAllText($p, ($contenu -replace "`r`n", "`n"), $utf8)
    "OK  $rel"
}
function Lire($rel) {
    $p = Join-Path $racine $rel
    if (-not (Test-Path $p)) { throw "Introuvable : $rel" }
    $brut = [System.IO.File]::ReadAllText($p, $utf8)
    return @{ Chemin = $p; Rel = $rel; Crlf = $brut.Contains("`r`n"); Texte = ($brut -replace "`r`n", "`n") }
}
function Sauver($f) {
    Copy-Item $f.Chemin "$($f.Chemin).$horo.bak"
    $t = $f.Texte
    if ($f.Crlf) { $t = $t -replace "`n", "`r`n" }
    [System.IO.File]::WriteAllText($f.Chemin, $t, $utf8)
    "OK  $($f.Rel)"
}
function Unique($texte, $ancre, $nom) {
    $i = $texte.IndexOf($ancre)
    if ($i -lt 0) { throw "Ancre introuvable : $nom" }
    if ($i -ne $texte.LastIndexOf($ancre)) { throw "Ancre en double : $nom" }
}

# ------------------------------------------------ 0. VERIFICATIONS (aucune ecriture)
$mainPy = Lire 'backend\app\main.py'
if ($mainPy.Texte -notmatch 'allow_headers\s*=\s*\[\s*["'']\*["'']\s*\]') {
    throw "CORS : allow_headers n'est pas ['*'] dans main.py. Rien n'a ete modifie. Envoie-moi le bloc CORSMiddleware."
}

$sess = Lire 'backend\app\security\sessions.py'
$sessFait = $sess.Texte.Contains('enregistrer_appareil')
if (-not $sessFait) {
    Unique $sess.Texte ("from app.security.audit import journaliser`n") 'sessions.py import audit'
    Unique $sess.Texte ("            nb_limite = cur.rowcount`n") 'sessions.py nb_limite'
    Unique $sess.Texte ("user_agent, expire_le)`n                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)") 'sessions.py INSERT'
    Unique $sess.Texte ("                    adresse_ip(request), ua[:500], expiration,`n") 'sessions.py params'
}

$rout = Lire 'backend\app\routers\sessions.py'
$routFait = $rout.Texte.Contains('/appareils')
if (-not $routFait) {
    Unique $rout.Texte ("from fastapi import APIRouter, Depends, HTTPException, Request`n") 'routers import'
    Unique $rout.Texte ('@router.post("/deconnexion")' + "`n") 'routers deconnexion'
}

$page = Lire 'frontend\src\pages\Appareils.jsx'
$pageFait = $page.Texte.Contains('MesAppareilsConnus')
if (-not $pageFait) {
    Unique $page.Texte ('import ActiviteRecente from "../components/ActiviteRecente";' + "`n") 'Appareils.jsx import'
    Unique $page.Texte ("      <ActiviteRecente />`n") 'Appareils.jsx rendu'
}

$mainJsx = Lire 'frontend\src\main.jsx'
$mainFait = $mainJsx.Texte.Contains('deviceId')
if (-not $mainFait) { Unique $mainJsx.Texte ('import "./i18n";' + "`n") 'main.jsx import i18n' }

$apiPath = Join-Path $racine 'frontend\src\api\sessionsApi.js'
if (-not (Test-Path $apiPath)) { throw "Introuvable : sessionsApi.js" }
"Verifications OK."

# ------------------------------------------------ 1. SQL (applique AVANT le code)
$sql = @'
-- 008_appareil.sql : appareils reconnus (ajout seul)
CREATE TABLE IF NOT EXISTS appareil (
  id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  type_compte       VARCHAR(12) NOT NULL,
  utilisateur_id    VARCHAR(64) NOT NULL,
  email             VARCHAR(255) NOT NULL,
  entreprise_id     VARCHAR(64),
  device_hash       CHAR(64) NOT NULL,
  libelle           VARCHAR(80),
  systeme           VARCHAR(60),
  navigateur        VARCHAR(60),
  type_appareil     VARCHAR(30),
  premiere_ip       INET,
  derniere_ip       INET,
  statut            VARCHAR(12) NOT NULL DEFAULT 'autorise'
                    CHECK (statut IN ('autorise','en_attente','bloque')),
  cree_le           TIMESTAMPTZ NOT NULL DEFAULT now(),
  derniere_activite TIMESTAMPTZ,
  bloque_le         TIMESTAMPTZ,
  bloque_par        VARCHAR(255),
  motif_blocage     TEXT,
  supprime_le       TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_appareil_identite
  ON appareil (type_compte, utilisateur_id, (COALESCE(entreprise_id, '')), device_hash);
CREATE INDEX IF NOT EXISTS ix_appareil_user ON appareil (type_compte, utilisateur_id);
ALTER TABLE session_utilisateur ADD COLUMN IF NOT EXISTS appareil_id UUID REFERENCES appareil(id);
CREATE INDEX IF NOT EXISTS ix_session_appareil ON session_utilisateur (appareil_id);
'@
Ecrire 'backend\database\central\008_appareil.sql' $sql

$ErrorActionPreference = 'Continue'
$sortie = ($sql | docker compose exec -T postgres-erp psql -U erp_user -d erp_db -v ON_ERROR_STOP=1 2>&1 | Out-String)
$code = $LASTEXITCODE
$ErrorActionPreference = 'Stop'
if ($code -ne 0) { throw "Echec du SQL :`n$sortie" }
"OK  SQL applique en base"

# ------------------------------------------------ 2. backend
$app = @'
"""Appareils connus d'un compte (table appareil).

L'identifiant brut (en-tete X-Device-Id, UUID genere par le navigateur) n'est
jamais stocke : seul son hash SHA-256 l'est. Un echec ici ne doit jamais
empecher une connexion (SAVEPOINT).
"""
import hashlib
import ipaddress
import logging
import re

_log = logging.getLogger("appareils")
_RE_ID = re.compile(r"^[0-9a-fA-F-]{36}$")


def hash_identifiant(request):
    brut = request.headers.get("x-device-id", "").strip()
    if not _RE_ID.match(brut):
        return None
    return hashlib.sha256(brut.lower().encode("ascii")).hexdigest()


def enregistrer_appareil(cur, *, type_compte, utilisateur_id, email, entreprise_id, info, ip, request):
    """Cree ou met a jour l'appareil. Retourne (appareil_id, est_nouveau)."""
    empreinte = hash_identifiant(request)
    if not empreinte:
        return None, False
    try:
        ip = str(ipaddress.ip_address(ip)) if ip else None
    except ValueError:
        ip = None

    cur.execute("SAVEPOINT sp_appareil")
    try:
        cur.execute(
            """
            INSERT INTO appareil
                (type_compte, utilisateur_id, email, entreprise_id, device_hash,
                 systeme, navigateur, type_appareil, premiere_ip, derniere_ip, derniere_activite)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::inet, %s::inet, NOW())
            ON CONFLICT (type_compte, utilisateur_id, (COALESCE(entreprise_id, '')), device_hash)
            DO UPDATE SET email = EXCLUDED.email, systeme = EXCLUDED.systeme,
                          navigateur = EXCLUDED.navigateur, type_appareil = EXCLUDED.type_appareil,
                          derniere_ip = EXCLUDED.derniere_ip, derniere_activite = NOW(),
                          supprime_le = NULL
            RETURNING id, (xmax = 0)
            """,
            (
                type_compte, str(utilisateur_id), email,
                str(entreprise_id) if entreprise_id is not None else None,
                empreinte, info["systeme"], info["navigateur"], info["appareil"], ip, ip,
            ),
        )
        ligne = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT sp_appareil")
        return str(ligne[0]), bool(ligne[1])
    except Exception:
        _log.exception("Enregistrement de l'appareil impossible")
        cur.execute("ROLLBACK TO SAVEPOINT sp_appareil")
        return None, False
'@
Ecrire 'backend\app\security\appareils.py' $app

if (-not $sessFait) {
    $t = $sess.Texte
    $t = $t.Replace("from app.security.audit import journaliser`n",
        "from app.security.audit import journaliser`nfrom app.security.appareils import enregistrer_appareil`n")
    $bloc = @'
            appareil_id, _nouvel_appareil = enregistrer_appareil(
                cur, type_compte=claims["type"], utilisateur_id=claims["id"], email=claims["email"],
                entreprise_id=entreprise_id, info=info, ip=adresse_ip(request), request=request,
            )
'@
    $bloc = ($bloc -replace "`r`n", "`n") + "`n"
    $t = $t.Replace("            nb_limite = cur.rowcount`n", "            nb_limite = cur.rowcount`n" + $bloc)
    $t = $t.Replace("user_agent, expire_le)`n                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    "user_agent, expire_le, appareil_id)`n                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)")
    $t = $t.Replace("                    adresse_ip(request), ua[:500], expiration,`n",
                    "                    adresse_ip(request), ua[:500], expiration,`n                    appareil_id,`n")
    $sess.Texte = $t
    Sauver $sess
} else { "--  sessions.py deja patche" }

if (-not $routFait) {
    $t = $rout.Texte
    $t = $t.Replace("from fastapi import APIRouter, Depends, HTTPException, Request`n",
        "import uuid`n`nfrom fastapi import APIRouter, Depends, HTTPException, Request`nfrom pydantic import BaseModel`n")
    $routes = @'
# ---------------------------------------------------------------------
# Appareils reconnus (C1)
# ---------------------------------------------------------------------

class RenommerPayload(BaseModel):
    libelle: str


_FILTRE_APPAREIL = (
    "type_compte = %s AND utilisateur_id = %s "
    "AND entreprise_id IS NOT DISTINCT FROM %s AND supprime_le IS NULL"
)


def _cle_appareil(u: dict) -> tuple:
    ent = u.get("entrepriseId")
    return (u["type"], str(u["id"]), str(ent) if ent is not None else None)


def _uuid_ou_404(valeur: str) -> str:
    try:
        return str(uuid.UUID(valeur))
    except ValueError:
        raise HTTPException(status_code=404, detail="Appareil introuvable.")


@router.get("/appareils")
def mes_appareils(utilisateur: dict = Depends(utilisateur_connecte)):
    courante = _lire("SELECT appareil_id FROM session_utilisateur WHERE jti = %s", (utilisateur["jti"],))
    id_courant = str(courante[0][0]) if courante and courante[0][0] else None
    lignes = _lire(
        f"""
        SELECT a.id, a.libelle, a.systeme, a.navigateur, a.type_appareil, host(a.derniere_ip),
               a.cree_le, a.derniere_activite, a.statut,
               (SELECT COUNT(*) FROM session_utilisateur s
                 WHERE s.appareil_id = a.id AND s.revoquee_le IS NULL AND s.expire_le > NOW())
        FROM appareil a
        WHERE {_FILTRE_APPAREIL}
        ORDER BY a.derniere_activite DESC NULLS LAST
        """,
        _cle_appareil(utilisateur),
    )
    return {"appareils": [
        {
            "id": str(l[0]), "libelle": l[1], "systeme": l[2], "navigateur": l[3],
            "typeAppareil": l[4], "derniereIp": l[5],
            "creeLe": l[6].isoformat(),
            "derniereActivite": l[7].isoformat() if l[7] else None,
            "statut": l[8], "sessionsActives": l[9], "courant": str(l[0]) == id_courant,
        }
        for l in lignes
    ]}


@router.post("/appareils/{appareil_id}/renommer")
def renommer_appareil(appareil_id: str, payload: RenommerPayload,
                      utilisateur: dict = Depends(utilisateur_connecte)):
    libelle = payload.libelle.strip()[:80] or None
    nombre = _ecrire(
        f"UPDATE appareil SET libelle = %s WHERE id = %s::uuid AND {_FILTRE_APPAREIL}",
        (libelle, _uuid_ou_404(appareil_id), *_cle_appareil(utilisateur)),
    )
    if nombre == 0:
        raise HTTPException(status_code=404, detail="Appareil introuvable.")
    return {"message": "Appareil renomm\u00e9."}


@router.delete("/appareils/{appareil_id}")
def retirer_appareil(appareil_id: str, request: Request,
                     utilisateur: dict = Depends(utilisateur_connecte)):
    """Retire l'appareil de la liste et ferme ses sessions."""
    ident = _uuid_ou_404(appareil_id)
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE appareil SET supprime_le = NOW() WHERE id = %s::uuid AND {_FILTRE_APPAREIL}",
                (ident, *_cle_appareil(utilisateur)),
            )
            if cur.rowcount == 0:
                conn.rollback()
                raise HTTPException(status_code=404, detail="Appareil introuvable.")
            cur.execute(
                "UPDATE session_utilisateur SET revoquee_le = NOW(), motif_revocation = 'appareil_supprime' "
                "WHERE appareil_id = %s::uuid AND revoquee_le IS NULL",
                (ident,),
            )
            nb = cur.rowcount
        conn.commit()
    finally:
        pool_central.putconn(conn)
    _journal("appareil_supprime", utilisateur, request, "avertissement",
             {"cible_id": ident, "nb": nb})
    return {"message": "Appareil retir\u00e9.", "sessionsFermees": nb}


'@
    $routes = ($routes -replace "`r`n", "`n")
    $t = $t.Replace('@router.post("/deconnexion")' + "`n", $routes + '@router.post("/deconnexion")' + "`n")
    $rout.Texte = $t
    Sauver $rout
} else { "--  routers/sessions.py deja patche" }

# ------------------------------------------------ 3. frontend
$dev = @'
// deviceId.js - identifiant d'appareil anonyme, envoye dans l'en-tete X-Device-Id.
import { API_BASE_URL } from "./config";

const CLE = "erp_device_id";

function genererUuid() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) return crypto.randomUUID();
  const o = new Uint8Array(16);
  crypto.getRandomValues(o);
  o[6] = (o[6] & 0x0f) | 0x40;
  o[8] = (o[8] & 0x3f) | 0x80;
  const h = Array.from(o, (b) => b.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

export function identifiantAppareil() {
  try {
    let id = localStorage.getItem(CLE);
    if (!id || id.length !== 36) {
      id = genererUuid();
      localStorage.setItem(CLE, id);
    }
    return id;
  } catch {
    return null;
  }
}

// Ajoute X-Device-Id a tous les appels vers notre API (et uniquement elle).
if (typeof window !== "undefined" && !window.__erpFetchPatche) {
  window.__erpFetchPatche = true;
  const original = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    try {
      const url = typeof input === "string" ? input : (input && (input.url || input.href)) || "";
      const id = identifiantAppareil();
      if (id && API_BASE_URL && url.startsWith(API_BASE_URL)) {
        const base = init.headers || (typeof input === "object" && input && input.headers) || undefined;
        const entetes = new Headers(base);
        entetes.set("X-Device-Id", id);
        return original(input, { ...init, headers: entetes });
      }
    } catch {
      /* ne jamais casser un appel reseau */
    }
    return original(input, init);
  };
}
'@
Ecrire 'frontend\src\api\deviceId.js' $dev

$jsx = @'
import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Monitor, Smartphone, Pencil, Trash2 } from "lucide-react";
import {
  deconnecter,
  listerMesAppareils,
  renommerAppareil,
  supprimerAppareil,
} from "../api/sessionsApi";

function formaterDate(iso) {
  return iso ? new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "-";
}

export default function MesAppareilsConnus() {
  const navigate = useNavigate();
  const [appareils, setAppareils] = useState([]);
  const [erreur, setErreur] = useState("");

  const charger = useCallback(async () => {
    try {
      const d = await listerMesAppareils();
      setAppareils(d.appareils || []);
      setErreur("");
    } catch (e) {
      if (e.status === 401) navigate("/");
      else setErreur(e.message);
    }
  }, [navigate]);

  useEffect(() => { charger(); }, [charger]);

  async function renommer(a) {
    const nom = window.prompt("Nom de cet appareil :", a.libelle || "");
    if (nom === null) return;
    try { await renommerAppareil(a.id, nom); await charger(); }
    catch (e) { setErreur(e.message); }
  }

  async function retirer(a) {
    const msg = a.courant
      ? "Retirer cet appareil vous deconnectera. Continuer ?"
      : "Retirer cet appareil et fermer ses sessions ?";
    if (!window.confirm(msg)) return;
    try {
      await supprimerAppareil(a.id);
      if (a.courant) { await deconnecter(); navigate("/"); return; }
      await charger();
    } catch (e) { setErreur(e.message); }
  }

  return (
    <section className="panel appareils-section">
      <div className="appareils-section__entete">
        <h2>Appareils reconnus</h2>
      </div>
      {erreur && <div className="erreur-message">{erreur}</div>}
      {!erreur && appareils.length === 0 && (
        <p className="parametres-muted">
          {"Aucun appareil identifi\u00e9. Reconnectez-vous pour enregistrer cet appareil."}
        </p>
      )}
      <ul className="appareils-liste">
        {appareils.map((a) => (
          <li key={a.id} className="appareils-item">
            {a.typeAppareil === "mobile" ? <Smartphone size={22} /> : <Monitor size={22} />}
            <div className="appareils-item__corps">
              <strong>
                {a.libelle || (a.navigateur + " sur " + a.systeme)}
                {a.courant && <span className="appareils-badge">Cet appareil</span>}
              </strong>
              <span>{a.navigateur + " sur " + a.systeme + " \u00b7 IP " + (a.derniereIp || "inconnue")}</span>
              <span>
                {"Derni\u00e8re activit\u00e9 : " + formaterDate(a.derniereActivite) +
                  " \u00b7 " + a.sessionsActives + " session(s) active(s)"}
              </span>
            </div>
            <div className="appareils-actions">
              <button type="button" className="appareils-bouton" onClick={() => renommer(a)}>
                <Pencil size={14} /> Renommer
              </button>
              <button type="button" className="appareils-bouton appareils-bouton--danger" onClick={() => retirer(a)}>
                <Trash2 size={14} /> Retirer
              </button>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
'@
Ecrire 'frontend\src\components\MesAppareilsConnus.jsx' $jsx

if (-not ([System.IO.File]::ReadAllText($apiPath, $utf8)).Contains('listerMesAppareils')) {
    Copy-Item $apiPath "$apiPath.$horo.bak"
    $ajout = "`n// Appareils reconnus (C1)`n" +
'async function appelAuthJson(methode, endpoint, corps) {' + "`n" +
'  const token = localStorage.getItem("token");' + "`n" +
'  const res = await fetch(`${API_BASE_URL}${endpoint}`, {' + "`n" +
'    method: methode,' + "`n" +
'    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },' + "`n" +
'    body: JSON.stringify(corps),' + "`n" +
'  });' + "`n" +
'  const data = await res.json().catch(() => null);' + "`n" +
'  if (!res.ok) {' + "`n" +
'    if (res.status === 401) localStorage.removeItem("token");' + "`n" +
'    const erreur = new Error(data?.detail || data?.message || `Erreur ${res.status}.`);' + "`n" +
'    erreur.status = res.status;' + "`n" +
'    throw erreur;' + "`n" +
'  }' + "`n" +
'  return data;' + "`n" +
'}' + "`n" +
'export const listerMesAppareils = () => appelAuth("GET", "/sessions/appareils");' + "`n" +
'export const supprimerAppareil = (id) => appelAuth("DELETE", `/sessions/appareils/${id}`);' + "`n" +
'export const renommerAppareil = (id, libelle) => appelAuthJson("POST", `/sessions/appareils/${id}/renommer`, { libelle });' + "`n"
    [System.IO.File]::AppendAllText($apiPath, $ajout, $utf8)
    "OK  frontend\src\api\sessionsApi.js"
} else { "--  sessionsApi.js deja a jour" }

if (-not $pageFait) {
    $t = $page.Texte
    $t = $t.Replace('import ActiviteRecente from "../components/ActiviteRecente";' + "`n",
        'import ActiviteRecente from "../components/ActiviteRecente";' + "`n" +
        'import MesAppareilsConnus from "../components/MesAppareilsConnus";' + "`n")
    $t = $t.Replace("      <ActiviteRecente />`n", "      <MesAppareilsConnus />`n      <ActiviteRecente />`n")
    $page.Texte = $t
    Sauver $page
} else { "--  Appareils.jsx deja patche" }

if (-not $mainFait) {
    $mainJsx.Texte = $mainJsx.Texte.Replace('import "./i18n";' + "`n", 'import "./i18n";' + "`n" + 'import "./api/deviceId";' + "`n")
    Sauver $mainJsx
} else { "--  main.jsx deja patche" }

"`nTERMINE. Reconnecte-toi une fois dans le navigateur, puis lance test-c1.ps1."