param(
    [Parameter(Mandatory)][string]$EnvFile,          # private file: secrets (see azure.env.example)
    [Parameter(Mandatory)][string]$RrSourceDir,      # checkout of the GradBridge Reactive Resume fork
    [string]$SubscriptionId = '<subscription-id>',
    [string]$Location = 'eastasia',
    [string]$Prefix = 'gradbridge',
    [string]$ImageTag = '1',
    [int]$MonthlyBudget = 0,                         # in the subscription's billing currency; required with -Execute
    [int]$From = 1,                                  # resume at this step after fixing a failure
    [int]$To = 9,
    [switch]$Execute                                  # without it, only print the commands
)
# GradBridge on Azure Container Apps (S3-07). Creates PAID resources when run with -Execute.
# Without -Execute it prints every command it would run, with secret values masked.
# Steps: 1 group + budget, 2 registry + pull identity + logs + environment, 3 PostgreSQL,
# 4 Azure Files, 5 images (built locally, pushed to ACR), 6 rr, 7 OAuth client, 8 api,
# 9 site + recruiter. Every step can be re-run; -From resumes after a failure.
# See docs/gradbridge-deployment.md section 5.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$private = Split-Path -Parent (Resolve-Path $EnvFile)

# --- settings -----------------------------------------------------------------------------
$cfg = @{}
foreach ($line in Get-Content $EnvFile) {
    if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)$') { $cfg[$Matches[1]] = $Matches[2].Trim().Trim('"') }
}
$required = 'DJANGO_SECRET_KEY', 'PG_ADMIN_PASSWORD', 'PEELJOBS_DB_PASSWORD', 'RR_DB_PASSWORD', 'RR_AUTH_SECRET', 'RR_TOKEN_ENCRYPTION_KEY', 'TIME_ZONE'
$missing = $required | Where-Object { -not $cfg[$_] }
if ($missing) { throw "missing in ${EnvFile}: $($missing -join ', ')" }
$script:secretValues = @($required | Where-Object { $_ -ne 'TIME_ZONE' } | ForEach-Object { $cfg[$_] })
$oauthFile = Join-Path $private 'rr-oauth.json'      # written by step 7, read by step 8
$oauth = $null
if (Test-Path $oauthFile) {
    $oauth = Get-Content $oauthFile -Raw | ConvertFrom-Json
    $script:secretValues += $oauth.RR_OAUTH_CLIENT_SECRET
}

$rg = "$Prefix-rg"; $acr = ($Prefix -replace '[^a-z0-9]', '') + 'acr'; $envName = "$Prefix-env"
$pg = "$Prefix-pg"; $storage = ($Prefix -replace '[^a-z0-9]', '') + 'files'; $logs = "$Prefix-logs"; $pull = "$Prefix-pull"
if ($Execute -and $From -le 1 -and $MonthlyBudget -le 0) { throw '-MonthlyBudget is required with -Execute' }

# The az executable, called by path: the helper below is also named Az, and PowerShell names are case-insensitive.
$script:azExe = (Get-Command az -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1).Source
if ($Execute -and -not $script:azExe) { throw 'Azure CLI (az) is not installed or not on PATH' }

function Show([string]$text) {
    foreach ($s in $script:secretValues) { if ($s) { $text = $text.Replace($s, '***') } }
    Write-Host $text
}
function Az([string[]]$a, [switch]$Capture, [switch]$AllowFail) {
    Show ("az " + ($a -join ' '))
    if (-not $Execute) { return '<dry-run>' }
    $out = & $script:azExe @a --only-show-errors 2>&1
    if ($LASTEXITCODE -ne 0) {
        $msg = (($out | Out-String).Trim())
        if ($AllowFail) { Show "   WARNING (continuing): $msg"; return $null }
        Show "   ERROR: $msg"
        throw "az $($a[0]) $($a[1]) failed (step $script:step)"
    }
    if ($Capture) { return (($out | Where-Object { $_ -is [string] }) -join "`n").Trim() }
}
function Run([string]$exe, [string[]]$a) {
    Show ("$exe " + ($a -join ' '))
    if (-not $Execute) { return }
    & $exe @a
    if ($LASTEXITCODE -ne 0) { throw "$exe failed (step $script:step)" }
}
function Step([int]$n, [string]$name) {
    $script:step = $n
    $run = $n -ge $From -and $n -le $To
    Write-Host "`n== $n. $name$(if (-not $run) { ' (skipped)' })" -ForegroundColor Cyan
    return $run
}

if ($Execute) {
    Az @('account', 'set', '--subscription', $SubscriptionId)
    Az @('extension', 'add', '--name', 'containerapp', '--upgrade')
    foreach ($ns in 'Microsoft.App', 'Microsoft.OperationalInsights', 'Microsoft.ContainerRegistry', 'Microsoft.DBforPostgreSQL', 'Microsoft.Storage', 'Microsoft.ManagedIdentity') {
        Az @('provider', 'register', '--namespace', $ns, '--wait')
    }
}

$facts = @{ domain = '<env-default-domain>'; envId = '<env-id>'; pullId = '<pull-identity-id>' }
function EnvFacts {
    if (-not $Execute) { return }
    $script:facts = @{
        domain = Az @('containerapp', 'env', 'show', '-g', $rg, '-n', $envName, '--query', 'properties.defaultDomain', '-o', 'tsv') -Capture
        envId  = Az @('containerapp', 'env', 'show', '-g', $rg, '-n', $envName, '--query', 'id', '-o', 'tsv') -Capture
        pullId = Az @('identity', 'show', '-g', $rg, '-n', $pull, '--query', 'id', '-o', 'tsv') -Capture
    }
}

# --- 1 --------------------------------------------------------------------------------------
if (Step 1 'Resource group and monthly budget alert') {
    Az @('group', 'create', '-n', $rg, '-l', $Location, '--tags', "project=$Prefix")
    # Subscription budget through the REST API ('az consumption budget create' is rejected with
    # "use filter interface" on current API versions). Alerts go to the subscription's Owners at
    # 80 % and 100 % of actual cost and 100 % of forecast. The amount is in the billing currency.
    # If this fails, create the budget in the portal (Cost Management > Budgets).
    $start = (Get-Date -Day 1).ToString('yyyy-MM-01T00:00:00Z')
    $alert = { param($t, $kind) @{ enabled = $true; operator = 'GreaterThanOrEqualTo'; threshold = $t; thresholdType = $kind; contactRoles = @('Owner') } }
    $budget = @{ properties = @{ category = 'Cost'; amount = $MonthlyBudget; timeGrain = 'Monthly'
        timePeriod = @{ startDate = $start; endDate = (Get-Date -Day 1).AddYears(1).ToString('yyyy-MM-01T00:00:00Z') }
        notifications = @{ actual80 = (& $alert 80 'Actual'); actual100 = (& $alert 100 'Actual'); forecast100 = (& $alert 100 'Forecasted') } } }
    $budgetFile = Join-Path ([IO.Path]::GetTempPath()) "$Prefix-budget.json"
    Set-Content $budgetFile ($budget | ConvertTo-Json -Depth 6) -Encoding utf8
    Az @('rest', '--method', 'put', '--url', "https://management.azure.com/subscriptions/$SubscriptionId/providers/Microsoft.Consumption/budgets/$Prefix-monthly?api-version=2023-05-01",
         '--body', "@$budgetFile") -AllowFail
    Remove-Item $budgetFile -ErrorAction SilentlyContinue
}

# --- 2 --------------------------------------------------------------------------------------
if (Step 2 'Container registry, pull identity, Log Analytics, Container Apps environment') {
    Az @('acr', 'create', '-g', $rg, '-n', $acr, '--sku', 'Basic', '--admin-enabled', 'false', '-l', $Location)
    # One user-assigned identity, allowed to pull before any app exists (a system identity
    # would only get the role after its first, failing, image pull).
    Az @('identity', 'create', '-g', $rg, '-n', $pull, '-l', $Location)
    $principal = Az @('identity', 'show', '-g', $rg, '-n', $pull, '--query', 'principalId', '-o', 'tsv') -Capture
    $acrId = Az @('acr', 'show', '-n', $acr, '--query', 'id', '-o', 'tsv') -Capture
    Az @('role', 'assignment', 'create', '--assignee-object-id', $principal, '--assignee-principal-type', 'ServicePrincipal', '--role', 'AcrPull', '--scope', $acrId)
    Az @('monitor', 'log-analytics', 'workspace', 'create', '-g', $rg, '-n', $logs, '-l', $Location, '--retention-time', '30')
    $logsId = Az @('monitor', 'log-analytics', 'workspace', 'show', '-g', $rg, '-n', $logs, '--query', 'customerId', '-o', 'tsv') -Capture
    $logsKey = Az @('monitor', 'log-analytics', 'workspace', 'get-shared-keys', '-g', $rg, '-n', $logs, '--query', 'primarySharedKey', '-o', 'tsv') -Capture
    if ($Execute) { $script:secretValues += $logsKey }
    # WorkloadProfiles (Consumption profile, billed per use): recent CLI versions otherwise create an
    # "Express" environment, which cannot mount Azure Files.
    $envExists = if ($Execute) { & $script:azExe containerapp env show -g $rg -n $envName --query name -o tsv 2>$null } else { $null }
    if (-not $envExists) {
        Az @('containerapp', 'env', 'create', '-g', $rg, '-n', $envName, '-l', $Location, '--environment-mode', 'WorkloadProfiles',
             '--logs-workspace-id', $logsId, '--logs-workspace-key', $logsKey)
    }
}
if ($To -ge 3) { EnvFacts }
$domain = $facts.domain
$url = @{ site = "https://$Prefix-site.$domain"; recruiter = "https://$Prefix-recruiter.$domain"; api = "https://$Prefix-api.$domain"; rr = "https://$Prefix-rr.$domain" }
Show ("   public URLs: " + (($url.GetEnumerator() | Sort-Object Name | ForEach-Object { "$($_.Name)=$($_.Value)" }) -join '  '))
$pgHost = "$pg.postgres.database.azure.com"

# --- 3 --------------------------------------------------------------------------------------
if (Step 3 'PostgreSQL Flexible Server, two databases, one owner per database') {
    # 'create' on an existing server fails, so a re-run skips it.
    $pgExists = if ($Execute) { & $script:azExe postgres flexible-server show -g $rg -n $pg --query name -o tsv 2>$null } else { $null }
    if (-not $pgExists) { Az @('postgres', 'flexible-server', 'create', '-g', $rg, '-n', $pg, '-l', $Location, '--tier', 'Burstable', '--sku-name', 'Standard_B1ms',
         '--storage-size', '32', '--version', '16', '--admin-user', 'gbadmin', '--admin-password', $cfg.PG_ADMIN_PASSWORD,
         '--public-access', '0.0.0.0', '--backup-retention', '7', '--zonal-resiliency', 'Disabled', '--yes') }
    # PeelJobs migration 0079 creates pg_trgm; Azure only allows extensions on this list.
    Az @('postgres', 'flexible-server', 'parameter', 'set', '-g', $rg, '-s', $pg, '--name', 'azure.extensions', '--value', 'PG_TRGM')
    foreach ($db in 'peeljobs', 'reactive_resume') { Az @('postgres', 'flexible-server', 'db', 'create', '-g', $rg, '-s', $pg, '-n', $db) }
    # Create the two owners from this machine with the local postgres:16 image, through a
    # firewall rule for this machine's public address that is removed again afterwards.
    $ip = if ($Execute) { (Invoke-RestMethod 'https://api.ipify.org').Trim() } else { '<this-machine-ip>' }
    Az @('postgres', 'flexible-server', 'firewall-rule', 'create', '-g', $rg, '-s', $pg, '-n', 'deploy-client', '--start-ip-address', $ip, '--end-ip-address', $ip)
    try {
        foreach ($db in @(@{ name = 'peeljobs'; pw = $cfg.PEELJOBS_DB_PASSWORD }, @{ name = 'reactive_resume'; pw = $cfg.RR_DB_PASSWORD })) {
            $sql = "DO `$`$BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$($db.name)') THEN CREATE ROLE $($db.name) LOGIN PASSWORD '$($db.pw)'; END IF; END`$`$; GRANT $($db.name) TO gbadmin; ALTER DATABASE $($db.name) OWNER TO $($db.name);"
            Run 'docker' @('run', '--rm', '-e', "PGPASSWORD=$($cfg.PG_ADMIN_PASSWORD)", 'postgres:16', 'psql', "host=$pgHost user=gbadmin dbname=postgres sslmode=require", '-v', 'ON_ERROR_STOP=1', '-c', $sql)
            Run 'docker' @('run', '--rm', '-e', "PGPASSWORD=$($cfg.PG_ADMIN_PASSWORD)", 'postgres:16', 'psql', "host=$pgHost user=gbadmin dbname=$($db.name) sslmode=require", '-v', 'ON_ERROR_STOP=1', '-c', "ALTER SCHEMA public OWNER TO $($db.name);")
        }
    } finally {
        Az @('postgres', 'flexible-server', 'firewall-rule', 'delete', '-g', $rg, '-s', $pg, '-n', 'deploy-client', '--yes') -AllowFail
    }
    Show '   NOTE: --public-access 0.0.0.0 admits Azure services only; use VNet integration for production.'
}

# --- 4 --------------------------------------------------------------------------------------
if (Step 4 'Storage account and file shares (api /data, rr /app/data)') {
    Az @('storage', 'account', 'create', '-g', $rg, '-n', $storage, '-l', $Location, '--sku', 'Standard_LRS', '--kind', 'StorageV2', '--min-tls-version', 'TLS1_2', '--allow-blob-public-access', 'false')
    $storageKey = Az @('storage', 'account', 'keys', 'list', '-g', $rg, '-n', $storage, '--query', '[0].value', '-o', 'tsv') -Capture
    if ($Execute) { $script:secretValues += $storageKey }
    foreach ($share in 'api-data', 'rr-data') {
        Az @('storage', 'share-rm', 'create', '-g', $rg, '--storage-account', $storage, '-n', $share, '--quota', '5')
        Az @('containerapp', 'env', 'storage', 'set', '-g', $rg, '-n', $envName, '--storage-name', $share, '--azure-file-account-name', $storage,
             '--azure-file-account-key', $storageKey, '--azure-file-share-name', $share, '--access-mode', 'ReadWrite')
    }
}

# --- 5 --------------------------------------------------------------------------------------
if (Step 5 'Images: built locally from the checked-out commits, pushed to the registry') {
    # Local builds: ACR Tasks (az acr build) are not available on some subscriptions (e.g. Azure for Students).
    Show "   PeelJobs commit: $(git -C $repo rev-parse --short HEAD)   RR commit: $(git -C $RrSourceDir rev-parse --short HEAD)"
    $reg = "$acr.azurecr.io"
    Az @('acr', 'login', '-n', $acr)
    Run 'docker' @('build', '-t', "$reg/gradbridge/api:$ImageTag", (Join-Path $repo 'backend'))
    Run 'docker' @('build', '-t', "$reg/gradbridge/rr:$ImageTag", $RrSourceDir)
    foreach ($app in 'site', 'recruiter') {
        Run 'docker' @('build', '-t', "$reg/gradbridge/${app}:$ImageTag", '-f', (Join-Path $repo 'deploy\gradbridge\sveltekit.Dockerfile'),
             '--build-arg', "PUBLIC_API_BASE_URL=$($url.api)/api/v1", '--build-arg', "PUBLIC_SITE_URL=$($url[$app])",
             '--build-arg', "PUBLIC_RECRUITER_URL=$($url.recruiter)", '--build-arg', "PUBLIC_JOBSEEKER_URL=$($url.site)", (Join-Path $repo $app))
    }
    foreach ($name in 'api', 'rr', 'site', 'recruiter') { Run 'docker' @('push', "$reg/gradbridge/${name}:$ImageTag") }
}

# --- container apps (ARM REST + JSON, so volumes, mount options and identities can be set) --
# 'az containerapp create --yaml' (containerapp extension, API 2025-10-02-preview) fails with
# "could not be converted to System.Boolean" for these definitions; the stable API accepts them.
$appApi = '2025-01-01'
$work = Join-Path ([IO.Path]::GetTempPath()) "$Prefix-aca"
New-Item -ItemType Directory -Force $work | Out-Null
function App([string]$name, [int]$port, [string]$image, [hashtable]$secrets, [hashtable]$envs, [string]$share, [string]$mount, [string]$mountOptions,
             [double]$cpu, [string]$memory, [int]$minReplicas) {
    $envList = @($envs.GetEnumerator() | Sort-Object Name | ForEach-Object {
        if ($_.Value -like 'secret:*') { [ordered]@{ name = $_.Key; secretRef = $_.Value.Substring(7) } }
        else { [ordered]@{ name = $_.Key; value = [string]$_.Value } } })
    $container = [ordered]@{ name = $name; image = "$acr.azurecr.io/$image"; resources = [ordered]@{ cpu = $cpu; memory = $memory }; env = $envList }
    $configuration = [ordered]@{
        activeRevisionsMode = 'Single'
        ingress = [ordered]@{ external = $true; targetPort = $port; transport = 'auto' }
        registries = @([ordered]@{ server = "$acr.azurecr.io"; identity = $facts.pullId })
    }
    if ($secrets.Count) { $configuration.secrets = @($secrets.GetEnumerator() | Sort-Object Name | ForEach-Object { [ordered]@{ name = $_.Key; value = [string]$_.Value } }) }
    $template = [ordered]@{ terminationGracePeriodSeconds = 30; scale = [ordered]@{ minReplicas = $minReplicas; maxReplicas = 1 }; containers = @($container) }
    if ($share) {
        $template.volumes = @([ordered]@{ name = 'data'; storageType = 'AzureFile'; storageName = $share; mountOptions = $mountOptions })
        $container.volumeMounts = @([ordered]@{ volumeName = 'data'; mountPath = $mount })
    }
    $body = [ordered]@{
        location = $Location
        identity = [ordered]@{ type = 'UserAssigned'; userAssignedIdentities = @{ $facts.pullId = @{} } }
        properties = [ordered]@{ environmentId = $facts.envId; configuration = $configuration; template = $template }
    }
    $json = $body | ConvertTo-Json -Depth 12
    $file = Join-Path $work "$name.json"
    Set-Content $file $json -Encoding utf8
    Show "   --- $name.json ---"; Show $json
    try {
        # PUT creates or replaces the app; a changed definition becomes a new revision.
        Az @('rest', '--method', 'put', '--url', "https://management.azure.com$($facts.envId -replace '/managedEnvironments/.*$', '')/containerApps/$Prefix-$name`?api-version=$appApi",
             '--body', "@$file")
    } finally {
        Remove-Item $file -ErrorAction SilentlyContinue   # it holds secret values
    }
    if (-not $Execute) { return }
    for ($i = 0; $i -lt 60; $i++) {
        $state = & $script:azExe containerapp show -g $rg -n "$Prefix-$name" --query properties.provisioningState -o tsv 2>$null
        if ($state -and $state -ne 'InProgress') { break }
        Start-Sleep 10
    }
    Show "   $Prefix-$name provisioning: $state"
    if ($state -ne 'Succeeded') { throw "$Prefix-$name did not provision (step $script:step)" }
}

# --- 6 --------------------------------------------------------------------------------------
if (Step 6 'rr (always 1 replica: refresh-token reuse window and JWKS are in-process)') {
    App 'rr' 3000 "gradbridge/rr:$ImageTag" @{
        'database-url' = "postgresql://reactive_resume:$($cfg.RR_DB_PASSWORD)@${pgHost}:5432/reactive_resume?sslmode=require"
        'auth-secret'  = $cfg.RR_AUTH_SECRET
    } @{ APP_URL = $url.rr; DATABASE_URL = 'secret:database-url'; AUTH_SECRET = 'secret:auth-secret'; LOCAL_STORAGE_PATH = '/app/data' } `
        'rr-data' '/app/data' 'uid=1000,gid=1000,dir_mode=0750,file_mode=0640' '0.5' '1Gi' 1
}

# --- 7 --------------------------------------------------------------------------------------
if (Step 7 'Register the PeelJobs OAuth client at RR (run here; only client id and secret are kept)') {
    if (Test-Path $oauthFile) { Show "   $oauthFile exists: client already registered, skipped" }
    elseif ($Execute) {
        $tmp = Join-Path $private 'rr-oauth.raw.json'
        Remove-Item $tmp -ErrorAction SilentlyContinue
        $env:RR_BASE_URL = $url.rr; $env:RR_INTERNAL_URL = $url.rr
        $env:RR_OAUTH_REDIRECT_URI = "$($url.site)/profile/integrations/rr/callback/"
        Push-Location (Join-Path $repo 'backend')
        try { Run (Join-Path $repo 'backend\.venv\Scripts\python.exe') @('manage.py', 'setup_rr_dev_integration', '--allow-production', '--client-name', 'GradBridge PeelJobs (Azure)', '--output', $tmp) }
        finally { Pop-Location }
        # The command also generates a token key; this deployment keeps the one in the env file.
        $raw = Get-Content $tmp -Raw | ConvertFrom-Json
        @{ RR_OAUTH_CLIENT_ID = $raw.RR_OAUTH_CLIENT_ID; RR_OAUTH_CLIENT_SECRET = $raw.RR_OAUTH_CLIENT_SECRET; RR_OAUTH_REDIRECT_URI = $raw.RR_OAUTH_REDIRECT_URI } |
            ConvertTo-Json | Set-Content $oauthFile -Encoding utf8
        Remove-Item $tmp
        $oauth = Get-Content $oauthFile -Raw | ConvertFrom-Json
        $script:secretValues += $oauth.RR_OAUTH_CLIENT_SECRET
        Show "   client registered: $($oauth.RR_OAUTH_CLIENT_ID)"
    } else { Show '   python manage.py setup_rr_dev_integration --allow-production ... (against the Azure RR)' }
}

# --- 8 --------------------------------------------------------------------------------------
if (Step 8 'api (uid 10001 owns its share; migrations on start while it has one replica)') {
    if ($Execute -and -not $oauth) { throw "step 7 has not produced $oauthFile" }
    App 'api' 8000 "gradbridge/api:$ImageTag" @{
        'secret-key' = $cfg.DJANGO_SECRET_KEY; 'db-password' = $cfg.PEELJOBS_DB_PASSWORD; 'token-key' = $cfg.RR_TOKEN_ENCRYPTION_KEY
        'rr-client-secret' = $(if ($oauth) { $oauth.RR_OAUTH_CLIENT_SECRET } else { 'from-step-7' })
    } @{
        SECRET_KEY = 'secret:secret-key'; DB_NAME = 'peeljobs'; DB_USER = 'peeljobs'; DB_PASSWORD = 'secret:db-password'; DB_HOST = $pgHost; DB_PORT = '5432'
        ALLOWED_HOSTS = "$Prefix-api.$domain,$Prefix-api"; CSRF_TRUSTED_ORIGINS = "$($url.site),$($url.recruiter)"; CORS_ALLOWED_ORIGINS = "$($url.site),$($url.recruiter)"
        SITE_FRONTEND_URL = $url.site; RECRUITER_FRONTEND_URL = $url.recruiter; TIME_ZONE = $cfg.TIME_ZONE; DJANGO_MIGRATE_ON_START = '1'
        RR_BASE_URL = $url.rr; RR_INTERNAL_URL = $url.rr; RR_TOKEN_ENCRYPTION_KEY = 'secret:token-key'
        RR_OAUTH_CLIENT_ID = $(if ($oauth) { $oauth.RR_OAUTH_CLIENT_ID } else { 'from-step-7' }); RR_OAUTH_CLIENT_SECRET = 'secret:rr-client-secret'
        RR_OAUTH_REDIRECT_URI = "$($url.site)/profile/integrations/rr/callback/"
    } 'api-data' '/data' 'uid=10001,gid=10001,dir_mode=0750,file_mode=0640' '0.25' '0.5Gi' 1
}

# --- 9 --------------------------------------------------------------------------------------
if (Step 9 'site and recruiter (scale to zero when idle)') {
    foreach ($app in 'site', 'recruiter') {
        App $app 3000 "gradbridge/${app}:$ImageTag" @{} @{ ORIGIN = $url[$app]; NODE_ENV = 'production' } '' '' '' '0.25' '0.5Gi' 0
    }
}

Write-Host "`nAfter deploying: run 'python manage.py load_gradbridge_locations' in the api app, warm up one PDF render, then the checklist in section 6a." -ForegroundColor Cyan
if (-not $Execute) { Write-Host 'Dry run only: nothing was created.' -ForegroundColor Yellow }
