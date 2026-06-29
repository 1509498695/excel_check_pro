"""用例生成 V1 参考案例库服务。"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import BinaryIO
from uuid import uuid4

from fastapi import UploadFile
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models import (
    TestCaseReferenceCategoryRecord,
    TestCaseReferenceFileRecord,
)
from backend.app.test_cases.constants import (
    REFERENCE_ALLOWED_SUFFIXES,
    REFERENCE_MAX_FILE_BYTES,
    REFERENCE_UNCATEGORIZED_NAME,
)
from backend.app.test_cases.reference_profiles import (
    ReferenceProfileError,
    extract_reference_profile,
)
from backend.app.test_cases.schemas import (
    ReferenceCategoryCreateRequest,
    ReferenceCategoryListResponse,
    ReferenceCategoryResponse,
    ReferenceCategoryUpdateRequest,
    ReferenceFileListResponse,
    ReferenceFileResponse,
    ReferenceProfile,
    ReferenceSheetOption,
)
from backend.config import settings


class ReferenceLibraryError(Exception):
    """参考案例库业务错误，可直接转换为 HTTP 错误。"""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class ReferenceGenerationContext:
    """生成链路使用的已校验参考上下文。"""

    reference_ids: list[int]
    supplementary_references: list[dict[str, object]]
    primary_reference_id: int | None = None
    primary_reference_profile: dict[str, object] | None = None

    @property
    def export_profile(self) -> dict[str, object] | None:
        return self.primary_reference_profile

    def model_dump(self) -> dict[str, object]:
        return {
            "reference_ids": self.reference_ids,
            "primary_reference_id": self.primary_reference_id,
            "primary_reference_sheet_name": (
                self.primary_reference_profile.get("selected_sheet_name")
                if self.primary_reference_profile
                else None
            ),
            "primary_reference_case_count": (
                self.primary_reference_profile.get("reference_case_count")
                if self.primary_reference_profile
                else None
            ),
            "supplementary_references": self.supplementary_references,
        }


async def create_reference_category(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    payload: ReferenceCategoryCreateRequest,
) -> ReferenceCategoryResponse:
    """创建项目内参考案例分类。"""
    name = _normalize_category_name(payload.name)
    await _ensure_category_name_available(db, project_id=project_id, name=name)

    record = TestCaseReferenceCategoryRecord(
        project_id=project_id,
        name=name,
        name_key=name,
        created_by=user_id,
    )
    db.add(record)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ReferenceLibraryError(400, "同项目下已存在同名参考分类。") from exc
    await db.refresh(record)
    return ReferenceCategoryResponse(id=record.id, name=record.name, reference_count=0)


async def list_reference_categories(
    db: AsyncSession,
    *,
    project_id: int,
) -> ReferenceCategoryListResponse:
    """列出项目参考案例分类及 active 参考数量。"""
    category_result = await db.execute(
        select(TestCaseReferenceCategoryRecord)
        .where(TestCaseReferenceCategoryRecord.project_id == project_id)
        .order_by(TestCaseReferenceCategoryRecord.created_at.asc())
    )
    categories = list(category_result.scalars().all())
    counts = await _count_active_references_by_category(db, project_id=project_id)
    return ReferenceCategoryListResponse(
        items=[
            ReferenceCategoryResponse(
                id=category.id,
                name=category.name,
                reference_count=counts.get(category.id, 0),
            )
            for category in categories
        ]
    )


async def rename_reference_category(
    db: AsyncSession,
    *,
    project_id: int,
    category_id: int,
    payload: ReferenceCategoryUpdateRequest,
) -> ReferenceCategoryResponse:
    """重命名参考案例分类。"""
    record = await _get_category_or_error(db, project_id=project_id, category_id=category_id)
    name = _normalize_category_name(payload.name)
    if name != record.name:
        await _ensure_category_name_available(
            db,
            project_id=project_id,
            name=name,
            exclude_category_id=category_id,
        )
        record.name = name
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ReferenceLibraryError(400, "同项目下已存在同名参考分类。") from exc
    await db.refresh(record)
    counts = await _count_active_references_by_category(db, project_id=project_id)
    return ReferenceCategoryResponse(
        id=record.id,
        name=record.name,
        reference_count=counts.get(record.id, 0),
    )


async def delete_reference_category(
    db: AsyncSession,
    *,
    project_id: int,
    category_id: int,
) -> dict[str, object]:
    """删除分类：关联参考移到未分类，并清空推荐主参考。"""
    record = await _get_category_or_error(db, project_id=project_id, category_id=category_id)
    await db.execute(
        update(TestCaseReferenceFileRecord)
        .where(
            TestCaseReferenceFileRecord.project_id == project_id,
            TestCaseReferenceFileRecord.category_id == category_id,
        )
        .values(category_id=None, is_recommended_primary=False)
    )
    await db.delete(record)
    await db.commit()
    return {"id": category_id, "deleted": True}


async def list_reference_files(
    db: AsyncSession,
    *,
    project_id: int,
    category_id: int | None = None,
) -> ReferenceFileListResponse:
    """列出项目 active 参考案例。"""
    statement = select(TestCaseReferenceFileRecord).where(
        TestCaseReferenceFileRecord.project_id == project_id,
        TestCaseReferenceFileRecord.deleted_at.is_(None),
    )
    if category_id is not None:
        statement = statement.where(TestCaseReferenceFileRecord.category_id == category_id)
    statement = statement.order_by(TestCaseReferenceFileRecord.created_at.asc())
    result = await db.execute(statement)
    records = list(result.scalars().all())
    category_names = await _load_category_names(db, project_id=project_id)
    return ReferenceFileListResponse(
        items=[
            _to_reference_file_response(record, category_names=category_names)
            for record in records
        ]
    )


async def resolve_generation_reference_context(
    db: AsyncSession,
    *,
    project_id: int,
    reference_ids: list[int],
    primary_reference_id: int | None,
    primary_reference_sheet_name: str | None,
) -> ReferenceGenerationContext:
    """校验并解析生成请求中的参考案例选择。

    这里只读取确定性画像和元数据。参考案例只作为输出形态参考，
    不作为需求来源，也不读取原始文件内容。
    """
    selected_ids = _unique_ints(reference_ids)
    if primary_reference_id is not None and primary_reference_id not in selected_ids:
        raise ReferenceLibraryError(400, "主参考案例必须属于已选参考案例集合。")
    if not selected_ids:
        return ReferenceGenerationContext(reference_ids=[], supplementary_references=[])

    records = await _load_active_reference_records(
        db,
        project_id=project_id,
        reference_ids=selected_ids,
    )
    records_by_id = {record.id: record for record in records}
    if set(records_by_id) != set(selected_ids):
        raise ReferenceLibraryError(400, "参考案例不存在或已删除，或不属于当前项目。")

    summaries = [
        _build_reference_summary(records_by_id[reference_id])
        for reference_id in selected_ids
    ]
    if primary_reference_id is None:
        return ReferenceGenerationContext(
            reference_ids=selected_ids,
            supplementary_references=summaries,
        )

    primary_record = records_by_id[primary_reference_id]
    primary_profile = _build_selected_primary_profile(
        primary_record,
        requested_sheet_name=primary_reference_sheet_name,
    )
    supplementary = [
        summary for summary in summaries if summary["id"] != primary_reference_id
    ]
    return ReferenceGenerationContext(
        reference_ids=selected_ids,
        supplementary_references=supplementary,
        primary_reference_id=primary_reference_id,
        primary_reference_profile=primary_profile,
    )


async def upload_reference_file(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    upload: UploadFile,
    category_id: int | None = None,
) -> ReferenceFileResponse:
    """保存参考案例文件，生成确定性画像并创建 active 记录。"""
    original_filename = _normalize_upload_filename(upload.filename)
    suffix = Path(original_filename).suffix.lower()
    if suffix not in REFERENCE_ALLOWED_SUFFIXES:
        allowed = ", ".join(sorted(REFERENCE_ALLOWED_SUFFIXES))
        raise ReferenceLibraryError(400, f"不支持的参考案例文件类型，仅支持：{allowed}。")
    if category_id is not None:
        await _get_category_or_error(db, project_id=project_id, category_id=category_id)
    await _ensure_original_filename_available(
        db,
        project_id=project_id,
        category_id=category_id,
        original_filename=original_filename,
    )

    storage_dir = _reference_project_dir(project_id)
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_filename = f"{uuid4().hex}{suffix}"
    storage_path = storage_dir / stored_filename

    try:
        size_bytes = await _write_upload(upload, storage_path)
        profile = extract_reference_profile(storage_path)
    except ReferenceProfileError:
        _unlink_if_exists(storage_path)
        raise
    except ReferenceLibraryError:
        _unlink_if_exists(storage_path)
        raise
    except OSError as exc:
        _unlink_if_exists(storage_path)
        raise ReferenceLibraryError(500, f"保存参考案例文件失败：{exc}") from exc

    record = TestCaseReferenceFileRecord(
        project_id=project_id,
        category_id=category_id,
        original_filename=original_filename,
        stored_filename=stored_filename,
        suffix=suffix,
        size_bytes=size_bytes,
        storage_path=str(storage_path),
        profile_json=profile.model_dump_json(),
        uploaded_by=user_id,
        is_recommended_primary=False,
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)
    category_names = await _load_category_names(db, project_id=project_id)
    return _to_reference_file_response(record, category_names=category_names)


async def set_recommended_primary_reference(
    db: AsyncSession,
    *,
    project_id: int,
    reference_id: int,
) -> ReferenceFileResponse:
    """设置分类范围内唯一推荐主参考。"""
    record = await _get_active_reference_or_error(
        db,
        project_id=project_id,
        reference_id=reference_id,
    )
    category_filter = (
        TestCaseReferenceFileRecord.category_id.is_(None)
        if record.category_id is None
        else TestCaseReferenceFileRecord.category_id == record.category_id
    )
    await db.execute(
        update(TestCaseReferenceFileRecord)
        .where(
            TestCaseReferenceFileRecord.project_id == project_id,
            TestCaseReferenceFileRecord.deleted_at.is_(None),
            category_filter,
        )
        .values(is_recommended_primary=False)
    )
    record.is_recommended_primary = True
    await db.commit()
    await db.refresh(record)
    category_names = await _load_category_names(db, project_id=project_id)
    return _to_reference_file_response(record, category_names=category_names)


async def delete_reference_file(
    db: AsyncSession,
    *,
    project_id: int,
    reference_id: int,
    user_id: int,
) -> dict[str, object]:
    """删除参考案例：先删物理文件，失败则保留 active 状态。"""
    record = await _get_active_reference_or_error(
        db,
        project_id=project_id,
        reference_id=reference_id,
    )
    if record.storage_path:
        path = Path(record.storage_path)
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            await db.rollback()
            raise ReferenceLibraryError(500, f"删除参考案例文件失败：{exc}") from exc

    record.storage_path = ""
    record.profile_json = ""
    record.is_recommended_primary = False
    record.deleted_by = user_id
    record.deleted_at = datetime.datetime.now(datetime.UTC)
    await db.commit()
    return {"id": reference_id, "deleted": True}


async def _load_active_reference_records(
    db: AsyncSession,
    *,
    project_id: int,
    reference_ids: list[int],
) -> list[TestCaseReferenceFileRecord]:
    if not reference_ids:
        return []
    result = await db.execute(
        select(TestCaseReferenceFileRecord).where(
            TestCaseReferenceFileRecord.project_id == project_id,
            TestCaseReferenceFileRecord.id.in_(reference_ids),
            TestCaseReferenceFileRecord.deleted_at.is_(None),
        )
    )
    return list(result.scalars().all())


def _build_reference_summary(record: TestCaseReferenceFileRecord) -> dict[str, object]:
    profile = _parse_profile_or_error(record)
    sheet_options = [
        {
            "name": option.name,
            "reference_case_count": option.reference_case_count,
            "recognized_fields": _recognized_fields(option.columns),
        }
        for option in profile.sheet_options
    ]
    return {
        "id": record.id,
        "original_filename": record.original_filename,
        "source_type": profile.source_type,
        "default_sheet_name": profile.default_sheet_name,
        "reference_case_count": profile.reference_case_count,
        "recognized_fields": _recognized_fields(profile.columns),
        "sheet_options": sheet_options,
    }


def _build_selected_primary_profile(
    record: TestCaseReferenceFileRecord,
    *,
    requested_sheet_name: str | None,
) -> dict[str, object]:
    profile = _parse_profile_or_error(record)
    profile_data = profile.model_dump(mode="json")
    requested_sheet_name = (requested_sheet_name or "").strip() or None

    if profile.source_type == "excel":
        selected_sheet = _select_excel_reference_sheet(profile, requested_sheet_name)
        profile_data["selected_sheet_name"] = selected_sheet.name
        profile_data["reference_case_count"] = selected_sheet.reference_case_count
        profile_data["columns"] = [
            column.model_dump(mode="json") for column in selected_sheet.columns
        ]
    else:
        if requested_sheet_name:
            raise ReferenceLibraryError(400, "当前主参考没有 Sheet，请清空主参考 Sheet 名称。")
        profile_data["selected_sheet_name"] = None

    profile_data["reference_id"] = record.id
    profile_data["original_filename"] = record.original_filename
    profile_data["recognized_fields"] = _recognized_fields_from_dict(profile_data)
    return profile_data


def _select_excel_reference_sheet(
    profile: ReferenceProfile,
    requested_sheet_name: str | None,
) -> ReferenceSheetOption:
    selected_name = requested_sheet_name or profile.default_sheet_name
    if not selected_name:
        raise ReferenceLibraryError(400, "Excel 主参考缺少默认 Sheet，请重新上传参考案例。")
    for option in profile.sheet_options:
        if option.name == selected_name:
            return option
    raise ReferenceLibraryError(400, f"主参考 Sheet '{selected_name}' 不在可用 Sheet 列表中。")


def _parse_profile_or_error(record: TestCaseReferenceFileRecord) -> ReferenceProfile:
    profile = _parse_profile(record.profile_json)
    if profile is None:
        raise ReferenceLibraryError(400, "参考案例画像不可用，请重新上传参考案例。")
    return profile


def _recognized_fields(columns: list) -> list[str]:
    fields: list[str] = []
    for column in columns:
        standard_field = getattr(column, "standard_field", None)
        if isinstance(standard_field, str) and standard_field:
            fields.append(standard_field)
    return list(dict.fromkeys(fields))


def _recognized_fields_from_dict(profile_data: dict[str, object]) -> list[str]:
    columns = profile_data.get("columns")
    if not isinstance(columns, list):
        return []
    fields: list[str] = []
    for column in columns:
        if not isinstance(column, dict):
            continue
        standard_field = column.get("standard_field")
        if isinstance(standard_field, str) and standard_field:
            fields.append(standard_field)
    return list(dict.fromkeys(fields))


async def _get_category_or_error(
    db: AsyncSession,
    *,
    project_id: int,
    category_id: int,
) -> TestCaseReferenceCategoryRecord:
    result = await db.execute(
        select(TestCaseReferenceCategoryRecord).where(
            TestCaseReferenceCategoryRecord.project_id == project_id,
            TestCaseReferenceCategoryRecord.id == category_id,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise ReferenceLibraryError(404, "参考案例分类不存在。")
    return record


async def _get_active_reference_or_error(
    db: AsyncSession,
    *,
    project_id: int,
    reference_id: int,
) -> TestCaseReferenceFileRecord:
    result = await db.execute(
        select(TestCaseReferenceFileRecord).where(
            TestCaseReferenceFileRecord.project_id == project_id,
            TestCaseReferenceFileRecord.id == reference_id,
            TestCaseReferenceFileRecord.deleted_at.is_(None),
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        raise ReferenceLibraryError(404, "参考案例不存在或已删除。")
    return record


async def _ensure_category_name_available(
    db: AsyncSession,
    *,
    project_id: int,
    name: str,
    exclude_category_id: int | None = None,
) -> None:
    statement = select(TestCaseReferenceCategoryRecord.id).where(
        TestCaseReferenceCategoryRecord.project_id == project_id,
        TestCaseReferenceCategoryRecord.name_key == name.strip(),
    )
    if exclude_category_id is not None:
        statement = statement.where(TestCaseReferenceCategoryRecord.id != exclude_category_id)
    result = await db.execute(statement.limit(1))
    if result.scalar_one_or_none() is not None:
        raise ReferenceLibraryError(400, "同项目下已存在同名参考分类。")


async def _ensure_original_filename_available(
    db: AsyncSession,
    *,
    project_id: int,
    category_id: int | None,
    original_filename: str,
) -> None:
    category_filter = (
        TestCaseReferenceFileRecord.category_id.is_(None)
        if category_id is None
        else TestCaseReferenceFileRecord.category_id == category_id
    )
    result = await db.execute(
        select(TestCaseReferenceFileRecord.id)
        .where(
            TestCaseReferenceFileRecord.project_id == project_id,
            TestCaseReferenceFileRecord.deleted_at.is_(None),
            category_filter,
            TestCaseReferenceFileRecord.original_filename == original_filename,
        )
        .limit(1)
    )
    if result.scalar_one_or_none() is not None:
        raise ReferenceLibraryError(400, "同一分类下已存在同名参考案例。")


async def _count_active_references_by_category(
    db: AsyncSession,
    *,
    project_id: int,
) -> dict[int | None, int]:
    result = await db.execute(
        select(
            TestCaseReferenceFileRecord.category_id,
            func.count(TestCaseReferenceFileRecord.id),
        )
        .where(
            TestCaseReferenceFileRecord.project_id == project_id,
            TestCaseReferenceFileRecord.deleted_at.is_(None),
        )
        .group_by(TestCaseReferenceFileRecord.category_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


async def _load_category_names(
    db: AsyncSession,
    *,
    project_id: int,
) -> dict[int, str]:
    result = await db.execute(
        select(
            TestCaseReferenceCategoryRecord.id,
            TestCaseReferenceCategoryRecord.name,
        ).where(TestCaseReferenceCategoryRecord.project_id == project_id)
    )
    return {int(row[0]): str(row[1]) for row in result.all()}


def _to_reference_file_response(
    record: TestCaseReferenceFileRecord,
    *,
    category_names: dict[int, str],
) -> ReferenceFileResponse:
    profile = _parse_profile(record.profile_json)
    return ReferenceFileResponse(
        id=record.id,
        category_id=record.category_id,
        category_name=(
            category_names.get(record.category_id, REFERENCE_UNCATEGORIZED_NAME)
            if record.category_id is not None
            else REFERENCE_UNCATEGORIZED_NAME
        ),
        original_filename=record.original_filename,
        suffix=record.suffix,
        size_bytes=record.size_bytes,
        profile=profile,
        reference_case_count=profile.reference_case_count if profile else None,
        default_sheet_name=profile.default_sheet_name if profile else None,
        is_recommended_primary=record.is_recommended_primary,
        created_at=record.created_at.isoformat(),
        updated_at=record.updated_at.isoformat(),
    )


def _parse_profile(profile_json: str) -> ReferenceProfile | None:
    if not profile_json:
        return None
    try:
        return ReferenceProfile.model_validate(json.loads(profile_json))
    except (ValueError, TypeError):
        return None


async def _write_upload(upload: UploadFile, storage_path: Path) -> int:
    size_bytes = 0
    with storage_path.open("wb") as output:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            size_bytes += len(chunk)
            if size_bytes > REFERENCE_MAX_FILE_BYTES:
                raise ReferenceLibraryError(400, "参考案例文件超过大小限制。")
            _write_chunk(output, chunk)
    if size_bytes <= 0:
        raise ReferenceLibraryError(400, "参考案例文件为空。")
    return size_bytes


def _write_chunk(output: BinaryIO, chunk: bytes) -> None:
    output.write(chunk)


def _normalize_category_name(name: str) -> str:
    normalized = name.strip()
    if not normalized:
        raise ReferenceLibraryError(400, "参考案例分类名称不能为空。")
    if len(normalized) > 80:
        raise ReferenceLibraryError(400, "参考案例分类名称不能超过 80 个字符。")
    return normalized


def _normalize_upload_filename(filename: str | None) -> str:
    if not filename:
        raise ReferenceLibraryError(400, "缺少参考案例文件名。")
    original_filename = Path(filename).name.strip()
    original_filename = re.sub(r"[\x00-\x1f]+", "", original_filename)
    if not original_filename:
        raise ReferenceLibraryError(400, "缺少参考案例文件名。")
    if len(original_filename) > 255:
        raise ReferenceLibraryError(400, "参考案例文件名过长。")
    return original_filename


def _unique_ints(values: list[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _reference_project_dir(project_id: int) -> Path:
    return settings.runtime_dir / "test-case-references" / str(project_id)


def _unlink_if_exists(path: Path) -> None:
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
