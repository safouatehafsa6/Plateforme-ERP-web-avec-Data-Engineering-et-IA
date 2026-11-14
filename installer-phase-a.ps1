# installer-phase-a.ps1 - Phase A : journal des evenements de securite
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
    return @{ Chemin = $p; Crlf = $brut.Contains("`r`n"); Texte = ($brut -replace "`r`n", "`n") }
}
function Sauver($f) {
    Copy-Item $f.Chemin "$($f.Chemin).$horo.bak"
    $t = $f.Texte
    if ($f.Crlf) { $t = $t -replace "`n", "`r`n" }
    [System.IO.File]::WriteAllText($f.Chemin, $t, $utf8)
}
function Unique($texte, $ancre, $nom) {
    $i = $texte.IndexOf($ancre)
    if ($i -lt 0) { throw "Ancre introuvable : $nom" }
    if ($i -ne $texte.LastIndexOf($ancre)) { throw "Ancre en double : $nom" }
}

# ---------------------------------------------------------------- 1. SQL
$sql = @'
-- 007_evenement_securite.sql : journal des evenements de securite (ajout seul)
CREATE TABLE IF NOT EXISTS evenement_securite (
  id              BIGSERIAL PRIMARY KEY,
  cree_le         TIMESTAMPTZ NOT NULL DEFAULT now(),
  type_evenement  VARCHAR(40) NOT NULL,
  gravite         VARCHAR(12) NOT NULL DEFAULT 'info'
                  CHECK (gravite IN ('info','avertissement','critique')),
  succes          BOOLEAN,
  type_compte     VARCHAR(12),
  utilisateur_id  VARCHAR(64),
  email           VARCHAR(255),
  entreprise_id   VARCHAR(64),
  jti             VARCHAR(64),
  adresse_ip      INET,
  systeme         VARCHAR(60),
  navigateur      VARCHAR(60),
  acteur_email    VARCHAR(255),
  details         JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_evt_ent_date ON evenement_securite (entreprise_id, cree_le DESC);
CREATE INDEX IF NOT EXISTS ix_evt_email_dt ON evenement_securite (email, cree_le DESC);
CREATE INDEX IF NOT EXISTS ix_evt_type_dt  ON evenement_securite (type_evenement, cree_le DESC);

CREATE OR REPLACE FUNCTION evenement_securite_immuable() RETURNS trigger AS $$
BEGIN
  IF TG_OP = 'DELETE' AND current_setting('erp.purge_autorisee', true) = 'on' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'evenement_securite est en ajout seul (UPDATE/DELETE interdits)';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evt_immuable ON evenement_securite;
CREATE TRIGGER trg_evt_immuable BEFORE UPDATE OR DELETE ON evenement_securite
  FOR EACH ROW EXECUTE FUNCTION evenement_securite_immuable();

CREATE OR REPLACE FUNCTION purger_evenements_securite(retention INTERVAL DEFAULT '12 months')
RETURNS BIGINT AS $$
DECLARE n BIGINT;
BEGIN
  PERFORM set_config('erp.purge_autorisee', 'on', true);
  DELETE FROM evenement_securite WHERE cree_le < now() - retention;
  GET DIAGNOSTICS n = ROW_COUNT;
  PERFORM set_config('erp.purge_autorisee', 'off', true);
  RETURN n;
END;
$$ LANGUAGE plpgsql;
'@
Ecrire 'backend\database\central\007_evenement_securite.sql' $sql

# ---------------------------------------------------------------- 2. audit.py
$audit = @'
"""Journal des evenements de securite (table evenement_securite).

journaliser() ne leve JAMAIS d'exception : le journal ne doit pas casser
une connexion. Seules les cles de _CLES_DETAILS sont conservees (jamais de
mot de passe, de jeton ou de secret).
"""
import ipaddress
import json
import logging

from app.db import pool_central

_log = logging.getLogger("audit")

_CLES_DETAILS = {"motif", "raison", "nb", "cible_email", "cible_jti", "cible_type", "cible_id"}


def _txt(valeur, taille):
    return None if valeur is None else str(valeur)[:taille]


def _nettoyer(details):
    if not details:
        return {}
    propre = {}
    for cle, valeur in details.items():
        if cle in _CLES_DETAILS:
            propre[cle] = valeur if isinstance(valeur, (int, float, bool)) else str(valeur)[:200]
    return propre


def journaliser(
    type_evenement,
    *,
    gravite="info",
    succes=None,
    type_compte=None,
    utilisateur_id=None,
    email=None,
    entreprise_id=None,
    jti=None,
    request=None,
    acteur_email=None,
    details=None,
):
    try:
        ip = systeme = navigateur = None
        if request is not None:
            from app.security.sessions import adresse_ip, analyser_user_agent
            ip = adresse_ip(request)
            info = analyser_user_agent(request.headers.get("user-agent", ""))
            systeme, navigateur = info["systeme"], info["navigateur"]
        if ip:
            try:
                ip = str(ipaddress.ip_address(ip))
            except ValueError:
                ip = None

        conn = pool_central.getconn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO evenement_securite
                        (type_evenement, gravite, succes, type_compte, utilisateur_id, email,
                         entreprise_id, jti, adresse_ip, systeme, navigateur, acteur_email, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::inet, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        _txt(type_evenement, 40), gravite, succes, _txt(type_compte, 12),
                        _txt(utilisateur_id, 64),
                        _txt(email.strip().lower(), 255) if email else None,
                        _txt(entreprise_id, 64), _txt(jti, 64), ip,
                        _txt(systeme, 60), _txt(navigateur, 60),
                        _txt(acteur_email.strip().lower(), 255) if acteur_email else None,
                        json.dumps(_nettoyer(details)),
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            pool_central.putconn(conn)
    except Exception:
        _log.exception("Journalisation de securite impossible (%s)", type_evenement)
'@
Ecrire 'backend\app\security\audit.py' $audit

# ---------------------------------------------------------------- 3. security/sessions.py (complet)
$sess = @'
"""Sessions actives : emission du JWT avec jti, verification a chaque
requete, revocation, plafond de sessions, journal de securite.

Toutes les sessions sont stockees dans la base centrale
(table session_utilisateur), pour les trois profils : plateforme
(super admin), interne et externe.
"""
import ipaddress
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request

from app.db import pool_central
from app.security.audit import journaliser

DUREE_SESSION = timedelta(hours=8)
# On ne met a jour "derniere_activite" qu'une fois par minute au plus.
INTERVALLE_ACTIVITE = timedelta(seconds=60)


def _lire_entier_env(nom, defaut, minimum, maximum):
    try:
        valeur = int(os.getenv(nom, str(defaut)))
    except ValueError:
        return defaut
    return max(minimum, min(maximum, valeur))


# Nombre maximal de sessions actives par utilisateur : au-dela, la plus
# ancienne est revoquee a la connexion (motif : limite_sessions).
MAX_SESSIONS_PAR_UTILISATEUR = _lire_entier_env("MAX_SESSIONS_PAR_UTILISATEUR", 5, 1, 50)
# Nombre de reverse proxies de confiance devant le backend (si TRUST_PROXY=1).
NB_PROXIES_CONFIANCE = _lire_entier_env("TRUST_PROXY_HOPS", 1, 1, 5)


def adresse_ip(request: Request) -> str | None:
    # Derriere un reverse proxy, l'IP reelle est dans X-Forwarded-For. On ne
    # lui fait confiance que si TRUST_PROXY=1 (sinon l'IP serait falsifiable).
    if os.getenv("TRUST_PROXY", "0") == "1":
        transfere = request.headers.get("x-forwarded-for")
        if transfere:
            # Saut ajoute par NOTRE proxy (en partant de la droite) : les
            # entrees de gauche sont fournies par le client.
            sauts = [s.strip() for s in transfere.split(",") if s.strip()]
            if len(sauts) >= NB_PROXIES_CONFIANCE:
                try:
                    return str(ipaddress.ip_address(sauts[-NB_PROXIES_CONFIANCE]))
                except ValueError:
                    pass
    return request.client.host if request.client else None


def analyser_user_agent(ua: str | None) -> dict:
    ua = ua or ""

    if re.search(r"iPhone|iPad|iPod", ua):
        systeme = "iOS"
    elif "Android" in ua:
        systeme = "Android"
    elif "Windows" in ua:
        systeme = "Windows"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        systeme = "macOS"
    elif "CrOS" in ua:
        systeme = "ChromeOS"
    elif "Linux" in ua:
        systeme = "Linux"
    else:
        systeme = "Syst\u00e8me inconnu"

    # L'ordre compte : Edge et Opera contiennent aussi "Chrome" et "Safari".
    if "Edg/" in ua or "EdgA/" in ua or "EdgiOS/" in ua:
        navigateur = "Edge"
    elif "OPR/" in ua or "Opera" in ua:
        navigateur = "Opera"
    elif "Firefox/" in ua or "FxiOS/" in ua:
        navigateur = "Firefox"
    elif "Chrome/" in ua or "CriOS/" in ua:
        navigateur = "Chrome"
    elif "Safari/" in ua:
        navigateur = "Safari"
    else:
        navigateur = "Navigateur inconnu"

    appareil = "mobile" if re.search(r"Mobi|iPhone|iPad|Android", ua) else "ordinateur"
    return {"systeme": systeme, "navigateur": navigateur, "appareil": appareil}


def emettre_jeton(claims: dict, request: Request) -> str:
    """Cree la session en base puis signe le JWT contenant son jti.

    `claims` = les champs habituels du jeton (id, email, role, type,
    nomBase, entrepriseId, clientId...), SANS exp ni jti.
    """
    jti = uuid.uuid4().hex
    expiration = datetime.now(timezone.utc) + DUREE_SESSION
    ua = request.headers.get("user-agent", "")
    info = analyser_user_agent(ua)
    entreprise_id = claims.get("entrepriseId")
    nb_limite = 0

    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            # Nettoyage opportuniste : historique conserve 30 jours.
            cur.execute(
                "DELETE FROM session_utilisateur WHERE expire_le < NOW() - INTERVAL '30 days'"
            )
            # Plafond de sessions simultanees. Le verrou (leve au commit) evite que
            # deux connexions simultanees depassent la limite.
            cle_utilisateur = "{}|{}|{}".format(claims["type"], claims["id"], entreprise_id)
            cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (cle_utilisateur,))
            cur.execute(
                """
                UPDATE session_utilisateur
                SET revoquee_le = NOW(), motif_revocation = 'limite_sessions'
                WHERE jti IN (
                    SELECT jti FROM session_utilisateur
                    WHERE type_compte = %s AND utilisateur_id = %s
                      AND entreprise_id IS NOT DISTINCT FROM %s
                      AND revoquee_le IS NULL AND expire_le > NOW()
                    ORDER BY cree_le DESC
                    OFFSET %s
                )
                """,
                (
                    claims["type"], str(claims["id"]),
                    str(entreprise_id) if entreprise_id is not None else None,
                    MAX_SESSIONS_PAR_UTILISATEUR - 1,
                ),
            )
            nb_limite = cur.rowcount
            cur.execute(
                """
                INSERT INTO session_utilisateur
                    (jti, type_compte, utilisateur_id, email, entreprise_id, nom_base,
                     systeme, navigateur, appareil, adresse_ip, user_agent, expire_le)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    jti, claims["type"], str(claims["id"]), claims["email"],
                    str(entreprise_id) if entreprise_id is not None else None,
                    claims.get("nomBase"),
                    info["systeme"], info["navigateur"], info["appareil"],
                    adresse_ip(request), ua[:500], expiration,
                ),
            )
        conn.commit()
    finally:
        pool_central.putconn(conn)

    # Journal (apres le commit, jamais bloquant).
    commun = dict(
        type_compte=claims["type"], utilisateur_id=claims["id"], email=claims["email"],
        entreprise_id=entreprise_id, jti=jti, request=request,
    )
    journaliser("connexion_reussie", succes=True, **commun)
    if nb_limite:
        journaliser("session_revoquee", gravite="avertissement",
                    details={"motif": "limite_sessions", "nb": nb_limite}, **commun)

    return jwt.encode(
        {**claims, "jti": jti, "exp": expiration},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )


def verifier_session(charge: dict) -> None:
    """A appeler apres le decodage du JWT : leve 401 si la session est
    inconnue, revoquee ou expiree. Un jeton sans jti est refuse."""
    jti = charge.get("jti")
    if not jti:
        raise HTTPException(status_code=401, detail="Session invalide, merci de vous reconnecter.")

    maintenant = datetime.now(timezone.utc)
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT revoquee_le, expire_le, derniere_activite FROM session_utilisateur WHERE jti = %s",
                (jti,),
            )
            ligne = cur.fetchone()

            if not ligne or ligne[0] is not None or ligne[1] <= maintenant:
                raise HTTPException(
                    status_code=401,
                    detail="Cette session a \u00e9t\u00e9 ferm\u00e9e ou a expir\u00e9. Merci de vous reconnecter.",
                )

            if maintenant - ligne[2] > INTERVALLE_ACTIVITE:
                cur.execute(
                    "UPDATE session_utilisateur SET derniere_activite = NOW() WHERE jti = %s",
                    (jti,),
                )
                conn.commit()
    finally:
        pool_central.putconn(conn)


def revoquer_sessions_par_email(email: str, motif: str, type_compte: str | None = None) -> int:
    """Ferme toutes les sessions actives d'une adresse email (ex. apres
    une reinitialisation de mot de passe)."""
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            requete = """
                UPDATE session_utilisateur
                SET revoquee_le = NOW(), motif_revocation = %s
                WHERE LOWER(email) = LOWER(%s) AND revoquee_le IS NULL
            """
            params = [motif, email]
            if type_compte:
                requete += " AND type_compte = %s"
                params.append(type_compte)
            cur.execute(requete, params)
            nombre = cur.rowcount
        conn.commit()
    finally:
        pool_central.putconn(conn)

    if nombre:
        journaliser("session_revoquee", gravite="avertissement", type_compte=type_compte,
                    email=email, details={"motif": motif, "nb": nombre})
    return nombre
'@
Ecrire 'backend\app\security\sessions.py' $sess

# ---------------------------------------------------------------- 4. routers/sessions.py (complet)
$rout = @'
from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import pool_central
from app.security.audit import journaliser
from app.security.auth_dependency import utilisateur_connecte, exiger_role_admin

# Sessions de la personne connectee (tous profils : plateforme, interne, externe)
router = APIRouter(prefix="/api/sessions", tags=["sessions"])

# Gestion par l'Administrateur de l'entreprise
router_admin = APIRouter(prefix="/api/admin/sessions", tags=["sessions-admin"])

COLONNES = (
    "jti, systeme, navigateur, appareil, adresse_ip, cree_le, "
    "derniere_activite, expire_le, email, type_compte, utilisateur_id"
)
ACTIVE = "revoquee_le IS NULL AND expire_le > NOW()"
COL_EVT = (
    "id, cree_le, type_evenement, gravite, succes, email, host(adresse_ip), "
    "systeme, navigateur, acteur_email, details"
)


def _lire(requete: str, params: tuple) -> list:
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(requete, params)
            return cur.fetchall()
    finally:
        pool_central.putconn(conn)


def _ecrire(requete: str, params: tuple) -> int:
    conn = pool_central.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute(requete, params)
            nombre = cur.rowcount
        conn.commit()
        return nombre
    finally:
        pool_central.putconn(conn)


def _formater(ligne, jti_courant: str) -> dict:
    return {
        "id": ligne[0],
        "systeme": ligne[1],
        "navigateur": ligne[2],
        "appareil": ligne[3],
        "adresseIp": ligne[4],
        "creeLe": ligne[5].isoformat(),
        "derniereActivite": ligne[6].isoformat(),
        "expireLe": ligne[7].isoformat(),
        "email": ligne[8],
        "typeCompte": ligne[9],
        "utilisateurId": ligne[10],
        "courante": ligne[0] == jti_courant,
    }


def _formater_evt(l) -> dict:
    return {
        "id": l[0], "creeLe": l[1].isoformat(), "type": l[2], "gravite": l[3],
        "succes": l[4], "email": l[5], "adresseIp": l[6], "systeme": l[7],
        "navigateur": l[8], "acteur": l[9], "details": l[10],
    }


def _journal(type_evt, u, request, gravite="info", details=None):
    journaliser(
        type_evt, gravite=gravite, type_compte=u.get("type"), utilisateur_id=u.get("id"),
        email=u.get("email"), entreprise_id=u.get("entrepriseId"), jti=u.get("jti"),
        request=request, details=details,
    )


def _evenements(base_sql, base_params, type_evt, gravite, email, limit, avant):
    where, params = [base_sql], list(base_params)
    if type_evt:
        where.append("type_evenement = %s")
        params.append(type_evt)
    if gravite:
        where.append("gravite = %s")
        params.append(gravite)
    if email:
        where.append("email = LOWER(%s)")
        params.append(email)
    if avant:
        where.append("id < %s")
        params.append(avant)
    limite = max(1, min(int(limit), 200))
    lignes = _lire(
        f"SELECT {COL_EVT} FROM evenement_securite WHERE {' AND '.join(where)} "
        "ORDER BY id DESC LIMIT %s",
        tuple(params + [limite]),
    )
    return {"evenements": [_formater_evt(l) for l in lignes]}


# ---------------------------------------------------------------------
# Mes appareils
# ---------------------------------------------------------------------

@router.get("")
def lister_mes_sessions(utilisateur: dict = Depends(utilisateur_connecte)):
    lignes = _lire(
        f"""
        SELECT {COLONNES} FROM session_utilisateur
        WHERE type_compte = %s AND utilisateur_id = %s AND {ACTIVE}
        ORDER BY derniere_activite DESC
        """,
        (utilisateur["type"], str(utilisateur["id"])),
    )
    return {"sessions": [_formater(l, utilisateur["jti"]) for l in lignes]}


@router.get("/evenements")
def mes_evenements(
    limit: int = 20,
    avant: int | None = None,
    type: str | None = None,
    utilisateur: dict = Depends(utilisateur_connecte),
):
    """Journal de securite de la personne connectee (ses propres evenements)."""
    return _evenements(
        "(LOWER(email) = LOWER(%s) OR (type_compte = %s AND utilisateur_id = %s))",
        (utilisateur["email"], utilisateur["type"], str(utilisateur["id"])),
        type, None, None, limit, avant,
    )


@router.post("/deconnexion")
def deconnexion(request: Request, utilisateur: dict = Depends(utilisateur_connecte)):
    """Deconnexion reelle : le jeton devient inutilisable cote serveur."""
    _ecrire(
        "UPDATE session_utilisateur SET revoquee_le = NOW(), motif_revocation = 'deconnexion' "
        "WHERE jti = %s AND revoquee_le IS NULL",
        (utilisateur["jti"],),
    )
    _journal("deconnexion", utilisateur, request)
    return {"message": "D\u00e9connexion effectu\u00e9e."}


@router.post("/autres/revoquer")
def revoquer_les_autres_sessions(request: Request, utilisateur: dict = Depends(utilisateur_connecte)):
    nombre = _ecrire(
        """
        UPDATE session_utilisateur
        SET revoquee_le = NOW(), motif_revocation = 'revoquee_par_utilisateur'
        WHERE type_compte = %s AND utilisateur_id = %s AND jti <> %s AND revoquee_le IS NULL
        """,
        (utilisateur["type"], str(utilisateur["id"]), utilisateur["jti"]),
    )
    _journal("session_revoquee", utilisateur, request, "avertissement",
             {"motif": "revoquee_par_utilisateur", "nb": nombre})
    return {"message": f"{nombre} session(s) ferm\u00e9e(s).", "fermees": nombre}


@router.delete("/{jti}")
def revoquer_ma_session(jti: str, request: Request, utilisateur: dict = Depends(utilisateur_connecte)):
    # Le filtre sur type + id empeche de fermer la session de quelqu'un d'autre.
    nombre = _ecrire(
        """
        UPDATE session_utilisateur
        SET revoquee_le = NOW(), motif_revocation = 'revoquee_par_utilisateur'
        WHERE jti = %s AND type_compte = %s AND utilisateur_id = %s AND revoquee_le IS NULL
        """,
        (jti, utilisateur["type"], str(utilisateur["id"])),
    )
    if nombre == 0:
        raise HTTPException(status_code=404, detail="Session introuvable ou d\u00e9j\u00e0 ferm\u00e9e.")
    _journal("session_revoquee", utilisateur, request, "info",
             {"motif": "revoquee_par_utilisateur", "cible_jti": jti})
    return {"message": "Session ferm\u00e9e."}


# ---------------------------------------------------------------------
# Administration (Admin de l'entreprise : uniquement SON entreprise)
# ---------------------------------------------------------------------

def _entreprise_admin(admin: dict) -> str:
    entreprise_id = admin.get("entrepriseId")
    if entreprise_id is None:
        raise HTTPException(status_code=403, detail="Action r\u00e9serv\u00e9e \u00e0 l'administrateur de l'entreprise.")
    return str(entreprise_id)


def _journal_admin(admin, request, details):
    journaliser(
        "action_admin", gravite="avertissement", type_compte=admin.get("type"),
        utilisateur_id=admin.get("id"), email=admin.get("email"),
        entreprise_id=admin.get("entrepriseId"), jti=admin.get("jti"),
        request=request, acteur_email=admin.get("email"), details=details,
    )


@router_admin.get("")
def lister_sessions_entreprise(admin: dict = Depends(exiger_role_admin)):
    lignes = _lire(
        f"""
        SELECT {COLONNES} FROM session_utilisateur
        WHERE entreprise_id = %s AND {ACTIVE}
        ORDER BY derniere_activite DESC
        """,
        (_entreprise_admin(admin),),
    )
    return {"sessions": [_formater(l, admin["jti"]) for l in lignes]}


@router_admin.get("/evenements")
def evenements_entreprise(
    limit: int = 30,
    avant: int | None = None,
    type: str | None = None,
    gravite: str | None = None,
    email: str | None = None,
    admin: dict = Depends(exiger_role_admin),
):
    """Journal de securite de l'entreprise (filtre impose par le jeton)."""
    return _evenements("entreprise_id = %s", (_entreprise_admin(admin),),
                       type, gravite, email, limit, avant)


@router_admin.delete("/utilisateur/{utilisateur_id}")
def revoquer_toutes_sessions_utilisateur(
    utilisateur_id: str,
    request: Request,
    type_compte: str = "interne",
    admin: dict = Depends(exiger_role_admin),
):
    if type_compte not in ("interne", "externe"):
        raise HTTPException(status_code=400, detail="Type de compte invalide.")

    nombre = _ecrire(
        """
        UPDATE session_utilisateur
        SET revoquee_le = NOW(), motif_revocation = 'revoquee_par_admin'
        WHERE entreprise_id = %s AND type_compte = %s AND utilisateur_id = %s
          AND revoquee_le IS NULL
        """,
        (_entreprise_admin(admin), type_compte, utilisateur_id),
    )
    _journal_admin(admin, request, {"motif": "revoquer_toutes_sessions", "cible_id": utilisateur_id,
                                    "cible_type": type_compte, "nb": nombre})
    return {"message": f"{nombre} session(s) ferm\u00e9e(s).", "fermees": nombre}


@router_admin.delete("/{jti}")
def revoquer_session_entreprise(jti: str, request: Request, admin: dict = Depends(exiger_role_admin)):
    nombre = _ecrire(
        """
        UPDATE session_utilisateur
        SET revoquee_le = NOW(), motif_revocation = 'revoquee_par_admin'
        WHERE jti = %s AND entreprise_id = %s AND revoquee_le IS NULL
        """,
        (jti, _entreprise_admin(admin)),
    )
    if nombre == 0:
        raise HTTPException(status_code=404, detail="Session introuvable ou d\u00e9j\u00e0 ferm\u00e9e.")
    _journal_admin(admin, request, {"motif": "revoquer_session", "cible_jti": jti})
    return {"message": "Session ferm\u00e9e."}
'@
Ecrire 'backend\app\routers\sessions.py' $rout

# ---------------------------------------------------------------- 5. auth.py (patch par ancres ASCII)
$a = Lire 'backend\app\routers\auth.py'
$t = $a.Texte
if ($t.Contains('journaliser(')) { "--  auth.py deja patche" }
else {
    $ancreImport = 'from app.security.sessions import emettre_jeton, revoquer_sessions_par_email' + "`n"
    Unique $t $ancreImport 'import sessions'
    $t = $t.Replace($ancreImport, $ancreImport + 'from app.security.audit import journaliser' + "`n")

    $ancreSA = '            enregistrer_echec(email)' + "`n" + '            etat_apres = etat_protection(email)' + "`n"
    Unique $t $ancreSA 'echec super_admin'
    $blocSA = '            journaliser("connexion_echouee", gravite="avertissement", succes=False,' + "`n" +
              '                        type_compte="plateforme", email=email, request=request,' + "`n" +
              '                        details={"raison": "identifiants"})' + "`n"
    $t = $t.Replace($ancreSA, $blocSA + $ancreSA)

    $ancreFin = "`n" + '    enregistrer_echec(email)' + "`n" + '    etat_apres = etat_protection(email)' + "`n"
    Unique $t $ancreFin 'echec final'
    $blocFin = "`n" + '    journaliser("connexion_echouee", gravite="avertissement", succes=False,' + "`n" +
               '                type_compte=(ligne_index[2] if ligne_index else None), email=email,' + "`n" +
               '                entreprise_id=(ligne_index[0] if ligne_index else None), request=request,' + "`n" +
               '                details={"raison": "identifiants"})' + "`n" +
               '    enregistrer_echec(email)' + "`n" + '    etat_apres = etat_protection(email)' + "`n"
    $t = $t.Replace($ancreFin, $blocFin)

    $ancreReset = '    revoquer_sessions_par_email(email, "mot_de_passe_reinitialise", "plateforme")' + "`n"
    Unique $t $ancreReset 'reset mot de passe'
    $t = $t.Replace($ancreReset, $ancreReset + '    journaliser("mdp_reinitialise", gravite="avertissement", succes=True,' + "`n" +
                    '                type_compte="plateforme", email=email)' + "`n")
    $a.Texte = $t
    Sauver $a
    "OK  backend\app\routers\auth.py (4 points d'appel)"
}

# ---------------------------------------------------------------- 6. frontend : composant + api + page + css
$jsx = @'
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
'@
Ecrire 'frontend\src\components\ActiviteRecente.jsx' $jsx

# sessionsApi.js : ajout en fin de fichier (idempotent)
$api = Join-Path $racine 'frontend\src\api\sessionsApi.js'
if (-not (Test-Path $api)) { throw "Introuvable : sessionsApi.js" }
if (-not ([System.IO.File]::ReadAllText($api, $utf8)).Contains('listerMesEvenements')) {
    Copy-Item $api "$api.$horo.bak"
    $ajout = "`n// Journal de securite (phase A)`n" +
      'export const listerMesEvenements = (limite = 20) => appelAuth("GET", `/sessions/evenements?limit=${limite}`);' + "`n" +
      'export const listerEvenementsEntreprise = (limite = 30) => appelAuth("GET", `/admin/sessions/evenements?limit=${limite}`);' + "`n"
    [System.IO.File]::AppendAllText($api, $ajout, $utf8)
    "OK  frontend\src\api\sessionsApi.js"
} else { "--  sessionsApi.js deja a jour" }

# Appareils.jsx : import + rendu
$p = Lire 'frontend\src\pages\Appareils.jsx'
$t = $p.Texte
if ($t.Contains('ActiviteRecente')) { "--  Appareils.jsx deja patche" }
else {
    $ancreI = '} from "../api/sessionsApi";' + "`n"
    Unique $t $ancreI 'import sessionsApi'
    $t = $t.Replace($ancreI, $ancreI + 'import ActiviteRecente from "../components/ActiviteRecente";' + "`n")
    $ancreR = '      {admin && (' + "`n" + '        <section className="panel appareils-section">'
    Unique $t $ancreR 'bloc admin'
    $t = $t.Replace($ancreR, '      <ActiviteRecente />' + "`n" + '      {admin && <ActiviteRecente admin />}' + "`n`n" + $ancreR)
    $p.Texte = $t
    Sauver $p
    "OK  frontend\src\pages\Appareils.jsx"
}

# CSS : ajout en fin de fichier (idempotent) + correctif du titre masque
$css = Join-Path $racine 'frontend\src\styles\global.css'
if (-not (Test-Path $css)) { throw "Introuvable : global.css" }
$marque = '/* --- Appareils / securite --- */'
if (-not ([System.IO.File]::ReadAllText($css, $utf8)).Contains($marque)) {
    Copy-Item $css "$css.$horo.bak"
    $bloc = "`n$marque`n" +
".appareils-page { padding-top: 96px; }`n" +
".activite-liste { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }`n" +
".activite-item { display: flex; flex-wrap: wrap; gap: 8px; align-items: baseline; font-size: 0.9rem; }`n" +
".activite-date { opacity: 0.7; min-width: 9.5rem; }`n" +
".activite-gravite--avertissement { color: #b45309; }`n" +
".activite-gravite--critique { color: #b91c1c; font-weight: 600; }`n"
    [System.IO.File]::AppendAllText($css, $bloc, $utf8)
    "OK  frontend\src\styles\global.css"
} else { "--  global.css deja a jour" }

"`nTERMINE. Etape suivante : appliquer le SQL (voir instructions)."