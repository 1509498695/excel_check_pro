# 项目级 AI 能力 Spec

## 0. Codex 快速入口

- 先读文件：`docs/adr/0001-unify-ai-credentials-project-level.md`、`backend/app/ai/credentials.py`、`backend/app/ai/providers.py`、`backend/app/ai/schemas.py`、`backend/app/admin/router.py` 的 AI / Vision AI 配置接口、`frontend/src/api/projectAiConfig.ts`、`frontend/src/features/admin/projectAiConfigForm.ts`。
- 最常改文件：`frontend/src/features/ai/providerPresets.ts`、`backend/app/services/package_items_ai_parser.py`、`backend/app/services/event_task_ai_advisor.py`、`backend/app/config_lookup/ai_matcher.py`。
- 不要改契约：项目级文本 AI 凭据与 Project Vision AI Credential 独立；Vision AI 不静默复用 Project AI Credential；个人设置不保存个人 AI Key；日志和响应不得暴露完整 API Key。
- 新增功能入口：新增 AI 调用先判断是否属于项目级能力，再通过项目凭据读取 provider。
- 必跑测试：`python -m pytest backend/tests/test_project_ai_config_api.py backend/tests/test_package_items_ai_parser.py backend/tests/test_event_task_ai_advisor.py backend/tests/test_config_lookup_service.py -q`；前端跑 `projectAiConfig*.test.ts`、`providerPresets.test.ts`。
- 常见误区：AI 不能替代确定性校验；AI 不可用时要有明确回退或用户提示。

## 1. 模块目标

项目级 AI 能力为少量明确边界的辅助场景提供统一 provider、凭据、脱敏和不可用策略。它不承担个人自然语言生成规则入口。

## 2. 用户入口与适用场景

| 入口 | 说明 |
|---|---|
| `/admin` 项目级 AI 配置 | 项目管理员保存、测试、删除和查看 AI 凭据状态。 |
| `/admin` 项目级 Vision AI 配置 | 项目管理员在 Source Evidence 运行配置卡中保存、测试、删除和查看视觉观察凭据状态。 |
| 配置表查询 | AI 名称匹配，只在确定性候选范围内排序或归一化。 |
| IAP 礼包校验 | 礼包规划表结构识别。 |
| 活动任务 | 字段映射或修复建议。 |
| 用例生成 Source Evidence 视觉观察 | 对用户选择并已下载的图片生成 observation；未采纳 observation 不进入生成。 |

## 3. 核心概念

- Project AI Credential：项目管理员维护的 AI 凭据。
- Project Vision AI Credential：项目管理员维护的视觉模型凭据，独立于文本生成/匹配使用的 Project AI Credential。
- Vision Model：支持 OpenAI-compatible `chat/completions` 图片输入的模型；文本模型默认值（例如 `deepseek-v4-flash`、`qwen-plus`、`qwen3.6-plus`、`glm-5.2`）不能被当作 Source Evidence 视觉观察模型。
- Project AI Unavailable：未配置、未启用、凭据无效、解密失败或上游不可用。
- Provider：供应商、模型、Base URL、API Key 和额外请求头的组合。
- 脱敏状态：普通成员可看状态，不看密钥。

## 4. 前端边界

- AI 配置 API：`frontend/src/api/projectAiConfig.ts`。
- AI 配置类型：`frontend/src/types/projectAiConfig.ts`。
- 管理表单：`frontend/src/features/admin/projectAiConfigForm.ts`。
- provider 预设：`frontend/src/features/ai/providerPresets.ts`。
- Vision AI 配置入口位于 `frontend/src/components/admin/SourceEvidenceAdminConfigCard.vue`，通过 `frontend/src/api/admin.ts` 调用 `/api/v1/admin/projects/{project_id}/vision-ai-config*`。
- Vision AI 配置卡不能直接复用文本 AI 的完整 provider 列表；只推荐明确的视觉模型入口（OpenAI、Qwen 视觉模型、智谱 GLM-V、OpenRouter 视觉模型或自定义 OpenAI 兼容视觉模型），已保存的旧文本 provider 仅兼容展示并给出警告。
- 调用 AI 的业务组件只展示本模块返回的可用性、建议或告警。

## 5. 后端边界

- 项目级配置接口集中在 `backend/app/admin/router.py`。
- 凭据读取和加解密状态在 `backend/app/ai/credentials.py`。
- provider 调用协议在 `backend/app/ai/providers.py`。
- 内置 OpenAI-compatible 默认值按官方 API 文档维护：通义千问（百炼）文本默认 `qwen3.6-plus`，Base URL 继续使用可兼容的 `https://dashscope.aliyuncs.com/compatible-mode/v1`；如果项目使用百炼业务空间专属域名，可在后台手动改为 `https://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/compatible-mode/v1`。智谱文本默认 `glm-5.2`，Base URL 为 `https://open.bigmodel.cn/api/paas/v4`。
- 业务调用方：
  - `backend/app/config_lookup/ai_matcher.py`
  - `backend/app/services/package_items_ai_parser.py`
  - `backend/app/services/event_task_ai_advisor.py`
  - `backend/app/test_cases/visual_evidence.py`

## 6. 数据与持久化边界

- AI 凭据按 `project_id` 存储。
- Vision AI 凭据按 `project_id` 独立存储，不回退使用文本 AI API Key。
- API Key 加密保存，只返回脱敏摘要和状态。
- 删除项目级 AI 配置后，所有业务调用方都应按不可用策略处理。
- 删除项目级 Vision AI 配置后，Source Evidence 文本/表格生成仍可继续，视觉 observation API 返回可展示降级错误。

## 7. API 契约

| API | 说明 |
|---|---|
| `GET /api/v1/admin/projects/{project_id}/ai-config` | 查看项目级 AI 配置状态。 |
| `PUT /api/v1/admin/projects/{project_id}/ai-config` | 保存项目级 AI 配置。 |
| `DELETE /api/v1/admin/projects/{project_id}/ai-config` | 删除项目级 AI 配置。 |
| `POST /api/v1/admin/projects/{project_id}/ai-config/test` | 测试配置可用性。 |
| `GET /api/v1/admin/projects/{project_id}/vision-ai-config` | 查看项目级 Vision AI 配置状态。 |
| `PUT /api/v1/admin/projects/{project_id}/vision-ai-config` | 保存项目级 Vision AI 配置。 |
| `DELETE /api/v1/admin/projects/{project_id}/vision-ai-config` | 删除项目级 Vision AI 配置。 |
| `POST /api/v1/admin/projects/{project_id}/vision-ai-config/test` | 测试 Vision AI 配置可用性。 |
| `GET /api/v1/test-cases/source-evidence-capabilities` | 读取当前项目 Source Evidence 运行能力状态；只判断 Project Vision AI Credential 是否存在、启用且可解密，并返回最近测试脱敏摘要，不实际调用视觉模型。 |

## 8. 关键流程

1. 项目管理员在后台保存 provider 配置。
2. 后端加密保存敏感字段。
3. 业务模块需要 AI 时读取当前项目凭据。
4. 若不可用，自动辅助场景回退确定性逻辑，显式 AI 操作返回中文提示。
5. AI 返回内容必须再经过业务模块确定性解析或校验。
6. Source Evidence 视觉观察只调用 Project Vision AI Credential；结果先形成 observation，用户显式采纳后才成为 Adopted Visual Evidence。
7. Source Evidence 运行能力状态接口只读取 Vision AI 配置状态和最近测试摘要，不触发 provider 探测；Vision 未配置时文本/表格读取和生成继续可用，页面提示图片不会参与语义理解。

## 9. 权限、安全与错误规则

- 只有项目管理员能保存、删除和测试 AI 凭据。
- 普通成员只能看脱敏状态。
- 响应、日志、异常摘要和持久化错误不得输出完整 API Key。
- AI 上游错误需要脱敏，并转换为面向用户的中文错误或告警。
- Vision observation 当前只支持 OpenAI-compatible 多模态 JSON 调用；其他 provider 返回“不支持当前视觉协议”类错误。
- Vision 配置连接测试必须使用真实图片输入探测；测试探针图片必须满足 Qwen/GLM-V 等视觉模型的最小尺寸限制，不能使用 1x1 PNG；如果使用不支持 image input 的文本模型，应返回测试失败并提示更换视觉模型。
- Observation、Adopted Visual Evidence、导出说明不得保存或返回 prompt、provider response、原图绝对路径、file token 或完整 API Key。

## 10. 测试覆盖

- 后端：`test_project_ai_config_api.py`、`test_project_vision_ai_config_api.py`、`test_package_items_ai_parser.py`、`test_event_task_ai_advisor.py`、`test_config_lookup_service.py`。
- 前端：`projectAiConfigApi.test.ts`、`projectAiConfigForm.test.ts`、`providerPresets.test.ts`。

## 11. 已知限制

- 当前仅保留 provider 基础调用、配置表查询 AI 名称匹配、礼包规划表结构识别、活动任务建议和 Source Evidence 视觉观察。
- Vision observation 真实调用先支持 OpenAI-compatible 协议；生成页只展示运行能力状态和降级提示，配置入口在管理后台 Source Evidence 运行配置卡。
- 为避免配置冗余误导，后台 Vision 表单保留独立凭据但只给视觉模型推荐；文本 Project AI 的 provider/model 不能自动回填为 Vision AI。当前推荐包含 Qwen `qwen3.7-plus` 和智谱 `glm-5v-turbo`，具体可用性仍以项目账号权限和后台连接测试为准。
- 个人校验不提供自然语言生成规则入口。

## 12. 维护检查清单

- 新增 AI 使用场景时，先写清不可用策略和确定性回退。
- 新增 provider 字段时，同步脱敏、测试、前端表单和文档。
- 修改错误处理时，检查密钥不会泄露。
- 调用方 Spec 只写“如何调用 AI”，共享策略写在本 Spec。
