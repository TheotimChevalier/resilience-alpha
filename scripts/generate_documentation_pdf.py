#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    ListFlowable,
)


NAVY = colors.HexColor("#10233F")
BLUE = colors.HexColor("#2463A6")
PALE_BLUE = colors.HexColor("#EAF2FA")
PALE_GRAY = colors.HexColor("#F3F6F9")
INK = colors.HexColor("#243447")
MUTED = colors.HexColor("#607286")
TEAL = colors.HexColor("#168C91")


def inline_markup(text: str) -> str:
    text = escape(text.strip(), quote=False)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<font color="#2463A6">\1</font>', text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", text)
    return text


def architecture_diagram(styles, available_width):
    cell_style = ParagraphStyle(
        "architectureCell",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.3,
        leading=10.5,
        textColor=INK,
        alignment=1,
    )
    arrow_style = ParagraphStyle(
        "architectureArrow",
        parent=cell_style,
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=14,
        textColor=TEAL,
    )

    def cell(title, description, background=PALE_BLUE):
        content = Paragraph(
            f'<font color="#10233F"><b>{escape(title)}</b></font><br/>'
            f'<font color="#607286">{escape(description)}</font>',
            cell_style,
        )
        table = Table([[content]], colWidths=[available_width / 3 - 5], rowHeights=[43])
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), background),
                    ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#C9D7E5")),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        return table

    def row(items):
        return Table(
            [[cell(title, description, background) for title, description, background in items]],
            colWidths=[available_width / len(items)] * len(items),
            hAlign="LEFT",
        )

    arrow = Paragraph("↓", arrow_style)
    return [
        row(
            [
                ("PC Hôte", "Dashboard opérateur · port 8080", PALE_BLUE),
                ("Point d’entrée", "WAF OWASP CRS · port 80", PALE_BLUE),
                ("PC Attaquant autorisé", "Scénario d’exercice uniquement", PALE_BLUE),
            ]
        ),
        arrow,
        row(
            [
                ("Auth", "Identité, rôles et jetons · interne", PALE_GRAY),
                ("Payment API", "Paiements, santé, métriques · interne", PALE_GRAY),
                ("Agent caméra hôte", "Webcam USB + ESP8266 série", PALE_GRAY),
            ]
        ),
        arrow,
        row(
            [
                ("PostgreSQL", "Transactions · volume persistant", PALE_BLUE),
                ("Prometheus + AIOps", "Métriques → détection → reprise bornée", PALE_BLUE),
                ("Loki + Grafana", "Événements → journaux et tableaux de bord", PALE_BLUE),
            ]
        ),
        Spacer(1, 5),
        Paragraph(
            '<font color="#607286">Les services Docker communiquent sur le réseau '
            "Compose interne. Seuls le dashboard et le WAF sont publiés par défaut ; "
            "l’agent caméra reste sur le PC Hôte.</font>",
            cell_style,
        ),
    ]


def build_story(markdown_path: Path, available_width):
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "h1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=25,
        leading=29,
        textColor=NAVY,
        spaceBefore=2,
        spaceAfter=13,
    )
    cover_title = ParagraphStyle(
        "coverTitle",
        parent=h1,
        fontSize=34,
        leading=39,
        spaceBefore=35,
        spaceAfter=14,
    )
    h2 = ParagraphStyle(
        "h2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=17,
        textColor=BLUE,
        spaceBefore=9,
        spaceAfter=5,
        keepWithNext=True,
    )
    h3 = ParagraphStyle(
        "h3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=13,
        textColor=NAVY,
        spaceBefore=6,
        spaceAfter=3,
        keepWithNext=True,
    )
    normal = ParagraphStyle(
        "normal",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=12.4,
        textColor=INK,
        firstLineIndent=0,
        spaceAfter=5,
        splitLongWords=1,
    )
    code_style = ParagraphStyle(
        "code",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=7.4,
        leading=9.2,
        leftIndent=6,
        borderPadding=5,
        backColor=PALE_GRAY,
        borderColor=colors.HexColor("#D6E0E9"),
        borderWidth=0.5,
        borderPaddingLeft=7,
        borderPaddingRight=7,
        borderPaddingTop=6,
        borderPaddingBottom=6,
        splitLongWords=1,
    )
    list_style = ParagraphStyle(
        "listItem",
        parent=normal,
        spaceAfter=1,
    )
    table_header_style = ParagraphStyle(
        "tableHeader",
        parent=normal,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.white,
    )
    quote_style = ParagraphStyle(
        "quote",
        parent=normal,
        textColor=NAVY,
        backColor=PALE_BLUE,
        borderColor=TEAL,
        borderWidth=0,
        borderPadding=7,
        leftIndent=8,
        rightIndent=8,
        spaceBefore=4,
        spaceAfter=8,
    )

    story = []
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    paragraph_buffer = []
    list_items = []
    code_buffer = []
    table_lines = []
    in_code_block = False
    cover = True

    def flush_paragraph():
        if paragraph_buffer:
            text = " ".join(inline_markup(part) for part in paragraph_buffer if part.strip())
            if text:
                style = quote_style if paragraph_buffer[0].lstrip().startswith(">") else normal
                if style is quote_style:
                    text = " ".join(
                        inline_markup(part.lstrip()[1:].strip())
                        for part in paragraph_buffer
                    )
                story.append(Paragraph(text, style))
            paragraph_buffer.clear()

    def flush_list():
        if list_items:
            items = [Paragraph(item, list_style) for item in list_items]
            numbered = list_items[0].startswith("1. ")
            if numbered:
                items = [
                    Paragraph(re.sub(r"^\d+\. ", "", item), list_style)
                    for item in list_items
                ]
            story.append(
                ListFlowable(
                    items,
                    bulletType="1" if numbered else "bullet",
                    bulletFontName="Helvetica",
                    bulletFontSize=8,
                    leftIndent=17,
                    bulletOffsetY=0,
                    spaceAfter=4,
                )
            )
            list_items.clear()

    def flush_code():
        if code_buffer:
            code_text = "\n".join(code_buffer)
            story.append(Preformatted(code_text, code_style))
            story.append(Spacer(1, 8))
            code_buffer.clear()

    def flush_table():
        if not table_lines:
            return
        rows = [
            [cell.strip() for cell in row.strip("|").split("|")]
            for row in table_lines
        ]
        table_lines.clear()
        rows = [
            row
            for row in rows
            if not all(re.fullmatch(r":?-{3,}:?", cell) for cell in row)
        ]
        if not rows:
            return
        column_count = max(len(row) for row in rows)
        table_data = []
        for index, row in enumerate(rows):
            cell_style = table_header_style if index == 0 else normal
            table_data.append(
                [
                    Paragraph(inline_markup(cell), cell_style)
                    for cell in row + [""] * (column_count - len(row))
                ]
            )
        table = Table(
            table_data,
            colWidths=[available_width / column_count] * column_count,
            repeatRows=1,
            hAlign="LEFT",
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE_GRAY]),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D6E0E9")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.extend([table, Spacer(1, 6)])

    for raw in lines:
        line = raw.rstrip()
        if table_lines:
            if line.startswith("|") and line.endswith("|"):
                table_lines.append(line)
                continue
            flush_table()
        if line == "<!-- pagebreak -->":
            flush_paragraph()
            flush_list()
            flush_code()
            story.append(PageBreak())
            cover = False
            continue
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
            story.append(
                Paragraph(
                    inline_markup(line[2:]),
                    cover_title if cover else h1,
                )
            )
            continue
        if re.match(r"^## ", line):
            flush_paragraph()
            flush_list()
            story.append(Paragraph(inline_markup(line[3:]), h2))
            continue
        if re.match(r"^### ", line):
            flush_paragraph()
            flush_list()
            story.append(Paragraph(inline_markup(line[4:]), h3))
            continue
        if re.match(r"^[-*] ", line):
            flush_paragraph()
            list_items.append(inline_markup(line[2:]))
            continue
        if re.match(r"^\d+\. ", line):
            flush_paragraph()
            list_items.append(inline_markup(line))
            continue
        if line == "[[ARCHITECTURE_DIAGRAM]]":
            flush_paragraph()
            flush_list()
            story.extend(architecture_diagram(styles, available_width))
            story.append(Spacer(1, 8))
            continue
        if line.startswith("|") and line.endswith("|"):
            flush_paragraph()
            flush_list()
            table_lines.append(line)
            continue
        if not line.strip():
            flush_paragraph()
            flush_list()
            continue
        paragraph_buffer.append(line)

    flush_paragraph()
    flush_list()
    flush_code()
    flush_table()
    return story


def decorate_page(canvas, doc):
    canvas.saveState()
    width, height = A4
    if doc.page == 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, height - 8 * mm, width, 8 * mm, fill=1, stroke=0)
    else:
        canvas.setStrokeColor(colors.HexColor("#D6E0E9"))
        canvas.setLineWidth(0.6)
        canvas.line(doc.leftMargin, height - 12 * mm, width - doc.rightMargin, height - 12 * mm)
        canvas.setFont("Helvetica-Bold", 7.5)
        canvas.setFillColor(NAVY)
        canvas.drawString(doc.leftMargin, height - 9 * mm, "RESILIENCE ALPHA")
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawRightString(width - doc.rightMargin, height - 9 * mm, "DOSSIER TECHNIQUE")
        canvas.line(doc.leftMargin, 12 * mm, width - doc.rightMargin, 12 * mm)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawString(doc.leftMargin, 8 * mm, "Prototype de laboratoire · Données synthétiques")
        canvas.drawRightString(width - doc.rightMargin, 8 * mm, f"{doc.page:02d} / 12")
    canvas.restoreState()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a structured Markdown project dossier to a styled PDF."
    )
    parser.add_argument("input", type=Path, help="Markdown file to render")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output PDF path")
    args = parser.parse_args()

    output = args.output or args.input.with_suffix(".pdf")
    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=19 * mm,
        bottomMargin=18 * mm,
        title="Resilience Alpha — Dossier technique",
        author="Équipe Resilience Alpha",
        subject="Architecture, exploitation et résilience du démonstrateur",
    )
    story = build_story(args.input, doc.width)
    doc.build(story, onFirstPage=decorate_page, onLaterPages=decorate_page)
    print(f"PDF generated: {output}")


if __name__ == "__main__":
    main()
