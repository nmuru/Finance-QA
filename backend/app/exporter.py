"""Offline export of completed SDLC documentation."""

from html import escape
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile
import threading


TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "export" / "index.html"

# Serialise export creation so a browser download cannot read a ZIP while another phase is rebuilding it.
download_package_lock = threading.Lock()


def _markdown_to_html(markdown: str, title: str) -> str:
    """Render phase Markdown as a standalone HTML document."""

    lines = markdown.splitlines()
    rendered = []
    in_code = False
    code_lines: list[str] = []
    code_language = ""
    in_list = False
    in_table = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            rendered.append("</ul>")
            in_list = False

    def close_table() -> None:
        nonlocal in_table
        if in_table:
            rendered.append("</tbody></table>")
            in_table = False

    def inline(value: str) -> str:
        value = escape(value)
        value = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', value)
        value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
        value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
        return re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", value)

    def render_code_block() -> None:
        nonlocal code_lines, code_language
        code = "\n".join(code_lines)
        if code_language.lower() == "mermaid":
            rendered.append('<div class="mermaid">' + escape(code) + "</div>")
        else:
            language_class = f' class="language-{escape(code_language)}"' if code_language else ""
            rendered.append(f"<pre><code{language_class}>{escape(code)}</code></pre>")
        code_lines = []
        code_language = ""

    for line in lines:
        if line.startswith("```"):
            close_list()
            close_table()
            if in_code:
                render_code_block()
                in_code = False
            else:
                code_language = line[3:].strip()
                code_lines = []
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if line.startswith("|") and line.endswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if all(set(cell) <= {"-", ":", " "} for cell in cells):
                continue
            close_list()
            if not in_table:
                rendered.append("<table><tbody>")
                in_table = True
            rendered.append("<tr>" + "".join(f"<td>{inline(cell)}</td>" for cell in cells) + "</tr>")
            continue

        close_table()
        heading = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            rendered.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
        elif re.match(r"^\s*[-*]\s+", line):
            if not in_list:
                rendered.append("<ul>")
                in_list = True
            rendered.append("<li>" + inline(re.sub(r"^\s*[-*]\s+", "", line)) + "</li>")
        elif not line.strip():
            close_list()
        else:
            close_list()
            rendered.append(f"<p>{inline(line)}</p>")

    close_list()
    close_table()
    if in_code:
        render_code_block()

    body = "\n".join(rendered)
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{}</title>
<style>
body {{ margin:0; background:#f6f7f9; color:#1f2937; font-family:Arial,Helvetica,sans-serif; }}
main {{ max-width:900px; margin:0 auto; padding:40px 28px; background:#fff; min-height:100vh; }}
h1,h2,h3,h4,h5,h6 {{ line-height:1.25; margin-top:1.5em; }}
p,li {{ line-height:1.6; }}
table {{ border-collapse:collapse; margin:18px 0; width:100%; }}
td {{ border:1px solid #d1d5db; padding:8px; text-align:left; vertical-align:top; }}
pre {{ background:#111827; color:#f9fafb; overflow:auto; padding:16px; border-radius:8px; }}
code {{ background:#eef0f3; padding:2px 4px; border-radius:3px; }}
pre code {{ background:transparent; padding:0; }}
a {{ color:#2563eb; }}
.mermaid {{ overflow-x:auto; margin:24px 0; padding:12px; }}
</style>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
mermaid.initialize({{ startOnLoad:true, securityLevel:"loose", theme:"default" }});
</script>
</head>
<body><main>{}</main></body>
</html>
""".format(escape(title), body)


def _phase_display_name(phase_name: str) -> str:
    """Convert a phase directory name to a readable documentation title."""
    return phase_name.replace("-", " ").title()


def _render_index(work_dir: Path) -> str:
    """Render an index containing only completed, exported phase documents."""
    links = []
    for html_path in sorted(work_dir.glob("*.html")):
        if html_path.name == "index.html":
            continue
        phase_name = html_path.stem
        links.append(
            f'<a href="./{escape(html_path.name)}">'
            f"{escape(_phase_display_name(phase_name))}</a>"
        )
    documentation_links = "\n".join(links)
    return TEMPLATE_PATH.read_text(encoding="utf-8").replace(
        "{{DOCUMENTATION_LINKS}}",
        documentation_links,
    )


def create_download_package(work_dir: Path) -> Path:
    """Create and return a ZIP containing the completed documentation."""
    with download_package_lock:
        return _create_download_package(work_dir)


def _create_download_package(work_dir: Path) -> Path:
    """Create a package while the caller holds download_package_lock."""
    if not work_dir.exists() or not work_dir.is_dir():
        raise FileNotFoundError(f"Analysis work directory does not exist: {work_dir}")

    if not TEMPLATE_PATH.exists() or not TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Export template does not exist: {TEMPLATE_PATH}")

    index_path = work_dir / "index.html"

    # The index is generated from files already present in the export directory.
    # Its links are always relative so the ZIP remains portable after extraction.
    index_path.write_text(_render_index(work_dir), encoding="utf-8")

    for phase_dir in work_dir.iterdir():
        if not phase_dir.is_dir():
            continue
        source_path = phase_dir / "raw.md"
        if not source_path.is_file():
            continue

        markdown_path = work_dir / f"{phase_dir.name}.md"
        markdown = source_path.read_text(encoding="utf-8")
        markdown_path.write_text(markdown, encoding="utf-8")

        html_path = work_dir / f"{phase_dir.name}.html"
        html_path.write_text(_markdown_to_html(markdown, phase_dir.name), encoding="utf-8")

    # Regenerate the index after phase HTML files are created so it reflects
    # the exact set of documents included in this package.
    index_path.write_text(_render_index(work_dir), encoding="utf-8")

    zip_path = work_dir / "financial-analysis.zip"
    temp_zip_path = work_dir / ".financial-analysis.zip.tmp"
    if temp_zip_path.exists():
        temp_zip_path.unlink()

    with ZipFile(temp_zip_path, "w", compression=ZIP_DEFLATED) as archive:
        archive.write(index_path, "index.html")
        # for markdown_path in sorted(work_dir.glob("*.md")):
        #     archive.write(markdown_path, markdown_path.name)
        for html_path in sorted(work_dir.glob("*.html")):
            if html_path.name != "index.html":
                archive.write(html_path, html_path.name)

    temp_zip_path.replace(zip_path)
    return zip_path
