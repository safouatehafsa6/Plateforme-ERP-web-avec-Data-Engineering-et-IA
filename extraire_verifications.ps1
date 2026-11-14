
$ErrorActionPreference = "Stop"
$racine = (Get-Location).Path
$sortie = Join-Path $racine "verifications_etape1.txt"
$utf8 = New-Object System.Text.UTF8Encoding($false)

$sb = New-Object System.Text.StringBuilder

$fichiers = @(
    "frontend\src\components\Header.jsx",
    "frontend\src\styles\global.css",
    "backend\app\security\sessions.py",
    "backend\app\routers\sessions.py",
    "docker-compose.yml",
    "docker-compose.override.yml"
)

foreach ($relatif in $fichiers) {
    $chemin = Join-Path $racine $relatif

    if (-not (Test-Path -LiteralPath $chemin -PathType Leaf)) {
        continue
    }

    [void]$sb.AppendLine("")
    [void]$sb.AppendLine("===== $relatif =====")

    $lignes = [System.IO.File]::ReadAllLines($chemin)

    if ($relatif -eq "frontend\src\styles\global.css") {
        $motifs = @(
            'page-shell',
            'page-head',
            'app-header',
            'appareils-page'
        )

        $indices = @(
            for ($i = 0; $i -lt $lignes.Length; $i++) {
                foreach ($motif in $motifs) {
                    if ($lignes[$i] -match [regex]::Escape($motif)) {
                        $i
                        break
                    }
                }
            }
        ) | Select-Object -Unique

        $retenues = @{}
        foreach ($i in $indices) {
            $debut = [Math]::Max(0, $i - 5)
            $fin = [Math]::Min($lignes.Length - 1, $i + 12)
            for ($j = $debut; $j -le $fin; $j++) {
                $retenues[$j] = $true
            }
        }

        foreach ($j in ($retenues.Keys | Sort-Object)) {
            [void]$sb.AppendLine(("{0}: {1}" -f ($j + 1), $lignes[$j]))
        }
    }
    elseif ($relatif -like "docker-compose*") {
        for ($i = 0; $i -lt $lignes.Length; $i++) {
            if ($lignes[$i] -match 'TRUST_PROXY|forwarded|ports:|proxy:|backend:|frontend:') {
                $ligne = $lignes[$i]
                if ($ligne -match '(?i)JWT_SECRET|PASSWORD|SECRET_KEY|DATABASE_URL|TOKEN|RECAPTCHA') {
                    $ligne = "[LIGNE MASQUEE - CONFIGURATION SENSIBLE]"
                }
                [void]$sb.AppendLine(("{0}: {1}" -f ($i + 1), $ligne))
            }
        }
    }
    else {
        for ($i = 0; $i -lt $lignes.Length; $i++) {
            if ($lignes[$i] -match '(?i)JWT_SECRET|SECRET_KEY|PASSWORD|DB_PASSWORD|DATABASE_URL|RECAPTCHA_SECRET|SMTP_PASSWORD|ACCESS_TOKEN|REFRESH_TOKEN') {
                [void]$sb.AppendLine("[LIGNE MASQUEE - CONFIGURATION SENSIBLE]")
            }
            else {
                [void]$sb.AppendLine(("{0}: {1}" -f ($i + 1), $lignes[$i]))
            }
        }
    }
}

[void]$sb.AppendLine("")
[void]$sb.AppendLine("===== RECHERCHE DU TEST 401 ET DU PLAFOND =====")

$repertoires = @(
    $racine,
    (Join-Path $racine "scripts"),
    (Join-Path $racine "backend")
)

foreach ($rep in $repertoires) {
    if (-not (Test-Path -LiteralPath $rep -PathType Container)) {
        continue
    }

    Get-ChildItem -LiteralPath $rep -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -match 'test-401\.ps1|sessions.*\.ps1|test.*session.*\.py'
        } |
        ForEach-Object {
            [void]$sb.AppendLine("Fichier de test trouvé : $($_.FullName.Substring($racine.Length + 1))")
        }
}

$encodage = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText($sortie, $sb.ToString(), $encodage)

Write-Host "Extraction terminée : $sortie"
Write-Host "Vérifie les éventuelles valeurs sensibles avant de transmettre le fichier."
