"""飞书电子表格 URL 解析测试。"""

from __future__ import annotations

import pytest

from backend.app.api.schemas import DataSource, VariableTag
from backend.app.integrations.feishu_client import FeishuSheetMetadata, FeishuSheetTable
from backend.app.loaders.feishu_reader import (
    FeishuSheetError,
    FeishuSheetLocator,
    load_feishu_variables_by_source,
    parse_feishu_sheet_url,
    preview_feishu_source_column,
)


def test_parse_feishu_sheet_url_without_sheet_id() -> None:
    locator = parse_feishu_sheet_url("https://demo.feishu.cn/sheets/shtcnabc123")

    assert locator == FeishuSheetLocator(
        spreadsheet_token="shtcnabc123",
        sheet_id=None,
        normalized_url="https://demo.feishu.cn/sheets/shtcnabc123",
    )


def test_parse_feishu_sheet_url_with_sheet_id() -> None:
    locator = parse_feishu_sheet_url(
        " https://demo.feishu.cn/sheets/shtcnabc123?sheet=gid987 "
    )

    assert locator.spreadsheet_token == "shtcnabc123"
    assert locator.sheet_id == "gid987"
    assert locator.normalized_url == "https://demo.feishu.cn/sheets/shtcnabc123?sheet=gid987"


def test_parse_larksuite_sheet_url_with_sheet_id() -> None:
    locator = parse_feishu_sheet_url(
        "https://tenant.larksuite.com/sheets/shtcnxyz789?sheet=gid001"
    )

    assert locator.spreadsheet_token == "shtcnxyz789"
    assert locator.sheet_id == "gid001"
    assert locator.normalized_url == "https://tenant.larksuite.com/sheets/shtcnxyz789?sheet=gid001"


def test_parse_feishu_wiki_sheet_url_as_resolvable_locator() -> None:
    locator = parse_feishu_sheet_url(
        "https://demo.feishu.cn/wiki/wikcnabc123?sheet=gid001"
    )

    assert locator.spreadsheet_token == "wikcnabc123"
    assert locator.sheet_id == "gid001"
    assert locator.url_type == "wiki"
    assert locator.normalized_url == "https://demo.feishu.cn/wiki/wikcnabc123?sheet=gid001"


def test_parse_feishu_sheet_url_normalizes_host_and_query() -> None:
    locator = parse_feishu_sheet_url(
        "https://DEMO.feishu.cn/sheets/shtcnabc123?foo=bar&sheet=gid987#section"
    )

    assert locator.spreadsheet_token == "shtcnabc123"
    assert locator.sheet_id == "gid987"
    assert locator.normalized_url == "https://demo.feishu.cn/sheets/shtcnabc123?sheet=gid987"


def test_parse_feishu_sheet_url_empty_input() -> None:
    with pytest.raises(FeishuSheetError) as exc_info:
        parse_feishu_sheet_url("  ")

    assert exc_info.value.code == "empty_url"
    assert str(exc_info.value) == "请输入飞书电子表格 URL"


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "http://demo.feishu.cn/sheets/shtcnabc123",
        "https://example.com/sheets/shtcnabc123",
        "https://demo.feishu.cn/mindnotes/shtcnabc123",
    ],
)
def test_parse_feishu_sheet_url_rejects_invalid_url(url: str) -> None:
    with pytest.raises(FeishuSheetError) as exc_info:
        parse_feishu_sheet_url(url)

    assert exc_info.value.code == "invalid_url"
    assert str(exc_info.value) == "请输入合法的飞书电子表格链接"


@pytest.mark.parametrize(
        "url",
        [
            "https://demo.feishu.cn/base/app123",
            "https://demo.feishu.cn/docx/doccn123",
            "https://demo.feishu.cn/docs/doccn123",
        ],
)
def test_parse_feishu_sheet_url_rejects_unsupported_links(url: str) -> None:
    with pytest.raises(FeishuSheetError) as exc_info:
        parse_feishu_sheet_url(url)

    assert exc_info.value.code == "unsupported_url"
    assert str(exc_info.value) == "第一版仅支持飞书电子表格链接，不支持多维表格或文档表格链接"


def test_parse_feishu_sheet_url_rejects_missing_token() -> None:
    with pytest.raises(FeishuSheetError) as exc_info:
        parse_feishu_sheet_url("https://demo.feishu.cn/sheets/")

    assert exc_info.value.code == "token_parse_failed"
    assert str(exc_info.value) == "无法从链接中解析电子表格 token"


def test_load_feishu_variables_by_source_builds_single_variable_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_feishu_loader_stubs(monkeypatch)

    result = load_feishu_variables_by_source(
        DataSource(
            id="src_feishu",
            type="feishu",
            pathOrUrl="https://demo.feishu.cn/sheets/shtcnabc123",
        ),
        [
            VariableTag(
                tag="[items-name]",
                source_id="src_feishu",
                sheet="Items",
                column="Name",
            )
        ],
        project_id=1,
    )

    frame = result["[items-name]"]
    assert list(frame.columns) == ["Name", "_row_index"]
    assert frame.to_dict("records") == [
        {"Name": "Alpha", "_row_index": 2},
        {"Name": "Beta", "_row_index": 3},
        {"Name": None, "_row_index": 4},
    ]


def test_load_feishu_variables_by_source_builds_composite_variable_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_feishu_loader_stubs(monkeypatch)

    result = load_feishu_variables_by_source(
        DataSource(
            id="src_feishu",
            type="feishu",
            pathOrUrl="https://demo.feishu.cn/sheets/shtcnabc123",
        ),
        [
            VariableTag(
                tag="[items-json]",
                source_id="src_feishu",
                sheet="Items",
                variable_kind="composite",
                columns=["ID", "Name", "Group"],
                key_column="ID",
                append_index_to_key=True,
            )
        ],
        project_id=1,
    )

    frame = result["[items-json]"]
    assert list(frame.columns) == ["__key__", "ID", "Name", "Group", "_row_index"]
    assert frame.to_dict("records") == [
        {"__key__": "1_0", "ID": 1, "Name": "Alpha", "Group": "A", "_row_index": 2},
        {"__key__": "1_1", "ID": 1, "Name": "Beta", "Group": "B", "_row_index": 3},
    ]


def test_load_feishu_variables_by_source_requires_project_id() -> None:
    with pytest.raises(ValueError) as exc_info:
        load_feishu_variables_by_source(
            DataSource(
                id="src_feishu",
                type="feishu",
                pathOrUrl="https://demo.feishu.cn/sheets/shtcnabc123",
            ),
            [
                VariableTag(
                    tag="[items-name]",
                    source_id="src_feishu",
                    sheet="Items",
                    column="Name",
                )
            ],
        )

    assert "项目上下文不可用" in str(exc_info.value)


@pytest.mark.anyio
async def test_preview_feishu_source_column_skips_empty_target_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_feishu_preview_stubs(monkeypatch)

    preview = await preview_feishu_source_column(
        DataSource(
            id="src_feishu",
            type="feishu",
            pathOrUrl="https://demo.feishu.cn/sheets/shtcnabc123",
        ),
        sheet_name="Items",
        column_name="Name",
        db=None,  # mocked Feishu client does not touch the session
        project_id=1,
    )

    assert preview["preview_rows"] == [
        {"row_index": 2, "value": "Alpha"},
        {"row_index": 6, "value": 0},
        {"row_index": 7, "value": False},
        {"row_index": 8, "value": "Beta"},
    ]
    assert preview["total_rows"] == 4
    assert preview["loaded_rows"] == 4
    assert preview["loaded_all_rows"] is True


def _install_feishu_loader_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.integrations import feishu_client

    async def _list_sheets(*_args, **_kwargs):
        return [
            FeishuSheetMetadata(
                sheet_id="gid_items",
                title="Items",
                index=0,
                row_count=4,
                column_count=3,
                hidden=False,
                resource_type="sheet",
            )
        ]

    async def _read_values(*_args, **_kwargs):
        return FeishuSheetTable(
            spreadsheet_token="shtcnabc123",
            sheet_id="gid_items",
            sheet_title="Items",
            range="gid_items!A1:C4",
            columns=["ID", "Name", "Group"],
            rows=[],
            raw_values=[
                ["ID", "Name", "Group"],
                [1, "Alpha", "A"],
                [1, "Beta", "B"],
                ["", "", "C"],
            ],
        )

    monkeypatch.setattr(feishu_client, "list_spreadsheet_sheets", _list_sheets)
    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)


def _install_feishu_preview_stubs(monkeypatch: pytest.MonkeyPatch) -> None:
    from backend.app.integrations import feishu_client

    async def _list_sheets(*_args, **_kwargs):
        return [
            FeishuSheetMetadata(
                sheet_id="gid_items",
                title="Items",
                index=0,
                row_count=9,
                column_count=3,
                hidden=False,
                resource_type="sheet",
            )
        ]

    async def _read_values(*_args, **_kwargs):
        return FeishuSheetTable(
            spreadsheet_token="shtcnabc123",
            sheet_id="gid_items",
            sheet_title="Items",
            range="gid_items!A1:C9",
            columns=["ID", "Name", "Group"],
            rows=[],
            raw_values=[
                ["ID", "Name", "Group"],
                [1, "Alpha", "A"],
                [2, "", "B"],
                [3, "   ", "C"],
                [4, None, "D"],
                [5, 0, "E"],
                [6, False, "F"],
                [7, "Beta"],
                [8],
            ],
        )

    monkeypatch.setattr(feishu_client, "list_spreadsheet_sheets", _list_sheets)
    monkeypatch.setattr(feishu_client, "read_sheet_values", _read_values)
