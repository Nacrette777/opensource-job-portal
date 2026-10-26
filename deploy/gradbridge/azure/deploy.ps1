param(
    [Parameter(Mandatory)][string]$EnvFile,          # private file: secrets (see azure.env.example)
    [Parameter(Mandatory)][string]$RrSourceDir,      # checkout of the GradBridge Reactive Resume fork
    [string]$SubscriptionId = '<subscription-id>',
    [string]$Location = 'australiaeast',
    [string]$Prefix = 'gradbridge',
    [string]$ImageTag = '1',
    [int]$MonthlyBudget = 0,                         # AUD/month; required with -Execute
    [string]$BudgetEmail = '',
    [switch]$Execute                                  # without it, only print the commands
)
# GradBridge on Azure Container Apps (S3-07). Creates PAID resources when run with -Execute.
# Without -Execute it prints every command it would run, with secret values masked, so the
# plan can be reviewed first. Order: group + budget -> registry -> PostgreSQL -> Azure Files
# -> Container Apps environment -> images (built in ACR) -> rr -> api -> OAuth client -> site,
# recruiter. See docs/gradbridge-deployment.md section 5.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path

# --- settings -----------------------------------------------------------------------------
$cfg = @{}
foreach ($line in Get-Content $EnvFile) {
    if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') { $cfg[$Matches[1]] = $Matches[2].Trim().Trim('"') }
}
$required = 'DJANGO_SECRET_KEY', 'PG_ADMIN_PASSWORD', 'PEELJOBS_DB_PASSWORD', 'RR_DB_PASSWORD', 'RR_AUTH_SECRET', 'RR_TOKEN_ENCRYPTION_KEY', 'TIME_ZONE'
$missing = $required | Where-Object { -not $cfg[$_] }
if ($missing) { throw "missing in ${EnvFile}: $($missing -join ', ')" }
$secretValues = $required | Where-Object { $_ -ne 'TIME_ZONE' } | ForEach-Object { $cfg[$_] }

$rg = "$Prefix-rg"; $acr = ($Prefix -replace '[^a-z0-9]', '') + 'acr'; $envName = "$Prefix-env"
$pg = "$Prefix-pg"; $storage = ($Prefix -replace '[^a-z0-9]', '') + 'files'; $logs = "$Prefix-logs"
if ($Execute -and $MonthlyBudget -le 0) { throw '-MonthlyBudget is required with -Execute' }

function Show([string]$text) {
    foreach ($s in $secretValues) { if ($s) { $text = $text.Replace($s, '***') } }
    Write-Host $text
}
function Az([string[]]$a, [switch]$Capture) {
    Show ("az " + ($a -join ' '))
    if (-not $Execute) { return '<dry-run>' }
    $out = & az @a --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "az $($a[0]) $($a[1]) failed" }
    if ($Capture) { return ($out -join "`n").Trim() }
}
function Step([string]$name) { Write-Host "`n== $name" -ForegroundColor Cyan }

if ($Execute) {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) { throw 'Azure CLI (az) is not installed' }
    Az @('account', 'set', '--subscription', $SubscriptionId)
    Az @('extension', 'add', '--name', 'containerapp', '--upgrade')
}

# --- 1. resource group and budget ---------------------------------------------------------
Step '1. Resource group and monthly budget alert'
Az @('group', 'create', '-n', $rg, '-l', $Location, '--tags', "project=$Prefix")
Az @('consumption', 'budget', 'create', '--budget-name', "$Prefix-monthly", '--amount', "$MonthlyBudget",
     '--category', 'cost', '--time-grain', 'monthly', '--resource-group', $rg,
     '--start-date', (Get-Date -Day 1).ToString('yyyy-MM-dd'), '--end-date', (Get-Date -Day 1).AddYears(1).ToString('yyyy-MM-dd'))
if ($BudgetEmail) { Show "   (then add an 80% / 100% notification to $BudgetEmail in the portal: Cost Management > Budgets)" }

# --- 2. registry, logs, environment -------------------------------------------------------
Step '2. Container registry, Log Analytics, Container Apps environment'
Az @('acr', 'create', '-g', $rg, '-n', $acr, '--sku', 'Basic', '--admin-enabled', 'false')
# One user-assigned identity, allowed to pull from the registry before any app exists
# (a system identity would only get the role after its first, failing, image pull).
Az @('identity', 'create', '-g', $rg, '-n', "$Prefix-pull", '-l', $Location)
$pullId = Az @('identity', 'show', '-g', $rg, '-n', "$Prefix-pull", '--query', 'id', '-o', 'tsv') -Capture
$pullPrincipal = Az @('identity', 'show', '-g', $rg, '-n', "$Prefix-pull", '--query', 'principalId', '-o', 'tsv') -Capture
$acrId = Az @('acr', 'show', '-n', $acr, '--query', 'id', '-o', 'tsv') -Capture
Az @('role', 'assignment', 'create', '--assignee-object-id', $pullPrincipal, '--assignee-principal-type', 'ServicePrincipal', '--role', 'AcrPull', '--scope', $acrId)
if (-not $Execute) { $pullId = '<pull-identity-id>' }
Az @('monitor', 'log-analytics', 'workspace', 'create', '-g', $rg, '-n', $logs, '-l', $Location)
$logsId = Az @('monitor', 'log-analytics', 'workspace', 'show', '-g', $rg, '-n', $logs, '--query', 'customerId', '-o', 'tsv') -Capture
$logsKey = Az @('monitor', 'log-analytics', 'workspace', 'get-shared-keys', '-g', $rg, '-n', $logs, '--query', 'primarySharedKey', '-o', 'tsv') -Capture
if ($Execute) { $secretValues += $logsKey }
Az @('containerapp', 'env', 'create', '-g', $rg, '-n', $envName, '-l', $Location, '--logs-workspace-id', $logsId, '--logs-workspace-key', $logsKey)
$domain = Az @('containerapp', 'env', 'show', '-g', $rg, '-n', $envName, '--query', 'properties.defaultDomain', '-o', 'tsv') -Capture
if (-not $Execute) { $domain = '<env-default-domain>' }
$url = @{ site = "https://$Prefix-site.$domain"; recruiter = "https://$Prefix-recruiter.$domain"; api = "https://$Prefix-api.$domain"; rr = "https://$Prefix-rr.$domain" }
Show ("   public URLs: " + (($url.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join '  '))

# --- 3. PostgreSQL ---------------------------------------------------------------------------
Step '3. PostgreSQL Flexible Server, two databases, two users'
Az @('postgres', 'flexible-server', 'create', '-g', $rg, '-n', $pg, '-l', $Location, '--tier', 'Burstable', '--sku-name', 'Standard_B1ms',
     '--storage-size', '32', '--version', '16', '--admin-user', 'gbadmin', '--admin-password', $cfg.PG_ADMIN_PASSWORD,
     '--public-access', '0.0.0.0', '--backup-retention', '7', '--yes')
foreach ($db in @(@{ name = 'peeljobs'; user = 'peeljobs'; pw = $cfg.PEELJOBS_DB_PASSWORD }, @{ name = 'reactive_resume'; user = 'reactive_resume'; pw = $cfg.RR_DB_PASSWORD })) {
    Az @('postgres', 'flexible-server', 'db', 'create', '-g', $rg, '-s', $pg, '-d', $db.name)
    Az @('postgres', 'flexible-server', 'execute', '-n', $pg, '-u', 'gbadmin', '-p', $cfg.PG_ADMIN_PASSWORD, '-d', $db.name,
         '-q', "CREATE USER $($db.user) WITH PASSWORD '$($db.pw)'; GRANT ALL ON DATABASE $($db.name) TO $($db.user); GRANT ALL ON SCHEMA public TO $($db.user);")
}
Show '   NOTE: --public-access 0.0.0.0 admits Azure services only; replace with VNet integration for production.'
$pgHost = "$pg.postgres.database.azure.com"

# --- 4. Azure Files ------------------------------------------------------------------------
Step '4. Storage account and file shares (api /data, rr /app/data)'
Az @('storage', 'account', 'create', '-g', $rg, '-n', $storage, '-l', $Location, '--sku', 'Standard_LRS', '--kind', 'StorageV2', '--min-tls-version', 'TLS1_2', '--allow-blob-public-access', 'false')
$storageKey = Az @('storage', 'account', 'keys', 'list', '-g', $rg, '-n', $storage, '--query', '[0].value', '-o', 'tsv') -Capture
if ($Execute) { $secretValues += $storageKey }
foreach ($share in 'api-data', 'rr-data') {
    Az @('storage', 'share-rm', 'create', '-g', $rg, '--storage-account', $storage, '-n', $share, '--quota', '5')
    Az @('containerapp', 'env', 'storage', 'set', '-g', $rg, '-n', $envName, '--storage-name', $share, '--azure-file-account-name', $storage,
         '--azure-file-account-key', $storageKey, '--azure-file-share-name', $share, '--access-mode', 'ReadWrite')
}

# --- 5. images (built in ACR from the exact commits) ---------------------------------------
Step '5. Images built in the registry'
Show "   PeelJobs commit: $(git -C $repo rev-parse --short HEAD)   RR commit: $(git -C $RrSourceDir rev-parse --short HEAD)"
Az @('acr', 'build', '-r', $acr, '-t', "gradbridge/api:$ImageTag", (Join-Path $repo 'backend'))
Az @('acr', 'build', '-r', $acr, '-t', "gradbridge/rr:$ImageTag", $RrSourceDir)
foreach ($app in 'site', 'recruiter') {
    Az @('acr', 'build', '-r', $acr, '-t', "gradbridge/${app}:$ImageTag", '-f', (Join-Path $repo 'deploy\gradbridge\sveltekit.Dockerfile'),
         '--build-arg', "PUBLIC_API_BASE_URL=$($url.api)/api/v1", '--build-arg', "PUBLIC_SITE_URL=$($url[$app])",
         '--build-arg', "PUBLIC_RECRUITER_URL=$($url.recruiter)", '--build-arg', "PUBLIC_JOBSEEKER_URL=$($url.site)", (Join-Path $repo $app))
}

# --- 6. container apps (YAML, so volumes and mount options can be set) ---------------------
$work = Join-Path ([IO.Path]::GetTempPath()) "$Prefix-aca"
New-Item -ItemType Directory -Force $work | Out-Null
function App([string]$name, [int]$port, [string]$image, [hashtable]$secrets, [hashtable]$envs, [string]$share, [string]$mount, [string]$mountOptions) {
    $envId = if ($Execute) { Az @('containerapp', 'env', 'show', '-g', $rg, '-n', $envName, '--query', 'id', '-o', 'tsv') -Capture } else { '<env-id>' }
    $secretYaml = ($secrets.GetEnumerator() | ForEach-Object { "      - name: $($_.Key)`n        value: `"$($_.Value)`"" }) -join "`n"
    $secretBlock = if ($secrets.Count) { "    secrets:`n$secretYaml" } else { '' }
    $envYaml = ($envs.GetEnumerator() | ForEach-Object {
        if ($_.Value -like 'secret:*') { "          - name: $($_.Key)`n            secretRef: $($_.Value.Substring(7))" }
        else { "          - name: $($_.Key)`n            value: `"$($_.Value)`"" } }) -join "`n"
    $volume = if ($share) { "    volumes:`n      - name: data`n        storageType: AzureFile`n        storageName: $share`n        mountOptions: `"$mountOptions`"" } else { '' }
    $volumeMount = if ($share) { "        volumeMounts:`n          - volumeName: data`n            mountPath: $mount" } else { '' }
    $yaml = @"
location: $Location
type: Microsoft.App/containerApps
identity:
  type: UserAssigned
  userAssignedIdentities:
    ${pullId}: {}
properties:
  managedEnvironmentId: $envId
  configuration:
    ingress:
      external: true
      targetPort: $port
      transport: auto
    registries:
      - server: $acr.azurecr.io
        identity: $pullId
$secretBlock
  template:
    scale:
      minReplicas: 1
      maxReplicas: 1
$volume
    containers:
      - name: $name
        image: $acr.azurecr.io/$image
        resources:
          cpu: 0.5
          memory: 1Gi
        env:
$envYaml
$volumeMount
"@
    $file = Join-Path $work "$name.yaml"
    Set-Content $file $yaml -Encoding utf8
    Show "   --- $name.yaml ---"; Show $yaml
    try {
        Az @('containerapp', 'create', '-g', $rg, '-n', "$Prefix-$name", '--yaml', $file)
    } finally {
        Remove-Item $file -ErrorAction SilentlyContinue   # it holds secret values
    }
}

Step '6. rr (uid 1000 must own its share; one replica: refresh-token reuse window and JWKS are in-process)'
App 'rr' 3000 "gradbridge/rr:$ImageTag" @{
    'database-url' = "postgresql://reactive_resume:$($cfg.RR_DB_PASSWORD)@${pgHost}:5432/reactive_resume?sslmode=require"
    'auth-secret'  = $cfg.RR_AUTH_SECRET
} @{ APP_URL = $url.rr; DATABASE_URL = 'secret:database-url'; AUTH_SECRET = 'secret:auth-secret'; LOCAL_STORAGE_PATH = '/app/data' } 'rr-data' '/app/data' 'uid=1000,gid=1000,dir_mode=0750,file_mode=0640'

Step '7. api (uid 10001 must own its share; migrations on start while it has one replica)'
App 'api' 8000 "gradbridge/api:$ImageTag" @{
    'secret-key' = $cfg.DJANGO_SECRET_KEY; 'db-password' = $cfg.PEELJOBS_DB_PASSWORD; 'token-key' = $cfg.RR_TOKEN_ENCRYPTION_KEY
} @{
    SECRET_KEY = 'secret:secret-key'; DB_NAME = 'peeljobs'; DB_USER = 'peeljobs'; DB_PASSWORD = 'secret:db-password'; DB_HOST = $pgHost; DB_PORT = '5432'
    ALLOWED_HOSTS = "$Prefix-api.$domain,$Prefix-api"; CSRF_TRUSTED_ORIGINS = "$($url.site),$($url.recruiter)"; CORS_ALLOWED_ORIGINS = "$($url.site),$($url.recruiter)"
    SITE_FRONTEND_URL = $url.site; RECRUITER_FRONTEND_URL = $url.recruiter; TIME_ZONE = $cfg.TIME_ZONE; DJANGO_MIGRATE_ON_START = '1'
    RR_BASE_URL = $url.rr; RR_INTERNAL_URL = $url.rr; RR_TOKEN_ENCRYPTION_KEY = 'secret:token-key'
    RR_OAUTH_REDIRECT_URI = "$($url.site)/profile/integrations/rr/callback/"
} 'api-data' '/data' 'uid=10001,gid=10001,dir_mode=0750,file_mode=0640'

Step '8. OAuth client: register once, then store the three values as api secrets'
Show "   az containerapp exec -g $rg -n $Prefix-api --command `"python manage.py setup_rr_dev_integration --allow-production --client-name 'GradBridge PeelJobs' --output /data/rr-oauth.json`""
Show '   Read /data/rr-oauth.json once, delete it, then:'
Show "   az containerapp secret set -g $rg -n $Prefix-api --secrets rr-client-id=<id> rr-client-secret=<secret>"
Show "   az containerapp update -g $rg -n $Prefix-api --set-env-vars RR_OAUTH_CLIENT_ID=secretref:rr-client-id RR_OAUTH_CLIENT_SECRET=secretref:rr-client-secret"

Step '9. site and recruiter'
foreach ($app in 'site', 'recruiter') {
    App $app 3000 "gradbridge/${app}:$ImageTag" @{} @{ ORIGIN = $url[$app]; NODE_ENV = 'production' } '' '' ''
}

Step '10. After deploying'
Show '   - python manage.py load_gradbridge_locations (az containerapp exec ... api)'
Show '   - one warm-up PDF render after each RR deployment (the first render loads the renderer, ~20 s in dev)'
Show '   - run the cloud acceptance checklist: docs/gradbridge-deployment.md section 6a'
if (-not $Execute) { Write-Host "`nDry run only: nothing was created. Re-run with -Execute -MonthlyBudget <AUD> after the checklist in section 5.0 is signed off." -ForegroundColor Yellow }
