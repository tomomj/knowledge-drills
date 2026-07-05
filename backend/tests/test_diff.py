from app.schemas import DocumentPatch, PatchStatus
from app.utils.diff import build_unified_diff


def test_unified_diff_is_empty_when_markdown_is_unchanged() -> None:
    assert build_unified_diff("# Title\nBody\n", "# Title\nBody\n") == ""


def test_unified_diff_includes_multiple_line_changes_and_markdown_headings() -> None:
    diff_text = build_unified_diff(
        "# Title\n\n## 手順\n古い説明\n末尾\n",
        "# Title\n\n## 手順\n新しい説明\n補足\n末尾\n",
    )

    assert "--- base.md" in diff_text
    assert "+++ patched.md" in diff_text
    assert "## 手順" in diff_text
    assert "-古い説明" in diff_text
    assert "+新しい説明" in diff_text
    assert "+補足" in diff_text


def test_diff_text_can_be_saved_on_document_patch() -> None:
    diff_text = build_unified_diff("# Before\n", "# After\n")
    patch = DocumentPatch(
        id="patch-1",
        course_id="course-1",
        drill_run_id="drill-1",
        status=PatchStatus.PROPOSED,
        base_markdown="# Before\n",
        patched_markdown="# After\n",
        patch_summary="見出しを更新",
        diff_text=diff_text,
    )

    assert patch.diff_text == diff_text
