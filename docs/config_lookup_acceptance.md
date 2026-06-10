# 配置表查询与共享飞书机器人验收清单

本文档用于配置表查询规则、飞书机器人共享 App ID 路由，以及原有飞书命令的端到端人工验收。验收时不要在截图、日志或记录中保存完整的 SVN 密码、Feishu App Secret、AI API Key。

## 1. 环境准备

1. 启动后端、前端和飞书长连接服务，确认管理员账号可进入管理后台，普通项目成员可进入规则配置页。
2. 准备两个项目：
   - 项目 A：绑定群 `chat_id_A`，配置 `query_roots` alias 为 `game_datas`。
   - 项目 B：绑定群 `chat_id_B`，配置同一个或不同的 Feishu App ID。
3. 在项目 A 的数据根下准备版本目录，例如 `/datas_qa88`，并放置规则中声明的 Excel 文件，例如 `IAPConfig.xls`。
4. 在项目 A 发布 `config_lookup` 规则，至少包含一个查询类型 `礼包`，并覆盖 ID 字段、名称字段、输出字段和可选引用表。
5. 如需验收 AI 名称匹配，在项目 A 管理后台配置并测试项目级 AI 凭据；普通成员只能看到脱敏状态。

## 2. 管理后台验收

1. 管理员进入项目 A 管理后台。
2. 保存飞书机器人基础配置、`bound_chat_ids`、`query_roots`、SVN 凭据状态、项目级 AI 凭据与名称匹配参数。
3. 确认 `SVN 下载根目录` 与 `query_roots` 分开展示和保存。
4. 设置 `allowed_open_ids` 为空，确认表示不限制触发人。
5. 设置 `allowed_open_ids` 为指定 open_id，确认非白名单用户无法执行配置表查询。
6. 普通成员不能进入管理后台，也不能查看完整 SVN 密码或 AI API Key。

## 3. 规则配置前端验收

1. 普通项目成员进入 `/rule-configs`，确认可见规则配置入口，管理后台入口不可见。
2. 打开 `/rule-configs/config_lookup`，执行结构校验、保存草稿、发布、查看历史、回滚。
3. 保存草稿和发布时，若出现版本冲突，应提示刷新或手动合并，不应静默覆盖。
4. 发布成功后显示“发布后已立即生效，无需重启机器人”。
5. 使用试查区域分别验证：
   - ID 查询命中并展示字段。
   - 名称查询返回候选或命中结果。
   - 勾选“使用当前草稿试查”不会改变草稿版本、发布状态或版本历史。
   - 版本目录不存在时显示 `未找到版本配置目录：/datas_qa88，请确认目录是否存在于数据根 game_datas 下`。
   - 配置文件不存在时显示 `未找到配置文件：IAPConfig.xls，请确认 /datas_qa88 下是否存在该文件`。

## 4. 飞书命令验收

在项目 A 绑定群内发送以下命令：

1. 原有下载命令：`下载 configs/a.xlsx`
   - 预期：仍走文件下载流程，不触发配置表查询。
2. 原有目录查询命令：`查询 configs`
   - 预期：仍返回目录列表，不触发配置表查询。
3. 原有项目校验命令：`项目校验`
   - 预期：仍执行项目校验并发送校验卡片。
4. 标准配置表查询：`礼包 查询 /datas_qa88 26051802`
   - 预期：按已发布规则查询，返回全部业务命中结果。
5. 紧凑格式：`礼包查询 /datas_qa88 26051802`
   - 预期：与标准格式等价。
6. 查询内容包含空格：`礼包 查询 /datas_qa88 26年7月 扭蛋机 礼包`
   - 预期：查询内容保留空格并进入名称匹配。

## 5. 路由和权限验收

1. 未绑定群发送配置表查询命令。
   - 预期：机器人不回复，只记录服务端日志。
2. 项目 A 和项目 B 使用同一个 App ID。
   - 预期：长连接可共享；`chat_id_A` 路由到项目 A，`chat_id_B` 路由到项目 B。
3. 项目 A 和项目 B 使用不同 App ID。
   - 预期：启动独立长连接，互不影响。
4. `allowed_open_ids` 为空时，任意群成员可执行配置表查询。
5. `allowed_open_ids` 非空且发送人不在白名单时，回复：
   - `当前用户无机器人指令执行权限`

## 6. 错误文案验收

1. 规则未发布：
   - `当前项目尚未发布配置表查询规则，请先在规则配置页发布`
2. 查询类型不存在：
   - `查询类型不存在：xxx`
3. 版本目录不存在：
   - `未找到版本配置目录：/datas_qa88，请确认目录是否存在于数据根 game_datas 下`
4. 配置文件不存在：
   - `未找到配置文件：IAPConfig.xls，请确认 /datas_qa88 下是否存在该文件`
5. AI 不可用：
   - 返回明确降级提示，不返回伪造候选，不暴露 API Key。

## 7. 结果和分段验收

1. ID 查询命中时，纯数字输入优先按 ID 字段精确查询，不触发 AI。
2. ID 查询未命中后，进入 AI 名称匹配。
3. AI 高置信单条候选自动返回详情。
4. AI 多候选返回候选列表。
5. AI 低置信不返回详情。
6. 多分页命中时全部返回，不合并、不只取第一条。
7. 飞书发送层每条消息最多展示 5 个结果；超过 5 个结果或超过消息长度限制时继续拆分。
8. 每段消息标题显示 `第 x/y 段`。

## 8. 自动化回归命令

```powershell
python -m pytest backend/tests/test_feishu_long_conn.py backend/tests/test_config_lookup_service.py backend/tests/test_rule_config_trial_api.py backend/tests/test_rule_configs_api.py
python -m pytest backend/tests
python -m ruff check backend/app backend/tests/test_feishu_long_conn.py backend/tests/test_config_lookup_service.py backend/tests/test_rule_config_trial_api.py

cd frontend
npm run test:unit -- tests/unit/ruleConfigsApi.test.ts tests/unit/ruleConfigViewModel.test.ts
npm run test:unit
npm run build
```

验收通过标准：以上命令通过，人工验收项无阻塞问题，且日志、响应、截图中没有完整 SVN 密码、Feishu App Secret 或 AI API Key。
