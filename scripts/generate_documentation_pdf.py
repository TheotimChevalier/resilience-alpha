#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, ListFlowable


def strip_markdown_links(text: str) -> str:
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", text)


def clean_line(line: str) -> str:
    return strip_markdown_links(line).strip()


def build_story(markdown_path: Path):
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "h1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=26,
        textColor=colors.HexColor("#0F172A"),
        spaceAfter=12,
        borderPadding=4,
    )
    h2 = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=colors.HexColor("#1F2937"),
        spaceBefore=12,
        spaceAfter=8,
    )
    normal = ParagraphStyle(
        "normal",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        firstLineIndent=0,
    )
    code_style = ParagraphStyle(
        "code",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=8.5,
        leading=10,
        leftIndent=10,
        borderPadding=4,
        backColor=colors.HexColor("#F8FAFC"),
        borderColor=colors.HexColor("#CBD5E1"),
        borderWidth=0.5,
        borderPaddingLeft=6,
        borderPaddingRight=6,
        borderPaddingTop=6,
        borderPaddingBottom=6,
    )

    story = []
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    paragraph_buffer = []
    list_items = []
    code_buffer = []
    in_code_block = False

    def flush_paragraph():
        if paragraph_buffer:
            text = " ".join(clean_line(part) for part in paragraph_buffer if clean_line(part))
            if text:
                story.append(Paragraph(text, normal))
                story.append(Spacer(1, 6))
            paragraph_buffer.clear()

    def flush_list():
        if list_items:
            story.append(ListFlowable([Paragraph(item, normal) for item in list_items], bulletType="bullet", bulletFontName="Helvetica", leftIndent=18, bulletOffsetY=0, spacing=6))
            story.append(Spacer(1, 6))
            list_items.clear()

    def flush_code():
        if code_buffer:
            code_text = "\n".join(code_buffer)
            story.append(Preformatted(code_text, code_style))
            story.append(Spacer(1, 8))
            code_buffer.clear()

    for raw in lines:
        line = raw.rstrip()
        if line.startswith("```"):
            flush_paragraph()
            flush_list()
            if in_code_block:
                flush_code()
                in_code_block = False
            else:
                in_code_block = True
            continue
        if in_code_block:
            code_buffer.append(line)
            continue
        if re.match(r"^# ", line):
            flush_paragraph()
            flush_list()
            story.append(Paragraph(clean_line(line[2:]), h1))
            continue
        if re.match(r"^## ", line):
            flush_paragraph()
            flush_list()
            story.append(Paragraph(clean_line(line[3:]), h2))
            continue
        if re.match(r"^- ", line):
            flush_paragraph()
            list_items.append(clean_line(line[2:]))
            continue
        if re.match(r"^\d+\. ", line):
            flush_paragraph()
            list_items.append(f"{clean_line(line)}")
            continue
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue
        paragraph_buffer.append(line)

    flush_paragraph()
    flush_list()
    flush_code()
    return story


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a consolidated Markdown documentation file to a PDF.")
    parser.add_argument("input", type=Path, help="Markdown file to render")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output PDF path")
    args = parser.parse_args()

    output = args.output or args.input.with_suffix(".pdf")
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
    )
    story = build_story(args.input)
    doc.build(story)
    print(f"PDF generated: {output}")


if __name__ == "__main__":
    main()
