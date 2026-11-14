# patch-etape1.ps1 - backend\app\security\sessions.py
# 1) plafond de sessions simultanees  2) adresse_ip durcie (sauts de confiance + validation)
$ErrorActionPreference = 'Stop'
$chemin = Join-Path (Get-Location).Path 'backend\app\security\sessions.py'
if (-not (Test-Path $chemin)) { throw "Introuvable : $chemin (lance le script depuis la racine du projet)" }

$utf8  = New-Object System.Text.UTF8Encoding($false)
$brut  = [System.IO.File]::ReadAllText($chemin, $utf8)
$crlf  = $brut.Contains("`r`n")
$t     = $brut -replace "`r`n", "`n"
$modif = $false

# --- 1. import ipaddress ---
if ($t -notmatch '(?m)^import ipaddress') {
    $ancre = "import os`nimport re`n"
    if (-not $t.Contains($ancre)) { throw "Ancre 'import os/import re' introuvable" }
    $t = $t.Replace($ancre, "import ipaddress`nimport os`nimport re`n")
    $modif = $true
    "OK  import ipaddress ajoute"
} else { "--  import ipaddress deja present" }

# --- 2. constantes ---
if ($t -notmatch 'MAX_SESSIONS_PAR_UTILISATEUR') {
    $ancre = "INTERVALLE_ACTIVITE = timedelta(seconds=60)`n"
    if (-not $t.Contains($ancre)) { throw "Ancre INTERVALLE_ACTIVITE introuvable" }
    $ajout = @'


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

'@
    $ajout = $ajout -replace "`r`n", "`n"
    $t = $t.Replace($ancre, $ancre + $ajout)
    $modif = $true
    "OK  constantes ajoutees"
} else { "--  constantes deja presentes" }

# --- 3. adresse_ip durcie ---
if ($t -notmatch 'NB_PROXIES_CONFIANCE\]') {
    $ancre = @'
        if transfere:
            return transfere.split(",")[0].strip()[:45]
'@
    $ancre = $ancre -replace "`r`n", "`n"
    if (-not $t.Contains($ancre)) { throw "Ancre adresse_ip introuvable (fonction deja modifiee ?)" }
    $nouveau = @'
        if transfere:
            # On prend le saut ajoute par NOTRE proxy (en partant de la droite) :
            # les entrees de gauche sont fournies par le client, donc falsifiables.
            sauts = [s.strip() for s in transfere.split(",") if s.strip()]
            if len(sauts) >= NB_PROXIES_CONFIANCE:
                try:
                    return str(ipaddress.ip_address(sauts[-NB_PROXIES_CONFIANCE]))
                except ValueError:
                    pass
'@
    $nouveau = $nouveau -replace "`r`n", "`n"
    $t = $t.Replace($ancre, $nouveau)
    $modif = $true
    "OK  adresse_ip durcie"
} else { "--  adresse_ip deja durcie" }

# --- 4. plafond de sessions dans emettre_jeton ---
if ($t -notmatch 'limite_sessions') {
    $ancre = "INTERVAL '30 days'" + '"' + "`n            )`n"
    if (-not $t.Contains($ancre)) { throw "Ancre du nettoyage 30 jours introuvable" }
    $bloc = @'

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
'@
    $bloc = $bloc -replace "`r`n", "`n"
    # le bloc se termine par un saut de ligne : sinon il serait colle a "cur.execute(" suivant
    $t = $t.Replace($ancre, $ancre + $bloc.TrimStart("`n") + "`n")
    $modif = $true
    "OK  plafond de sessions ajoute"
} else { "--  plafond deja present" }

if (-not $modif) { "Rien a faire : fichier deja a jour."; return }

$bak = "$chemin.bak"
if (Test-Path $bak) { $bak = "$chemin.$(Get-Date -Format 'yyyyMMdd-HHmmss').bak" }
Copy-Item $chemin $bak
if ($crlf) { $t = $t -replace "`n", "`r`n" }
[System.IO.File]::WriteAllText($chemin, $t, $utf8)
"Sauvegarde : $bak"
"Ecrit      : $chemin"