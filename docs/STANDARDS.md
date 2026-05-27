# Excel Check 开发规范

本文档是当前开发与文档维护规范源。若规范需要调整，先改本文档，再按单模块单切片实施。

## 1. 基本原则

- 兼容优先：无迁移方案时不得破坏 API 路径、JSON 字段、`TaskTree` 和统一执行结果结构。
- 单模块单切片：一次只处理一个明确模块或文档切片。
- 文档跟随事实：对外行为、部署方式、接口语义或占位状态变化时，同步稳定文档。
- 历史兼容字段不直接删除；旧 shim 和迁移逻辑保留到有明确清理窗口。

## 2. 后端规范

- Python 文件、模块、函数、变量使用 `snake_case`；模型和异常类使用 `PascalCase`。
- FastAPI 路由按业务模块拆分，再由 `backend/app/api/router.py` 聚合。
- Pydantic 入参模型默认 `extra="forbid"`，兼容历史配置的模型除外。
- 普通业务响应使用 `code/msg/data`；执行响应额外含 `meta`。
- 新规则复用 `ValidationRule.rule_type` 和规则注册中心，不复制第二套执行入口。
- 中文 docstring 只写在模块入口、公开函数、复杂分支和兼容逻辑处。

## 3. 前端规范

- Vue 组件使用 `PascalCase.vue`；组合函数使用 `useXxx`；普通变量和函数使用 `camelCase`。
- 请求集中在 `frontend/src/api/`；类型集中在 `frontend/src/types/`。
- Pinia store 维护状态和动作，请求统一走 `apiFetch` / `apiDownloadFile`。
- 页面布局优先复用 `components/shell/`。
- 历史 wire 字段保持原名，例如 `pathOrUrl`、`source_id`、`rule_type`、`local_path_replacement_presets`。

## 4. API 与类型规范

- API URL 统一以 `/api/v1` 开头，前端不得硬编码主机 IP。
- 统一执行入口保持：
  - 个人校验：`POST /api/v1/engine/execute`
  - 项目校验：`POST /api/v1/fixed-rules/execute`
- `TaskTree` 稳定结构保持 `sources / variables / rules`。
- 前端新增响应类型优先复用 `ApiResponse<TData, TMeta>`、`ExecutionResponse<TItem>`、`ApiFileResponse`。
- 新增字段优先做兼容扩展，再规划旧字段清理。

## 5. 检查与测试

```powershell
python -m ruff check backend
python -m pytest backend/tests -q
```

```powershell
cd frontend
npm run lint
npm run build
```

```powershell
.\scripts\check-standards.ps1
```

## 6. 稳定文档职责

| 文档 | 职责 |
|---|---|
| `README.md` | 项目入口、启动、部署、最短联调、常用 API。 |
| `docs/ARCHITECTURE.md` | 稳定架构、核心契约、接口边界、限制。 |
| `docs/MODULES.md` | 路由、目录和业务切片定位。 |
| `docs/STANDARDS.md` | 本文档：开发与文档维护规则。 |
| `frontend/README.md` | 前端子项目启动、构建、目录和约定。 |
| `CHANGELOG.md` | 版本级变化，不记录分钟级流水。 |
| `PROJECT_RECORD.md` | 当前执行进度记录，按次追加本次完成和项目整体状态。 |
| `docs/archive/` | 历史需求、旧进度日记、一次性方案和快照，不再追加。 |

维护规则：

- 当前说明不得复制历史流水；需要追溯时链接到 `docs/archive/`。
- `README.md` 修改时更新 `文档更新时间：YYYY-MM-DD HH:mm`。
- 每次文档或代码治理后追加 `PROJECT_RECORD.md`，不再追加 `docs/archive/PROJECT_RECORD.md`。
- 文档中出现 API 路径时，以代码路由为准。
- 仅文档治理不要求改动业务代码或归档旧进度日记。
