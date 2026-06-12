"""config_lookup 新语法 Markdown 解析测试。"""

from __future__ import annotations

import pytest

from backend.app.rule_configs.parser import (
    RuleConfigParseError,
    parse_config_lookup_markdown,
    validate_config_lookup_markdown,
)


VALID_MARKDOWN = """
查询类型: 礼包
数据根: game_datas
配置文件: IAPConfig.xls

  - 分页名称: AbsolutePack
  - 输出字段
    - ID字段: INT_PackageId
    - 礼包名称:DESC
    - 国际服开启:STR_ServerCond_US
    - 绿色服开关:STR_ABSwitch
      - 0:绿色服关闭
      - 1:绿色服开启

  - 分页名称: Template
  - 输出字段
    - ID字段: INT_PackageId
    - 礼包名称:DESC
    - 价格:INT_PriceId
      - 引用分页名称:Price
      - 引用规则:Template.INT_PriceId=Price.INT_Id
      - 显示内容:Price.INT_Point/100
""".strip()


def test_parse_new_config_lookup_markdown() -> None:
    """新语法会被解析为单查询类型顶层 JSON。"""
    parsed = parse_config_lookup_markdown(
        VALID_MARKDOWN,
        allowed_query_roots={"game_datas"},
    )

    assert parsed["rule_family"] == "config_lookup"
    assert parsed["query_type"] == "礼包"
    assert parsed["query_root"] == "game_datas"
    assert parsed["file"] == "IAPConfig.xls"
    assert "queries" not in parsed
    assert [page["name"] for page in parsed["pages"]] == ["AbsolutePack", "Template"]
    assert parsed["pages"][0]["id_field"] == "INT_PackageId"
    assert parsed["pages"][0]["name_field"] == "DESC"


def test_parse_enum_value_map() -> None:
    """输出字段的枚举映射会保留在 value_map 中。"""
    parsed = parse_config_lookup_markdown(
        VALID_MARKDOWN,
        allowed_query_roots={"game_datas"},
    )

    enum_field = parsed["pages"][0]["output_fields"][3]
    assert enum_field == {
        "label": "绿色服开关",
        "field": "STR_ABSwitch",
        "value_map": {"0": "绿色服关闭", "1": "绿色服开启"},
    }


def test_parse_reference_expression() -> None:
    """引用字段会保留显式分页、关联和显示表达式。"""
    parsed = parse_config_lookup_markdown(
        VALID_MARKDOWN,
        allowed_query_roots={"game_datas"},
    )

    price_field = parsed["pages"][1]["output_fields"][2]
    assert price_field == {
        "label": "价格",
        "field": "INT_PriceId",
        "reference": {
            "page": "Price",
            "join": "Template.INT_PriceId=Price.INT_Id",
            "display_expression": "Price.INT_Point/100",
        },
    }


def test_validate_returns_summary_for_valid_content() -> None:
    """结构校验成功时返回运行时 JSON、空错误和摘要。"""
    result = validate_config_lookup_markdown(
        VALID_MARKDOWN,
        allowed_query_roots={"game_datas"},
    )

    assert result.ok is True
    assert result.errors == []
    assert result.parsed_config_json["query_type"] == "礼包"
    assert result.summary["query_types"] == ["礼包"]
    assert result.summary["query_roots"] == ["game_datas"]
    assert result.summary["primary_files"] == ["IAPConfig.xls"]
    assert result.summary["pages"] == [
        {"query_type": "礼包", "names": ["AbsolutePack", "Template"]},
    ]
    assert result.summary["references"] == [
        {
            "page": "Template",
            "label": "价格",
            "reference_page": "Price",
            "join": "Template.INT_PriceId=Price.INT_Id",
            "display_expression": "Price.INT_Point/100",
        },
    ]


@pytest.mark.parametrize(
    ("line", "expected_error"),
    [
        ("查询类型: 礼包\n", "缺少必填字段：查询类型"),
        ("数据根: game_datas\n", "缺少必填字段：数据根"),
        ("配置文件: IAPConfig.xls\n", "缺少必填字段：配置文件"),
    ],
)
def test_validate_reports_top_required_field_errors(line: str, expected_error: str) -> None:
    result = validate_config_lookup_markdown(
        VALID_MARKDOWN.replace(line, ""),
        allowed_query_roots={"game_datas"},
    )

    assert result.ok is False
    assert expected_error in result.errors


def test_validate_reports_missing_page() -> None:
    content = "\n".join(VALID_MARKDOWN.splitlines()[:3])

    result = validate_config_lookup_markdown(content, allowed_query_roots={"game_datas"})

    assert result.ok is False
    assert "至少需要配置一个分页" in result.errors


def test_validate_reports_missing_id_field() -> None:
    content = VALID_MARKDOWN.replace("    - ID字段: INT_PackageId\n", "", 1)

    result = validate_config_lookup_markdown(content, allowed_query_roots={"game_datas"})

    assert result.ok is False
    assert "分页 AbsolutePack 必须配置 ID字段" in result.errors


def test_validate_reports_missing_name_match_field() -> None:
    content = """
查询类型: 礼包
数据根: game_datas
配置文件: IAPConfig.xls

  - 分页名称: AbsolutePack
  - 输出字段
    - ID字段: INT_PackageId
""".strip()

    result = validate_config_lookup_markdown(content, allowed_query_roots={"game_datas"})

    assert result.ok is False
    assert "分页 AbsolutePack 必须配置至少一个名称匹配字段" in result.errors


def test_rejects_multi_query_separator() -> None:
    with pytest.raises(RuleConfigParseError, match="不允许使用 ---"):
        parse_config_lookup_markdown(
            f"{VALID_MARKDOWN}\n---\n{VALID_MARKDOWN}",
            allowed_query_roots={"game_datas"},
        )


@pytest.mark.parametrize("old_key", ["分页", "名称", "名称字段", "引用", "字段", "显示名"])
def test_rejects_old_syntax_fields(old_key: str) -> None:
    content = f"{VALID_MARKDOWN}\n{old_key}: x"

    result = validate_config_lookup_markdown(content, allowed_query_roots={"game_datas"})

    assert result.ok is False
    assert f"旧语法字段不再支持：{old_key}" in result.errors[0]


def test_rejects_english_key() -> None:
    content = "query_root: game_datas\n查询类型: 礼包\n配置文件: IAPConfig.xls"

    result = validate_config_lookup_markdown(content, allowed_query_roots={"game_datas"})

    assert result.ok is False
    assert "不支持英文配置项：query_root" in result.errors[0]


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "https://svn.example.com/IAPConfig.xls",
        "svn://svn.example.com/IAPConfig.xls",
        "C:datas/IAPConfig.xls",
        "../IAPConfig.xls",
        "/datas/IAPConfig.xls",
    ],
)
def test_validate_reports_disallowed_file_paths(unsafe_path: str) -> None:
    result = validate_config_lookup_markdown(
        VALID_MARKDOWN.replace("IAPConfig.xls", unsafe_path, 1),
        allowed_query_roots={"game_datas"},
    )

    assert result.ok is False
    assert "配置文件 必须是相对路径" in result.errors[0]


def test_validate_reports_missing_query_root_alias() -> None:
    result = validate_config_lookup_markdown(
        VALID_MARKDOWN,
        allowed_query_roots={"activity_datas"},
    )

    assert result.ok is False
    assert "数据根 alias 不存在：game_datas" in result.errors


@pytest.mark.parametrize(
    ("old_line", "new_line", "expected_error"),
    [
        (
            "引用规则:Template.INT_PriceId=Price.INT_Id",
            "引用规则:Template.INT_PriceId=INT_Id",
            "引用规则必须是 Page.Field=Page.Field",
        ),
        (
            "引用规则:Template.INT_PriceId=Price.INT_Id",
            "引用规则:Other.INT_PriceId=Price.INT_Id",
            "引用规则左侧分页必须等于当前分页名称",
        ),
        (
            "显示内容:Price.INT_Point/100",
            "显示内容:Other.INT_Point/100",
            "显示内容分页必须等于引用分页名称",
        ),
        (
            "显示内容:Price.INT_Point/100",
            "显示内容:Price.INT_Point + 1",
            "显示内容只支持 Page.Field 或 Page.Field/数字",
        ),
    ],
)
def test_validate_reports_invalid_reference_rules(
    old_line: str,
    new_line: str,
    expected_error: str,
) -> None:
    content = VALID_MARKDOWN.replace(old_line, new_line)

    result = validate_config_lookup_markdown(content, allowed_query_roots={"game_datas"})

    assert result.ok is False
    assert expected_error in result.errors[0]
