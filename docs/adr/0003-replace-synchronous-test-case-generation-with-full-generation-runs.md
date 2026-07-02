# ADR 0003: Replace synchronous test case generation with full-generation runs

## 状态

已采纳。

## 背景

旧用例生成链路围绕 `Planning Sheet Snapshot` 和同步 `/generate` 请求设计，会在快照读取和生成 prompt 两层截断输入。它适合受控小输入，但不能证明所选策划案已被全量读取和覆盖。

## 决策

V3 不再兼容旧同步生成作为主链路，而是以短期 `Generation Run` 替换：后端读取当前选中 `Planning Sheet` 的 `Full Planning Sheet Context`，结构化切片后抽取 `Requirement Atom`，合并去重，再生成 `Test Case Blueprint`、测试用例和 `Coverage Audit`。前端导出改为按 generation run id 请求后端导出，不能再由前端回传蓝图、用例和统计作为导出事实来源。

## 后果

- 生成变成异步、多阶段、多次 AI 调用，页面必须展示进度、取消、失败 chunk 和短期恢复状态。
- 生成结果、需求原子、覆盖审计和错误摘要需要短期保存，默认与 Source Evidence TTL 对齐，到期清理详细内容，只保留最小审计摘要。
- `Planning Sheet Snapshot` 保留为受控预览概念，不再承担 V3 全量生成输入语义。
- 参考案例库只继续影响输出字段、粒度、命名和导出形态，不影响需求原子抽取或当前需求事实。
