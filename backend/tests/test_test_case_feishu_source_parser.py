"""用例生成飞书富来源 URL 解析测试。"""

from __future__ import annotations

import pytest

from backend.app.test_cases.feishu_source_parser import (
    FeishuSourceUrlError,
    parse_feishu_source_url,
)


def test_parse_docx_url_success() -> None:
    locator = parse_feishu_source_url("https://demo.feishu.cn/docx/doccnabc123")

    assert locator.doc_type == "docx"
    assert locator.token == "doccnabc123"
    assert locator.normalized_url == "https://demo.feishu.cn/docx/doccnabc123"


def test_parse_legacy_docs_url_as_docx_compatible() -> None:
    locator = parse_feishu_source_url(
        " https://demo.feishu.cn/docs/doccnlegacy123?from=copy "
    )

    assert locator.doc_type == "docx"
    assert locator.token == "doccnlegacy123"
    assert locator.original_doc_type == "docs"
    assert locator.normalized_url == "https://demo.feishu.cn/docs/doccnlegacy123"


@pytest.mark.parametrize(
    ("url", "doc_type", "token"),
    [
        ("https://demo.feishu.cn/wiki/wikcnabc123", "wiki", "wikcnabc123"),
        ("https://demo.feishu.cn/sheets/shtcnabc123?sheet=gid001", "sheets", "shtcnabc123"),
        ("https://demo.feishu.cn/base/appcnabc123", "bitable", "appcnabc123"),
        ("https://demo.feishu.cn/bitable/appcnxyz789", "bitable", "appcnxyz789"),
    ],
)
def test_parse_supported_feishu_source_urls(url: str, doc_type: str, token: str) -> None:
    locator = parse_feishu_source_url(url)

    assert locator.doc_type == doc_type
    assert locator.token == token


@pytest.mark.parametrize(
    "url",
    [
        "not-a-url",
        "http://demo.feishu.cn/docx/doccnabc123",
        "https://example.com/docx/doccnabc123",
        "https://demo.feishu.cn/docx/",
        "https://demo.feishu.cn/mindnotes/doccnabc123",
    ],
)
def test_parse_feishu_source_url_rejects_invalid_or_missing_token(url: str) -> None:
    with pytest.raises(FeishuSourceUrlError):
        parse_feishu_source_url(url)
