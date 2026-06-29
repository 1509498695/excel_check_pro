"""用例生成 V1 参考案例确定性画像测试。"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from backend.app.test_cases.reference_profiles import (
    ReferenceProfileError,
    extract_reference_profile,
)


def _write_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, dataframe in sheets.items():
            dataframe.to_excel(writer, sheet_name=sheet_name, index=False)
    return path


def test_excel_profile_reads_all_sheets_and_prefers_default_sheet_name(
    tmp_path: Path,
) -> None:
    workbook_path = _write_workbook(
        tmp_path / "references.xlsx",
        {
            "说明": pd.DataFrame({"字段": ["这里只是说明"], "值": ["不是用例"]}),
            "功能用例": pd.DataFrame(
                {
                    "模块": ["支付"],
                    "用例标题": ["支付成功后展示到账"],
                    "操作步骤": ["发起支付并完成"],
                    "预期结果": ["展示到账状态"],
                }
            ),
            "测试用例": pd.DataFrame(
                {
                    "用例编号": ["TC-001", "TC-002", ""],
                    "功能模块": ["登录", "登录", "登录汇总"],
                    "用例标题": ["账号密码登录成功", "密码错误提示", ""],
                    "操作步骤": ["输入正确账号密码", "输入错误密码", ""],
                    "预期结果": ["进入首页", "提示密码错误", ""],
                    "优先级": ["P1", "P2", ""],
                    "备注": ["", "", "汇总 2 条"],
                }
            ),
        },
    )

    profile = extract_reference_profile(workbook_path)

    assert profile.source_type == "excel"
    assert profile.default_sheet_name == "测试用例"
    assert profile.reference_case_count == 2
    assert {option.name for option in profile.sheet_options} == {"功能用例", "测试用例"}
    assert any("说明" in warning.message for warning in profile.warnings)
    assert [column.standard_field for column in profile.columns[:6]] == [
        "case_id",
        "module",
        "title",
        "steps",
        "expected_results",
        "priority",
    ]


def test_excel_profile_does_not_count_group_or_remark_only_rows(
    tmp_path: Path,
) -> None:
    workbook_path = _write_workbook(
        tmp_path / "grouping.xlsx",
        {
            "用例": pd.DataFrame(
                {
                    "模块": ["登录模块", "登录模块", ""],
                    "用例标题": ["", "账号密码登录成功", ""],
                    "操作步骤": ["", "输入正确账号密码", ""],
                    "预期结果": ["", "进入首页", ""],
                    "备注": ["分组行", "", "备注行"],
                }
            )
        },
    )

    profile = extract_reference_profile(workbook_path)

    assert profile.default_sheet_name == "用例"
    assert profile.reference_case_count == 1


def test_excel_profile_rejects_workbook_without_usable_sheet(tmp_path: Path) -> None:
    workbook_path = _write_workbook(
        tmp_path / "invalid.xlsx",
        {
            "原始数据": pd.DataFrame(
                {
                    "姓名": ["张三"],
                    "年龄": [18],
                    "城市": ["上海"],
                }
            )
        },
    )

    with pytest.raises(ReferenceProfileError, match="没有可用的测试用例 Sheet"):
        extract_reference_profile(workbook_path)


@pytest.mark.parametrize(
    ("filename", "content", "source_type", "expected_count"),
    [
        ("cases.md", "- [ ] 登录成功\n- [x] 密码错误提示\n", "markdown", 2),
        ("cases.txt", "登录成功\n密码错误提示\n", "text", 2),
    ],
)
def test_text_profile_accepts_supported_plain_text_files(
    tmp_path: Path,
    filename: str,
    content: str,
    source_type: str,
    expected_count: int,
) -> None:
    reference_path = tmp_path / filename
    reference_path.write_text(content, encoding="utf-8")

    profile = extract_reference_profile(reference_path)

    assert profile.source_type == source_type
    assert profile.reference_case_count == expected_count
    assert profile.default_sheet_name is None
