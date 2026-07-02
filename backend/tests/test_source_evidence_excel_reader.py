"""local_file Source Evidence Excel reader tests."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.drawing.image import Image as OpenpyxlImage
from PIL import Image

from backend.app.test_cases import source_evidence_storage
from backend.app.test_cases.excel_source_reader import read_xlsx_source_evidence


def _make_png(path: Path) -> None:
    image = Image.new("RGB", (4, 4), color=(220, 40, 40))
    image.save(path, format="PNG")


def _make_xlsx_with_hidden_sheet_and_image(path: Path, image_path: Path) -> None:
    workbook = Workbook()
    visible = workbook.active
    visible.title = "活动配置"
    visible["A1"] = "活动名称"
    visible["B2"] = "春节签到"
    visible.add_image(OpenpyxlImage(str(image_path)), "B12")

    hidden = workbook.create_sheet("隐藏配置")
    hidden["A1"] = "不应进入快照"
    hidden.sheet_state = "hidden"

    workbook.save(path)


def test_read_xlsx_source_evidence_reads_visible_text_and_extracts_images(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """可见 Sheet 文本和图片进入 ParsedSource，隐藏 Sheet 只产生 warning。"""
    root = tmp_path / "source-evidence"
    monkeypatch.setattr(
        source_evidence_storage,
        "settings",
        type("Settings", (), {"source_evidence_dir": root})(),
    )
    upload_dir = source_evidence_storage.ensure_source_evidence_subdirs(
        project_id=1,
        run_id=2,
    )["raw"] / "upload"
    upload_dir.mkdir(parents=True)
    image_path = tmp_path / "source.png"
    workbook_path = upload_dir / "source.xlsx"
    _make_png(image_path)
    _make_xlsx_with_hidden_sheet_and_image(workbook_path, image_path)

    parsed = read_xlsx_source_evidence(
        project_id=1,
        run_id=2,
        source_path=workbook_path,
        original_filename="活动配置.xlsx",
        source_sha256="abc123",
    )

    assert parsed.doc_type == "xlsx"
    assert parsed.title == "活动配置.xlsx"
    assert parsed.token == "sha256:abc123"
    assert any(unit.title == "活动配置" for unit in parsed.source_units)
    assert "春节签到" in parsed.markdown
    assert "不应进入快照" not in parsed.markdown
    assert any("隐藏配置" in warning.message for warning in parsed.warnings)

    resource = parsed.resources[0]
    assert resource.ref == "excel_img_s001_001"
    assert resource.type == "image"
    assert resource.position == "excel:sheet=活动配置:image=1:anchor=B12"
    assert resource.filename == "excel_img_s001_001.png"
    assert resource.mime_type == "image/png"
    assert resource.metadata["local_path"] == "images/excel_img_s001_001.png"
    assert source_evidence_storage.resolve_source_evidence_path(
        1,
        2,
        resource.metadata["local_path"],
    ).is_file()
