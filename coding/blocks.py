"""Parse human-readable file proposals; parsing NEVER writes or approves files."""
import re
from pathlib import PurePosixPath

MAX_BLOCK_BYTES = 256_000
ALLOWED_EXTENSIONS = {'.py','.pyi','.ts','.tsx','.js','.jsx','.json','.html','.css',
                      '.scss','.md','.txt','.yaml','.yml','.toml','.ini','.cfg','.sh',
                      '.bat','.ps1','.sql','.svg','.xml','.gitignore'}
WINDOWS_RESERVED = {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),
                    *(f'LPT{i}' for i in range(1,10))}
HEADER = re.compile(r'^\s*###\s*FILE:\s*(.+?)\s*$',re.I)
FENCE = re.compile(r'^\s*(`{3,}|~{3,})([^\r\n]*)$')


def safe_path(raw):
    if not isinstance(raw,str) or not raw or len(raw)>240 or '\x00' in raw:
        raise ValueError('Invalid file path')
    if '\\' in raw or raw.startswith('/') or ':' in raw:
        raise ValueError('Absolute, Windows or device paths are forbidden')
    parts=raw.split('/')
    if any(p in ('','.','..') or p.rstrip(' .')!=p or p.split('.')[0].upper() in WINDOWS_RESERVED for p in parts):
        raise ValueError('Unsafe relative path')
    if PurePosixPath(raw).suffix.lower() not in ALLOWED_EXTENSIONS and raw not in ('.gitignore',):
        raise ValueError('Unsupported file extension')
    return raw


def parse_file_blocks(text, max_files=24):
    """Return (blocks, incomplete); never silently accept an unclosed fence."""
    if not isinstance(text,str) or len(text.encode('utf-8'))>MAX_BLOCK_BYTES*max_files:
        raise ValueError('Oversized model output')
    lines=text.replace('\r\n','\n').replace('\r','\n').splitlines(keepends=True)
    blocks=[]; incomplete=False; pos=0
    while pos<len(lines):
        header=HEADER.match(lines[pos].rstrip('\n'))
        if not header:
            pos+=1;continue
        path=safe_path(header.group(1).strip());pos+=1
        while pos<len(lines) and not FENCE.match(lines[pos].rstrip('\n')):
            if HEADER.match(lines[pos].rstrip('\n')):
                raise ValueError('Missing file content for '+path)
            pos+=1
        if pos==len(lines):
            raise ValueError('Missing code fence for '+path)
        marker=FENCE.match(lines[pos].rstrip('\n')).group(1);pos+=1
        content=[];closed=False
        while pos<len(lines):
            line=lines[pos];pos+=1
            if re.match(r'^\s*'+re.escape(marker[0])+r'{'+str(len(marker))+r',}\s*$',line.rstrip('\n')):
                closed=True;break
            content.append(line)
        data=''.join(content)
        if '\x00' in data or len(data.encode('utf-8'))>MAX_BLOCK_BYTES:
            raise ValueError('Invalid or oversized file content')
        if any(item['path']==path for item in blocks):
            raise ValueError('Duplicate path in generated reply')
        blocks.append({'path':path,'content':data,'truncated':not closed})
        if len(blocks)>max_files:raise ValueError('Too many files')
        if not closed:
            incomplete=True;break
    return blocks,incomplete


EDIT_RE=re.compile(r'^\s*###\s*EDIT:\s*(.+?)\s*$',re.I)

def parse_edit_blocks(text):
    """Parse exact SEARCH/REPLACE suggestions; do not perform fuzzy guessing."""
    lines=text.replace('\r\n','\n').replace('\r','\n').splitlines(keepends=True)
    edits=[];i=0
    while i<len(lines):
        match=EDIT_RE.match(lines[i].rstrip('\n'))
        if not match:i+=1;continue
        path=safe_path(match.group(1));i+=1
        if i>=len(lines) or lines[i].strip()!='<<<<<<< SEARCH':
            raise ValueError('Missing SEARCH marker')
        i+=1;old=[]
        while i<len(lines) and lines[i].strip()!='=======':
            old.append(lines[i]);i+=1
        if i==len(lines):raise ValueError('Missing edit separator')
        i+=1;new=[]
        while i<len(lines) and lines[i].strip()!='>>>>>>> REPLACE':
            new.append(lines[i]);i+=1
        if i==len(lines):raise ValueError('Missing REPLACE marker')
        i+=1
        before=''.join(old);after=''.join(new)
        if not before or len(before)+len(after)>MAX_BLOCK_BYTES:raise ValueError('Invalid edit size')
        edits.append({'path':path,'before':before,'after':after})
    return edits
