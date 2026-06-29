# 项目进度记录

本文档记录当前活动执行进度。2026-04-20 之前的旧分钟级记录已归档到 [docs/archive/PROJECT_RECORD.md](docs/archive/PROJECT_RECORD.md)。

## 进度记录 2026-06-29 20:20

### 本次目标

根据已收敛的需求文档和对话，为用例生成 V1 完成后的飞书文档读取能力移植，拆分可直接交给 Codex 执行的分步骤开发提示词。

### 本次完成

- 阅读 `docs/specs/test-case-generation-feishu-doc-migration.md`、`docs/specs/test-case-generation.md`、飞书集成 Spec、项目级 AI Spec、当前用例生成后端/前端实现和 QA Workspace 飞书富读取参考实现。
- 确认当前 V1 以 `PlanningSnapshotResponse` 为生成中心，适合先把 `Source Evidence Run` 转成兼容快照，再接入生成。
- 确认当前 `feishu_reader.py` 只支持飞书电子表格，且会拒绝 docx/docs/base，因此移植不能直接改旧快照入口硬接文档 URL。
- 新增 `docs/superpowers/plans/2026-06-29-test-case-generation-feishu-doc-migration-codex-prompts.md`，按“Source Evidence 数据模型 -> 飞书富读取 -> Source Evidence API -> 生成/导出接入 -> 前端闭环 -> Vision 凭据 -> 视觉选择 -> observation 采纳 -> TTL 清理 -> 验收”拆分提示词。

### 当前项目进度

- 用例生成 V1 主链路已完成后的飞书文档读取移植已有可执行切片计划。
- 推荐先完成不依赖 Vision 的文本/表格闭环，再实现视觉凭据、观察、采纳和 TTL 审计。

### 文档同步

- `docs/superpowers/plans/2026-06-29-test-case-generation-feishu-doc-migration-codex-prompts.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只新增开发提示词文档，没有修改业务代码。
- 未运行后端/前端业务测试；本次验证范围为文档结构和空白检查。

## 进度记录 2026-06-12 17:50

### 本次目标

按业务能力切片重建项目 Spec 文档体系，让 Codex 在开发新功能前能快速定位模块边界、稳定契约、代码入口和必跑测试，并清理已被新 Spec 覆盖的旧散落文档。

### 本次完成

- 新增 `docs/specs/README.md` 作为业务能力 Spec 索引和模板说明。
- 新增 10 份业务能力 Spec：身份与后台管理、个人校验、项目校验、规则引擎、数据源、飞书集成、规则配置与配置表查询、项目级 AI、执行任务与结果、交付部署与工程治理。
- 更新 `README.md` 的文档入口，新增 `docs/specs/` 链接并更新文档时间。
- 更新 `docs/MODULES.md`，将业务切片表改为 Spec、前端入口和后端入口的三向定位。
- 更新 `docs/STANDARDS.md`，明确开发业务能力前必须先读对应 Spec。
- 更新 `CHANGELOG.md`，记录本次文档治理的阶段性变化。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 11 类规则执行能力和 IAP 礼包校验主流程已接入。
- 项目级飞书机器人、规则配置工作区、配置表查询规则和项目级 AI 凭据配置能力已接入。
- Alembic 迁移、一键检查、基础 CI、源码交付包和生产安全配置检查已接入。
- 业务能力 Spec 体系已按粗模块建立，后续 Codex 开发前有稳定阅读入口。

#### 已实现但未打通/占位功能

- 本地文件选择器默认关闭，开发或单机使用时需显式设置 `ENABLE_LOCAL_PICKER=true`，且所选路径仍必须位于 allowlist 内。
- 飞书电子表格主链路依赖项目飞书机器人配置、`FEISHU_OAUTH_CALLBACK_URL` 和飞书应用权限；多维表格、文档表格不在当前支持范围。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。
- 任务执行第一阶段为单进程后台任务，不支持跨进程队列、任务重试、进度百分比或取消 API。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 聚合、公式、平均值等复杂规则未纳入当前规则库。

### 规范化调整

- 将“模块速查”和“业务能力维护说明”分离：`docs/MODULES.md` 负责定位，`docs/specs/` 负责完整链路说明。
- 明确 `CONTEXT.md` 继续只作为术语表，不承载 Spec 或实现细节。
- 保留 `docs/archive/**` 历史归档，不再作为当前 Codex 必读入口。

### 文档同步

- `README.md`
- `docs/MODULES.md`
- `docs/STANDARDS.md`
- `docs/specs/`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只做文档体系治理，不修改后端、前端业务代码、API 路径、数据库结构或测试。
- 新 Spec 基于当前代码和稳定文档梳理；后续业务代码变化时需要同步对应 Spec，避免再次漂移。

### 下一步建议

- 后续新增或修改业务能力时，先更新对应 Spec 的 Codex 快速入口和维护检查清单，再进入实现。

## 进度记录 2026-06-03 17:17

### 本次目标

落实项目系统审计中阶段 1 的交付卫生和基础 CI 门禁，先处理不影响业务逻辑的 P0 可复现交付问题。

### 本次完成

- 从 Git 跟踪中移除根目录 `node_modules`，保留开发者本地目录并继续由 `.gitignore` 忽略。
- 新增 GitHub Actions 基础 CI，push、pull request 和手动触发会执行后端 ruff/pytest、前端 `npm ci`、lint、单元测试和构建。
- 将 Playwright E2E 冒烟测试接入手动触发的 CI job，避免普通检查默认承担浏览器依赖成本。
- 将 `.e2e-runtime/` 纳入 release 检查黑名单，避免本地 E2E 数据混入源码包。
- 更新 README 和 CHANGELOG，明确源码仓库、源码交付包和 CI 均不依赖已存在的 `node_modules`。

### 未完成项与风险

- 根目录 `package.json` 当前仅包含仓库级 ESLint/Prettier/TypeScript 依赖，是否保留为正式工具链入口仍需项目负责人确认。
- 本次不处理固定/个人配置表唯一约束、旧 `regex` 规则兼容、SVN 密码回显等 P1 问题。

## 进度记录 2026-06-03 14:48

### 本次目标

为当前 Vue + FastAPI 项目补充最小可用的 Playwright 端到端冒烟测试，覆盖默认登录、Excel 上传、个人规则执行、导入项目校验和项目校验执行结果查看。

### 本次完成

- 新增前端 E2E 脚本入口，`npm run e2e` 会启动隔离后端、隔离 Vite 前端和独立 `.e2e-runtime/`。
- 新增 Playwright 配置，失败时保留 screenshot、trace 和 video。
- 新增小型 Excel fixture，使用 `Items.Name` 空值稳定触发 `not_null` 异常。
- 为登录、导航、数据源、变量、规则、导入和执行结果关键控件补充 `data-testid`。
- 更新 README 和前端 README，说明本地运行与 CI 可选运行方式。

### 未完成项与风险

- 本次只覆盖 Excel 上传链路，不覆盖 SVN、飞书或异步执行任务接口。
- E2E 依赖本机已安装后端 Python 依赖和 Playwright Chromium 浏览器。

## 进度记录 2026-06-03 14:03

### 本次目标

整理当前 Vue 前端的全局 CSS 和样式覆盖，降低共享样式、页面域样式、Element Plus 覆盖和组件局部覆盖之间的冲突风险，同时保持页面视觉和业务交互不变。

### 本次完成

- 新增 `frontend/src/styles/tokens.css`，集中维护运行时颜色、间距、圆角、阴影、控件尺寸、表格和弹窗 token，并保留 legacy alias 兼容旧样式。
- 新增 `frontend/src/styles/element-plus.css`，集中承载 Element Plus、通用按钮、表单、表格、状态标签和操作链接覆盖。
- 调整 `frontend/src/main.ts` 样式导入说明和顺序，显式标明第三方样式、Tailwind、token、共享基础、Element Plus 覆盖、页面域样式和兼容收口层。
- 从 `shared.css`、`shared-overrides.css`、`shared-final.css` 移除已迁出的重复 token 和重复 Element Plus 覆盖段。
- 将路径替换弹窗和礼包校验弹窗的局部深度覆盖改为引用 token。
- 新增 `docs/FRONTEND_STYLE_GUIDE.md`，说明颜色 token、间距 token、表格、卡片、表单、弹窗和 `!important` 使用边界。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 11 类规则执行能力、IAP 礼包校验和 AI 规则助手主链路。
- 干净源码交付包、可复现安装测试构建流程、Alembic 数据库迁移机制。
- 执行链路任务化第一阶段。
- 前端全局样式 token 和 Element Plus 覆盖开始收敛到明确分层。

#### 已实现但未打通/占位功能

- 前端样式治理本次为第一阶段：仍保留部分历史 `shared-overrides.css`、`workbench.css` 和页面域 CSS，后续可继续按页面拆分。
- 任务执行第一阶段为单进程后台任务，不支持跨进程队列、任务重试、进度百分比或取消 API。
- 飞书电子表格主链路依赖项目飞书机器人配置、OAuth 回调和飞书应用权限；多维表格、文档表格不在当前支持范围。

#### 未开始功能

- 样式 token 与 Tailwind config 自动同步尚未建立。
- 大面积页面 CSS 迁入组件 scoped style 仍需单独小阶段推进。
- 多配置集切换、SaaS 化部署、分布式任务队列、任务取消和失败重试仍未开始。

### 规范化调整

- 将运行时样式 token、Element Plus 覆盖和最终兼容收口层拆开，减少同一类样式在多个文件中重复抢权重。
- 组件专属深度覆盖改为限定在组件根 class 下，并引用全局 token。

### 文档同步

- `README.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`
- `frontend/README.md`
- `docs/FRONTEND_STYLE_GUIDE.md`

### 未完成项与风险

- 本次不做视觉重设计，不重命名现有 class，不调整 Vue 模板、路由、store、API 或业务文案。
- 全局 `!important` 仍未清零；保留部分用于覆盖 Element Plus、Tailwind utility 和历史兼容样式。
- 若后续继续迁移 `workbench.css` 或 `shared-overrides.css`，需要按页面截图和构建验证小步推进。

### 下一步建议

- 继续按页面域推进：优先拆分 `personal-check.css` 与 `fixed-rules.css` 中的重复步骤条和表格样式。
- 后续可增加视觉回归截图基线，再迁移更多全局覆盖到组件 scoped style。

## 进度记录 2026-06-03 13:26

### 本次目标

设计并落地执行链路任务化第一阶段，解决大 Excel、SVN、飞书校验时同步 HTTP 请求长时间等待的问题，同时保留现有同步接口兼容。

### 本次完成

- 在 `execution_runs` 主表上新增任务状态、执行模式、错误信息、开始时间和结束时间字段，并新增 Alembic migration。
- 抽出个人校验和项目校验共用的执行摘要构建逻辑，同步接口继续复用原返回结构。
- 新增进程内执行任务服务，使用 FastAPI `BackgroundTasks` 执行任务，并写入 `pending/running/success/failed/cancelled` 状态。
- 新增 `POST /api/v1/execute-runs`、`GET /api/v1/execute-runs/{run_id}`、`GET /api/v1/execute-runs/{run_id}/items` 三个任务接口。
- 服务启动时会把上次进程遗留的 `pending/running` 任务标记为失败，避免任务永久卡住。
- 补充任务接口测试，覆盖创建任务、状态查询、成功、失败、个人任务权限隔离和固定规则任务执行。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 11 类规则执行能力和 AI 规则助手主链路。
- 干净源码交付包、可复现安装测试构建流程、Alembic 数据库迁移机制。
- 执行链路任务化第一阶段：个人校验和项目校验可通过进程内后台任务执行。

#### 已实现但未打通/占位功能

- 任务执行第一阶段为单进程后台任务，不支持跨进程队列、任务重试、进度百分比或取消 API。
- 飞书电子表格主链路依赖项目飞书机器人配置、OAuth 回调和飞书应用权限；多维表格、文档表格不在当前支持范围。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 分布式任务队列、任务列表、任务取消、失败重试和进度推送仍待后续阶段设计。

### 规范化调整

- 将“执行并产出摘要”与“结果/任务落库”拆开，减少同步接口和任务接口之间的重复逻辑。
- 同步执行结果只清理同步模式的旧记录，避免误删异步任务记录。

### 文档同步

- `README.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次不修改前端调用，现有页面仍默认使用同步执行接口。
- 进程内后台任务适合第一阶段减小 HTTP 等待，不适合作为多 worker、跨机器或高可靠任务系统。

### 下一步建议

- 前端可先在大文件执行入口试点任务接口，轮询状态后再读取 items。
- 后续若需要生产级任务能力，再评估 Redis/RQ/Celery 或独立 worker，并补充取消、重试和进度推送。

## 进度记录 2026-06-03 12:27

### 本次目标

为 SQLAlchemy 数据库引入 Alembic 正式迁移机制，替代 `backend/app/database.py` 中不断累积的手工 `ALTER TABLE` 自修复逻辑，并保证新库初始化和旧 SQLite 库升级路径清晰可测。

### 本次完成

- 新增根目录 `alembic.ini`、`migrations/env.py`、`migrations/script.py.mako` 和首个 `0001_initial_schema` migration。
- 新增 `backend/app/db_migrations.py`，由应用启动路径执行 `alembic upgrade head`。
- `backend/app/database.py` 改为先迁移数据库结构，再执行默认项目、默认管理员和主归属项目播种；移除历史 `_ensure_*` 手工结构补丁。
- 测试夹具改为通过 Alembic 初始化测试库，新增迁移契约测试覆盖空库建表、旧库补字段/索引和重复执行幂等。
- 更新 README 和更新日志，说明数据库备份、初始化、升级和后续生成 migration 的命令。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 11 类规则执行能力和 AI 规则助手主链路。
- 干净源码交付包、可复现安装测试构建流程，以及 Alembic 数据库迁移机制。

#### 已实现但未打通/占位功能

- 飞书电子表格主链路依赖项目飞书机器人配置、OAuth 回调和飞书应用权限；多维表格、文档表格不在当前支持范围。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 聚合、公式、平均值等复杂 AI 规则仍返回不支持或需后续扩展。

### 规范化调整

- 数据库结构变更统一进入 `migrations/versions/`，后续不再向 `database.py` 追加新的结构自修复分支。
- 应用启动自动迁移数据库后再做业务播种，避免结构升级和默认账号修复分散在两套路径。

### 文档同步

- `README.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次不修改 API、数据库业务模型、前端调用或固定规则 JSON 配置迁移。
- 当前迁移运行器按现有部署口径支持 SQLite / `sqlite+aiosqlite`；如未来切换 PostgreSQL 或 MySQL，需要补充同步驱动和迁移验证。

### 下一步建议

- 后续表结构变更先修改 ORM 模型，再执行 `python -m alembic revision --autogenerate -m "说明"` 并人工审查 migration。
- 旧库正式升级前先备份 `backend/.runtime/excel_check.db`，再运行 `python -m alembic upgrade head` 或启动服务。

## 进度记录 2026-06-03 10:19

### 本次目标

建立可复现的安装、测试和构建流程，让新开发者从不包含 `.venv`、`node_modules` 和构建产物的干净源码包中稳定完成依赖安装、检查和构建。

### 本次完成

- 新增 `backend/requirements.in` 维护后端直接依赖，并用 `pip-compile` 生成锁定版本的 `backend/requirements.txt`。
- 新增跨平台 `scripts/check-standards.py`，串联后端依赖安装、`ruff check`、`pytest`、前端 `npm ci`、lint、单元测试和构建。
- 改造 `scripts/check-standards.ps1` 为 Windows PowerShell 包装入口，支持 `-DryRun` 查看命令顺序。
- 补充 `.gitignore`，显式忽略根目录和前端依赖目录、前端构建产物。
- 新增 `backend/tests/test_devops_scripts.py`，覆盖依赖锁定、直接依赖清单和一键检查 dry-run 命令顺序。
- 更新 README、前端说明、开发规范和更新日志，明确干净源码首次安装、`npm ci` 和源码包不包含依赖目录。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 11 类规则执行能力，覆盖单字段、固定值、正则、顺序、跨表映射、组合分支、双组比较、多组串行、多组映射和 IAP 礼包校验。
- AI 规则助手草稿生成、预校验、确认添加、草稿历史、提示优化和当前 11 类规则元数据识别。
- 项目规则从个人校验导入、执行结果分页、明细读取和 Excel 导出。
- 干净源码交付包生成与目录/zip 敏感内容检查能力。
- 可复现安装、测试和构建流程，后端依赖锁定，前端统一 `npm ci`。

#### 已实现但未打通/占位功能

- 飞书电子表格主链路已接入，但依赖项目飞书机器人配置、`FEISHU_OAUTH_CALLBACK_URL` 和飞书应用权限；多维表格、文档表格不在当前支持范围。
- IAP 礼包校验当前重点接在个人校验 03 规则页签；固定规则侧保留预览与运行时兼容能力，但不是主要业务入口。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 聚合、公式、平均值等复杂 AI 规则仍返回不支持或需后续扩展。

### 规范化调整

- 将后端依赖来源与锁文件拆分为 `requirements.in` / `requirements.txt`，后续升级依赖需显式重新编译锁文件。
- 将前端依赖安装统一为 `npm ci`，避免源码 zip 解压后复用不兼容或权限异常的 `node_modules`。
- 一键检查脚本集中管理本地安装、测试和构建命令，减少 README 与脚本漂移。

### 文档同步

- `README.md`
- `frontend/README.md`
- `docs/STANDARDS.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次不修改后端 API、前端路由、数据库结构、配置格式或业务逻辑。
- 完整检查脚本会重建 `frontend/node_modules`，执行前如有本地未保存的依赖目录实验内容需要自行保留。

### 下一步建议

- 后续新增后端依赖时先改 `backend/requirements.in`，再运行 `pip-compile --output-file backend/requirements.txt backend/requirements.in` 更新锁文件。
- CI 接入时直接调用 `python scripts/check-standards.py`，Windows 本地开发继续使用 `.\scripts\check-standards.ps1`。

## 进度记录 2026-06-02 21:11

### 本次目标

修复已实现功能与元数据、接口能力声明、前端文案不一致的问题，重点同步 `package_items_compare`、飞书数据源和当前 11 类规则口径。

### 本次完成

- 在规则元数据 registry 中补齐 `package_items_compare`，显示名统一为 `IAP礼包校验`。
- 同步后端 AI 提示词、候选识别、模板别名、规则库摘要和确定性 compiler registry，确保当前规则清单包含 11 类。
- 修正 `/api/v1/sources/capabilities` 的 `implemented` 状态，保持响应结构不变。
- 清理飞书读取模块和前端数据源步骤中的旧状态文案，并移除未使用的飞书兼容读取入口。
- 补充后端和前端契约测试，覆盖规则元数据、能力声明、飞书旧入口清理和前端文案一致性。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 11 类规则执行能力，覆盖单字段、固定值、正则、顺序、跨表映射、组合分支、双组比较、多组串行、多组映射和 IAP 礼包校验。
- 个人校验 03 页签的 IAP 礼包校验入口、飞书 Sheet 解析预览、规则保存、执行期运行时变量注入和 `STR_Items` 最终比对。
- AI 规则助手草稿生成、预校验、确认添加、草稿历史、提示优化和当前 11 类规则元数据识别。
- 项目规则从个人校验导入、执行结果分页、明细读取和 Excel 导出。
- 前端主要页面、系统使用说明页和共享工作台视觉组件。

#### 已实现但未打通/占位功能

- 飞书电子表格主链路已接入，但依赖项目飞书机器人配置、`FEISHU_OAUTH_CALLBACK_URL` 和飞书应用权限；多维表格、文档表格不在当前支持范围。
- IAP 礼包校验当前重点接在个人校验 03 规则页签；固定规则侧保留预览与运行时兼容能力，但不是主要业务入口。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 聚合、公式、平均值等复杂 AI 规则仍返回不支持或需后续扩展。

### 规范化调整

- 将已实现礼包校验的后端 registry、AI 清单、compiler 注册和前端别名识别统一到同一 11 类规则口径。
- 清理当前有效代码与页面文案中的飞书旧状态表述，历史归档文档保持不变。

### 文档同步

- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次不改执行入口、TaskTree、数据库结构、API 入参或返回结构。
- 飞书数据源仍依赖真实飞书应用配置与权限，测试主要覆盖元数据和契约一致性。

### 下一步建议

- 若后续继续扩展 AI 对 IAP 礼包校验的自然语言生成，可单独补充更完整的礼包字段线索提取与端到端用例。

## 进度记录 2026-05-27 10:33

### 本次目标

阅读当前代码和稳定文档，重新梳理项目现状，并更新与代码事实不一致的中文文档。

### 本次完成

- 阅读并对齐 `README.md`、`CHANGELOG.md`、`frontend/README.md`、`docs/ARCHITECTURE.md`、`docs/MODULES.md`、`docs/STANDARDS.md` 和归档进度记录尾部。
- 运行工作区扫描脚本，确认当前主语言、API 入口、稳定契约、占位实现和推荐更新文档项。
- 基于当前代码修正飞书数据源状态：飞书电子表格已接入权限检测、授权卡片、OAuth 回调、项目机器人配置、元数据读取、列预览和执行链路。
- 更新 README、架构、模块速查、前端说明、开发规范和更新日志，并新增当前活动进度记录入口。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 10 类规则执行能力，覆盖单字段、固定值、正则、顺序、跨表映射、组合分支、双组比较、多组串行和多组映射。
- AI 规则助手草稿生成、预校验、确认添加、草稿历史和提示优化。
- 项目规则从个人校验导入、执行结果分页、明细读取和 Excel 导出。
- 前端主要页面、使用说明页和共享工作台视觉组件。

#### 已实现但未打通/占位功能

- 飞书电子表格已具备主链路，但依赖项目飞书机器人配置、`FEISHU_OAUTH_CALLBACK_URL` 和飞书应用权限；多维表格、文档表格不在当前支持范围。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。
- `backend/app/loaders/feishu_reader.py` 仍保留旧占位模块说明和 `read_feishu_sheet` 兼容占位函数，但主流程已使用新的飞书读取函数。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 聚合、公式、平均值等复杂 AI 规则仍返回不支持或需后续扩展。

### 规范化调整

- 将当前活动进度记录从历史归档中分离为根目录 `PROJECT_RECORD.md`。
- 明确文档职责：稳定说明文档记录当前事实，`docs/archive/` 只保留历史快照。

### 文档同步

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/MODULES.md`
- `docs/STANDARDS.md`
- `frontend/README.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未改业务代码，仅做文档梳理；飞书相关代码中仍有旧“占位”模块 docstring，后续可单独开代码注释治理切片。
- 本次未运行完整测试；文档表述依据当前代码扫描、路由读取和测试文件分布判断。

### 下一步建议

- 单独处理飞书模块注释治理，移除已过时的“占位实现”模块说明。
- 后续若继续扩展飞书能力，应优先补充飞书配置与授权流程的端到端联调说明。

## 进度记录 2026-06-02 16:33

### 本次目标

阅读当前项目代码和说明文档，围绕近期已接入的 IAP 礼包校验能力，同步更新稳定文档和系统使用说明。

### 本次完成

- 阅读并对齐 `README.md`、`PROJECT_RECORD.md`、`CHANGELOG.md`、`frontend/README.md`、`docs/ARCHITECTURE.md`、`docs/MODULES.md`、`docs/STANDARDS.md` 和系统使用说明内容。
- 运行工作区扫描脚本，确认当前仍保持 `TaskTree`、统一执行入口和统一结果结构，且已存在礼包校验 parser、preview API、runtime 注入和 compare handler。
- 更新稳定文档，将规则能力从 10 类修正为 11 类，并补充 `package_items_compare` / `IAP礼包校验` 的预览、保存、执行和结果说明。
- 更新 `/user-guide` 内置使用说明，补充礼包校验操作流程、飞书数据源说明、异常类型和 FAQ。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 11 类规则执行能力，覆盖单字段、固定值、正则、顺序、跨表映射、组合分支、双组比较、多组串行、多组映射和 IAP 礼包校验。
- 个人校验 03 页签的 IAP 礼包校验入口、飞书 Sheet 解析预览、规则保存、执行期运行时变量注入和 `STR_Items` 最终比对。
- AI 规则助手草稿生成、预校验、确认添加、草稿历史和提示优化。
- 项目规则从个人校验导入、执行结果分页、明细读取和 Excel 导出。
- 前端主要页面、系统使用说明页和共享工作台视觉组件。

#### 已实现但未打通/占位功能

- 飞书电子表格主链路已接入，但依赖项目飞书机器人配置、`FEISHU_OAUTH_CALLBACK_URL` 和飞书应用权限；多维表格、文档表格不在当前支持范围。
- IAP 礼包校验当前重点接在个人校验 03 规则页签；固定规则侧保留预览与运行时兼容能力，但不是主要业务入口。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。
- `backend/app/loaders/feishu_reader.py` 仍保留旧占位模块说明和 `read_feishu_sheet` 兼容占位函数，但主流程已使用新的飞书读取函数。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 聚合、公式、平均值等复杂 AI 规则仍返回不支持或需后续扩展。

### 规范化调整

- 统一稳定文档、模块速查和系统使用说明中对 IAP 礼包校验、飞书数据源和规则数量的表述。
- 保持历史归档文档不变，仅更新当前稳定说明入口。

### 文档同步

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/MODULES.md`
- `frontend/README.md`
- `frontend/src/content/userGuide.ts`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只做文档与使用说明更新，未修改后端业务代码、前端业务逻辑或 API 类型。
- 文档说明基于当前工作区代码、路由、类型和测试分布判断；未执行后端 pytest。
- 飞书与礼包校验实际联调仍依赖真实项目机器人、表格授权和业务 Sheet 数据。

### 下一步建议

- 如继续治理文档，可单独整理飞书旧兼容模块的中文 docstring，移除容易误解的“占位”措辞。
- 如继续增强礼包校验，可补充一份面向业务用户的示例 Sheet / STR_Items 对照说明。

## 进度记录 2026-06-02 19:46

### 本次目标

新增干净源码交付包能力，在不改变后端、前端业务逻辑的前提下，提供 release 打包脚本、发布包敏感内容检查脚本、测试覆盖和中文交付说明。

### 本次完成

- 新增 `scripts/release_package.py`，按文件系统遍历生成源码 zip，默认输出到项目同级 `release-packages/`，并排除依赖目录、构建产物、runtime 数据、SVN 缓存、数据库、日志、密钥和本地凭据文件。
- 新增 `scripts/check_release_package.py`，支持扫描待发布目录或 zip，发现敏感路径、运行时数据或 zip slip 风险时直接失败。
- 新增 `backend/tests/test_release_package_scripts.py`，使用临时目录覆盖源码保留、敏感目录排除、敏感文件排除、源码 credentials 命名放行、目录/zip 违规检测和 zip slip 检测。
- 更新 `README.md`，补充源码交付包命令、检查命令、交付内容边界和 runtime 数据不随包交付的说明。
- 更新 `CHANGELOG.md`，记录干净源码交付包能力。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 11 类规则执行能力，覆盖单字段、固定值、正则、顺序、跨表映射、组合分支、双组比较、多组串行、多组映射和 IAP 礼包校验。
- 个人校验 03 页签的 IAP 礼包校验入口、飞书 Sheet 解析预览、规则保存、执行期运行时变量注入和 `STR_Items` 最终比对。
- AI 规则助手草稿生成、预校验、确认添加、草稿历史和提示优化。
- 项目规则从个人校验导入、执行结果分页、明细读取和 Excel 导出。
- 前端主要页面、系统使用说明页和共享工作台视觉组件。
- 干净源码交付包生成与目录/zip 敏感内容检查能力。

#### 已实现但未打通/占位功能

- 飞书电子表格主链路已接入，但依赖项目飞书机器人配置、`FEISHU_OAUTH_CALLBACK_URL` 和飞书应用权限；多维表格、文档表格不在当前支持范围。
- IAP 礼包校验当前重点接在个人校验 03 规则页签；固定规则侧保留预览与运行时兼容能力，但不是主要业务入口。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。
- `backend/app/loaders/feishu_reader.py` 仍保留旧占位模块说明和 `read_feishu_sheet` 兼容占位函数，但主流程已使用新的飞书读取函数。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 聚合、公式、平均值等复杂 AI 规则仍返回不支持或需后续扩展。

### 规范化调整

- 将发布包敏感路径规则集中在检查脚本中，release 脚本复用同一套规则，避免打包规则和检查规则后续漂移。
- 保持业务源码、API、数据库结构、配置格式和本地 runtime 文件不变。

### 文档同步

- `README.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未修改后端和前端业务代码，仅新增 release 工具、测试和文档。
- 源码交付包不包含 `frontend/dist/`，因此它是源码包，不是可直接运行的部署包。

### 下一步建议

- 正式交付前执行 `python scripts/release_package.py`，再用 `python scripts/check_release_package.py <zip路径>` 复核生成物。

## 进度记录 2026-06-02 20:22

### 本次目标

加固 FastAPI 数据源相关接口，要求登录和项目成员校验，阻断匿名探测服务端本地路径，并保持上传、SVN 和飞书数据源正常流程可用。

### 本次完成

- `backend/app/auth/dependencies.py` 为当前用户上下文保留 JWT 原始 `pid`，新增严格项目成员校验，避免普通用户 Token 指向非成员项目时静默回退到默认项目。
- `backend/config.py` 新增 `LOCAL_FILE_ROOT_ALLOWLIST` 和 `ENABLE_LOCAL_PICKER` 配置；本地文件选择器默认关闭。
- `backend/app/loaders/local_reader.py` 新增本地 Excel/SVN 本地工作副本路径 allowlist 校验，显式白名单与上传目录、SVN 缓存目录合并为有效读取范围。
- `backend/app/api/source_api.py` 将 metadata、column-preview、composite-preview、local-directory-validate、local-pick、upload 和 SVN 相关接口切到登录依赖与严格项目校验；allowlist 外本地路径返回 403。
- 新增 `backend/tests/test_source_api_security.py`，覆盖未登录访问、跨项目访问、allowlist 外拒绝、allowlist 内正常读取、目录探测阻断和 local-picker 开关。
- 更新测试公共 fixture，让测试环境仅显式放行测试数据目录和每个用例的临时目录，避免新安全边界破坏既有本地 Excel 回归测试。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 数据源元数据、列预览、组合变量预览、本地目录校验、本地选择、上传和 SVN 相关接口已要求登录与项目成员校验。
- 本地 Excel 路径读取已增加服务端 allowlist，浏览器上传目录和 SVN 缓存目录自动允许读取。
- 11 类规则执行能力，覆盖单字段、固定值、正则、顺序、跨表映射、组合分支、双组比较、多组串行、多组映射和 IAP 礼包校验。
- 干净源码交付包生成与目录/zip 敏感内容检查能力。

#### 已实现但未打通/占位功能

- 本地文件选择器默认关闭，开发或单机使用时需显式设置 `ENABLE_LOCAL_PICKER=true`，且所选路径仍必须位于 allowlist 内。
- 飞书电子表格主链路已接入，但依赖项目飞书机器人配置、`FEISHU_OAUTH_CALLBACK_URL` 和飞书应用权限；多维表格、文档表格不在当前支持范围。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 聚合、公式、平均值等复杂 AI 规则仍返回不支持或需后续扩展。

### 规范化调整

- 将本地路径读取安全边界集中在 `local_reader`，source API 和执行链路复用同一套 allowlist 校验。
- 保持后端 API 入参、返回结构、数据库结构、前端路由和现有配置格式不变，仅新增环境变量。

### 文档同步

- `README.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- `POST /api/v1/engine/execute` 本轮按计划不改登录策略，但底层本地文件读取已走 allowlist；匿名执行若引用 allowlist 外本地文件会被拒绝。
- 共享或生产部署如需读取固定共享盘，需要管理员显式配置 `LOCAL_FILE_ROOT_ALLOWLIST`，否则只能使用上传、远端 SVN 或飞书数据源。

### 下一步建议

- 生产部署前设置固定 `JWT_SECRET_KEY` 和管理员密码，并按实际共享盘路径配置最小化 `LOCAL_FILE_ROOT_ALLOWLIST`。

## 进度记录 2026-06-02 20:39

### 本次目标

新增生产环境安全配置检查，在不影响本地开发体验的前提下，阻止生产部署继续使用开发默认密钥、默认管理员密码、开放 CORS 和隐式 SVN host 白名单。

### 本次完成

- `backend/config.py` 新增 `APP_ENV`，仅支持 `development` 与 `production`，默认 `development`。
- 在 `Settings` 初始化阶段增加 production 安全校验，缺少 `JWT_SECRET_KEY`、`DEFAULT_SUPER_ADMIN_PASSWORD`、`CORS_ALLOW_ORIGINS`、`SVN_URL_ALLOWLIST`，使用默认管理员密码 `123456`，或配置 CORS `*` 时直接抛出明确错误。
- `backend/run.py` 在 development 创建应用时输出警告日志，说明默认值仅适合本地开发，生产需启用 `APP_ENV=production` 并显式配置安全项。
- 新增 `backend/tests/test_config_security.py`，覆盖 development 默认值、production 缺失配置、默认密码、CORS 通配符、合法 production 配置和非法 `APP_ENV`。
- 更新 `README.md` 的部署配置说明，并同步 `CHANGELOG.md`。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 数据源相关接口已要求登录与项目成员校验，本地 Excel 路径读取已增加服务端 allowlist。
- 生产环境配置安全检查已接入启动前配置初始化阶段。
- 11 类规则执行能力和 IAP 礼包校验主流程已接入。
- 干净源码交付包生成与目录/zip 敏感内容检查能力。

#### 已实现但未打通/占位功能

- 本地文件选择器默认关闭，开发或单机使用时需显式设置 `ENABLE_LOCAL_PICKER=true`，且所选路径仍必须位于 allowlist 内。
- 飞书电子表格主链路已接入，但依赖项目飞书机器人配置、`FEISHU_OAUTH_CALLBACK_URL` 和飞书应用权限；多维表格、文档表格不在当前支持范围。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 聚合、公式、平均值等复杂 AI 规则仍返回不支持或需后续扩展。

### 规范化调整

- 将生产部署安全门禁集中在 `Settings`，保证任意启动路径都会先经过同一套配置校验。
- development 继续保留本地快速启动默认值，production 才强制显式配置。

### 文档同步

- `README.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次不新增 API、数据库字段或前端交互；生产环境变量需要由部署脚本、系统服务或运维平台提供。
- development 日志只提示风险，不阻断启动；真正对外部署必须显式设置 `APP_ENV=production`。

### 下一步建议

- 后续若补充 Docker、systemd 或 Windows 服务部署脚本，应同步把 `APP_ENV=production` 与四个必填安全变量写入示例配置。

## 进度记录 2026-06-10 12:30

### 本次目标

同步项目活跃文档，使其与“删除个人 AI 凭据体系、删除智能添加规则、统一使用项目级 AI 凭据”的最终设计一致。

### 本次完成

- 更新 README、架构文档、模块速查和系统使用说明中的 AI 配置口径。
- 新增 ADR，记录统一 AI 凭据为项目级配置并删除个人 AI 凭据体系的决策。
- 在更新日志中补充本次文档治理记录。
- 保持 `docs/archive/**` 历史归档不变。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 11 类规则执行能力和 IAP 礼包校验主流程已接入。
- 项目级飞书机器人、配置表查询规则和项目级 AI 凭据配置能力已接入。
- AI 配置已统一为项目级凭据，个人 AI 配置和智能添加规则不再作为当前功能入口。

#### 已实现但未打通/占位功能

- 本地文件选择器默认关闭，开发或单机使用时需显式设置 `ENABLE_LOCAL_PICKER=true`，且所选路径仍必须位于 allowlist 内。
- 飞书电子表格主链路依赖项目飞书机器人配置、`FEISHU_OAUTH_CALLBACK_URL` 和飞书应用权限；多维表格、文档表格不在当前支持范围。
- SVN 远端依赖 SVN CLI、host 白名单和用户凭据，缓存暂无定时清理策略。

#### 未开始功能

- 多配置集切换未开放。
- SaaS 化部署、容器编排、反向代理、HTTPS 不在当前项目边界。
- 聚合、公式、平均值等复杂规则未纳入当前规则库。

### 规范化调整

- 将项目级 AI 凭据、AI 不可用策略和保留 AI 辅助能力写入稳定文档和 ADR。
- 保持 CONTEXT 只描述术语，不加入表名、接口路径或函数名等实现细节。

### 文档同步

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/MODULES.md`
- `docs/STANDARDS.md`
- `docs/adr/0001-unify-ai-credentials-project-level.md`
- `frontend/src/content/userGuide.ts`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档和静态用户指南，不修改业务代码。
- 项目级 AI 的实际可用性仍依赖管理员配置供应商、模型、Base URL、API Key 和上游服务状态。

### 下一步建议

- 后续如新增 AI 辅助能力，先在 ADR 或架构文档中明确是否读取项目级凭据、不可用时是否回退、以及是否会影响确定性校验结果。

## 进度记录 2026-06-22 10:38

### 本次目标

阅读当前仓库代码和稳定文档，结合旧会话 `019eca67-83e2-7532-babe-54883f9497cc`、`qa-case` skill 与 TestCaseStudio 项目，新增一份专门记录“用例生成”需求的上下文文档。

### 本次完成

- 新增 `docs/specs/test-case-generation.md`，整理独立“用例生成”页面的需求目标、已确认口径、策划案来源、快照边界、参考案例库、生成方法论、V1 工作流、输出字段、权限安全、前后端边界、测试覆盖和待确认问题。
- 将旧会话中已确认的关键结论沉淀到 Spec：单次一个 `Planning Sheet`、默认整张 Sheet、后端快照预算和 warnings、项目级 AI 凭据、项目级参考案例库、参考案例画像、V1 参考案例格式、暂不做跨项目引用和图片识别。
- 更新 `docs/specs/README.md`，把“用例生成（需求整理中）”加入业务能力 Spec 索引。
- 更新 `CHANGELOG.md` 的文档治理条目，明确该能力仍处于需求整理阶段，尚未新增页面或生产接口。

### 当前项目进度

#### 已完成功能

- 多用户认证、注册、登录、项目切换、项目/成员/角色/密码管理。
- 个人校验四步工作流和项目校验长期规则配置，共用 `TaskTree` 与统一执行结果结构。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格数据源接入。
- 11 类规则执行能力、IAP 礼包校验、配置表查询规则、项目级飞书机器人和项目级 AI 凭据配置已接入。
- `CONTEXT.md` 已具备用例生成相关术语，包括 `Planning Sheet`、`Planning Sheet Snapshot`、`Test Case Generation Workspace`、`Reference Test Case Library`、`Reference Test Case Profile` 和 `Test Case Blueprint`。

#### 已实现但未打通/占位功能

- 用例生成能力目前只有需求上下文和领域术语沉淀，尚未进入生产代码实现。
- 当前仓库已有飞书和 Excel 读取、项目级 AI provider、项目成员权限等底座，但尚未封装为用例生成专用服务。
- TestCaseStudio 可作为参考项目，其个人 API Key、Streamlit 本地应用和本地目录扫描模式不适合直接照搬到当前多用户 Web 项目。

#### 未开始功能

- `/test-cases` 前端页面、导航入口、API 类型和页面状态管理未开始。
- `backend/app/test_cases/`、`test_cases_api.py`、参考案例库持久化、画像生成、AI 编排和 Excel 导出未开始。
- 图片/原型图理解、XMind/Markdown/Feishu 表导出、生成历史持久化和跨项目案例库引用不在 V1 范围。

### 规范化调整

- 保持 `CONTEXT.md` 只作为术语表，不继续写入接口、组件、默认上限等实现细节。
- 将新需求按业务能力 Spec 记录到 `docs/specs/`，符合“业务 Spec 先行”的开发规范。
- 明确 `qa-case` 在当前仓库中不能直接执行 CLI，只迁移方法论和字段口径。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/specs/README.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只新增和同步文档，不修改业务代码，不新增数据库迁移，不运行前后端测试。
- 旧会话中已有的 `CONTEXT.md` 修改处于工作区未提交状态，本次没有回滚或覆盖。
- 后续实现前仍需确认案例库维护权限、是否保存生成历史、蓝图是否允许人工编辑、导出列顺序是否严格复刻主参考和图片能力是否进入 V2。

### 下一步建议

- 下一轮先围绕 `docs/specs/test-case-generation.md` 的待确认问题逐项收敛；确认 V1 范围后，再拆后端数据模型、API schema、前端页面和测试计划。

## 进度记录 2026-06-22 11:05

### 本次目标

在“用例生成”V1 决策已收敛后，按“数据模型/迁移 → 参考案例库和画像 → 策划案快照 → AI 生成编排 → Excel 导出 → 前端页面”拆出可执行实施计划。

### 本次完成

- 新增 `docs/superpowers/plans/2026-06-22-test-case-generation.md`，按后续 agent 可执行的复选清单格式整理实施计划。
- 计划覆盖数据表、迁移、参考案例库、画像提取、策划案快照、项目级 AI 编排、Excel 导出、前端页面、测试文件和验证命令。
- 将已确认 V1 范围写入计划：不保存生成历史、不编辑蓝图、不做图片理解、不严格复刻参考 Excel、案例库维护权限按项目成员/项目管理员收口。

### 当前项目进度

- 用例生成仍处于需求与实施计划阶段，尚未新增生产接口、数据库迁移或前端页面。
- 下一步可直接从计划的 Phase 1 “数据模型/迁移”开始实施。

### 文档同步

- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只新增计划文档和项目记录，不修改业务代码。
- 未运行前后端测试；后续实现每个 Phase 时按计划中的 targeted 命令验证。

## 进度记录 2026-06-22 12:09

### 本次目标

将“用例生成”从需求上下文整理为 V1 版本需求文档，明确范围、权限、流程、输入输出、限制和验收标准。

### 本次完成

- 重写 `docs/specs/test-case-generation.md` 为《用例生成 V1 需求文档》，覆盖页面入口、策划案来源、快照预算、参考案例库、参考案例画像、AI 蓝图与用例生成、Excel 导出、权限安全、验收标准和 V2 候选。
- 更新 `docs/specs/README.md`，将用例生成状态从“需求整理中”调整为“V1 需求已确认”。
- 更新 `CHANGELOG.md` 的文档治理条目，说明该能力已有 V1 需求文档但尚未实现生产接口或页面。

### 当前项目进度

- 用例生成 V1 需求已形成稳定文档。
- 用例生成实现仍未开始；下一步仍可按 `docs/superpowers/plans/2026-06-22-test-case-generation.md` 从 Phase 1 数据模型/迁移推进。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/specs/README.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只修改文档，不新增业务代码、迁移或页面。
- 未运行测试；后续进入实现切片时再按计划中的 targeted 命令验证。

## 进度记录 2026-06-22 14:44

### 本次目标

基于《用例生成 V1 需求文档》和当前前端样式规范，生成一张与项目风格一致的“用例生成”页面 UI 方向图。

### 本次完成

- 使用图像生成工具生成桌面端 16:9 高保真 UI 方向图，覆盖左侧项目导航、策划案来源、参考案例库、生成设置、用例表格、蓝图摘要和 warnings。
- 将生成图复制到 `docs/assets/test-case-generation-ui-v1.png`，避免只保留在 Codex 默认生成目录。
- 在 `docs/specs/test-case-generation.md` 的快速入口中补充 UI 设计图路径。
- 更新 `CHANGELOG.md` 的文档治理条目，记录 V1 需求文档配套页面 UI 方向图。

### 当前项目进度

- 用例生成 V1 需求文档和 UI 方向图已具备。
- 生产代码仍未开始实现；下一步仍应按实施计划从 Phase 1 数据模型/迁移推进。

### 文档同步

- `docs/assets/test-case-generation-ui-v1.png`
- `docs/specs/test-case-generation.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只新增设计图和文档引用，不新增业务代码、迁移或页面。
- 图像生成的中文细节可能存在轻微渲染偏差；实现时以需求文档和现有组件样式为准。
- 未运行测试。

## 进度记录 2026-06-22 18:21

### 本次目标

参照“用例生成”V1 需求文档和 UI 方向图，先新增静态数据版前端页面，不接入后端接口。

### 本次完成

- 新增 `frontend/src/views/TestCaseGeneratorView.vue`，使用静态数据呈现策划案来源、参考案例库、生成设置、测试用例表格、用例蓝图、warnings 和导出入口。
- 更新 `frontend/src/router/index.ts`，新增认证路由 `/test-cases`。
- 更新 `frontend/src/router/routePreload.ts`，补充用例生成页面预加载。
- 更新 `frontend/src/App.vue`，在左侧主导航加入“用例生成”入口。
- 新增 `frontend/tests/unit/testCaseGeneratorRoute.test.ts`，覆盖 `/test-cases` 路由注册。
- 新增 `frontend/tests/unit/TestCaseGeneratorView.test.ts`，覆盖静态工作台内容和策划案来源切换。
- 更新 `docs/specs/test-case-generation.md` 和 `docs/specs/README.md`，说明静态前端页已新增但后端尚未接入。
- 更新 `CHANGELOG.md`，记录静态“用例生成”页面。

### 当前项目进度

- 用例生成 V1 已有需求文档、UI 方向图和静态前端页面。
- 参考案例库、策划案快照、AI 生成编排、Excel 导出等后端能力仍未开始。

### 验证结果

- `npm run test:unit -- testCaseGeneratorRoute`：先失败于缺少 `/test-cases` 路由，接入路由后通过。
- `npm run test:unit -- testCaseGeneratorRoute TestCaseGeneratorView`：通过，2 个测试文件、3 个用例。
- `npm run build`：通过。
- `npm run lint`：通过。
- 浏览器级 Playwright 检查未执行成功：本机缺少 Playwright Chromium 浏览器二进制。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/specs/README.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 页面所有业务数据均为静态数据，未调用后端。
- `/test-cases` 仍复用现有登录守卫；本地试看需要已有前端登录态或后端认证服务。
- 后续接入真实接口时，需要按实施计划继续补后端模型、API、导出器和 API 层测试。

## 进度记录 2026-06-22 18:46

### 本次目标

确认用例生成 V1 参考案例库中“推荐主参考”的唯一性范围，并同步需求文档和实施计划。

### 本次完成

- 明确 V1 推荐主参考按“项目 + 分类”唯一；同一项目的不同分类可以各自拥有一个推荐主参考。
- 更新 `docs/specs/test-case-generation.md` 的“推荐主参考”需求描述。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md`，同步服务函数、清理范围、权限测试和生成兜底规则。

### 当前项目进度

- 用例生成 V1 的参考案例库推荐主参考范围已确认。
- 后续实现参考案例库时，应按 `project_id + category_id` 清理同分类下其它推荐标记。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-22 18:53

### 本次目标

确认用例生成 V1 中删除参考案例分类时，原分类下推荐主参考标记的处理规则。

### 本次完成

- 明确删除分类时将关联参考案例移动到“未分类”展示，同时清空这些参考案例的推荐主参考标记。
- 明确“未分类”作为 `category_id = null` 的独立推荐范围，管理员可重新设置一个推荐主参考。
- 更新 `docs/specs/test-case-generation.md` 的分类删除规则。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md`，同步数据处理规则和 API 测试要求。

### 当前项目进度

- 推荐主参考的唯一范围和分类删除后的标记清理规则均已确认。
- 后续实现 `delete_reference_category` 时，应在同一事务内完成分类删除、关联文件 `category_id` 置空和 `is_recommended_primary` 清空；未分类范围后续可单独设置一个推荐主参考。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-22 18:56

### 本次目标

确认用例生成 V1 参考案例上传时，同名 active 文件的处理规则。

### 本次完成

- 明确 V1 不做参考案例覆盖替换。
- 明确同一项目、同一分类、同名 active 参考案例直接拒绝上传，并提示先联系项目管理员删除旧文件后再上传。
- 更新 `docs/specs/test-case-generation.md`，移除“上传或替换”措辞并补充同名 active 拒绝规则。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md`，同步服务规则和测试覆盖要求。

### 当前项目进度

- 参考案例库的推荐主参考范围、分类删除标记清理和同名 active 上传冲突规则均已确认。
- 后续实现 `save_reference_file` 时，应按 `project_id + category_id + original_filename + deleted_at IS NULL` 做 active 冲突检查；`category_id = null` 的未分类范围也参与同名检查。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-22 19:01

### 本次目标

确认用例生成 V1 参考案例分类创建权限。

### 本次完成

- 明确 V1 参考案例分类创建对所有项目成员开放。
- 明确分类重命名和删除仍仅限项目管理员和超级管理员。
- 更新 `docs/specs/test-case-generation.md` 的角色能力、分类需求和权限验收。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md`，同步 API 权限边界和测试覆盖要求。

### 当前项目进度

- 参考案例库权限口径进一步收敛：成员可创建分类和上传参考案例，管理员维护删除、重命名和推荐主参考。
- 后续实现 API 时，`POST /api/v1/test-cases/reference-categories` 应走严格项目成员校验，`PATCH/DELETE /reference-categories/{category_id}` 走项目管理员校验。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-22 19:05

### 本次目标

确认用例生成 V1 参考案例分类是否允许空分类。

### 本次完成

- 明确 V1 允许项目成员创建空分类。
- 明确空分类仅用于组织参考案例，不影响生成流程。
- 更新 `docs/specs/test-case-generation.md` 的分类需求。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md`，同步创建分类服务和测试要求。

### 当前项目进度

- 参考案例库分类规则已进一步明确：成员可创建空分类，上传参考案例时可选择已有分类或未分类。
- 后续实现 `create_reference_category` 时，只校验项目成员身份、名称非空和同项目名称唯一，不要求分类下已有参考文件。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-22 19:09

### 本次目标

确认用例生成 V1 参考案例分类名称的规范化和去重规则。

### 本次完成

- 明确分类名称保存前去除首尾空格。
- 明确去除首尾空格后为空字符串时拒绝。
- 明确同一项目内按去除首尾空格后的名称唯一。
- 明确不做大小写折叠、内部空格规整或全角/半角转换。
- 更新 `docs/specs/test-case-generation.md` 的分类名称规则。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md`，同步实现提示和测试覆盖要求。

### 当前项目进度

- 参考案例分类命名规则已确认，并与现有项目名称保存前 `strip()` 的处理风格对齐。
- 后续实现 `create_reference_category` 和 `rename_reference_category` 时，应统一使用 trim 后名称进行保存与唯一性校验。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-23 17:26

### 本次目标

确认用例生成 V1 参考案例上传后，画像生成失败时是否保留文件或记录。

### 本次完成

- 明确画像生成失败视为上传失败。
- 明确画像失败时删除已写入文件，不保存参考案例记录，不在列表中暴露 failed 半成品。
- 更新 `docs/specs/test-case-generation.md` 的参考案例上传和画像异常规则。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md`，同步上传服务清理行为和测试覆盖要求。

### 当前项目进度

- 参考案例上传链路的失败边界已确认：V1 只暴露可用画像的 active 参考案例。
- 后续实现 `save_reference_file` 时，应在画像解析失败后清理临时文件并回滚数据库插入，不提供 failed 记录重试入口。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-23 18:03

### 本次目标

确认用例生成 V1 中 Excel 参考案例多 Sheet 时的默认 Sheet 选择和页面手动选择规则。

### 本次完成

- 明确 Excel 参考案例默认 Sheet 由后端判定。
- 明确默认优先级为 `测试用例`、`用例`、`TestCases`；都未命中时使用第一个非空 Sheet。
- 明确页面默认选中后端识别出的默认 Sheet，用户可以在生成设置中手动改选主参考 Sheet。
- 更新 `docs/specs/test-case-generation.md` 的参考案例上传和主参考 Sheet 需求。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md`，同步常量、画像提取逻辑、API 测试和前端测试要求。

### 当前项目进度

- 参考案例 Excel 多 Sheet 画像和生成选择规则已确认。
- 后续实现 `reference_profiles.py` 时，应为每个非空 Sheet 生成画像，并按 `测试用例`、`用例`、`TestCases`、第一个非空 Sheet 的顺序解析默认 Sheet。
- 后续前端接入真实接口时，应将 `default_sheet_name` 作为默认选中值，并允许用户改选 `sheet_options` 中的其它 Sheet。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-23 18:09

### 本次目标

澄清用例生成页面中红框位置的“数量”含义，并同步需求文档、实施计划和当前静态页面。

### 本次完成

- 明确该位置展示的是从参考案例或主参考 Sheet 画像中读取出的参考用例数量。
- 明确该字段为只读展示，不是用户可输入的目标生成数量。
- 更新 `docs/specs/test-case-generation.md`，补充参考用例数量的画像字段和前端状态规则。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md`，将 `generation_options` 中的 case count target 口径移除，改为 `reference_case_count` 只读展示。
- 更新 `frontend/src/views/TestCaseGeneratorView.vue`，将静态页面文案从“目标用例数量”改为“参考用例数量”，并按主参考 Sheet 示例展示数量。
- 更新 `frontend/tests/unit/TestCaseGeneratorView.test.ts`，同步静态页面断言。

### 当前项目进度

- 用例生成 V1 的数量字段语义已收口：参考用例数量来自参考画像，用于提示参考规模，不作为生成数量控制项。
- 后续实现 `reference_profiles.py` 时，应从可识别用例行中计算 `reference_case_count`；前端接入真实接口后应展示该字段并随主参考 Sheet 切换更新。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 代码同步

- `frontend/src/views/TestCaseGeneratorView.vue`
- `frontend/tests/unit/TestCaseGeneratorView.test.ts`

### 未完成项与风险

- 本次只同步文档和静态前端页面，未接入后端。
- 后端真实 `reference_case_count` 的识别规则仍需在实现时通过单测固定。

## 进度记录 2026-06-23 18:54

### 本次目标

确认用例生成 V1 中 `reference_case_count` 的具体计数规则。

### 本次完成

- 明确 Excel 参考用例数量从识别到的表头下一行开始统计。
- 明确只统计包含用例标题、检查点、步骤、预期等用例内容字段的行。
- 明确模块、功能、场景等层级字段只作为辅助判断，纯分组行不计入。
- 明确完全空行、说明行、合计行、只有备注/说明字段有值的行不计入。
- 明确 Markdown/TXT 只有能识别表格用例行或 checklist 用例项时才统计，否则返回未知并在页面显示“未识别”。
- 更新 `docs/specs/test-case-generation.md` 和 `docs/superpowers/plans/2026-06-22-test-case-generation.md`。

### 当前项目进度

- 参考用例数量已具备可实现、可测试的 V1 规则。
- 后续实现 `reference_profiles.py` 时，应围绕表头识别、分组行排除、说明/合计行排除、Markdown/TXT 未识别回退补单测。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-23 18:56

### 本次目标

确认 Excel 参考案例可读取但表头或用例行无法可靠识别时的 V1 处理规则。

### 本次完成

- 明确 Excel 参考案例必须至少有一个可用 Sheet。
- 明确可用 Sheet 指能可靠识别表头，并能识别出至少一行参考用例的 Sheet。
- 明确只有可用 Sheet 进入主参考 Sheet 可选列表。
- 明确 Excel 文件可读取但没有任何可用 Sheet 时，视为画像生成失败并拒绝上传。
- 更新 `docs/specs/test-case-generation.md` 和 `docs/superpowers/plans/2026-06-22-test-case-generation.md`。

### 当前项目进度

- 参考案例画像失败边界进一步收紧：Excel 能打开不等于可作为参考案例，必须识别出可用 Sheet 才能保存。
- 后续实现 `reference_profiles.py` 时，应在无可用 Sheet 时抛出画像提取错误，由上传服务清理文件并不保存记录。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-23 19:03

### 本次目标

澄清参考案例库的存储形态、与现有 Excel 上传读取能力的复用边界，以及多 Sheet 中部分 Sheet 不可用时的上传规则。

### 本次完成

- 明确参考案例库是项目级服务端资源，不是用户本机配置。
- 明确参考案例通过浏览器上传到后端，由后端按项目保存文件、画像和元数据，同项目成员通过 API 查看、选择和使用。
- 明确参考案例文件属于长期项目资产，不能放入普通 Excel 上传清理目录；实施计划改为独立参考案例存储根目录。
- 明确不能直接把现有 `/api/v1/sources/upload` 的返回结果当作参考案例库记录，因为现有接口面向用户级数据源路径，不管理分类、画像、推荐主参考和项目共享列表。
- 明确可复用或抽取现有上传/Excel 读取的底层能力，包括文件名清洗、分块保存、大小限制、后缀校验、Excel engine 选择和 workbook 打开。
- 明确多 Sheet Excel 只要至少有一个可用 Sheet 就允许上传；不可用 Sheet 跳过并记录 warnings。
- 更新 `docs/specs/test-case-generation.md` 和 `docs/superpowers/plans/2026-06-22-test-case-generation.md`。

### 当前项目进度

- 参考案例库的存储和复用边界已明确：API 和业务生命周期独立，长期文件存储独立，底层上传/读取能力尽量复用。
- 后续实现时应优先抽取共享文件上传和 Excel 打开 helper，避免复制 `source_api.py` / `local_reader.py` 中的底层逻辑，同时保持 `/api/v1/test-cases/references` 独立。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-23 19:44

### 本次目标

确认用例生成 V1 中管理员删除参考案例时，数据库记录、物理文件和画像数据的处理规则。

### 本次完成

- 明确删除参考案例时，列表和生成选择立即排除该记录。
- 明确数据库记录采用软删除，仅保留审计所需元数据。
- 明确物理文件立即删除。
- 明确删除后不继续保留可复用的 `storage_path` 和 `profile_json`。
- 更新 `docs/specs/test-case-generation.md` 的参考案例删除需求。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md` 的数据模型、服务行为、测试覆盖和风险说明。

### 当前项目进度

- 参考案例删除边界已收口：V1 不长期保留原文件或画像，只保留文件名、后缀、大小、上传人、上传时间、删除人、删除时间等审计元数据。
- 后续实现 `soft_delete_reference_file` 时，应在同一业务操作中删除物理文件、设置 `deleted_at/deleted_by`，并清空 `storage_path/profile_json/is_recommended_primary`。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-24 20:43

### 本次目标

确认用例生成 V1 中删除参考案例时，物理文件已不存在或删除失败的处理规则。

### 本次完成

- 明确物理文件已不存在时，删除接口按幂等成功处理，继续软删除记录并清空可复用元数据。
- 明确物理文件存在但因权限或 IO 错误删除失败时，接口返回删除失败，记录保持 active。
- 明确删除失败时不清空 `storage_path/profile_json/is_recommended_primary`，便于管理员修复后重试。
- 更新 `docs/specs/test-case-generation.md` 的参考案例删除边界。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md` 的服务行为和测试覆盖。

### 当前项目进度

- 参考案例删除事务边界已补齐：只有物理删除成功或确认文件已不存在时，才进入软删除和元数据清理。
- 后续实现删除接口时，应先处理物理文件删除结果，再决定是否提交数据库软删除；避免出现列表隐藏但文件仍残留的状态。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只更新文档，不新增业务代码。
- 未运行测试。

## 进度记录 2026-06-24 20:56

### 本次目标

确认用例生成 V1 中参考案例库与生成主链路的依赖关系，并同步文档和静态页面文案。

### 本次完成

- 明确生成主线以 `qa-case` 方法论为主体，先蓝图、再用例行，并覆盖完整性矩阵。
- 明确参考案例库是可选增强输入，不是生成前置条件。
- 明确未选择参考案例或主参考时，也必须能基于策划案快照生成高质量用例。
- 明确未选择主参考时，导出采用标准字段顺序；选择主参考时才尽量贴近参考字段和风格。
- 更新 `CONTEXT.md` 中参考案例选择和主参考的术语定义。
- 更新 `docs/specs/test-case-generation.md` 的用户流程、参考选择、前端状态、验收标准。
- 更新 `docs/superpowers/plans/2026-06-22-test-case-generation.md` 的生成契约、测试覆盖和实施顺序。
- 调整 `frontend/src/views/TestCaseGeneratorView.vue` 静态页文案与生成可用状态，生成按钮不再依赖参考案例选择。
- 更新 `frontend/tests/unit/TestCaseGeneratorView.test.ts` 中对应静态页面断言。

### 当前项目进度

- 依赖顺序已调整：可以先实现“策划案快照 → qa-case 生成 → 标准 Excel 导出”的无参考闭环，再开发参考案例库作为增强能力。
- 后续实现 `generate` 接口时，`reference_ids` 和 `primary_reference_id` 应为可选；不得自动选最新参考案例作为主参考。

### 文档同步

- `CONTEXT.md`
- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`
- `frontend/src/views/TestCaseGeneratorView.vue`
- `frontend/tests/unit/TestCaseGeneratorView.test.ts`

### 未完成项与风险

- 本次未实现后端 API。
- 前端单测 `npm run test:unit -- TestCaseGeneratorView` 已通过。

## 进度记录 2026-06-24 21:07

### 本次目标

确认用例生成 V1 是否实现可维护 QA 知识库，以及如何为 V2 预留扩展并记录延期项。

### 本次完成

- 明确 V1 不做可维护 QA 知识库。
- 明确 V1 只内置 `QA Case Method`，包含蓝图、完整性矩阵、场景库、自检和代码统计约束。
- 明确后端可预留内部 `knowledge_context` 或等价扩展点，但 V1 公共请求不接收用户传入知识内容；如传入则拒绝。
- 明确 `Project QA Knowledge Library` 是 V2 候选，不等同于参考案例库。
- 在 `CONTEXT.md` 增加 `QA Case Method` 和 `Project QA Knowledge Library` 术语。
- 在 `docs/specs/test-case-generation.md` 增加 V1 不做知识库、V2 候选和 V1 延期清单。
- 在 `docs/superpowers/plans/2026-06-22-test-case-generation.md` 增加 `qa_case_method.py`、`QaCaseMethodContext`、`RequirementTrace`、V2 延期项和测试要求。

### 当前项目进度

- V1 生成主链路收口为“策划案快照 + 内置 QA Case Method + 项目级 AI + 代码校验/统计”。
- 参考案例库仍是可选增强；项目级 QA 知识库延期到 V2，后续需要单独设计数据模型、权限、审核和检索。

### 文档同步

- `CONTEXT.md`
- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现后端 API。
- 未运行测试；本次只更新需求和实施计划文档。

## 进度记录 2026-06-24 21:12

### 本次目标

罗列 `qa-case` 移植到当前产品 V1 时仍不实现的功能，并为后续升级记录扩展预留方向。

### 本次完成

- 在 `docs/specs/test-case-generation.md` 新增 `qa-case 移植 V1 不做清单`。
- 明确 V1 不移植 QA Workspace preflight/setup/profile/Git 护栏。
- 明确 V1 不创建 `tasks/<task>` 任务目录，不保存原始来源证据包。
- 明确 V1 不做 QA 知识库读取、草案、审核、发布、检索或知识沉淀。
- 明确 V1 不接 Jira、配置 SVN、服务器代码、Trino/Data MCP、多来源 context-reading。
- 明确 V1 不承接 `coupling-test-point-generation` 产物作为前置输入。
- 明确 V1 不做图片/附件视觉证据、权限申请、观察和校验流程。
- 明确 V1 不新建 AI-owned Feishu 表，不写回 Feishu，不输出 CSV/Markdown/Feishu 文本。
- 明确 V1 不做双层表头、模块行继承、执行版本/测试人员/设备矩阵等高级导出模板。
- 明确 V1 不做局部补充生成、澄清问题闭环、未映射需求复核工作台、外部系统只读验证和自动覆盖检查。
- 在实施计划中新增 `Deferred qa-case Migration Matrix`，把每个延期项对应的 V2 扩展方向写入计划。

### 当前项目进度

- V1 只保留 `qa-case` 的方法核心：策划案快照、蓝图先行、完整性矩阵、结构化用例、自检、warnings 和代码统计。
- 其余 QA Workspace 运行时、来源管理、知识管理、视觉证据和多格式交付能力全部进入 V2+ 扩展池。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/superpowers/plans/2026-06-22-test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现后端 API。
- 未运行测试；本次只更新需求和实施计划文档。

## 进度记录 2026-06-25 11:01

### 本次目标

阅读当前代码和文档，把用例生成 V1 的实现拆成可逐步交给 Codex 执行的提示词和推荐实施顺序。

### 本次完成

- 核对当前 V1 需求文档、实施计划、后端路由/模型/上传/Excel 读取/AI 调用入口和前端静态页面。
- 明确推荐实施顺序调整为先打通 01/02/04 无参考生成闭环，再接入 03 参考案例库增强。
- 新增 `docs/superpowers/plans/2026-06-25-test-case-generation-codex-prompts.md`，按 10 个可执行切片沉淀 Codex 提示词。
- 每个提示词都包含阅读范围、实现目标、建议文件、测试命令和 V1 约束。

### 当前项目进度

- V1 需求文档和原实施计划仍是源文档。
- 新增提示词文档作为执行入口，便于分会话或分阶段实施。
- 参考案例库继续保持可选增强，不阻塞无参考生成主链路。

### 文档同步

- `docs/superpowers/plans/2026-06-25-test-case-generation-codex-prompts.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现业务代码。
- 未运行测试；本次只新增执行提示词文档。

## 进度记录 2026-06-25 15:30

### 本次目标

确认是否完整迁移 QA Workspace 的飞书文档读取、图片/附件和视觉证据链路，以及来源证据是否允许短期保存。

### 本次完成

- 明确选择完整迁移方案，不只做飞书文档正文/表格文本读取。
- 明确新增 `Source Evidence Run` 作为 V2 级来源证据读取会话。
- 明确飞书文档、图片、附件和视觉证据包允许在当前项目服务器短期落盘保存。
- 明确来源证据按项目隔离，默认 7 天 TTL 自动清理。
- 明确 `Source Evidence Run` 不进入生成历史，也不等同于项目级 QA 知识库。
- 在 `CONTEXT.md` 增加 `Source Evidence Run` 术语。
- 在 `docs/specs/test-case-generation.md` 的 V2 候选、延期清单和 qa-case 移植矩阵中补充来源证据短期保存决策。

### 当前项目进度

- V1 已完成的用例生成主链路边界不变。
- 飞书完整读取能力进入 V2 设计范围，需要继续确认视觉模型、权限申请、证据清理和前端交互。

### 文档同步

- `CONTEXT.md`
- `docs/specs/test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现业务代码。
- 未运行测试；本次只更新领域术语和需求边界。

## 进度记录 2026-06-25 15:40

### 本次目标

确认 V2 飞书视觉证据链路是否复用现有项目级 AI 凭据，还是新增独立视觉模型凭据。

### 本次完成

- 明确新增独立的项目级 `Project Vision AI Credential`。
- 明确视觉理解不复用现有文本/结构化生成用的 `Project AI Credential`。
- 明确没有视觉凭据时，飞书正文/表格和证据包仍可读取或准备，但图片 observation 应进入待配置或不可用状态。
- 修正 `CONTEXT.md` 中 `Project AI Credential` “唯一 AI 凭据面”的旧表述，收窄为文本/结构化 AI 凭据。
- 在 `CONTEXT.md` 增加 `Project Vision AI Credential` 术语。
- 在 `docs/specs/test-case-generation.md` 的 V2 候选、延期清单和 qa-case 移植矩阵中补充独立视觉凭据决策。

### 当前项目进度

- V1 已实现链路继续使用现有项目级 AI 凭据。
- V2 飞书视觉证据链路需要独立设计视觉凭据配置、状态展示、权限、测试连接、模型能力校验、成本提示和不可用降级。

### 文档同步

- `CONTEXT.md`
- `docs/specs/test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现业务代码。
- 未运行测试；本次只更新领域术语和需求边界。

## 进度记录 2026-06-25 11:20

### 本次目标

开始实现用例生成 V1 的后端基础骨架，只新增领域包、共享契约和 `/api/v1/test-cases/*` 占位接口，不实现参考案例库数据库、不实现 AI 调用。

### 本次完成

- 新增 `backend/app/test_cases/` 领域包。
- 新增 `backend/app/test_cases/constants.py`，沉淀标准用例字段、中文字段名、V1 禁止公开传入的知识上下文字段和占位响应文案。
- 新增 `backend/app/test_cases/schemas.py`，定义策划案快照、生成请求/响应、导出请求、warnings、统计、需求追踪和 QA Case Method 上下文等 Pydantic 契约。
- 新增 `backend/app/api/test_cases_api.py`，注册 `POST /api/v1/test-cases/planning-snapshot`、`POST /api/v1/test-cases/generate`、`POST /api/v1/test-cases/export` 三个占位接口。
- 更新 `backend/app/api/router.py`，将用例生成 router 挂载到 `/api/v1` 聚合路由。
- 新增 `backend/tests/test_test_case_api_contracts.py`，先确认路由缺失红灯，再覆盖路由注册、登录校验、严格项目成员校验、501 占位响应和 `knowledge_context` 类字段拒绝规则。

### 当前项目进度

#### 已完成功能

- 用例生成 V1 需求文档、实施计划和 Codex 分步提示词已形成。
- 前端 `/test-cases` 静态页面、路由、导航和静态交互单测已存在。
- 后端用例生成基础 API 路由骨架已注册，后续切片可以在稳定路径和共享 schema 上继续实现。
- V1 公共请求禁止用户直接注入知识库上下文的规则已在接口入口建立测试保护。

#### 已实现但未打通/占位功能

- 三个用例生成接口当前只返回稳定 `501` 占位响应，尚未读取策划案、调用 AI 或生成导出文件。
- `backend/app/test_cases/schemas.py` 已定义共享契约，但后续服务实现仍需继续校准字段粒度。
- 前端静态页尚未接入真实后端 API。

#### 未开始功能

- 策划案快照读取。
- 无参考 AI 生成主链路。
- Excel 导出。
- 参考案例库数据模型、迁移、上传、画像和权限 API。
- 参考案例增强接入生成与导出。

### 规范化调整

- 新接口统一使用 `ctx.require_strict_project_member()`，避免 Token 指向非成员项目时静默回退。
- 新增请求模型默认拒绝未知字段，防止 V2 输入被 V1 误接入。
- 保持 `TaskTree`、个人校验、项目校验执行入口和统一结果结构不变。

### 文档同步

- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次只完成后端骨架，不代表用例生成业务可用。
- 占位接口后续实现时需要继续保持“不保存生成历史”“无参考生成优先”和“项目级 AI 凭据唯一入口”的约束。
- 参考案例库仍是可选增强，后续不要反向阻塞无参考生成闭环。

### 下一步建议

- 下一刀实现 `POST /api/v1/test-cases/planning-snapshot`，先支持上传 Excel 的单 Sheet 快照，再用可 monkeypatch 的方式接入飞书表格读取。

## 进度记录 2026-06-25 11:32

### 本次目标

实现用例生成 V1 的 Planning Sheet Snapshot：读取一个策划案 Sheet，返回页面可预览并可直接传入生成接口的快照；不保存快照历史，不实现 AI 调用。

### 本次完成

- 新增 `backend/app/test_cases/planning_snapshot.py`，实现上传 Excel 单 Sheet 快照读取、单元格文本规范化和行/列/非空单元格/单元格长度/总字符预算控制。
- `POST /api/v1/test-cases/planning-snapshot` 从 501 占位切换为真实快照响应，继续统一执行 `ctx.require_strict_project_member()`。
- 本地 Excel 复用 `local_reader` 的路径 allowlist、工作簿打开和 Sheet 名解析能力。
- 飞书读取通过 `read_feishu_planning_values()` 独立适配，复用现有飞书 Sheet 解析/授权链路，测试可 monkeypatch 外部读取。
- 所有快照固定返回 V1 未读取图片、附件、批注或评论语义的 warning；任何超限均以 warning 显式暴露，不静默截断。
- 继续保持快照接口 stateless，不创建 `ExecutionRunRecord` 等生成历史记录。
- 更新 `backend/tests/test_test_case_api_contracts.py`，保留 `generate/export` 的 501 骨架断言，避免把已实现的快照接口误判为占位。
- 新增 `backend/tests/test_test_case_planning_snapshot.py`，覆盖 Excel 指定 Sheet、空 Sheet、各类超限 warning、非法本地路径拒绝、无历史记录、飞书 monkeypatch 和飞书权限中文错误。

### 验证结果

- `python -m pytest backend/tests/test_test_case_planning_snapshot.py`
- `python -m pytest backend/tests/test_test_case_planning_snapshot.py backend/tests/test_source_api_security.py`
- `python -m pytest backend/tests/test_test_case_api_contracts.py`
- `python -m ruff check backend/app/api/test_cases_api.py backend/app/test_cases backend/tests/test_test_case_api_contracts.py backend/tests/test_test_case_planning_snapshot.py`

以上命令均通过；pytest 仅保留现有 `lark_oapi` 依赖的 2 条 deprecation warnings。

## 进度记录 2026-06-25 11:54

### 本次目标

实现用例生成 V1 的无参考 AI 生成主链路：按内置 `QA Case Method` 先生成蓝图，再生成用例，并返回完整性矩阵、需求追踪、warnings、代码统计和方法上下文；不接入参考案例库数据库。

### 本次完成

- 新增 `backend/app/test_cases/qa_case_method.py`，内置 `QA Case Method` 的蓝图维度、完整性矩阵、场景库、自检规则、warning 模板和 V1 知识库说明。
- 新增 `backend/app/test_cases/generation.py`，实现无参考生成编排：加载项目级 AI 凭据、两次调用 `call_provider_json`、校验蓝图和用例 JSON、合并 warnings、补齐缺失用例编号、生成需求追踪和代码统计。
- `POST /api/v1/test-cases/generate` 从 501 占位切换为真实生成接口；继续拒绝公共 `knowledge_context` 类字段。
- 项目级 AI 统一使用 `load_project_credential`、`decrypt_credential_key`、`parse_extra_headers`、`call_provider_json` 和 `sanitize_ai_error`，不新增个人 AI 或旁路配置。
- 未配置或禁用项目 AI 时返回中文配置错误；Provider 错误返回前会脱敏完整 API Key。
- 生成结果的 `stats.total`、`priority_counts`、`module_counts`、`case_type_counts` 和 `warning_count` 均由代码计算，不采信模型统计。
- 无参考场景下明确不自动选择最新参考案例；本刀不读取参考案例库表。
- 保持生成接口 stateless，不创建 `ExecutionRunRecord` 或生成历史记录。
- 更新 `backend/tests/test_test_case_api_contracts.py`，保留 `/export` 的 501 骨架断言，`/generate` 不再按占位接口校验。
- 新增 `backend/tests/test_test_case_generation.py`，覆盖项目 AI 缺失/禁用、Provider 成功两次调用、错误脱敏、无参考生成、代码统计、需求追踪、无历史记录和知识上下文拒绝。

### 验证结果

- `python -m pytest backend/tests/test_test_case_generation.py`
- `python -m pytest backend/tests/test_test_case_generation.py backend/tests/test_project_ai_config_api.py`
- `python -m pytest backend/tests/test_test_case_api_contracts.py backend/tests/test_test_case_planning_snapshot.py`
- `python -m ruff check backend/app/api/test_cases_api.py backend/app/test_cases backend/tests/test_test_case_api_contracts.py backend/tests/test_test_case_planning_snapshot.py backend/tests/test_test_case_generation.py`

以上命令均通过；pytest 仅保留现有 `lark_oapi` 依赖的 2 条 deprecation warnings。

### 未完成项与风险

- `/api/v1/test-cases/export` 仍是 501 占位。
- 参考案例库、主参考字段顺序、参考画像和导出增强仍未实现，后续不得反向阻塞无参考生成主链路。
- 当前生成质量依赖项目级 AI 返回的蓝图和用例内容；后续可继续增加更细的结构校验、去重和导出前校验。

## 进度记录 2026-06-25 12:06

### 本次目标

实现用例生成 V1 的 Excel 导出：完全基于当前页面提交的 `blueprint`、`cases`、`warnings`、`stats` 生成 xlsx 文件，不依赖生成历史。

### 本次完成

- 新增 `backend/app/test_cases/exporter.py`，使用 openpyxl 在内存中生成导出工作簿。
- `POST /api/v1/test-cases/export` 从 501 占位切换为 xlsx 文件响应，返回 `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` 和附件文件名。
- 导出文件包含 `测试用例`、`用例蓝图`、`生成说明` 三个 Sheet。
- 无主参考时使用 `STANDARD_CASE_FIELDS` 标准字段顺序和中文表头。
- 有 `primary_reference_profile` 时，只采用能映射到标准字段的主参考字段顺序，未知列丢弃，缺失标准字段追加兜底。
- `生成说明` 写入来源、导出字段、stats、warnings、V1 限制和安全说明。
- 导出器不写入完整 API Key、原始 prompt、原始 provider response 或隐藏敏感元数据。
- 保持导出接口 stateless，不创建 `ExecutionRunRecord` 或生成历史记录。
- 更新 `backend/tests/test_test_case_api_contracts.py`，移除已经失效的 501 占位断言。
- 新增 `backend/tests/test_test_case_exporter.py`，覆盖三个 Sheet、标准字段兜底、未知参考列忽略、图片/附件未读 warning、文件响应头和无历史持久化。

### 验证结果

- `python -m pytest backend/tests/test_test_case_exporter.py`
- `python -m pytest backend/tests/test_test_case_exporter.py backend/tests/test_test_case_api_contracts.py backend/tests/test_test_case_generation.py backend/tests/test_test_case_planning_snapshot.py`
- `python -m ruff check backend/app/api/test_cases_api.py backend/app/test_cases backend/tests/test_test_case_api_contracts.py backend/tests/test_test_case_planning_snapshot.py backend/tests/test_test_case_generation.py backend/tests/test_test_case_exporter.py`

以上命令均通过；pytest 仅保留现有 `lark_oapi` 依赖的 2 条 deprecation warnings。

### 未完成项与风险

- 参考案例库数据库、参考画像生成与真实主参考选择仍未实现；本次只消费页面传入的 `primary_reference_profile`。
- 前端仍未接入真实快照、生成和导出 API。

## 进度记录 2026-06-25 12:25

### 本次目标

实现用例生成 V1 的参考案例库服务和 API：分类、上传、列表、删除、推荐主参考和确定性画像；不调用 AI 做画像。

### 本次完成

- 新增 `test_case_reference_categories` 和 `test_case_reference_files` 两张表及迁移 `0010_test_case_reference_library.py`，按项目隔离分类和参考文件。
- 新增 `backend/app/test_cases/reference_profiles.py`，支持 `.xlsx/.xls/.md/.txt` 的确定性画像；Excel 读取所有 Sheet，识别可用 Sheet、默认 Sheet、标准字段映射和只读参考用例数量。
- 新增 `backend/app/test_cases/reference_library.py`，实现独立项目级存储目录 `runtime/test-case-references/{project_id}`，不复用普通上传目录。
- 接入参考案例库 API：分类创建/列表/重命名/删除、参考上传/列表/删除、设置推荐主参考。
- 普通项目成员可查看、创建分类和上传；重命名/删除分类、删除参考、设置推荐主参考要求项目管理员或超级管理员。
- 上传前校验项目、分类、后缀和 active 同名文件；同项目 + 同分类 + 同 original_filename 的 active 文件拒绝上传。
- 分类删除会把关联参考移到未分类，并清空推荐主参考标记。
- 推荐主参考按项目 + 分类唯一；`category_id = null` 的未分类范围独立处理。
- 参考删除先删除物理文件；文件缺失视为成功，IO/权限失败则保留 active 状态并返回错误；成功后清空 `storage_path`、`profile_json`、`is_recommended_primary`。
- 画像失败时拒绝上传、清理已保存文件且不创建数据库记录。
- JSON 与 multipart 公共请求都会拒绝 `knowledge_context` 或等价字段，避免 V1 接收用户注入知识库上下文。
- 新增 `backend/tests/test_test_case_reference_profiles.py` 和 `backend/tests/test_test_case_reference_library_api.py`，覆盖画像、权限、目录隔离、重名拒绝、推荐唯一性、删除语义和无历史记录。

### 验证结果

- `python -m pytest backend/tests/test_test_case_reference_profiles.py backend/tests/test_test_case_reference_library_api.py backend/tests/test_source_api_security.py`
- `python -m ruff check backend/app/test_cases/reference_profiles.py backend/app/test_cases/reference_library.py backend/app/api/test_cases_api.py backend/app/models.py backend/tests/test_test_case_reference_profiles.py backend/tests/test_test_case_reference_library_api.py migrations/versions/0010_test_case_reference_library.py`

以上命令均通过；pytest 仅保留现有 `lark_oapi` 依赖的 2 条 deprecation warnings。

### 未完成项与风险

- 前端尚未接入参考案例库 API。
- 生成链路尚未读取参考案例库和推荐主参考，只完成参考资产的后端管理能力。

## 进度记录 2026-06-25 12:37

### 本次目标

把参考案例库作为可选增强接入用例生成和导出；参考案例只影响字段顺序、层级、粒度、命名和历史风格，不作为需求来源，也不作为生成前置条件。

### 本次完成

- 新增生成链路参考选择解析：`reference_ids` 可为空，`primary_reference_id` 可为空，不会自动选择最新、第一条或推荐主参考。
- `primary_reference_id` 存在时必须属于 `reference_ids`，且必须是当前项目 active 参考案例；跨项目、已删除或不存在的参考会在 AI 调用前拒绝。
- Excel 主参考支持 `primary_reference_sheet_name`；未传时使用画像里的 `default_sheet_name`，传入时必须命中 `sheet_options`。
- Markdown/TXT 主参考不接受非空 Sheet 名。
- 生成 prompt 明确写入参考边界：参考案例不是需求来源，需求来源只能来自 `Planning Sheet Snapshot`。
- 生成响应返回 `primary_reference_profile` 和 `reference_context`，并按主参考选中 Sheet 的可识别字段生成 `export_columns`，缺失标准字段后置补齐。
- 导出器增强为可识别完整 Excel 主参考画像中的 `selected_sheet_name/sheet_options`，未知列继续忽略，缺失标准字段继续兜底。
- 补充生成测试，覆盖无参考、只有附加参考无主参考、主参考不在已选集合、跨项目参考拒绝、Excel Sheet 选择影响参考数量和导出列、Markdown/TXT Sheet 名拒绝。
- 补充导出测试，覆盖完整 Excel 画像按选中 Sheet 决定列序且未知列不导出。

### 验证结果

- `python -m pytest backend/tests/test_test_case_generation.py backend/tests/test_test_case_exporter.py backend/tests/test_test_case_reference_library_api.py`
- `python -m ruff check backend/app/test_cases/generation.py backend/app/test_cases/exporter.py backend/app/test_cases/reference_library.py backend/app/test_cases/schemas.py backend/app/api/test_cases_api.py backend/tests/test_test_case_generation.py backend/tests/test_test_case_exporter.py`

以上命令均通过；pytest 仅保留现有 `lark_oapi` 依赖的 2 条 deprecation warnings。

### 未完成项与风险

- 前端尚未把参考案例库选择、主参考 Sheet 和生成响应里的参考上下文接入页面状态。
- 生成仍不读取原始参考案例文件内容；本次只使用上传时保存的确定性画像。

## 进度记录 2026-06-25 13:24

### 本次目标

把静态 `TestCaseGeneratorView` 先接入真实用例生成 API，但只打通 01 数据源、02 生成输入、04 结果预览/导出；03 参考案例库保持静态，不阻塞无参考生成。

### 本次完成

- 新增 `frontend/src/types/testCases.ts`，按后端 V1 Pydantic 契约定义快照、生成、导出、warnings、stats、蓝图和用例行类型。
- 新增 `frontend/src/api/testCases.ts`，封装 `/api/v1/test-cases/planning-snapshot`、`/generate`、`/export`，导出使用 `apiDownloadFile` 发送当前页面内存结果。
- `TestCaseGeneratorView` 复用 `fetchSourceMetadata` 获取策划案来源 Sheet；上传来源仍通过现有 `DataSourcePanel` 复用 `uploadSourceFile`。
- 读取快照按钮接入真实 API，快照成功后展示 Sheet 文本快照，并清空旧生成结果。
- 生成按钮改为依赖当前 `planningSnapshot`，不依赖参考案例库；请求显式传空 `reference_ids` 和空主参考。
- 生成结果展示后端返回的蓝图、用例、warnings、stats 和导出列；warnings 预览合并顶层 warnings 与蓝图 warnings。
- 导出按钮基于当前页面内存中的 `blueprint/cases/warnings/stats/export_columns/source_summary` 调用导出 API，不读取或保存历史。
- 切换策划案来源或 Sheet 时清空快照和生成结果；页面不使用 `localStorage` 保存生成结果。
- 更新前端单测，覆盖快照前不可生成、无参考生成、结果渲染、导出 payload 和切换来源清空结果。

### 验证结果

- `npm run test:unit -- testCasesApi TestCaseGeneratorView`
- `npm run build`

以上命令均通过；build 仅保留现有 chunk size 和 plugin timing 警告。

### 未完成项与风险

- 03 参考案例库仍是静态/页面态数据，尚未接真实分类、上传、列表和主参考画像 API。
- 本次生成请求暂不传前端静态参考选择，符合“无参考不阻塞生成”的当前切片目标。

## 进度记录 2026-06-25 13:32

### 本次目标

实现用例生成 V1 的 03 参考案例库持久化结构和最小服务测试；只处理数据模型与迁移，不接前端。

### 本次完成

- 更新 `backend/app/models.py`，补齐 `TestCaseReferenceCategoryRecord` 和 `TestCaseReferenceFileRecord` 的持久化契约。
- 分类新增 `name_key`，由 ORM validator 从 `name.strip()` 同步，唯一索引改为 `project_id + name_key`，保证同项目内按 trim 后名称唯一。
- 参考文件继续支持 `category_id = null` 表示未分类；删除采用 `deleted_at/deleted_by` 软删除审计，`storage_path/profile_json/is_recommended_primary` 可在删除成功后清空。
- 更新 `migrations/versions/0010_test_case_reference_library.py`，创建参考分类和参考文件表，不新增生成历史表，不新增 `profile_status/profile_error` 半成品状态字段。
- 更新 `backend/app/test_cases/reference_library.py`，创建分类时写入 `name_key`，分类重名检查改为基于 trim 后键。
- 新增 `backend/tests/test_test_case_reference_models.py`，覆盖 trim 唯一、未分类软删除审计和禁止生成历史/画像半成品状态字段。
- 更新 `backend/tests/test_alembic_migrations.py`，将 Alembic head 推进到 `0010_test_case_reference_library`，并校验参考库表结构。

### 验证结果

- `python -m pytest backend/tests/test_test_case_reference_models.py backend/tests/test_alembic_migrations.py`
- `python -m pytest backend/tests/test_test_case_reference_library_api.py`
- `python -m ruff check backend/app/models.py backend/app/test_cases/reference_library.py migrations/versions/0010_test_case_reference_library.py backend/tests/test_test_case_reference_models.py backend/tests/test_alembic_migrations.py`

以上命令均通过；pytest 仅保留现有 `lark_oapi` 依赖的 2 条 deprecation warnings。

### 未完成项与风险

- 本次不接前端。
- 本次不新增生成历史表，也不新增参考画像异步状态字段；参考画像仍保持后续确定性解析切片处理。

## 进度记录 2026-06-25 13:42

### 本次目标

按 `2026-06-25-test-case-generation-codex-prompts.md` 的前八步执行顺序做复核与补正，重点处理 Prompt 5/6 实际在 Prompt 7/8 后执行造成的潜在问题。

### 本次完成

- 更新 `docs/superpowers/plans/2026-06-25-test-case-generation-codex-prompts.md`，明确前八步实际/补正执行顺序为 `1 → 2 → 3 → 4 → 7 → 8 → 5 → 6`，并在 Prompt 5/6/7/8 标题中标注执行顺序。
- 识别并修复一个真实顺序风险：旧版 `0010_test_case_reference_library` 已经在开发库落库但缺少 `name_key` 时，后续只修改同一个 0010 revision 不会被 Alembic 重放。
- 新增 `migrations/versions/0011_test_case_reference_category_name_key.py`，对旧 0010 库幂等补齐 `test_case_reference_categories.name_key` 和 `project_id + name_key` 唯一索引。
- 更新 `backend/tests/test_alembic_migrations.py`，新增旧 0010 漂移库迁移测试，并将 Alembic head 预期推进到 `0011_test_case_reference_category_name_key`。
- 重新回归前八步相关后端与前端测试，确认无参考生成、参考案例增强、导出、迁移、前端 01/02/04 接线没有因执行顺序产生回归。

### 验证结果

- `python -m pytest backend/tests/test_alembic_migrations.py::test_migrate_old_reference_library_revision_adds_category_name_key`：先红后绿，确认覆盖旧 0010 漂移。
- `python -m pytest backend/tests/test_alembic_migrations.py backend/tests/test_test_case_reference_models.py`
- `python -m pytest backend/tests/test_test_case_api_contracts.py backend/tests/test_test_case_planning_snapshot.py backend/tests/test_test_case_generation.py backend/tests/test_test_case_exporter.py backend/tests/test_test_case_reference_models.py backend/tests/test_test_case_reference_profiles.py backend/tests/test_test_case_reference_library_api.py backend/tests/test_project_ai_config_api.py backend/tests/test_source_api_security.py backend/tests/test_alembic_migrations.py`
- `python -m ruff check backend/tests/test_alembic_migrations.py migrations/versions/0011_test_case_reference_category_name_key.py docs/superpowers/plans/2026-06-25-test-case-generation-codex-prompts.md`
- `npm run test:unit -- testCasesApi TestCaseGeneratorView`
- `npm run build`

以上命令均通过；pytest 仅保留现有 `lark_oapi` 依赖的 2 条 deprecation warnings，前端 build 仅保留既有 chunk size/plugin timing 警告。

### 未完成项与风险

- 前端 03 参考案例库仍未接真实 API，后续应按补正后的 Prompt 9 执行。
- 既有开发库如果存在同项目内 trim 后重复的参考分类名，`0011` 创建唯一索引时仍会暴露数据冲突；当前服务入口会 trim 并拒绝同名，正常 API 路径不会产生这类重复。

## 进度记录 2026-06-25 14:00

### 本次目标

把 `TestCaseGeneratorView` 的 03 参考案例库从静态数据接到真实 API，并把 02 主参考设置和 04 导出字段增强接入同一套页面内存状态。

### 本次完成

- 补齐 `frontend/src/types/testCases.ts` 的参考案例分类、参考文件、画像、Sheet 选项、主参考画像和参考库 API 响应类型。
- 扩展 `frontend/src/api/testCases.ts`，封装参考分类列表/创建、参考文件列表/上传/删除、设置推荐主参考等真实后端接口。
- `TestCaseGeneratorView` 页面加载时读取项目参考案例分类和文件列表，合成 `category_id = null` 的“未分类”展示范围。
- 分类 pill 数量改为真实后端数量；切换分类会清空选择，仅当该分类有推荐主参考时默认勾选并设为主参考。
- 支持多选参考案例；手动设为主参考会自动勾选；取消勾选当前主参考时清空主参考且不自动改选。
- Excel 主参考按后端 `default_sheet_name` 默认选中并展示可选 Sheet；Markdown/TXT 主参考禁用 Sheet 选择。
- 参考用例数量来自当前主参考画像和选中 Sheet；未选择主参考显示“未使用主参考”。
- 生成请求改为传当前页面选中的 `reference_ids`、`primary_reference_id` 和 Excel 主参考 Sheet；无参考仍传空数组和 `null`。
- 导出继续完全基于当前页面内存生成结果，传递后端返回的 `export_columns` 和 `primary_reference_profile`。
- 新建分类、上传参考案例、删除参考案例、设置推荐主参考均调用真实 API；管理员动作以后端权限拒绝为准。
- 更新前端单测，覆盖参考库加载、分类数量、无推荐分类不自动选择、推荐主参考默认选择、多选、主参考 Sheet、上传、新建分类、管理员动作、生成请求参考参数和导出增强 payload。

### 验证结果

- `npm run test:unit -- testCasesApi TestCaseGeneratorView`
- `npm run build`

以上命令均通过；build 仅保留既有 chunk size 和 plugin timing 警告。

### 未完成项与风险

- 分类重命名/删除的前端入口仍未完整实现，当前更多操作只接入参考文件删除和设置推荐主参考。
- 前端只做弱交互和错误展示，普通成员是否可执行管理员动作完全以后端权限校验为准。

## 进度记录 2026-06-25 14:43

### 本次目标

对用例生成 V1 做最终验收、文档同步和风险清理，不新增新功能。

### 本次完成

- 按验收清单复核 V1 安全边界：不保存生成历史、无参考生成是一等路径、参考案例库只增强输出格式/粒度/历史风格、公共请求拒绝 `knowledge_context` 等知识上下文字段。
- 复核图片/附件未读限制：策划案快照固定返回“未读取图片、附件、批注或评论语义” warning，生成 prompt 和导出说明会保留相关 warnings/备注。
- 复核 Excel 导出：导出文件包含 `测试用例`、`用例蓝图`、`生成说明` 三个 Sheet，并且导出只基于当前页面提交的结果，不依赖历史记录。
- 复核前端刷新行为：生成结果只存在于组件内存状态，页面不使用 `localStorage` 或 `sessionStorage` 保存生成结果，刷新不会恢复上次生成结果。
- 清理一个验收风险：参考选择、主参考或主参考 Sheet 变更后，页面已有生成结果会标记失效，并禁用旧结果导出，要求重新生成后再导出。
- 同步 `docs/specs/test-case-generation.md`，将状态从“静态页/后端待实现”更新为 V1 主链路已实现，并同步参考变更后结果失效与禁用导出的行为。
- 同步 `CHANGELOG.md`，记录“用例生成”V1 用户可见主链路已交付，并修正旧静态页口径。

### 验证结果

- `python -m pytest backend/tests/test_test_case_api_contracts.py backend/tests/test_test_case_planning_snapshot.py backend/tests/test_test_case_generation.py backend/tests/test_test_case_exporter.py backend/tests/test_test_case_reference_models.py backend/tests/test_test_case_reference_profiles.py backend/tests/test_test_case_reference_library_api.py backend/tests/test_project_ai_config_api.py backend/tests/test_source_api_security.py backend/tests/test_alembic_migrations.py`
- `npm run test:unit -- testCasesApi TestCaseGeneratorView`
- `npm run build`

以上命令均通过；后端 pytest 为 70 passed，仅保留现有 `lark_oapi` 依赖的 2 条 deprecation warnings；前端单测为 31 passed，build 仅保留既有 chunk size/plugin timing 警告。

### 未完成项与风险

- 分类重命名和删除分类的前端入口仍未完整接入；后端 API 和权限校验已存在。
- V1 仍不读取图片、附件、批注或评论语义；该限制已在 warnings/备注路径可见。
- V1 不保存生成历史，后续如引入历史留存，需要重新设计策划案快照、AI 响应、导出文件和参考上下文的存储/清理/权限边界。

## 进度记录 2026-06-25 15:52

### 本次目标

确认 V2 飞书视觉证据链路在没有 Vision AI 凭据或视觉模型不可用时是否阻断生成流程。

### 本次完成

- 明确允许继续读取飞书正文、表格和资源清单。
- 明确图片、原型图和附件降级为“待观察图片/附件”，不参与语义生成。
- 明确页面和导出说明需要提示“视觉模型未配置，图片/附件未参与语义理解”或等价 warning。
- 明确同一个未过期 `Source Evidence Run` 可以在后续配置 Vision AI 后重新执行 observation。
- 在 `docs/specs/test-case-generation.md` 的 V2 候选、延期清单和 qa-case 移植矩阵中补充该降级策略。

### 当前项目进度

- V1 已完成链路不变。
- V2 飞书完整读取链路的 Vision 不可用分支已收口为“文本/表格 + 资源清单 + 待观察图片/附件”。

### 文档同步

- `docs/specs/test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现业务代码。
- 未运行测试；本次只更新需求边界和项目记录。

## 进度记录 2026-06-25 15:55

### 本次目标

确认 V2 `Source Evidence Run` 读取飞书文档、图片和附件时使用项目级服务身份，还是当前登录用户个人 OAuth 身份。

### 本次完成

- 明确采用项目级 `Project Feishu Service Identity` 作为服务端长期读取主体。
- 明确当前登录用户只触发读取、授权申请或重试，不保存个人 OAuth token 作为长期读取凭据。
- 明确不把 QA Workspace 的本机个人 user token 模式直接迁移到当前多用户 Web 项目。
- 明确权限不足时记录待授权资源，并通过项目级机器人/授权卡片方向申请给 App/Bot 可读取权限。
- 在 `CONTEXT.md` 增加 `Project Feishu Service Identity` 术语。
- 在 `docs/specs/feishu-integration.md` 和 `docs/specs/test-case-generation.md` 同步授权主体边界。

### 当前项目进度

- V2 飞书完整读取链路的身份边界已收口：按项目隔离、可重试、可审计，不依赖个人用户长期 token。
- 后续仍需确认资源观察范围、权限申请交互和 Source Evidence Run 的清理任务细节。

### 文档同步

- `CONTEXT.md`
- `docs/specs/feishu-integration.md`
- `docs/specs/test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现业务代码。
- 未运行测试；本次只更新领域术语、需求边界和项目记录。

## 进度记录 2026-06-25 20:10

### 本次目标

在用例生成 V1 主链路已开发完成的基础上，整理 `qa-case` 飞书文档读取能力移植到当前项目的需求方案文档。

### 本次完成

- 新增 `docs/specs/test-case-generation-feishu-doc-migration.md`，作为用例生成飞书文档读取移植的专项方案。
- 明确方案不是重写 V1，而是在 V1 之后新增 `Source Evidence Run`、飞书文档富读取、资源清单、视觉证据、TTL 清理和 Project Vision AI Credential。
- 将前面对话中已确认的策略写入方案：来源证据默认 7 天 TTL、到期删除原文/图片/附件/视觉包/observation 详情、最小审计元数据按项目审计策略保留、Vision AI 独立配置、Vision 不可用时降级继续、observation 需用户采纳后才进入生成依据。
- 对照 QA Workspace 的 `context-reading`、`rich_reader`、`docx_blocks`、`visual` 和 `source_guard`，明确只迁移读取方法和证据边界，不迁移 CLI、本地任务目录、个人 token cache、preflight 或知识库维护流。
- 更新 `docs/specs/README.md`，新增飞书文档读取移植方案入口，并修正用例生成 V1 状态。
- 更新 `docs/MODULES.md`，补充 `/test-cases` 路由和用例生成业务切片定位。

### 当前项目进度

- 用例生成 V1 主链路继续保持当前实现边界。
- 飞书文档富读取已经形成可开发的专项方案，后续可按“数据模型与 TTL → Feishu rich reader adapter → Source Evidence API → 文本/表格生成闭环 → Vision 观察与采纳 → 前端接入”推进。

### 文档同步

- `docs/specs/test-case-generation-feishu-doc-migration.md`
- `docs/specs/README.md`
- `docs/MODULES.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现业务代码。
- 本次未运行测试；改动仅为文档和索引。
- 后续实现时需要重点验证飞书 DOCX blocks、资源下载权限、TTL 清理和 adopted visual evidence 不自动污染生成依据。

## 进度记录 2026-06-25 20:43

### 本次目标

确认 V2 `Source Evidence Run` 默认 7 天 TTL 到期后的证据清理策略，以及 `Adopted Visual Evidence` 在页面和导出中的可复查边界。

### 本次完成

- 明确默认 7 天 TTL 到期后删除原文快照、图片/附件文件、视觉证据包和 observation 详情。
- 明确 TTL 到期后只保留最小审计元数据，例如 run id、项目、来源标识、资源文件名、状态、操作人、创建时间和清理时间。
- 明确最小审计元数据不随 7 天 TTL 删除，按项目审计数据保留策略保留。
- 明确 V2 不提供项目级审计保留独立配置页；只有超级管理员可配置全局默认值，项目管理员只能查看。
- 明确项目管理员可查看本项目的清理记录摘要，但不能查看已清理内容、视觉证据包或 observation 明细。
- 明确清理记录摘要字段限定为 run id、来源标识、资源文件名、状态、创建时间、清理时间和操作人。
- 明确普通项目成员不能查看项目级清理记录列表，只能在自己当前页面遇到过期证据时看到“证据已清理/需重新读取来源”的状态提示。
- 明确页面和导出文件在 TTL 内可以引用 `Adopted Visual Evidence` 做证据复查。
- 明确 TTL 到期后不再提供证据复查或 observation 明细查看，用户需要重新读取来源。
- 明确 TTL 清理触发采用“后台定时清理 + 访问时懒清理”双保险，避免定时任务延迟导致过期证据继续可见。
- 明确该策略仍符合“不做生成历史”和“敏感策划案短期保存”的边界。
- 更新 `docs/specs/test-case-generation.md` 的 V2 候选、V1 延期清单和 qa-case 移植矩阵。
- 更新 `docs/specs/admin-auth-projects.md`，记录项目审计数据保留策略的超级管理员配置边界。
- 更新 `CONTEXT.md`，增加 `Source Evidence Cleanup Audit Summary` 术语。
- 更新 `CHANGELOG.md` 记录本次需求文档口径变化。

### 当前项目进度

- V2 飞书完整读取链路的证据留存边界已进一步收口。
- 后续实现 `Source Evidence Run` 时，需要把后台定时清理、访问时懒清理、审计元数据模型、超级管理员全局默认配置、项目管理员清理记录摘要查看、普通成员过期状态提示、页面过期状态和导出引用失效策略作为同一切片设计。

### 文档同步

- `docs/specs/test-case-generation.md`
- `docs/specs/admin-auth-projects.md`
- `CONTEXT.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现业务代码。
- 未运行测试；本次只更新需求文档和项目记录。

## 进度记录 2026-06-25 20:00

### 本次目标

根据确认结果取消用例生成结果预览中的“原始表格/追踪视图”和“用例蓝图”前端常驻展示，同时保留后端快照、蓝图协议和 Excel 导出能力。

### 本次完成

- 将 `TestCaseGeneratorView.vue` 的预览页签收口为 `AI 整理稿`、`测试用例`、`限制提示`。
- 移除前端原始快照表格页签、蓝图片签和下方用例蓝图摘要区。
- 将生成完成状态文案从“蓝图已生成”调整为“用例已生成”，避免取消蓝图展示后造成理解偏差。
- 保留整理稿失败时的快照摘要提示，未改动后端 `Planning Sheet Snapshot`、`Test Case Blueprint` 和 Excel `用例蓝图` 导出数据。
- 更新 `docs/specs/test-case-generation.md`，明确蓝图是后端中间结果和导出审计数据，不是 V1 常驻前端页签。
- 更新 `CHANGELOG.md` 记录本次前端体验变更。

### 验证记录

- `npm run test:unit -- TestCaseGeneratorView` 通过，34 个用例全部通过。
- `npm run build` 通过，`vue-tsc` 与 Vite 构建均成功。
- `git diff --check -- frontend/src/views/TestCaseGeneratorView.vue frontend/tests/unit/TestCaseGeneratorView.test.ts docs/specs/test-case-generation.md CHANGELOG.md PROJECT_RECORD.md` 通过，仅出现现有 CRLF 提示。

### 当前项目进度

- 用例生成 V1 前端结果区已按当前产品决策收口，页面阅读负担降低。
- 后端仍保留快照和蓝图结构，后续 V2 若要做证据追踪、复核工作台或蓝图确认，不需要重建生成协议。

### 文档同步

- `docs/specs/test-case-generation.md`
- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未调整后端导出和生成协议。
- 未做浏览器截图验证；本次通过组件单测和生产构建验证前端行为与模板类型。

## 进度记录 2026-06-25 19:07

### 本次目标

继续定位并修复用例生成页面“AI 用例返回结构不符合用例生成契约：Input should be a valid string”的失败。

### 本次完成

- 使用当前项目 1 的项目级 AI 凭据和已上传 Excel `3d24a9f317364891b886a0e65d2a8d1b_upload.xlsx` 的 `详案` Sheet 真实调用生成链路。
- 确认真实快照为 116 行、23 列、124 个非空单元格。
- 截获真实 provider 返回并确认根因：`cases[*].steps` 返回为字符串数组，而 `GeneratedTestCase.steps` 契约要求字符串。
- 同时发现真实返回里 `requirement_trace` 可能出现两类非契约形态：使用 `requirement_id/cases` 别名，或直接返回 `null`。
- 在 `backend/app/test_cases/generation.py` 中补齐用例阶段归一化：
  - `steps`、`expected_results` 等用例字符串字段若为数组，按换行合并。
  - 数值型文本字段转为字符串。
  - `requirement_trace` 的 `requirement_id/cases` 归一化为当前 `RequirementTrace` 结构。
  - `requirement_trace: null` 归一化为空列表，并继续由后端已有逻辑按用例行补 trace。
- 在用例阶段 prompt 中补充“多步骤使用换行字符串”约束，降低 provider 再次返回数组的概率。
- 新增回归测试：
  - `test_generation_normalizes_provider_case_lists_and_trace_aliases`
  - `test_generation_normalizes_null_requirement_trace_to_empty_list`
- 更新 `CHANGELOG.md` 修复记录。

### 验证结果

- `python -m pytest backend/tests/test_test_case_generation.py::test_generation_normalizes_provider_case_lists_and_trace_aliases -q`：先红后绿。
- `python -m pytest backend/tests/test_test_case_generation.py::test_generation_normalizes_null_requirement_trace_to_empty_list -q`：先红后绿。
- `python -m pytest backend/tests/test_test_case_generation.py -q`
- `python -m ruff check backend/app/test_cases/generation.py backend/tests/test_test_case_generation.py`
- 使用当前项目真实 AI 和同一份 `详案` 快照运行生成调试脚本，生成 16 条用例、5 条 warning、12 条 trace，`steps` 已为字符串，不再触发契约错误。

以上命令均通过；pytest 仅保留现有 `lark_oapi` 依赖的 2 条 deprecation warnings。

### 当前项目进度

- 用例生成主链路已兼容本次真实 provider 返回的常见形态，不再因步骤数组或空 trace 直接失败。

### 文档同步

- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 如果后续 provider 在其它字段返回全新结构，仍可能触发 502；当前策略是只归一化已验证的常见形态，避免静默吞掉真正错误。
- 本次真实 AI 调试会消耗一次项目 AI 调用额度。

## 进度记录 2026-06-25 18:18

### 本次目标

定位并修复用例生成页面“AI 蓝图返回结构不符合用例生成契约：Input should be a valid dictionary or instance of GenerationWarning”的失败。

### 本次完成

- 使用当前项目已上传的 `3d24a9f317364891b886a0e65d2a8d1b_upload.xlsx`，读取 `详案` Sheet 构造真实 `Planning Sheet Snapshot`，确认快照为 116 行、23 列、124 个非空单元格。
- 用该真实快照和模拟 provider 返回复现同一错误：蓝图阶段返回 `warnings: ["..."]` 时，`TestCaseBlueprint.warnings` 直接按 `GenerationWarning` 校验失败。
- 确认根因不是 Excel 快照内容，而是生成链路缺少 provider warning 字符串归一化；`snapshot_brief` 已有类似兼容逻辑，`generation` 没有。
- 在 `backend/app/test_cases/generation.py` 新增 `_normalize_provider_warnings()`，蓝图阶段默认归一化为 `source=blueprint`，用例阶段默认归一化为 `source=cases`。
- 新增回归测试 `test_generation_normalizes_provider_warning_strings`，覆盖蓝图和用例两个阶段的字符串 warnings。
- 同步 `CHANGELOG.md` 修复记录。

### 验证结果

- `python -m pytest backend/tests/test_test_case_generation.py::test_generation_normalizes_provider_warning_strings -q`：先红后绿，红时复现截图中的 502。
- `python -m pytest backend/tests/test_test_case_generation.py -q`
- `python -m ruff check backend/app/test_cases/generation.py backend/tests/test_test_case_generation.py`
- 使用项目已上传 Excel `详案` 快照运行调试脚本，确认同类 provider 返回已归一化为 `snapshot / blueprint / cases` 三类 warning，不再触发蓝图契约错误。

以上命令均通过；pytest 仅保留现有 `lark_oapi` 依赖的 2 条 deprecation warnings。

### 当前项目进度

- 用例生成主链路对 provider 字符串 warnings 更稳健，页面不应再因这一类蓝图 warnings 直接失败。

### 文档同步

- `CHANGELOG.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未调用真实 AI 生成完整用例，只用当前项目真实上传快照和模拟 provider 返回验证了失败形态。
- 如果 provider 在其它字段返回非契约结构，仍会按现有策略返回 502，避免静默吞掉真正结构错误。

## 进度记录 2026-06-25 16:10

### 本次目标

确认 V2 图片/附件 observation 完成后，视觉语义是否自动进入用例生成依据。

### 本次完成

- 明确 observation 结果不自动进入生成依据。
- 明确 observation 完成后先展示模型观察结果、关联资源、来源位置和风险提示。
- 明确用户确认采纳后才形成 `Adopted Visual Evidence`，并进入生成上下文、蓝图和用例追踪。
- 明确已观察但未采纳的资源可以保留在 `Source Evidence Run` 中用于复核，但不得影响本次生成。
- 在 `CONTEXT.md` 增加 `Adopted Visual Evidence` 术语。
- 在 `docs/specs/test-case-generation.md` 的 V2 候选、延期清单和 qa-case 移植矩阵中补充视觉证据采纳策略。

### 当前项目进度

- V2 飞书完整读取链路已经区分“已观察”和“已采纳”，降低视觉模型误读直接放大为测试用例的风险。
- 后续仍需确认 Source Evidence Run 到期清理时，已采纳视觉证据的引用和导出备注如何处理。

### 文档同步

- `CONTEXT.md`
- `docs/specs/test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现业务代码。
- 未运行测试；本次只更新领域术语、需求边界和项目记录。

## 进度记录 2026-06-25 16:07

### 本次目标

确认 V2 图片/附件视觉 observation 是默认全量执行，还是先出资源清单后选择性观察。

### 本次完成

- 明确采用“资源清单先出 + 系统推荐观察 + 用户可调整”的混合模式。
- 明确不默认全量观察所有图片或附件。
- 明确系统推荐依据包括文档位置、文件类型、文件名、附近文本、重复度和预算。
- 明确用户可增删观察集合，只有被观察且校验通过的资源可作为图片语义依据。
- 明确未选择或未观察的图片/附件继续保持“待观察”。
- 在 `CONTEXT.md` 增加 `Visual Observation Selection` 术语。
- 在 `docs/specs/test-case-generation.md` 的 V2 候选、延期清单和 qa-case 移植矩阵中补充视觉观察选择策略。

### 当前项目进度

- V2 飞书完整读取链路的视觉成本和依据边界已进一步收口。
- 后续仍需确认 observation 结果是否自动参与生成，还是需要用户确认后才进入生成依据。

### 文档同步

- `CONTEXT.md`
- `docs/specs/test-case-generation.md`
- `PROJECT_RECORD.md`

### 未完成项与风险

- 本次未实现业务代码。
- 未运行测试；本次只更新领域术语、需求边界和项目记录。
