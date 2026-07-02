# 更新日志

本日志按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 风格维护，记录版本级变化，不记录分钟级流水。

- 当前活动进度记录：[PROJECT_RECORD.md](PROJECT_RECORD.md)
- 历史分钟级日记：[docs/archive/PROJECT_RECORD.md](docs/archive/PROJECT_RECORD.md)
- 本次文档精简前的长篇 `[Unreleased]` 明细快照：[docs/archive/changelog-unreleased-before-doc-cleanup-2026-05-19.md](docs/archive/changelog-unreleased-before-doc-cleanup-2026-05-19.md)

## [Unreleased]

### 交付能力

- 新增项目级“用例生成”V1 主链路：支持策划案快照读取、无参考 AI 生成、参考案例库可选增强、Excel 导出和刷新不恢复生成结果；生成历史不落库。
- 新增干净源码交付包脚本和发布包检查脚本，源码 zip 会排除 `.git/`、依赖目录、前端构建产物、runtime 数据、E2E runtime、数据库、日志、SVN 缓存、密钥和本地凭据文件，并在生成后自动复核 zip 内容。

### 开发流程

- 新增 GitHub Actions 基础 CI，push、pull request 和手动触发会执行后端 ruff/pytest、前端 `npm ci`、lint、单元测试和构建；手动触发时可额外运行 Playwright E2E 冒烟测试。
- 从 Git 跟踪中移除根目录 `node_modules`，源码仓库和交付包均不再依赖已存在的依赖目录。
- 后端依赖新增 `backend/requirements.in` 直接依赖清单，`backend/requirements.txt` 改为 `pip-compile` 生成的锁定依赖文件。
- 新增跨平台 `scripts/check-standards.py`，并由 `scripts/check-standards.ps1` 包装调用，统一执行后端依赖安装、ruff、pytest、前端 `npm ci`、lint、单元测试和构建。
- 前端开发和构建文档统一使用 `npm ci`，源码交付包继续不包含 `node_modules`、`.venv` 和 `frontend/dist`。
- 新增 Playwright 端到端冒烟测试入口 `npm run e2e`，覆盖默认登录、Excel 上传、个人非空规则执行、导入项目校验和项目校验执行闭环，失败时保留截图、trace 和视频。

### 文档治理

- 新增并持续同步 `docs/specs/test-case-generation.md` 和 `docs/assets/test-case-generation-ui-v1.png`，形成“用例生成”V1 需求文档与页面 UI 方向图，覆盖独立页面、项目级参考案例库、策划案快照、项目级 AI 生成、Excel 导出、权限、安全和验收标准。
- 细化用例生成 V2 `Source Evidence Run` 证据留存策略：默认 7 天 TTL，到期删除原文、图片/附件、视觉包和 observation 详情；最小审计元数据不随 7 天 TTL 删除，按项目审计数据保留策略保留；V2 不做独立项目配置页，只有超级管理员可配置全局默认值，项目管理员只读查看本项目清理记录摘要，普通项目成员只能在当前页面看到证据过期状态提示；清理触发采用后台定时清理和访问时懒清理双保险，TTL 后不再提供证据复查。
- 新增 `docs/specs/` 业务能力 Spec 体系，按 10 个粗模块覆盖前端、后端、数据、API、测试和限制；`docs/MODULES.md` 与 `docs/STANDARDS.md` 明确开发前先读对应 Spec，README 仅保留入口链接。
- 同步统一项目级 AI 凭据的最终设计文档，删除活跃文档中个人 AI 配置和智能添加规则旧口径，并新增 ADR 记录该架构决策。
- 同步稳定文档和系统使用说明，补充个人校验 03 页签 `IAP礼包校验` 的预览、保存、执行和结果说明，并修正飞书数据源旧状态表述。
- 重新按当前代码梳理稳定文档，修正飞书数据源、飞书机器人授权、用户指南、结果导出和当前进度记录入口的说明。
- 新增当前活动进度记录 `PROJECT_RECORD.md`，旧分钟级进度继续保留在 `docs/archive/PROJECT_RECORD.md` 作为历史归档。
- 早前二次精简稳定文档：当时保留 6 份入口并压缩重复段落，明确 README、架构、模块、规范、前端说明和更新日志的职责边界，并修正个人规则导入项目校验的当前 API 路径。
- 早前精简文档入口：`README.md`、`docs/ARCHITECTURE.md`、`docs/MODULES.md`、`docs/STANDARDS.md`、`frontend/README.md` 与本文件成为当前说明主入口。
- 压缩 README、架构、模块和前端说明中的重复段落，将历史需求、分钟级进度、一次性重构方案和长篇变更流水收口到 `docs/archive/`。

### 规则与执行能力

- 新增执行链路任务化第一阶段接口 `POST /api/v1/execute-runs`、`GET /api/v1/execute-runs/{run_id}` 和 `GET /api/v1/execute-runs/{run_id}/items`，支持个人校验和项目校验通过进程内后台任务执行；原同步执行接口保持兼容。
- 个人校验与项目校验规则弹窗统一支持 5 类入口：单一变量校验、组合分支校验、跨组变量校验、多组串行校验、多组映射校验。
- 当前规则库覆盖 11 类规则：非空、唯一、固定值、正则、顺序、跨表映射、组合分支、双组比较、多组串行、多组映射、IAP 礼包校验。
- `package_items_compare` 支持从飞书礼包规划 Sheet 解析礼包明细，并与礼包配置组合变量中的 `STR_Items` 按礼包 ID、道具 ID 和数量做无序比对。
- 组合分支、跨组比较、多组串行/映射持续补齐筛选、断言、结果显示字段、规则集、Key 后追加序号等能力，并保持个人校验与项目校验共用执行引擎。

### 数据源与部署

- 新增 Alembic 正式数据库迁移机制，FastAPI 启动时自动升级到 head；旧 SQLite 库缺失的历史字段和飞书 app_id partial unique index 改由 migration 补齐。
- CSV 数据源入口已下线，历史 CSV 配置提示改用 Excel、SVN Excel 或飞书电子表格。
- 本地 Excel、浏览器上传 Excel、SVN Excel、飞书电子表格统一接入变量池、元数据读取、列预览和执行链路。
- 数据源 metadata、列预览、组合变量预览、本地目录校验、本地文件选择、上传和 SVN 相关接口要求登录并校验当前项目；本地 Excel 路径读取新增服务端 allowlist，`local-pick` 默认关闭，避免匿名探测服务端路径。
- 新增 `APP_ENV` 与 production 启动安全校验，生产模式要求显式配置 JWT 密钥、默认管理员密码、CORS 来源和 SVN host 白名单，并禁止默认管理员密码 `123456` 与 CORS `*`。
- 飞书电子表格支持项目机器人配置、权限检测、群授权卡片、OAuth 回调追加只读协作者和授权记录复用；多维表格与文档表格仍不支持。
- SVN HTTP 数据源支持目录浏览、凭据加密、缓存刷新、个人校验和项目校验更新；鉴权失败使用 HTTP 403，避免误触登录态过期。
- 本机共享部署支持前端构建后由 FastAPI 单服务托管，并通过环境变量配置监听地址、端口、CORS、上传大小、JWT 密钥和默认管理员密码。

### 前端与体验

- 新增 `/test-cases`“用例生成”页面，接入左侧导航、路由和预加载；页面现已接入真实策划案快照、生成、导出和参考案例库 API。
- 全站前端样式进一步对齐个人/项目校验页：收敛旧毛玻璃和负字距装饰，统一按钮、弹窗、表单、流程节点和指标图标的显示质感，并补齐关键表单与装饰图标的可访问性属性。
- 全站前端字体入口统一为共享正文与等宽字体 token，Element Plus、Tailwind、工作台页面、用例生成页和管理后台局部样式不再各自维护独立字体栈。
- `/test-cases` 按最新设计图完成贴合验收：01 数据源三种来源态、02 当前来源跟随、03 Excel-only 参考案例库和 04 结果预览保持同一工作台结构，并继续避免展示完整 URL、token、open_id、Authorization、Bearer 或原始 prompt。
- “用例生成”页面接入 Source Evidence Run：01 数据源新增飞书文档 URL 短期入口，支持读取富文档 snapshot、展示证据状态和资源清单抽屉，并在生成/导出时携带受控证据 run id；旧 Excel 与飞书电子表格单 Sheet 快照路径保持不变。
- “用例生成”页面将本地文件、SVN 文件和飞书文档三入口统一到 Source Evidence Run：本地上传 `.xlsx/.xls/.png/.jpg/.jpeg/.webp` 直接创建 `local_file` run，SVN 文件 URL 创建 `svn_file` run，三者共用状态卡、TTL、warnings、资源清单、视觉观察/采纳、snapshot、生成和导出链路；本地/SVN V2 不再走旧 `uploaded_excel/planning-snapshot` 主链路。
- “用例生成”页面新增 Source Evidence 运行能力状态提示：展示项目级 SVN 凭据、Source Evidence SVN Root、Vision AI 和 LibreOffice/soffice 可用性；SVN 运行能力缺失时禁用 SVN 文件读取，Vision 未配置时提示图片不会参与语义理解但不阻断文本/表格生成。
- 修复 Source Evidence 运行能力状态在 Windows 本地配置 LibreOffice/soffice 后仍显示未配置的问题，并避免 Vision AI 最近测试已成功时继续展示历史失败摘要。
- 修复 Source Evidence 大型本地工作簿生成用例不稳定的问题：生成 prompt 现在按预算截断超大 snapshot 并返回 warning，同时兼容模型把蓝图列表字段返回为对象映射的常见形态。
- 修复 Source Evidence 生成时模型将蓝图 warnings 返回为 `{id, description}` 导致 “Field required” 的问题，后端现在会归一化为稳定的 `{source, level, message}` warning 契约。
- 管理后台新增 Source Evidence 运行配置卡：项目管理员可维护 Source Evidence SVN Root，并配置、测试或清除 Project Vision AI Credential，避免生成页提示用户去 `/admin` 后找不到对应入口。
- 管理后台 Project Vision AI Credential 表单改为只推荐明确的 OpenAI-compatible 视觉模型入口，并对已保存的 DeepSeek、`qwen-plus`、`qwen3.6-plus`、`glm-5.2` 等文本 provider/model 给出风险提示，避免文本模型被误当作 Source Evidence 图片 observation 模型。
- 项目级 AI 配置按通义千问百炼和智谱最新 API 文档更新默认值：通义千问文本默认 `qwen3.6-plus`，智谱文本默认 `glm-5.2`；Vision 推荐新增 Qwen `qwen3.7-plus` 和智谱 `glm-5v-turbo`。
- “用例生成”页面接入并验收 Source Evidence 授权申请：权限不足或资源下载失败时可显式发送授权卡，等待授权/已授权/发送失败/过期清理等状态会在当前 Source Evidence 状态区提示，并继续避免展示完整 URL、文档 token、文件 token 或 open_id 明细。
- “用例生成”页面的 Source Evidence 资源抽屉新增 Vision observation 与采纳/撤销采纳流程；已观察未采纳不进入生成，生成/导出只携带已采纳视觉证据。
- “用例生成”页面的生成设置支持主参考 Sheet 选择框；Excel 参考案例按 Sheet 保存画像，Markdown/TXT 参考案例显示无 Sheet 禁用态。
- “用例生成”页面新增页面态 01 数据源模块，复用个人校验数据源添加体验，并将原策划案来源卡片调整为来源与 Sheet 选择区。
- “用例生成”页面完善参考案例库交互：分类作为本次生成范围，支持多选参考案例、唯一主参考、推荐主参考默认选中、无推荐分类空选择、搜索筛选排序和分页浏览。
- “用例生成”页面将参考案例库从左侧生成输入区拆出为全宽独立模块，文件行在桌面端横向展开展示，避免案例库被窄栏挤压。
- “用例生成”页面将生成输入和预览区也调整为全宽独立模块，形成数据源、生成输入、参考案例库、预览区纵向工作台布局。
- 压缩“用例生成”页面纵向模块高度，并修正底部预览区被内部限高裁切的问题，改由页面主滚动完整展示预览内容。
- 在不调整布局结构的前提下优化“用例生成”页面视觉显示，统一面板质感、参考案例行状态、表单控件和预览表格的扫描层级。
- “用例生成”页面参考案例库改为每页 5 条分页展示，改善文件数量较多时的拥挤显示。
- “用例生成”页面移除顶部重复上传参考案例入口，并将生成用例、导出 Excel 收拢到预览区顶部操作栏。
- “用例生成”页面进一步收敛工作台文案和视觉层级，降低面板阴影与拥挤感，优化指标、输入、参考库和预览区的简洁度。
- “用例生成”页面为生成输入、参考案例库和结果预览补齐 02/03/04 模块编号，并统一流程型说明文案。
- “用例生成”页面在参考选择、主参考或主参考 Sheet 变更后标记结果失效，并禁用旧结果导出，要求重新生成。
- “用例生成”结果预览移除原始表格/追踪视图和用例蓝图常驻页签，前端聚焦 AI 整理稿、测试用例和限制提示，后端蓝图与 Excel 导出仍保留。
- 整理前端全局样式层级，新增运行时 CSS token 文件和 Element Plus 覆盖文件，降低共享样式、页面域样式和组件局部覆盖之间的冲突风险。
- 新增前端样式规范文档，明确颜色、间距、表格、卡片、表单、弹窗和 `!important` 使用边界。
- 全站页面统一到 SaaS 工作台视觉：共享 shell 组件、分区标题、指标卡、表格、空态、按钮和状态标签。
- 个人校验、项目校验、管理后台、个人设置完成主要 UI 对齐，业务数据流保持不变。
- 规则导入、结果导出、系统使用说明入口等用户流程持续完善。

### 修复

- 修复 Project Vision AI Credential 连接测试使用 1x1 PNG 探针导致 Qwen 视觉模型拒绝请求的问题；测试探针改为满足常见视觉模型最小尺寸限制的小图。
- 修复管理后台 Project Vision AI Credential 已保存后连接测试失败仍显示“配置未保存”的误导提示；测试失败现在显示“Vision AI 连接测试失败”，并展示后端返回的脱敏失败原因。
- 修复“用例生成”AI 返回常见非契约形态时直接 502 的问题，包括字符串形式 `warnings`、数组形式 `steps/expected_results`、数值型文本字段和 `requirement_trace: null`。
- 补齐 `package_items_compare` 在规则元数据中的当前能力声明，修正数据源 capabilities 的实现状态，并清理飞书读取与页面展示中的旧状态文案。
- 修复组合分支保存、跨组变量比较、SVN 变量添加、默认管理员自修复、文件选择卡顿和页面刷新状态误判等问题。

## [0.5.0] - 2026-04-20

### 新增

- 共享展示组件层：`PageHeader / SectionHeader / StatPill / StatusDot / EmptyState / DataTable`，统一工作台 / 固定规则 / 管理后台 / 个人设置四页的视觉骨架。
- `docs/MODULES.md` 与本 `CHANGELOG.md` 由 `README.md` 在「相关文档」入口暴露。

### 变更

- 全站切到 Tailwind v3 + 单 accent (`#2563eb`) 色板；`frontend/src/style.css` 收口为冷静风 token，弃用旧的 Apple 玻璃质感样式。
- 主工作台改为 4 个始终展开的模块（数据源 / 变量池 / 规则 / 结果），结果区切换为参考稿式 4 统计块 + 异常表。
- 固定规则页与管理后台改为单列三模块全宽通栏；模块头统一 `01 / 02 / 03` 浅蓝序号 + 标题 + 状态胶囊；按钮收到模块头同行右侧。
- 个人设置页改为全宽 + 内部 `max-w-md` 表单 + 横向 4 列账号信息；项目表 4 列等宽。
- 管理后台所有边框收口到 `border-gray-100 / 200`，01 项目卡片化（选中态 `border-blue-500 + bg-blue-50`），02 字段值用只读容器包裹，03 成员表用极浅完整网格线。
- 工作台顶栏移除「载入样例数据」与「执行校验」两个按钮，仅保留 `pageError` 时出现的「清除错误」。
- 规则引擎完成 `domain / infrastructure / handlers` 三层物理分层；`RULE_REGISTRY` 升级为 `RuleSpec(handler + dependent_tags)`。

### 修复

- 固定规则页步骤 3 排版崩坏（旧 `fixed-rules.css` 已删除后 `WorkbenchRuleOrchestrationPanel.vue` 引用失效）。
- 默认管理员 `admin / 123456` 缺失场景下，`POST /api/v1/auth/login` 触发受控自修复并重试一次。

## [0.4.0] - 2026-04-17

### 新增

- 多用户认证体系：JWT、注册、登录、`/auth/me`、修改密码、切换项目。
- 三级角色：超级管理员、项目管理员、普通用户；默认超级管理员 `admin / 123456` 启动时固定播种。
- 用户表 `primary_project_id` 主归属项目语义；登录默认项目按主归属确定，不再依赖 `roles[0]`。
- 管理后台 `/admin`：项目 CRUD、成员角色与归属调整、密码重置；项目管理员获得受限版后台。
- 个人设置 `/profile`：账号信息、密码修改、项目切换。
- 数据持久化迁移到 SQLite（SQLAlchemy 异步引擎）：`Project / User / UserProjectRole / FixedRulesConfigRecord / WorkbenchConfigRecord` 五张 ORM 模型。
- 前端 `apiFetch` 统一 JWT 注入与 `401` 跳转；路由全局守卫；项目切换走 SPA 内 store 重置（不再整页刷新）。

### 变更

- 默认项目 `默认项目` 设为系统保留，禁止删除；删除自定义项目时成员自动迁移到默认项目并降为普通用户。
- 密码哈希从 `passlib[bcrypt]` 切到直接使用 `bcrypt`，兼容 `bcrypt 5.x`。
- 默认项目中删除成员等同删除账号；其他项目中删除成员自动迁移到默认项目；删除统一二次确认。

## [0.3.0] - 2026-04-13

### 新增

- 组合变量：`variable_kind = composite`，同一数据源同 Sheet 的多列组合，支持 `key_column` 与 JSON 映射预览。
- 规则类型 `composite_condition_check`：组合分支校验，支持「全局筛选 + 分支筛选 + 分支校验」结构；筛选操作符覆盖 `eq / ne / gt / lt / not_null / contains`，分支校验操作符覆盖 `eq / ne / gt / lt / not_null / unique / duplicate_required`。
- 主工作台步骤 3 与 `/fixed-rules` 同构的规则组编排：规则组 CRUD、当前组规则 CRUD、分页（`20 / 页`）。

### 变更

- 工作台规则状态由 `useWorkbenchStore` 维护；与 `fixedRules` store 完全隔离。
- 抽取共用规则模型工具 `frontend/src/utils/ruleOrchestrationModel.ts`。

## [0.2.0] - 2026-04-10

### 新增

- 固定规则模块独立持久化：`/fixed-rules` 拥有自己的 `sources / variables / groups / rules`，`version = 4` 配置写入 `backend/.runtime/fixed-rules/default.json`。
- 固定规则页变量池：与主工作台相同的「来源 → Sheet → 列名」下拉，并支持组合变量预览。
- 规则弹窗：从「文件路径 + Sheet + 列」改为直接绑定固定规则页变量池中的 `target_variable_tag`；规则名称按 `sheet-目标列-规则选择名称(+值)` 自动生成。
- 固定规则配置读取支持 `meta.config_issues` 非阻断告警：本地路径失效 / Sheet / 列不存在不再阻塞页面，仅在数据源行标 `路径失效`。

### 变更

- 旧版 `version = 2 / 3` 固定规则配置在读取时自动迁移至 `version = 4`。
- `/fixed-rules` 与主工作台数据源 / 变量池完全隔离，互不影响。

## [0.1.0] - 2026-04-08

### 新增

- 主工作台四步骨架（数据源 / 变量池 / 规则 / 结果）+ 统一执行引擎 `POST /api/v1/engine/execute`。
- 数据源能力：`/api/v1/sources/capabilities / local-pick / metadata / column-preview / composite-preview`。
- 规则注册表与 5 类规则：`not_null / unique / fixed_value_compare / cross_table_mapping / composite_condition_check`。
- 固定规则模块独立路由 `/fixed-rules` 与接口 `/api/v1/fixed-rules/{config,svn-update,execute}`。
- 本地文件选择走 `tkinter` 桌面对话框，避免浏览器拿不到本地绝对路径的问题。
- SVN CLI 自动探测：默认按 `SVN_EXECUTABLE` 环境变量、`PATH`、Windows 下 TortoiseSVN 安装路径顺序解析。
