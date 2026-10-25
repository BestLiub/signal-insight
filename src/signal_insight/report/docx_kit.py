"""Word 报告的最小工具箱：python-docx 只在报告命令里用到（命令行按需 import）。"""
from pathlib import Path

from docx import Document
from docx.shared import Cm, Pt


def new_doc(title):
    doc = Document()
    doc.add_heading(title, level=0)
    return doc


def heading(doc, text, level=1):
    doc.add_heading(text, level=level)


def para(doc, text, size=10.5):
    p = doc.add_paragraph(text)
    for run in p.runs:
        run.font.size = Pt(size)
    return p


def bullets(doc, items):
    for x in items:
        doc.add_paragraph(str(x), style="List Bullet")


def table(doc, df, widths_cm=None):
    t = doc.add_table(rows=1, cols=len(df.columns))
    t.style = "Light Grid Accent 1"
    for j, c in enumerate(df.columns):
        t.rows[0].cells[j].text = str(c)
    for _, r in df.iterrows():
        cells = t.add_row().cells
        for j, c in enumerate(df.columns):
            cells[j].text = "" if r[c] is None else str(r[c])
    return t


def picture(doc, path, width_cm=16):
    path = Path(path)
    if path.exists():
        doc.add_picture(str(path), width=Cm(width_cm))
        return True
    return False


def save(doc, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return path
