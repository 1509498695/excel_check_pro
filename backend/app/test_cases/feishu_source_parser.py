"""飞书富来源 URL 解析。"""

from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


_TOKEN_RE = r"(?P<token>[A-Za-z0-9_-]+)"
_PATTERNS = (
    ("docx", "docx", re.compile(rf"^/docx/{_TOKEN_RE}$")),
    ("docx", "docs", re.compile(rf"^/docs/{_TOKEN_RE}$")),
    ("wiki", "wiki", re.compile(rf"^/wiki/{_TOKEN_RE}$")),
    ("sheets", "sheets", re.compile(rf"^/sheets/{_TOKEN_RE}$")),
    ("bitable", "base", re.compile(rf"^/base/{_TOKEN_RE}$")),
    ("bitable", "bitable", re.compile(rf"^/bitable/{_TOKEN_RE}$")),
)
_SUPPORTED_HOST_SUFFIXES = (
    "feishu.cn",
    "larksuite.com",
    "larkoffice.com",
    "larkoffice.cn",
)


@dataclass(frozen=True)
class FeishuSourceLocator:
    """飞书富来源定位信息。"""

    doc_type: str
    token: str
    normalized_url: str
    original_url: str
    original_doc_type: str
    sheet_id: str | None = None


class FeishuSourceUrlError(ValueError):
    """飞书富来源 URL 解析错误。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return self.message


def parse_feishu_source_url(url: str) -> FeishuSourceLocator:
    """解析飞书 docx/docs/wiki/sheets/base/bitable 来源 URL。"""
    raw_url = (url or "").strip()
    if not raw_url:
        raise FeishuSourceUrlError("empty_url", "请输入飞书来源 URL")

    parsed = urlparse(raw_url)
    if parsed.scheme.lower() != "https" or not _is_supported_host(parsed.hostname):
        raise FeishuSourceUrlError("invalid_url", "请输入合法的飞书来源链接")

    path = parsed.path if parsed.path.startswith("/") else f"/{parsed.path}"
    path = path.rstrip("/")
    for doc_type, original_doc_type, pattern in _PATTERNS:
        match = pattern.fullmatch(path)
        if not match:
            continue
        token = match.group("token").strip()
        if not token:
            break
        sheet_id = _extract_sheet_id(parsed.query) if doc_type == "sheets" else None
        return FeishuSourceLocator(
            doc_type=doc_type,
            token=token,
            normalized_url=_build_normalized_url(
                host=(parsed.hostname or "").lower(),
                original_doc_type=original_doc_type,
                token=token,
                sheet_id=sheet_id,
            ),
            original_url=raw_url,
            original_doc_type=original_doc_type,
            sheet_id=sheet_id,
        )

    raise FeishuSourceUrlError("unsupported_url", "无法从链接中解析支持的飞书来源 token")


def _is_supported_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    normalized = hostname.lower().rstrip(".")
    return any(
        normalized == suffix or normalized.endswith(f".{suffix}")
        for suffix in _SUPPORTED_HOST_SUFFIXES
    )


def _extract_sheet_id(query: str) -> str | None:
    values = parse_qs(query, keep_blank_values=True).get("sheet") or []
    if not values:
        return None
    sheet_id = values[0].strip()
    return sheet_id or None


def _build_normalized_url(
    *,
    host: str,
    original_doc_type: str,
    token: str,
    sheet_id: str | None,
) -> str:
    query = urlencode({"sheet": sheet_id}) if sheet_id else ""
    return urlunparse(("https", host, f"/{original_doc_type}/{token}", "", query, ""))
