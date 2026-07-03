# 用例生成 V2 Source Evidence 规格

## 0. Codex 快速入口

- 先读文件：`backend/app/test_cases/source_evidence.py`、`backend/app/test_cases/visual_evidence.py`、`backend/app/test_cases/planning_snapshot.py`、`backend/app/test_cases/schemas.py`、`backend/app/loaders/local_reader.py`、`backend/app/loaders/svn_cache.py`、`frontend/src/views/TestCaseGeneratorView.vue`、`frontend/src/types/testCases.ts`。
- 需求文档：`docs/specs/test-case-generation-v2-requirements.md`。
- 相关决策：`docs/adr/0002-generalize-source-evidence-for-test-case-generation-v2.md`。
- 领域术语：`CONTEXT.md` 中的 `Source Evidence Run`、`Planning Sheet`、`Planning Sheet Snapshot`、`Full Planning Sheet Context`、`Generation Run`、`Source Evidence SVN Root`、`Visual Observation Selection`、`Adopted Visual Evidence`。
- V2 目标：飞书文档、本地文件、SVN 文件都通过 `Source Evidence Run` 读取文本、表格、图片资源，并让图片只在采纳后进入用例生成。
- 不要改错方向：不要把本地/SVN V2 继续塞进旧 `planning-snapshot`；不要把用例生成 source evidence 扩成个人校验数据源能力。

## 1. 目标

V2 把用例生成来源读取从“单 Sheet 文本快照”升级为“短期来源证据会话”。用户可以从飞书文档、本地文件或 SVN 文件创建一个 `Source Evidence Run`，读取文本、表格和图片资源，经过视觉选择、观察和采纳后供 V3 `Generation Run` 消费。

`Source Evidence Run` 是来源证据会话，不是生成历史，也不等同于 `Generation Run`。V3 生成由 `Generation Run` 从当前 selected `Planning Sheet` 构建 `Full Planning Sheet Context`；Source Evidence 负责提供可校验、可清理、可脱敏的来源事实和视觉证据。

V2.0 必须支持：

- 飞书文档已有富读取链路。
- 本地上传 `.xlsx/.xls` 工作簿。
- SVN `.xlsx/.xls` 工作簿。
- `.xlsx` 内嵌图片。
- `.xls` 内嵌图片。
- 独立图片文件：`.png`、`.jpg`、`.jpeg`、`.webp`。

## 2. 非目标

- 不把 `Source Evidence Run` 做成生成历史或项目级知识库。
- 不把个人 SVN 凭据读取出的内容缓存成项目共享证据。
- 不自动观察全部图片，不让未采纳图片进入 prompt。
- 不重算 Excel 公式，不修改源文件，不写回 SVN 或飞书。
- V2.0 不承诺 `.docx`、PDF、XMind 读取；这些进入后续版本。

## 3. 来源类型

| source_type | 创建方式 | 说明 |
|---|---|---|
| `feishu` | `POST /api/v1/test-cases/source-evidence-runs` | 读取飞书 docx/wiki/sheets/bitable 支持范围，沿用项目级 Feishu 服务身份。 |
| `local_file` | `POST /api/v1/test-cases/source-evidence-runs/upload` | 上传本地文件并直接创建短期 source evidence run，不写入长期数据源配置。 |
| `svn_file` | `POST /api/v1/test-cases/source-evidence-runs` | 使用项目级 SVN 凭据和 `Source Evidence SVN Root` 校验后读取 SVN 文件。 |

旧 `PlanningSnapshotRequest.source_type = uploaded_excel | feishu` 只保留 V1 兼容。V2 页面默认不再让本地/SVN 走旧 `planning-snapshot`。

Source Evidence 实际 API 入口：

| API | 说明 |
|---|---|
| `POST /api/v1/test-cases/source-evidence-runs` | 创建 `feishu` 或 `svn_file` run。 |
| `POST /api/v1/test-cases/source-evidence-runs/upload` | 上传文件并创建 `local_file` run。 |
| `GET /api/v1/test-cases/source-evidence-runs/{run_id}` | 查询 run 摘要；workbook/sheets run 会暴露可选 `sheet_options`。 |
| `GET /api/v1/test-cases/source-evidence-runs/{run_id}/resources` | 查询资源清单安全摘要。 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/snapshot` | 构建兼容预览/旧路径的 `Planning Sheet Snapshot`；workbook/sheets run 可传 `{ "sheet_name": "..." }`。 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/retry` | 重新读取来源。 |
| `GET /api/v1/test-cases/source-evidence-runs/{run_id}/visual-candidates` | 查询或懒生成视觉候选；可传 `sheet_name` 让当前 Sheet 图片默认进入候选选中集合。 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/visual-selections` | 保存视觉观察选择；可带 `sheet_name` 记录手动选择所属 Sheet。 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/observations` | 执行 Vision observation。 |
| `GET /api/v1/test-cases/source-evidence-runs/{run_id}/observations` | 查询 observation 安全摘要。 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence` | 采纳视觉证据。 |
| `DELETE /api/v1/test-cases/source-evidence-runs/{run_id}/adopted-visual-evidence/{evidence_id}` | 撤销采纳。 |
| `POST /api/v1/test-cases/source-evidence-runs/{run_id}/authorization-request` | 对飞书 Source Evidence Run 显式发送源文档授权申请。 |
| `GET /api/v1/test-cases/source-evidence-authorizations/oauth/callback` | Source Evidence 专用 OAuth callback。 |
| `GET /api/v1/test-cases/source-evidence-authorizations` | 项目管理员查看飞书 Source Evidence 授权审计摘要。 |
| `POST /api/v1/test-cases/source-evidence-authorizations/{authorization_id}/invalidate` | 项目管理员手动失效本系统授权复用记录。 |
| `GET /api/v1/test-cases/source-evidence-capabilities` | 查询运行能力状态。 |
| `GET /api/v1/test-cases/source-evidence-cleanup-audits` | 项目管理员查看清理审计摘要。 |

飞书授权申请、OAuth callback、授权审计和失效规则的详细语义以 `docs/specs/feishu-integration.md` 为准；本规格只列出 Source Evidence 主链路实际暴露的入口。

## 4. 工作簿读取规则

- `Source Evidence Run` 读取整个工作簿的可见 Sheet，隐藏 Sheet 默认排除并写入 warning；run 内仍保留完整 parsed source 和完整资源清单。
- `SourceEvidenceRunResponse.sheet_options` 只暴露可见/可用 Sheet 摘要，默认 Sheet 是第一个可见 Sheet。
- Source Evidence 为用户当前选择的单个 `Planning Sheet` 提供来源证据：snapshot rows 仅包含该 Sheet 的文本、表格和位于该 Sheet 的图片/附件资源行；V3 `Generation Run` 消费同一 selected sheet 的 `Full Planning Sheet Context`。
- 多 Sheet workbook/sheets run 缺少 `sheet_name` 时必须返回错误；单 Sheet run 可默认唯一 Sheet；飞书 docx/wiki、独立图片等非 Sheet 来源继续使用 `sheet_name = Source Evidence` 的兼容行为。
- 资源清单安全摘要仍按 run 保留完整清单，方便资源抽屉展示和手动跨 Sheet 选择；但未观察、未采纳或跨当前 Sheet 的资源不得作为本次需求事实进入生成或导出。
- Source Evidence Snapshot 页面预览可以展示当前 Sheet 的文本/表格摘要，并按旧预览预算返回 warnings。V3 full generation 不使用旧 snapshot prompt 截断；它由 `Full Planning Sheet Context`、chunking 和 `Requirement Atom` 抽取控制 AI 输入规模。
- 单元格公式读取文件里已有的显示值或缓存值，不主动重算公式。
- `.xlsx` 使用 `openpyxl` 读取文本、表格和图片。
- `.xls` 文本继续使用 `xlrd`；图片通过受控转换 `.xls -> .xlsx` 后复用 `.xlsx` 图片解析。

## 5. `.xls` 图片转换规则

`.xls` 内嵌图片是 V2.0 首批硬要求。实现采用 LibreOffice headless / `soffice` 作为外部运行时依赖：

- 后端通过固定配置项定位 `soffice` 可执行文件，不接受请求传入命令。
- 当前配置项为 `SOURCE_EVIDENCE_SOFFICE_EXECUTABLE` 和 `SOURCE_EVIDENCE_XLS_CONVERT_TIMEOUT_SECONDS`。
- 转换输入来自已通过权限校验的本地文件或 SVN 缓存文件。
- 转换产物只写入当前 run 目录，例如 `raw/converted/source.xlsx`，随 TTL 清理。
- 转换进程必须设置超时、独立临时 profile、输出目录限制和错误脱敏。
- 不执行宏，不联网，不跟随外部链接。
- 转换失败时，文本主体仍可读取则 run 状态保持 `ready`；写入 warning，不登记伪造图片资源，不得伪装为已读取图片。

## 6. 图片资源与 ref

图片资源必须登记为 `SourceEvidenceResource`，并写入资源清单。推荐 ref 格式：

- Excel 内嵌图片：`excel_img_s001_001`、`excel_img_s002_003`。
- 独立图片文件：`local_img_001` 或 `svn_img_001`。

`position` 使用人可读定位：

- 有锚点：`excel:sheet=活动配置:image=1:anchor=B12`。
- 无稳定锚点：`excel:sheet=活动配置:image=1:anchor=unknown`。

如果 `.xls` 转换后无法稳定还原锚点，必须保留 Sheet、图片序号和附近文本/估计位置，并写入 warning。

## 7. SVN 读取边界

`svn_file` 必须使用项目级 `Source Evidence SVN Root` 和项目级 SVN 凭据：

- 请求中的 SVN URL 必须位于项目管理员批准的 root 内。
- Source Evidence SVN Root 独立存储在 `project_source_evidence_svn_roots`，字段为 `project_id`、`alias`、`display_name`、`svn_root_url`、`status`、时间戳。
- 管理接口为 `GET/PUT /api/v1/admin/projects/{project_id}/source-evidence-svn-roots`；PUT 使用 `items[].alias/display_name/svn_url/enabled` 替换式保存。
- 管理后台 `/admin` 的 Source Evidence 运行配置卡提供 Source Evidence SVN Root 保存入口；不要把它混同为飞书机器人卡中的配置表查询 `query_roots`。
- 项目级 SVN 凭据复用 `project_svn_credentials`，但读取时不得调用个人 `svn_credentials`。
- 后端记录 SVN URL、revision 或 last changed rev、文件 hash、读取时间和来源摘要。
- SVN 文件先 shallow checkout 到当前 run 的 `raw/svn-cache/<dir-hash>/`，再复用本地文件 reader；manifest 只记录 run-relative 路径，不记录 SVN 密码、完整命令行或本地绝对 cache 路径。
- 如果未来允许个人 SVN 凭据读取，run 必须限制为创建者可见；V2.0 不采用该模式。

`Remote SVN Query Root` 只用于配置表查询，不得复用为用例生成来源证据的权限术语。

## 8. 视觉证据规则

图片和附件进入生成前必须经过：

1. 资源清单生成。
2. `Visual Observation Selection` 推荐和用户调整。
3. Vision observation。
4. 用户确认采纳为 `Adopted Visual Evidence`。

未观察、观察失败、未采纳、提取失败或转换失败的图片只能进入 warnings，不得进入生成依据。

对 workbook/sheets run，`GET /visual-candidates?sheet_name=...` 会把当前 Sheet 内 `ready/selectable` 的图片候选默认标记为选中，其他 Sheet 图片仍可在资源抽屉中手动选择。默认选中只是 `Visual Observation Selection` 的初始值，不代表已观察，不代表已采纳，也不会自动写入 `Adopted Visual Evidence`。

Vision AI 未配置或不可用时，文本/表格读取和生成继续可用；页面和导出说明必须提示图片未参与语义理解。

Project Vision AI Credential 独立于文本生成/配置表查询的 Project AI Credential，不静默复用文本 AI Key 或文本模型默认值。后台配置卡只推荐明确支持图片输入的 OpenAI-compatible 视觉模型入口；如果已保存 DeepSeek、`qwen-plus`、`qwen3.6-plus`、`glm-5.2` 等文本 provider/model，页面必须兼容展示但提示其不是明确的 Source Evidence 视觉模型。当前内置推荐包含 Qwen `qwen3.7-plus` 和智谱 `glm-5v-turbo`，真实可用性以项目账号权限和连接测试为准。

## 9. visual validate

V3 `Generation Run`、导出和旧兼容生成路径在使用视觉证据前必须做确定性校验：

阻塞：

- 请求传入的 adopted evidence id 不存在、不属于当前 run、已过期或未采纳。
- 请求传入的 adopted evidence id 不属于当前 `Planning Sheet`。
- 生成结果引用了未采纳图片 ref，或把未观察图片写成已确认需求依据。

warning：

- run 存在未观察图片。
- run 存在图片提取失败、`.xls` 转换失败或 Vision 不可用。

该校验等价于 `qa-case` 工作流中的视觉引用校验，但实现为当前 Web 产品的后端服务规则。

## 10. 前端入口

用例生成页 01 区域保留三入口，但语义改为：

- 本地文件。
- SVN 文件。
- 飞书文档。

三者创建 run 后展示同一套 Source Evidence 状态、TTL、warnings、资源清单、视觉选择、观察、采纳和重试流程。

对本地 `.xlsx/.xls`、SVN `.xlsx/.xls` 和飞书 sheets 等 workbook/spreadsheet run，页面显示 Source Evidence Sheet selector，并默认选择后端 `is_default` Sheet 或第一张可用 Sheet。读取 snapshot 预览、拉取视觉候选、保存视觉选择和创建 V3 Generation Run 时都携带当前 Sheet。切换 Sheet 必须清空旧 snapshot、AI 整理稿、当前 Generation Run 结果和导出可用态，并重新拉取当前 Sheet 的视觉候选。

飞书 docx/wiki 和独立图片等非 Sheet 来源不会显示 Source Evidence Sheet selector，继续按 run-wide 兼容行为处理。

独立图片文件可以创建 run；由于没有文本主体，必须先观察并采纳图片证据后才能生成。

## 11. 运行能力展示

项目凭据或运行能力状态需要展示：

- `GET /api/v1/test-cases/source-evidence-capabilities` 按当前登录用户所在项目返回运行能力状态。
- SVN 凭据是否可用。
- Source Evidence SVN Root 是否已配置。
- Vision AI 是否可用。
- LibreOffice/soffice 转换器是否可用。

响应包含 `svn_credential_configured`、`source_evidence_svn_roots_configured`、`vision_ai_configured`、`soffice_configured`、`soffice_available`、`warnings`、`items[]` 和 `is_project_admin`。普通成员只看可用/不可用和中文处理建议；项目管理员/超管在同一响应中额外看到 `admin_details`，包括 `/admin` 配置入口、启用 root 数量、Vision 最近测试摘要和 soffice 检测摘要。

该接口不接收命令或路径参数，不触发 SVN/Vision 外部连接测试；soffice 只读取服务端 `SOURCE_EVIDENCE_SOFFICE_EXECUTABLE` 配置并用固定 `--version` 探测。错误响应、状态摘要和日志不得泄露密钥、SVN 密码、完整命令行参数或本地敏感路径。

管理员后台 Source Evidence 运行配置卡提供两类项目级入口：

- Source Evidence SVN Root：调用 `GET/PUT /api/v1/admin/projects/{project_id}/source-evidence-svn-roots`，维护 `svn_file` 允许读取的 SVN URL root。
- Project Vision AI Credential：调用 `GET/PUT/DELETE/POST /api/v1/admin/projects/{project_id}/vision-ai-config*`，维护图片 observation 使用的视觉模型凭据；该凭据独立于文本生成/配置表查询的 Project AI Credential。表单仅推荐 OpenAI、Qwen 视觉模型、智谱 GLM-V、OpenRouter 视觉模型或自定义 OpenAI 兼容视觉模型，旧文本 provider 只做兼容展示和风险提示。

## 12. 实施切片

1. 文档和 ADR：更新 glossary、ADR、V2 spec，冻结术语和范围。
2. 后端契约：扩展 source evidence schemas，新增 `local_file` 上传创建接口和 `svn_file` JSON 创建入口。
3. 本地文件 reader：实现工作簿文本/表格/图片 resource 抽取，支持 `.xlsx` 图片和独立图片。
4. `.xls` 转换器：新增受控 LibreOffice converter，提供 fake converter 单测成功/失败路径。
5. SVN 接入：新增 `Source Evidence SVN Root` 校验和项目级 SVN 凭据读取，缓存后复用本地文件 reader。
6. Generation Run/export 校验：加入 visual validate，确保只有当前 `Planning Sheet` 范围内的 `Adopted Visual Evidence` 进入 full context、Requirement Atom、用例追踪和导出说明。
7. 前端统一入口：把本地文件、SVN 文件、飞书文档统一到 Source Evidence 状态和视觉证据流程。
8. 验收与回归：覆盖 V1 上传 Excel、旧飞书电子表格、参考案例库、生成、导出不回归。

## 13. 测试矩阵

后端必须覆盖：

- 本地 `.xlsx` 文本和内嵌图片。
- 本地 `.xls` 文本和转换成功后的内嵌图片。
- 本地 `.xls` 转换失败但文本可用。
- SVN `.xls` 通过项目 root 和凭据校验后进入同一 reader。
- 独立图片 run 在未采纳前不能生成。
- 未采纳图片不进入 prompt。
- adopted evidence id 无效时 Generation Run/export 阻塞。
- 多 Sheet Source Evidence snapshot 只返回所选 Sheet 的文本、表格和图片资源行。
- 跨 Sheet adopted evidence 在 Generation Run/export 前阻塞。
- Source Evidence TTL 清理删除转换产物、原图、视觉包和 observation 详情。

前端必须覆盖：

- 三入口都能创建或展示 Source Evidence Run。
- workbook/sheets Source Evidence run 显示 Sheet selector，默认第一张可用 Sheet。
- 切换 Source Evidence Sheet 会清空旧 snapshot、AI 整理稿、生成结果和导出状态。
- 当前 Sheet 图片候选默认选中，但用户手动选择在同 Sheet 内保持。
- 资源清单、视觉选择、观察、采纳、撤销状态一致。
- Vision 或转换器不可用时展示 warning，不误导用户图片已参与理解。

真实环境验收必须至少包含一份带内嵌图片的 `.xlsx` 样例、一份带内嵌图片的 `.xls` 样例和一份 SVN `.xls` 样例。

## 14. 维护检查清单

- 修改 source evidence 来源类型时，同步本文件、`frontend/src/types/testCases.ts` 和 `backend/app/test_cases/schemas.py`。
- 修改 Source Evidence Sheet 范围或 snapshot/Generation Run/export 契约时，同步本文件、`docs/specs/test-case-generation-v2-requirements.md`、前端类型/API 和后端 schemas。
- 修改 SVN 权限时，同步 `CONTEXT.md` 的 `Source Evidence SVN Root` 定义。
- 修改 `.xls` 转换策略时，同步 ADR 或新增 superseding ADR。
- 修改视觉证据规则时，同步生成、导出和前端 resource drawer 测试。
