"""Render the reviewed Markdown proposal as a printable PDF."""
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate

ROOT = Path(__file__).resolve().parents[1]


def inline(text):
    text = html.escape(text)
    return re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="#184f76">\1</link>', text)


def footer(canvas, document):
    canvas.setFont("Times-Roman", 9)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawString(44, 26, "ParityLab | Project proposal")
    canvas.drawRightString(A4[0] - 44, 26, str(document.page))


def build():
    output = ROOT / "output/pdf/proposal-2020-2026.pdf"
    output.parent.mkdir(parents=True, exist_ok=True)
    body = ParagraphStyle("Body", fontName="Times-Roman", fontSize=11, leading=14.3,
                          spaceAfter=7, alignment=TA_JUSTIFY)
    heading = ParagraphStyle("Section", fontName="Times-Bold", fontSize=12, leading=15,
                             spaceBefore=10, spaceAfter=6, keepWithNext=True)
    title = ParagraphStyle("ProposalTitle", fontName="Times-Bold", fontSize=15, leading=18,
                           alignment=TA_CENTER, spaceAfter=9)
    meta = ParagraphStyle("Meta", parent=body, alignment=0, spaceAfter=4)
    citation = ParagraphStyle("Citation", parent=body, fontSize=9.7, leading=12.5, alignment=0)
    bullet = ParagraphStyle("Bullet", parent=body, leftIndent=12, firstLineIndent=-12)
    flow = []
    references = False
    for block in (ROOT / "docs/proposal.md").read_text(encoding="utf-8").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("# "):
            flow.append(Paragraph(inline(block[2:]), title))
        elif block.startswith("## "):
            references = block.startswith("## References")
            if references:
                flow.append(PageBreak())
            flow.append(Paragraph(inline(block[3:]), heading))
        elif block.startswith("- ") or re.match(r"\d+\. ", block):
            for line in block.splitlines():
                flow.append(Paragraph(inline(line.removeprefix("- ")), bullet, bulletText="-" if line.startswith("- ") else None))
        elif references:
            flow.append(Paragraph(inline(block), citation))
        elif block.startswith(("Author:",)):
            flow.append(Paragraph(inline(block), meta))
        else:
            flow.append(Paragraph(inline(block), body))
    document = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=44, leftMargin=44,
                                 topMargin=38, bottomMargin=43,
                                 title="Loss-Adaptive Packet-Level Parity FEC with Selective Repeat ARQ",
                                 author="A Aswanth Raj")
    document.build(flow, onFirstPage=footer, onLaterPages=footer)
    print(output)


if __name__ == "__main__":
    build()

