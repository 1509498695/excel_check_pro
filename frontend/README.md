# Excel Check Frontend

前端子项目使用 `Vue 3 + TypeScript + Vite + Pinia + Element Plus + Tailwind v3`。项目总览见 [../README.md](../README.md)，接口契约见 [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)。

## 1. 安装与启动

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

默认开发地址：<http://127.0.0.1:5173>。开发期 API 通过 Vite 代理到 <http://127.0.0.1:8000>。
`npm ci` 会根据 `frontend/package-lock.json` 重新安装依赖，源码包不包含也不复用 `node_modules`。

## 2. 构建与检查

```powershell
cd frontend
npm ci
npm run lint
npm run test:unit
npm run format:check
npm run build
```

`npm run build` 会先执行 `vue-tsc` 类型检查，再输出生产包到 `frontend/dist/`。完整后端安装、后端测试、前端 `npm ci`、lint、单元测试和构建可在项目根目录运行 `.\scripts\check-standards.ps1` 或 `python scripts/check-standards.py`。共享部署由根目录脚本 `.\scripts\start-local-deploy.ps1` 统一处理。

可选端到端冒烟测试使用 Playwright，覆盖默认管理员登录、上传 Excel、创建个人非空规则、执行、导入项目校验、执行项目校验和查看结果：

```powershell
cd frontend
npm ci
npx playwright install chromium
npm run e2e
```

`npm run e2e` 会自动清理并重建项目根目录 `.e2e-runtime/`，后端使用独立 SQLite 和 runtime，前端代理到隔离后端端口。失败时保留截图、trace 和视频，可用 `npm run e2e:report` 打开报告。

## 3. 目录约定

```text
frontend/src
├── api/          # HTTP 封装
├── components/   # 共享 shell 与业务组件
├── content/      # 静态内容
├── features/     # 跨页面功能切片
├── router/       # 路由与守卫
├── rules/        # 规则前端模型
├── store/        # Pinia 状态
├── styles/       # token、Element Plus 校准、页面域样式
├── types/        # API 与业务类型
├── utils/        # 通用工具
├── views/        # 页面入口
├── App.vue
├── main.ts
└── style.css     # Tailwind 入口与全局兼容样式
```

更细的代码定位见 [../docs/MODULES.md](../docs/MODULES.md)。
全局样式 token、Element Plus 覆盖和页面域样式约定见 [../docs/FRONTEND_STYLE_GUIDE.md](../docs/FRONTEND_STYLE_GUIDE.md)。

## 4. 当前页面

| 路由 | 说明 |
|---|---|
| `/` | 个人校验四步工作流，含数据源、变量、规则、结果和 AI 规则助手。 |
| `/fixed-rules` | 项目校验配置、导入个人规则、执行、结果分页和导出。 |
| `/admin` | 项目、成员、角色、密码和项目飞书机器人配置。 |
| `/profile` | 账号信息、密码、项目切换、AI 配置和使用说明入口。 |
| `/user-guide` | 登录后使用说明。 |

个人校验 03 规则页签额外提供 `IAP礼包校验` 入口。弹窗会选择飞书礼包规划 Sheet 和包含 `INT_PackageId / STR_Items` 的礼包配置组合变量，调用 `/api/v1/workbench/package-items/preview` 生成解析预览，保存后由执行链路重新读取飞书 Sheet 并完成最终比对。

## 5. 设计与代码约定

- 页面布局优先复用 `components/shell/`。
- 业务组件只处理当前业务域，不复制全局按钮、表格和状态样式。
- 新增颜色、间距、圆角、阴影优先使用 `src/styles/tokens.css` 中的 CSS variables。
- Element Plus 全局覆盖集中在 `src/styles/element-plus.css`；组件专属覆盖必须限定在组件根 class 下。
- API 请求集中在 `src/api/`，接口类型集中在 `src/types/`。
- Pinia store 维护业务状态，不散落 `fetch`。
- 历史 wire 字段保持原名，例如 `pathOrUrl`、`source_id`、`rule_type`。
- `corePlugins.preflight = false`，避免 Tailwind reset 与 Element Plus 冲突。

## 6. 联调入口

完整联调步骤见 [../README.md](../README.md) 的“最短联调”。规则能力、AI 智能添加规则、SVN、飞书电子表格、IAP 礼包校验和接口契约见 [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)。
