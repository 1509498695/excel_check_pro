# Excel Check 架构设计

> 本文档只记录稳定架构、核心契约、接口边界和限制。启动、部署和联调见 [../README.md](../README.md)，代码位置见 [MODULES.md](MODULES.md)。

## 1. 系统边界

Excel Check 解决配置表规则校验的工程问题：把数据源、变量和规则抽象为统一 `TaskTree`，个人校验和项目校验共用同一个执行引擎与结果协议。

| 业务线 | 路由 | 持久化边界 | 用途 |
|---|---|---|---|
| 个人校验 | `/` | `project_id + user_id` | 临时排查、个人编排、IAP 礼包校验。 |
| 项目校验 | `/fixed-rules` | `project_id` | 长期规则配置、导入个人规则、周期性复用。 |

明确不做：

- 不做 SaaS 化、容器编排、反代、HTTPS。
- 不恢复 CSV 数据源。
- 飞书只支持电子表格和 wiki 电子表格链接；不支持多维表格、文档表格或任意 Drive 文件。
- AI provider 基础能力只服务项目级 AI 配置、配置表查询 AI 名称匹配、礼包结构识别和活动任务建议；个人校验不提供自然语言生成规则入口。
- SVN 远端只支持白名单 host、`http(s)://`、单文件 `.xls/.xlsx`。

## 2. 核心契约

### 2.1 `TaskTree`

`TaskTree` 是统一执行入参：

```python
class TaskTree:
    sources: list[DataSource]
    variables: list[VariableTag]
    rules: list[ValidationRule]
```

关键字段：

- `DataSource`: `id / type / path / url / pathOrUrl / token`
- `VariableTag`: `tag / source_id / sheet / variable_kind / column / columns / key_column / expected_type`
- `ValidationRule`: `rule_id / rule_type / params`

执行入参模型默认拒绝未知字段；历史字段兼容只在配置读取、迁移或导入层处理。

个人校验中的 `package_items_compare` 规则是 `TaskTree` 的兼容扩展：规则保存时携带 `package_parse_config`，执行前由运行时预处理读取飞书 Sheet，解析为临时组合变量 `__runtime_package_plan__:{rule_id}`，再交给既有规则 handler 与右侧礼包配置组合变量比对。这个过程不改变 `TaskTree` 顶层结构，也不新增第二套执行入口。

### 2.2 项目校验配置

项目校验配置当前版本为 `version = 6`，包含 `sources / variables / groups / rules`。旧版 `version 2/3/4/5` 在读取时自动迁移。多组串行和多组映射规则仍保留部分兼容字段，但真实执行以节点配置为准。

### 2.3 统一执行结果

`POST /api/v1/engine/execute` 与 `POST /api/v1/fixed-rules/execute` 返回同一结构：

```python
{
    "code": 200,
    "msg": "Execution Completed",
    "meta": {
        "execution_time_ms": int,
        "total_rows_scanned": int,
        "failed_sources": [str],
    },
    "data": {
        "abnormal_results": [
            {
                "level": "error",
                "rule_name": str,
                "location": str,
                "row_index": int,
                "raw_value": Any,
                "display_value": Any,
                "message": str,
            }
        ]
    },
}
```

固定规则配置读取可额外返回 `meta.config_issues`，用于非阻断告警。

## 3. 规则能力

当前规则库支持 11 类规则：

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
| `package_items_compare` | IAP 礼包校验：飞书礼包规划明细与配置变量 `STR_Items` 按礼包 ID、道具 ID 无序比对。 |

规则引擎由注册调度、领域工具和 handler 三层组成。旧路径 shim 仅为兼容保留。

`package_items_compare` 只解析 `STR_Items` 中的 `{item,道具ID,数量}`，忽略 `{asgift,...}`；`[]` 表示右侧空道具列表。异常结果会按礼包和道具输出缺失、多余、数量不一致、重复道具、礼包不存在和格式错误等结构化明细。

## 4. API 边界

所有业务 API 位于 `/api/v1` 下。

| 模块 | 入口 |
|---|---|
| 认证 | `/auth/register`、`/auth/login`、`/auth/me`、`/auth/change-password`、`/auth/switch-project/{project_id}` |
| 管理后台 | `/admin/projects*`、`/admin/projects/{id}/members*`、`/admin/users/{id}/reset-password`、`/admin/projects/{id}/feishu-bot*` |
| 数据源 | `/sources/capabilities`、`/sources/upload`、`/sources/local-pick`、`/sources/metadata`、`/sources/column-preview`、`/sources/composite-preview`、`/sources/svn-*` |
| 飞书数据源 | `/feishu/sources/check-permission`、`/feishu/sources/send-authorization-card`、`/feishu/sources/oauth/callback` |
| 个人校验 | `/workbench/config`、`/workbench/svn-update`、`/workbench/package-items/preview`、`/engine/execute` |
| 项目级 AI 配置 | `/admin/projects/{id}/ai-config*` |
| 项目校验 | `/fixed-rules/config`、`/fixed-rules/import/workbench/draft`、`/fixed-rules/import/workbench/preview`、`/fixed-rules/import/workbench/commit`、`/fixed-rules/execute`、`/fixed-rules/results/*` |

SVN 鉴权失败使用 HTTP 403，不触发前端登录态过期逻辑；HTTP 401 只表达认证失效。

飞书数据源权限不足时不直接失败为登录态问题：前端先调用权限检测接口，必要时通过项目飞书机器人向默认群发送授权卡片；有权限的飞书用户完成 OAuth 后，服务端把机器人加入表格只读协作者，再复用同一飞书电子表格读取链路获取元数据、列预览和执行数据。

## 5. 项目级 AI provider 基础能力

项目级 AI 凭据是系统唯一 AI 配置入口，由项目管理员在管理后台保存、测试、删除和查看脱敏状态。个人设置只承担账号、密码和项目切换职责，后端 AI 配置接口只保留项目级边界。所有保留的 AI 辅助能力都读取当前项目的 AI 凭据。

保留的 AI 调用场景：

- 配置表查询 AI 名称匹配：在确定性候选范围内做排序或归一化，不改变查询规则配置。
- 礼包规划表结构识别。
- 活动任务配置建议。

项目级 AI 不可用时，自动辅助能力应尽量回退到确定性逻辑并给出告警；用户显式触发的 AI 操作应提示联系项目管理员配置项目级 AI 凭据。任何接口、日志和持久化摘要都不得暴露完整 API Key。

## 6. 多用户与安全

- JWT 携带用户与当前项目。
- 超级管理员可管理全部项目；项目管理员只能管理授权项目和受限默认项目视图。
- 个人校验配置按 `project_id + user_id` 隔离。
- 项目校验配置按 `project_id` 隔离。
- SVN 凭据按用户和 host 隔离，使用 Fernet 加密落盘。
- SVN URL 受 `SVN_URL_ALLOWLIST` 限制。
- 飞书机器人配置按项目隔离，`app_secret` 加密落库；飞书表格授权记录按 `project_id + source_id` 记录，并可按 spreadsheet token 复用已授权表格。

## 7. 已知限制

| 限制 | 状态 |
|---|---|
| 飞书数据源 | 仅支持飞书电子表格和 wiki 电子表格，依赖项目机器人、OAuth callback 和表格只读授权。 |
| CSV 数据源 | 已下线，仅保留历史提示。 |
| 多配置集切换 | 未开放。 |
| SVN 远端 | 仅支持白名单 host、`http(s)://`、单文件 Excel。 |
| SVN 缓存清理 | 暂无定时清理策略。 |
| IAP 礼包校验 | 当前重点接在个人校验 03 规则页签；固定规则侧保留预览与运行时兼容能力，但不作为主要业务入口。 |
| AI 能力 | 当前仅保留 provider 基础调用、礼包规划表结构识别和活动任务配置建议。 |
