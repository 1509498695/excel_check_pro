# 项目校验 / 固定规则 Spec

## 0. Codex 快速入口

- 先读文件：`frontend/src/views/FixedRulesBoard.vue`、`frontend/src/store/fixedRules.ts`、`frontend/src/features/fixed-rules-import/`、`backend/app/api/fixed_rules_api.py`、`backend/app/fixed_rules/`。
- 最常改文件：`frontend/src/api/fixedRules.ts`、`frontend/src/types/fixedRules.ts`、`backend/app/fixed_rules/service.py`、`backend/app/fixed_rules/importer/`。
- 不要改契约：项目校验同步执行入口保持 `POST /api/v1/fixed-rules/execute`；配置读取可返回 `meta.config_issues` 非阻断告警；旧配置版本只能通过迁移兼容。
- 新增功能入口：项目级长期规则配置从 `fixed_rules` 服务和 API 接入；导入个人规则从 importer 子模块接入。
- 必跑测试：`python -m pytest backend/tests/test_fixed_rules_api.py backend/tests/test_fixed_rules_import_api.py backend/tests/test_package_items_runtime.py -q`；前端跑 `FixedRules*.test.ts` 和 `usePersonalRulesImport.test.ts`。
- 常见误区：项目校验不是个人校验配置的共享副本，它按 `project_id` 持久化并服务团队复用。

## 1. 模块目标

项目校验用于维护项目级长期规则。项目成员可复用固定配置执行校验，也可从个人校验导入规则并逐步沉淀为团队规则。

## 2. 用户入口与适用场景

| 路由 | 说明 |
|---|---|
| `/fixed-rules` | 项目校验配置、导入、执行、结果分页和导出。 |

适用场景：

- 团队长期维护同一批配置表规则。
- 从个人校验导入成熟规则。
- 执行项目规则并分页查看历史结果。

## 3. 核心概念

- 项目校验配置：当前版本为 `version = 6`，包含 `sources / variables / groups / rules`。
- 规则组：前端组织规则的分组视图。
- 导入草稿：从个人校验转换到项目配置前的预览和冲突检测。
- `meta.config_issues`：配置读取时的非阻断问题提示。

## 4. 前端边界

- `FixedRulesBoard.vue` 是页面入口。
- `store/fixedRules.ts` 维护项目规则配置、执行状态、结果和路径替换状态。
- `features/fixed-rules-import/` 负责个人规则导入项目校验。
- 规则弹窗复用 `features/rule-orchestration/` 的表单逻辑。

## 5. 后端边界

- `backend/app/api/fixed_rules_api.py` 暴露项目配置、导入、预览、执行和结果 API。
- `backend/app/fixed_rules/` 负责配置读取、保存、版本迁移、执行整合、导入和运行时补充。
- `backend/app/fixed_rules/importer/` 负责导入预览、冲突检测、变量映射和提交。

## 6. 数据与持久化边界

- 项目校验配置按 `project_id` 隔离。
- 旧版 `version 2/3/4/5` 在读取时迁移到当前结构。
- 项目校验执行结果复用统一结果存储。
- 固定规则侧保留 IAP 礼包校验兼容能力，但主要业务入口仍在个人校验。

## 7. API 契约

| API | 说明 |
|---|---|
| `GET /api/v1/fixed-rules/config` | 获取项目配置。 |
| `PUT /api/v1/fixed-rules/config` | 保存项目配置。 |
| `GET /api/v1/fixed-rules/import/workbench/draft` | 获取导入草稿。 |
| `POST /api/v1/fixed-rules/import/workbench/preview` | 预览个人规则导入。 |
| `POST /api/v1/fixed-rules/import/workbench/commit` | 提交导入。 |
| `POST /api/v1/fixed-rules/package-items/preview` | 固定规则侧礼包预览兼容接口。 |
| `POST /api/v1/fixed-rules/svn-update` | 刷新项目配置中的 SVN 数据源。 |
| `POST /api/v1/fixed-rules/execute` | 项目校验同步执行。 |
| `GET /api/v1/fixed-rules/results/{result_id}` | 读取执行结果。 |
| `GET /api/v1/fixed-rules/results/{result_id}/export` | 导出结果。 |

## 8. 关键流程

1. 页面读取项目配置，展示数据源、变量、规则组和规则。
2. 用户可直接编辑项目规则，也可从个人校验导入。
3. 保存配置时按当前版本写入项目级记录。
4. 执行时项目配置转换为 `TaskTree` 并进入统一规则引擎。
5. 结果写入统一结果存储，前端分页读取和导出。

## 9. 权限、安全与错误规则

- 项目配置读写要求登录和当前项目成员关系。
- 项目管理员负责项目级飞书机器人、AI 凭据和成员管理；普通项目成员可使用项目校验能力。
- SVN 鉴权失败使用 HTTP 403，避免误触登录态过期逻辑。

## 10. 测试覆盖

- 后端：`test_fixed_rules_api.py`、`test_fixed_rules_import_api.py`、`test_fixed_rules_variable_mapper.py`、`test_package_items_runtime.py`、`test_svn_source_api.py`。
- 前端：`FixedRulesBoardPackageEntry.test.ts`、`FixedRulesResultPanelPackageItems.test.ts`、`fixedRulesImportApi.test.ts`、`usePersonalRulesImport.test.ts`。

## 11. 已知限制

- 多配置集切换未开放。
- 项目校验仍以配置表校验为主，不承担配置表查询规则发布职责。

## 12. 维护检查清单

- 改配置结构时，新增 migrator 并覆盖旧版本读取。
- 改导入逻辑时，检查变量映射、冲突检测和提交三段测试。
- 改执行结果时，同步检查个人校验结果协议是否仍一致。
- 不要为项目校验复制第二套规则引擎。
