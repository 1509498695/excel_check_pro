# 前端样式规范

本文档描述当前 Vue 前端的全局样式约定。目标是降低全局覆盖冲突，不改变现有页面视觉。

## 1. 样式入口顺序

`frontend/src/main.ts` 统一引入样式，顺序固定为：

1. `element-plus/dist/index.css`：Element Plus 官方基础样式。
2. `frontend/src/style.css`：Tailwind v3 入口，只启用 utilities，preflight 关闭。
3. `frontend/src/styles/tokens.css`：运行时 CSS variables，是颜色、间距、圆角、阴影和控件尺寸的主来源。
4. `frontend/src/styles/shared.css`、`shared-overrides.css`：共享基础样式和历史兼容样式。
5. `frontend/src/styles/element-plus.css`：Element Plus 与通用控件覆盖。
6. 页面域样式：`workbench.css`、`personal-check.css`、`fixed-rules.css` 等。
7. `shared-final.css`：保留少量最终卡片和空态兼容收口。

新增样式优先放在组件 scoped style 或对应功能目录；只有跨页面复用样式才进入 `styles/`。

## 2. 颜色 Token

颜色优先使用 `tokens.css` 中的变量：

| Token | 用途 |
|---|---|
| `--color-primary` | 主按钮、主链接、当前态强调 |
| `--color-primary-hover` | 主色 hover / active 文本 |
| `--color-primary-soft` | 主色浅底胶囊、空态 icon 背景 |
| `--color-primary-light` | 表格 hover、浅强调背景 |
| `--color-success` / `--color-success-soft` | 成功态和成功浅底 |
| `--color-warning` / `--color-warning-soft` | 警告态和警告浅底 |
| `--color-danger` / `--color-danger-soft` | 危险态和错误浅底 |
| `--color-text-main` | 主标题、关键数据 |
| `--color-text-secondary` | 正文和表格内容 |
| `--color-text-muted` | 说明、辅助文本、表头弱化文字 |
| `--color-border` / `--color-border-light` | 卡片、表格、分割线边框 |
| `--color-bg-page` / `--color-bg-card` | 页面背景和卡片白底 |

遗留变量 `--text-main`、`--accent`、`--surface` 等继续保留，仅用于兼容旧样式。新代码不要新增新的 legacy token。

## 3. 间距与尺寸 Token

常用间距使用 `--space-*`：

| Token | 值 | 用途 |
|---|---:|---|
| `--space-xs` | `4px` | 小图标间距 |
| `--space-sm` | `8px` | 按钮图标与文字间距 |
| `--space-md` | `12px` | 表单局部间距 |
| `--space-lg` | `16px` | 卡片内小段落间距 |
| `--space-xl` | `24px` | 弹窗、卡片常用 padding |
| `--space-2xl` | `28px` | 页面内容区 padding 基准 |

控件尺寸使用 `--ui-control-height-sm`、`--ui-control-height-md`、`--ui-control-radius`。表格行高使用 `--ui-table-row-height`。

## 4. 表格样式

- Element Plus 表格统一由 `frontend/src/styles/element-plus.css` 覆盖。
- 业务表格优先使用 `workbench-table` 或共享 `DataTable`，不要在页面里重复写 `.el-table` 深度覆盖。
- 表头使用 `--color-bg-page` 与 `--color-text-muted`；行 hover 使用 `--color-primary-light`。
- 若某个表格需要特殊空态高度，优先在组件 scoped style 内限定到该组件 class。

## 5. 卡片样式

- 通用卡片优先使用 `components/shell/AppCard.vue`，对应全局 class 为 `ui-card`。
- 卡片 token：`--ui-card-border`、`--ui-card-radius`、`--ui-card-bg`、`--ui-card-shadow`。
- 页面域卡片可以增加布局、间距和局部状态，但不要重复定义全局卡片阴影和边框。

## 6. 表单样式

- Element Plus 输入框、选择器、文本域的基础视觉统一在 `element-plus.css`。
- 业务组件如果需要深度覆盖 Element Plus，必须限定到组件根 class，例如 `.source-path-management-dialog :deep(...)`。
- 不新增无根选择器的 `.el-input__wrapper` 覆盖；否则会影响全站表单。

## 7. 弹窗样式

- 通用弹窗视觉由 `element-plus.css` 的 `.el-dialog`、`.el-dialog__header`、`.el-dialog__footer` 统一控制。
- 单弹窗差异使用 dialog class 加 scoped 或 `:global(.xxx-dialog ...)`，例如礼包校验弹窗。
- 弹窗体 padding、footer 边框、textarea 最小高度应优先引用 token。

## 8. `!important` 使用边界

只在以下场景保留 `!important`：

- 覆盖 Element Plus 内联权重或组件库高权重选择器。
- 覆盖 Tailwind utility 且无法调整模板 class 顺序。
- 兼容历史全局样式，且删除会造成明显视觉回归。

新增业务样式不要默认使用 `!important`。如确实需要，必须限定在页面或组件根 class 下。
