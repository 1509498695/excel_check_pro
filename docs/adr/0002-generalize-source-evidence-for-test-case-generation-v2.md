# ADR 0002: 用例生成 V2 统一使用 Source Evidence Run 读取来源材料

## 状态

已采纳。

## 背景

用例生成 V1 的 `Planning Sheet Snapshot` 面向单个 Excel 或飞书电子表格 Sheet，只读取单元格文本，不读取图片、附件或文档块。飞书文档富读取迁移已经引入 `Source Evidence Run`、资源清单、视觉观察和 `Adopted Visual Evidence`，但当前代码和文档仍把该链路主要限制在飞书文档。

V2 需要让飞书文档、本地文件和 SVN 文件都能读取图片，并且 `.xls` 内嵌图片必须首批支持。如果继续让本地/SVN Excel 走旧 `planning-snapshot`，会出现三套读取语义、三套权限边界和不一致的视觉证据规则。

## 决策

用例生成 V2 的新来源读取统一进入 `Source Evidence Run`。`planning-snapshot` 保留为 V1 兼容路径；新飞书文档、本地文件和 SVN 文件使用同一套短期证据、资源清单、视觉选择、观察、采纳、TTL 清理和生成/export 校验规则。

V2 新增 `local_file` 和 `svn_file` 来源类型。本地文件通过用例生成专用上传接口创建 source evidence run；SVN 文件通过项目级 `Source Evidence SVN Root` 和项目级 SVN 凭据读取，不能把个人 SVN 凭据读取出的内容缓存成项目共享证据。SVN 文件缓存后复用本地文件 reader。

`.xls` 内嵌图片首批支持通过受控 LibreOffice headless 转换实现：服务端把 `.xls` 临时转换为 `.xlsx` 后复用 `.xlsx` 图片解析。转换产物只保存在当前 source evidence run 目录内，随 TTL 清理；转换失败不污染文本主体，但必须产生明确 warning，且失败图片不得进入视觉证据。

图片和附件永远不能自动成为需求事实。只有经过用户选择、视觉观察和人工采纳的 `Adopted Visual Evidence` 才能进入生成上下文和导出说明。生成/export 阶段必须校验 adopted evidence id 有效，并阻止未采纳图片 ref 被当作已确认依据。

## 后果

- 后端需要把 `SourceEvidenceRunCreateRequest.source_type` 从飞书专用扩展为 `feishu | svn_file`，并新增本地文件上传创建接口。
- 前端用例生成页的“本地文件 / SVN 文件 / 飞书文档”三入口要展示同一套 Source Evidence 状态、资源清单、视觉选择、观察和采纳流程。
- 部署需要暴露 LibreOffice/soffice 转换器可用状态；未配置时 `.xls` 文本仍可读，但 `.xls` 图片读取必须明确降级。
- 旧个人/项目校验数据源模块继续服务规则执行和变量预览，不承担 V2 用例生成证据链路。
