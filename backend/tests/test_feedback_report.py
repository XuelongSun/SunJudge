from datetime import UTC, datetime

from app.services.feedback_report import markdown_filename, markdown_text, report_date


def test_feedback_table_cells_cannot_create_extra_rows_or_columns():
    assert markdown_text("第一行|内容\n第二行 **说明**") == r"第一行\|内容 第二行 \*\*说明\*\*"
    assert markdown_filename("a`|b.md") == r"`` a`\|b.md ``"
    assert markdown_text("✅ :smile:") == "✅ :smile:"


def test_report_dates_use_shanghai_time_for_sqlite_and_aware_timestamps():
    assert report_date(datetime(2026, 10, 8, 12)) == "2026-10-08 20:00:00"
    assert report_date(datetime(2026, 10, 8, 12, tzinfo=UTC)) == "2026-10-08 20:00:00"
    assert report_date(None) == "未设置"
