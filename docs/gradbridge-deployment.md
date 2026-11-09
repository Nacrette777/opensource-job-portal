# GradBridge 部署手册（S2-08）

本文说明如何把 GradBridge（PeelJobs 主站 + 招聘端 + Reactive Resume）打包成镜像、在本地做生产式演练，以及按步骤部署到 Azure Container Apps。所有密钥都通过环境变量或平台密钥库注入，仓库里只有占位符。

## 1 组成

| 服务 | 镜像来源 | 端口 | 持久数据 |
|---|---|---|---|
| `api`（Django + gunicorn） | `backend/Dockerfile` | 8000 | `/data`：`private_media/`（已发布简历 JSON/PDF，私有）、`media/` |
| `site`（学生端 SvelteKit） | `deploy/gradbridge/sveltekit.Dockerfile`，上下文 `site/` | 3000 | 无 |
| `recruiter`（招聘端 SvelteKit） | 同上，上下文 `recruiter/` | 3000 | 无 |
| `rr`（Reactive Resume） | GradBridge RR fork 的 `Dockerfile` | 3000 | `/app/data`（RR 文件存储） |
| `peeljobs-db` | `postgres:16` | 5432 | 数据卷 |
| `rr-db` | `postgres:18`（与 RR 开发环境同一大版本；换大版本需要导出导入） | 5432 | 数据卷 |

两个应用各自管理自己的数据库和迁移：Django 不管理 RR 的表，主站也不直接写 RR 数据库。主站与 RR 之间只通过 RR 的 OAuth 与 OpenAPI 交互。

RR 必须使用 GradBridge fork（分支 `fix/gradbridge-runtime` 或其后续合并分支），它包含：

- `POST /api/openapi/resumes/import/json-resume`（带 requestId 幂等的 JSON Resume 导入，S2-05）；
- OAuth refresh token 60 秒宽限期（`refreshTokenReuseInterval`），保证主站续期响应丢失时可以恢复；
- 源码运行时服务端 PDF 的 JSX 修复（仅影响开发模式，镜像本身由 tsdown 构建）。

## 2 配置项

`api` 使用 `DJANGO_SETTINGS_MODULE=jobsp.settings_gradbridge`（镜像默认值），所有环境相关配置来自环境变量：

| 变量 | 必填 | 说明 |
|---|---|---|
| `SECRET_KEY` | 是 | Django 密钥 |
| `DB_NAME` `DB_USER` `DB_PASSWORD` `DB_HOST` `DB_PORT` | 是 | PeelJobs 数据库 |
| `ALLOWED_HOSTS` | 是 | 逗号分隔，含 API 公网主机名和内部服务名 |
| `CSRF_TRUSTED_ORIGINS`、`CORS_ALLOWED_ORIGINS` | 是 | 学生端、招聘端的公网 origin |
| `SITE_FRONTEND_URL`、`RECRUITER_FRONTEND_URL` | 是 | 邮件链接、OAuth 回调地址的基础 |
| `SECURE_COOKIES` | 否 | 默认 `true`；只有纯 HTTP 演练才设 `false` |
| `TIME_ZONE` | 否 | 默认 `Australia/Sydney`（2026-10-27 起；PeelJobs 原值为 `Asia/Kolkata`）。项目关闭了 `USE_TZ`，数据库存的是该时区的本地时间，**必须在首次部署前确定，之后不要修改**，否则所有已存时间都会整体偏移 |
| `SECURE_SSL_REDIRECT` | 否 | 默认 `false`（HTTPS 由入口强制，服务间调用走内部 HTTP） |
| `EMAIL_BACKEND` | 否 | 默认控制台输出；正式环境改为 SMTP/SES |
| `CELERY_TASK_ALWAYS_EAGER` | 否 | 默认 `true`（无 worker 时任务同步执行） |
| `DJANGO_MIGRATE_ON_START` | 否 | `1` 时容器启动先执行迁移；多副本时只在一个地方执行 |
| `GRADBRIDGE_PRIVATE_MEDIA_ROOT` | 否 | 默认 `/data/private_media`，必须是持久卷 |
| `RR_BASE_URL` | 是 | RR 公网地址；同时是 OAuth issuer 基址和 token 的 `resource` |
| `RR_INTERNAL_URL` | 否 | 主站访问 RR 的内部地址（如 `http://rr:3000`） |
| `RR_OAUTH_CLIENT_ID` `RR_OAUTH_CLIENT_SECRET` | 是 | 见第 4 节注册 |
| `RR_OAUTH_REDIRECT_URI` | 是 | `<学生端>/profile/integrations/rr/callback/` |
| `RR_TOKEN_ENCRYPTION_KEY` | 是 | Fernet 密钥，加密学生的 RR refresh token；**轮换会使现有关联失效，学生需重新连接** |

`site`、`recruiter` 的 `PUBLIC_API_BASE_URL`、`PUBLIC_SITE_URL`、`PUBLIC_RECRUITER_URL`、`PUBLIC_JOBSEEKER_URL` 在**构建时**编译进镜像（构建参数），运行时只需 `ORIGIN`（各自的公网地址，SvelteKit 表单 action 的 CSRF 检查依赖它）。因此每个环境要用自己的公网地址构建前端镜像。

`rr` 必填 `APP_URL`（RR 公网地址）、`DATABASE_URL`、`AUTH_SECRET`；文件存储用 `LOCAL_STORAGE_PATH=/app/data` 挂持久卷，或配置 S3 兼容存储的 `S3_*`。

## 3 本地生产式演练

```bash
cp deploy/gradbridge/.env.example <私有目录>/drill.env   # 填入随机密钥
docker compose --env-file <私有目录>/drill.env -f deploy/gradbridge/compose.yml up -d --build
```

演练使用 `*.localhost` 主机名（浏览器会解析到本机），容器通过 `extra_hosts: host-gateway` 访问同一组公网地址。学生端用 `http://localhost:18173`，因为 RR 的动态客户端注册只接受主机名恰为 `localhost` 的 http 回调。

迁移由 `api` 在启动时执行（`DJANGO_MIGRATE_ON_START=1`），RR 启动时自动执行自己的迁移。

注意事项（均来自实际演练）：

- **Windows 上用 PowerShell 执行 `docker compose exec/cp`**。Git Bash 会把参数里的容器路径改写成 Windows 路径（`/data/...` 变成 `D:/Git/data/...`）；如果一定要用 Git Bash，先设 `MSYS_NO_PATHCONV=1`。
- **停止服务用 `docker compose stop` 或不带 `-v` 的 `down`**。`down -v` 会删除数据库、已发布简历和 RR 文件所在的数据卷。
- `api` 镜像的 gunicorn 带 `--no-control-socket`：gunicorn 26 默认在工作目录创建控制套接字（`/app/.gunicorn/gunicorn.ctl`），而容器以非 root 用户运行、对 `/app` 没有写权限，不加会在启动时报权限错误。
- `rr` 服务设置了 `init: true`。RR 镜像让 node 直接作为 PID 1 运行，且没有处理 SIGTERM；不加 init 时 `stop` 要等 10 秒超时后强制结束（退出码 137），加上后 1 秒内正常退出。

### 3.1 从干净检出复现开发与测试（S3-01，2026-10-26 实测）

以下步骤在两个仓库的干净 `git worktree` 上执行过，依赖全部来自锁文件：

| 部分 | 安装 | 检查 |
|---|---|---|
| `backend` | `uv sync --frozen`（`uv.lock`） | 准备 `backend/.env`（`DB_*`、`SECRET_KEY` 等，见第 2 节）后 `python manage.py test --noinput --parallel 1`；设 `REACTIVE_RESUME_DIR` 指向 RR 检出时，导出兼容测试也会运行 |
| `site`、`recruiter` | `pnpm@10.34.9 install --frozen-lockfile`（`pnpm-lock.yaml`） | 先 `cp .env.example .env`（只含公开地址），再 `pnpm run check`；缺少 `.env` 时 svelte-check 会报 `$env/static/public` 没有导出 `PUBLIC_*` |
| RR | `pnpm install --frozen-lockfile`（根 `package.json` 的 `packageManager` 为 pnpm 12.4.2） | `packages/api`、`packages/auth` 下 `vitest run`，以及 `tsgo --noEmit` |

`site/` 同时有 `package-lock.json`（npm）和 `pnpm-lock.yaml`；镜像和上表都以 `pnpm-lock.yaml` 为准。

## 4 注册主站的 OAuth 客户端

每个环境注册一次。`api` 启动后：

```bash
docker compose ... exec api python manage.py setup_rr_dev_integration \
    --allow-production --client-name "GradBridge PeelJobs" --output /data/rr-oauth.json
```

命令通过 RR 的动态客户端注册创建客户端，并生成 Fernet 密钥，写入 `--output` 文件，不在屏幕上输出任何密钥。把文件中的 `RR_OAUTH_CLIENT_ID`、`RR_OAUTH_CLIENT_SECRET`、`RR_TOKEN_ENCRYPTION_KEY` 放入环境（或 Azure 密钥），删除容器里的文件，重建 `api`。回调地址取自 `RR_OAUTH_REDIRECT_URI`，必须与学生端公网地址一致。

## 5 部署到 Azure Container Apps（逐步）

前提：已有订阅和预算上限；本节命令会创建**付费资源**，由 PM 或负责人执行。名称仅为示例。

**状态（2026-10-27）：已部署到 Azure for Students 订阅，区域 eastasia**（订阅策略只允许 malaysiawest、koreacentral、indiasouthcentral、japaneast、eastasia），记录见 5.3。脚本 `deploy/gradbridge/azure/deploy.ps1` 默认只打印将要执行的全部命令（密钥打码），加 `-Execute -MonthlyBudget <订阅计费货币金额>` 才会真正创建资源；`-From/-To` 可以从失败的步骤继续，每一步都可以重复执行。密钥模板见同目录 `azure.env.example`。执行前把 Azure CLI 加入 PATH，并由负责人本人 `az login`。

### 5.0 开通前必须确定的事项（签字后再执行）

| 事项 | 需要谁决定 | 说明 |
|---|---|---|
| 是否仍部署 Azure | advisor / PM | 原计划要求 Azure；若取消需有书面范围决定 |
| 订阅、区域、资源名前缀 | 费用负责人 | 脚本默认 `eastasia`、前缀 `gradbridge`；先用 `az account list-locations` 或门户确认订阅策略允许的区域 |
| 月度预算与告警 | 费用负责人 | 脚本通过 REST 创建订阅级月度预算，实际费用达 80%/100%、预测达 100% 时通知订阅所有者（Owner 角色）。金额按订阅计费货币（学生订阅为美元） |
| 费用估算 | 费用负责人 | 资源与规格：ACR Basic、PostgreSQL Flexible Server Burstable B1ms（32 GB，备份 7 天）、Storage Standard LRS（两个 5 GB 共享）、Container Apps：rr 0.5 vCPU / 1 GiB 常驻 1 个副本，api 0.25 vCPU / 0.5 GiB 常驻 1 个副本，site 与 recruiter 各 0.25 / 0.5 GiB、空闲时缩到 0；Log Analytics 保留 30 天。按 2026-10 Azure 零售价目 API（eastasia，美元）估算：PostgreSQL 约 21 + 存储约 5、ACR 约 5、两个常驻应用空闲时约 18，合计约 50 美元/月，持续高负载时约 85 美元/月（未扣除 Container Apps 每月免费额度） |
| 域名与 HTTPS | PM | 默认使用 Container Apps 自带域名与证书；换自定义域名必须重建前端镜像（公共地址在构建时写入） |
| PostgreSQL 版本 | 部署负责人 | 本地 RR 库为 18、PeelJobs 库为 16；脚本使用 Azure 上稳定提供的 16（RR 要求 16 及以上）。从本地迁移数据时注意大版本差异（导出导入） |
| 网络 | 部署负责人 | 脚本用“允许 Azure 服务”的防火墙规则；正式环境建议改为 VNet 集成 |
| 邮件 | PM | 默认输出到控制台；验收可用合成账号绕过邮件，正式使用需配置 SMTP/SES |
| 密钥保管 | PM | `RR_TOKEN_ENCRYPTION_KEY` 等密钥存入密钥库或密码管理器，与备份分开（第 10 节） |

### 5.1 与 Azure 的兼容性核查

2026-10-27 云端实测：RR 健康检查显示数据库与 Azure Files 存储均正常；PeelJobs 全部迁移（含 0079 的 pg_trgm）在 Azure PostgreSQL 16 上执行成功。下列其余各条为读代码结论。

- RR 本地文件存储只用普通的读、写、建目录、删除，没有符号链接或重命名，可放在 Azure Files（SMB）上；启动时会检查目录可读写，权限不对会立即失败。RR 以 uid 1000 运行，api 以 uid 10001 运行，脚本为两个共享分别设置了 `uid/gid` 挂载选项。
- 主站私有文件使用 Django 的文件系统存储，写入后会重新读取并核对 SHA-256，SMB 上同样适用。
- Azure Blob 不是 S3 兼容存储，不能填入 RR 的 `S3_*`。
- PostgreSQL 16：RR 的迁移只用到 `gen_random_uuid()`（PostgreSQL 13 起提供）。2026-10-26 在临时的 PostgreSQL 16.15 容器上执行了全部 32 个 RR 迁移，并通过导入记录的真实数据库测试（6 项）。
- Container Apps 不能设置 `init`：RR 切换修订版时会等到终止宽限期结束（第 3 节）。
- 冷启动后第一次生成 PDF 较慢（S3-06：开发模式约 20 秒）；每次部署 RR 后先做一次预热渲染。

### 5.2 手工步骤（脚本所做内容的说明）

```bash
RG=gradbridge-rg; LOC=eastasia; ACR=gradbridgeacr; ENV=gradbridge-env
az group create -n $RG -l $LOC
az acr create -g $RG -n $ACR --sku Basic
# 必须是 WorkloadProfiles：新版 CLI 默认建 Express 环境，不能挂载 Azure Files
az containerapp env create -g $RG -n $ENV -l $LOC --environment-mode WorkloadProfiles
```

1. **数据库**：创建一台 Azure Database for PostgreSQL Flexible Server，建两个库与两个独立用户（`peeljobs`、`reactive_resume`），只开放给 Container Apps 环境（VNet 集成或防火墙规则）。开启自动备份。RR 需要 PostgreSQL 16 及以上。
2. **文件存储**：创建 Storage Account 与两个 Azure Files 共享（`gradbridge-api-data`、`gradbridge-rr-data`），用 `az containerapp env storage set` 挂到环境中。Azure Blob 不是 S3 兼容存储，不能直接填到 RR 的 `S3_ENDPOINT`；如需对象存储，另行接入 S3 兼容服务。
3. **镜像**：先确定四个公网地址（Container Apps 的 FQDN 或自定义域名），再构建并推送：
   ```bash
   az acr login -n $ACR
   docker build -t $ACR.azurecr.io/gradbridge/api:1 backend
   docker build -t $ACR.azurecr.io/gradbridge/rr:1 <RR fork 路径>
   docker build -f deploy/gradbridge/sveltekit.Dockerfile site \
     --build-arg PUBLIC_API_BASE_URL=https://<api>/api/v1 --build-arg PUBLIC_SITE_URL=https://<site> \
     --build-arg PUBLIC_RECRUITER_URL=https://<recruiter> --build-arg PUBLIC_JOBSEEKER_URL=https://<site> \
     -t $ACR.azurecr.io/gradbridge/site:1
   # recruiter 同理，PUBLIC_SITE_URL 用招聘端地址
   docker push ...（四个镜像）
   ```
4. **RR**：创建 `rr` 应用（外部 ingress，目标端口 3000），挂载 `gradbridge-rr-data` 到 `/app/data`，密钥 `AUTH_SECRET`、`DATABASE_URL`，环境变量 `APP_URL=https://<rr>`。最少 1 个副本（refresh token 宽限期与 JWKS 依赖进程常驻）。Container Apps 无法设置 `init`，RR 在切换修订版时会等到终止宽限期（默认 30 秒）结束才退出；数据都在数据库和文件卷中，不会丢失，只是切换慢一些。
5. **API**：创建 `api` 应用（外部 ingress，端口 8000），挂载 `gradbridge-api-data` 到 `/data`，按第 2 节配置；`RR_INTERNAL_URL` 可用 RR 的内部 FQDN。首次部署设 `DJANGO_MIGRATE_ON_START=1` 并保持 1 个副本；扩容前改为用 Container Apps Job 执行 `python manage.py migrate`。
6. **注册 OAuth 客户端**：按第 4 节在 `api` 容器内执行，把三个值存为 `api` 的 secrets，重启修订版。
7. **前端**：创建 `site`、`recruiter` 应用（外部 ingress，端口 3000），设置 `ORIGIN`。
8. **验收**：按第 6 节逐项检查，然后重启各应用的修订版，确认关联、已发布 PDF、RR 草稿仍在。

部署顺序：数据库 → 存储 → RR → API → 注册客户端 → 前端。回滚：Container Apps 保留旧修订版，切回旧修订版即可；数据库迁移只新增表与列，旧代码可以忽略它们。

### 5.3 实际部署记录（2026-10-27，Azure CLI 2.91.0）

公共地址（Container Apps 自带域名与证书）：

| 应用 | 地址 |
|---|---|
| 学生端 | `https://gradbridge-site.mangowater-328d9d2e.eastasia.azurecontainerapps.io` |
| 招聘端 | `https://gradbridge-recruiter.mangowater-328d9d2e.eastasia.azurecontainerapps.io` |
| API | `https://gradbridge-api.mangowater-328d9d2e.eastasia.azurecontainerapps.io` |
| RR | `https://gradbridge-rr.mangowater-328d9d2e.eastasia.azurecontainerapps.io` |

镜像来自 PeelJobs `1949a46`、RR `363c45a0d`，在本机构建后推送到 `gradbridgeacr`（标签 `1`）。资源组 `gradbridge-rg` 中有：ACR、拉取身份 `gradbridge-pull`、Log Analytics、环境 `gradbridge-env`、PostgreSQL 16 `gradbridge-pg`、存储账户 `gradbridgefiles`（共享 `api-data`、`rr-data`）和四个应用。迁移在 api 首次启动时执行到 0086，地区数据已导入。

首次真实执行时遇到并已在脚本中修正的问题：

| 问题 | 处理 |
|---|---|
| `az consumption budget create` 返回 400（要求新版筛选接口） | 改用 REST API 创建订阅级预算 |
| `az acr build`（ACR Tasks）在学生订阅不可用 | 本机 `docker build` 后推送 |
| `--high-availability` 参数已被移除 | 改为 `--zonal-resiliency Disabled` |
| `flexible-server db create -d`、`firewall-rule --rule-name` 参数名变化 | 改为 `-n`；防火墙规则用 `-s <服务器> -n <规则>` |
| 新版 CLI 默认创建 Express 环境，不支持 Azure Files | 用 `--environment-mode WorkloadProfiles` 重建环境（域名随之改变，前端镜像需重建） |
| `az containerapp create --yaml`（扩展使用 2025-10-02-preview API）返回 “could not be converted to System.Boolean” | 改为 `az rest` 以正式版 API `2025-01-01` 提交 JSON 定义 |

运维命令（在 api 容器内执行管理命令、暂停数据库以节省费用）：

```powershell
az containerapp exec -g gradbridge-rg -n gradbridge-api --command "python manage.py showmigrations peeldb"
az postgres flexible-server stop -g gradbridge-rg -n gradbridge-pg    # 停止期间不收计算费，7 天后 Azure 会自动启动
az postgres flexible-server start -g gradbridge-rg -n gradbridge-pg
az group delete -n gradbridge-rg                                      # 全部删除（不可恢复，先按第 10 节备份）
```

注册新账号需要邮件验证，而邮件目前只输出到 api 容器日志。在配置 SMTP 之前，验证链接要从日志中取得：`az containerapp logs show -g gradbridge-rg -n gradbridge-api --tail 100 | Select-String verify-email`。

### 5.4 发信：Azure Communication Services（S4-02，2026-11-08）
api 通过 ACS 的 REST 接口发信（`backend/jobsp/acs_email.py`）。它用连接串做 HMAC 签名，所以不需要 Azure SDK，也不需要 ACS SMTP 所要求的 Entra 应用注册。实际执行过的开通命令如下（`communication` CLI 扩展 1.14.0）：

```powershell
az provider register --namespace Microsoft.Communication --wait
az extension add --name communication
az communication email create --name gradbridge-email -g gradbridge-rg --location global --data-location Australia
az communication email domain create --domain-name AzureManagedDomain --email-service-name gradbridge-email -g gradbridge-rg --location global --domain-management AzureManaged --user-engmnt-tracking Disabled
$domainId = az communication email domain show --domain-name AzureManagedDomain --email-service-name gradbridge-email -g gradbridge-rg --query id -o tsv
az communication create --name gradbridge-acs -g gradbridge-rg --location global --data-location Australia --linked-domains $domainId
az communication email domain sender-username update --sender-username DoNotReply --username DoNotReply --display-name GradBridge --domain-name AzureManagedDomain --email-service-name gradbridge-email -g gradbridge-rg
```

- 把连接串（`az communication list-key --name gradbridge-acs -g gradbridge-rg --query primaryConnectionString -o tsv`，属于密钥，不要打印）和发件地址 `DoNotReply@<mailFromSenderDomain>` 写入 env 文件同目录下的 `acs-email.json`，格式为 `{"connection_string": "...", "sender": "..."}`。之后 `deploy.ps1` 第 8 步会把连接串设为 api 的密钥 `acs-email-connection`，并设置 `EMAIL_BACKEND=jobsp.acs_email.EmailBackend` 和 `DEFAULT_FROM_EMAIL`。没有这个文件时，邮件只输出到 api 日志。
- Azure 托管域名的发送配额很低，只适合演示和测试；正式使用应换成自有域名（需要在 DNS 中添加 SPF/DKIM 记录并验证）。ACS 接受邮件后返回 202，再异步投递；投递失败只能在 ACS 资源的日志里看到。
- 费用按封数计算，演示用量下几乎为零。

### 5.5 密钥放进 Key Vault（S4-07，2026-11-08）
应用的密钥存放在 Key Vault `gradbridge-kv-53888c`（RBAC 模式，软删除保留 7 天，未开启清除保护）。Container Apps 用拉取镜像的托管身份 `gradbridge-pull` 读取这些密钥（角色为 “Key Vault Secrets User”）；部署者需要有 “Key Vault Secrets Officer” 角色。

```powershell
az provider register --namespace Microsoft.KeyVault --wait
az keyvault create --name gradbridge-kv-53888c -g gradbridge-rg --location eastasia --enable-rbac-authorization true --retention-days 7
$kvId = az keyvault show -n gradbridge-kv-53888c --query id -o tsv
az role assignment create --role "Key Vault Secrets Officer" --assignee-object-id (az ad signed-in-user show --query id -o tsv) --assignee-principal-type User --scope $kvId
az role assignment create --role "Key Vault Secrets User" --assignee-object-id (az identity show -g gradbridge-rg -n gradbridge-pull --query principalId -o tsv) --assignee-principal-type ServicePrincipal --scope $kvId
```

- 带 `-KeyVault gradbridge-kv-53888c` 运行 `deploy.ps1` 时，第 6 步和第 8 步会先把每个应用密钥写入同名的 Key Vault 机密（通过临时文件写入，命令行和输出中都不出现密钥值），然后在应用里只引用 `keyVaultUrl`。另外还会写入 `pg-admin-password`。
  - rr 使用的机密：`auth-secret`、`database-url`。
  - api 使用的机密：`secret-key`、`db-password`、`token-key`、`rr-client-secret`、`acs-email-connection`。
- 本机的 `azure.env`、`rr-oauth.json`、`acs-email.json` 仍作为备份保留：它们是部署时写入 Key Vault 的来源，也能在 Key Vault 不可用时去掉 `-KeyVault` 重新部署。
- 轮换密钥：先改本机文件，再带 `-KeyVault` 重新运行对应的步骤。也可以直接在 Key Vault 里新建版本，然后重启对应的应用修订版。注意 `token-key` 不能单独轮换，否则已保存的 RR 令牌会无法解密，学生需要重新关联 RR。
- 部署脚本每次只更新一个镜像标签，所以 rr 和 api 标签不同时要分两次运行。例如：`-ImageTag 5 -From 6 -To 6 -KeyVault ...`，然后 `-ImageTag 10 -From 8 -To 8 -KeyVault ...`。

### 5.6 可用性监控（S4-08，2026-11-08）
- Application Insights `gradbridge-insights`，基于现有的 Log Analytics `gradbridge-logs`，区域 eastasia。
- 3 个标准可用性测试，每 15 分钟一次，超时 60 秒，失败会重试，要求返回 200，并检查 TLS 证书（到期前 7 天报警）：

| 测试 | 地址 | 检测地点 |
|---|---|---|
| `gb-api` | api `/api/v1/jobs/?page_size=1`（会访问数据库） | Australia East、Southeast Asia |
| `gb-rr` | rr `/api/auth/get-session` | Australia East、Southeast Asia |
| `gb-site` | site 首页 | Australia East（只用一个地点，减少把缩到 0 的 site 唤醒的次数） |

- 告警规则 `gradbridge-availability`：任一测试在 30 分钟内的可用率低于 60% 时触发，每 15 分钟评估一次，严重级别 1。动作组 `gradbridge-owner` 会以公共告警格式发邮件给订阅的 Owner 角色成员，不需要填写邮箱地址。
- 费用：标准测试每次检测约 0.0005 美元，每个地点各算一次。按每月约 1.4 万次计算，约 7 美元，另加少量日志写入费用。
- 2026-11-08 首批结果：5 组全部通过。api 0.25–1.1 秒，rr 0.17–0.74 秒，site 平均 21 秒（每次都从 0 个副本冷启动）。

```powershell
az extension add --name application-insights
az monitor app-insights component create --app gradbridge-insights -g gradbridge-rg --location eastasia --workspace <gradbridge-logs id> --kind web --application-type web
az monitor app-insights web-test create -g gradbridge-rg --name gb-api --location eastasia --web-test-kind standard --defined-web-test-name gb-api --synthetic-monitor-id gb-api --enabled true --frequency 900 --timeout 60 --retry-enabled true --locations Id=emea-au-syd-edge --locations Id=apac-sg-sin-azr --http-verb GET --request-url <url> --expected-status-code 200 --ssl-check true --ssl-lifetime-check 7 --tags "hidden-link:<component id>=Resource"
az monitor action-group create -g gradbridge-rg -n gradbridge-owner --short-name gbowner --action armrole owner 8e3af657-a8ff-443c-a75c-2fe8c4bcb635 usecommonalertschema
az monitor metrics alert create -n gradbridge-availability -g gradbridge-rg --scopes <component id> --condition "avg availabilityResults/availabilityPercentage < 60 where availabilityResult/name includes *" --window-size 30m --evaluation-frequency 15m --severity 1 --action <action group id>
```

## 6a 云端验收清单（S3-07，部署后由未参与开发的成员执行）

| 检查 | 通过标准 |
|---|---|
| HTTPS 全链路 | 独立浏览器经 HTTPS 完成：学生连接 RR → 创建草稿 → 发布 → HR 搜索、下载 PDF |
| OAuth 地址 | 授权与回调都在 Azure 域名上，没有任何一步跳回 localhost；回调后 RR 账号仍是学生本人的 |
| 不意外公开 | 数据库只接受环境内访问；Storage 关闭公共访问；直接访问文件共享或猜测 URL 拿不到 PDF；`/media/` 不提供私有文件 |
| 实例替换后数据仍在 | 对四个应用各重启一次修订版、再部署一次新修订版后：关联、已发布 PDF 的 SHA-256、HR 备注与收藏、RR 草稿数不变 |
| PDF | 中文 PDF 字体正常；冷启动首次渲染时间与预热后渲染时间都记录下来 |
| 停止与切换 | 记录 RR 修订版切换的实际耗时（无 init，会等终止宽限期） |
| 邮件 | 已配置并实测，或写明使用合成账号的限制 |
| 记录 | 镜像对应的两个仓库提交、资源清单、公共地址、密钥名称（不含值）、费用上限与实际费用 |
| 备份 | 按第 10 节在云端做一次备份并恢复到隔离环境 |

## 6 部署后检查清单

- RR `/api/health` 为 healthy；API 匿名访问 `/api/v1/integrations/rr/` 返回 401。
- 学生登录 → Integrations 连接 RR → 创建草稿 → Published resume 发布。
- 招聘方登录 → Candidates 能搜到该学生、下载 PDF；学生撤回后搜索与下载立即失效。
- 重启所有服务后：学生仍为已连接，检查连接成功；HR 下载的 PDF 与重启前 SHA256 相同；RR 草稿数量不变。
- 日志中不出现 token、密码或 Fernet 密钥。

## 7 本地演练记录（2026-10-13）

在开发机上用本 compose 文件起了一套独立环境：项目名 `gradbridge-drill`，端口 18000/18173/18174/18300，四个新数据卷，与开发环境的容器和数据卷互不相干。四个镜像都从当前分支和 GradBridge RR fork 构建。数据只有合成账号：1 名学生、1 名招聘方、1 个 RR 账号。演练脚本和结果保存在仓库外的私有目录，不入库。

| 阶段 | 内容 | 结果 |
|---|---|---|
| 启动 | 首次 `up -d --build`；api 启动时迁移；RR 健康检查；api 匿名请求 | 通过（RR healthy，api 返回 401） |
| 注册客户端 | 第 4 节命令（`--allow-production`）；三个值写入私有 env 文件，删除容器内文件，重建 api | 通过，屏幕上没有输出任何密钥 |
| 业务流程 | RR 注册 → 学生连接 RR（OAuth 同意页）→ 创建草稿 → 发布 → 检查连接 → HR 搜索并下载 PDF | 通过；HR 下载的 PDF 与学生发布的 PDF SHA256 相同 |
| 重启 1 | `docker compose restart` | 关联仍为 Connected，检查连接成功；学生与 HR 的 PDF 字节不变；RR 草稿数不变 |
| 重启 2 | `down`（不带 `-v`）后 `up -d`，所有容器重建 | 同上，全部保持 |
| 重新授权 | 断开（撤销 refresh token）→ 重新连接 → 第二份草稿 → 再次发布 → HR 下载 | 通过；HR 拿到新版本，与学生的一致 |
| 升级 api | 修改设置后重建 api 镜像并只替换 api 容器 | 关联、PDF、草稿数（2）全部保持 |
| 日志检查 | 在 6 个容器的日志中查找：所有部署密钥、三个合成账号密码、当前 refresh token 的明文和密文；以及 JWT、Bearer、`refresh_token=`、`client_secret=`、URL 中的 `code=`、Fernet 密文、"password" 字样 | 全部 0 次。OAuth 回调由前端以 POST 转交 api，授权码不会出现在访问日志里 |
| 停止 | `docker compose stop` | 数据卷保留；`rr` 加 `init: true` 后正常退出 |

## 8 已知限制

- 前端公网地址在构建时固定，换域名需重建前端镜像。
- `api` 的 `/data` 为单个共享卷；多副本需要支持多写的存储（Azure Files 可以）。
- Django admin 的静态文件未由 gunicorn 提供；如需使用 admin，另行配置静态文件托管。
- 邮件默认输出到控制台；正式环境需要配置 SMTP/SES。

## 8a 地区、货币与电话格式（S3-04，2026-10-27 增加新加坡与货币）

- **首次部署后必须执行 `python manage.py load_initial_data`**（云端用 `az containerapp exec`）：它依次载入地区、技能、行业、学历、学位、院校、语言和职能领域。2026-11-08 首次云端登录测试发现，只执行地区和学历命令时，学生无法添加技能（技能表为空），也无法保存教育经历（没有学位可选）。
- `python manage.py load_gradbridge_locations`：载入澳大利亚 8 个州/领地及主要城市（数据写在该命令里，依据 ABS 的州/领地列表），以及新加坡（国家、州、城市都是 Singapore）。命令可重复执行，只新建或重新启用，不删除；修改城市列表后再执行一次即可更新。上游的 `countries/states/cities.json` 夹具是印度为主的示例数据，GradBridge 不载入。
- 备用手机号与邮编以文本保存（迁移 0086）：保留开头的 0 和 +（如 0412…、+61…、邮编 0800）。迁移前已经以数字保存的值原样转成文本，丢失的前导 0 无法也不会被猜测补回。
- 学历与语言选项：执行 `python manage.py load_gradbridge_reference_data`（澳大利亚 AQF 与新加坡的学历，两国常用语言；可重复执行）。`load_initial_data` 已改为调用这两个 GradBridge 命令，不再载入上游的印度地区、学历、语言夹具；演示数据工具 `create_test_data`、`create_test_users`（`test-users.json`）、`load_test_jobs.py` 也只生成新加坡与澳大利亚的数据。
- 学生端顶部菜单的 “Jobs by Location / Internship” 城市列表写在 `site/src/routes/(site)/+layout.svelte`，链接为 `/jobs/?location=<城市 slug>`，slug 必须与上面命令载入的城市一致。Find Jobs 页的地区筛选项来自数据库中有在招职位的城市。
- 职位薪资货币（迁移 0087 新增 `salary_currency`，取值 AUD/SGD，旧数据默认 AUD）：招聘方发布时可选；不选时，职位城市全部在新加坡则为 SGD，否则为 AUD。学生端统一显示年薪，如 `A$85k–95k a year`、`S$60k–78k a year`（按月填写的工资乘以 12）。薪资筛选参数 `min_salary`/`max_salary` 以“千/年”为单位（80 即 80,000），不做 AUD 与 SGD 之间的换算。
- 未设 `TIME_ZONE` 环境变量时，生产配置默认 `Australia/Sydney`；开发配置 `jobsp/settings.py` 仍为上游的 `Asia/Kolkata`，因为本地已有数据按该时区保存，改动会让所有已存时间偏移。
- 0086 的反向迁移会把文本转回数字：只有全部值都是纯数字时才能成功，且会再次丢掉前导 0；需要回退时先导出这两列。
- JSON Resume 导出 `city`、`region`、`postalCode`（RR 导入时忽略地址与邮编），不填写 `countryCode`（国家表没有 ISO 代码）；备用手机号不导出，招聘端也看不到电话、地址和邮编。

### 8b 演示数据（S4-03）
`python manage.py load_gradbridge_demo_data` 会生成 8 家演示公司，每家 5 个已上线职位，币种按城市分别用 AUD 或 SGD；`--remove` 会全部删除。数据都有明确标注：
- 公司名以 “(Demo)” 结尾；公司简介和职位描述开头都有 “Demo company / Demo listing” 说明；
- 职位所属的招聘方账号使用 example.test 邮箱和不可用密码，无法登录；
- 不设置网站、邮箱或电话。

再次运行会先删除上一批，再重新生成。学生对演示职位的申请会随 `--remove` 一起删除。`create_test_data` 只能在开发环境使用：它生成的账号共用仓库里写明的密码，网站和电话看起来也像真的。

## 9 已发布简历的隐私规则（S3-03B）

- 学生发布即同意招聘方下载该 PDF 的全文。主站不修改 PDF：招聘端页面隐藏电话、地址（邮箱只在学生选择公开时显示），但 PDF 里写了什么，招聘方就能看到什么。
- 发布页在发布前提供 **Preview PDF**（由 RR 按当前内容渲染，不保存），并在发布确认框中写明上述规则。
- 撤回只阻止之后的搜索、详情和下载；招聘方已经下载的 PDF 无法收回。
- 已发布文件只存在 `GRADBRIDGE_PRIVATE_MEDIA_ROOT`（不在 `MEDIA_ROOT` 下，也没有公开 URL），只能经主站鉴权下载，响应带 `Cache-Control: private, no-store`。
- 招聘方的收藏与备注按个人隔离：同公司同事和其他公司都看不到、改不了；目前没有任何导出路径包含备注。Django admin 没有注册这些模型。

## 10 备份、恢复与回退（S3-08，2026-10-26 本地实测）

脚本在 `deploy/gradbridge/ops/`，均在 PowerShell 中执行。

### 10.1 备份

```powershell
& deploy/gradbridge/ops/backup.ps1 -Project <compose 项目名> -BackupRoot <私有备份目录> -Label <日期-说明>
```

- 内容：两个数据库的 `pg_dump -Fc`（PeelJobs、RR），以及 `api` 的 `/data` 卷（已发布简历 JSON/PDF）和 `rr` 的 `/app/data` 卷；`manifest.json` 记录时间、镜像、每个文件的大小与 SHA-256。
- 顺序：先数据库、后文件卷，保证数据库引用的文件都已在归档中。可以在线备份（服务不停）。
- **不在备份里的东西**：env 文件中的密钥。其中 `RR_TOKEN_ENCRYPTION_KEY` 必须和备份一起、但分开保管（例如密码管理器或密钥库）：用别的密钥恢复后，所有学生都需要重新连接 Reactive Resume。
- 本地演练：一次备份约 3 秒（演练数据量很小，生产数据量下需要重新测量）。

### 10.2 恢复（到新的 compose 项目，绝不覆盖正在使用的环境）

```powershell
& deploy/gradbridge/ops/restore.ps1 -Project <新项目名> -BackupDir <某次备份目录> -EnvFile <该环境的 env 文件> -ImageTag <镜像标签>
```

脚本拒绝恢复到已有数据卷的项目。流程：建空卷 → 只启动两个数据库 → `pg_restore` → 解压文件卷并修正属主 → 启动应用。本地演练约 23 秒。恢复环境与原环境使用相同端口时，先停止原环境（不要删除它的卷）。

### 10.3 回退

| 方式 | 做法 | 演练结果 |
|---|---|---|
| 只回退镜像（推荐） | `IMAGE_TAG=<旧标签> docker compose ... up -d api site recruiter rr`，数据库保持新结构 | 约 8 秒；旧代码在新结构上运行正常（新迁移都是新增表或放宽列类型） |
| 镜像 + 数据一起回退 | 用升级前的备份按 10.2 恢复到新项目，并用旧镜像启动 | 结构完全回到升级前；**会丢失备份之后的全部数据** |

注意：
- 迁移 0086（电话、邮编改为文本）的反向迁移会把文本转回数字，遇到 `+` 或字母会失败，并丢失前导 0。回退时只回退镜像，不要执行 Django 的反向迁移。
- 只回退镜像期间，旧代码按数字读写备用手机号：带 `+` 的号码再次保存时会丢掉 `+`。回退窗口应尽量短。
- 只回退镜像期间，旧版 RR 创建的草稿不会写入导入记录表（S3-02）；重新升级后，这些草稿的重试仍按旧的 slug 方式匹配。
- RR 的 drizzle 迁移只会向前执行；旧镜像遇到数据库里多出的新迁移记录时不报错。


### 10.4 Azure 上的备份与恢复演练（S4-07，2026-11-08 实测）
- **PostgreSQL**：灵活服务器自带时间点恢复（PITR），保留 7 天，未开启异地冗余。演练时恢复到一台**新的**服务器，不覆盖正在使用的服务器：
  ```powershell
  az postgres flexible-server restore -g gradbridge-rg --name gradbridge-pg-drill --source-server gradbridge-pg --restore-time <UTC 时间>
  # 恢复出来的服务器不带防火墙规则，必须手动加回去：
  az postgres flexible-server firewall-rule create -g gradbridge-rg --server-name gradbridge-pg-drill --name AllowAzureServices --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0
  ```
  - 2026-11-08 实测：恢复到 14:39:05Z 的时间点，用时 9 分钟。
  - 在 api 容器中用应用账号连接正式库和恢复库，对比结果：用户 11、职位 40、公司 9、RR 关联 1、简历版本 2、迁移 150 条、最新迁移 0089，两边完全一致；`peeljobs` 和 `reactive_resume` 两个库都存在。
  - 核对完成后已删除演练服务器（`az postgres flexible-server delete ... --yes`），它按小时计费。
  - 实际切换到恢复库的步骤：把 api 的 `DB_HOST`、rr 的 `database-url`（Key Vault 机密）改为新服务器地址，然后重新部署第 6 步和第 8 步。
- **Azure Files**（`api-data` 存放已发布的 PDF，`rr-data` 存放 RR 上传的文件）：使用共享快照，不另建备份保管库。
  ```powershell
  az storage share-rm snapshot --storage-account gradbridgefiles -g gradbridge-rg --name api-data
  az storage share-rm list --storage-account gradbridgefiles -g gradbridge-rg --include-snapshot -o table
  ```
  - 2026-11-08 实测：快照与当前共享一致（api-data 4 个文件、61,983 字节；rr-data 为空）。
  - 恢复方法：用 `az storage file copy start --source-share <share> --source-snapshot <time>` 把文件复制回去，或者在门户的“快照”页面直接恢复。
  - 快照不会自动生成。如需每日自动备份，要另建 Recovery Services 保管库并启用 Azure Backup（属于付费资源，需另行批准）。
- `token-key` 必须和数据库一起保留（已放在 Key Vault 和本机文件中）；缺少它，恢复后所有学生都要重新关联 RR。

## 11 访问频率限制与 RR 客户端注册（S4-05，2026-11-08）

### 11.1 PeelJobs api 的频率限制
浏览器不直接调用登录、注册等接口，而是由学生端和招聘端的 SvelteKit 服务器调用，所以 api 看到的来源地址只有这两台服务器。按 IP 限流会把所有用户算在一起，因此改为按“请求针对的对象”计数（`backend/api/v1/throttles.py`）：

| 接口（学生端与招聘端相同） | 计数方式 | 频率（`settings_gradbridge.py`） |
|---|---|---|
| 登录 | 目标邮箱（大小写和首尾空格不区分；缓存里只存哈希） | 10 次/分钟 |
| 找回密码 | 目标邮箱 | 10 次/小时 |
| 重发验证邮件 | 目标邮箱 | 10 次/小时 |
| 注册 | 全站合计（两个注册入口共用） | 100 次/小时 |
| 联系表单 | 全站合计 | 30 次/小时 |

- 学生端与招聘端的同一邮箱共用计数；不合格的请求也计数（限流在校验之前）。
- 超过限制时返回 429，`detail` 为 “Too many attempts. Please try again in N minutes.”，各页面会直接显示这句话。
- 计数存放在数据库缓存表 `gradbridge_throttle_cache`，由迁移 0089 创建（执行 `createcachetable`）。这样 3 个 gunicorn 进程共用同一份计数。开发设置没有配置频率，所以开发环境和测试不限流。
- 代价：别人故意输错密码，可以让某个邮箱暂时无法用密码登录（Google 登录不受影响）。2026-11-09 PM 决定放宽（风险 R11）：登录改为按分钟计数，这种锁定最多持续 1 分钟，猜密码仍限制在每分钟 10 次；找回密码和重发验证邮件放宽到每小时 10 次。如需调整，只改 `settings_gradbridge.py` 中的 `DEFAULT_THROTTLE_RATES`。

### 11.2 RR 的动态客户端注册（决定：保留上游做法）
RR 上游开启了 OAuth 动态客户端注册（RFC 7591），并允许未登录时注册，用于 MCP 客户端（如 Claude）接入。具体规则见 `reactive-resume/packages/auth/src/config.ts` 和 `packages/utils/src/url-security.node.ts`：
- 回调地址只能是 RR 自己的地址、本机地址（http://localhost 或 127.0.0.1），或者公网 https 地址。内网地址和私有地址都会被拒绝。授权时回调地址必须与注册时完全一致。
- 新注册的客户端在获取简历数据之前，用户必须在 RR 的授权页亲自点 Allow。生产环境下，Better Auth 对注册和授权接口都有自带的频率限制。
- 剩余风险：任何人都能注册一个名字看起来可信的客户端，然后诱导用户在授权页点 Allow，这和普通的 OAuth 钓鱼一样。GradBridge 主站的客户端是用 `setup_rr_dev_integration` 预先注册的，不依赖动态注册。
- 如果不需要 MCP 接入，只要在 `config.ts` 中把 `allowDynamicClientRegistration` 设为 `false`，就能关闭这个风险，不影响 GradBridge 的账号关联、草稿和发布。目前保留上游行为，以减少和上游的差异。
- 生产环境不得设置 `FLAG_ALLOW_UNSAFE_OAUTH_REDIRECT_URI`（默认 false，部署脚本没有设置它）。
