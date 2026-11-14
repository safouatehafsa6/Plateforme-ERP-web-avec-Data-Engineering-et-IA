
$ErrorActionPreference = "Stop"

$path = Join-Path (Get-Location) "frontend\src\styles\global.css"

if (-not (Test-Path -LiteralPath $path)) {
    throw "Fichier CSS introuvable : $path"
}

$text = [System.IO.File]::ReadAllText(
    $path,
    [System.Text.Encoding]::UTF8
)

$marker = "/* Correctif cible pour le titre Mes appareils */"

if ($text.Contains($marker)) {
    Write-Host "Le correctif est deja present. Aucun changement."
    exit 0
}

$anchor = "/* ===== Param"
$index = $text.IndexOf($anchor, [System.StringComparison]::Ordinal)

if ($index -lt 0) {
    throw "Ancre CSS introuvable. Aucun changement effectue."
}

$newline = "`r`n"
if ($text.Contains("`n") -and -not $text.Contains("`r`n")) {
    $newline = "`n"
}

$block = @'
/* Correctif cible pour le titre Mes appareils */
.appareils-page {
  padding-top: calc(64px + 1.5rem);
}

'@

$block = $block -replace "`r?`n", $newline

$backup = "$path.bak"
if (Test-Path -LiteralPath $backup) {
    $backup = "$path.$(Get-Date -Format 'yyyyMMdd-HHmmss').bak"
}

Copy-Item -LiteralPath $path -Destination $backup

$updated = $text.Insert($index, $block)
$encoding = New-Object System.Text.UTF8Encoding($false)

[System.IO.File]::WriteAllText($path, $updated, $encoding)

Write-Host "Correction appliquee."
Write-Host "Sauvegarde : $backup"
Write-Host "Fichier modifie : $path"
