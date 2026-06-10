# 项目进度记录

本文档记录当前活动执行进度。2026-04-20 之前的旧分钟级记录已归档到 [docs/archive/PROJECT_RECORD.md](docs/archive/PROJECT_RECORD.md)。

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
