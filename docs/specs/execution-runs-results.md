# 执行任务与结果 Spec

## 0. Codex 快速入口

- 先读文件：`backend/app/api/execute_api.py`、`backend/app/api/fixed_rules_api.py`、`backend/app/api/execute_runs_api.py`、`backend/app/execute_runs_service.py`、`backend/app/execution_pipeline.py`、`backend/app/execution_summary.py`、`backend/app/result_store.py`、`backend/app/result_exporter.py`。
- 最常改文件：`frontend/src/views/MainBoard.vue`、`frontend/src/views/FixedRulesBoard.vue`、`frontend/src/api/fixedRules.ts`、`frontend/src/api/workbench.ts`。
- 不要改契约：同步执行结果结构保持一致；任务接口是第一阶段进程内后台任务，不承诺分布式队列、重试、进度百分比或取消 API。
- 新增功能入口：执行摘要放入 `execution_summary.py`；任务化执行放入 `execute_runs_service.py`；导出放入 `result_exporter.py`。
- 必跑测试：`python -m pytest backend/tests/test_execute_api.py backend/tests/test_execute_runs_api.py backend/tests/test_fixed_rules_api.py backend/tests/test_engine_snapshot.py -q`。
- 常见误区：不要为个人校验和项目校验复制两套结果结构；不要把任务状态当作生产级队列语义。

## 1. 模块目标

本模块统一个人校验、项目校验和后台任务的执行过程、结果存储、摘要统计、异常明细读取和 Excel 导出。

## 2. 用户入口与适用场景

- 个人校验结果区：同步执行后展示统计和异常。
- 项目校验结果区：执行、分页读取历史明细并导出。
- 任务接口：为大 Excel、SVN 或飞书校验提供第一阶段后台执行能力。

## 3. 核心概念

- 同步执行：HTTP 请求等待执行完成。
- Execution Run：后台任务主表，记录状态、模式、时间、错误和统计。
- Result Store：结果落库和读取。
- Execution Summary：统一摘要构建。
- Export：结果导出为 Excel。

## 4. 前端边界

- 个人校验当前主要展示同步执行结果。
- 项目校验提供结果分页和导出入口。
- 若页面接入任务接口，需要轮询 run 状态，再读取 items。
- 下载应复用 `apiDownloadFile`。

## 5. 后端边界

- `execute_api.py`：个人同步执行、结果读取和导出。
- `fixed_rules_api.py`：项目同步执行、结果读取和导出。
- `execute_runs_api.py`：任务创建、状态查询和分页明细。
- `execute_runs_service.py`：后台任务生命周期。
- `execution_pipeline.py`：执行流程整合。
- `execution_summary.py`：摘要统计。
- `result_store.py` 和 `result_exporter.py`：结果存储和导出。

## 6. 数据与持久化边界

- 执行结果按项目和作用域隔离。
- 服务启动时遗留的 `pending/running` 任务会标记为 `failed`。
- 同步执行和任务执行复用摘要和结果结构。

## 7. API 契约

| API | 说明 |
|---|---|
| `POST /api/v1/engine/execute` | 个人校验同步执行。 |
| `GET /api/v1/engine/results/{result_id}` | 读取个人执行结果。 |
| `GET /api/v1/engine/results/{result_id}/export` | 导出个人执行结果。 |
| `POST /api/v1/fixed-rules/execute` | 项目校验同步执行。 |
| `GET /api/v1/fixed-rules/results/{result_id}` | 读取项目执行结果。 |
| `GET /api/v1/fixed-rules/results/{result_id}/export` | 导出项目执行结果。 |
| `POST /api/v1/execute-runs` | 创建后台任务。 |
| `GET /api/v1/execute-runs/{run_id}` | 查询任务状态。 |
| `GET /api/v1/execute-runs/{run_id}/items` | 分页读取任务异常明细。 |

## 8. 关键流程

1. API 层完成权限和入参校验。
2. 执行流程读取数据源、运行规则引擎并构建异常结果。
3. 摘要模块生成耗时、扫描行数、失败数据源和异常总数。
4. 结果写入存储并返回统一结构。
5. 导出接口把异常明细转换为 Excel。
6. 任务接口额外维护 `pending/running/success/failed/cancelled` 状态。

## 9. 权限、安全与错误规则

- 结果读取必须校验项目和作用域。
- 任务失败需要记录受控错误信息，不暴露密钥或内部路径细节。
- HTTP 401 只表达认证失效；SVN 鉴权失败仍应是 403。

## 10. 测试覆盖

- 后端：`test_execute_api.py`、`test_execute_runs_api.py`、`test_fixed_rules_api.py`、`test_engine_snapshot.py`、`test_execute_package_items_runtime.py`。
- 前端：`FixedRulesResultPanelPackageItems.test.ts`、E2E 冒烟测试。

## 11. 已知限制

- 任务接口为进程内 `BackgroundTasks`，不支持跨进程调度、失败重试、进度百分比或取消 API。
- 前端并非所有执行入口都已切到任务接口。

## 12. 维护检查清单

- 修改结果结构时，同步个人、项目、任务、导出和前端类型。
- 新增任务状态字段时，新增 migration 和任务接口测试。
- 改导出时，确认 release 包不包含生成文件。
- 改后台执行时，检查服务重启遗留任务处理。
