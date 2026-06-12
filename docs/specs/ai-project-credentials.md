# 项目级 AI 能力 Spec

## 0. Codex 快速入口

- 先读文件：`docs/adr/0001-unify-ai-credentials-project-level.md`、`backend/app/ai/credentials.py`、`backend/app/ai/providers.py`、`backend/app/ai/schemas.py`、`backend/app/admin/router.py` 的 AI 配置接口、`frontend/src/api/projectAiConfig.ts`、`frontend/src/features/admin/projectAiConfigForm.ts`。
- 最常改文件：`frontend/src/features/ai/providerPresets.ts`、`backend/app/services/package_items_ai_parser.py`、`backend/app/services/event_task_ai_advisor.py`、`backend/app/config_lookup/ai_matcher.py`。
- 不要改契约：项目级 AI 凭据是唯一 AI 配置入口；个人设置不保存个人 AI Key；日志和响应不得暴露完整 API Key。
- 新增功能入口：新增 AI 调用先判断是否属于项目级能力，再通过项目凭据读取 provider。
- 必跑测试：`python -m pytest backend/tests/test_project_ai_config_api.py backend/tests/test_package_items_ai_parser.py backend/tests/test_event_task_ai_advisor.py backend/tests/test_config_lookup_service.py -q`；前端跑 `projectAiConfig*.test.ts`、`providerPresets.test.ts`。
- 常见误区：AI 不能替代确定性校验；AI 不可用时要有明确回退或用户提示。

## 1. 模块目标

项目级 AI 能力为少量明确边界的辅助场景提供统一 provider、凭据、脱敏和不可用策略。它不承担个人自然语言生成规则入口。

## 2. 用户入口与适用场景

| 入口 | 说明 |
|---|---|
| `/admin` 项目级 AI 配置 | 项目管理员保存、测试、删除和查看 AI 凭据状态。 |
| 配置表查询 | AI 名称匹配，只在确定性候选范围内排序或归一化。 |
| IAP 礼包校验 | 礼包规划表结构识别。 |
| 活动任务 | 字段映射或修复建议。 |

## 3. 核心概念

- Project AI Credential：项目管理员维护的 AI 凭据。
- Project AI Unavailable：未配置、未启用、凭据无效、解密失败或上游不可用。
- Provider：供应商、模型、Base URL、API Key 和额外请求头的组合。
- 脱敏状态：普通成员可看状态，不看密钥。

## 4. 前端边界

- AI 配置 API：`frontend/src/api/projectAiConfig.ts`。
- AI 配置类型：`frontend/src/types/projectAiConfig.ts`。
- 管理表单：`frontend/src/features/admin/projectAiConfigForm.ts`。
- provider 预设：`frontend/src/features/ai/providerPresets.ts`。
- 调用 AI 的业务组件只展示本模块返回的可用性、建议或告警。

## 5. 后端边界

- 项目级配置接口集中在 `backend/app/admin/router.py`。
- 凭据读取和加解密状态在 `backend/app/ai/credentials.py`。
- provider 调用协议在 `backend/app/ai/providers.py`。
- 业务调用方：
  - `backend/app/config_lookup/ai_matcher.py`
  - `backend/app/services/package_items_ai_parser.py`
  - `backend/app/services/event_task_ai_advisor.py`

## 6. 数据与持久化边界

- AI 凭据按 `project_id` 存储。
- API Key 加密保存，只返回脱敏摘要和状态。
- 删除项目级 AI 配置后，所有业务调用方都应按不可用策略处理。

## 7. API 契约

| API | 说明 |
|---|---|
| `GET /api/v1/admin/projects/{project_id}/ai-config` | 查看项目级 AI 配置状态。 |
| `PUT /api/v1/admin/projects/{project_id}/ai-config` | 保存项目级 AI 配置。 |
| `DELETE /api/v1/admin/projects/{project_id}/ai-config` | 删除项目级 AI 配置。 |
| `POST /api/v1/admin/projects/{project_id}/ai-config/test` | 测试配置可用性。 |

## 8. 关键流程

1. 项目管理员在后台保存 provider 配置。
2. 后端加密保存敏感字段。
3. 业务模块需要 AI 时读取当前项目凭据。
4. 若不可用，自动辅助场景回退确定性逻辑，显式 AI 操作返回中文提示。
5. AI 返回内容必须再经过业务模块确定性解析或校验。

## 9. 权限、安全与错误规则

- 只有项目管理员能保存、删除和测试 AI 凭据。
- 普通成员只能看脱敏状态。
- 响应、日志、异常摘要和持久化错误不得输出完整 API Key。
- AI 上游错误需要脱敏，并转换为面向用户的中文错误或告警。

## 10. 测试覆盖

- 后端：`test_project_ai_config_api.py`、`test_package_items_ai_parser.py`、`test_event_task_ai_advisor.py`、`test_config_lookup_service.py`。
- 前端：`projectAiConfigApi.test.ts`、`projectAiConfigForm.test.ts`、`providerPresets.test.ts`。

## 11. 已知限制

- 当前仅保留 provider 基础调用、配置表查询 AI 名称匹配、礼包规划表结构识别和活动任务建议。
- 个人校验不提供自然语言生成规则入口。

## 12. 维护检查清单

- 新增 AI 使用场景时，先写清不可用策略和确定性回退。
- 新增 provider 字段时，同步脱敏、测试、前端表单和文档。
- 修改错误处理时，检查密钥不会泄露。
- 调用方 Spec 只写“如何调用 AI”，共享策略写在本 Spec。
