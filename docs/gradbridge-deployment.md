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
| `TIME_ZONE` | 否 | 默认 `Asia/Kolkata`（PeelJobs 原值）。项目关闭了 `USE_TZ`，数据库存的是该时区的本地时间，**必须在首次部署前确定，之后不要修改**，否则所有已存时间都会整体偏移 |
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

- 首次部署后执行 `python manage.py load_gradbridge_locations`：载入澳大利亚 8 个州/领地及主要城市（数据写在该命令里，依据 ABS 的州/领地列表），以及新加坡（国家、州、城市都是 Singapore）。命令可重复执行，只新建或重新启用，不删除；修改城市列表后再执行一次即可更新。上游的 `countries/states/cities.json` 夹具是印度为主的示例数据，GradBridge 不载入。
- 备用手机号与邮编以文本保存（迁移 0086）：保留开头的 0 和 +（如 0412…、+61…、邮编 0800）。迁移前已经以数字保存的值原样转成文本，丢失的前导 0 无法也不会被猜测补回。
- 学生端顶部菜单的 “Jobs by Location / Internship” 城市列表写在 `site/src/routes/(site)/+layout.svelte`，链接为 `/jobs/?location=<城市 slug>`，slug 必须与上面命令载入的城市一致。Find Jobs 页的地区筛选项来自数据库中有在招职位的城市。
- 职位薪资货币（迁移 0087 新增 `salary_currency`，取值 AUD/SGD，旧数据默认 AUD）：招聘方发布时可选；不选时，职位城市全部在新加坡则为 SGD，否则为 AUD。学生端统一显示年薪，如 `A$85k–95k a year`、`S$60k–78k a year`（按月填写的工资乘以 12）。薪资筛选参数 `min_salary`/`max_salary` 以“千/年”为单位（80 即 80,000），不做 AUD 与 SGD 之间的换算。
- 未设 `TIME_ZONE` 环境变量时，生产配置默认 `Australia/Sydney`；开发配置 `jobsp/settings.py` 仍为上游的 `Asia/Kolkata`，因为本地已有数据按该时区保存，改动会让所有已存时间偏移。
- 0086 的反向迁移会把文本转回数字：只有全部值都是纯数字时才能成功，且会再次丢掉前导 0；需要回退时先导出这两列。
- JSON Resume 导出 `city`、`region`、`postalCode`（RR 导入时忽略地址与邮编），不填写 `countryCode`（国家表没有 ISO 代码）；备用手机号不导出，招聘端也看不到电话、地址和邮编。

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
