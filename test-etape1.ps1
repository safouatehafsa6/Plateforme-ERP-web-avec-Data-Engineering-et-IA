# test-etape1.ps1 - preuves : (1) jeton revoque -> 401  (2) plafond de sessions
# Le test ferme les sessions du compte utilise : prends un compte de test.
param(
    [string]$Api   = 'http://localhost:8000',
    [string]$Email = (Read-Host 'Email du compte de test'),
    [int]$Max      = 5
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
    try {
        $r = Invoke-WebRequest @p
        return @{ Code = [int]$r.StatusCode; Corps = $r.Content }
    } catch {
        $code = 0
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        return @{ Code = $code; Corps = '' }
    }
}

function Connexion {
    $r = Appel 'POST' '/api/auth/login' $null @{ email = $Email; motDePasse = $mdp }
    if ($r.Code -ne 200) { throw "Connexion impossible (HTTP $($r.Code)). Captcha requis ou identifiants incorrects ?" }
    return ($r.Corps | ConvertFrom-Json).token
}

$script:tout_ok = $true
function Verifier($nom, $obtenu, $attendu) {
    if ($obtenu -eq $attendu) { Write-Host "[OK] $nom (obtenu $obtenu)" -ForegroundColor Green }
    else { Write-Host "[KO] $nom : attendu $attendu, obtenu $obtenu" -ForegroundColor Red; $script:tout_ok = $false }
}

Write-Host "`n--- Test 1 : un jeton revoque renvoie 401"
$t1 = Connexion
$r = Appel 'GET'  '/api/sessions' $t1 $null;             Verifier 'Jeton valide -> /api/sessions' $r.Code 200
$r = Appel 'POST' '/api/sessions/deconnexion' $t1 $null; Verifier 'Deconnexion' $r.Code 200
$r = Appel 'GET'  '/api/sessions' $t1 $null;             Verifier 'Meme jeton apres deconnexion' $r.Code 401

Write-Host "`n--- Test 2 : plafond de $Max sessions (connexions : $($Max + 1))"
$jetons = @()
for ($i = 1; $i -le ($Max + 1); $i++) { $jetons += Connexion }
$r = Appel 'GET' '/api/sessions' $jetons[0] $null;  Verifier 'Plus ancien jeton revoque' $r.Code 401
$r = Appel 'GET' '/api/sessions' $jetons[-1] $null; Verifier 'Jeton le plus recent valide' $r.Code 200
$nb = @(($r.Corps | ConvertFrom-Json).sessions).Count
Verifier 'Nombre de sessions actives' $nb $Max

Write-Host "`n--- Nettoyage"
$null = Appel 'POST' '/api/sessions/autres/revoquer' $jetons[-1] $null
$null = Appel 'POST' '/api/sessions/deconnexion' $jetons[-1] $null
$mdp = $null

if ($tout_ok) { Write-Host "`nRESULTAT : TOUS LES TESTS REUSSIS" -ForegroundColor Green; exit 0 }
else          { Write-Host "`nRESULTAT : ECHEC" -ForegroundColor Red; exit 1 }