# 用例生成 V1 Codex 分步执行提示词

> 用途：把 `docs/specs/test-case-generation.md` 和 `docs/superpowers/plans/2026-06-22-test-case-generation.md` 拆成可逐步复制给 Codex 执行的实现提示词。当前保留历史 Prompt 编号，但前八步按已执行补正顺序组织：先完成后端无参考闭环，再接参考库服务和生成/导出增强，之后补前端 01/02/04 与持久化结构收敛。

## 执行总原则

- 每个切片开始前先读：`CONTEXT.md`、`docs/specs/test-case-generation.md`、`docs/superpowers/plans/2026-06-22-test-case-generation.md`、`frontend/src/views/TestCaseGeneratorView.vue`。
- 涉及后端时同时读：`backend/app/api/router.py`、`backend/app/models.py`、`backend/app/auth/dependencies.py`、`backend/app/api/source_api.py`、`backend/app/loaders/local_reader.py`、`backend/app/ai/credentials.py`、`backend/app/ai/providers.py`。
- 涉及前端时同时读：`frontend/src/api/workbench.ts`、`frontend/src/utils/apiFetch.ts`、`frontend/src/types/workbench.ts`、`frontend/tests/unit/TestCaseGeneratorView.test.ts`。
- 不直接调用 `D:\project\QAWORK\qa_workspace` 的 CLI，不在 Web 请求里运行 `uv run qa ...`；只移植 `qa-case` 方法核心。
- V1 不保存生成历史，不落库保存蓝图、用例、策划案快照或原始 prompt。
- 参考案例库是可选增强，不得让生成强依赖主参考或任何参考案例。
- 公共请求不得接收 `knowledge_context` 或等价用户知识输入；如传入应拒绝。
- 每个切片都要补测试；能跑的测试必须跑，跑不了要记录原因。
- 每个切片完成后追加 `PROJECT_RECORD.md`，记录实际改动和验证结果。

## 推荐实施顺序

1. 后端用例生成包、API 路由骨架和共享契约。
2. 策划案快照读取：先支持本地 Excel，再接飞书表格。
3. 内置 `QA Case Method` 和无参考 AI 生成主链路。
4. Excel 导出：基于当前页面结果 stateless 导出三张 Sheet。
5. 参考案例上传、画像、分类、推荐主参考和删除（执行历史对应 Prompt 7）。
6. 参考案例增强接入生成和导出（执行历史对应 Prompt 8）。
7. 前端 01/02/04 接真实 API，完成无参考端到端闭环（执行历史对应 Prompt 5）。
8. 参考案例库数据模型和迁移一致性补正（执行历史对应 Prompt 6；用于消除 7/8 先执行导致的持久化结构漂移）。
9. 前端 03 参考案例库接真实 API。
10. 全量验收、文档同步和风险清理。

> 顺序补正说明：Prompt 5/6 的文件章节保留历史编号，避免已有 `PROJECT_RECORD.md` 记录失真；执行时应以上方“推荐实施顺序”为准。尤其是 Prompt 6 不应只看作全新建表任务，还必须检查旧 0010 已经落库但缺少后续字段/索引的开发库漂移，并通过后续幂等 migration 修复。

## Prompt 0：实现前基线检查

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

阅读当前项目代码和文档，为用例生成 V1 开始实现做基线检查，但不要改业务代码。

必须读取：
- CONTEXT.md
- docs/specs/test-case-generation.md
- docs/superpowers/plans/2026-06-22-test-case-generation.md
- frontend/src/views/TestCaseGeneratorView.vue
- backend/app/api/router.py
- backend/app/models.py
- backend/app/auth/dependencies.py
- backend/app/api/source_api.py
- backend/app/loaders/local_reader.py
- backend/app/ai/credentials.py
- backend/app/ai/providers.py

请输出：
1. 当前已有能力和可复用代码点。
2. 本次实现的文件边界。
3. 当前 dirty worktree 中哪些文件可能是既有修改，不要覆盖。
4. 第一刀建议从哪个切片开始。
5. 需要先跑的最小测试命令。
```

## Prompt 1：后端路由骨架和共享契约

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

开始实现用例生成 V1 的后端基础骨架，只做 API 路由、领域包和共享 Pydantic 契约，不实现参考案例库数据库、不实现 AI 调用。

目标：
- 新建 backend/app/test_cases/ 包。
- 新建 backend/app/api/test_cases_api.py，并挂载到 backend/app/api/router.py。
- 定义后续快照、生成、导出会共用的 schema 和标准字段常量。
- 保证所有接口先使用项目成员校验：ctx.require_strict_project_member()。
- 预留但不开放 knowledge_context：公共请求如果带 knowledge_context 或等价字段，后续必须能拒绝。

建议文件：
- backend/app/test_cases/__init__.py
- backend/app/test_cases/constants.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- backend/app/api/router.py
- backend/tests/test_test_case_api_contracts.py

接口先提供：
- POST /api/v1/test-cases/planning-snapshot
- POST /api/v1/test-cases/generate
- POST /api/v1/test-cases/export

这一刀可以先返回 501 或可预测的未实现错误，但鉴权、路由路径、请求结构和 knowledge_context 拒绝规则要有测试。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_api_contracts.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 2：策划案快照读取

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现用例生成 V1 的 Planning Sheet Snapshot。先完成本地 Excel 上传结果读取，再用可 monkeypatch 的方式接入飞书表格读取；不要保存快照历史。

目标：
- POST /api/v1/test-cases/planning-snapshot 返回当前页面可直接预览和用于生成的快照。
- 每次只读取一个 Planning Sheet。
- 默认读取整张 Sheet，但按需求文档限制行、列、非空单元格、单元格长度和总字符数。
- 超限必须返回 warnings，不允许静默截断。
- 始终提示 V1 未读取图片/附件语义。
- 本地 Excel 复用 local_reader 的路径安全和 Excel 读取能力。
- 飞书读取复用现有飞书表格解析/授权思路，测试里允许 monkeypatch 外部 client。

建议文件：
- backend/app/test_cases/planning_snapshot.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- backend/tests/test_test_case_planning_snapshot.py

必须覆盖：
- Excel 指定 Sheet 读取成功。
- 空 Sheet、超行、超列、超长单元格、总字符超限都有 warnings。
- 非法本地路径拒绝。
- 快照不创建任何生成历史表或结果记录。
- 飞书权限失败能转换成中文错误。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_planning_snapshot.py backend/tests/test_source_api_security.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 3：无参考 AI 生成主链路

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现用例生成 V1 的无参考 AI 生成主链路。重点是 qa-case 方法移植：蓝图先行、完整性矩阵、需求追踪、warnings 和代码统计。不要做参考案例库依赖。

目标：
- 新建 backend/app/test_cases/qa_case_method.py，内置 QA Case Method 常量。
- 新建 backend/app/test_cases/generation.py。
- POST /api/v1/test-cases/generate 支持 reference_ids 为空、primary_reference_id 为空时生成。
- 生成流程调用项目级 AI 两次：先 blueprint，再 cases。
- 使用 load_project_credential、decrypt_credential_key、parse_extra_headers、call_provider_json 和 sanitize_ai_error。
- 模型返回 JSON 后用 Pydantic 校验。
- 统计 total、priority_counts、module_counts 等必须由代码计算，不采信模型统计。
- 快照 warnings、蓝图 warnings、用例 warnings 合并返回。
- 返回 method_context，说明 V1 未接入项目级 QA 知识库。
- 公共请求传入 knowledge_context 时拒绝。

建议文件：
- backend/app/test_cases/qa_case_method.py
- backend/app/test_cases/generation.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- backend/tests/test_test_case_generation.py

必须覆盖：
- 未配置或禁用项目 AI 时返回中文配置错误。
- Provider 成功时调用两次。
- Provider 错误不泄露 API key。
- 无参考也能生成。
- 不自动选择最新参考。
- stats 由代码计算。
- requirement_trace 能关联到快照行或片段。
- 不创建历史记录。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_generation.py backend/tests/test_project_ai_config_api.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 4：Excel 导出

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现用例生成 V1 的 Excel 导出。导出必须完全基于当前页面提交的 blueprint、cases、warnings、stats，不依赖生成历史。

目标：
- 新建 backend/app/test_cases/exporter.py。
- POST /api/v1/test-cases/export 返回 xlsx 文件。
- 文件至少包含三个 Sheet：测试用例、用例蓝图、生成说明。
- 无主参考时使用标准字段顺序。
- 有主参考字段画像时，采用“标准字段兜底 + 尽量贴近主参考”：能映射的列按主参考顺序，缺失关键标准字段追加，未知列不强行生成。
- 不写入完整 API Key、原始 prompt、原始 provider response 或隐藏敏感元数据。

建议文件：
- backend/app/test_cases/exporter.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- backend/tests/test_test_case_exporter.py

必须覆盖：
- 三个 Sheet 存在。
- 标准字段兜底。
- 未知参考列被忽略。
- warnings 中包含图片/附件未读限制。
- response content-type 和 filename 正确。
- 导出不持久化历史。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_exporter.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 5（执行顺序 7）：前端先接 01/02/04 无参考闭环

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

把现有静态 TestCaseGeneratorView 先接入真实 API，但只接 01 数据源、02 生成输入、04 结果预览/导出。03 参考案例库仍保留静态或禁用态，不阻塞生成。

目标：
- 新建 frontend/src/types/testCases.ts。
- 新建 frontend/src/api/testCases.ts。
- 复用 frontend/src/api/workbench.ts 的 uploadSourceFile 和 fetchSourceMetadata 处理策划案 Excel 来源。
- 读取快照按钮调用 /api/v1/test-cases/planning-snapshot。
- 生成按钮只依赖 snapshot，不依赖参考案例。
- 生成结果渲染 blueprint、cases、warnings、stats。
- 导出按钮用 apiDownloadFile 调 /api/v1/test-cases/export。
- 切换策划案来源或 Sheet 时清空快照和生成结果。
- 页面不使用 localStorage 保存生成结果。

建议文件：
- frontend/src/types/testCases.ts
- frontend/src/api/testCases.ts
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/tests/unit/testCasesApi.test.ts
- frontend/tests/unit/TestCaseGeneratorView.test.ts

必须覆盖：
- 快照前生成按钮不可用。
- 无参考也可生成。
- 生成结果展示蓝图、用例和 warnings。
- 导出请求使用当前页面内存结果。
- 切换来源清空结果。

必须测试：
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

完成后追加 PROJECT_RECORD.md。
```

## Prompt 6（执行顺序 8）：参考案例库数据模型和迁移一致性补正

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现/校准 03 参考案例库的数据模型和迁移，只做持久化结构和最小服务测试，不接前端。注意：如果参考案例上传/API 或生成增强已经先执行，本刀必须检查并修复由执行顺序造成的模型、迁移和本地开发库漂移。

目标：
- 在 backend/app/models.py 添加 TestCaseReferenceCategoryRecord 和 TestCaseReferenceFileRecord。
- 新增 migrations/versions/0010_test_case_reference_library.py。
- 如果旧 0010 已经在开发库落库但缺少后续字段/索引，新增幂等后续 migration 修复，不要只修改已执行 revision。
- 分类按 project_id + trim 后 name 唯一。
- 参考文件支持 category_id nullable，用 category_id = null 表示未分类。
- 参考文件删除是软删除，但需要保留最小审计元数据；storage_path/profile_json/is_recommended_primary 后续删除时要能清空，所以字段设计要允许。

必须注意：
- 不把分类作为权限边界。
- 不新增生成历史表。
- 不新增 profile_status/profile_error 半成品状态。

建议文件：
- backend/app/models.py
- migrations/versions/0010_test_case_reference_library.py
- migrations/versions/0011_test_case_reference_category_name_key.py 如需修复旧 0010 漂移
- backend/tests/test_test_case_reference_models.py
- backend/tests/test_alembic_migrations.py 如有必要

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_reference_models.py backend/tests/test_alembic_migrations.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 7（执行顺序 5）：参考案例上传、画像和权限 API

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

实现参考案例库服务和 API：分类、上传、列表、删除、推荐主参考、确定性画像。不要调用 AI 做画像。

目标：
- 参考案例文件保存在独立项目级目录，不放入现有 user-scoped runtime_upload_dir，也不被普通上传清理误删。
- 支持 .xlsx/.xls/.md/.txt。
- 项目成员可查看、创建分类、上传。
- 项目管理员/超级管理员可重命名分类、删除分类、删除参考案例、设置推荐主参考。
- 同项目 + 同分类 + 同 original_filename 的 active 文件拒绝上传。
- 删除分类时把关联参考移到未分类，并清空推荐主参考标记。
- 推荐主参考按项目 + 分类唯一，未分类是 category_id = null 的独立范围。
- 删除参考案例时先删除物理文件；已缺失视为成功，IO/权限失败则保留 active 状态并返回错误。
- 删除成功后清空 storage_path、profile_json、is_recommended_primary。

Excel 画像规则：
- 读取所有 Sheet。
- 可用 Sheet = 能可靠识别表头 + 至少一行可识别用例行。
- 默认 Sheet 优先 测试用例、用例、TestCases，否则第一个可用 Sheet。
- 没有任何可用 Sheet 时拒绝上传并清理文件。
- 参考用例数量只读展示，不能作为生成目标。

建议文件：
- backend/app/test_cases/reference_profiles.py
- backend/app/test_cases/reference_library.py
- backend/app/test_cases/schemas.py
- backend/app/api/test_cases_api.py
- backend/tests/test_test_case_reference_profiles.py
- backend/tests/test_test_case_reference_library_api.py

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_reference_profiles.py backend/tests/test_test_case_reference_library_api.py backend/tests/test_source_api_security.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 8（执行顺序 6）：参考案例增强接入生成和导出

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

把参考案例库作为可选增强接入生成和导出。重点：参考不是需求来源，不是生成前置条件。

目标：
- generate 支持 reference_ids、primary_reference_id、primary_reference_sheet_name。
- reference_ids 为空合法。
- primary_reference_id 为空合法，不自动挑最新或第一条。
- primary_reference_id 如果存在，必须属于 reference_ids，且项目内 active。
- Excel 主参考必须校验 sheet 名在 sheet_options 中；缺省时用 default_sheet_name。
- Markdown/TXT 主参考不允许非空 sheet 名。
- prompt 中参考案例只作为字段顺序、层级、粒度、命名和历史风格参考，不作为需求来源。
- export_columns 按主参考可识别字段顺序 + 缺失标准字段生成。

建议文件：
- backend/app/test_cases/generation.py
- backend/app/test_cases/exporter.py
- backend/app/test_cases/reference_library.py
- backend/app/test_cases/schemas.py
- backend/tests/test_test_case_generation.py
- backend/tests/test_test_case_exporter.py

必须覆盖：
- 无参考仍成功。
- 只有 supplementary references、无 primary 时成功，且不隐式选主参考。
- 跨项目 reference 被拒绝。
- Excel 主参考 Sheet 选择影响 reference_case_count 和 export_columns。
- 未知参考列不进入导出。

必须测试：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_generation.py backend/tests/test_test_case_exporter.py backend/tests/test_test_case_reference_library_api.py

完成后追加 PROJECT_RECORD.md。
```

## Prompt 9：前端 03 参考案例库接真实 API

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

把 TestCaseGeneratorView 的 03 参考案例库从静态数据接到真实 API，并接入 02 主参考设置和 04 导出字段增强。

目标：
- 页面加载时读取分类和参考案例列表。
- 新建分类、上传参考案例调用真实 API。
- 分类 pill 显示真实数量。
- 切换分类清空选择；如果该分类有推荐主参考，则默认勾选并设为主参考；没有推荐主参考时不自动选文件。
- 支持多选参考案例。
- 设置主参考时自动勾选该文件。
- 取消勾选当前主参考时清空主参考，不自动改选。
- Excel 主参考显示可选 Sheet，默认选后端 default_sheet_name，用户可改。
- Markdown/TXT 主参考禁用 Sheet 选择。
- 参考用例数量来自当前主参考画像和 Sheet，只读展示；未选择主参考显示“未使用主参考”。
- 普通成员的管理操作即使页面入口可见，也必须以后端拒绝为准；如果已有角色状态可用，可做前端弱隐藏。

建议文件：
- frontend/src/types/testCases.ts
- frontend/src/api/testCases.ts
- frontend/src/views/TestCaseGeneratorView.vue
- frontend/tests/unit/testCasesApi.test.ts
- frontend/tests/unit/TestCaseGeneratorView.test.ts

必须测试：
cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

完成后追加 PROJECT_RECORD.md。
```

## Prompt 10：最终验收和文档同步

```text
[$grill-me](C:\Users\chenzhen\.agents\skills\grill-me\SKILL.md) [$grill-with-docs](C:\Users\chenzhen\.agents\skills\grill-with-docs\SKILL.md)

对用例生成 V1 做最终验收、文档同步和风险清理。不要新增新功能。

必须检查：
- V1 不保存生成历史。
- 无参考生成是第一等路径。
- 参考案例库只增强输出格式、粒度和历史风格，不作为需求来源。
- 公共请求不能注入 knowledge_context。
- 图片/附件未读限制在 warnings 或备注中可见。
- Excel 导出有 测试用例、用例蓝图、生成说明 三个 Sheet。
- 刷新页面不会恢复上次生成结果。

必须运行：
cd D:\project\excel-checkers\excel_check_pro
python -m pytest backend/tests/test_test_case_api_contracts.py backend/tests/test_test_case_planning_snapshot.py backend/tests/test_test_case_generation.py backend/tests/test_test_case_exporter.py backend/tests/test_test_case_reference_models.py backend/tests/test_test_case_reference_profiles.py backend/tests/test_test_case_reference_library_api.py backend/tests/test_project_ai_config_api.py backend/tests/test_source_api_security.py backend/tests/test_alembic_migrations.py

cd D:\project\excel-checkers\excel_check_pro\frontend
npm run test:unit -- testCasesApi TestCaseGeneratorView
npm run build

文档同步：
- 如实现中接口名、字段名、限制值有变化，同步 docs/specs/test-case-generation.md。
- 如新增稳定领域术语，只更新 CONTEXT.md 术语，不写实现细节。
- 更新 PROJECT_RECORD.md。
- 只有用户可见行为完成时再更新 CHANGELOG.md。

最终输出：
- 改动摘要。
- 测试结果。
- 未完成项。
- 下一步建议。
```
