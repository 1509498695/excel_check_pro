"""Reader dispatcher for local Source Evidence uploads."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from backend.app.test_cases import source_evidence_storage
from backend.app.test_cases.excel_source_reader import (
    read_xls_source_evidence,
    read_xlsx_source_evidence,
)
from backend.app.test_cases.schemas import (
    GenerationWarning,
    ParsedSource,
    ParsedSourceResource,
)


SUPPORTED_LOCAL_SOURCE_SUFFIXES = frozenset({".xlsx", ".xls", ".png", ".jpg", ".jpeg", ".webp"})
SUPPORTED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp"})


def read_local_uploaded_source(
    *,
    project_id: int,
    run_id: int,
    upload_relative_path: str,
    original_filename: str,
    source_sha256: str,
    origin: str = "local_file",
) -> ParsedSource:
    """Read a run-local uploaded source into the generic ParsedSource contract."""
    source_path = source_evidence_storage.resolve_source_evidence_path(
        project_id,
        run_id,
        upload_relative_path,
    )
    suffix = Path(original_filename).suffix.lower()
    if suffix == ".xlsx":
        return read_xlsx_source_evidence(
            project_id=project_id,
            run_id=run_id,
            source_path=source_path,
            original_filename=original_filename,
            source_sha256=source_sha256,
            origin=origin,
        )
    if suffix == ".xls":
        return read_xls_source_evidence(
            project_id=project_id,
            run_id=run_id,
            source_path=source_path,
            original_filename=original_filename,
            source_sha256=source_sha256,
            origin=origin,
        )
    if suffix in SUPPORTED_IMAGE_SUFFIXES:
        return read_standalone_image_source(
            project_id=project_id,
            run_id=run_id,
            source_path=source_path,
            original_filename=original_filename,
            source_sha256=source_sha256,
            suffix=suffix,
            origin=origin,
        )
    raise ValueError(f"不支持的本地文件类型：{suffix or '无后缀'}。")


def read_standalone_image_source(
    *,
    project_id: int,
    run_id: int,
    source_path: Path,
    original_filename: str,
    source_sha256: str,
    suffix: str,
    origin: str = "local_file",
) -> ParsedSource:
    """Register an uploaded image as a textless Source Evidence run."""
    try:
        with Image.open(source_path) as image:
            image.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValueError(f"读取本地上传文件失败：无法识别图片文件：{exc}") from exc

    extension = ".jpg" if suffix in {".jpg", ".jpeg"} else suffix
    mime_type = _image_mime_type(extension)
    ref = "svn_img_001" if origin == "svn_file" else "local_img_001"
    filename = f"{ref}{extension}"
    relative_path = f"images/{filename}"
    position = "svn:image=1" if origin == "svn_file" else "local:image=1"
    source_evidence_storage.write_source_evidence_bytes(
        project_id,
        run_id,
        relative_path,
        source_path.read_bytes(),
    )
    warning = GenerationWarning(
        source=origin,
        level="warning",
        message="独立图片缺少文本主体；生成前需要先观察并采纳视觉证据。",
    )
    return ParsedSource(
        title=original_filename,
        source_type=origin,
        doc_type="image",
        token=f"sha256:{source_sha256}",
        url="",
        markdown=(
            f"# Source: {original_filename}\n\n"
            "Type: image\n\n"
            f'<image ref="{ref}" position="{position}" />\n'
        ),
        source_units=[],
        resources=[
            ParsedSourceResource(
                ref=ref,
                type="image",
                source_id=ref,
                position=position,
                filename=filename,
                file_token=ref,
                mime_type=mime_type,
                status="downloaded",
                metadata={
                    "local_path": relative_path,
                    "source": "standalone_image",
                    "origin": origin,
                },
            )
        ],
        raw_manifest={
            "doc_type": "image",
            "original_filename": original_filename,
            "sha256": source_sha256,
            "resource_count": 1,
        },
        warnings=[warning],
    )


def _image_mime_type(extension: str) -> str:
    if extension == ".jpg":
        return "image/jpeg"
    if extension == ".webp":
        return "image/webp"
    return "image/png"
