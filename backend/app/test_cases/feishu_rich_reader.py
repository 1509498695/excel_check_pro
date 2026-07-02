"""飞书富文档 Parsed Source reader adapter。"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.integrations.feishu_client import (
    FEISHU_API_ERROR,
    FEISHU_INVALID_URL,
    FeishuClientError,
    FeishuSheetLocator,
    feishu_json_request,
    get_spreadsheet_metadata,
    list_spreadsheet_sheets,
    read_sheet_values,
    resolve_feishu_wiki_node,
)
from backend.app.test_cases.feishu_source_parser import (
    FeishuSourceLocator,
    parse_feishu_source_url,
)
from backend.app.test_cases.schemas import (
    GenerationWarning,
    ParsedFeishuSource,
    ParsedSourceCell,
    ParsedSourceResource,
    ParsedSourceUnit,
    UnsupportedResourceCandidate,
)


MAX_DOCX_BLOCK_PAGES = 200
DOCX_BLOCK_PAGE_SIZE = 500


async def read_feishu_parsed_source(
    db: AsyncSession,
    project_id: int,
    url: str,
) -> ParsedFeishuSource:
    """读取飞书 docx/wiki/sheets/bitable 为统一 Parsed Source。"""
    locator = parse_feishu_source_url(url)
    if locator.doc_type == "wiki":
        node = await resolve_feishu_wiki_node(db, project_id, locator.token)
        locator = FeishuSourceLocator(
            doc_type=node.doc_type,
            token=node.obj_token,
            normalized_url=locator.normalized_url,
            original_url=locator.original_url,
            original_doc_type=node.doc_type,
            sheet_id=locator.sheet_id,
        )

    if locator.doc_type == "docx":
        return await _read_docx(db, project_id, locator)
    if locator.doc_type == "sheets":
        return await _read_sheets(db, project_id, locator)
    if locator.doc_type == "bitable":
        return await _read_bitable(db, project_id, locator)
    raise FeishuClientError(
        FEISHU_INVALID_URL,
        f"暂不支持该飞书来源类型：{locator.doc_type}",
    )


async def _read_docx(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSourceLocator,
) -> ParsedFeishuSource:
    token = quote(locator.token, safe="")
    raw_content = await feishu_json_request(
        db,
        project_id,
        "GET",
        f"/docx/v1/documents/{token}/raw_content",
    )
    _validate_docx_raw_content_payload(raw_content)

    block_pages: list[dict[str, Any]] = []
    page_token = ""
    for _ in range(MAX_DOCX_BLOCK_PAGES):
        params: dict[str, Any] = {
            "page_size": DOCX_BLOCK_PAGE_SIZE,
            "document_revision_id": -1,
        }
        if page_token:
            params["page_token"] = page_token
        page = await feishu_json_request(
            db,
            project_id,
            "GET",
            f"/docx/v1/documents/{token}/blocks",
            params=params,
        )
        block_pages.append(page)
        data = page.get("data") if isinstance(page, dict) else {}
        if not isinstance(data, dict) or not data.get("has_more"):
            break
        next_page_token = data.get("page_token") or data.get("next_page_token")
        if not next_page_token:
            raise FeishuClientError(
                FEISHU_API_ERROR,
                "Feishu docx blocks has_more response missing page_token",
            )
        page_token = str(next_page_token)
    else:
        raise FeishuClientError(
            FEISHU_API_ERROR,
            "Feishu docx blocks page count exceeded safety limit",
        )

    blocks = _extract_blocks(block_pages)
    renderer = _DocxBlockRenderer(blocks)
    body = renderer.render()
    title = _docx_title(raw_content) or locator.token
    markdown = _render_docx_markdown(title=title, url=locator.original_url, body=body)
    candidate_payloads = [
        candidate.model_dump(mode="json")
        for candidate in renderer.resource_candidates
    ]
    raw_manifest = {
        "doc_type": "docx",
        "token": locator.token,
        "docx_block_count": len(blocks),
        "docx_supported_resource_count": len(renderer.resources),
        "docx_resource_candidates": candidate_payloads,
        "raw_content": raw_content,
        "block_pages": block_pages,
    }
    return ParsedFeishuSource(
        source_type="feishu",
        title=title,
        doc_type="docx",
        token=locator.token,
        url=locator.original_url,
        markdown=markdown,
        source_units=[
            ParsedSourceUnit(
                unit_id=f"docx_{locator.token}",
                kind="docx",
                title=title,
                metadata={
                    "block_count": len(blocks),
                    "resource_count": len(renderer.resources),
                },
            )
        ],
        resources=renderer.resources,
        unsupported_resource_candidates=[
            candidate
            for candidate in renderer.resource_candidates
            if not candidate.supported
        ],
        raw_manifest=raw_manifest,
        warnings=[
            GenerationWarning(source="feishu", message=message)
            for message in renderer.warnings
        ],
    )


async def _read_sheets(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSourceLocator,
) -> ParsedFeishuSource:
    sheet_locator = FeishuSheetLocator(
        spreadsheet_token=locator.token,
        sheet_id=locator.sheet_id,
        normalized_url=locator.normalized_url,
        url_type="sheet",
    )
    metadata = await get_spreadsheet_metadata(db, project_id, sheet_locator)
    sheets = await list_spreadsheet_sheets(db, project_id, sheet_locator)
    visible_sheets = [sheet for sheet in sheets if not sheet.hidden]
    hidden_sheets = [sheet for sheet in sheets if sheet.hidden]
    warnings = [
        GenerationWarning(
            source="feishu",
            message=f"隐藏 Sheet '{sheet.title}' 已排除。",
        )
        for sheet in hidden_sheets
    ]

    units: list[ParsedSourceUnit] = []
    resources: list[ParsedSourceResource] = []
    raw_sheets: list[dict[str, Any]] = []
    for index, sheet in enumerate(sorted(visible_sheets, key=lambda item: item.index)):
        table = await read_sheet_values(
            db,
            project_id,
            sheet_locator,
            sheet_id=sheet.sheet_id,
            value_render_option="FormattedValue",
        )
        cells = _sheet_values_to_sparse_cells(table.raw_values)
        sheet_resources = _resources_from_values(
            sheet_id=sheet.sheet_id,
            sheet_title=sheet.title,
            values=table.raw_values,
            start_index=len(resources) + 1,
        )
        sheet_resources.extend(
            await _read_float_images(
                db,
                project_id,
                spreadsheet_token=locator.token,
                sheet_id=sheet.sheet_id,
                sheet_title=sheet.title,
                start_index=len(resources) + len(sheet_resources) + 1,
            )
        )
        resources.extend(sheet_resources)
        unit = ParsedSourceUnit(
            unit_id=f"sheet_{sheet.sheet_id}",
            kind="sheet",
            title=sheet.title,
            path=f"raw/sheet_{_safe_id(sheet.sheet_id)}.json",
            cells=cells,
            rows=_rows_from_cells(cells),
            metadata={
                "sheet_id": sheet.sheet_id,
                "index": index,
                "row_count": len(table.raw_values),
                "col_count": max((len(row) for row in table.raw_values), default=0),
                "non_empty_cell_count": len(cells),
                "resource_count": len(sheet_resources),
            },
        )
        units.append(unit)
        raw_sheets.append(
            {
                "sheet_id": sheet.sheet_id,
                "title": sheet.title,
                "range": table.range,
                "cells": [cell.model_dump(mode="json") for cell in cells],
                "resources": [resource.ref for resource in sheet_resources],
            }
        )

    raw_manifest = {
        "doc_type": "sheets",
        "token": locator.token,
        "spreadsheet": metadata.__dict__,
        "sheet_manifest": [_unit_manifest(unit) for unit in units],
        "hidden_sheets": [
            {"sheet_id": sheet.sheet_id, "title": sheet.title}
            for sheet in hidden_sheets
        ],
        "sheets": raw_sheets,
    }
    return ParsedFeishuSource(
        source_type="feishu",
        title=metadata.title or locator.token,
        doc_type="sheets",
        token=locator.token,
        url=locator.original_url,
        markdown=_render_sheets_markdown(
            title=metadata.title or locator.token,
            units=units,
            resources=resources,
        ),
        source_units=units,
        resources=resources,
        raw_manifest=raw_manifest,
        warnings=warnings,
    )


async def _read_bitable(
    db: AsyncSession,
    project_id: int,
    locator: FeishuSourceLocator,
) -> ParsedFeishuSource:
    token = quote(locator.token, safe="")
    tables_payload = await feishu_json_request(
        db,
        project_id,
        "GET",
        f"/bitable/v1/apps/{token}/tables",
    )
    tables = _expect_list(_dig(tables_payload, "data", "items", default=[]), "bitable tables")

    units: list[ParsedSourceUnit] = []
    resources: list[ParsedSourceResource] = []
    raw_tables: list[dict[str, Any]] = []
    for table in tables:
        table_data = _expect_dict(table, "bitable table")
        table_id = str(table_data.get("table_id") or table_data.get("id") or "").strip()
        if not table_id:
            continue
        table_name = str(table_data.get("name") or table_id)
        table_token = quote(table_id, safe="")
        views_payload = await feishu_json_request(
            db,
            project_id,
            "GET",
            f"/bitable/v1/apps/{token}/tables/{table_token}/views",
        )
        views = _expect_list(_dig(views_payload, "data", "items", default=[]), "bitable views")
        records_payload = await feishu_json_request(
            db,
            project_id,
            "POST",
            f"/bitable/v1/apps/{token}/tables/{table_token}/records/search",
            json_payload={},
        )
        records = _expect_list(
            _dig(records_payload, "data", "items", default=[]),
            "bitable records",
        )
        rows: list[dict[str, Any]] = []
        for record in records:
            record_data = _expect_dict(record, "bitable record")
            record_id = str(record_data.get("record_id") or record_data.get("id") or "")
            fields = _simplify_bitable_fields(record_data.get("fields", {}))
            rows.append({"record_id": record_id, "fields": fields})
            resources.extend(
                _resources_from_bitable_fields(
                    table_name=table_name,
                    table_id=table_id,
                    record_id=record_id,
                    fields=fields,
                    start_index=len(resources) + 1,
                )
            )
        unit = ParsedSourceUnit(
            unit_id=f"bitable_{table_id}",
            kind="bitable",
            title=table_name,
            rows=rows,
            path=f"raw/bitable_{_safe_id(table_id)}.json",
            metadata={
                "table_id": table_id,
                "views": views,
                "record_count": len(rows),
            },
        )
        units.append(unit)
        raw_tables.append(
            {
                "table_id": table_id,
                "name": table_name,
                "views": views,
                "records": rows,
            }
        )

    title = _title_from_first(raw_tables, locator.token)
    return ParsedFeishuSource(
        source_type="feishu",
        title=title,
        doc_type="bitable",
        token=locator.token,
        url=locator.original_url,
        markdown=_render_bitable_markdown(title=title, units=units),
        source_units=units,
        resources=resources,
        raw_manifest={"doc_type": "bitable", "token": locator.token, "tables": raw_tables},
    )


class _DocxBlockRenderer:
    def __init__(self, blocks: list[dict[str, Any]]) -> None:
        self.blocks = blocks
        self.block_by_id = {
            block_id: block
            for block in blocks
            if (block_id := _block_id(block))
        }
        self.children_by_parent = _children_by_parent(blocks, self.block_by_id)
        self.inline_target_ids = _inline_target_ids(blocks)
        self.resources: list[ParsedSourceResource] = []
        self.resource_candidates: list[UnsupportedResourceCandidate] = []
        self.warnings: list[str] = []
        self._image_index = 0
        self._attachment_index = 0

    def render(self) -> str:
        roots = _root_ids(
            self.blocks,
            self.block_by_id,
            self.children_by_parent,
            self.inline_target_ids,
        )
        lines: list[str] = []
        visited: set[str] = set()
        for block_id in roots:
            lines.extend(self._render_block(block_id, cell_block_id=None, visited=visited))
        return "\n".join(line for line in lines if line.strip()).strip()

    def _render_block(
        self,
        block_id: str,
        *,
        cell_block_id: str | None,
        visited: set[str],
    ) -> list[str]:
        if block_id in visited:
            self.warnings.append(f"cycle detected at block {block_id}")
            return []
        if block_id in self.inline_target_ids:
            return []
        block = self.block_by_id.get(block_id)
        if not block:
            self.warnings.append(f"missing block {block_id}")
            return []

        visited.add(block_id)
        current_cell_id = block_id if _is_table_cell(block) else cell_block_id
        lines: list[str] = []
        own = self._render_block_own_content(
            block,
            block_id=block_id,
            cell_block_id=current_cell_id,
        )
        if own:
            lines.append(own)
        for child_id in self.children_by_parent.get(block_id, []):
            lines.extend(
                self._render_block(
                    child_id,
                    cell_block_id=current_cell_id,
                    visited=visited,
                )
            )
        visited.remove(block_id)
        return lines

    def _render_block_own_content(
        self,
        block: dict[str, Any],
        *,
        block_id: str,
        cell_block_id: str | None,
    ) -> str:
        image_payload = _dict_value(block.get("image"))
        if image_payload is not None:
            token, source = _first_token(image_payload, ("token", "file_token"))
            if token:
                return _marker(
                    self._add_resource(
                        kind="image",
                        token=token,
                        block_id=block_id,
                        position=f"docx:block:{block_id}",
                        source=f"image.{source}",
                        payload=image_payload,
                        cell_block_id=cell_block_id,
                    )
                )
            self._add_unsupported(
                block_id=block_id,
                position=f"docx:block:{block_id}",
                source="image",
                payload=image_payload,
                cell_block_id=cell_block_id,
            )
            return ""

        file_payload = _dict_value(block.get("file"))
        if file_payload is not None:
            token, source = _first_token(file_payload, ("file_token", "token"))
            if token:
                return _marker(
                    self._add_resource(
                        kind="attachment",
                        token=token,
                        block_id=block_id,
                        position=f"docx:block:{block_id}",
                        source=f"file.{source}",
                        payload=file_payload,
                        cell_block_id=cell_block_id,
                    )
                )
            self._add_unsupported(
                block_id=block_id,
                position=f"docx:block:{block_id}",
                source="file",
                payload=file_payload,
                cell_block_id=cell_block_id,
            )
            return ""

        elements = _block_elements(block)
        if not elements:
            self._record_unsupported_shapes(
                block,
                block_id=block_id,
                cell_block_id=cell_block_id,
                exclude_keys=_KNOWN_BLOCK_KEYS,
            )
            return ""

        segments: list[str] = []
        for index, element in enumerate(elements, start=1):
            text = _element_text(element)
            if text:
                segments.append(text)

            file_element = _dict_value(element.get("file"))
            if file_element is not None:
                token, source = _first_token(file_element, ("file_token", "token"))
                position = f"docx:block:{block_id}:element:{index}"
                if token:
                    segments.append(
                        _marker(
                            self._add_resource(
                                kind="attachment",
                                token=token,
                                block_id=block_id,
                                position=position,
                                source=f"elements.file.{source}",
                                payload=file_element,
                                cell_block_id=cell_block_id,
                                extra_metadata={"element_index": index},
                            )
                        )
                    )
                else:
                    self._add_unsupported(
                        block_id=block_id,
                        position=position,
                        source="elements.file",
                        payload=file_element,
                        cell_block_id=cell_block_id,
                    )

            inline_block = _dict_value(element.get("inline_block"))
            if inline_block is not None:
                target_id = str(
                    inline_block.get("block_id") or inline_block.get("blockId") or ""
                ).strip()
                marker = self._render_inline_target(
                    owner_block_id=block_id,
                    target_block_id=target_id,
                    cell_block_id=cell_block_id,
                    element_index=index,
                )
                if marker:
                    segments.append(marker)
            self._record_unsupported_shapes(
                element,
                block_id=block_id,
                cell_block_id=cell_block_id,
                position=f"docx:block:{block_id}:element:{index}",
                source_prefix="elements",
                exclude_keys={
                    "text_run",
                    "textRun",
                    "plain_text",
                    "text",
                    "content",
                    "file",
                    "inline_block",
                },
            )
        self._record_unsupported_shapes(
            block,
            block_id=block_id,
            cell_block_id=cell_block_id,
            exclude_keys=_KNOWN_BLOCK_KEYS,
        )
        return " ".join(segment.strip() for segment in segments if segment.strip())

    def _render_inline_target(
        self,
        *,
        owner_block_id: str,
        target_block_id: str,
        cell_block_id: str | None,
        element_index: int,
    ) -> str:
        position = f"docx:block:{owner_block_id}:element:{element_index}"
        target = self.block_by_id.get(target_block_id)
        if target is None:
            self._add_unsupported(
                block_id=owner_block_id,
                position=position,
                source="elements.inline_block.block_id",
                payload={"block_id": target_block_id},
                cell_block_id=cell_block_id,
            )
            return ""

        image_payload = _dict_value(target.get("image"))
        if image_payload is not None:
            token, source = _first_token(image_payload, ("token", "file_token"))
            if token:
                return _marker(
                    self._add_resource(
                        kind="image",
                        token=token,
                        block_id=owner_block_id,
                        position=position,
                        source="elements.inline_block.block_id",
                        payload=image_payload,
                        cell_block_id=cell_block_id,
                        pointer_block_id=target_block_id,
                        extra_metadata={
                            "target_token_key": source,
                            "element_index": element_index,
                        },
                    )
                )

        file_payload = _dict_value(target.get("file"))
        if file_payload is not None:
            token, source = _first_token(file_payload, ("file_token", "token"))
            if token:
                return _marker(
                    self._add_resource(
                        kind="attachment",
                        token=token,
                        block_id=owner_block_id,
                        position=position,
                        source="elements.inline_block.block_id",
                        payload=file_payload,
                        cell_block_id=cell_block_id,
                        pointer_block_id=target_block_id,
                        extra_metadata={
                            "target_token_key": source,
                            "element_index": element_index,
                        },
                    )
                )

        self._add_unsupported(
            block_id=owner_block_id,
            position=position,
            source="elements.inline_block.block_id",
            payload=target,
            cell_block_id=cell_block_id,
            pointer_block_id=target_block_id,
        )
        return ""

    def _add_resource(
        self,
        *,
        kind: str,
        token: str,
        block_id: str,
        position: str,
        source: str,
        payload: dict[str, Any],
        cell_block_id: str | None,
        pointer_block_id: str | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> ParsedSourceResource:
        if kind == "image":
            self._image_index += 1
            ref = f"docx_img_{self._image_index:03d}"
        else:
            self._attachment_index += 1
            ref = f"docx_att_{self._attachment_index:03d}"
        metadata = self._candidate_metadata(
            block_id=block_id,
            position=position,
            source=source,
            payload=payload,
            cell_block_id=cell_block_id,
            pointer_block_id=pointer_block_id,
        )
        if extra_metadata:
            metadata.update(extra_metadata)
        self.resource_candidates.append(
            UnsupportedResourceCandidate(
                kind=kind,
                token=token,
                block_id=block_id,
                position=position,
                source=source,
                status="supported",
                supported=True,
                pointer_block_id=pointer_block_id,
                cell_block_id=cell_block_id,
                metadata={**metadata, "ref": ref},
            )
        )
        resource = ParsedSourceResource(
            ref=ref,
            type=kind,
            source_id=token,
            position=position,
            filename=_filename(payload),
            file_token=token,
            mime_type=_mime_type(payload),
            metadata=metadata,
        )
        self.resources.append(resource)
        return resource

    def _add_unsupported(
        self,
        *,
        block_id: str,
        position: str,
        source: str,
        payload: dict[str, Any],
        cell_block_id: str | None,
        pointer_block_id: str | None = None,
    ) -> None:
        token, _source = _first_token(
            payload,
            ("token", "file_token", "obj_token", "image_token", "media_id"),
        )
        self.resource_candidates.append(
            UnsupportedResourceCandidate(
                kind="unsupported",
                token=token,
                block_id=block_id,
                position=position,
                source=source,
                status="unsupported",
                supported=False,
                pointer_block_id=pointer_block_id,
                cell_block_id=cell_block_id,
                metadata=self._candidate_metadata(
                    block_id=block_id,
                    position=position,
                    source=source,
                    payload=payload,
                    cell_block_id=cell_block_id,
                    pointer_block_id=pointer_block_id,
                ),
            )
        )

    def _record_unsupported_shapes(
        self,
        payload: dict[str, Any],
        *,
        block_id: str,
        cell_block_id: str | None,
        position: str | None = None,
        source_prefix: str = "",
        exclude_keys: set[str] | None = None,
    ) -> None:
        for key, value in payload.items():
            if exclude_keys and key in exclude_keys:
                continue
            if key in {
                "block_id",
                "blockId",
                "parent_id",
                "parentId",
                "children",
                "child_ids",
                "childIds",
            }:
                continue
            resource_payload = _resource_like_payload(key, value)
            if resource_payload is None:
                continue
            source = f"{source_prefix}.{key}" if source_prefix else key
            self._add_unsupported(
                block_id=block_id,
                position=position or f"docx:block:{block_id}",
                source=source,
                payload=resource_payload,
                cell_block_id=cell_block_id,
            )

    def _candidate_metadata(
        self,
        *,
        block_id: str,
        position: str,
        source: str,
        payload: dict[str, Any],
        cell_block_id: str | None,
        pointer_block_id: str | None,
    ) -> dict[str, Any]:
        block = self.block_by_id.get(block_id, {})
        metadata: dict[str, Any] = {
            "doc_type": "docx",
            "block_id": block_id,
            "docx_block_id": block_id,
            "parent_block_id": _parent_id(block),
            "block_type": _block_type(block),
            "sequence": len(self.resource_candidates) + 1,
            "position_kind": "table_cell" if cell_block_id else "block",
            "source": source,
            "source_field": source,
            "source_payload": payload,
        }
        if pointer_block_id:
            metadata["pointer_block_id"] = pointer_block_id
        if cell_block_id:
            metadata["cell_block_id"] = cell_block_id
        return metadata


def _validate_docx_raw_content_payload(payload: Any) -> None:
    if not isinstance(payload, dict):
        raise FeishuClientError(FEISHU_API_ERROR, "Feishu docx response must be an object")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise FeishuClientError(FEISHU_API_ERROR, "Feishu docx response missing data")
    content = data.get("content") if "content" in data else data.get("raw_content")
    if content is None and "markdown" in data:
        content = data["markdown"]
    if content is None:
        raise FeishuClientError(FEISHU_API_ERROR, "Feishu docx response missing content")
    if not isinstance(content, (str, int, float, bool)):
        raise FeishuClientError(FEISHU_API_ERROR, "Feishu docx content must be string-ish")


def _docx_title(payload: dict[str, Any]) -> str:
    data = payload.get("data") if isinstance(payload, dict) else {}
    if isinstance(data, dict):
        return str(data.get("title") or "").strip()
    return ""


def _extract_blocks(block_pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for page in block_pages:
        data = page.get("data") if isinstance(page, dict) else {}
        if not isinstance(data, dict):
            continue
        items = data.get("items") or data.get("blocks") or []
        if isinstance(items, list):
            blocks.extend(item for item in items if isinstance(item, dict))
    return blocks


def _children_by_parent(
    blocks: list[dict[str, Any]],
    block_by_id: dict[str, dict[str, Any]],
) -> dict[str, list[str]]:
    children: dict[str, list[str]] = {block_id: [] for block_id in block_by_id}
    for block in blocks:
        block_id = _block_id(block)
        if not block_id:
            continue
        for child_id in _child_ids(block):
            if child_id in block_by_id and child_id not in children[block_id]:
                children[block_id].append(child_id)
    for block in blocks:
        block_id = _block_id(block)
        parent_id = _parent_id(block)
        if block_id and parent_id in children and block_id not in children[parent_id]:
            children[parent_id].append(block_id)
    return children


def _root_ids(
    blocks: list[dict[str, Any]],
    block_by_id: dict[str, dict[str, Any]],
    children_by_parent: dict[str, list[str]],
    inline_target_ids: set[str],
) -> list[str]:
    child_ids = {
        child_id
        for child_list in children_by_parent.values()
        for child_id in child_list
    }
    roots: list[str] = []
    for block in blocks:
        block_id = _block_id(block)
        parent_id = _parent_id(block)
        if not block_id or block_id in inline_target_ids:
            continue
        has_parent = bool(parent_id and parent_id in block_by_id)
        if not has_parent and block_id not in child_ids:
            roots.append(block_id)
        elif not has_parent and block_id in child_ids:
            continue
        elif not has_parent:
            roots.append(block_id)
    if roots:
        return roots
    return [
        block_id
        for block in blocks
        if (block_id := _block_id(block)) and block_id not in inline_target_ids
    ]


def _inline_target_ids(blocks: list[dict[str, Any]]) -> set[str]:
    target_ids: set[str] = set()
    for block in blocks:
        for element in _block_elements(block):
            inline_block = _dict_value(element.get("inline_block"))
            if inline_block is None:
                continue
            block_id = str(
                inline_block.get("block_id") or inline_block.get("blockId") or ""
            ).strip()
            if block_id:
                target_ids.add(block_id)
    return target_ids


def _block_elements(block: dict[str, Any]) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    for key in (
        "text",
        "page",
        "bullet",
        "ordered",
        "heading",
        "heading1",
        "heading2",
        "heading3",
        "heading4",
        "heading5",
        "heading6",
        "heading7",
        "heading8",
        "heading9",
        "todo",
        "quote",
        "callout",
        "code",
    ):
        value = block.get(key)
        if isinstance(value, dict) and isinstance(value.get("elements"), list):
            elements.extend(item for item in value["elements"] if isinstance(item, dict))
    if not elements:
        for value in block.values():
            if isinstance(value, dict) and isinstance(value.get("elements"), list):
                elements.extend(item for item in value["elements"] if isinstance(item, dict))
    return elements


def _element_text(element: dict[str, Any]) -> str:
    for key in ("text_run", "textRun"):
        text_run = element.get(key)
        if isinstance(text_run, dict):
            content = text_run.get("content") or text_run.get("text")
            if content is not None:
                return str(content).strip()
    for key in ("plain_text", "text", "content"):
        value = element.get(key)
        if isinstance(value, str):
            return value.strip()
    return ""


def _marker(resource: ParsedSourceResource) -> str:
    tag = "image" if resource.type == "image" else "attachment"
    return f'<{tag} ref="{_xml_attr(resource.ref)}" position="{_xml_attr(resource.position)}" />'


def _render_docx_markdown(*, title: str, url: str, body: str) -> str:
    parts = [
        f"# Source: {title or 'Untitled Feishu Source'}",
        "",
        f"URL: {url}",
        "",
        "Type: docx",
        "",
    ]
    if body.strip():
        parts.append(body.strip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _block_id(block: dict[str, Any]) -> str:
    return str(block.get("block_id") or block.get("blockId") or "").strip()


def _parent_id(block: dict[str, Any]) -> str:
    return str(block.get("parent_id") or block.get("parentId") or "").strip()


def _child_ids(block: dict[str, Any]) -> list[str]:
    children = block.get("children") or block.get("child_ids") or block.get("childIds") or []
    if not isinstance(children, list):
        return []
    return [str(child_id).strip() for child_id in children if str(child_id).strip()]


def _is_table_cell(block: dict[str, Any]) -> bool:
    block_type = str(block.get("block_type") or block.get("blockType") or "").lower()
    return "table_cell" in block or block_type in {"32", "table_cell", "tablecell"}


def _block_type(block: dict[str, Any]) -> str:
    raw_type = block.get("block_type") or block.get("blockType")
    if raw_type not in (None, ""):
        return str(raw_type)
    for key, value in block.items():
        if key in {"block_id", "blockId", "parent_id", "parentId", "children"}:
            continue
        if isinstance(value, dict):
            return key
    return ""


def _dict_value(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _first_token(payload: dict[str, Any], keys: tuple[str, ...]) -> tuple[str, str]:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value), key
    return "", ""


def _mime_type(payload: dict[str, Any]) -> str:
    value = payload.get("mime_type") or payload.get("mimeType")
    return str(value) if value else ""


def _filename(payload: dict[str, Any]) -> str:
    for key in ("name", "file_name", "fileName", "title"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


_KNOWN_BLOCK_KEYS = {
    "block_id",
    "blockId",
    "parent_id",
    "parentId",
    "children",
    "child_ids",
    "childIds",
    "image",
    "file",
    "text",
    "page",
    "bullet",
    "ordered",
    "heading",
    "heading1",
    "heading2",
    "heading3",
    "heading4",
    "heading5",
    "heading6",
    "heading7",
    "heading8",
    "heading9",
    "todo",
    "quote",
    "callout",
    "code",
    "table",
    "table_cell",
}
_RESOURCE_LIKE_KEYS = {
    "whiteboard",
    "board",
    "mindnote",
    "mind_map",
    "mindMap",
    "sheet",
    "bitable",
    "doc",
    "docx",
    "media",
    "embed",
    "embedded",
    "embedded_file",
    "embeddedFile",
    "reference",
    "block_reference",
    "blockReference",
    "synced",
    "synced_block",
    "syncedBlock",
    "wiki",
}


def _resource_like_payload(key: str, value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        if key in _RESOURCE_LIKE_KEYS or _contains_token_like(value):
            return value
        return None
    if isinstance(value, list):
        items = [
            item
            for item in value
            if isinstance(item, dict)
            and (key in _RESOURCE_LIKE_KEYS or _contains_token_like(item))
        ]
        if items:
            return {"items": items}
    return None


def _contains_token_like(value: Any) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            if "token" in key_text.lower() or key_text in {
                "fileId",
                "file_id",
                "mediaId",
                "media_id",
            }:
                return True
            if isinstance(nested, (dict, list)) and _contains_token_like(nested):
                return True
    elif isinstance(value, list):
        return any(_contains_token_like(item) for item in value)
    return False


def _sheet_values_to_sparse_cells(values: list[list[Any]]) -> list[ParsedSourceCell]:
    cells: list[ParsedSourceCell] = []
    for row_index, row in enumerate(values, start=1):
        if not isinstance(row, (list, tuple)):
            continue
        for col_index, value in enumerate(row, start=1):
            text = _cell_text(value)
            if not text.strip():
                continue
            cells.append(
                ParsedSourceCell(
                    coord=_a1_coord(row_index, col_index),
                    row=row_index,
                    col=col_index,
                    text=text,
                    raw=value,
                )
            )
    return cells


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        file_value = _normalized_file_value(value)
        if file_value is not None:
            return str(file_value.get("name") or file_value["file_token"])
        for key in ("text", "plain_text", "content", "name", "title"):
            if value.get(key) not in (None, ""):
                return str(value[key])
    return json.dumps(value, ensure_ascii=False)


def _rows_from_cells(cells: list[ParsedSourceCell]) -> list[dict[str, Any]]:
    rows: dict[int, list[dict[str, Any]]] = {}
    for cell in cells:
        rows.setdefault(cell.row, []).append(
            {"coord": cell.coord, "row": cell.row, "col": cell.col, "text": cell.text}
        )
    return [
        {"row": row, "cells": cells_for_row}
        for row, cells_for_row in sorted(rows.items())
    ]


async def _read_float_images(
    db: AsyncSession,
    project_id: int,
    *,
    spreadsheet_token: str,
    sheet_id: str,
    sheet_title: str,
    start_index: int,
) -> list[ParsedSourceResource]:
    try:
        payload = await feishu_json_request(
            db,
            project_id,
            "GET",
            f"/sheets/v3/spreadsheets/{quote(spreadsheet_token, safe='')}/sheets/{quote(sheet_id, safe='')}/float_images/query",
        )
    except FeishuClientError:
        return []
    items = _dig(payload, "data", "items", default=[]) or []
    if not isinstance(items, list):
        return []
    resources: list[ParsedSourceResource] = []
    index = start_index
    for item in items:
        if not isinstance(item, dict):
            continue
        file_token = item.get("float_image_token") or item.get("floatImageToken")
        if not file_token:
            continue
        anchor, anchor_precision = _anchor_from_resource_payload(item)
        resources.append(
            _resource_from_file_value(
                ref=_sheet_resource_ref(
                    sheet_title=sheet_title,
                    anchor=anchor or "floating",
                    index=index,
                ),
                source_id=str(file_token),
                position=f"{sheet_title}!{anchor}" if anchor else f"{sheet_title}!floating",
                file_value={
                    "file_token": str(file_token),
                    "token_key": "float_image_token",
                    "type": "floating-image",
                    "mime_type": item.get("mime_type") or item.get("mimeType"),
                    "name": item.get("name") or item.get("file_name") or item.get("fileName"),
                    "source_payload": item,
                },
                metadata={
                    "sheet_id": sheet_id,
                    "sheet_title": sheet_title,
                    "anchor": anchor,
                    "anchor_precision": anchor_precision,
                    "float_image_id": item.get("float_image_id") or item.get("floatImageId"),
                    "source_payload": item,
                },
            )
        )
        index += 1
    return resources


def _resources_from_values(
    *,
    sheet_id: str,
    sheet_title: str,
    values: list[list[Any]],
    start_index: int,
) -> list[ParsedSourceResource]:
    resources: list[ParsedSourceResource] = []
    index = start_index
    for row_index, row_values in enumerate(values, start=1):
        if not isinstance(row_values, (list, tuple)):
            continue
        for col_index, value in enumerate(row_values, start=1):
            coord = _a1_coord(row_index, col_index)
            for file_value in _iter_file_values(value):
                file_token = file_value["file_token"]
                resources.append(
                    _resource_from_file_value(
                        ref=_sheet_resource_ref(
                            sheet_title=sheet_title,
                            anchor=coord,
                            index=index,
                        ),
                        source_id=file_token,
                        position=f"{sheet_title}!{coord}",
                        file_value=file_value,
                        metadata={
                            "sheet_id": sheet_id,
                            "sheet_title": sheet_title,
                            "anchor": coord,
                            "anchor_precision": "cell",
                            "row": row_index,
                            "col": col_index,
                            "source_payload": file_value.get("source_payload"),
                        },
                    )
                )
                index += 1
    return resources


def _resources_from_bitable_fields(
    *,
    table_name: str,
    table_id: str,
    record_id: str,
    fields: dict[str, Any],
    start_index: int,
) -> list[ParsedSourceResource]:
    resources: list[ParsedSourceResource] = []
    index = start_index
    for field_name, value in fields.items():
        for file_value in _iter_file_values(value):
            resources.append(
                _resource_from_file_value(
                    ref=f"file_{index:03d}",
                    source_id=file_value["file_token"],
                    position=f"{table_id}/{record_id}/{field_name}",
                    file_value=file_value,
                    metadata={
                        "table_id": table_id,
                        "table_name": table_name,
                        "record_id": record_id,
                        "field_name": field_name,
                        "source_payload": file_value.get("source_payload"),
                    },
                )
            )
            index += 1
    return resources


def _iter_file_values(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        file_value = _normalized_file_value(value)
        if file_value is not None:
            return [file_value]
        results: list[dict[str, Any]] = []
        for item in value.values():
            results.extend(_iter_file_values(item))
        return results
    if isinstance(value, list):
        results: list[dict[str, Any]] = []
        for item in value:
            results.extend(_iter_file_values(item))
        return results
    return []


def _normalized_file_value(value: dict[str, Any]) -> dict[str, Any] | None:
    token_key, file_token = _first_present_key(
        value,
        "file_token",
        "fileToken",
        "image_token",
        "imageToken",
        "image_key",
        "imageKey",
        "float_image_token",
        "floatImageToken",
    )
    if file_token in (None, ""):
        return None
    result: dict[str, Any] = {
        "file_token": str(file_token),
        "token_key": token_key,
        "source_payload": value,
    }
    name = _first_present(value, "name", "file_name", "fileName", "title")
    mime_type = _first_present(value, "mime_type", "mimeType", "mime")
    if name is not None:
        result["name"] = name
    if mime_type is not None:
        result["mime_type"] = mime_type
    for key in ("size", "type", "url"):
        if value.get(key) is not None:
            result[key] = value[key]
    return result


def _resource_from_file_value(
    *,
    ref: str,
    source_id: str,
    position: str,
    file_value: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> ParsedSourceResource:
    mime_type = str(file_value.get("mime_type") or file_value.get("mimeType") or "")
    filename = str(file_value.get("name") or "")
    return ParsedSourceResource(
        ref=ref,
        type=_resource_type(
            name=filename,
            mime_type=mime_type,
            type_value=file_value.get("type"),
            token_key=file_value.get("token_key"),
            source_payload=file_value.get("source_payload"),
        ),
        source_id=source_id,
        position=position,
        filename=filename,
        file_token=str(file_value.get("file_token") or ""),
        mime_type=mime_type,
        metadata={"name": filename, **(metadata or {})},
    )


def _resource_type(
    *,
    name: str,
    mime_type: str,
    type_value: Any,
    token_key: Any,
    source_payload: Any,
) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if name.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
        return "image"
    if _is_image_type_value(type_value):
        return "image"
    if str(token_key or "").lower() in {
        "image_token",
        "imagetoken",
        "image_key",
        "imagekey",
        "float_image_token",
        "floatimagetoken",
    }:
        return "image"
    if _payload_mentions_image(source_payload):
        return "image"
    return "attachment"


def _is_image_type_value(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    normalized = value.strip().lower().replace("_", "-")
    return normalized in {
        "image",
        "img",
        "picture",
        "embed-image",
        "embedded-image",
        "sheet-image",
        "cell-image",
        "floating-image",
    }


def _payload_mentions_image(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    if any(key in value for key in ("imageToken", "image_token", "imageKey", "image_key")):
        return True
    for key in ("type", "resource_type", "resourceType", "file_type", "fileType"):
        if _is_image_type_value(value.get(key)):
            return True
    return False


def _simplify_bitable_fields(fields: Any) -> dict[str, Any]:
    if not isinstance(fields, dict):
        return {}
    return {str(key): _simplify_bitable_value(value) for key, value in fields.items()}


def _simplify_bitable_value(value: Any) -> Any:
    if isinstance(value, list):
        simplified = [_simplify_bitable_value(item) for item in value]
        strings = [item for item in simplified if isinstance(item, str)]
        non_strings = [item for item in simplified if not isinstance(item, str)]
        if strings and not non_strings:
            return "".join(strings)
        return simplified
    if isinstance(value, dict):
        token = _file_token(value)
        if token:
            result: dict[str, Any] = {"file_token": token}
            for key in ("name", "size", "mime_type", "mimeType", "type", "url"):
                if value.get(key) is not None:
                    result[key] = value[key]
            return result
        if "link" in value or "url" in value:
            return {
                key: value[key]
                for key in ("text", "link", "url", "type")
                if value.get(key) is not None
            }
        for key in ("text", "plain_text", "content", "name", "email"):
            if value.get(key) not in (None, ""):
                return str(value[key])
        return {str(key): _simplify_bitable_value(item) for key, item in value.items()}
    return value


def _file_token(value: dict[str, Any]) -> str:
    normalized = _normalized_file_value(value)
    if normalized is None:
        return ""
    return str(normalized["file_token"])


def _render_sheets_markdown(
    *,
    title: str,
    units: list[ParsedSourceUnit],
    resources: list[ParsedSourceResource],
) -> str:
    lines = [f"# Source: {title or 'Untitled Feishu Source'}", "", "Type: sheets", ""]
    resources_by_position: dict[str, list[ParsedSourceResource]] = {}
    for resource in resources:
        resources_by_position.setdefault(resource.position, []).append(resource)
    for unit in units:
        lines.extend([f"## Sheet: {unit.title}", ""])
        for cell in unit.cells:
            lines.append(f"- {cell.coord}: {cell.text}")
            for resource in resources_by_position.get(f"{unit.title}!{cell.coord}", []):
                tag = "image" if resource.type == "image" else "attachment"
                lines.append(
                    f'  <{tag} ref="{_xml_attr(resource.ref)}" position="{_xml_attr(resource.position)}" />'
                )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_bitable_markdown(*, title: str, units: list[ParsedSourceUnit]) -> str:
    lines = [f"# Source: {title or 'Untitled Feishu Source'}", "", "Type: bitable", ""]
    for unit in units:
        lines.extend([f"## Bitable: {unit.title}", ""])
        for row in unit.rows:
            lines.append(f"- {row.get('record_id')}: {json.dumps(row.get('fields', {}), ensure_ascii=False)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _unit_manifest(unit: ParsedSourceUnit) -> dict[str, Any]:
    return {
        "unit_id": unit.unit_id,
        "kind": unit.kind,
        "title": unit.title,
        "path": unit.path,
        **{
            key: value
            for key, value in unit.metadata.items()
            if key
            in {
                "sheet_id",
                "table_id",
                "index",
                "row_count",
                "col_count",
                "non_empty_cell_count",
                "resource_count",
                "record_count",
            }
        },
    }


def _anchor_from_resource_payload(payload: Any) -> tuple[str | None, str]:
    if not isinstance(payload, dict):
        return None, "floating"
    anchor = payload.get("anchor") or payload.get("position") or payload.get("range")
    if isinstance(anchor, str) and anchor:
        anchor = _strip_sheet_from_anchor(anchor)
        normalized = anchor.strip().upper()
        if re.fullmatch(r"[A-Z]+\d+", normalized):
            return anchor, "cell"
        if re.fullmatch(r"[A-Z]+\d+:[A-Z]+\d+", normalized):
            return anchor, "range"
        return anchor, "unknown"
    coord = _coord_from_anchor_dict(payload)
    if coord:
        return coord, "cell"
    return None, "floating"


def _coord_from_anchor_dict(value: dict[str, Any]) -> str | None:
    coord = _first_present(value, "coord", "cell", "cellRef", "cell_ref")
    if isinstance(coord, str) and coord:
        return coord
    row = _first_present(value, "row", "rowIndex", "row_index")
    col = _first_present(value, "col", "column", "columnIndex", "column_index")
    if row is None or col is None:
        return None
    try:
        row_number = int(row)
        col_number = int(col)
    except (TypeError, ValueError):
        return None
    if row_number < 1 or col_number < 1:
        return None
    return f"{_a1_col_name(col_number)}{row_number}"


def _first_present(value: dict[str, Any], *keys: str) -> Any:
    _key, found = _first_present_key(value, *keys)
    return found


def _first_present_key(value: dict[str, Any], *keys: str) -> tuple[str | None, Any]:
    for key in keys:
        if key in value and value[key] is not None:
            return key, value[key]
    return None, None


def _expect_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FeishuClientError(FEISHU_API_ERROR, f"Feishu {label} must be an object")
    return value


def _expect_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise FeishuClientError(FEISHU_API_ERROR, f"Feishu {label} must be a list")
    return value


def _dig(value: Any, *keys: str, default: Any = None) -> Any:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return default
        if key not in current:
            return default
        current = current[key]
    return current


def _a1_coord(row: int, col: int) -> str:
    return f"{_a1_col_name(col)}{row}"


def _a1_col_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(ord("A") + remainder) + name
    return name


def _sheet_resource_ref(*, sheet_title: str, anchor: str, index: int) -> str:
    return (
        f"img_{_resource_ref_part(sheet_title)}_"
        f"{_resource_ref_part(_strip_sheet_from_anchor(anchor))}_{index:03d}"
    )


def _resource_ref_part(value: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s!]+', "_", str(value).strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "unknown"


def _strip_sheet_from_anchor(anchor: str) -> str:
    text = str(anchor).strip()
    if "!" in text:
        text = text.rsplit("!", 1)[-1]
    if ":" in text:
        left, right = text.split(":", 1)
        right = right.rsplit("!", 1)[-1]
        return f"{left}:{right}"
    return text


def _safe_id(value: str) -> str:
    return re.sub(r"[^\w.-]+", "_", str(value), flags=re.UNICODE).strip("_") or "item"


def _title_from_first(items: list[dict[str, Any]], fallback: str) -> str:
    if not items:
        return fallback
    first = items[0]
    return str(first.get("name") or first.get("title") or fallback)


def _xml_attr(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
