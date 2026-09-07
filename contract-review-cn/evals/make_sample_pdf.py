"""Create a Chinese text-layer PDF from the C01 synthetic fixture."""
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from pypdf import PdfReader

root = Path(__file__).resolve().parent
output = root / "output/pdf/C01-purchase-sample.pdf"
output.parent.mkdir(parents=True, exist_ok=True)
font_path = os.environ.get("CONTRACT_SAMPLE_FONT", "/System/Library/Fonts/Supplemental/Arial Unicode.ttf")
pdfmetrics.registerFont(TTFont("SampleChinese", font_path))
style = ParagraphStyle("body", fontName="SampleChinese", fontSize=11, leading=19,
                       spaceAfter=12, alignment=TA_LEFT, wordWrap="CJK")
title = ParagraphStyle("title", parent=style, fontSize=17, leading=25, spaceAfter=18)
lines = (root / "inputs/C01.txt").read_text().splitlines()
story = [Paragraph(escape(lines[0]), title), Spacer(1, 8)]
story.extend(Paragraph(escape(line), style) for line in lines[1:])
SimpleDocTemplate(str(output), pagesize=(595.28, 841.89), leftMargin=48,
                  rightMargin=48, topMargin=45, bottomMargin=45,
                  title="C01 合成采购合同验收样例", author="Contract Review Test Fixture").build(story)
reader = PdfReader(output)
actual = "".join((page.extract_text() or "") for page in reader.pages)
normalize = lambda value: "".join(value.split())
if normalize(actual) != normalize("".join(lines)):
    raise RuntimeError("PDF_TEXT_MISMATCH")
print(f"PDF_OK pages={len(reader.pages)}")
