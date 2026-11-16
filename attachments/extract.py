"""Bounded text extraction for user-selected attachments. Nothing persists on upload."""
import io
from pathlib import Path

MAX_UPLOAD=10*1024*1024
MAX_TEXT=50000
SUPPORTED={'.txt','.md','.py','.js','.ts','.jsx','.tsx','.json','.yaml','.yml','.csv','.log','.html','.css','.sql','.pdf','.docx','.xlsx'}

def extract(name,blob):
    ext=Path(name).suffix.lower()
    if ext not in SUPPORTED:raise ValueError('Unsupported attachment format')
    if not blob or len(blob)>MAX_UPLOAD:raise ValueError('Attachment must be 1 byte to 10 MB')
    if ext=='.pdf':
        try:
            import fitz
        except ImportError as exc:raise ValueError('PDF reading dependency PyMuPDF is missing') from exc
        with fitz.open(stream=blob,filetype='pdf') as doc:
            pages=[]
            for page in list(doc)[:60]:
                pages.append(page.get_text('text'))
                if sum(map(len,pages))>MAX_TEXT:break
            result='\n'.join(pages)
    elif ext=='.docx':
        try:from docx import Document
        except ImportError as exc:raise ValueError('DOCX reading dependency python-docx is missing') from exc
        d=Document(io.BytesIO(blob));result='\n'.join(p.text for p in d.paragraphs)
        for table in d.tables:
            result+='\n'+'\n'.join(' | '.join(c.text for c in row.cells) for row in table.rows)
    elif ext=='.xlsx':
        try:from openpyxl import load_workbook
        except ImportError as exc:raise ValueError('Excel reading dependency openpyxl is missing') from exc
        book=load_workbook(io.BytesIO(blob),read_only=True,data_only=True)
        lines=[]
        for sheet in book.worksheets[:10]:
            lines.append('Sheet: '+sheet.title)
            for row in sheet.iter_rows(max_row=2000,max_col=30,values_only=True):
                lines.append(' | '.join('' if v is None else str(v) for v in row))
                if sum(map(len,lines))>MAX_TEXT:break
            if sum(map(len,lines))>MAX_TEXT:break
        book.close();result='\n'.join(lines)
    else:
        try:result=blob.decode('utf-8-sig')
        except UnicodeDecodeError:raise ValueError('Only UTF-8 text attachments supported')
    result=result[:MAX_TEXT]
    if not result.strip():raise ValueError('No extractable text found (scanned PDFs require separate OCR)')
    return {'filename':Path(name).name[:120],'text':result,'truncated':len(result)>=MAX_TEXT,'length':len(result)}
