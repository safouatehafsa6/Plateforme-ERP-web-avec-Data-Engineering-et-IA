
$ErrorActionPreference = "Stop"

$racine = (Get-Location).Path
$sortie = Join-Path $racine "analyse_securite_etape1.txt"

$chemins = @(
    "backend\app\security\sessions.py",
    "backend\app\security\auth_dependency.py",
    "backend\app\security\jwt_utils.py",
    "backend\app\routers\sessions.py",
    "backend\app\routers\auth.py",
    "backend\app\main.py",
    "frontend\src\pages\Appareils.jsx",
    "frontend\src\api\sessionsApi.js",
    "frontend\src\App.jsx",
    "frontend\src\components\Navbar.jsx",
    "frontend\src\components\Navigation.jsx",
    "frontend\src\index.css",
    "frontend\src\App.css",
    "frontend\src\pages\Appareils.css",
    "test-401.ps1",
    "scripts\test-401.ps1"
)

$extensionsCss = @()
$repertoire = Join-Path $racine "frontend\src"

if (Test-Path $repertoire) {
    $extensionsCss = Get-ChildItem $repertoire -Recurse -File |
        Where-Object {
            $_.Extension -eq ".css" -and
            $_.FullName -notmatch '[\\/](node_modules|dist)[\\/]'
        } |
        ForEach-Object {
            $_.FullName.Substring($racine.Length + 1)
        }
}

$chemins = @($chemins) + @($extensionsCss) |
    Select-Object -Unique

$contenu = New-Object System.Text.StringBuilder

[void]$contenu.AppendLine("AUDIT DE SECURITE - ETAPE 1")
[void]$contenu.AppendLine("Date : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')")
[void]$contenu.AppendLine("Racine : $racine")
[void]$contenu.AppendLine("Les fichiers .env sont exclus.")
[void]$contenu.AppendLine("")

foreach ($relatif in $chemins) {
    $fichier = Join-Path $racine $relatif

    if (-not (Test-Path -LiteralPath $fichier -PathType Leaf)) {
        continue
    }

    [void]$contenu.AppendLine("")
    [void]$contenu.AppendLine("========== FICHIER : $relatif ==========")

    $lignes = [System.IO.File]::ReadAllLines($fichier)

    foreach ($ligne in $lignes) {
        if ($ligne -match '(?i)JWT_SECRET|SECRET_KEY|PASSWORD|DB_PASSWORD|DATABASE_URL|RECAPTCHA_SECRET|SMTP_PASSWORD|ACCESS_TOKEN|REFRESH_TOKEN') {
            [void]$contenu.AppendLine("[LIGNE MASQUEE - CONFIGURATION SENSIBLE]")
        }
        else {
            [void]$contenu.AppendLine($ligne)
        }
    }
}

$encodage = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText(
    $sortie,
    $contenu.ToString(),
    $encodage
)

Write-Host "Extraction terminee : $sortie"
Write-Host "Verifie le fichier avant de me l'envoyer."
