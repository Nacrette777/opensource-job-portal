# GradBridge：PeelJobs 学生资料 → JSON Resume → Reactive Resume

本轮只做单向文件导出，用户在 RR 手动导入。没有跨库写入、自动绑定账号、管理员 API key 或回写逻辑。

## 源码核对

- 学生/求职者是 `backend/peeldb/models.py` 的 `User(user_type="JS")`；`EM` 是招聘方，不能作为学生导出。没有新建资料表。
- `User.education` → `EducationDetails` → `EducationInstitue`、`Degree` → `Qualification`。
- `User.employment_history` → `EmploymentHistory`；`User.skills` → `TechnicalSkill` → `Skill`；`User.project` → `Project`。
- 不使用招聘方的 `User.technical_skills`，也不解析已有简历附件或 `resume_text`。
- RR 5.3.1：`packages/import/src/json-resume.tsx` 的 `parseJSONResume` 接受标准格式，调用现有转换器、`defaultResumeData` 和 `resumeDataSchema.parse`。
- RR 界面：`apps/web/src/dialogs/resume/import.utils.ts` 将有 `basics`、无 `sections/metadata` 的文件识别为 `json-resume-json`；`parse-json.ts` 调用上述转换器；`import.tsx` 提供 **JSON Resume** 选项。

**标准 JSON Resume** 的顶层是 `basics/work/education/skills/projects`。**RR 原生 JSON** 包含 `sections/metadata` 及布局、样式、项目 ID。本命令只输出前者，不拼装 RR 原生结构。

## 实际字段映射

| PeelJobs 来源 | JSON Resume 字段 | RR 导入结果 |
| --- | --- | --- |
| `User.first_name + last_name` | `basics.name` | 姓名；不以账号用户名代替缺失姓名 |
| `email / mobile` | `basics.email / phone` | 联系方式；不使用备用电话冒充主号码 |
| `job_role` | `basics.label` | headline；不使用招聘方专用 `job_title` |
| `profile_description` | `basics.summary` | 简介 |
| `current_city`，无则 `city`；其 `state`，无则 `User.state` | `basics.location.city / region` | 位置 |
| `address / pincode` | `basics.location.address / postalCode` | 文件保留；当前 RR 转换器不显示这两项 |
| `education.institute.name` | `education[].institution` | 学校 |
| `education.degree.degree_name.name` | `education[].studyType` | 学位/学历名称 |
| `education.degree.specialization` | `education[].area` | 专业；RR 同时组合到 degree 文本 |
| `education.score` | `education[].score` | grade |
| `employment_history.company / designation / job_profile` | `work[].name / position / summary` | 公司、职位、经历描述 |
| 教育/经历的 `from_date / to_date` | `startDate / endDate` | ISO 日期，RR 格式化为时间段 |
| `skills.skill.name` | `skills[].name` | 技能名称 |
| `skills.proficiency` | `skills[].level` | 使用学生 UI 标签：Poor→Beginner、Average→Intermediate、Good→Advanced、Expert→Expert |
| `project.name / description` | `projects[].name / description` | 项目名称与描述 |
| `project.from_date / to_date` | `projects[].startDate / endDate` | 项目时间段 |
| `project.role / skills[].name` | `projects[].roles / keywords` | RR 当前忽略这两个结构字段；同时放进 highlights，保证可见 |
| `project.location.name / size` | `projects[].highlights` | 项目地点、团队人数，仅有值时输出 |

关系记录按主键排列以保证导出顺序稳定，不自动筛选“最近一条”。

## 缺口和限制

- 空值、省略字段和没有记录的模块不会生成虚构内容。命令输出缺口路径与数量，不打印个人资料正文。
- `current_job/current_education=True` 时省略结束日期。若非当前记录缺少结束日期，仍保留真实开始日期，并警告：RR 会显示 `Present`，需要核对。项目没有“仍在进行”布尔字段，同样提示。
- 国家模型只有名称，没有 ISO 国家代码；不猜测 `countryCode`。
- 现有学生模型没有本轮可用的个人网站、学校/公司/项目 URL、课程列表，故省略。
- 学习形式 `degree_type` 不等于学位，不冒充 `studyType`。技能年限、版本、最后使用日期没有本轮标准字段映射；证书、语言不在本轮七类映射范围。
- RR 会丢弃没有学校名的教育、没有公司和职位的经历、没有名称的技能或项目。命令会警告；校验工具还会检查导入前后记录数量，避免默默丢失。
- 邮箱为空则省略；明显无效邮箱省略并警告。当前 RR 对邮箱、URL、日期有自己的严格校验，导出后应运行下面的兼容检查。
- 资料页对部分可选字段使用“非空才提交”；清空页面文本不一定清除数据库旧值。本流程以保存后重新加载的数据为准。

## 在学生端填写资料

1. 使用学生端 `http://localhost:5173/register/` 注册独立测试账号，再登录。不要使用招聘端 5174 的账号；邮箱唯一，同一招聘账号不能直接当作学生账号。
2. `http://localhost:5173/profile/`：姓名、手机号、Job Role、Profile Description、所在城市，点击 **Save Profile**。
3. `/profile/education/`：**Add Education**，填写学校、学位/专业、日期、成绩。学校可选已有项或 Other 自填；学历/专业依赖现有 lookup 选项，不由导出命令创建。
4. `/profile/employment/`：**Add Experience**，填写公司、职位、日期、描述。没有经历可以留空。
5. `/profile/skills/`：搜索并选定技能，填写熟练程度，保存。只输入搜索词而未选中技能不算已保存。
6. `/profile/projects/`：**Add Project**，填写项目名、描述、日期、角色、技能等已有内容。
7. 每次保存后刷新对应页面，确认字段和记录仍在；这一步验收实际持久化，而不只看成功提示。

前端同源 `/api/...` 路由通过已有 HttpOnly 会话转发到 Django：

| 数据 | Django API |
| --- | --- |
| 基本资料 | GET/PATCH `/api/v1/profile/` |
| 教育 | `/api/v1/profile/education/` 及记录详情 |
| 经历 | GET `/api/v1/employment/my-history/`，POST `.../add/`，PATCH `.../<id>/` |
| 技能 | GET `/api/v1/skills/my-skills/`，POST `.../add/`，PATCH `.../<id>/` |
| 项目 | `/api/v1/profile/projects/` 及记录详情 |

导出直接读取这些 API 保存的模型关系，不另外调用 API 获取令牌。

## 导出指定测试学生（Windows PowerShell）

先确认学生资料已保存。此命令要求显式邮箱或 ID；不会选择第一个用户或批量导出。招聘方、未知账号和邮箱匹配不唯一时失败。

```powershell
cd D:\GradBridge\opensource-job-portal\backend
$env:PYTHONUTF8 = "1"
$testStudentEmail = Read-Host "输入已确认的测试学生邮箱"
New-Item -ItemType Directory -Force D:\GradBridge\exports | Out-Null
$resumeOutput = "D:\GradBridge\exports\student-$(Get-Date -Format 'yyyyMMdd-HHmmss').json"
.\.venv\Scripts\python.exe manage.py export_json_resume --email $testStudentEmail --output $resumeOutput
```

也可把 `--email $testStudentEmail` 替换为 `--user-id <确切ID>`，不能同时传两者。输出文件使用 UTF-8、无 BOM；已有文件不覆盖。**不要用 PowerShell `>` 重定向**：Django 启动日志会污染 JSON。真实导出放在两个 Git 仓库之外，不要提交。

## 使用当前 RR 实际导入器验证

该检查不连接 RR 数据库、不创建简历、不打印资料正文；会调用当前 RR checkout 的 UI 格式识别与转换入口，并校验原生 schema、关键字段及记录数量。

```powershell
cd D:\GradBridge\opensource-job-portal
node --import file:///D:/GradBridge/reactive-resume/apps/server/node_modules/tsx/dist/loader.mjs `
  ./tools/validate_resume_import.mjs `
  --rr-root D:\GradBridge\reactive-resume `
  --input $resumeOutput
```

成功输出 `accepted: true` 和各模块数量。输出文件仍是标准 JSON Resume，不被改写成 RR 原生 JSON。

## 手动导入 RR 与验收

1. 在 `http://localhost:3000/dashboard/resumes` 登录 RR，点击 **Import** / 导入卡片。
2. 选择导出的 `.json` 文件；格式应自动识别为 **JSON Resume**。不要选 Reactive Resume JSON 或 v4。
3. 点击导入，进入新简历。逐项对照姓名、联系方式、简介、教育、经历、技能、项目与记录数量；核对项目角色/技能要点和所有日期。
4. 刷新确认简历保存，再生成 PDF 检查展示。无结束日期但不是当前记录时，修正源资料重新导出，或手动调整 RR 时间段。
5. 在 RR 修改一个字段后，刷新 PeelJobs 资料页，原资料应保持不变。每次重新导入会创建另一份简历，不更新或覆盖旧简历。

## 自动测试

```powershell
cd D:\GradBridge\opensource-job-portal\backend
$env:PYTHONUTF8 = "1"
$env:REACTIVE_RESUME_DIR = "D:\GradBridge\reactive-resume"
.\.venv\Scripts\python.exe manage.py test peeldb.tests.test_resume_export
```

Django 使用独立测试数据库和合成 ORM 数据，不修改开发库。设置 `REACTIVE_RESUME_DIR` 后还会调用 Node 校验两份实际命令输出（多条记录、空关系/可选空值）；未设置时该兼容测试明确跳过。测试不导出任何真实用户资料。

## 单独记录：学生端退出登录

用户报告当前学生端无法退出登录，待另行复现、定位和修复。本轮不修改退出登录流程；可使用无痕窗口或独立浏览器会话登录测试学生，避免替换现有招聘方会话。
