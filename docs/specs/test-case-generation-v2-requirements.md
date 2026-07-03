# 用例生成 V2 需求文档

## 0. 文档状态

| 项 | 内容 |
|---|---|
| 版本 | V2.0 |
| 状态 | 已实现主体链路，验收中 |
| 关联 ADR | `docs/adr/0002-generalize-source-evidence-for-test-case-generation-v2.md` |
| 关联技术规格 | `docs/specs/test-case-generation-v2-source-evidence.md` |
| 分步执行提示词 | `docs/superpowers/plans/2026-07-01-test-case-generation-v2-source-evidence-codex-prompts.md` |
| 主要范围 | 飞书文档、本地文件、SVN 文件统一通过 `Source Evidence Run` 读取文本、表格和图片证据 |
| 首批硬要求 | SVN 文档和本地文件都支持读取图片；`.xls` 内嵌图片必须支持 |

当前 Source Evidence Sheet 口径：

- `Source Evidence Run` 保留 workbook/sheets 的可见 Sheet 全量读取结果和完整资源清单。
- `Source Evidence Run` 是 V3 的来源基础，不等于 V3 `Generation Run`；V3 由 Generation Run 消费当前选择的 `Planning Sheet` full context。
- `Planning Sheet Snapshot` 只保留为预览/兼容接口；Generation Run 和导出按当前选择的单个 `Planning Sheet` 收敛。
- 当前 Sheet 内可观察图片会默认进入 observation candidates 的选中集合，但不会自动观察或自动采纳。

## 1. 背景

用例生成 V1 曾具备项目级用例生成页面、策划案 Sheet 快照、项目级 AI 生成、参考案例库和 Excel 导出能力，但 V1 的读取模型以 `Planning Sheet Snapshot` 为核心，只面向单 Sheet 文本，不读取图片、附件或文档块语义。

飞书文档富读取迁移已经引入 `Source Evidence Run`、资源清单、视觉观察、采纳视觉证据和 TTL 清理能力。V2 主体链路已扩展到本地文件和 SVN 文件，用于解决策划案中截图、原型图、流程图和 Excel 内嵌图片无法参与测试设计的问题。

## 2. 当前代码与文档现状

已具备：

- 后端已有 `Source Evidence Run`、resource、visual observation、adopted visual evidence、TTL 清理和生成接入基础。
- V3 `Generation Run` 已以 `source_evidence_run_id + planning_sheet_name` 消费 Source Evidence，并限制 adopted evidence 必须通过当前项目/run/sheet 校验。
- 飞书富读取已支持 docx/wiki/sheets/bitable 的文本、表格和资源清单。
- 前端用例生成页已把“本地文件 / SVN 文件 / 飞书文档”三入口统一到 Source Evidence Run 状态、资源清单、视觉观察、采纳、生成和导出链路。
- 项目已有 `openpyxl`、`xlrd`、`pillow` 依赖，并已实现 `.xlsx` 文本/图片、`.xls` 文本和受控 `.xls -> .xlsx` 图片转换路径。
- 后端已实现 `svn_file` 项目级 SVN 凭据、`Source Evidence SVN Root` 校验和 run 内 `raw/svn-cache` 副本读取。
- 运行能力接口已展示项目级 SVN 凭据、Source Evidence SVN Root、Vision AI 和 LibreOffice/soffice 可用性。

主要不足：

- 真实环境验收仍依赖部署侧配置：`SOURCE_EVIDENCE_SOFFICE_EXECUTABLE`、项目级 SVN 凭据、Source Evidence SVN Root、Project Vision AI Credential 和可访问的飞书文档。
- 自动化已覆盖 fake converter 与 SVN reader 边界；真实 LibreOffice/soffice、真实 SVN `.xls` 和真实 Vision observation 仍需要环境样例验收。
- `PlanningSnapshotRequest.source_type = feishu | uploaded_excel` 仍仅用于 V1 兼容，不能承载 V2 图片证据；V2 新入口必须走 Source Evidence Run。

## 3. 目标

V2.0 的目标是把用例生成来源读取统一升级为短期来源证据会话：

- 用户可以从飞书文档、本地文件或 SVN 文件创建 `Source Evidence Run`。
- 系统读取文本、表格、图片资源和来源摘要。
- 图片先进入资源清单，再由用户选择、Vision 观察、人工采纳。
- 只有 `Adopted Visual Evidence` 可以进入生成上下文和导出说明。
- 对 workbook/sheets 来源，一次 V3 `Generation Run` 只以当前 `Planning Sheet` 为需求范围。
- `.xls` 内嵌图片在首批版本中可被提取、登记和观察。
- 旧 V1 `Planning Sheet Snapshot` 保留兼容，但不再作为 V2 新来源主链路。

## 4. 用户角色

| 角色 | V2 能力 |
|---|---|
| 项目成员 | 创建 Source Evidence Run、读取来源、查看资源清单、选择图片、发起视觉观察、采纳/撤销自己的本次证据、创建 Generation Run 并导出用例 |
| 项目管理员 | 拥有项目成员能力；可配置或查看 SVN、Vision、LibreOffice 相关运行能力状态；可查看 source evidence cleanup audit summary |
| 超级管理员 | 拥有项目管理员能力；可配置全局默认 TTL、运行能力和系统级依赖 |
| 非项目成员 | 不可访问当前项目的 source evidence、视觉证据、生成或导出能力 |

## 5. 范围

### 5.1 必须支持

- 来源类型：
  - 飞书文档：`feishu`
  - 本地文件上传：`local_file`
  - SVN 文件：`svn_file`
- 文件格式：
  - `.xlsx`
  - `.xls`
  - 独立图片 `.png`、`.jpg`、`.jpeg`、`.webp`
- Excel 读取：
  - 读取可见 Sheet 的文本和表格，并在 run 内保留完整 parsed source。
  - 读取 `.xlsx` 内嵌图片。
  - 读取 `.xls` 内嵌图片。
  - 隐藏 Sheet 默认排除并产生 warning。
  - snapshot 预览、Generation Run 和 export 按当前选择的单个 `Planning Sheet` 收敛。
- 视觉证据：
  - 资源清单。
  - 系统推荐观察项。
  - 用户调整选择。
  - Vision observation。
  - 人工采纳为 `Adopted Visual Evidence`。
  - Generation Run/export 前 `visual validate`。
- 安全与清理：
  - Source Evidence Run 默认 7 天 TTL。
  - 到期删除原文快照、图片/附件文件、转换产物、视觉包和 observation 详情。
  - 仅保留最小审计元数据。

### 5.2 明确不支持

- V2.0 不支持 `.docx` 本地或 SVN 文件读取；飞书 docx/wiki 仍按现有飞书富读取链路处理。
- V2.0 不支持 PDF、XMind、压缩包、多文件目录递归读取。
- 不自动观察或自动采纳全部图片；当前 Sheet 图片默认选中只表示 observation candidate 初始值。
- 不允许未采纳图片进入生成依据。
- 不重算 Excel 公式。
- 不修改原始本地文件、SVN 文件或飞书文档。
- 不把 Source Evidence Run 做成生成历史、永久源文件库或项目 QA 知识库。
- 不使用个人 SVN 凭据创建项目级可见证据。

## 6. 核心用户流程

```text
进入“用例生成”页
-> 选择来源入口：本地文件 / SVN 文件 / 飞书文档
-> 创建 Source Evidence Run
-> 后端读取来源文本、表格、资源清单和 warnings
-> 页面展示来源状态、TTL、资源数量、warnings
-> 如果来源是 workbook/sheets，默认选择第一张可用 Sheet，用户可切换当前 Planning Sheet
-> 用户查看资源清单
-> 系统推荐图片观察集合；当前 Sheet 图片默认选中，用户可增删选择
-> 用户发起 Vision observation
-> 页面展示 observation 结果和风险提示
-> 用户确认采纳为 Adopted Visual Evidence
-> 用户可读取 Planning Sheet Snapshot / AI 整理稿作为来源预览
-> 用户创建 Generation Run
-> 后端执行 visual validate、构建 Full Planning Sheet Context、抽取 Requirement Atom、生成蓝图和用例
-> 用户预览结果并导出 Excel
```

## 7. 来源读取需求

### 7.1 飞书文档

- 沿用现有飞书富读取能力。
- 读取主体使用项目级 `Project Feishu Service Identity`。
- 权限不足时进入 Source Evidence 授权和重试流程。
- 飞书图片、附件和表格资源必须登记到 resource 清单。

### 7.2 本地文件

- 用例生成 V2 新增专用上传创建入口，不复用 `/sources/upload` 作为长期数据源配置。
- 上传成功后直接创建 `local_file` Source Evidence Run。
- 本地上传文件进入当前 run 的短期证据存储，随 TTL 清理。
- 独立图片文件可以创建 run；如果没有文本主体，必须先观察并采纳视觉证据后才能生成。

### 7.3 SVN 文件

- `svn_file` 必须使用项目级 SVN 凭据。
- SVN URL 必须位于项目管理员批准的 `Source Evidence SVN Root` 内。
- 后端读取时记录 SVN URL、revision 或 last changed rev、文件 hash 和读取时间。
- SVN 文件先缓存到受控目录，再复用本地文件 reader。
- 个人 SVN 凭据读取的内容不得成为项目级共享 Source Evidence Run。

## 8. Excel 与图片需求

### 8.1 `.xlsx`

- 使用 `openpyxl` 读取文本、表格和内嵌图片。
- 图片需写入 run 内 `images/` 或等价目录。
- 每个图片必须有稳定 ref、来源 Sheet、位置描述和资源状态。
- run response 必须暴露可见 Sheet 的 `sheet_options`，前端用它作为 Sheet selector 的唯一来源。
- snapshot 只返回当前 Sheet 的文本、表格和位于该 Sheet 的图片/附件资源行。

### 8.2 `.xls`

`.xls` 内嵌图片是首批必须支持能力。

需求规则：

- `.xls` 文本读取继续使用 `xlrd`。
- `.xls` 图片读取通过受控 LibreOffice headless / `soffice` 转换为 `.xlsx` 后复用 `.xlsx` 图片解析。
- `soffice` 可执行文件只能由服务端配置，不能由请求指定。
- 转换产物只保存在当前 run 目录，例如 `raw/converted/source.xlsx`。
- 转换进程必须有超时、独立临时 profile、输出目录限制和错误脱敏。
- 不执行宏，不联网，不跟随外部链接。
- 转换失败时：
  - 如果文本主体可读，run 状态仍可为 `ready`。
  - 页面和导出说明必须展示图片未参与理解的 warning。
  - 失败图片不得进入视觉证据或 prompt。

### 8.3 图片 ref 与位置

推荐 ref：

- Excel 内嵌图片：`excel_img_s001_001`
- 独立本地图片：`local_img_001`
- 独立 SVN 图片：`svn_img_001`

推荐 position：

- 有锚点：`excel:sheet=活动配置:image=1:anchor=B12`
- 无锚点：`excel:sheet=活动配置:image=1:anchor=unknown`

无法稳定定位时，至少保留 Sheet、图片序号、附近文本或估计位置，并产生 warning。

## 9. 视觉证据需求

- 图片和附件默认只是资源，不是需求事实。
- 系统可以基于文档位置、文件类型、文件名、附近文本、重复度和预算推荐观察集合。
- 对 workbook/sheets 来源，当前 Sheet 内可观察且 ready/selectable 的图片默认选中；其他 Sheet 图片仍可手动选择，但不会默认选中。
- 用户必须能调整观察集合。
- observation 结果必须先展示给用户。
- 用户确认采纳后才形成 `Adopted Visual Evidence`。
- 已观察但未采纳的内容不得进入蓝图、用例、需求追踪或导出说明中的已确认依据。
- 用户可以撤销已采纳视觉证据；撤销后后续生成不得继续使用该证据。
- Vision AI 不可用时，文本/表格生成继续可用，但图片必须显示为未参与理解。

## 10. 生成与导出需求

V3 `Generation Run` 使用视觉证据前必须执行 `visual validate`：

阻塞条件：

- 请求传入的 adopted evidence id 不存在。
- adopted evidence 不属于当前 run。
- adopted evidence 已过期、已撤销或未采纳。
- adopted evidence 不属于当前 `Planning Sheet`。
- Full Planning Sheet Context、Requirement Atom、用例或导出说明引用了未采纳图片 ref。

warning 条件：

- 存在未观察图片。
- 存在图片提取失败。
- `.xls` 转换失败。
- Vision AI 未配置或不可用。

导出要求：

- 导出说明 Sheet 必须包含来源摘要、当前 Sheet 名、Generation Run 状态、Source Evidence Run 状态、TTL 状态、当前 Sheet 图片参与情况和 adopted visual evidence 摘要。
- 导出文件不得包含原图文件、完整 observation provider response、API Key、Base URL 密钥或本地敏感路径。
- TTL 到期后，不再提供视觉证据详情复查；用户需要重新读取来源。

## 11. 前端需求

用例生成页 01 区域保留三入口，但统一进入 Source Evidence 流程：

- 本地文件。
- SVN 文件。
- 飞书文档。

页面必须展示：

- 来源标题和来源类型。
- run 状态。
- TTL 或过期提示。
- warnings。
- 文本/表格读取摘要。
- 图片/附件资源数量。
- 资源清单抽屉。
- 视觉选择状态。
- observation 状态。
- adopted visual evidence 状态。
- 重试入口。

交互要求：

- 本地/SVN/飞书三入口创建 run 后的状态展示一致。
- workbook/sheets Source Evidence run 必须显示 Sheet selector，并默认选择后端 `is_default` Sheet 或第一张可用 Sheet。
- 切换 Source Evidence Sheet 必须清空旧 snapshot、AI 整理稿、当前 Generation Run 结果和导出可用态，并重新拉取当前 Sheet 的视觉候选。
- 读取快照预览、创建 Generation Run 和导出按钮必须感知 run 状态、TTL、视觉校验结果。
- 用户切换来源后，旧生成结果失效。
- 独立图片 run 在没有 adopted visual evidence 前不允许生成。
- Vision 或转换器不可用时，提示必须明确，不能让用户误以为图片已参与理解。

## 12. 后端接口需求

当前接口形态：

| 接口 | 用途 |
|---|---|
| `POST /api/v1/test-cases/source-evidence-runs` | 创建 `feishu` 或 `svn_file` run |
| `POST /api/v1/test-cases/source-evidence-runs/upload` | 上传本地文件并创建 `local_file` run |
| `GET /api/v1/test-cases/source-evidence-runs/{run_id}` | 查询 run 状态；workbook/sheets run 返回 `sheet_options` |
| `GET /api/v1/test-cases/source-evidence-runs/{run_id}/resources` | 查询资源清单 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/retry` | 重试读取 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/snapshot` | 构建当前 `Planning Sheet Snapshot` 预览；workbook/sheets run 支持 body `sheet_name` |
| `GET /api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates` | 查询或懒生成视觉候选；支持 query `sheet_name` |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections` | 保存视觉观察选择；支持 body `sheet_name` |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/observations` | 执行 Vision observation |
| `GET /api/v1/test-cases/source-evidence-runs/{run_id}/observations` | 查询 observation 安全摘要 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence` | 采纳视觉证据 |
| `DELETE /api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence/{evidence_id}` | 撤销采纳 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request` | 对飞书 Source Evidence Run 显式发送源文档授权申请 |
| `GET /api/v1/test-cases/source-evidence-authorizations/oauth/callback` | Source Evidence 专用 OAuth callback |
| `GET /api/v1/test-cases/source-evidence-authorizations` | 项目管理员查看飞书 Source Evidence 授权审计摘要 |
| `POST /api/v1/test-cases/source-evidence-authorizations/{authorization_id}/invalidate` | 项目管理员手动失效本系统授权复用记录 |
| `GET /api/v1/test-cases/source-evidence-capabilities` | 查询 Source Evidence 运行能力状态 |
| `GET /api/v1/test-cases/source-evidence-cleanup-audits` | 项目管理员查看清理审计摘要 |

契约要求：

- JSON 创建请求的 `source_type` 支持 `feishu | svn_file`；`local_file` 只能通过上传接口创建，响应中的 run `source_type` 为 `local_file`。
- `local_file` 不要求也不允许 JSON 创建携带本地绝对路径。
- `svn_file` 创建请求必须包含 SVN URL，并通过项目级 root 校验。
- 多 Sheet workbook/sheets snapshot 缺少 `sheet_name` 时返回错误；单 Sheet run 可默认唯一 Sheet；非 Sheet 来源继续兼容旧行为。
- V3 Generation Run create 请求携带 `source_evidence_run_id` 和 `planning_sheet_name`；旧 snapshot endpoint 只作为预览/兼容入口。
- 所有接口必须校验当前用户是项目成员。
- 管理性配置和审计列表必须校验项目管理员或超级管理员身份。

## 13. 运行能力与配置需求

系统需要展示并校验以下运行能力：

- 项目级 SVN 凭据。
- `Source Evidence SVN Root`。
- Project Vision AI Credential。
- LibreOffice/soffice 转换器。

普通项目成员看到可用性和处理建议；管理员看到配置入口或测试连接入口。错误响应、日志和导出文件不得泄露密钥、完整命令行、provider response 或本地敏感路径。

## 14. 权限与安全需求

- Source Evidence Run 按项目隔离。
- 证据内容只在 TTL 内可复查。
- 过期后清理原文、图片、附件、转换产物、视觉包和 observation 详情。
- 最小审计元数据不随 TTL 删除，按项目审计保留策略处理。
- 项目管理员可查看 cleanup audit summary，但不能查看已清理内容。
- 普通成员不能查看项目级清理列表，只能在当前页面看到当前 run 已过期或已清理。
- 不保存生成历史，不把 Source Evidence Run 作为长期知识库。
- 不允许用户请求指定本地转换命令或绕过 SVN root。

## 15. 验收标准

### 15.1 正向验收

- 项目成员可以上传 `.xlsx`，读取文本、表格和内嵌图片资源。
- 项目成员可以在多 Sheet workbook run 中选择当前 Sheet，snapshot 只包含该 Sheet 的文本、表格和图片资源行。
- 项目成员可以上传 `.xls`，读取文本，并通过转换读取内嵌图片资源。
- 项目成员可以通过 SVN URL 创建 `.xls` Source Evidence Run，并读取文本和内嵌图片。
- 项目成员可以上传独立图片，先观察并采纳，再生成用例。
- 飞书文档读取、资源清单、视觉观察和采纳流程保持可用。
- 用户可以看到图片资源清单、选择图片、执行观察、采纳视觉证据。
- 当前 Sheet 图片候选默认选中；用户取消或跨 Sheet 手动选择后，后端只观察已保存的 `selected_refs`。
- 采纳后的视觉证据可以进入 V3 full context、Requirement Atom 和导出说明。
- 当前 Sheet 的已采纳视觉证据可以进入 V3 full context 和导出说明，跨 Sheet 已采纳证据会被阻塞。
- 未采纳图片不会进入生成依据。
- 生成结果包含来自文本/表格和已采纳视觉证据的测试点。
- 导出 Excel 中能看到 Source Evidence 摘要和视觉证据使用说明。

### 15.2 降级验收

- LibreOffice/soffice 未配置时，`.xls` 文本仍可读取，图片读取显示 warning。
- `.xls` 转换失败时，文本可读则 run 仍可用于纯文本生成。
- Vision AI 未配置时，文本/表格生成仍可用，图片标记为未参与语义理解。
- 存在未观察图片时，生成允许继续但必须提示 warning。
- adopted evidence id 无效时，生成和导出必须阻塞。
- adopted evidence 属于其他 Sheet 时，生成和导出必须阻塞。

### 15.3 安全验收

- 非项目成员不能访问 run、resource、observation、adopted evidence、生成或导出。
- 个人 SVN 凭据不会创建项目级共享 Source Evidence Run。
- 请求中的 SVN URL 超出 `Source Evidence SVN Root` 时被拒绝。
- TTL 到期后原图、转换产物和 observation 详情不可复查。
- 错误信息不暴露 API Key、SVN 密码、完整本地敏感路径或完整 provider response。

## 16. 测试覆盖要求

后端：

- `feishu` 创建和旧行为不回归。
- `local_file` 上传 `.xlsx` 成功。
- `local_file` 上传 `.xls` 转换成功。
- `local_file` 上传 `.xls` 转换失败但文本可用。
- `svn_file` root 校验成功和失败。
- SVN `.xls` 进入同一本地 reader。
- 独立图片 run 未采纳前不能生成。
- adopted evidence 无效时 Generation Run/export 阻塞。
- 多 Sheet Source Evidence snapshot 预览、Generation Run 和 export 按当前 Planning Sheet 收敛。
- 当前 Sheet 视觉候选默认选中和手动选择保存。
- 未采纳图片 ref 不进入 prompt。
- TTL 清理删除转换产物和视觉详情。

前端：

- 三入口都能创建或展示 Source Evidence Run。
- 本地/SVN/飞书 run 状态展示一致。
- 资源清单、视觉选择、观察、采纳、撤销状态正确。
- workbook/sheets Source Evidence run 的 Sheet selector 默认、切换清理和 snapshot body 传参正确。
- Vision 不可用、转换器不可用、图片提取失败时 warning 明确。
- 切换来源后旧生成结果失效。

真实环境：

- 至少准备一份带内嵌图片的 `.xlsx`。
- 至少准备一份带内嵌图片的 `.xls`。
- 至少准备一份 SVN `.xls`。
- 使用真实 LibreOffice/soffice 跑一次转换验收。

## 17. 实施优先级

1. 后端契约扩展：`source_type`、上传创建接口、`svn_file` 创建入口。
2. 本地文件 reader：`.xlsx` 文本/图片、独立图片。
3. `.xls` 转换器：fake converter 单测、真实 converter 手工验收。
4. SVN 接入：项目级 root 和凭据校验、缓存后复用 reader。
5. Generation Run/export `visual validate`。
6. 前端三入口统一 Source Evidence 状态和视觉流程。
7. 回归 V1 策划案快照、飞书表格、参考案例库、生成和导出。

## 18. 维护检查清单

- 修改 V2 需求时同步 `docs/specs/test-case-generation-v2-source-evidence.md`。
- 修改架构决策时同步 `docs/adr/0002-generalize-source-evidence-for-test-case-generation-v2.md` 或新增 superseding ADR。
- 新增稳定领域术语时只写入 `CONTEXT.md`，不把实现细节写进 glossary。
- 每个实现切片完成后追加 `PROJECT_RECORD.md` 并更新 `CHANGELOG.md`。
