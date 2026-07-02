# 数据源能力 Spec

## 0. Codex 快速入口

- 先读文件：`backend/app/api/source_api.py`、`backend/app/loaders/`、`backend/config.py`、`frontend/src/components/workbench/DataSourcePanel.vue`、`frontend/src/api/workbench.ts`、`frontend/src/api/svn.ts`。
- 最常改文件：`backend/app/loaders/local_reader.py`、`backend/app/loaders/svn_manager.py`、`backend/app/loaders/svn_credentials.py`、`backend/app/loaders/svn_cache.py`、`frontend/src/components/workbench/DataSourcePanel.vue`。
- 不要改契约：CSV 已下线；本地文件读取必须经过 allowlist；SVN 远端只支持白名单 host 和 Excel 文件。
- 用例生成 V2 的 `Source Evidence Run` 不是本模块的数据源配置；本地/SVN 策划案文件、图片读取和 `.xls` 图片转换见 `docs/specs/test-case-generation-v2-source-evidence.md`。
- 新增功能入口：新增数据源类型先接入 capabilities、metadata、preview 和执行读取链路。
- 必跑测试：`python -m pytest backend/tests/test_source_api_security.py backend/tests/test_svn_source_api.py backend/tests/test_svn_manager.py backend/tests/test_svn_cache.py backend/tests/test_svn_credentials.py -q`；前端跑 `DataSourcePanel.test.ts`、`VariablePoolPanel.test.ts`。
- 常见误区：浏览器不能直接读取用户本地绝对路径；共享或生产部署应优先使用上传、SVN 或飞书数据源。

## 1. 模块目标

数据源模块为个人校验和项目校验提供统一的数据读取、元数据识别、列预览和组合变量预览能力。

## 2. 用户入口与适用场景

数据源在个人校验和项目校验中使用：

- 本地 Excel：适合服务所在机器或 allowlist 内共享盘。
- 浏览器上传 Excel：适合同网段共享部署或普通浏览器用户。
- SVN Excel：适合远端版本目录。
- 飞书电子表格：适合项目机器人授权后的在线表格。

## 3. 核心概念

- capabilities：前端展示当前支持的数据源能力。
- metadata：读取文件/表格的 Sheet 和列。
- column preview：读取单列样例。
- composite preview：读取多列组合变量样例。
- path allowlist：服务端本地文件读取安全边界。
- SVN cache：远端文件缓存和刷新边界。

## 4. 前端边界

- 数据源面板主要在 `frontend/src/components/workbench/DataSourcePanel.vue`。
- API 封装分布在 `frontend/src/api/workbench.ts` 和 `frontend/src/api/svn.ts`。
- 变量池依赖 metadata 和 preview 结果，位于 `VariablePoolPanel.vue`。
- 路径替换逻辑位于 `frontend/src/utils/sourcePathReplacement.ts` 和相关 store action。

## 5. 后端边界

- `backend/app/api/source_api.py` 暴露数据源能力、上传、本地选择、metadata、preview 和 SVN API。
- `backend/app/loaders/local_reader.py` 负责本地 Excel 读取和 allowlist 校验。
- `backend/app/loaders/svn_manager.py` 负责 SVN 目录、下载和刷新。
- `backend/app/loaders/svn_credentials.py` 负责 SVN 凭据加密保存。
- `backend/app/loaders/feishu_reader.py` 读取飞书电子表格，但授权和机器人配置属于飞书集成模块。

## 6. 数据与持久化边界

- 上传文件和 SVN 缓存属于 runtime 数据，不进入源码包。
- SVN 凭据按用户和 host 隔离，使用 Fernet 加密。
- 数据源配置随个人或项目配置持久化，读取时再解析真实文件。
- 用例生成 V2 的 `svn_file` Source Evidence 不复用个人 SVN 凭据或本模块的 SVN cache 权限边界；它使用项目级 `project_svn_credentials` 和独立 `project_source_evidence_svn_roots`，文件只落当前 Source Evidence Run 目录。

## 7. API 契约

| API | 说明 |
|---|---|
| `GET /api/v1/sources/capabilities` | 数据源能力声明。 |
| `POST /api/v1/sources/upload` | 上传 Excel。 |
| `POST /api/v1/sources/local-pick` | 服务端本地选择器，默认关闭。 |
| `POST /api/v1/sources/local-directory-validate` | 校验本地目录。 |
| `POST /api/v1/sources/metadata` | 读取 Sheet 和列。 |
| `POST /api/v1/sources/column-preview` | 单列预览。 |
| `POST /api/v1/sources/composite-preview` | 组合变量预览。 |
| `POST /api/v1/sources/svn-list` | SVN 目录浏览。 |
| `POST /api/v1/sources/svn-credentials` | 保存 SVN 凭据。 |
| `GET /api/v1/sources/svn-credentials*` | 读取 SVN 凭据状态。 |
| `DELETE /api/v1/sources/svn-credentials/{host}` | 删除 SVN 凭据。 |
| `POST /api/v1/sources/svn-refresh` | 刷新 SVN 缓存。 |

## 8. 关键流程

1. 前端读取 capabilities 展示可选类型。
2. 用户选择或上传数据源。
3. 前端调用 metadata 获取 Sheet 和列。
4. 变量池调用 column preview 或 composite preview 生成样例。
5. 执行时后端根据数据源类型走对应 loader。

## 9. 权限、安全与错误规则

- 数据源相关接口需要登录并校验当前项目成员关系。
- 本地读取仅允许上传目录、SVN 缓存目录和 `LOCAL_FILE_ROOT_ALLOWLIST` 内路径。
- `ENABLE_LOCAL_PICKER` 默认 `false`。
- SVN URL 受 `SVN_URL_ALLOWLIST` 限制，鉴权失败返回 HTTP 403。

## 10. 测试覆盖

- 后端：`test_source_api_security.py`、`test_svn_source_api.py`、`test_svn_manager.py`、`test_svn_cache.py`、`test_svn_credentials.py`。
- 前端：`DataSourcePanel.test.ts`、`VariablePoolPanel.test.ts`、`variablePreviewFilters.test.ts`。

## 11. 已知限制

- CSV 已下线。
- SVN 远端只支持 `http(s)://`、白名单 host 和 `.xls/.xlsx` 单文件；该限制仅指个人/项目校验数据源链路，用例生成 V2 的 SVN 来源证据走独立 `Source Evidence Run` 链路。
- `Remote SVN Query Root` 只用于配置表查询；用例生成来源证据的管理员边界是 `Source Evidence SVN Root`，通过 `GET/PUT /api/v1/admin/projects/{project_id}/source-evidence-svn-roots` 独立维护。
- 全局 SVN cache 由 `runtime_cleanup` 按 `SVN_CACHE_RETENTION_DAYS` 清理过期目录；用例生成 V2 的 SVN 文件副本只清理当前 Source Evidence Run 目录，不复用或删除本模块的全局 cache。
- 飞书仅支持电子表格和 wiki 电子表格链接。

## 12. 维护检查清单

- 新增数据源类型时，更新 capabilities、metadata、preview、执行读取和前端类型。
- 修改路径策略时，跑 source security 测试。
- 修改 SVN 行为时，检查 403 / 401 边界。
- 修改上传 runtime 时，确认 release 包不会包含 runtime 数据。
