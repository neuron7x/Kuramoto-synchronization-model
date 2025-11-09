"""Render markdown reports into HTML and PDF formats."""

from __future__ import annotations

import html
import textwrap
from pathlib import Path


def render_markdown_to_html(markdown: str, output_path: Path) -> None:
    """Persist a very small HTML representation of the markdown payload."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    escaped = html.escape(markdown.strip())
    body = f"<pre>{escaped}</pre>" if escaped else "<pre></pre>"
    html_doc = "\n".join(
        [
            "<!doctype html>",
            '<html lang="en">',
            "<head>",
            '  <meta charset="utf-8">',
            "  <title>TradePulse Report</title>",
            "  <style>body{font-family:Arial, sans-serif;} pre{white-space:pre-wrap;}</style>",
            "</head>",
            "<body>",
            body,
            "</body>",
            "</html>",
        ]
    )
    output_path.write_text(html_doc, encoding="utf-8")


def render_markdown_to_pdf(markdown: str, output_path: Path) -> None:
    """Create a very small PDF containing the markdown as preformatted text."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for line in markdown.splitlines():
        wrapped = textwrap.wrap(line, width=90) or [""]
        lines.extend(wrapped)
    if not lines:
        lines = [""]

    def _escape_pdf(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    cursor_y = 780
    line_height = 14
    stream_parts = ["BT", "/F1 12 Tf"]
    for entry in lines:
        stream_parts.append(f"1 0 0 1 72 {cursor_y} Tm ({_escape_pdf(entry)}) Tj")
        cursor_y -= line_height
    stream_parts.append("ET")
    stream = ("\n".join(stream_parts) + "\n").encode("utf-8")

    content = (
        b"<< /Length "
        + str(len(stream)).encode("ascii")
        + b" >>\nstream\n"
        + stream
        + b"endstream"
    )
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        content,
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    buffer = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(buffer))
        buffer.extend(f"{index} 0 obj\n".encode("ascii"))
        buffer.extend(obj)
        buffer.extend(b"\nendobj\n")

    startxref = len(buffer)
    buffer.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for offset in offsets[1:]:
        buffer.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    buffer.extend(b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n")
    buffer.extend(str(startxref).encode("ascii"))
    buffer.extend(b"\n%%EOF\n")

    output_path.write_bytes(buffer)
