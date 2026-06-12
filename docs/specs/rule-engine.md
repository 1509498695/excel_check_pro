# 规则引擎与规则模型 Spec

## 0. Codex 快速入口

- 先读文件：`docs/ARCHITECTURE.md` 的 `TaskTree` 和统一执行结果章节、`backend/app/rules/registry.py`、`backend/app/rules/engine_core.py`、`backend/app/rules/handlers/`、`frontend/src/rules/`、`frontend/src/features/rule-orchestration/`。
- 最常改文件：`backend/app/rules/handlers/fixed/*`、`backend/app/rules/domain/*`、`frontend/src/utils/taskTree.ts`、`frontend/src/utils/workbenchOrchestrationRules.ts`。
- 不要改契约：`TaskTree -> sources / variables / rules`；`ValidationRule.rule_type` 是规则扩展入口；执行响应保持 `code / msg / meta / data.abnormal_results`。
- 新增功能入口：新规则优先注册到现有 registry，并复用现有 handler 调度；前端补规则模型、表单、摘要和 `TaskTree` 转换。
- 必跑测试：`python -m pytest backend/tests/test_rule_registry.py backend/tests/test_rule_registry_contract.py backend/tests/test_rule_contracts.py backend/tests/test_engine_snapshot.py -q`；前端跑 `ruleOrchestration*.test.ts`、`workbenchRuleForm.test.ts`、`taskTree.test.ts`。
- 常见误区：不要为某类规则新增第二套执行入口；不要让 AI 直接改变确定性校验结论。

## 1. 模块目标

规则引擎把数据源读取结果、变量和规则统一成可执行校验，并输出统一异常结果。个人校验和项目校验共享同一套规则模型和执行结果协议。

## 2. 用户入口与适用场景

规则能力通过两个页面进入：

- `/` 个人校验规则编排。
- `/fixed-rules` 项目校验长期规则配置。

## 3. 核心概念

- `TaskTree`：统一执行入参，包含 `sources / variables / rules`。
- `DataSource`：数据源描述。
- `VariableTag`：规则引用的数据列或组合字段。
- `ValidationRule`：规则 ID、规则类型和参数。
- `RuleSpec`：规则注册中心中的 handler 与依赖变量定义。
- `abnormal_results`：统一异常结果列表。

## 4. 前端边界

- `frontend/src/rules/` 维护规则前端模型。
- `frontend/src/features/rule-orchestration/` 维护规则表单、校验、摘要和提交转换。
- `frontend/src/utils/taskTree.ts` 将前端规则转换为后端执行结构。
- 个人校验和项目校验应复用同一规则表单能力，避免页面级复制。

## 5. 后端边界

- `backend/app/rules/registry.py` 注册规则类型。
- `backend/app/rules/engine_core.py` 执行调度。
- `backend/app/rules/domain/` 提供领域值、操作符和结果工具。
- `backend/app/rules/handlers/` 实现具体规则。
- `backend/app/rules/handlers/fixed/` 承载固定规则、组合变量和礼包校验等复杂 handler。

## 6. 数据与持久化边界

- 规则定义本身随个人配置或项目配置持久化。
- 执行结果进入统一结果存储。
- 旧路径 shim 仅为兼容保留，新实现应写入当前分层目录。

## 7. API 契约

规则引擎没有单独对外 API，主要被以下入口调用：

| API | 调用方 |
|---|---|
| `POST /api/v1/engine/execute` | 个人校验同步执行。 |
| `POST /api/v1/fixed-rules/execute` | 项目校验同步执行。 |
| `POST /api/v1/execute-runs` | 后台任务执行个人或项目校验。 |

## 8. 当前规则类型

| 规则类型 | 说明 |
|---|---|
| `not_null` | 单字段非空。 |
| `unique` | 单字段唯一。 |
| `fixed_value_compare` | 单字段与固定值或规则集比较。 |
| `regex_check` | 正则完整匹配。 |
| `sequence_order_check` | 按原始行序校验连续性。 |
| `cross_table_mapping` | 单字段包含于引用变量。 |
| `composite_condition_check` | 组合变量筛选和分支断言。 |
| `dual_composite_compare` | 两组组合变量筛选、Key 对齐和字段比较。 |
| `multi_composite_pipeline_check` | 多组串行节点，失败短路。 |
| `multi_composite_mapping_check` | 多组映射节点，独立汇总异常。 |
| `package_items_compare` | IAP 礼包规划与配置 `STR_Items` 比对。 |

## 9. 权限、安全与错误规则

- 规则执行本身不做权限判断，权限在 API 层和数据读取层完成。
- handler 应返回结构化异常，不应抛出用户不可理解的内部错误。
- AI 辅助只能提供建议、候选排序或结构识别，不应绕过确定性规则执行。

## 10. 测试覆盖

- 后端：`test_rule_registry.py`、`test_rule_registry_contract.py`、`test_rule_contracts.py`、`test_engine_snapshot.py`、`test_package_items_compare.py`。
- 前端：`ruleOrchestrationFormModel.test.ts`、`RuleOrchestrationContainer.test.ts`、`workbenchOrchestrationRules.test.ts`、`taskTree.test.ts`。

## 11. 已知限制

- 聚合、公式、平均值等复杂规则未纳入当前规则库。
- `package_items_compare` 只解析 `STR_Items` 中的 `{item,道具ID,数量}`，忽略 `{asgift,...}`。

## 12. 维护检查清单

- 新增规则时同步后端 registry、handler、前端表单、前端摘要、`TaskTree` 转换和测试。
- 修改异常格式时，同步个人校验、项目校验、任务结果和导出。
- 改组合变量语义时，检查所有多组规则和 preview。
- 保持规则类型命名稳定，旧字段清理必须先有迁移计划。
