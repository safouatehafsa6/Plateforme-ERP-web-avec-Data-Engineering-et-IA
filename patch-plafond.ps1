# patch-plafond.ps1 - ajoute le plafond de sessions dans emettre_jeton
$ErrorActionPreference = 'Stop'
$chemin = Join-Path (Get-Location).Path 'backend\app\security\sessions.py'
if (-not (Test-Path $chemin)) { throw "Introuvable : $chemin" }

$utf8 = New-Object System.Text.UTF8Encoding($false)
$brut = [System.IO.File]::ReadAllText($chemin, $utf8)
$crlf = $brut.Contains("`r`n")
$t    = $brut -replace "`r`n", "`n"

if ($t.Contains('limite_sessions''')) { "--  plafond deja present, rien a faire"; return }

# Repere : le debut du INSERT (une seule occurrence attendue)
$repere = "            cur.execute(`n                `"`"`"`n                INSERT INTO session_utilisateur"
if ($t.IndexOf($repere) -lt 0) { throw "Repere INSERT introuvable : envoie-moi le fichier" }
if ($t.IndexOf($repere) -ne $t.LastIndexOf($repere)) { throw "Repere INSERT en double" }

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
$bloc = ($bloc -replace "`r`n", "`n") + "`n"

$t = $t.Replace($repere, $bloc + $repere)

Copy-Item $chemin "$chemin.$(Get-Date -Format 'yyyyMMdd-HHmmss').bak"
if ($crlf) { $t = $t -replace "`n", "`r`n" }
[System.IO.File]::WriteAllText($chemin, $t, $utf8)
"OK  plafond ajoute dans $chemin"