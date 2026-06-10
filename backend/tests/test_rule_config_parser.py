"""规则配置 Markdown 解析测试。"""

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

分页:
  - 名称: AbsolutePack
    ID字段: INT_PackageId
    名称字段: DESC
    输出字段:
      - INT_PackageId
      - 字段: DESC
        显示名: 礼包名称

引用:
  - 名称: price
    配置文件: Price.xls
    分页: Price
    关联: INT_PriceId=INT_PriceId
    输出字段:
      - 字段: INT_Point
        显示名: 价格点数
""".strip()


def test_parse_chinese_config_lookup_markdown() -> None:
    """中文固定字段会被解析为运行时 JSON。"""
    parsed = parse_config_lookup_markdown(
        VALID_MARKDOWN,
        allowed_query_roots={"game_datas"},
    )

    assert parsed["rule_family"] == "config_lookup"
    query = parsed["queries"][0]
    assert query["query_type"] == "礼包"
    assert query["query_root"] == "game_datas"
    assert query["file"] == "IAPConfig.xls"
    assert query["pages"][0]["name"] == "AbsolutePack"
    assert query["pages"][0]["id_field"] == "INT_PackageId"
    assert query["pages"][0]["output_fields"] == [
        {"field": "INT_PackageId", "display_name": None},
        {"field": "DESC", "display_name": "礼包名称"},
    ]
    assert query["references"][0]["name"] == "price"
    assert query["references"][0]["join"] == "INT_PriceId=INT_PriceId"


def test_validate_returns_summary_for_valid_content() -> None:
    """结构校验成功时返回运行时 JSON、空错误和前端摘要。"""
    result = validate_config_lookup_markdown(
        VALID_MARKDOWN,
        allowed_query_roots={"game_datas"},
    )

    assert result.ok is True
    assert result.errors == []
    assert result.parsed_config_json["queries"][0]["query_type"] == "礼包"
    assert result.summary["query_types"] == ["礼包"]
    assert result.summary["query_roots"] == ["game_datas"]
    assert result.summary["primary_files"] == ["IAPConfig.xls"]
    assert result.summary["pages"] == [
        {"query_type": "礼包", "names": ["AbsolutePack"]},
    ]
    assert result.summary["references"] == [
        {
            "query_type": "礼包",
            "name": "price",
            "file": "Price.xls",
            "page": "Price",
        },
    ]


def test_parse_multiple_pages_and_display_names() -> None:
    """多分页和输出字段显示名会被保留。"""
    content = VALID_MARKDOWN.replace(
        "  - 名称: AbsolutePack\n"
        "    ID字段: INT_PackageId\n"
        "    名称字段: DESC\n"
        "    输出字段:\n"
        "      - INT_PackageId\n"
        "      - 字段: DESC\n"
        "        显示名: 礼包名称",
        "  - 名称: AbsolutePack\n"
        "    ID字段: INT_PackageId\n"
        "    名称字段: DESC\n"
        "    输出字段:\n"
        "      - INT_PackageId\n"
        "      - 字段: DESC\n"
        "        显示名: 礼包名称\n"
        "  - 名称: Template\n"
        "    ID字段: INT_TemplateId\n"
        "    名称字段: DESC\n"
        "    输出字段:\n"
        "      - 字段: DESC\n"
        "        显示名: 模板名称",
    )

    parsed = parse_config_lookup_markdown(
        content,
        allowed_query_roots={"game_datas"},
    )

    pages = parsed["queries"][0]["pages"]
    assert [page["name"] for page in pages] == ["AbsolutePack", "Template"]
    assert pages[1]["output_fields"] == [{"field": "DESC", "display_name": "模板名称"}]


@pytest.mark.parametrize(
    "bad_content",
    [
        "query_root: game_datas\n查询类型: 礼包\n配置文件: IAPConfig.xls\n分页:\n  - 名称: A",
        "查询类型: 礼包\n数据根: game_datas\n配置文件: IAPConfig.xls\n未知字段: x\n分页:\n  - 名称: A",
    ],
)
def test_rejects_english_or_unknown_keys(bad_content: str) -> None:
    """英文旧 key 或未知中文字段不允许发布。"""
    with pytest.raises(RuleConfigParseError):
        parse_config_lookup_markdown(bad_content, allowed_query_roots={"game_datas"})


def test_rejects_duplicate_query_type() -> None:
    """同一文档内查询类型必须唯一。"""
    content = f"{VALID_MARKDOWN}\n---\n{VALID_MARKDOWN}"

    with pytest.raises(RuleConfigParseError, match="查询类型重复"):
        parse_config_lookup_markdown(content, allowed_query_roots={"game_datas"})


@pytest.mark.parametrize(
    "unsafe_path",
    ["../IAPConfig.xls", "/datas/IAPConfig.xls", "C:\\datas\\IAPConfig.xls"],
)
def test_rejects_unsafe_paths(unsafe_path: str) -> None:
    """配置文件路径不能是绝对路径或父目录逃逸。"""
    content = VALID_MARKDOWN.replace("IAPConfig.xls", unsafe_path, 1)

    with pytest.raises(RuleConfigParseError):
        parse_config_lookup_markdown(content, allowed_query_roots={"game_datas"})


@pytest.mark.parametrize(
    ("missing_line", "expected_error"),
    [
        ("查询类型: 礼包\n", "缺少必填字段：查询类型"),
        ("数据根: game_datas\n", "缺少必填字段：数据根"),
        ("配置文件: IAPConfig.xls\n", "缺少必填字段：配置文件"),
        (
            "分页:\n"
            "  - 名称: AbsolutePack\n"
            "    ID字段: INT_PackageId\n"
            "    名称字段: DESC\n"
            "    输出字段:\n"
            "      - INT_PackageId\n"
            "      - 字段: DESC\n"
            "        显示名: 礼包名称\n"
            "\n",
            "分页不能为空",
        ),
    ],
)
def test_validate_reports_required_field_errors(missing_line: str, expected_error: str) -> None:
    """缺少固定必填配置项时返回中文错误列表。"""
    result = validate_config_lookup_markdown(
        VALID_MARKDOWN.replace(missing_line, ""),
        allowed_query_roots={"game_datas"},
    )

    assert result.ok is False
    assert expected_error in result.errors


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "https://svn.example.com/IAPConfig.xls",
        "svn://svn.example.com/IAPConfig.xls",
        "C:datas/IAPConfig.xls",
        "../IAPConfig.xls",
    ],
)
def test_validate_reports_disallowed_file_paths(unsafe_path: str) -> None:
    """配置文件和引用配置文件不能使用 URL、盘符或父目录逃逸。"""
    result = validate_config_lookup_markdown(
        VALID_MARKDOWN.replace("IAPConfig.xls", unsafe_path, 1),
        allowed_query_roots={"game_datas"},
    )

    assert result.ok is False
    assert result.errors


def test_validate_reports_invalid_join_format() -> None:
    """引用关联格式必须是 A=B。"""
    result = validate_config_lookup_markdown(
        VALID_MARKDOWN.replace("INT_PriceId=INT_PriceId", "INT_PriceId"),
        allowed_query_roots={"game_datas"},
    )

    assert result.ok is False
    assert "关联格式必须是 A=B" in result.errors[0]


def test_validate_reports_missing_query_root_alias() -> None:
    """数据根必须引用项目已启用 query_roots alias。"""
    result = validate_config_lookup_markdown(
        VALID_MARKDOWN,
        allowed_query_roots={"activity_datas"},
    )

    assert result.ok is False
    assert "数据根 alias 不存在：game_datas" in result.errors
