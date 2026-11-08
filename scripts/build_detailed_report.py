"""Build the detailed A4 report from Markdown and selected JSON evidence.

Optional authoring dependencies: reportlab, pypdf. No application/database calls.
Works in the workspace and in the filtered submission's MaNguon directory.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, Image, KeepTogether,
    LongTable, PageBreak, PageTemplate, Paragraph, Preformatted, Spacer, Table, TableStyle)
from reportlab.platypus.tableofcontents import TableOfContents
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]
INK=colors.HexColor('#183944')
MUTED=colors.HexColor('#53636b')
LINE=colors.HexColor('#d3dcdf')
PALE=colors.HexColor('#f0f5f7')
WIDTH,HEIGHT=A4
LEFT,RIGHT,TOP,BOTTOM=23*mm,19*mm,20*mm,18*mm
CONTENT=WIDTH-LEFT-RIGHT


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def evidence_summary(directory):
    path=directory/'acceptance-summary.json'
    if path.exists():
        data=read_json(path)
        assert data['status']=='PASS'
        return data
    final=read_json(directory/'final-delivery-acceptance.json')
    release=read_json(directory/'release-acceptance-latest.json')
    assert final['status']=='PASS' and release['status']=='PASS'
    return {'status':'PASS','evidence_date':'2026-11-05','release_run':release['run_id'],
        'release_project':release['project'],'release_image_id':release['image_id'],
        'clean_image_build':release['clean_image_build'],'tests':final['tests'],
        'load':release['load'],
        'scope':'Existing runtime acceptance; reporting/packaging does not rerun financial fault tests.',
        'notes':['Local transaction plus durable saga; no cross-service ACID claim.',
                 'SMTP is at-least-once; duplicate messages remain possible after lost ACK.',
                 'Request correlation is not full W3C/OpenTelemetry tracing.',
                 'Two member identities and actual work allocation remain to be filled by the team.']}


def register_fonts():
    directory=Path(os.getenv('IBANKING_REPORT_FONT_DIR','C:/Windows/Fonts'))
    choices=[(directory,('times.ttf','timesbd.ttf','timesi.ttf','timesbi.ttf')),
        (Path('/usr/share/fonts/truetype/dejavu'),('DejaVuSerif.ttf','DejaVuSerif-Bold.ttf','DejaVuSerif-Italic.ttf','DejaVuSerif-BoldItalic.ttf'))]
    for folder,names in choices:
        if all((folder/name).is_file() for name in names):
            for font,name in zip(('Report','Report-Bold','Report-Italic','Report-BoldItalic'),names):
                pdfmetrics.registerFont(TTFont(font,str(folder/name)))
            pdfmetrics.registerFontFamily('Report',normal='Report',bold='Report-Bold',italic='Report-Italic',boldItalic='Report-BoldItalic')
            return
    raise RuntimeError('Set IBANKING_REPORT_FONT_DIR to a folder containing the Times New Roman font files.')


def inline(text):
    text=escape(text)
    text=re.sub(r'\*\*(.+?)\*\*',r'<b>\1</b>',text)
    text=re.sub(r'`(.+?)`',r'<font name="Courier" size="9">\1</font>',text)
    text=re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',r'<link href="\2" color="#225c77">\1</link>',text)
    return text


class ReportDoc(BaseDocTemplate):
    def __init__(self,path,**options):
        super().__init__(str(path),pagesize=A4,leftMargin=LEFT,rightMargin=RIGHT,
            topMargin=TOP,bottomMargin=BOTTOM,allowSplitting=True,**options)
        frame=Frame(LEFT,BOTTOM,CONTENT,HEIGHT-TOP-BOTTOM,id='body',leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        self.addPageTemplates(PageTemplate(id='report',frames=[frame],onPage=self.decorate))

    def decorate(self,canvas,doc):
        canvas.saveState()
        if doc.page>1:
            canvas.setFont('Report',9)
            canvas.setFillColor(MUTED)
            canvas.drawString(LEFT,HEIGHT-12*mm,'NHÓM 12  -  KIẾN TRÚC HƯỚNG DỊCH VỤ')
            canvas.drawString(LEFT,10*mm,'Phân hệ đóng học phí qua iBanking')
            canvas.drawRightString(WIDTH-RIGHT,10*mm,str(doc.page))
        canvas.restoreState()

    def afterFlowable(self,flowable):
        if isinstance(flowable,Paragraph) and hasattr(flowable,'toc_key'):
            text=flowable.getPlainText()
            self.canv.bookmarkPage(flowable.toc_key)
            self.canv.addOutlineEntry(text,flowable.toc_key,level=0,closed=False)
            self.notify('TOCEntry',(0,text,self.page,flowable.toc_key))


def build(args):
    register_fonts()
    source_path=(ROOT/args.source).resolve()
    evidence=(ROOT/args.evidence).resolve()
    output=(ROOT/args.output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    summary=evidence_summary(evidence)
    team=read_json(ROOT/'docs/team.json')
    tokens={'COURSE':team['course'],'GROUP':team['group'],'LECTURER':team['lecturer'],
            'RUN':summary['release_run'],'PROJECT':summary['release_project']}
    tokens.update({key.upper():str(value) for key,value in summary['tests'].items()})
    for key in ('payments','workers','invoices','p50_seconds','p95_seconds','max_seconds','convergence_seconds'):
        tokens[key.upper()]=str(summary['load'][key])
    source=source_path.read_text(encoding='utf-8')
    for key,value in tokens.items():
        source=source.replace('{{'+key+'}}',value)
    assert not re.search(r'\{\{[A-Z0-9_]+\}\}',source), 'Unresolved content token'
    styles={
        'body':ParagraphStyle('Body',fontName='Report',fontSize=12,leading=15.4,spaceAfter=7,alignment=TA_JUSTIFY,textColor=colors.black,splitLongWords=True),
        'h1':ParagraphStyle('Chapter',fontName='Report-Bold',fontSize=17,leading=21,spaceAfter=14,keepWithNext=True,textColor=INK),
        'h2':ParagraphStyle('Subheading',fontName='Report-Bold',fontSize=12.5,leading=16,spaceBefore=8,spaceAfter=5,keepWithNext=True),
        'note':ParagraphStyle('Note',fontName='Report-Italic',fontSize=10,leading=13,spaceAfter=8,textColor=MUTED),
        'cell':ParagraphStyle('Cell',fontName='Report',fontSize=10,leading=12.1,spaceAfter=0,splitLongWords=True),
        'headcell':ParagraphStyle('Headcell',fontName='Report-Bold',fontSize=10,leading=12.5,spaceAfter=0,textColor=colors.white),
        'caption':ParagraphStyle('Caption',fontName='Report-Italic',fontSize=10,leading=12.5,alignment=TA_CENTER,spaceBefore=4,spaceAfter=10),
        'code':ParagraphStyle('Code',fontName='Courier',fontSize=8.4,leading=11.3,spaceBefore=4,spaceAfter=10,leftIndent=8,rightIndent=8),
    }
    story=[]
    centered=ParagraphStyle('Center',parent=styles['body'],alignment=TA_CENTER)
    cover_title=ParagraphStyle('CoverTitle',fontName='Report-Bold',fontSize=25,leading=32,alignment=TA_CENTER,spaceAfter=20)
    story+=[Spacer(1,13*mm),Paragraph('TRƯỜNG ĐẠI HỌC TÔN ĐỨC THẮNG',centered),
        Paragraph('KHOA CÔNG NGHỆ THÔNG TIN',centered),Spacer(1,25*mm),
        Paragraph('BÁO CÁO DỰ ÁN GIỮA KỲ',centered),Spacer(1,7*mm),
        Paragraph('PHÂN HỆ ĐÓNG HỌC PHÍ<br/>QUA ỨNG DỤNG IBANKING',cover_title),
        Paragraph('Môn học: '+escape(team['course']),centered),
        Paragraph('Giảng viên: '+escape(team['lecturer']),centered),
        Paragraph(escape(team['group']),centered),Spacer(1,11*mm)]
    members=[['STT','Họ và tên','MSSV']]+[[str(i),member['name'],member['student_id']] for i,member in enumerate(team['members'],1)]
    story.append(make_table(members,[35,CONTENT-145,110],styles))
    story+=[Spacer(1,17*mm),Paragraph('Học kỳ 1 - Năm học 2026-2027',centered),
        Paragraph('Thành phố Hồ Chí Minh, tháng 11 năm 2026',centered),PageBreak()]
    lines=source.splitlines();i=0;section=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith('# '):i+=1;continue
        if line=='---':story.append(PageBreak());i+=1;continue
        if line=='<!-- TOC -->':
            story.append(Paragraph('MỤC LỤC',styles['h1']))
            toc=TableOfContents()
            toc.levelStyles=[ParagraphStyle('TOC',fontName='Report',fontSize=10.8,leading=13.8,leftIndent=0,firstLineIndent=0,spaceBefore=0,textColor=colors.black)]
            toc.dotsMinLevel=0
            story.append(toc);i+=1;continue
        if line.startswith('## '):
            section+=1;p=Paragraph(inline(line[3:]),styles['h1']);p.toc_key='chapter_'+str(section);story.append(p);i+=1;continue
        if line.startswith('### '):story.append(Paragraph(inline(line[4:]),styles['h2']));i+=1;continue
        if line.startswith('!['):
            matches=re.findall(r'!\[([^\]]*)\]\(([^)]+)\)',line)
            images=[]
            max_width=CONTENT if len(matches)==1 else CONTENT*.5-6
            max_height=250 if len(matches)==1 else 245
            for caption,relative in matches:
                path=(source_path.parent/relative).resolve()
                if not path.exists() and relative.startswith('../artifacts/'):
                    path=evidence/Path(relative).name
                assert path.is_file(), str(path)
                w,h=ImageReader(str(path)).getSize();scale=min(max_width/w,max_height/h)
                image=Image(str(path),width=w*scale,height=h*scale)
                images.append([image,Spacer(1,4),Paragraph(inline(caption),styles['caption'])])
            if len(images)==1:story.append(KeepTogether(images[0]))
            else:
                table=Table([[images[0],images[1]]],colWidths=[CONTENT*.5]*2)
                table.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3)]))
                story.append(table)
            i+=1;continue
        if line.startswith('```'):
            code=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):code.append(lines[i]);i+=1
            story.append(Preformatted('\n'.join(code),styles['code'],maxLineLength=88));i+=1;continue
        if line.startswith('|'):
            matrix=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                row=[cell.strip() for cell in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r'[: -]+',cell) for cell in row):matrix.append(row)
                i+=1
            n=len(matrix[0]);ratios={2:[.32,.68],3:[.25,.35,.40],4:[.23,.20,.17,.40],5:[.08,.23,.20,.30,.19]}.get(n,[1/n]*n)
            assert all(len(row)==n for row in matrix),'Uneven table'
            story.append(make_table(matrix,[CONTENT*r for r in ratios],styles));story.append(Spacer(1,9));continue
        if line.startswith('> '):story.append(Paragraph(inline(line[2:]),styles['note']));i+=1;continue
        if line.startswith('- '):
            style=ParagraphStyle('Bullet',parent=styles['body'],leftIndent=12,firstLineIndent=-9,spaceAfter=5,alignment=TA_LEFT)
            story.append(Paragraph('• '+inline(line[2:]),style));i+=1;continue
        if re.match(r'^\d+\.\s+',line):
            style=ParagraphStyle('Numbered',parent=styles['body'],leftIndent=14,firstLineIndent=-14,spaceAfter=6,alignment=TA_LEFT)
            story.append(Paragraph(inline(line),style));i+=1;continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not lines[i].startswith(('#','|','![','```','---','- ','> ','<!--')):
            if re.match(r'^\d+\.\s+',lines[i]):break
            paragraph.append(lines[i].strip());i+=1
        style=styles['body']
        if re.match(r'^\[\d+\]',line):
            style=ParagraphStyle('Reference',parent=styles['body'],alignment=TA_LEFT)
        story.append(Paragraph(inline(' '.join(paragraph)),style))
    pdf=output/'bao-cao-ibanking-chi-tiet.pdf'
    doc=ReportDoc(pdf,title='Nhóm 12 - Phân hệ đóng học phí qua iBanking',author='Nhóm 12',subject='Phân tích, kiến trúc, API, dữ liệu, transaction và kiểm thử')
    doc.multiBuild(story)
    reader=PdfReader(pdf)
    text='\n'.join(page.extract_text() for page in reader.pages)
    assert '524H009' in reader.pages[0].extract_text() and 'ALL_UNPAID' in text
    assert all(page.extract_text().strip() for page in reader.pages)
    (output/'bao-cao-ibanking-chi-tiet.md').write_text(source,encoding='utf-8')
    summary.update(report_pages=len(reader.pages),report_source=str(source_path.relative_to(ROOT)),
        report_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        report_updated_at_utc=datetime.now(timezone.utc).isoformat())
    (evidence/'acceptance-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pdf':str(pdf),'pages':len(reader.pages),'outline_entries':len(reader.outline),'release':summary['release_run']},ensure_ascii=True))


def make_table(matrix,widths,styles):
    rows=[[Paragraph(inline(value),styles['headcell' if r==0 else 'cell']) for value in row] for r,row in enumerate(matrix)]
    table=LongTable(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),INK),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,PALE]),
        ('GRID',(0,0),(-1,-1),.35,LINE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
    return table


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',default='docs/final-report-detailed.md')
    parser.add_argument('--evidence',default='artifacts')
    parser.add_argument('--output',default='submission')
    build(parser.parse_args())
