"""规则配置 Markdown 解析测试。"""

from __future__ import annotations

import pytest

from backend.app.rule_configs.parser import RuleConfigParseError, parse_config_lookup_markdown


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
    parsed = parse_config_lookup_markdown(VALID_MARKDOWN)

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
        parse_config_lookup_markdown(bad_content)


def test_rejects_duplicate_query_type() -> None:
    """同一文档内查询类型必须唯一。"""
    content = f"{VALID_MARKDOWN}\n---\n{VALID_MARKDOWN}"

    with pytest.raises(RuleConfigParseError, match="查询类型重复"):
        parse_config_lookup_markdown(content)


@pytest.mark.parametrize(
    "unsafe_path",
    ["../IAPConfig.xls", "/datas/IAPConfig.xls", "C:\\datas\\IAPConfig.xls"],
)
def test_rejects_unsafe_paths(unsafe_path: str) -> None:
    """配置文件路径不能是绝对路径或父目录逃逸。"""
    content = VALID_MARKDOWN.replace("IAPConfig.xls", unsafe_path, 1)

    with pytest.raises(RuleConfigParseError):
        parse_config_lookup_markdown(content)
