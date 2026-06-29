# 飞书集成 Spec

## 0. Codex 快速入口

- 先读文件：`backend/app/admin/router.py` 的飞书机器人接口、`backend/app/api/feishu_api.py`、`backend/app/integrations/feishu_client.py`、`backend/app/integrations/feishu_bot.py`、`backend/app/integrations/feishu_long_conn.py`、`backend/app/loaders/feishu_reader.py`、`frontend/src/components/admin/FeishuBotConfigCard.vue`。
- 最常改文件：`frontend/src/api/admin.ts`、`frontend/src/features/admin/feishuBotConfigForm.ts`、`backend/app/services/feishu_sheet_authorization_service.py`。
- 不要改契约：飞书在配置表查询中是通道和项目路由；查询业务语义写在 `rule-configs-config-lookup.md`。
- 新增功能入口：机器人配置从 `/api/v1/admin/projects/{project_id}/feishu-bot*` 接入；数据源授权从 `/api/v1/feishu/sources/*` 接入。
- 必跑测试：`python -m pytest backend/tests/test_admin_feishu_bot.py backend/tests/test_feishu_permission_api.py backend/tests/test_feishu_reader.py backend/tests/test_feishu_client.py backend/tests/test_feishu_bot_client.py backend/tests/test_feishu_long_conn.py -q`；前端跑 `adminFeishuBotApi.test.ts`、`feishuBotConfigForm.test.ts`。
- 常见误区：不要把飞书 app 配置做成全局单例；项目配置、chat 绑定、下载根和查询根都按项目隔离。

## 1. 模块目标

飞书集成提供项目机器人配置、电子表格授权、表格读取、消息发送和事件通道能力。它是多个业务能力的通道，不承载配置表查询本身的规则语义。

## 2. 用户入口与适用场景

| 入口 | 说明 |
|---|---|
| `/admin` 飞书机器人配置卡片 | 项目管理员维护 App ID、App Secret、默认群、chat 绑定、触发用户、SVN 凭据和查询根。 |
| 个人校验数据源面板 | 检测飞书表格权限并发送授权卡片。 |
| Feishu OAuth callback | 完成表格只读协作者授权。 |

## 3. 核心概念

- 项目级飞书机器人配置：每个项目独立维护。
- Shared Feishu Bot App：多个项目可共用同一 App ID，但同 App ID 的 App Secret 必须一致。
- Project Feishu Service Identity：服务端项目自动化读取飞书来源时使用项目级 App/Bot 身份，不使用当前登录用户的个人 OAuth token 作为长期读取身份。
- Chat-Scoped Project Routing：机器人事件按 chat 绑定路由到项目。
- Default Bot Chat：默认主动通知群，必须属于项目 chat 绑定。
- Feishu Sheet Authorization：项目和 source 维度的表格授权记录。

## 4. 前端边界

- 管理后台飞书配置组件：`frontend/src/components/admin/FeishuBotConfigCard.vue`。
- 表单逻辑：`frontend/src/features/admin/feishuBotConfigForm.ts`。
- 管理 API：`frontend/src/api/admin.ts`。
- 个人校验数据源授权入口：`DataSourcePanel.vue` 和 `frontend/src/api/workbench.ts`。

## 5. 后端边界

- 项目飞书机器人配置：`backend/app/admin/router.py`。
- 飞书数据源授权：`backend/app/api/feishu_api.py`。
- 飞书 HTTP 客户端、机器人和长连接：`backend/app/integrations/feishu_*`。
- 飞书电子表格读取：`backend/app/loaders/feishu_reader.py`。
- 授权记录：`backend/app/services/feishu_sheet_authorization_service.py`。

## 6. 数据与持久化边界

- `app_secret` 加密落库。
- 表格授权记录按 `project_id + source_id` 记录，并可按 spreadsheet token 复用。
- Chat 绑定按项目隔离；同一 chat 不能绑定多个项目。

## 7. API 契约

| API | 说明 |
|---|---|
| `GET /api/v1/admin/projects/{project_id}/feishu-bot` | 获取项目飞书机器人配置。 |
| `PUT /api/v1/admin/projects/{project_id}/feishu-bot` | 保存项目飞书机器人配置。 |
| `DELETE /api/v1/admin/projects/{project_id}/feishu-bot` | 删除项目飞书机器人配置。 |
| `POST /api/v1/admin/projects/{project_id}/feishu-bot/test-send` | 测试发送消息。 |
| `POST /api/v1/feishu/sources/check-permission` | 检查表格读取权限。 |
| `POST /api/v1/feishu/sources/send-authorization-card` | 发送授权卡片。 |
| `GET /api/v1/feishu/sources/oauth/callback` | OAuth 回调并追加协作者。 |

## 8. 关键流程

1. 项目管理员保存飞书机器人配置。
2. 用户添加飞书数据源时，后端检查表格权限。
3. 权限不足时，项目机器人向默认群发送授权卡片。
4. 有权限的飞书用户点击卡片完成 OAuth。
5. 后端把机器人加入表格只读协作者并记录授权。
6. 后续 metadata、preview 和执行复用飞书读取链路。

### 8.1 Source Evidence Run 授权主体

用例生成 V2 若扩展到飞书文档、图片、附件和 `Source Evidence Run`，读取主体仍以 `Project Feishu Service Identity` 为准：

- 当前登录用户只触发读取、授权申请或重试，不作为长期来源读取身份。
- 不把 QA Workspace 的本机个人 user token 模式直接迁移到当前 Web 项目。
- 权限不足时，记录资源的待授权状态，并沿用项目级机器人/授权卡片方向申请给 App/Bot 可读取权限。
- 授权成功后，未过期的 `Source Evidence Run` 可以重试读取资源和视觉 observation。

## 9. 权限、安全与错误规则

- 普通项目成员可查看必要状态，但敏感配置由项目管理员维护。
- App Secret、tenant token、access token 不得明文暴露。
- 权限不足时返回业务错误或授权状态，不触发前端登录态过期。
- 飞书来源读取不得把当前登录用户的个人 OAuth token 作为服务端长期读取凭据。
- 查询命令的业务解析归配置表查询模块；飞书模块只负责事件、路由和消息。

## 10. 测试覆盖

- 后端：`test_admin_feishu_bot.py`、`test_feishu_permission_api.py`、`test_feishu_reader.py`、`test_feishu_client.py`、`test_feishu_bot_client.py`、`test_feishu_long_conn.py`、`test_feishu_download.py`、`test_feishu_datasource_e2e.py`。
- 前端：`adminFeishuBotApi.test.ts`、`feishuBotConfigForm.test.ts`、`FeishuBotConfigCardSvnTest.test.ts`。

## 11. 已知限制

- 仅支持飞书电子表格和 wiki 电子表格。
- 不支持多维表格、文档表格或任意 Drive 文件。
- 飞书主链路依赖真实项目机器人、OAuth callback 和应用权限。

## 12. 维护检查清单

- 改机器人配置时，检查 shared App ID 和 App Secret 一致性。
- 改 chat 绑定时，检查一群一项目规则。
- 改飞书读取时，跑权限 API、reader 和 datasource e2e 测试。
- 配置表查询相关改动，应优先更新 `rule-configs-config-lookup.md`。
