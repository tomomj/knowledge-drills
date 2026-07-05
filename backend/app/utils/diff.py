from difflib import unified_diff


def build_unified_diff(
    base_markdown: str,
    patched_markdown: str,
    *,
    from_file: str = "base.md",
    to_file: str = "patched.md",
) -> str:
    if base_markdown == patched_markdown:
        return ""

    # 末尾に改行がないと unified_diff の出力行が連結されて表示が崩れるため正規化する
    if not base_markdown.endswith("\n"):
        base_markdown += "\n"
    if not patched_markdown.endswith("\n"):
        patched_markdown += "\n"

    return "".join(
        unified_diff(
            base_markdown.splitlines(keepends=True),
            patched_markdown.splitlines(keepends=True),
            fromfile=from_file,
            tofile=to_file,
        )
    )
