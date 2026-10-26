param(
    [Parameter(Mandatory)][string]$Project,     # NEW compose project to restore into, e.g. gradbridge-restore
    [Parameter(Mandatory)][string]$BackupDir,   # one folder written by backup.ps1
    [Parameter(Mandatory)][string]$EnvFile,     # the environment's env file (URLs and secrets)
    [Parameter(Mandatory)][string]$ImageTag     # image tag to run after restoring
)
# Restore a backup taken by backup.ps1 into a separate compose project (fresh volumes,
# so the source stack and its volumes are never touched). The env file must hold the
# same RR_TOKEN_ENCRYPTION_KEY as when the backup was taken, or every student has to
# reconnect Reactive Resume (see docs/gradbridge-deployment.md section 10).
$ErrorActionPreference = 'Stop'
foreach ($f in 'peeljobs-db.dump', 'rr-db.dump', 'api_data.tgz', 'rr_data.tgz') {
    if (-not (Test-Path (Join-Path $BackupDir $f))) { throw "missing $f in $BackupDir" }
}
# Never restore into a project that already has volumes (would overwrite live data).
$existing = docker volume ls --format '{{.Name}}' | Where-Object { $_ -like "${Project}_*" }
if ($existing) { throw "project $Project already has volumes: $existing" }

Set-Location (Join-Path $PSScriptRoot '..\..\..')
$env:COMPOSE_PROJECT_NAME = $Project
$env:IMAGE_TAG = $ImageTag
$compose = @('compose', '--env-file', $EnvFile, '-f', 'deploy/gradbridge/compose.yml')
$timer = [Diagnostics.Stopwatch]::StartNew()

# 1. Containers and empty volumes; start only the two databases.
docker @compose create 2>&1 | Out-Null
docker @compose up -d --wait peeljobs-db rr-db 2>&1 | Out-Null

# 2. Databases from the dumps.
foreach ($db in 'peeljobs-db', 'rr-db') {
    $container = "$Project-$db-1"
    docker cp (Join-Path $BackupDir "$db.dump") "${container}:/tmp/restore.dump" | Out-Null
    docker exec $container sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error /tmp/restore.dump && rm /tmp/restore.dump'
    if ($LASTEXITCODE -ne 0) { throw "pg_restore failed for $db" }
}

# 3. File volumes from the archives.
foreach ($vol in 'api_data', 'rr_data') {
    docker run --rm -v "${Project}_${vol}:/v" -v "${BackupDir}:/b:ro" alpine:3.20 sh -c "tar xzf /b/$vol.tgz -C /v" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "restore failed for $vol" }
}
# The api image runs as uid 10001 and must be able to write its volume.
docker run --rm -v "${Project}_api_data:/v" alpine:3.20 chown -R 10001:10001 /v | Out-Null

# 4. Applications.
docker @compose up -d --wait 2>&1 | Out-Null
$timer.Stop()
docker @compose ps --format '{{.Service}} {{.Image}} {{.Status}}'
"restore seconds: $([math]::Round($timer.Elapsed.TotalSeconds, 1))"
