# GradBridge 最终交接（S3-10，2026-10-27；S4 收尾于 2026-11-09）

本文让接手成员在不依赖旧聊天记录的情况下理解、运行、使用、验收和恢复 GradBridge。运维细节在 [部署手册](gradbridge-deployment.md)，资料转换在 [JSON Resume 导出说明](gradbridge-resume-export.md)，本文只给出总览和入口。本文不含任何密码、令牌或密钥。

## 1 最终版本

| 项目 | 值 |
|---|---|
| PeelJobs fork | `Nacrette777/opensource-job-portal`，`master` 为 `4132e37`（已合并 PR #1 的 S2–S4 全部提交，以及 PR #2 的邀请注册与 Logout 修复）|
| RR fork | `Nacrette777/reactive-resume`，`main` 为 `25aa5a586cb869d7baf6f701e653c98270ebdd3e`（已合并 PR #1，来自 `feat/s3-02-import-request` 363c45a0d）|
| Azure 镜像 | `gradbridgeacr.azurecr.io/gradbridge/{api,rr,site,recruiter}`，当前标签见第 9 节 |
| Azure 地址 | 学生端 `https://gradbridge-site.mangowater-328d9d2e.eastasia.azurecontainerapps.io`；招聘端 `https://gradbridge-recruiter…`；API `https://gradbridge-api…`；RR `https://gradbridge-rr…`（同一域名后缀）|
| PR | 已全部由用户在 GitHub 上合并：RR #1、PeelJobs #1、PeelJobs #2（第 9 节）|

PeelJobs 分支历史（每个任务一个分支，后一个基于前一个）：S2 的 `fix/student-logout-button` → … → `feat/gradbridge-deploy`；S3 的 `chore/s3-01-pin-build` → `feat/s3-02-idempotent-draft` → `fix/s3-03a-token-checks` → `feat/s3-03b-publish-privacy` → `feat/s3-04-location-phone` → `fix/s3-05-mobile-usability` → `perf/s3-06-candidate-search` → `fix/s3-08-unreadable-token` → `feat/s3-07-azure-prep` → `fix/sg-au-localisation`；S4 的 `feat/s4-01-gradbridge-brand` → `feat/s4-04-small-fixes` → `feat/s4-05-security` → `feat/s4-02-acs-email` → `feat/s4-03-demo-data` → `feat/s4-07-keyvault` → `feat/s4-08-monitoring` → `feat/s4-10-handoff`，之后是 `fix/s4-06-invitation-signup`。以上全部已合并进 `master`，接手后以 `master` 为准。

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
| 0088 `sg_au_choice_labels` | 职位类型与政府职位分类改为本地叫法（只改选项名称，不改数据库结构）|
| 0089 `throttle_cache_table` | 为频率限制创建数据库缓存表（未配置数据库缓存时不做任何操作）|

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
| 备份、恢复、回退 | 部署手册第 10 节；`deploy/gradbridge/ops/backup.ps1`、`restore.ps1`；Azure 上的演练见 10.4 节 |
| 发信（ACS）| 部署手册 5.4 节；`backend/jobsp/acs_email.py` |
| 密钥（Key Vault）| 部署手册 5.5 节；`deploy.ps1 -KeyVault` |
| 可用性监控与告警 | 部署手册 5.6 节 |
| 演示数据 | 部署手册 8b 节；`load_gradbridge_demo_data [--remove]` |
| 频率限制、RR 动态客户端注册 | 部署手册第 11 节 |

常见故障：

- **RR 冷启动后第一次生成 PDF 很慢**（开发模式实测停顿 37 秒；生产镜像首次约 7.5 秒）：每次部署或重启 RR 后先做一次预热渲染。停顿过长时学生可能需要重新连接 RR。
- **学生显示需要重新连接 RR**：refresh token 失效、被撤销，或 `RR_TOKEN_ENCRYPTION_KEY` 被更换或丢失。学生在 Integrations 页点 Reconnect 即可；不要尝试手工修数据库。
- **重试创建草稿返回“草稿已删除”**：这是有意设计（S3-02），学生需要发起新的创建请求。
- **注册收不到邮件**：Azure 上通过 ACS 发信（部署手册 5.4 节）。先检查 api 的 `EMAIL_BACKEND` 是否为 `jobsp.acs_email.EmailBackend`，再看是否进了垃圾箱。Azure 托管域名的发送配额很低。本地和演练环境中，邮件只输出到 api 日志。
- **登录或找回密码返回 “Too many attempts”**：触发了按邮箱的频率限制（部署手册 11.1 节），等提示的分钟数过后再试即可。
- **学生端第一次打开要等约 20 秒**：site 闲置时缩到 0 个副本，这是冷启动。演示前先打开一次；或者把 site 的最少副本数设为 1，费用会增加。
- **收到 “gradbridge-availability” 告警邮件**：某个可用性测试连续失败（部署手册 5.6 节）。在门户的 Application Insights → Availability 中查看是哪个应用，再看该应用的日志。
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
| 端到端验收 | — | S3-09 UAT 16/16；S3-10 最终回归；2026-11-08 Azure 登录验收 17 步 |
| 品牌与文案（S4-01）| 学生端、招聘端页面与邮件模板 | 页面检查；svelte-check 0 错误 |
| 频率限制（S4-05）| `backend/api/v1/throttles.py` | `api/v1/test_throttles.py`；云端连续 6 次请求，第 6 次返回 429 |
| 发信（S4-02）| `backend/jobsp/acs_email.py` | `peeldb/tests/test_acs_email.py`；云端 ACS 返回 202 / Succeeded |
| 演示数据与职位链接（S4-03）| `load_gradbridge_demo_data`、`JobPost.public_slug()` | `test_demo_data.py`、`jobs/test_job_links.py` |

## 8 风险登记与待决定事项（2026-11-09）

“PM 决定”一栏由 PM 填写。“建议”是开发方的意见，不代表已经决定。

**需要 PM 决定的风险**

| 编号 | 风险 | 影响 | 选项 | 建议 | PM 决定 |
|---|---|---|---|---|---|
| R2 | refresh token 有 60 秒复用窗口（为恢复丢失的续期响应而设）| 被盗的旧 token 在 60 秒内仍可用；卡顿超过“重试 + 60 秒”会要求学生重新连接 RR | 接受；缩短窗口；取消窗口（丢失响应时只能重新连接）| 演示和课程阶段接受，真实上线前复查 | 待定 |
| R6 | 没有性能目标 | 不能声称“达到性能要求” | 设定目标；声明只交付基线 | 声明只交付基线：5000 名候选人时搜索 p50 为 21–62 ms | 待定 |
| R7 | 管理员角色没有验收 | 后台功能可能有未发现的问题 | 用合成管理员在本地验收；声明不在范围内 | 声明不在本期范围内 | 待定 |
| R11 | 按邮箱限流：别人可以让某个邮箱最多 1 小时无法用密码登录 | 少量用户被骚扰 | 接受；加 CAPTCHA；放宽频率 | 接受（Google 登录不受影响）| 待定 |
| R12 | Azure for Students 的 100 美元额度用完后，订阅会被停用 | 云端停止服务，之后数据可能被删除 | 定一个停用日期并提前导出备份；继续使用直到额度用完 | 定在最终展示或评审结束之后，停用前导出数据库和文件 | 待定（日期未定）|
| R13 | RR 保留了上游的 OAuth 动态客户端注册（部署手册 11.2）| 有人可以注册一个看起来可信的客户端，诱导用户点 Allow（OAuth 钓鱼）| 保留；把 `allowDynamicClientRegistration` 设为 false | 演示阶段保留；真实上线前关闭 | 待定 |
| R14 | 没有团队成员独立复跑验收 | 验收结果只来自开发方 | 指定一名成员按第 6 节演示脚本或 S3-09 脚本复跑 | 在最终展示前完成一次 | 待定 |
| R21 | 提交作者都是维护账号 | 成员的实际贡献不能从 git 记录中看出 | 由 PM 按评审和验收记录另行填写 | 在提交材料中单独列出 | 待定 |
| R22 | 所有凭据只保存在维护人本机（`local-private`）| 维护人不在时，没人能运维 | 指定第二位保管人，通过密码管理器转交 | 指定部署负责人作为第二位保管人 | 待定 |

**已接受或已决定的风险（记录在案，PM 可以复核）**

| 编号 | 风险 | 处理 |
|---|---|---|
| R1 | RR 重启后第一次生成 PDF 较慢（生产约 7.5 秒）| 接受；每次部署后先生成一次 PDF 预热（已写入手册）|
| R4 | S3 之前、在故障窗口内改名的草稿无法追溯 | 接受，只影响学生自己的账号 |
| R5 | 上游页脚和面包屑在手机上点击区域偏小 | 接受，不改全站布局 |
| R8 | 只回退镜像时，备用电话中的 `+` 保存后可能丢失 | 接受，回退窗口尽量短 |
| R9 | 已下载的 PDF 无法收回 | 2026-10-26 已接受，发布前会提示学生 |
| R15 | 发信用的是 Azure 托管域名，配额低，发件人地址不像正式地址 | 演示阶段接受；真实使用时改用自定义域名 |
| R16 | 学生端闲置后第一次打开约 21 秒 | 2026-11-09 决定维持现状；演示前先打开一次 |
| R17 | 文件共享没有每日自动备份 | 2026-11-09 决定不开；数据库有 7 天时间点恢复，停用前手动做一次快照 |
| R19 | 云端保留了测试账号（2hr、HR2、HR3 及其公司）和 40 个标注为演示的职位 | 2026-11-09 决定保留到停用 |
| R20 | 招聘端服务器连接 api 偶尔失败（一次 PDF 下载返回 500，重试后正常）| 记录为观察项；再次出现时考虑加重试 |
| R23 | 薪资筛选不在 AUD 与 SGD 之间换算；开发配置的时区仍为 Asia/Kolkata；上游夹具的 SEO 字段写着 India | 影响小，接受 |

**已关闭**：R3（云端登录验收，2026-11-08/09 通过）、R10（发信，ACS 已送达真实收件箱）。

**已验证的内容**：2026-11-08 云端登录全链路 17 步；2026-11-09 在云端验证了同公司与不同公司 HR 的隔离、学生账号登录招聘端被拒绝、ACS 邮件约 15 秒到达收件箱、可用性告警（停服约 13 分钟后告警邮件送达）。Key Vault 切换后的登录流程，已经在上述云端验收中覆盖。

## 9 PR 建议、上游复用与贡献

**状态（2026-11-09）**：以下 PR 均已合并——RR #1 → `main` 25aa5a586；PeelJobs #1 → `master` 199c2ae；PeelJobs #2（`fix/s4-06-invitation-signup`，接受邀请时没有设置密码的步骤、Logout 没有反应、公司用户侧栏缺少 Account）→ `master` 4132e37。下面保留当时的 PR 文本作为记录。

**合并顺序**：先 RR，再 PeelJobs（部署顺序同理：RR → api 迁移 → 注册 OAuth 客户端 → 前端）。

**RR PR**：`feat/s3-02-import-request` → `main`（创建链接：https://github.com/Nacrette777/reactive-resume/compare/main...feat/s3-02-import-request）

> 标题：GradBridge: JSON Resume import with idempotent requests, OAuth refresh recovery and dev JSX fix
>
> 说明：新增 `POST /api/openapi/resumes/import/json-resume`，以独立的导入请求表实现幂等（不依赖可编辑 slug，含迁移 `20261026094545_gradbridge_import_request`）；OAuth refresh token 60 秒复用窗口，主站续期响应丢失时可以恢复；源码运行时服务端 PDF 的 JSX 编译修复。测试：packages/api 412 通过/7 跳过（上游），packages/auth 22 通过，tsgo 无错误（S3-09）。S4 没有改动 RR。

**PeelJobs PR**：`feat/s4-10-handoff` → `master`（创建链接：https://github.com/Nacrette777/opensource-job-portal/compare/master...feat/s4-10-handoff）

> 标题：GradBridge: Reactive Resume integration, published resumes, recruiter search, SG/AU localisation and Azure operations
>
> 说明：
> - 学生资料修复与 JSON Resume 导出；RR 账号 OAuth 关联；一键草稿（幂等、绑定账号）；发布快照与隐私规则；招聘方候选人搜索、个人收藏与备注。
> - 地区、电话、货币（新加坡与澳大利亚）；移动端可用性；搜索性能。
> - S4：GradBridge 品牌与如实的文案；页面内确认框；按邮箱与全站的频率限制；通过 Azure Communication Services 发信；带标注、可删除的演示数据；修复职位列表点进详情页 404。
> - 容器镜像、Azure 部署脚本（含 Key Vault 引用）、备份恢复脚本与手册（含监控和云端恢复演练）。
> - 迁移 0081–0089。
> - 测试：后端完整套件 331 项通过（跳过 1 项）；学生端、招聘端 svelte-check 0 错误。依赖 RR PR 先合并。
>
> 合并后：用合并后的 master 重新构建镜像并部署（部署手册 5.5 节，带 `-KeyVault`），然后按 6a 节检查。

**上游复用与团队新增**（相对两个 fork 的默认分支）：
- PeelJobs（截至 `35e38a5`，即本交接提交之前）：45 个提交，224 个文件，+11256/−1412 行（不含 `site/package-lock.json`）。复用上游的 Django/DRF 后端、两个 SvelteKit 前端、账号与职位功能；新增 RR 集成、发布、候选人搜索、本地化、部署与运维。
- RR：4 个提交，15 个文件，+7181/−2 行（大部分是 drizzle 迁移快照；其余为 API、认证与数据库模式）。复用上游的编辑器、导入器、PDF 渲染与 OAuth 提供方。
- 提交记录中的作者为本仓库维护账号；实际成员贡献应按评审与验收记录另行填写，不按计划分工推定。

**镜像与云端版本（2026-11-09，与 master 一致）**：
- api、rr 为标签 `11`（PeelJobs `199c2ae`，RR `25aa5a586`；`199c2ae` 到 `4132e37` 之间后端没有改动）；site、recruiter 为标签 `13`（`43f2e72`，与 `4132e37` 的内容完全相同）。
- rr 和 api 的密钥通过 Key Vault `gradbridge-kv-53888c` 引用；发信使用 ACS；Application Insights 有 3 个可用性测试，告警 `gradbridge-availability` 发给 Owner。
- 云端有 8 家演示公司、40 个演示职位，可用 `load_gradbridge_demo_data --remove` 删除；测试账号保留到停用。
- 下次部署：`deploy.ps1 -SubscriptionId <id> -ImageTag <新标签> -KeyVault gradbridge-kv-53888c`，先运行第 5 步构建镜像，然后运行第 6–9 步（第 7 步在 `rr-oauth.json` 已存在时会自动跳过）。

## 10 凭据、联系人与待办

- **凭据位置（只列名称）**：合成账号凭据 `local-private\*.credentials.json`；本地 RR 集成配置 `local-private\s2-04-20261012\peeljobs-rr-dev.env.json`；演练环境 `local-private\s2-08-drill\drill.env`；Azure 密钥 `local-private\s3-07-azure\azure.env`、`rr-oauth.json`、`acs-email.json`（云端存放在 Key Vault `gradbridge-kv-53888c`，应用只保存引用）。这些文件只在维护人本机，交接时通过密码管理器或加密渠道转交，不放入仓库或聊天。
- **维护联系人**：PM 为本项目用户；部署负责人和认证负责人待 PM 指定（见 R22）。
- **待办**（开发方的工作已全部完成，以下由团队负责）：
  - PM 对第 8 节中“待定”的风险作出决定；
  - 团队成员独立复跑验收（R14）；
  - 确定 Azure 停用日期（R12）。停用前先按部署手册第 10 节导出数据库和文件，然后删除资源组 `gradbridge-rg`，会一并删除数据库、文件、Key Vault（软删除保留 7 天）、ACS 和监控资源；
  - 合并后的功能分支可以在 GitHub 上删除（`master`/`main` 已包含全部提交）。
