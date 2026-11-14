# test-phase-a.ps1 - preuves phase A (utilise un compte de test)
param(
    [string]$Api   = 'http://localhost:8000',
    [string]$Email = (Read-Host 'Email du compte de test')
)
$sec  = Read-Host 'Mot de passe (non affiche)' -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$mdp  = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)

function Appel($methode, $chemin, $token, $corps) {
    $h = @{}
    if ($token) { $h['Authorization'] = "Bearer $token" }
    $p = @{ Uri = "$Api$chemin"; Method = $methode; Headers = $h; UseBasicParsing = $true }
    if ($corps) {
        $p['Body'] = [Text.Encoding]::UTF8.GetBytes(($corps | ConvertTo-Json -Compress))
        $p['ContentType'] = 'application/json'
    }
    try { $r = Invoke-WebRequest @p; return @{ Code = [int]$r.StatusCode; Corps = $r.Content } }
    catch {
        $code = 0
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        return @{ Code = $code; Corps = '' }
    }
}
function Sql($q) { (docker compose exec -T postgres-erp psql -U erp_user -d erp_db -t -A -c $q 2>$null) -join ' ' }
$script:ok = $true
function Verifier($nom, $obtenu, $attendu) {
    if ("$obtenu" -eq "$attendu") { Write-Host "[OK] $nom (obtenu $obtenu)" -ForegroundColor Green }
    else { Write-Host "[KO] $nom : attendu $attendu, obtenu $obtenu" -ForegroundColor Red; $script:ok = $false }
}

$depart = [int](Sql "SELECT COALESCE(MAX(id),0) FROM evenement_securite")

$r = Appel 'POST' '/api/auth/login' $null @{ email = $Email; motDePasse = 'mauvais-mot-de-passe-XXX' }
Verifier 'Login avec mauvais mot de passe' $r.Code 401
$r = Appel 'POST' '/api/auth/login' $null @{ email = $Email; motDePasse = $mdp }
Verifier 'Login correct' $r.Code 200
$token = ($r.Corps | ConvertFrom-Json).token
$r = Appel 'GET' '/api/sessions/evenements' $token $null
Verifier 'GET /api/sessions/evenements' $r.Code 200
$types = @(($r.Corps | ConvertFrom-Json).evenements | ForEach-Object { $_.type })
Verifier 'Evenement connexion_echouee visible' ($types -contains 'connexion_echouee') $true
Verifier 'Evenement connexion_reussie visible' ($types -contains 'connexion_reussie') $true
$r = Appel 'GET' '/api/admin/sessions/evenements' $token $null
Write-Host "[info] journal entreprise (admin) : HTTP $($r.Code) (200 attendu si le compte est Admin)"
$null = Appel 'POST' '/api/sessions/deconnexion' $token $null

Verifier 'connexion_reussie en base'  (Sql "SELECT COUNT(*) FROM evenement_securite WHERE id > $depart AND type_evenement='connexion_reussie' AND email=lower('$Email')") 1
Verifier 'connexion_echouee en base'  (Sql "SELECT COUNT(*) FROM evenement_securite WHERE id > $depart AND type_evenement='connexion_echouee' AND email=lower('$Email')") 1
Verifier 'deconnexion en base'        (Sql "SELECT COUNT(*) FROM evenement_securite WHERE id > $depart AND type_evenement='deconnexion' AND email=lower('$Email')") 1
Verifier 'Aucun secret dans details'  (Sql "SELECT COUNT(*) FROM evenement_securite WHERE id > $depart AND details::text ~* '(password|mot_de_passe|token|secret)'") 0

$m = docker compose exec -T postgres-erp psql -U erp_user -d erp_db -c "UPDATE evenement_securite SET gravite='info' WHERE id=(SELECT MAX(id) FROM evenement_securite)" 2>&1 | Out-String
Verifier 'UPDATE refuse (ajout seul)' ($m -match 'ajout seul') $true
$m = docker compose exec -T postgres-erp psql -U erp_user -d erp_db -c "DELETE FROM evenement_securite WHERE id=(SELECT MAX(id) FROM evenement_securite)" 2>&1 | Out-String
Verifier 'DELETE refuse (ajout seul)' ($m -match 'ajout seul') $true
$mdp = $null
if ($ok) { Write-Host "`nRESULTAT : TOUS LES TESTS REUSSIS" -ForegroundColor Green } else { Write-Host "`nRESULTAT : ECHEC" -ForegroundColor Red }