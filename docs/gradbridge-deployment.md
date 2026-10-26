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

```bash
RG=gradbridge-rg; LOC=australiaeast; ACR=gradbridgeacr$RANDOM; ENV=gradbridge-env
az group create -n $RG -l $LOC
az acr create -g $RG -n $ACR --sku Basic
az containerapp env create -g $RG -n $ENV -l $LOC
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

## 8a 地区选项与电话格式（S3-04）

- 首次部署后执行 `python manage.py load_gradbridge_locations`：载入澳大利亚 8 个州/领地及主要城市（数据写在该命令里，依据 ABS 的州/领地列表）。命令可重复执行，只新建或重新启用，不删除；修改城市列表后再执行一次即可更新。上游的 `countries/states/cities.json` 夹具是印度为主的示例数据，GradBridge 不载入。
- 备用手机号与邮编以文本保存（迁移 0086）：保留开头的 0 和 +（如 0412…、+61…、邮编 0800）。迁移前已经以数字保存的值原样转成文本，丢失的前导 0 无法也不会被猜测补回。
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
