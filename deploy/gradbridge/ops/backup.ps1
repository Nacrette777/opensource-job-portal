param(
    [Parameter(Mandatory)][string]$Project,     # compose project, e.g. gradbridge
    [Parameter(Mandatory)][string]$BackupRoot,  # private folder for backups (never in the repo)
    [Parameter(Mandatory)][string]$Label        # backup folder name, e.g. 2026-10-26-before-upgrade
)
# Online backup of a GradBridge compose stack (deploy/gradbridge/compose.yml):
#   1. PeelJobs DB and RR DB with pg_dump -Fc (each a consistent snapshot),
#   2. then the api /data volume (published JSON/PDF) and the RR /app/data volume.
# Databases go first, so every file a dump points to is already on disk when the
# volumes are archived; files newer than the dump are merely unreferenced.
# Secrets (the env file, above all RR_TOKEN_ENCRYPTION_KEY) are NOT in the backup; keep
# them separately. See docs/gradbridge-deployment.md section 10.
$ErrorActionPreference = 'Stop'
$dir = Join-Path $BackupRoot $Label
New-Item -ItemType Directory -Force $dir | Out-Null
$started = Get-Date
$timer = [Diagnostics.Stopwatch]::StartNew()

foreach ($db in @('peeljobs-db', 'rr-db')) {
    $container = "$Project-$db-1"
    docker exec $container sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /tmp/backup.dump' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "pg_dump failed for $container" }
    docker cp "${container}:/tmp/backup.dump" "$dir\$db.dump" | Out-Null
    docker exec $container rm /tmp/backup.dump | Out-Null
}
foreach ($vol in @('api_data', 'rr_data')) {
    docker run --rm -v "${Project}_${vol}:/v:ro" -v "${dir}:/b" alpine:3.20 tar czf "/b/$vol.tgz" -C /v . | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "archive failed for $vol" }
}
$timer.Stop()

$files = Get-ChildItem $dir -File | Where-Object Name -ne 'manifest.json' | ForEach-Object {
    [ordered]@{ name = $_.Name; bytes = $_.Length; sha256 = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower() }
}
[ordered]@{
    project = $Project; label = $Label
    started = $started.ToString('s'); seconds = [math]::Round($timer.Elapsed.TotalSeconds, 1)
    images = (docker ps --filter "label=com.docker.compose.project=$Project" --format '{{.Names}}={{.Image}}')
    files = @($files)
} | ConvertTo-Json -Depth 4 | Set-Content "$dir\manifest.json" -Encoding utf8
Get-Content "$dir\manifest.json"
