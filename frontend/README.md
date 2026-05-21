# Excel Check Frontend

前端子项目使用 `Vue 3 + TypeScript + Vite + Pinia + Element Plus + Tailwind v3`。项目总览见 [../README.md](../README.md)，接口契约见 [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)。

## 1. 安装与启动

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

默认开发地址：<http://127.0.0.1:5173>。开发期 API 通过 Vite 代理到 <http://127.0.0.1:8000>。

## 2. 构建与检查

```powershell
cd frontend
npm run lint
npm run format:check
npm run build
```

`npm run build` 会先执行 `vue-tsc` 类型检查，再输出生产包到 `frontend/dist/`。共享部署由根目录脚本 `.\scripts\start-local-deploy.ps1` 统一处理。

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

## 4. 设计与代码约定

- 页面布局优先复用 `components/shell/`。
- 业务组件只处理当前业务域，不复制全局按钮、表格和状态样式。
- API 请求集中在 `src/api/`，接口类型集中在 `src/types/`。
- Pinia store 维护业务状态，不散落 `fetch`。
- 历史 wire 字段保持原名，例如 `pathOrUrl`、`source_id`、`rule_type`。
- `corePlugins.preflight = false`，避免 Tailwind reset 与 Element Plus 冲突。

## 5. 联调入口

完整联调步骤见 [../README.md](../README.md) 的“最短联调”。规则能力、AI 智能添加规则、SVN 和接口契约见 [../docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)。
