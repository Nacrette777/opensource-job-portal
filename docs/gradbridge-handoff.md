# GradBridge 最终交接（S3-10，2026-10-27）

本文让接手成员在不依赖旧聊天记录的情况下理解、运行、使用、验收和恢复 GradBridge。运维细节在 [部署手册](gradbridge-deployment.md)，资料转换在 [JSON Resume 导出说明](gradbridge-resume-export.md)，本文只给出总览和入口。本文不含任何密码、令牌或密钥。

## 1 最终版本

| 项目 | 值 |
|---|---|
| PeelJobs fork | `Nacrette777/opensource-job-portal`，分支 `fix/sg-au-localisation`（线性包含 S2 与全部 S3 分支）|
| RR fork | `Nacrette777/reactive-resume`，分支 `feat/s3-02-import-request`，`363c45a0d9107a04e62a3e27e0b6dd77886f0992` |
| Azure 镜像 | `gradbridgeacr.azurecr.io/gradbridge/{api,rr,site,recruiter}`，最新标签见第 9 节 |
| Azure 地址 | 学生端 `https://gradbridge-site.mangowater-328d9d2e.eastasia.azurecontainerapps.io`；招聘端 `https://gradbridge-recruiter…`；API `https://gradbridge-api…`；RR `https://gradbridge-rr…`（同一域名后缀）|
| PR | 尚未创建，也未合并；建议的标题、说明与合并顺序见第 9 节 |

PeelJobs 分支历史（每个任务一个分支，后一个基于前一个）：S2 的 `fix/student-logout-button` → … → `feat/gradbridge-deploy`；S3 的 `chore/s3-01-pin-build` → `feat/s3-02-idempotent-draft` → `fix/s3-03a-token-checks` → `feat/s3-03b-publish-privacy` → `feat/s3-04-location-phone` → `fix/s3-05-mobile-usability` → `perf/s3-06-candidate-search` → `fix/s3-08-unreadable-token` → `feat/s3-07-azure-prep` → `fix/sg-au-localisation`。最终分支包含以上全部提交，评审时只需看最终分支。

## 2 架构与数据所有权

```
学生端 site (SvelteKit) ─┐                       ┌─ RR web/server (Reactive Resume fork)
招聘端 recruiter        ─┼─ HTTPS ─ api (Django) ─┤   OAuth 2.1 + PKCE、OpenAPI 导入、PDF 渲染
                         │          │             └─ rr 数据库（PostgreSQL）+ RR 文件存储
                         │          └─ peeljobs 数据库（PostgreSQL）+ 私有文件 /data/private_media
```

- **PeelJobs 拥有**：账号、学生资料、RR 账号关联（加密的 refresh token）、草稿请求记录、发布快照（JSON 与 PDF 文件）、招聘方收藏与私有备注。
- **RR 拥有**：学生的 RR 账号、简历草稿及编辑内容、导入请求记录（S3-02）。
- 两个应用各自管理数据库和迁移。主站只通过 RR 的 OAuth 与 OpenAPI 操作 RR，从不直接写 RR 的表。RR 中的编辑不会回写学生资料。
- 业务流程：学生已保存的资料 → 服务端转换为标准 JSON Resume → RR 导入（校验所有权，按请求号幂等）→ RR 私有草稿 → 学生编辑 → 学生明确发布（同时固定 JSON 与 PDF）→ 招聘方受控访问。
- 发布固定一个版本；之后在 RR 里的编辑不影响招聘方，重新发布才更新。撤回会阻止之后的搜索、详情和下载，但已下载的 PDF 无法收回。
- 招聘方搜索：多个技能必须全部满足；学历、学位与毕业年份必须在同一条教育记录中匹配；收藏与备注属于具体的招聘方个人，不在公司内共享；候选人池只包含已发布简历的学生。

## 3 数据库变更与转换约定

| PeelJobs 迁移 | 内容 |
|---|---|
| 0081 `resumeaccountlink` | 学生与 RR 账号的关联（加密 refresh token、RR 用户 ID）|
| 0082 `resumeintegrationrequest` | “一键创建草稿”请求，与发起时的 RR 账号绑定 |
| 0083 `…_source_payload` | 请求首次提交的内容快照（重试不会覆盖学生在 RR 的编辑）|
| 0084 `resume_publication` | 发布版本（JSON、PDF、SHA-256、撤回状态）|
| 0085 `candidate_shortlist_notes` | 招聘方个人收藏与备注 |
| 0086 `user_phone_and_postcode_as_text` | 备用手机号、邮编改为文本（保留前导 0 与 +）|
| 0087 `jobpost_salary_currency` | 职位薪资货币 AUD/SGD |

RR 迁移：`20261026094545_gradbridge_import_request`（导入请求表，不依赖可编辑的 slug 实现幂等）。

转换约定见 [gradbridge-resume-export.md](gradbridge-resume-export.md)：导出标准 JSON Resume，RR 原生格式由 RR 自己的导入器生成；不编造国家代码；备用手机号不导出。

参考数据：`load_initial_data` 会调用 `load_gradbridge_locations`（澳大利亚 8 个州/领地与主要城市、新加坡）和 `load_gradbridge_reference_data`（两国学历、常用语言），不再载入上游以印度为主的夹具（部署手册 8a 节）。

## 4 运行、部署、备份与故障处理

| 主题 | 位置 |
|---|---|
| 本地开发启动与端口 | [getting-started](getting-started/index.md)；部署手册 3.1 节（从干净检出复现）|
| 本地生产式演练（Docker Compose）| 部署手册第 3 节；`deploy/gradbridge/compose.yml` |
| 注册 OAuth 客户端 | 部署手册第 4 节（`setup_rr_dev_integration --allow-production`）|
| 部署到 Azure | 部署手册第 5 节与 5.3 节实际记录；`deploy/gradbridge/azure/deploy.ps1`（默认只打印，`-Execute` 才创建资源，`-From/-To` 断点续做）|
| 云端验收清单 | 部署手册 6a 节 |
| 备份、恢复、回退 | 部署手册第 10 节；`deploy/gradbridge/ops/backup.ps1`、`restore.ps1` |

常见故障：

- **RR 冷启动后第一次生成 PDF 很慢**（开发模式实测停顿 37 秒；生产镜像首次约 7.5 秒）：每次部署或重启 RR 后先做一次预热渲染。停顿过长时学生可能需要重新连接 RR。
- **学生显示需要重新连接 RR**：refresh token 失效、被撤销，或 `RR_TOKEN_ENCRYPTION_KEY` 被更换或丢失。学生在 Integrations 页点 Reconnect 即可；不要尝试手工修数据库。
- **重试创建草稿返回“草稿已删除”**：这是有意设计（S3-02），学生需要发起新的创建请求。
- **注册收不到邮件**：邮件默认只输出到 api 日志，正式使用前需配置 SMTP（部署手册第 2、8 节）。
- **云端暂停省钱**：`az postgres flexible-server stop`（7 天后 Azure 会自动启动），见部署手册 5.3 节。

## 5 用户指南

**学生**
1. 注册并验证邮箱，登录学生端，在 Profile 填写个人信息、教育、工作经历、技能和项目，每个弹窗保存后刷新确认。
2. 进入 Profile → Integrations，点 Connect Reactive Resume，在 RR 登录或注册自己的账号并点 Allow。
3. 点 Create draft，在 RR 编辑器中修改简历（自动保存）。
4. 进入 Published resume，先点 Preview PDF 检查内容，再发布。发布即同意招聘方阅读并下载 PDF 全文。
5. 需要更新时在 RR 修改后重新发布；需要隐藏时点 Withdraw。已被下载的 PDF 无法收回。

**招聘方（HR）**
1. 在招聘端注册并验证邮箱、登录，进入 Candidates。
2. 用关键词、技能（全部满足）、学历与毕业年份筛选，打开候选人详情，下载 PDF。
3. 收藏候选人、写备注；收藏和备注只有自己能看到。学生撤回后，收藏中显示 “Candidate no longer available”。
4. 发布职位时选择城市；薪资货币可选 AUD/SGD，不选时按城市自动判断（新加坡为 SGD）。

**管理员**
- Django admin（`/admin/`）没有注册发布、版本、收藏、备注模型，管理员不能在后台查看学生的私有草稿或招聘方备注。管理员角色没有专门验收（S3-09 风险 R7）。
- 参考数据维护：修改城市、学历、语言列表后重新执行 `load_gradbridge_locations` / `load_gradbridge_reference_data`（只新增或重新启用，不删除）。

## 6 演示脚本（约 12 分钟）

准备：开发服务已运行，或使用 Azure 环境；普通窗口登录学生 A，InPrivate 窗口登录 HR A1（合成账号，凭据在交接包的私有目录）。

| 时间 | 内容 | 要点 |
|---|---|---|
| 0:00–1:00 | 开场 | 问题：毕业生资料与简历分离，HR 难以找到可信版本；GradBridge 把两者用授权连接起来 |
| 1:00–3:00 | 学生资料 | Find Jobs 菜单与地区为新加坡/澳大利亚；资料弹窗保存后刷新仍在 |
| 3:00–5:00 | 连接 RR | Integrations → Connect → RR 登录/同意页 → 回到主站显示 Connected |
| 5:00–7:00 | 一键草稿 | Create draft → 在 RR 中改 Headline；说明重试不会重复创建、不会覆盖编辑 |
| 7:00–8:30 | 发布 | Preview PDF → 确认框中的隐私提醒 → 发布成功、版本历史 |
| 8:30–11:00 | HR 端 | 多技能筛选 → 详情（不显示电话）→ 下载 PDF → 收藏与私有备注；说明同公司同事也看不到 |
| 11:00–12:00 | 撤回 | 学生撤回 → HR 刷新后搜索不到、下载 404；重新发布恢复；收尾说明部署与备份 |

备用录屏：交接包私有目录中的 `s3-10-20261027\demo-recording\`（本地合成账号录制，见 S3-10 报告）。

## 7 需求、实现与测试对应

| 需求 | 实现位置 | 测试与证据 |
|---|---|---|
| 学生资料增删改与隔离 | `backend/api/v1/profile/`、`site/src/routes/(site)/profile/` | `api/v1/profile/tests.py`；S2-02 跨学生 404 |
| 资料转 JSON Resume | `backend/peeldb/resume_export.py` | `peeldb/tests/test_resume_export.py` |
| RR 账号 OAuth 关联 | `backend/api/v1/integrations/`；RR `packages/auth` | `api/v1/integrations/tests.py`；RR `config.test.ts`；S3-03A 真实故障注入 |
| 一键草稿与幂等重试 | PeelJobs integrations；RR `packages/api/src/features/resume/` | `integrations/tests.py`；RR `crud.test.ts`、`import-request.integration.test.ts`；S3-02 故障注入 |
| 发布快照、撤回、隐私 | `api/v1/integrations/`（publication）、发布页 | `integrations/test_publication.py`；S3-03B 权限矩阵 |
| HR 搜索、收藏、备注 | `api/v1/recruiter/`、`recruiter/src/routes/(dashboard)/dashboard/candidates/` | `recruiter/test_candidates.py`；S3-06 性能基线 |
| 地区、电话、货币（新加坡/澳大利亚）| `load_gradbridge_locations`、迁移 0086/0087、前端菜单与薪资显示 | `test_gradbridge_locations.py`、`jobs/test_salary_currency.py`、`test_demo_data.py` |
| 移动端可用性 | 学生端、招聘端组件 | S3-05 视口审计 |
| 部署、备份、回退 | `deploy/gradbridge/` | S2-08/S3-08 本地演练；S3-07 Azure 部署 |
| 端到端验收 | — | S3-09 UAT 16/16；S3-10 最终回归 |

## 8 已知限制与待决定事项

- 需要登录的云端全链路验收尚未执行（云端是新库、无账号；邮件只输出到日志）。
- 尚无团队成员独立复跑 S3-09 的验收（脚本可复用）。
- refresh token 60 秒复用窗口的安全取舍需要认证负责人决定（S3-09 R2）。
- 没有性能目标，S3-06 只交付基线。
- 管理员角色未验收；邮件未配置；Azure 学生订阅总额度 100 美元，月预算 65 美元。
- 薪资筛选不在 AUD 与 SGD 之间换算；开发配置时区仍为 Asia/Kolkata（本地已有数据按该时区保存）。
- 上游技能、行业夹具的 SEO 字段仍写着 “India”（新前端不显示）。

## 9 PR 建议、上游复用与贡献

**建议合并顺序**：先 RR，再 PeelJobs（部署顺序同理：RR → api 迁移 → 注册 OAuth 客户端 → 前端）。

**RR PR**：`feat/s3-02-import-request` → `main`

> 标题：GradBridge: JSON Resume import with idempotent requests, OAuth refresh recovery and dev JSX fix
>
> 说明：新增 `POST /api/openapi/resumes/import/json-resume`，以独立的导入请求表实现幂等（不依赖可编辑 slug，含迁移 `20261026094545_gradbridge_import_request`）；OAuth refresh token 60 秒复用窗口，主站续期响应丢失时可以恢复；源码运行时服务端 PDF 的 JSX 编译修复。测试：packages/api 412 通过/7 跳过（上游），packages/auth 22 通过，tsgo 无错误（S3-09）。

**PeelJobs PR**：`fix/sg-au-localisation` → `master`

> 标题：GradBridge: Reactive Resume integration, published resumes, recruiter candidate search, deployment and SG/AU localisation
>
> 说明：学生资料修复与 JSON Resume 导出；RR 账号 OAuth 关联；一键草稿（幂等、绑定账号）；发布快照与隐私规则；招聘方候选人搜索、个人收藏与备注；地区/电话/货币（新加坡与澳大利亚）；移动端可用性；搜索性能；容器镜像、Azure 部署脚本、备份恢复脚本与手册。迁移 0081–0087。测试：后端完整套件 306 项通过；学生端、招聘端 svelte-check 0 错误。依赖 RR PR 先合并。

**上游复用与团队新增**（相对两个 fork 的默认分支）：
- PeelJobs（截至 `ed18016`）：32 个提交，144 个文件，+9256/−773 行（不含 `site/package-lock.json`）。复用上游的 Django/DRF 后端、两个 SvelteKit 前端、账号与职位功能；新增 RR 集成、发布、候选人搜索、本地化、部署与运维。
- RR：4 个提交，15 个文件（主要为 API、认证、数据库模式与迁移快照）。复用上游的编辑器、导入器、PDF 渲染与 OAuth 提供方。
- 提交记录中的作者为本仓库维护账号；实际成员贡献应按评审与验收记录另行填写，不按计划分工推定。

**镜像与云端版本**：Azure 四个应用当前为镜像标签 `4`，构建自 PeelJobs `ed18016`（2026-10-27 补修福利选项等最后几处印度内容）与 RR `363c45a0d`。

## 10 凭据、联系人与待办

- **凭据位置（只列名称）**：合成账号凭据 `local-private\*.credentials.json`；本地 RR 集成配置 `local-private\s2-04-20261012\peeljobs-rr-dev.env.json`；演练环境 `local-private\s2-08-drill\drill.env`；Azure 密钥 `local-private\s3-07-azure\azure.env` 与 `rr-oauth.json`（云端另存为 Container Apps secrets）。这些文件只在维护人本机，交接时通过密码管理器或加密渠道转交，不放入仓库或聊天。
- **维护联系人**：待团队填写（PM、部署负责人、认证负责人）。
- **待办**：云端全链路验收与云端备份恢复（部署手册 6a、第 10 节）；团队成员独立复跑 UAT；对 refresh token 窗口、性能目标、管理员验收作出决定；配置 SMTP；评审并提交上面的两个 PR。
