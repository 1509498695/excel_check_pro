# 规则配置工作区 / 配置表查询 Spec

## 0. Codex 快速入口

- 先读文件：`CONTEXT.md` 中查询规则术语、`frontend/src/views/RuleConfigsView.vue`、`frontend/src/views/RuleConfigLookupView.vue`、`frontend/src/api/ruleConfigs.ts`、`backend/app/api/rule_configs_api.py`、`backend/app/rule_configs/`、`backend/app/config_lookup/`。
- 最常改文件：`backend/app/rule_configs/parser.py`、`backend/app/rule_configs/service.py`、`backend/app/config_lookup/service.py`、`frontend/src/features/rule-configs/`。
- 不要改契约：一份 Query Rule Configuration 只描述一个 query type；发布版本才影响运行时；飞书只是命令通道，查询语义归本模块。
- 新增功能入口：新增规则族从 `rule_configs` 的 family 机制接入；配置表查询规则族是 `config_lookup`。
- 必跑测试：`python -m pytest backend/tests/test_rule_config_parser.py backend/tests/test_rule_configs_api.py backend/tests/test_rule_config_trial_api.py backend/tests/test_config_lookup_service.py -q`；前端跑 `ruleConfigsApi.test.ts`、`ruleConfigViewModel.test.ts`。
- 常见误区：不要把查询规则和项目校验固定规则合并；二者发布、运行时和领域语言不同。

## 1. 模块目标

规则配置工作区为项目成员提供 Markdown 化的项目规则配置能力。当前重点规则族是 `config_lookup`，用于配置 Feishu bot 的配置表查询命令。

## 2. 用户入口与适用场景

| 路由 | 说明 |
|---|---|
| `/rule-configs` | 规则配置工作区首页，浏览规则族和查询规则。 |
| `/rule-configs/config_lookup/:ruleId` | 编辑、校验、发布、查看历史和试运行单条查询规则。 |

适用场景：

- 项目成员维护“礼包 查询 /datas 26051802”这类配置表查询规则。
- 发布规则后，Feishu bot 按项目和 query type 执行查询。
- 在发布前使用试运行验证文件、Sheet、字段和输入匹配。

## 3. 核心概念

- Rule Configuration Workspace：项目成员可见的规则配置工作区。
- Rule Family：规则族，当前主要是 `config_lookup`。
- Query Rule Configuration：一个 query type 的 Markdown 查询规则。
- Query Type：确定性命令路由 key，例如 `礼包`。
- Query Rule Draft：可编辑草稿，不影响运行时。
- Published Query Rule Version：已校验并立即影响运行时的版本。
- Lookup Trial Run：不发布的试运行。
- Query Root Alias：配置中引用的查询根别名。
- Versioned Config Folder：用户命令中的版本目录，例如 `/datas`。

## 4. 前端边界

- `RuleConfigsView.vue` 是规则配置首页。
- `RuleConfigLookupView.vue` 是 `config_lookup` 编辑器。
- `frontend/src/api/ruleConfigs.ts` 封装规则配置 API。
- `frontend/src/features/rule-configs/` 承载编辑器 view model 和查询规则处理。
- 前端展示 Markdown，但发布前必须依赖后端确定性校验。

## 5. 后端边界

- `backend/app/api/rule_configs_api.py` 暴露规则配置 CRUD、草稿、发布、校验、版本、回滚和试运行 API。
- `backend/app/rule_configs/parser.py` 解析中文 Markdown 规则语言。
- `backend/app/rule_configs/service.py` 管理草稿、发布版本、冲突和历史。
- `backend/app/config_lookup/service.py` 执行配置表查询运行时。
- `backend/app/config_lookup/ai_matcher.py` 只在确定性候选内进行 AI 名称匹配。

## 6. 数据与持久化边界

- 规则配置按 `project_id`、`rule_family` 和 query type 隔离。
- 发布历史只记录已发布版本；草稿保存不进入发布历史。
- 删除查询规则后，不回退到历史版本执行。
- 查询根、机器人配置和项目级 AI 凭据由项目配置提供，本模块只消费。

## 7. API 契约

| API | 说明 |
|---|---|
| `GET /api/v1/rule-configs/{rule_family}` | 列表。 |
| `POST /api/v1/rule-configs/{rule_family}` | 创建规则。 |
| `GET /api/v1/rule-configs/{rule_family}/credentials/status` | 查看相关凭据状态。 |
| `GET /api/v1/rule-configs/{rule_family}/{rule_id}` | 详情。 |
| `DELETE /api/v1/rule-configs/{rule_family}/{rule_id}` | 删除。 |
| `PUT /api/v1/rule-configs/{rule_family}/{rule_id}/draft` | 保存草稿。 |
| `POST /api/v1/rule-configs/{rule_family}/{rule_id}/publish` | 发布。 |
| `POST /api/v1/rule-configs/{rule_family}/{rule_id}/validate` | 校验草稿。 |
| `GET /api/v1/rule-configs/{rule_family}/{rule_id}/versions` | 发布历史。 |
| `POST /api/v1/rule-configs/{rule_family}/{rule_id}/versions/{version}/rollback` | 回滚到草稿。 |
| `POST /api/v1/rule-configs/{rule_family}/{rule_id}/trial` | 试运行。 |

## 8. 关键流程

1. 项目成员创建 query type 对应的查询规则。
2. 编辑器保存当前草稿。
3. 用户校验 Markdown 结构和确定性字段。
4. 发布后生成 Published Query Rule Version，并立即影响运行时。
5. Feishu bot 收到命令后按 chat 路由到项目，再按 query type 找发布规则。
6. 运行时读取 query root 和 versioned config folder，匹配输入并回复结果或候选。

## 9. 权限、安全与错误规则

- 规则配置按项目隔离。
- 发布冲突需要显式提示，不做静默覆盖。
- Markdown 只接受当前中文规则语言，不接受同义词、英文 schema 或多 query bundle。
- AI 只能在确定性候选范围内排序或归一化，不选择文件、Sheet 或输出字段。

## 10. 测试覆盖

- 后端：`test_rule_config_parser.py`、`test_rule_configs_api.py`、`test_rule_config_trial_api.py`、`test_config_lookup_service.py`。
- 前端：`ruleConfigsApi.test.ts`、`ruleConfigViewModel.test.ts`。

## 11. 已知限制

- 第一阶段发布校验不要求实时 SVN Excel 字段检查。
- 查询规则删除后不保留历史运行 fallback。
- AI 不可用时尽量回退确定性匹配；显式 AI 行为提示联系项目管理员。

## 12. 维护检查清单

- 改 Markdown 语法时，同步 parser、前端编辑提示、测试和 `CONTEXT.md` 术语。
- 改发布或回滚语义时，检查版本历史和运行时选择。
- 改 Feishu 命令语义时，本 Spec 是主文档；飞书 Spec 只补通道边界。
- 新增规则族时，不要破坏 `config_lookup` 的单 query type 规则。
