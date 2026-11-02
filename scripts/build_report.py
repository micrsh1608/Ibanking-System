"""Render the editable Markdown report into a Vietnamese PDF.

Optional authoring dependencies: reportlab, pypdf. Application runtime is unchanged.
Set IBANKING_REPORT_FONT_DIR if Arial is stored outside C:/Windows/Fonts.
"""
import json
import os
import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image, Preformatted, KeepTogether

ROOT = Path(__file__).resolve().parents[1]
FONT = Path(os.getenv('IBANKING_REPORT_FONT_DIR', 'C:/Windows/Fonts'))
for name, file in [('Arial', 'arial.ttf'), ('Arial-Bold', 'arialbd.ttf'), ('Arial-Italic', 'ariali.ttf')]:
    pdfmetrics.registerFont(TTFont(name, str(FONT / file)))
pdfmetrics.registerFontFamily('Arial', normal='Arial', bold='Arial-Bold', italic='Arial-Italic', boldItalic='Arial-Bold')
team = json.loads((ROOT / 'docs/team.json').read_text(encoding='utf8'))
release = json.loads((ROOT / 'artifacts/release-acceptance-latest.json').read_text(encoding='utf8'))
assert release['status'] == 'PASS', 'Do not publish a report before release acceptance passes'
load = release['load']
tokens = {'COURSE': team['course'], 'GROUP': team['group'], 'LECTURER': team['lecturer'], 'PROJECT': release['project'], 'RUN': release['run_id'],
    **{key: str(load[value]) for key, value in {'PAYMENTS':'payments','WORKERS':'workers','INVOICES':'invoices','P50':'p50_seconds','P95':'p95_seconds','MAX':'max_seconds','CONVERGENCE':'convergence_seconds'}.items()}}
for i, member in enumerate(team['members'], 1):
    tokens[f'MEMBER{i}'], tokens[f'ID{i}'] = member['name'], member['student_id']
source = (ROOT / 'docs/final-report.md').read_text(encoding='utf8')
for token, value in tokens.items():
    source = source.replace('{{' + token + '}}', value)
assert not re.search(r'\{\{[A-Z0-9]+\}\}', source)
out = ROOT / 'submission'
out.mkdir(exist_ok=True)
(out / 'bao-cao-ibanking.md').write_text(source.replace('(diagrams/exported/', '(../docs/diagrams/exported/'), encoding='utf8')
styles = {
    'body': ParagraphStyle('Body', fontName='Arial', fontSize=11, leading=15.2, spaceAfter=8, textColor=colors.HexColor('#172B27'), splitLongWords=True),
    'title': ParagraphStyle('Title', fontName='Arial-Bold', fontSize=25, leading=32, spaceAfter=28, textColor=colors.black, alignment=TA_CENTER),
    'heading': ParagraphStyle('Heading', fontName='Arial-Bold', fontSize=16, leading=22, spaceAfter=14, textColor=colors.black, keepWithNext=True),
    'cell': ParagraphStyle('Cell', fontName='Arial', fontSize=9.4, leading=12.2, spaceAfter=0),
    'headcell': ParagraphStyle('Headcell', fontName='Arial-Bold', fontSize=9.4, leading=12.2, textColor=colors.white),
    'code': ParagraphStyle('Code', fontName='Arial', fontSize=9, leading=12, spaceBefore=6, spaceAfter=10),
}
story = []
lines = source.splitlines()
i = 0
def inline(value):
    return escape(value).replace('`','')

while i < len(lines):
    line = lines[i].strip()
    if not line:
        i += 1
        continue
    if line == '---':
        story.append(PageBreak()); i += 1; continue
    if line.startswith('# '):
        story += [Spacer(1,30), Paragraph(inline(line[2:]), styles['title'])]; i += 1; continue
    if line.startswith('## '):
        story.append(Paragraph(inline(line[3:]),styles['heading'])); i += 1; continue
    if line.startswith('!['):
        image_path = re.search(r'\]\((.*?)\)',line).group(1)
        image_path = (ROOT/'docs'/image_path).resolve()
        w,h = ImageReader(str(image_path)).getSize()
        target = min(504/w, 300/h)
        story += [Image(str(image_path),width=w*target,height=h*target),Spacer(1,12)]
        i += 1; continue
    if line.startswith('```'):
        block=[]; i += 1
        while i < len(lines) and not lines[i].startswith('```'):
            block.append(lines[i]); i += 1
        story.append(Preformatted('\n'.join(block),styles['code'],maxLineLength=100)); i += 1; continue
    if line.startswith('|'):
        matrix=[]
        while i < len(lines) and lines[i].strip().startswith('|'):
            row=[cell.strip() for cell in lines[i].strip().strip('|').split('|')]
            if not all(re.fullmatch(r'[: -]+',cell) for cell in row): matrix.append(row)
            i += 1
        n=len(matrix[0]); widths=([180,324] if n==2 else [185,143,176])
        if matrix[0][0]=='Thành viên': widths=[62,300,142]
        cells=[[Paragraph(inline(cell),styles['headcell' if r==0 else 'cell']) for cell in row] for r,row in enumerate(matrix)]
        table=Table(cells,colWidths=widths,repeatRows=1,hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#304B44')),('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.45,colors.HexColor('#C5D0CD')),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F1F5F3')])]))
        story += [table,Spacer(1,12)]; continue
    if line.startswith('- '):
        story.append(Paragraph('• '+inline(line[2:]),styles['body'])); i += 1; continue
    paragraph=[line]; i += 1
    while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','![','```','---','- ')):
        paragraph.append(lines[i].strip()); i += 1
    story.append(Paragraph(inline(' '.join(paragraph)),styles['body']))

def decorate(canvas, doc):
    canvas.saveState()
    if doc.page > 1:
        canvas.setFont('Arial',8.5); canvas.setFillColor(colors.HexColor('#526A64'))
        canvas.drawString(54,758,'NHÓM 12  |  KIẾN TRÚC HƯỚNG DỊCH VỤ')
        canvas.setStrokeColor(colors.HexColor('#D1DBD7')); canvas.line(54,748,558,748)
    canvas.setFont('Arial',9); canvas.setFillColor(colors.HexColor('#526A64'))
    canvas.drawString(54,34,'iBanking — Phân hệ đóng học phí')
    canvas.drawRightString(558,34,str(doc.page)); canvas.restoreState()

pdf = out/'bao-cao-ibanking.pdf'
SimpleDocTemplate(str(pdf),pagesize=(612,792),rightMargin=54,leftMargin=54,topMargin=58,bottomMargin=54,title='Nhóm 12 — Phân hệ đóng học phí iBanking',author='Nhóm 12',allowSplitting=True).build(story,onFirstPage=decorate,onLaterPages=decorate)
from pypdf import PdfReader
reader=PdfReader(str(pdf))
assert all(page.extract_text().strip() for page in reader.pages)
assert '524H009' in reader.pages[0].extract_text()
print(json.dumps({'pdf':str(pdf),'pages':len(reader.pages),'release_run':release['run_id']},ensure_ascii=False))
