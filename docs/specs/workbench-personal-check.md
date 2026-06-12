# 个人校验工作台 Spec

## 0. Codex 快速入口

- 先读文件：`frontend/src/views/MainBoard.vue`、`frontend/src/store/workbench.ts`、`frontend/src/components/workbench/`、`frontend/src/features/rule-orchestration/`、`backend/app/api/workbench_api.py`、`backend/app/api/execute_api.py`。
- 最常改文件：`frontend/src/api/workbench.ts`、`frontend/src/types/workbench.ts`、`frontend/src/utils/taskTree.ts`、`backend/app/api/workbench_api.py`。
- 不要改契约：个人校验执行入口保持 `POST /api/v1/engine/execute`；`TaskTree` 顶层保持 `sources / variables / rules`；统一执行结果结构不复制。
- 新增功能入口：页面交互先落到 workbench store，再转换成 `TaskTree` 或预览请求。
- 必跑测试：`python -m pytest backend/tests/test_execute_api.py backend/tests/test_workbench_svn_update.py backend/tests/test_workbench_package_items_preview.py -q`；前端跑 `workbench*.test.ts`、`taskTree.test.ts`、`VariablePoolPanel.test.ts`。
- 常见误区：不要把个人校验做成项目级持久规则；个人配置隔离边界是 `project_id + user_id`。

## 1. 模块目标

个人校验工作台提供临时配置表校验能力。用户通过数据源、变量池、规则编排和结果区四步完成一次校验，适合排查、试验和导入项目校验前的准备。

## 2. 用户入口与适用场景

| 路由 | 说明 |
|---|---|
| `/` | 个人校验主页面。 |
| `/user-guide` | 面向业务用户的操作说明。 |

适用场景：

- 临时校验单个或多个 Excel 表。
- 试配变量和规则。
- 配置 IAP 礼包校验并预览礼包规划。
- 将个人规则导入项目校验。

## 3. 核心概念

- 数据源：本地 Excel、上传 Excel、SVN Excel 或飞书电子表格。
- 变量：单字段变量或组合变量，是规则绑定的目标。
- 规则：保存为 `ValidationRule`，执行时进入统一规则引擎。
- `TaskTree`：个人校验执行请求的稳定结构。
- IAP 礼包校验：通过 `package_items_compare` 扩展规则参数，但不改变 `TaskTree` 顶层。

## 4. 前端边界

- `MainBoard.vue` 负责页面骨架。
- `components/workbench/` 承载数据源、变量池、规则和结果区业务组件。
- `store/workbench.ts` 维护个人工作台状态、自动保存和执行状态。
- `features/rule-orchestration/` 承载个人校验和项目校验共用的规则表单模型。
- `utils/taskTree.ts` 把前端状态转换为后端执行结构。

## 5. 后端边界

- `backend/app/api/workbench_api.py` 负责个人配置读取/保存、SVN 更新、礼包预览、活动任务预览/校验/AI 建议。
- `backend/app/api/execute_api.py` 负责同步执行和个人结果读取/导出。
- 执行引擎位于 `backend/app/rules/`，数据读取由 `backend/app/loaders/` 提供。

## 6. 数据与持久化边界

- 个人工作台配置按 `project_id + user_id` 保存。
- 执行结果进入统一结果存储，不在前端复制第二套结果协议。
- 历史字段兼容只能放在读取、迁移或导入层，不能污染新的执行入参模型。

## 7. API 契约

| API | 说明 |
|---|---|
| `GET /api/v1/workbench/config` | 获取当前用户当前项目的个人配置。 |
| `PUT /api/v1/workbench/config` | 保存个人配置。 |
| `POST /api/v1/workbench/svn-update` | 刷新个人配置中的 SVN 数据源。 |
| `POST /api/v1/workbench/package-items/preview` | 预览 IAP 礼包规划解析。 |
| `POST /api/v1/workbench/event-tasks/preview` | 活动任务预览。 |
| `POST /api/v1/workbench/event-tasks/validate` | 活动任务校验。 |
| `POST /api/v1/workbench/event-tasks/ai-suggestions` | 活动任务 AI 建议。 |
| `POST /api/v1/engine/execute` | 个人校验同步执行。 |

## 8. 关键流程

1. 页面加载后读取个人配置。
2. 用户添加数据源并读取 metadata / preview。
3. 用户创建变量，再基于变量配置规则。
4. 前端把当前工作台状态转换为 `TaskTree`。
5. 后端读取数据源、执行规则、写入结果并返回统一结果结构。
6. 结果区展示统计、异常明细和导出入口。

## 9. 权限、安全与错误规则

- 工作台配置需要登录态和项目成员关系。
- 本地路径读取必须经过 allowlist；远程 SVN 受 host 白名单和凭据约束。
- 飞书表格权限不足时走授权卡片和 OAuth，不视为登录失效。

## 10. 测试覆盖

- 后端：`test_execute_api.py`、`test_workbench_svn_update.py`、`test_workbench_package_items_preview.py`、`test_execute_package_items_runtime.py`。
- 前端：`workbenchAutoSave.test.ts`、`workbenchRuleForm.test.ts`、`workbenchOrchestrationRules.test.ts`、`workbenchPackageItemsRuleTransform.test.ts`、`WorkbenchRuleOrchestrationPanelPackageItems.test.ts`、`taskTree.test.ts`。
- E2E：`frontend/tests/e2e/smoke.e2e.ts` 覆盖登录、上传、个人非空规则执行、导入项目校验和项目校验执行。

## 11. 已知限制

- 前端当前默认使用同步执行接口；大 Excel、SVN 或飞书校验可使用任务接口，但不是所有页面都已切换。
- 个人校验不再提供自然语言生成规则入口。
- IAP 礼包校验当前重点接在个人校验 03 规则页签。

## 12. 维护检查清单

- 改规则表单时，同时检查个人校验和项目校验共用表单。
- 改 `TaskTree` 转换时，跑前端 `taskTree` 和后端执行契约测试。
- 新增预览接口时，确认是否需要登录、项目成员校验和数据源 allowlist。
- 用户可见流程变化时，同步 `/user-guide` 内容。
