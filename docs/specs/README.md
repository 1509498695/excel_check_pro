# Excel Check 业务能力 Spec 索引

本文档面向 Codex 和维护者，用于在开发新功能、修复问题或调整接口前快速建立项目上下文。Spec 按业务能力切片划分，每份文档覆盖前端、后端、数据、API、测试和限制的完整链路。

## 使用规则

- 修改某个业务能力前，先读对应 Spec，再读 [../ARCHITECTURE.md](../ARCHITECTURE.md) 中的全局契约。
- 一次只处理一个业务能力切片；跨模块改动需要在相关 Spec 中交叉确认边界。
- `TaskTree`、统一执行入口和统一结果结构属于全局稳定契约，除非先形成明确迁移方案，否则不得破坏。
- Spec 记录当前事实和维护入口，不记录历史流水；历史资料仍在 [../archive/](../archive/)。

## 模块清单

| 模块 | Spec | 开发前重点 |
|---|---|---|
| 身份、项目与后台管理 | [admin-auth-projects.md](admin-auth-projects.md) | 登录、注册、JWT、项目切换、角色、成员、密码、管理后台。 |
| 个人校验工作台 | [workbench-personal-check.md](workbench-personal-check.md) | `/` 四步流程、个人配置、规则编排、执行入口。 |
| 项目校验 / 固定规则 | [fixed-rules-project-check.md](fixed-rules-project-check.md) | `/fixed-rules`、项目级配置、导入个人规则、结果分页和导出。 |
| 规则引擎与规则模型 | [rule-engine.md](rule-engine.md) | `TaskTree`、11 类规则、handler、registry、执行结果。 |
| 数据源能力 | [data-sources.md](data-sources.md) | 本地 Excel、上传 Excel、SVN、metadata、preview、路径安全。 |
| 飞书集成 | [feishu-integration.md](feishu-integration.md) | 飞书机器人、OAuth、授权卡片、电子表格读取、消息通道。 |
| 规则配置工作区 / 配置表查询 | [rule-configs-config-lookup.md](rule-configs-config-lookup.md) | Markdown 查询规则、发布、历史、试运行、查询运行时。 |
| 项目级 AI 能力 | [ai-project-credentials.md](ai-project-credentials.md) | 项目级凭据、provider、脱敏、不可用策略、调用方边界。 |
| 执行任务与结果 | [execution-runs-results.md](execution-runs-results.md) | 同步执行、后台任务、结果存储、异常明细、导出。 |
| 交付、部署与工程治理 | [delivery-devops.md](delivery-devops.md) | Alembic、检查脚本、CI、源码包、生产安全配置。 |
| 用例生成（V1 主链路已完成） | [test-case-generation.md](test-case-generation.md) | 独立用例生成页、项目级参考案例库、策划案快照、AI 生成、Excel 导出的 V1 需求与当前边界。 |
| 用例生成飞书文档读取移植方案 | [test-case-generation-feishu-doc-migration.md](test-case-generation-feishu-doc-migration.md) | V1 完成后移植 `qa-case` 飞书文档富读取、Source Evidence Run、视觉证据、TTL 清理和 Vision AI 凭据的专项方案。 |
| 用例生成 V2 需求文档 | [test-case-generation-v2-requirements.md](test-case-generation-v2-requirements.md) | V2 用户目标、范围、角色、流程、验收和测试覆盖要求。 |
| 用例生成 V2 Source Evidence | [test-case-generation-v2-source-evidence.md](test-case-generation-v2-source-evidence.md) | 飞书/本地/SVN 来源统一 Source Evidence Run、`.xls` 图片转换、视觉证据采纳和校验。 |

## 文档边界

| 文档 | 职责 |
|---|---|
| `README.md` | 项目入口、启动、部署、最短联调和常用 API。 |
| `docs/ARCHITECTURE.md` | 稳定架构、全局契约、接口边界和限制。 |
| `docs/MODULES.md` | 路由、目录、业务切片和 Spec 定位。 |
| `docs/STANDARDS.md` | 开发与文档维护规则。 |
| `docs/specs/*.md` | 业务能力维护上下文和 Codex 开发前阅读入口。 |
| `CONTEXT.md` | 领域术语表，不放实现细节或 Spec 内容。 |
| `docs/adr/` | 难逆转、存在取舍且未来会疑惑的架构决策。 |

## 单份 Spec 模板

```markdown
# 模块名 Spec

## 0. Codex 快速入口
- 先读哪些文件：
- 最常改哪些文件：
- 不要改哪些契约：
- 新增功能通常从哪里接入：
- 必跑测试：
- 常见误区：

## 1. 模块目标
## 2. 用户入口与适用场景
## 3. 核心概念
## 4. 前端边界
## 5. 后端边界
## 6. 数据与持久化边界
## 7. API 契约
## 8. 关键流程
## 9. 权限、安全与错误规则
## 10. 测试覆盖
## 11. 已知限制
## 12. 维护检查清单
```
