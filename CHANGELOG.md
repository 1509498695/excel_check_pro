# 更新日志

本日志按 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 风格维护，记录版本级变化，不记录分钟级流水。

- 分钟级历史日记：[docs/archive/PROJECT_RECORD.md](docs/archive/PROJECT_RECORD.md)
- 本次文档精简前的长篇 `[Unreleased]` 明细快照：[docs/archive/changelog-unreleased-before-doc-cleanup-2026-05-19.md](docs/archive/changelog-unreleased-before-doc-cleanup-2026-05-19.md)

## [Unreleased]

### 文档治理

- 二次精简当前稳定文档：保留 6 份入口但压缩重复段落，明确 README、架构、模块、规范、前端说明和更新日志的职责边界，并修正个人规则导入项目校验的当前 API 路径。
- 精简当前文档入口：`README.md`、`docs/ARCHITECTURE.md`、`docs/MODULES.md`、`docs/STANDARDS.md`、`frontend/README.md` 与本文件成为当前说明主入口。
- 压缩 README、架构、模块和前端说明中的重复段落，将历史需求、分钟级进度、一次性重构方案和长篇变更流水收口到 `docs/archive/`。

### AI 智能添加规则

- 个人校验步骤 03「智能添加规则」完成多轮结构收口：后端拆出凭据、上下文、草稿仓储、字段解析、workflow hints、模板兼容、compiler registry、materializer registry 与部分 extractor；前端拆出 dry-run 线索同步、预校验、确认添加、历史、模板和草稿门禁 composable。
- 对外 AI 接口保持兼容：`rule-draft`、`rule-prompt-optimize`、`dry_run=true`、草稿历史、三态结果和现有字段不变。
- 规则描述输入继续支持短模板、自然句、旧 v3 技术模板、旧三段模板和自由文本；后端优先确定性编译，必要时再调用模型补语义。
- 高风险场景保持覆盖：多筛选、`FIELD 唯一` 作为 Key 前置、字段对字段断言、`duplicate_required`、`dual_composite_compare` 左右筛选与 Key、聚合/公式类拒绝。
- 智能添加规则「查看配置」改为只读规则配置预览，默认展示规则组、变量、筛选、Key 和比较字段等表单化信息，JSON 调试信息改为默认收起。

### 规则与执行能力

- 个人校验与项目校验规则弹窗统一支持 5 类入口：单一变量校验、组合分支校验、跨组变量校验、多组串行校验、多组映射校验。
- 当前规则库覆盖 10 类规则：非空、唯一、固定值、正则、顺序、跨表映射、组合分支、双组比较、多组串行、多组映射。
- 组合分支、跨组比较、多组串行/映射持续补齐筛选、断言、结果显示字段、规则集、Key 后追加序号等能力，并保持个人校验与项目校验共用执行引擎。

### 数据源与部署

- CSV 数据源入口已下线，历史 CSV 配置提示改用 Excel 或 SVN Excel；飞书仍为占位入口。
- 本地 Excel、浏览器上传 Excel、SVN Excel 统一接入变量池、元数据读取和执行链路。
- SVN HTTP 数据源支持目录浏览、凭据加密、缓存刷新、个人校验和项目校验更新；鉴权失败使用 HTTP 403，避免误触登录态过期。
- 本机共享部署支持前端构建后由 FastAPI 单服务托管，并通过环境变量配置监听地址、端口、CORS、上传大小、JWT 密钥和默认管理员密码。

### 前端与体验

- 全站页面统一到 SaaS 工作台视觉：共享 shell 组件、分区标题、指标卡、表格、空态、按钮和状态标签。
- 个人校验、项目校验、管理后台、个人设置完成主要 UI 对齐，业务数据流保持不变。
- 规则导入、结果导出、AI 草稿预校验解释卡、系统使用说明入口等用户流程持续完善。

### 修复

- 修复多类智能规则解析、草稿历史回填、组合分支保存、跨组变量比较、SVN 变量添加、默认管理员自修复、文件选择卡顿和页面刷新状态误判等问题。

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
