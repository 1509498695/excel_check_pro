# 用例生成 Spec

## 0. Codex 快速入口

- 先读哪些文件：`CONTEXT.md`、`docs/ARCHITECTURE.md`、`docs/specs/data-sources.md`、`docs/specs/feishu-integration.md`、`docs/specs/ai-project-credentials.md`、`docs/FRONTEND_STYLE_GUIDE.md`。
- V3 方向文档：`docs/superpowers/specs/2026-07-02-test-case-generation-v3-full-generation-design.md`。
- 架构决策：`docs/adr/0003-replace-synchronous-test-case-generation-with-full-generation-runs.md`。
- 历史 V1 实施计划：`docs/superpowers/plans/2026-06-22-test-case-generation.md`。
- 配套 UI 设计图：`docs/assets/test-case-generation-ui-v1.png`。
- 参考来源：旧 Codex 线程 `019eca67-83e2-7532-babe-54883f9497cc`、`D:\project\TestCaseStudio\TestCaseStudio`、`qa-case` skill。
- 当前状态：V3 `Generation Run` 已成为前端主生成/导出链路；旧版同步生成和旧快照导出只保留为兼容/历史路径，不再作为当前主流程。
- 不要改哪些契约：不改变 `TaskTree`、个人校验工作台、项目校验执行入口、统一执行结果结构；不要恢复个人 AI Key。
- 新增功能从哪里接入：前端独立页面 `/test-cases`；后端独立用例生成业务模块，并由 `/api/v1/test-cases/*` 聚合路由挂载。
- 必跑测试：实现后至少覆盖 Generation Run 创建/轮询/取消/重试、Requirement Atom、Coverage Audit、run id 导出、参考案例库权限、Source Evidence 视觉证据和前端页面状态。
- 常见误区：把参考案例当需求来源、把 `Planning Sheet Snapshot` 当 V3 全量生成输入、把 Source Evidence Run 混同为 Generation Run、让前端提交用例作为导出事实、把 `qa-case` CLI 当应用内依赖、复用 TestCaseStudio 的个人 API Key 输入框、让模型口算统计结果、永久保存 raw prompt/provider response。

## 1. 文档状态

| 项 | 内容 |
|---|---|
| 版本 | V3 当前主方向，保留 V1/V2 历史边界 |
| 状态 | V3 Generation Run 主链路已接入；稳定文档以 V3 为当前事实 |
| 需求范围 | 项目级“用例生成”页面、Source Evidence 来源证据、Generation Run 异步全量生成、Requirement Atom、Coverage Audit、按 run id 导出 |
| 明确不做 | 永久生成历史、raw prompt/raw response 留存、蓝图编辑、Feishu 写回、跨项目案例库引用、可维护 QA 知识库 |
| 主要使用者 | 项目成员、项目管理员、超级管理员 |

## 2. 背景与目标

当前项目已经具备多用户项目权限、Source Evidence 来源证据、项目级 AI 凭据、参考案例库和 Excel 导出基础能力。当前 V3 主方向是在这些能力之上，用短期 `Generation Run` 把当前选中的完整 `Planning Sheet` 转换为可追踪、可审计、可导出的测试用例。

V3 目标不是复刻 TestCaseStudio，也不是直接运行 `qa-case` skill，而是吸收两者的方法论，同时补齐 V1/V2 的覆盖证明缺口：

- 从 `qa-case` 吸收测试设计蓝图、完整性矩阵、可执行步骤、可观察预期和风险备注。
- 从 TestCaseStudio 吸收参考案例库、主参考案例、结构画像、固定 JSON 生成和 Excel 导出体验。
- 以 `Full Planning Sheet Context` 替代旧版同步生成的截断输入，以 `Requirement Atom` 和 `Coverage Audit` 证明需求覆盖。
- 服从 Excel Check Pro 当前的项目权限、项目级 AI、Source Evidence 和后台式工作台风格。

`QA Case Method` 仍作为内置方法随代码发布，不提供页面维护、上传知识、知识审核、知识版本或项目级知识检索。后端实现时需要保留未来接入项目级 QA 知识库的扩展点，但当前 V3 生成不得依赖该扩展点。

## 2.1 当前 V3 主方向

V3 主链路：

```text
Source Evidence Run
-> 选择 Planning Sheet
-> 创建 Generation Run
-> 构建 Full Planning Sheet Context
-> 结构优先 chunking
-> 按 chunk 抽取 Requirement Atom
-> 合并去重 official atoms
-> 基于 atoms 生成 Test Case Blueprint
-> 按 module / atom group 分批生成用例
-> Coverage Audit
-> 对 uncovered atoms 自动补生成一次
-> Case Quality Audit 与一次安全定向修复
-> 自动渲染并校验 xlsx / blueprint / stats / coverage / quality 产物
-> completed / partial_completed / failed
-> 页面选择文件预览，下载读取已生成文件
```

V3 的需求事实只来自当前 selected `Planning Sheet` 的完整文本/表格事实和同 sheet 的 `Adopted Visual Evidence`。参考案例库只影响层级、命名、粒度和历史风格，不得改变 canonical 字段、执行列或产生新需求。旧 `Planning Sheet Snapshot` 可以继续作为来源预览、AI 整理稿输入或兼容接口使用，但不承担 V3 全量生成输入语义。

## 3. 角色与权限

| 角色 | 当前能力 |
|---|---|
| 项目成员 | 查看/选择/使用参考案例、创建分类、上传参考案例、读取策划案、生成用例、导出 Excel |
| 项目管理员 | 拥有项目成员能力；可删除参考案例、重命名分类、删除分类、设置推荐主参考 |
| 超级管理员 | 拥有所有项目管理员能力 |
| 非项目成员 | 不可进入或调用当前项目的用例生成能力 |

权限收口原则：

- 分类只是组织方式，不是权限边界。
- 参考案例库按 `project_id` 隔离。
- 不做跨项目引用。
- 会影响全项目共享资产的动作只允许项目管理员和超级管理员执行。

## 4. 当前范围

### 4.1 V3 必须支持

- 独立页面 `/test-cases`，导航名称为“用例生成”。
- 策划案来源通过 `Source Evidence Run` 支持飞书文档、本地文件、SVN 文件和 workbook/sheets 来源。
- 单次 `Generation Run` 只选择一个 `Planning Sheet`，并以完整 selected sheet 构建 `Full Planning Sheet Context`。
- 旧 `Planning Sheet Snapshot` 只作为受控预览/兼容接口，不驱动 V3 全量生成。
- 支持项目级参考案例库，参考文件格式为 `.xlsx`、`.xls`、`.md`、`.txt`。
- 参考案例上传时生成确定性的 `Reference Test Case Profile`。
- 生成流程采用“Full Context -> chunks -> Requirement Atoms -> Blueprint -> Cases -> Coverage Audit -> Case Quality Audit -> Artifacts”的异步多阶段编排。
- 页面展示 run 状态、阶段进度、测试用例、覆盖审计、质量审计、需求原子、限制提示和产物选择器。
- Generation Run 完成前自动从后端短期 DB 真相渲染产物包；Excel 至少包含 `测试用例`、`用例蓝图`、`生成说明`、`覆盖审计`，并同时生成 blueprint Markdown、stats JSON、coverage JSON、quality JSON。
- 所有 AI 调用只使用项目级 AI 凭据。

### 4.2 明确不支持

- 不保存永久生成历史；Generation Run 详细结果只在 TTL 内短期保存。
- 不保存 raw prompt、raw response、完整 provider response、API Key、token 或本地敏感路径。
- 不允许编辑蓝图，也不提供“编辑蓝图后重新生成”。
- 不让未观察、未采纳、跨 Sheet 或已过期视觉资源进入需求事实。
- 不支持 Word 上传。
- 不支持 XMind 导出。
- 不写回 Feishu 表格。
- 不做跨项目参考案例引用。
- 不提供用户个人 API Key 输入框。
- 不严格复刻主参考案例 Excel 的所有未知列。
- 不提供可维护 QA 知识库，不做知识上传、知识审核、知识版本、知识检索或知识命中解释。

### 4.3 V1/V2 兼容边界

- V1 同步生成和旧导出属于历史/兼容路径，不再是前端主链路。
- V2 Source Evidence 继续负责短期来源证据、视觉观察、采纳和 TTL 清理；它不是 Generation Run，也不是生成历史。
- `Planning Sheet Snapshot` 继续可用于来源预览、AI 整理稿和旧路径兼容；V3 不用它作为全量生成输入，也不受旧 snapshot row/char prompt budget 限制。

## 5. 核心概念

| 概念 | 定义 |
|---|---|
| Planning Sheet | 本次生成选择的单个策划案 Sheet |
| Planning Sheet Snapshot | 从 Planning Sheet 读取后经过预算限制、截断和 warnings 标记的受控预览；当前 V3 不把它作为全量生成输入 |
| Full Planning Sheet Context | V3 从当前 selected Planning Sheet 构造的完整输入，包含所有可读文本/表格事实和同 sheet 已采纳视觉证据 |
| Generation Run | V3 短期异步工作流，承载读取、切片、原子抽取、蓝图、用例、覆盖审计、质量审计、产物渲染和 TTL 清理 |
| Requirement Atom | 从 Full Planning Sheet Context 抽取出的可追踪需求事实，是 V3 蓝图和用例的正式需求来源 |
| Coverage Audit | 比对 official atoms、cases、failed chunks 和限制项的覆盖审计结果 |
| Case Quality Audit | 按 QA Case Method 检查可执行性并最多执行一次安全定向修复；不能用模型猜测补齐不确定需求 |
| Generated Test Case Artifact | 从 Generation Run 数据库真相确定性生成并校验的短期文件，包括 xlsx、blueprint Markdown 和三类 JSON 审计/统计文件 |
| AI-Assisted Snapshot Brief | 从 Planning Sheet Snapshot 自动整理出的 Markdown 阅读稿，用于策划/QA 对齐和来源预览，不替代 V3 full context |
| Reference Test Case Library | 当前项目共享的参考案例库 |
| Primary Reference Test Case | 本次生成主要贴近的参考案例 |
| Reference Test Case Profile | 上传参考案例后确定性解析出的字段、层级、优先级和粒度画像 |
| Test Case Blueprint | V3 基于 official Requirement Atoms 生成的只读测试设计蓝图 |
| Test Case Generation Warning | 读取、截断、权限、AI 或导出过程中需要用户知晓的警告 |
| QA Case Method | 内置的用例生成方法规则，包含蓝图、完整性矩阵、自检和统计约束 |
| Project QA Knowledge Library | 候选的项目级可维护 QA 知识库，当前不实现 |

## 6. 用户流程

```text
进入“用例生成”页
-> 创建或选择 Source Evidence Run
-> 选择一个 Planning Sheet
-> 可选读取 Planning Sheet Snapshot / AI-Assisted Snapshot Brief 作为来源预览
-> 可选选择参考案例分类、参考案例和一个 Primary Reference Test Case
-> 创建 Generation Run
-> 后端构建 Full Planning Sheet Context
-> 结构优先 chunking
-> 抽取并合并 Requirement Atom
-> 基于 official atoms 生成 Test Case Blueprint
-> 按 module / atom group 分批生成测试用例
-> Coverage Audit，并对 uncovered atoms 自动补生成一次
-> 前端轮询 run 进度，展示用例、覆盖审计、需求原子和限制提示
-> 按 generation run id 导出 Excel
```

页面刷新后，前端可用本地保存的最近 run id 恢复短期 Generation Run。TTL 到期或详情被清理后，用户需要重新读取来源并重新生成。

## 7. 策划案来源需求

### 7.0 前端来源添加模块

当前前端页复用个人校验的 01 数据源模块外观和 `DataSourcePanel` 交互，用于维护本次用例生成的策划案来源。该模块支持添加飞书表格、上传 Excel 或 SVN Excel 作为策划案来源，并按当前项目 + 当前用户持久化为用例生成页的策划案来源配置。前端复用 workbench config 的独立 `test_case_generation` 命名空间保存 `planning_sources`、`preferred_planning_source_id` 和 `selected_planning_sheet_name`；不得写入或覆盖个人校验的 `sources`、`variables`、`ruleGroups`、`orchestrationRules`，也不新增用例生成后端数据源接口。

左侧“策划案来源”卡片保留为选择区：用户从当前用户在当前项目下保存的数据源列表中选择一个策划案来源，再选择该来源下的一个 Sheet 并读取快照。刷新页面后恢复来源和上次选择；若 Sheet 信息不可用或已变化，则回退到当前来源的第一个可用 Sheet。

### 7.1 飞书电子表格

V1 复用当前飞书数据源能力：

- 支持飞书电子表格和 wiki 电子表格链接。
- 复用链接解析、权限检测、授权卡片、OAuth 只读授权和授权记录。
- 支持读取 Sheet 列表。
- 用户选择一个 Sheet 后，读取二维单元格值并生成快照。

限制：

- 不支持飞书多维表格。
- 不支持飞书文档中的表格。
- 不读取单元格内图片、附件或评论语义。
- 权限不足时沿用现有授权流程，不静默失败。

### 7.2 Excel 上传

V1 复用当前浏览器上传能力：

- 支持 `.xlsx` 和 `.xls`。
- 文件大小沿用当前上传上限。
- 上传后读取 workbook 的 Sheet 列表。
- 用户选择一个 Sheet 作为本次 `Planning Sheet`。

限制：

- 不支持 Word、PDF、XMind 或压缩包作为策划案输入。
- 不读取 Excel 内图片、附件或批注语义。

## 8. 来源预览与兼容快照需求

`Planning Sheet Snapshot` 是给页面使用的受控来源预览，也是 V1/V2 旧版同步路径的兼容输入；它不等同于原始文件，也不承担 V3 全量生成输入语义。V3 生成必须从 `Source Evidence Run + planning_sheet_name` 构建 `Full Planning Sheet Context`，不得受旧 snapshot 行数、字符数或 prompt budget 影响。

旧快照预览默认预算：

| 维度 | 默认上限 |
|---|---:|
| 有效字符 | 80,000 |
| 有效行 | 800 |
| 有效列 | 80 |
| 单元格文本 | 300 字符 |
| 非空单元格 | 12,000 |

预览超限时必须返回 warnings。示例：

- `读取 1800 行，纳入前 800 行。`
- `5 个超长单元格已截断到 300 字符。`
- `末尾内容未纳入预览；V3 全量生成仍会读取完整 selected Planning Sheet。`
- `来源材料可能包含图片、原型图或附件，V1 未读取其中语义。`

需求约束：

- 截断必须显式可见。
- 不允许静默丢弃超限内容。
- 快照不落库。
- V3 `Generation Run` 不从前端提交的快照读取需求事实。
- 旧版同步兼容路径若仍保留，必须明确标注不支持 V3 全量生成。

### 8.1 AI 快照整理稿

`AI-Assisted Snapshot Brief` 是给策划和 QA 阅读、复制、对齐用的 Markdown 整理稿，不替代 `Planning Sheet Snapshot`，也不替代 V3 `Full Planning Sheet Context`。

行为要求：

- 读取快照成功后自动触发 AI 整理，但不得阻塞原始快照返回和页面可继续操作。
- AI 整理通过独立接口 `POST /api/v1/test-cases/planning-snapshot/brief` 执行；前端在快照读取成功后异步调用该接口，`重新整理` 也复用该接口。
- AI 整理失败只影响整理稿，不影响已读取快照、重新整理或后续生成。
- AI 整理失败时页面只展示脱敏摘要和重新整理入口，不展示完整 provider 响应、prompt、API Key 或 Base URL。
- 页面需要提供重新整理入口。
- 整理稿可作为人工阅读和来源预览辅助；V3 生成的需求事实来源、行号追踪和覆盖审计必须来自 `Full Planning Sheet Context` 与 `Requirement Atom`。
- 整理稿应按原策划案顺序组织重点，减少当前原始快照表格过大、过散导致的阅读成本。
- 快照读取成功后，页面默认展示整理稿；原始快照表格不作为常驻前端页签展示，仅保留在当前页面态、生成请求和排查链路中。
- 整理稿使用固定 Markdown 模板：`核心目标`、`功能范围`、`规则与流程`、`配置/数值/条件`、`时间、刷新与生命周期`、`UI、提示与表现`、`风险点与易漏点`、`待确认问题`、`来源索引`。
- `来源索引` 必须保留快照行号或原始片段引用，方便策划和 QA 回到原始表格核对。
- 整理稿不保存到后端，只保留在当前页面态；可用于复制和人工核对，刷新页面后丢失。
- 页面提供 `复制 Markdown` 和 `重新整理` 两个整理稿操作；V1 不提供下载 `.md` 文件。

## 9. 参考案例库需求

参考案例库是项目级服务端资源，不是用户本机配置。参考案例通过浏览器上传到后端，由后端按项目保存文件、画像和元数据；同项目成员通过 API 查看、选择和使用，不依赖上传者本机路径。

参考案例文件是长期项目资产，不应进入当前普通 Excel 上传目录或上传保留期清理策略。后端应使用独立的参考案例存储目录，或显式将参考案例目录排除在 runtime upload cleanup 之外。

现有数据源上传和 Excel 读取能力可以复用底层能力，但不能直接把 `/api/v1/sources/upload` 的返回结果当作参考案例库记录。参考案例上传需要额外处理分类、同名 active 冲突、画像生成、推荐主参考、删除权限和项目共享列表。

### 9.1 分类

V1 提供项目级分类，用于组织参考案例。示例：

- 活动用例
- 礼包用例
- 配置校验
- UI 通用
- 回归模板

分类需求：

- 分类是本次可选参考案例的组织范围；一次生成只在当前分类内选择参考案例。
- 切换分类时，前端必须清空已选参考案例、主参考案例和主参考 Sheet。
- 如果新分类存在推荐主参考，前端默认选中该推荐主参考并把它设为本次主参考。
- 如果新分类没有推荐主参考，前端不得自动选择第一条、最新文件或任意文件；生成仍可基于策划案快照和 `qa-case` 标准逻辑执行，并提示“未使用参考案例增强”。
- 分类名称保存前必须去除首尾空格；去除后为空时拒绝，同一项目内按去除首尾空格后的名称唯一。
- 分类名称不做大小写折叠、内部空格规整或全角/半角转换。
- 项目成员可以创建分类。
- V1 允许创建空分类；空分类仅用于组织参考案例，不影响生成。
- 分类重命名和删除仅项目管理员和超级管理员可执行。
- 分类删除后，关联参考案例展示为“未分类”或等价状态，并清空这些参考案例的推荐主参考标记。
- 分类不承载权限。

### 9.2 参考案例文件

V1 支持格式：

- `.xlsx`
- `.xls`
- `.md`
- `.txt`

上传需求：

- 项目成员可以上传。
- V1 不做覆盖替换；同一项目、同一分类下已存在同名 active 参考案例时，拒绝上传并提示先联系项目管理员删除旧文件后再上传。
- 上传后立即生成并保存 `Reference Test Case Profile`。
- Excel 参考案例上传后读取 workbook 的 Sheet 列表，并为每个可用 Sheet 生成独立画像。
- 可用 Sheet 指能可靠识别表头，并能识别出至少一行参考用例的 Sheet。
- Excel 参考案例默认 Sheet 由后端判定：优先选择名称命中 `测试用例`、`用例`、`TestCases` 的可用 Sheet；都未命中时选择第一个可用 Sheet。
- 多 Sheet 文件只要至少有一个可用 Sheet 就允许上传；不可用的说明页、目录页、配置页等不进入主参考 Sheet 可选列表，并通过 warnings 告知。
- Excel 文件可读取但没有任何可用 Sheet 时，视为画像生成失败并拒绝上传。
- 画像生成失败视为上传失败；后端删除已写入文件，不保存参考案例记录，不在列表中暴露 failed 半成品。
- 上传失败时返回明确错误，不产生半成品可选参考。
- 删除参考案例仅项目管理员和超级管理员可执行。
- 删除参考案例成功时，列表和生成选择立即排除该记录；后端软删除记录用于审计，同时删除物理文件。
- 删除物理文件时，如果文件已不存在，视为删除成功，继续软删除记录并清空可复用元数据。
- 如果物理文件存在但因权限或 IO 错误删除失败，后端返回删除失败；记录保持 active，不清空 `storage_path`、`Reference Test Case Profile` 或推荐主参考标记，管理员可重试删除。
- 删除后仅保留必要元数据，例如文件名、后缀、大小、上传人、上传时间、删除人、删除时间；不得继续保留可复用的原文件路径或 `Reference Test Case Profile` 画像内容。

### 9.3 推荐主参考

需求：

- 项目管理员和超级管理员可将某个参考案例设置为推荐主参考。
- 推荐主参考按“项目 + 分类”唯一；例如同一项目的“活动用例”和“礼包用例”可以分别拥有一个推荐主参考。
- “未分类”视为 `category_id = null` 的独立推荐范围，也可以设置一个推荐主参考。
- 普通成员可以选择推荐主参考，也可以在本次生成中手动选择其他主参考。
- 推荐主参考只是分类切换后的默认增强选择；用户可以清空主参考并按无参考模式生成。
- 推荐主参考不得成为生成前置条件，参考案例只补充层级、命名、粒度和历史风格，不改变 canonical 字段与模板布局。

### 9.4 主参考 Sheet

需求：

- 当主参考案例是 Excel 文件时，用户必须能在“生成设置”中选择一个主参考 Sheet。
- 主参考 Sheet 只从该 Excel 参考案例已解析出的可用 Sheet 列表中选择，不允许手输任意 Sheet 名。
- 页面默认选中后端识别出的默认 Sheet，用户可以手动改选；未显式选择时后端也按该默认 Sheet 兜底。
- 当主参考案例是 Markdown 或 TXT 时，Sheet 选择框保留但禁用，并显示“当前参考案例无 Sheet”或等价文案。
- 未选择主参考案例时，主参考 Sheet 选择框禁用，并显示“未选择主参考”或等价文案。
- 切换主参考案例或主参考 Sheet 后，已生成结果失效，需要重新生成。

### 9.5 参考案例选择

需求：

- 同一分类内允许多选参考案例，作为本次生成的可选增强参考集合。
- 本次生成可以不选择参考案例或主参考案例；无参考时仍必须能生成高质量用例。
- 主参考案例是可选增强输入；选择时最多只能有一个，且必须属于当前已选参考案例集合。
- 用户将某个文件设为主参考时，如果该文件尚未被勾选，前端应自动把它加入已选参考集合。
- 用户取消勾选当前主参考时，前端清空主参考，不自动改选其他已选文件，以避免隐式改变生成风格；生成仍可继续。
- “生成设置”中的“主参考案例”下拉只展示当前已选参考案例；未选择任何参考案例时禁用并提示“可选：先选择参考案例后指定主参考”。
- 参考用例数量来自当前主参考案例画像；未选择主参考时显示“未使用主参考”，Excel 主参考按当前主参考 Sheet 展示数量，Markdown/TXT 无法可靠识别时显示“未识别”。

列表交互：

- 分类展示应优先使用横向 pill/tab，而不是仅使用下拉框。
- 文件过多时，参考案例库使用搜索、类型筛选、排序和分页展示；前端默认每页展示 5 条参考案例，避免列表拥挤或撑高整个页面。
- 搜索范围至少包含文件名和画像摘要。
- 空态需要区分“当前分类暂无参考案例”和“没有匹配的参考案例”。
- 文件行需要展示勾选状态、文件类型、推荐主参考标识、画像摘要、上传人、上传时间和操作入口。

## 10. 参考案例画像需求

画像生成必须是确定性解析，不调用 AI。
画像异常只作为上传错误返回；V1 不提供 failed 画像记录、重试入口或半成品清理入口。

Excel 参考案例画像按 Sheet 维度保存：`Reference Test Case Profile` 需要包含可选 Sheet 列表、默认 Sheet，以及每个可用 Sheet 的字段、层级、优先级和粒度画像。生成时使用选中的主参考 Sheet 对应画像；非 Excel 参考案例没有 Sheet 画像。
Excel 表头或用例行无法可靠识别时，不允许作为可用 Sheet；如果整份 Excel 没有任何可用 Sheet，则上传失败。

V1 至少提炼：

- 参考用例数量：从当前参考案例或 Excel Sheet 中确定性读取出的可识别用例行数，用于页面只读展示，不作为生成数量输入。
- Excel 参考用例数量：从识别到的表头下一行开始统计；统计包含用例标题、检查点、步骤、预期等任一用例内容字段的行；模块、功能、场景等层级字段只参与辅助判断，只有层级字段有值的纯分组行不计入。
- Excel 不计入：完全空行、纯模块/功能/场景分组行、说明行、合计行、只有备注/说明字段有值的行。
- Markdown/TXT 参考用例数量：仅当能识别表格用例行或 checklist 用例项时统计；无法可靠识别时返回未知，页面显示“未识别”。
- 字段结构：用例编号、模块、检查点、步骤、预期、备注等列。
- 标题层级：模块、功能、场景、用例标题等层级信号。
- 优先级风格：`P0/P1/P2/P3`、`高/中/低` 或 `H/M/L`。
- 用例粒度：一行单验证目标，还是一行多检查点。
- 备注习惯：配置来源、版本、Bug、待确认项、限制说明。
- 导出建议：生成时如何尽量贴近该参考案例。

边界：

- 参考案例只影响格式、字段、层级、命名风格和用例粒度。
- 参考案例不能当作新的需求来源。
- 无法识别的参考列不强行生成。

## 11. AI 生成需求

### 11.1 凭据

- 只使用项目级 AI 凭据。
- 不提供用户个人 API Key 输入框。
- 项目级 AI 未配置、禁用或不可用时，生成操作提示联系项目管理员配置项目级 AI。
- 错误响应、日志、页面和导出文件不得暴露完整 API Key。

### 11.2 蓝图

AI 生成正式用例前必须先形成 `Test Case Blueprint`。V3 蓝图只从合并后的 official `Requirement Atom`、`QA Case Method` 矩阵、来源摘要和已知 warnings 生成，不直接读取 raw sheet、旧 `Planning Sheet Snapshot` 或参考案例事实。

参考案例库不是必需输入；选择参考案例时只作为层级、命名、粒度和历史风格的增强信号，不能改变 canonical 字段或补充新需求。`AI-Assisted Snapshot Brief` 只用于人工阅读和来源预览，不作为 V3 需求事实输入。

V3 的 `QA Case Method` 包含：

- 需求来源追踪：从 `Requirement Atom` 追踪到 source sheet、row/column、source excerpt 和 adopted visual evidence，再追踪到蓝图节点和用例行。
- 蓝图先行：不得从策划案直接堆用例行。
- 完整性矩阵：生命周期、时间刷新、权限关系、地图/服务器、配置数值、UI 通用、输入、历史记录、外部耦合。
- 具体场景库：弹窗/面板、红点、分享/拜访、售卖/兑换、每日任务、产出/收取/偷取、账单/邮件、移民/活动下线、性能/稳定性。
- 自检规则：检查是否有未映射需求、无依据测试点、待确认问题、未读图片/附件限制和环境限制。
- 统计规则：用例总数、模块分布、优先级分布等必须由代码计算。

当前不做可维护 QA 知识库。后端内部可以预留 `knowledge_context` 或等价扩展结构，但公共请求不得接收用户传入的知识内容；如果客户端提交 `knowledge_context` 或等价字段，后端应以 400 拒绝。响应只记录“未接入项目级 QA 知识库”或等价说明；不得提供用户维护入口，也不得把参考案例库当成知识库。

蓝图至少包含：

- 模块树。
- 核心流程。
- 状态或生命周期。
- 配置/数据来源。
- 角色关系。
- 时间刷新点。
- 外部耦合。
- 变更影响范围。
- 需求追踪关系，必须包含 atom id 或可回溯 source fragment。
- 覆盖维度。
- 风险点。
- 未映射需求。
- 无需求依据的测试点，必须进入 unsupported/unfounded warnings，不得作为正式需求。
- 待确认问题。
- 已使用的内置方法规则。
- 未接入项目级 QA 知识库说明。
- warnings。

蓝图只读生成，不可编辑；前端可以在结果区展示摘要，Excel 导出必须保留 `用例蓝图` Sheet 供审计和排查。

### 11.3 用例

用例生成要求：

- 一行一个明确验证目标。
- 每条正式用例必须引用至少一个有效 official `Requirement Atom`。
- 步骤可执行。
- 预期可观察。
- 备注记录假设、待确认、配置来源、策划答疑、Bug 链接和未读图限制。
- 生成后由后端结构校验、补默认值、去重和计算统计。
- 无 atom 支撑的候选用例默认剔除，并进入 `Coverage Audit` 的 unfounded candidates。
- 统计不得由模型直接提供最终数值。

## 12. 输出字段需求

基础用例字段：

- 用例编号
- 功能模块
- 检查点
- 来源测试点
- 用例标题
- 前置条件
- 操作步骤
- 预期结果
- 优先级
- 初始状态
- 配置来源
- 策划答疑
- Bug 链接
- 备注

默认值：

- 初始状态默认为“未执行”。
- 缺少用例编号时由代码生成稳定编号。
- 缺少优先级时按生成策略补默认值，并在 warnings 或备注中说明。

## 13. Excel 导出需求

导出策略：

- V3 导出入口是 `POST /api/v1/test-cases/generation-runs/{run_id}/export`。
- Generation Run 在终态前自动按短期 DB 结果生成并校验完整产物包；下载接口只读已生成文件，不在点击下载时重新调用 AI 或临时拼工作簿。
- canonical workbook 使用仓库内版本化模板，固定 A-I 为编号、一级模块、二级模块、检查点、前置条件、步骤、预期、优先级、备注，J-L 为三个中性执行列，优先级枚举固定为 P0/P1/P2/P3。
- 参考案例不严格复刻，只用于层级、命名、粒度和历史风格，不能重排或扩展 canonical 字段。
- artifact retry 只重跑确定性渲染，不重跑来源读取、AI、Requirement Atom、蓝图或用例生成。

导出文件至少包含：

| Sheet | 内容 |
|---|---|
| 测试用例 | 正式用例行 |
| 用例蓝图 | 模块树、流程、风险、覆盖维度、待确认问题、atom traces |
| 生成说明 | Source Evidence 摘要、Sheet 名、Generation Run 状态、主参考案例、附加参考、warnings、AI 供应商脱敏状态、生成时间、coverage limitation |
| 覆盖审计 | atom id、source sheet、source rows、source columns、atom type、atom text、coverage status、linked case ids、failed chunk、limitation notes |

strict mode 下存在覆盖或质量阻塞项时不生成可下载 workbook，但仍生成其余审计产物。`partial_completed` 且非 strict mode 可以生成 workbook，但 `生成说明` 和 `覆盖审计` 必须显著标记未覆盖范围、失败 chunk、质量问题和导出限制。

导出安全要求：

- 不写入完整 API Key。
- 不写入完整原始 prompt。
- 不写入完整 provider response、local path、Feishu/SVN token、未采纳视觉 observation detail 或隐藏敏感元数据。

## 14. 前端需求

页面定位：

- 后台式工作台页面。
- 不做营销页或说明页。
- 首屏直接展示可操作流程，主按钮为“全量生成用例”或等价中文。
- 当前主生成/导出链路是 V3 `Generation Run`；旧版 `/api/v1/test-cases/generate` / export 不得作为页面主路径。

页面区域：

- 策划案来源区：01 数据源模块、策划案来源选择、Sheet 选择。
- 参考案例区：分类、文件列表、上传、主参考选择、主参考 Sheet 选择、推荐标识、参考用例数量。
- 操作区：来源预览位于生成输入区；创建 Generation Run、取消、失败 chunk 重试与产物操作统一放在结果区顶部。
- 预览区：提供生成文件选择器；xlsx 映射为测试用例表格预览，Markdown/JSON 读取已生成文本预览，并保留 `覆盖审计`、`需求原子`、`限制提示` 等结果视图。
- 状态区：AI 可用状态、读取/生成/导出进度、错误提示。

状态规则：

- 未创建可用 `Source Evidence Run` 或未选择 `Planning Sheet` 时不能创建 Generation Run。
- V3 生成读取完整 selected Planning Sheet，不只读取 snapshot preview rows。
- 快照预览读取成功后可帮助用户核对来源；AI 整理稿仍在生成中时，Generation Run 入口不应被整理进度阻塞。
- 快照读取成功后默认打开整理稿视图；整理稿尚未完成时展示整理中状态，不提供原始表格/追踪视图常驻页签。
- 整理稿未完成或失败时允许创建 Generation Run，页面提示“整理稿仅用于来源预览，未作为 V3 需求事实”或等价文案。
- 页面刷新后不恢复整理稿或原始快照；可通过 localStorage 中的最近 run id 调用 `GET /generation-runs/{run_id}` 恢复短期 active/latest run。
- active 状态每 2 秒轮询；`completed`、`partial_completed`、`failed`、`cancelled`、`expired` 后停止轮询。
- `completed` 或 `partial_completed` 后拉取 atoms/cases/artifacts，并展示 Coverage Audit 与 Case Quality Audit 摘要。
- `partial_completed` 必须显著提示 uncovered atoms、failed chunks、quality issues 和 export limitations；strict mode 存在阻塞项时 workbook 显示为 blocked。
- 未选择参考案例时仍可生成，后端按 `qa-case-xlsx` 标准蓝图、完整性矩阵和 canonical 字段输出。
- 当前参考案例分类没有推荐主参考时，不自动选择任何参考案例，生成仍可用，并提示本次未使用参考案例增强。
- 切换参考案例分类时清空已选参考案例、主参考案例和主参考 Sheet；如果新分类有推荐主参考，则默认勾选该推荐主参考并设为主参考。
- 同一分类内可选择多个参考案例；主参考可选，选择时最多一个。
- 取消勾选当前主参考后，不自动改选其他参考案例为主参考，生成继续按无主参考模式可用。
- 参考用例数量来自主参考画像，页面只读展示；切换主参考或主参考 Sheet 后同步更新，不允许用户手填“目标用例数量”。
- 切换策划案来源后清空快照和生成结果。
- 切换参考案例选择后生成结果标记失效，需要重新生成；失效状态下不允许导出旧结果。
- 切换主参考后生成结果标记失效，需要重新生成；失效状态下不允许导出旧结果。
- 切换主参考 Sheet 后生成结果标记失效，需要重新生成；失效状态下不允许导出旧结果。
- 页面不使用 localStorage 保存生成结果内容，只保存最近 run id 以恢复短期 run。

## 15. 后端需求

后端能力按业务边界拆分：

- 参考案例库：分类、上传、列表、删除、推荐主参考、项目隔离。
- 参考案例画像：上传时确定性解析并保存。
- 策划案快照：读取单个 Sheet，预算限制，warnings。
- AI 快照整理稿：接收当前页面持有的 `Planning Sheet Snapshot`，调用项目级 AI 生成 Markdown 整理稿，不保存整理结果。
- Generation Run：创建、读取、取消、失败 chunk 重试、TTL/expired 懒清理、阶段进度和项目隔离。
- Full Context / chunking / Requirement Atom / Blueprint / Cases / Coverage Audit：按阶段推进 run，不保存 raw prompt/raw response。
- 产物渲染：基于 `generation_run_id` 读取短期 DB 结果自动生成 xlsx/md/json 文件，不依赖前端页面内存结果；下载只读文件，重试只重跑 renderer。

接口边界：

- 所有接口必须校验当前项目成员身份。
- 管理动作必须校验项目管理员或超级管理员身份。
- Generation Run 是短期异步工作流记录，不是永久生成历史；详情按 TTL 清理，只保留最小审计。
- `POST /api/v1/test-cases/planning-snapshot/brief` 接收 `planning_snapshot`，返回 `brief_markdown` 和 `warnings`；该接口不读取原文件、不创建历史记录、不保存整理稿。
- V3 `POST /api/v1/test-cases/generation-runs` 接收 `source_evidence_run_id`、`planning_sheet_name`、reference selection 和 `strict_mode`，返回 `queued` run 并以异步语义推进。
- V3 `GET /generation-runs/{run_id}` 返回 run summary 和 sanitized stage payload。
- V3 `POST /generation-runs/{run_id}/cancel` 取消 active run；`POST /generation-runs/{run_id}/retry-failed-chunks` 只允许对存在 failed chunks 的 partial run 重新打开后续阶段。
- V3 `GET /generation-runs/{run_id}/atoms`、`GET /generation-runs/{run_id}/cases` 返回短期结果。
- V3 `GET /generation-runs/{run_id}/artifacts` 返回短期产物元数据，`GET /generation-runs/{run_id}/artifacts/{artifact_key}` 预览或下载已校验文件。
- V3 `POST /generation-runs/{run_id}/artifacts/retry` 只重跑确定性产物渲染；`POST /generation-runs/{run_id}/export` 保留为 workbook 下载兼容入口，均不接收前端提交的 cases/blueprint/stats。
- 旧 `POST /api/v1/test-cases/generate` 若保留，必须明确不支持 V3 全量生成，不能被前端主流程依赖。
- 响应结构沿用当前项目 API 风格。

## 16. 权限、安全与错误规则

- 页面入口对当前项目成员可见。
- 后端优先使用严格项目成员校验，避免 Token 指向非成员项目时静默回退。
- 案例库和画像按项目隔离。
- Generation Run 详情按项目隔离并在 TTL 内短期保存；TTL 清理后不再提供 atoms/cases/audit detail，只保留最小审计。
- 飞书权限不足时沿用授权卡片和 OAuth 只读授权流程。
- 所有截断、未读取图片/附件、AI 不可用、参考画像异常都必须可见。
- 不保存永久生成历史；不得保存 raw prompt、raw response、完整 provider response、API Key、token 或本地敏感路径。

## 17. 验收标准

### 17.1 正向验收

- 项目成员可以进入 `/test-cases`。
- 前端页可以在 01 数据源模块中添加策划案来源，刷新页面后仍能在来源选择区恢复当前用户在当前项目下保存的来源。
- 项目成员可以上传参考案例并在列表中看到画像摘要。
- 项目成员可以从飞书电子表格选择一个 Sheet 并读取快照。
- 项目成员可以上传 Excel、选择一个 Sheet 并读取快照。
- 快照超限时页面展示 warnings。
- 项目成员可以选择多个参考案例、一个主参考案例，并在主参考为 Excel 时选择一个主参考 Sheet。
- 未选择任何参考案例时，项目成员也可以创建 Generation Run，并得到基于 `qa-case` 标准逻辑、official atoms 和 Coverage Audit 的蓝图、用例和 warnings。
- 切换到无推荐主参考的参考案例分类时，页面不自动选择文件，并提示本次未使用参考案例增强。
- 参考案例文件过多时，页面通过搜索、筛选、排序和每页 5 条分页保持布局稳定。
- 点击“全量生成用例”后页面展示 Generation Run stage progress、用例表格、Coverage Audit、Case Quality Audit、Requirement Atom、warnings、统计摘要和产物选择器。
- `completed` run 已自动生成可下载 Excel，至少包含 `测试用例`、`用例蓝图`、`生成说明`、`覆盖审计` 四个 Sheet，同时可选择预览/下载 blueprint、stats、coverage、quality 文件。
- `partial_completed` 非 strict run 可生成 workbook 并显著提示限制；strict mode 下存在覆盖或质量阻塞项时 workbook 被阻塞，审计文件仍可预览下载。
- 刷新页面后可通过最近 run id 恢复 TTL 内的 active/latest Generation Run。

### 17.2 权限验收

- 普通项目成员可以查看、使用、创建分类、上传参考案例。
- 普通项目成员不能删除参考案例、重命名分类、删除分类或设置推荐主参考。
- 项目管理员可以删除参考案例、重命名分类、删除分类和设置推荐主参考。
- 非项目成员不能读取当前项目案例库、快照、生成或导出。
- 不同项目之间参考案例不可见。

### 17.3 安全验收

- 项目级 AI 未配置时，生成失败并提示联系项目管理员。
- AI 快照整理稿失败时，页面保留原始快照并提示可重新整理；错误详情只能使用脱敏摘要。
- 任何错误、页面、日志和导出文件都不展示完整 API Key。
- 图片、原型图或附件未读取时，warnings 或备注中能看到限制说明。
- 后端只保存短期 Generation Run 详情和最小审计，不保存永久生成历史或 raw prompt/provider response。

## 18. 测试覆盖要求

实现时至少覆盖：

- 策划案快照：空 Sheet、超行、超列、超长单元格、空行过滤、图片/附件未读提示、warnings。
- AI 快照整理稿：读取快照后自动非阻塞触发、失败不清空原始快照、重新整理、Markdown 阅读稿可复制、生成时仅作为辅助上下文。
- 飞书来源：权限已授权、权限不足、授权复用、非法链接、metadata 失败。
- Excel 来源：格式限制、大小限制、Sheet 不存在、公式/空值读取。
- 参考案例画像：Excel 多 Sheet 列表、主参考 Sheet 选择、表头定位、标题层级、优先级风格、Markdown/TXT 摘要。
- 参考案例权限：非项目成员拒绝、跨项目不可读、普通成员和项目管理员维护权限差异。
- Full Planning Sheet Context：超过旧 snapshot 行数/字符限制仍保留完整 selected sheet facts，已采纳视觉证据只允许同 sheet 进入。
- Generation Run：创建 queued、轮询阶段、取消、TTL expired、failed chunk retry、跨项目隔离和非成员拒绝。
- Requirement Atom：chunk 抽取、非法 JSON 容错、去重合并、unfounded candidate 不计入 official atom set。
- Blueprint/Cases：只从 official atoms 生成，正式用例必须引用 atom id，无依据 case 进入 audit candidates。
- Coverage Audit：covered/uncovered atom 计算、单轮 supplement、strict/non-strict export 行为、failed chunks 导致 partial。
- 产物渲染：canonical A-L 列、P0-P3、四 Sheet、五文件包、run id DB truth、前端篡改 cases 不影响文件、哈希/大小校验、strict block、确定性 retry 和脱敏。
- 前端页面：01 数据源模块、策划案来源选择、策划案 Sheet 选择、主参考 Sheet 选择、Generation Run 创建/轮询/取消/重试、warnings 展示、cases/coverage/atoms 视图、文件选择预览和已生成文件下载状态。
- 参考案例库前端页面：分类 pill 和数量、切换分类清空选择、推荐主参考默认选中、无推荐分类不自动选择、多选参考案例、设为主参考自动勾选、主参考下拉仅展示已选参考、搜索空态、文件过多时每页 5 条分页展示。

## 19. 历史边界与后续候选

用例生成 V2 的 Source Evidence 泛化、SVN/本地文件读取、`.xls` 图片转换、视觉证据采纳和校验规则已拆到 `docs/specs/test-case-generation-v2-source-evidence.md`。本文件当前以 V3 Generation Run 为主方向，以下保留为历史边界和后续候选索引。

- 飞书文档、图片、原型图和文档附件理解。
- 本地文件和 SVN 文件通过 `Source Evidence Run` 读取策划案文本、表格和图片资源；workbook run 保留可见 Sheet 与资源清单，V3 `Generation Run` 按当前 `Planning Sheet` 构建 full context；旧 `Planning Sheet Snapshot` 只保留预览和兼容用途。
- `.xls` 内嵌图片进入 V2.0 首批范围，通过受控 `.xls -> .xlsx` 转换后复用图片解析能力。
- `Source Evidence Run`：允许为飞书文档读取、图片/附件下载、视觉证据包和 observation 短期保存来源证据；按项目隔离，默认 7 天 TTL 自动清理，不进入生成历史。
- `Source Evidence Run` TTL 到期清理时必须删除原文快照、图片/附件文件、视觉证据包和 observation 详情；只保留最小审计元数据，例如 run id、项目、来源标识、资源文件名、状态、操作人、创建时间和清理时间。最小审计元数据不随 7 天 TTL 删除，按项目审计数据保留策略保留。
- 项目审计数据保留策略 V2 不新增独立项目配置页；沿用项目审计默认策略。只有超级管理员可配置全局默认值，项目管理员只能查看，不允许按项目覆盖审计保留期限。
- 项目管理员可以查看本项目的 `Source Evidence Cleanup Audit Summary`，但不能查看已清理内容、视觉证据包或 observation 明细。摘要字段限定为 run id、来源标识、资源文件名、状态、创建时间、清理时间和操作人。普通项目成员不能查看项目级清理记录列表，只在当前页面遇到过期证据时看到“证据已清理/需重新读取来源”的状态提示。
- TTL 清理触发机制采用“后台定时清理 + 访问时懒清理”双保险：后台任务负责批量清理过期 run；页面/API 访问到过期 run 时必须先执行过期判定并立即转为已清理状态，避免定时任务延迟导致过期证据继续可见。
- 页面和导出文件在 TTL 内可以引用 `Adopted Visual Evidence` 做证据复查；TTL 到期后不再提供证据复查或 observation 明细查看，只能展示证据已过期/已清理状态，用户需要重新读取来源后再复查或重新生成。
- `Source Evidence Run` 的飞书读取主体使用项目级 `Project Feishu Service Identity`，不使用当前登录用户个人 OAuth token 作为长期读取身份；用户只触发读取、授权申请或重试。
- `Visual Observation Selection`：图片/附件先形成资源清单，再由系统按文档位置、文件类型、文件名、附近文本、重复度和预算推荐观察集合，用户可增删选择；V2 不默认全量观察所有图片或附件。
- `Adopted Visual Evidence`：视觉 observation 结果必须先预览，经用户确认采纳后才能进入生成依据；未确认的 observation 记录为“已观察未采纳”，不得进入蓝图、用例或需求追踪。
- 项目级 Vision AI 凭据：视觉理解使用独立的 `Project Vision AI Credential`，不复用文本生成用的项目级 AI 凭据。
- Vision AI 凭据缺失或不可用时，飞书正文、表格和资源清单读取仍允许继续；图片、原型图和附件只能标记为“待观察图片/附件”，不得参与语义生成或被写成已确认需求依据。
- Word、PDF、XMind 等更多策划案输入格式。
- XMind 导出。
- Feishu 表格写回。
- 跨项目只读参考案例库。
- 项目级 QA 知识库：知识上传、审核、版本、检索、命中解释、项目隔离和权限控制。
- 从 QA Workspace `knowledge_base/knowledge/` 导入已审阅知识，并建立来源、审阅人和更新时间。
- 生成时引入知识命中记录，展示“已使用知识 / 未找到相关知识 / 知识可能过期”。
- 生成历史、结果比对、清理策略和审计。
- 蓝图编辑和二次生成协议。

## 19.1 V1 延期清单

以下点全部不进入 V1，但需要在后续设计中单独评估：

- 可维护 QA 知识库的数据模型、维护页面和项目权限。
- 知识审核流、发布状态、回滚和版本历史。
- 知识来源登记、引用证据、审阅人、适用项目和过期策略。
- 知识检索、相关性排序、命中解释和无命中提示。
- 知识与参考案例库的边界：知识补充测试经验，参考案例只补充输出格式和历史风格。
- 知识对生成 prompt 的注入预算、优先级、冲突处理和脱敏策略。
- 知识使用记录是否随生成结果展示、导出或审计。
- 从 QA Workspace 导入知识时的格式兼容、人工确认和跨系统同步策略。
- 图片/附件语义理解与知识库联动。
- 生成历史、结果比对和知识版本变更后的重复生成对比。
- `Source Evidence Run` 存储、清理、权限、审计和敏感内容处理；默认 7 天 TTL，到期删除原文快照、图片/附件文件、视觉包和 observation 详情，仅保留最小审计元数据；最小审计元数据不随 7 天 TTL 删除，按项目审计数据保留策略保留；V2 不做独立项目配置页，超级管理员可配置全局默认值，项目管理员只读查看；项目管理员可查看本项目清理记录摘要，字段限定为 run id、来源标识、资源文件名、状态、创建时间、清理时间和操作人，不得查看已清理内容或 observation 明细；普通项目成员不能查看项目级清理记录列表，只在当前页面遇到过期证据时看到状态提示；清理触发采用后台定时清理和访问时懒清理双保险；它区别于生成历史和项目级 QA 知识库。
- 飞书来源授权主体：`Source Evidence Run` 读取正文、表格、图片和附件时使用项目级 App/Bot 身份；权限不足时记录待授权资源并通过项目级机器人/授权卡片方向申请，不保存个人 OAuth token 作为长期读取凭据。
- `Project Vision AI Credential` 的配置、状态展示、权限、测试连接、模型能力校验、成本提示和不可用降级策略。
- 视觉不可用降级：未配置或不可用时返回“文本/表格 + 资源清单 + 待观察图片/附件”，页面和导出说明必须提示“视觉模型未配置，图片/附件未参与语义理解”；同一个未过期 `Source Evidence Run` 可在后续配置 Vision AI 后重新执行 observation。
- 视觉观察选择：前端需要展示完整资源清单、系统推荐观察项、选择原因、预算/成本提示和用户调整入口；只有被观察且校验通过的资源可作为图片语义依据，未选择或未观察资源继续保持“待观察”。
- 视觉证据采纳：observation 完成后先展示模型观察结果、关联资源、来源位置和风险提示；用户确认后才形成 `Adopted Visual Evidence` 并进入生成上下文。已观察但未采纳的资源可保留在 `Source Evidence Run` 中用于复核，但不得影响本次生成。

## 19.2 qa-case 移植 V1 不做清单

以下功能来自 `qa-case` / QA Workspace 的完整工作流，但当前产品 V1 不实现。每一项都需要保留后续升级扩展点，避免 V1 代码把能力写死：

| qa-case 能力 | V1 不做内容 | 后续扩展预留 |
|---|---|---|
| QA Workspace preflight / setup / role / Git 快进检查 | 不移植 `uv run qa preflight --json`、本机 `.qa_workspace.local`、user/developer profile、Git 远端检查 | 如未来接入外部 QA Workspace，同步走独立 adapter，不侵入当前项目登录和项目权限 |
| 任务目录 `tasks/<task>`、manifest、inputs、summary | V1 不创建本地任务目录，不保存原始来源文件或任务运行现场 | 预留 `generation_run` / `source_artifact` 类模型给 V2 生成历史或来源审计使用 |
| `knowledge_base/knowledge/` 审阅知识读取 | V1 不读取、导入或检索 QA Workspace 知识库 | 预留 `Project QA Knowledge Library`，后续做知识导入、审核、版本和检索 |
| `knowledge_base/knowledge_local/drafts` 草案与知识沉淀 | V1 不做知识草案、知识提升、review packet 或知识维护流 | V2 需要独立知识审核和发布状态，不允许直接把生成结果沉淀为正式知识 |
| context-reading 统一来源登记 | V1 只读取当前页面选择的 Planning Sheet Snapshot，不把 Feishu/Jira/本地材料写入统一 `sources/` 目录 | 预留来源登记抽象，后续支持多来源、来源状态、来源证据和追踪 |
| Jira 来源读取 | V1 不读取 Jira，也不修改 Jira 状态、评论或字段 | V2 可新增只读 Jira source connector，并把 Jira key 纳入需求追踪 |
| 配置 SVN、服务器代码、Trino/Data MCP 上下文 | V1 不读取配置工作副本、服务器代码或数据查询上下文 | V2 以 source connector 方式接入，必须标明只读、权限和成本 |
| `coupling-test-point-generation` 产物承接 | V1 不要求已有耦合测试点产物，也不读取 QA Workspace 测试点任务目录 | V2 可允许导入已确认测试点，作为 `confirmed_test_points` 输入并参与追踪 |
| 图片/附件视觉证据流程 | V1 不执行 `visual prepare/list/packet/observe/validate`，不下载或理解图片/附件语义 | V2 需要 `Source Evidence Run`、Visual Evidence 模型、observation、引用校验和导出标注；来源证据允许按项目隔离短期保存，默认 7 天 TTL 自动清理，不进入生成历史；到期删除原文快照、图片/附件文件、视觉包和 observation 详情，仅保留最小审计元数据；最小审计元数据不随 7 天 TTL 删除，按项目审计数据保留策略保留；V2 不做独立项目配置页，超级管理员可配置全局默认值，项目管理员只读查看；项目管理员可查看本项目清理记录摘要，但不能查看已清理内容、视觉包或 observation 明细；普通项目成员不能查看项目级清理记录列表，只在当前页面遇到过期证据时看到状态提示；清理触发采用后台定时清理和访问时懒清理双保险；视觉 observation 使用独立 `Project Vision AI Credential`；Vision 不可用时降级为文本/表格、资源清单和待观察图片/附件，不得把图片内容当作已理解需求；观察采用“资源清单先出 + 系统推荐 + 用户可调整”的 `Visual Observation Selection`，不默认全量观察；observation 结果必须经用户确认成为 `Adopted Visual Evidence` 后才进入生成依据；TTL 内页面和导出可引用已采纳视觉证据，TTL 后不提供证据复查，需要重新读取来源 |
| 飞书图片/附件编辑权限自动申请 | V1 不为图片/附件下载申请当前用户编辑权限；只保留现有表格读取授权能力 | V2 图片理解若需要权限，应接入独立权限状态和重试流程，并把权限状态绑定到 `Source Evidence Run`；授权目标是项目级 `Project Feishu Service Identity`，当前用户只触发申请，不作为长期读取身份 |
| AI-owned Feishu 表交付物 | V1 不新建 Feishu 表作为 AI 交付物，也不写回既有 Feishu 表 | V2 可做 Export Target 抽象，区分 Excel 下载、AI-owned Feishu、新建文档等目标 |
| CSV / Markdown / Feishu 友好文本输出 | V1 只做页面预览和 Excel 导出 | V2 可扩展 `export_format`，但必须复用同一结构化用例结果 |
| 双层表头和模块行继承格式 | V1 采用标准字段兜底，不强制生成双层表头、模块行或空白继承语义 | V2 可做 Export Template/Profile，按项目模板选择表头和模块行策略 |
| 执行版本列、测试人员列、设备列等执行维度 | V1 只提供基础执行状态和标准字段，不做多版本/多人执行矩阵 | V2 可作为导出模板字段，不影响生成主链路 |
| 只补充某模块/变更影响范围 | V1 默认围绕整个 Planning Sheet 生成，不提供局部补充模式 | V2 可加 `scope_mode`、模块选择和变更影响范围输入 |
| 交互式澄清 / 待确认问题闭环 | V1 只返回待确认问题，不保存问题状态，也不支持答复后继续生成 | V2 可设计蓝图确认、问题答复和二次生成协议 |
| 需求来源完整证据包 | V1 只保留快照和 warnings，不保存完整原始文档、图片、附件和证据包 | V2 通过 `Source Evidence Run` 短期保存来源证据；它不等同于生成历史，到期后不再提供原文、图片/附件、视觉包和 observation 详情复查，只保留最小审计元数据；最小审计元数据不随 7 天 TTL 删除，按项目审计数据保留策略保留 |
| 未映射需求 / 无依据测试点复核工作台 | V1 通过 warnings 和导出蓝图保留，不提供单独复核、认领或处理状态 | V2 可加入人工复核状态和重新生成入口 |
| 外部系统只读检查步骤 | V1 生成的操作步骤不会自动调用外部系统做只读验证 | V2 可扩展为验证建议或只读检查插件，但不能修改外部系统 |
| 知识与图片观察联动沉淀 | V1 不把图片观察、生成经验或人工备注沉淀为知识 | V2 必须经过知识审核流后才能进入项目级知识库 |
| 生成结果覆盖检查 | V1 不在生成后自动跑覆盖统计或覆盖率报告 | V2 可接入覆盖检查能力，基于导出的用例结构计算覆盖情况 |
| QA Workspace CLI 直接复用 | V1 不 shell 调用 `uv run qa ...`，避免引入外部仓库、Git 状态和本机 profile 依赖 | V2 若复用，也应通过受控服务 adapter，而不是从 Web 请求直接执行本地 CLI |

## 20. 维护检查清单

- 修改用例生成需求时，同步本文件。
- 涉及实施步骤时，同步 `docs/superpowers/plans/2026-06-22-test-case-generation.md` 或新增后续计划。
- 新增术语时只把稳定领域词放入 `CONTEXT.md`，不写接口、表名或组件名。
- 用户可见行为变化后同步 `CHANGELOG.md`。
- 每个实现切片完成后追加 `PROJECT_RECORD.md`。
