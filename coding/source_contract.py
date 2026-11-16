"""Bind a complete model response to one application-selected target file."""
import ast,re
from pathlib import Path
from coding.blocks import parse_file_blocks,safe_path
from coding.quality import source_check


def source_content(text,target):
    safe_path(target)
    if not isinstance(text,str) or len(text.encode('utf-8'))>256000:raise ValueError('Invalid source size')
    clean=re.sub(r'^\s*<think>[\s\S]*?</think>\s*','',text,count=1).strip()
    if re.search(r'^\s*###\s*FILE:',clean,re.M|re.I):
        blocks,incomplete=parse_file_blocks(clean,max_files=1)
        if incomplete or len(blocks)!=1 or blocks[0]['path']!=target:raise ValueError('Incomplete or wrong target FILE block')
        content=blocks[0]['content']
    elif clean.startswith(('```','~~~')):
        lines=clean.splitlines(keepends=True)
        marker=re.match(r'^(`{3,}|~{3,})[^\r\n]*$',lines[0].strip()).group(1)
        close=next((i for i,line in enumerate(lines[1:],1)
                    if re.fullmatch(re.escape(marker[0])+r'{'+str(len(marker))+r',}',line.strip())),None)
        if close is None or any(line.strip() for line in lines[close+1:]):
            raise ValueError('Expected one complete source fence without trailing text')
        content=''.join(lines[1:close])
    else:
        if Path(target).suffix.lower() not in {'.py','.json','.toml','.yaml','.yml','.md','.txt'}:
            raise ValueError('Use a complete source code fence')
        content=clean+'\n'
        if target.endswith('.py'):
            try:parsed=ast.parse(content)
            except SyntaxError as exc:raise ValueError('Invalid Python source: '+str(exc)) from exc
            if not parsed.body or all(isinstance(n,ast.Expr) and isinstance(n.value,(ast.Name,ast.Constant)) for n in parsed.body):
                raise ValueError('Response is prose, not substantive Python source')
    if not content.strip():raise ValueError('Empty source')
    report=source_check(target,content)
    if not report['valid']:raise ValueError('Invalid source: '+str(report['errors'])[:260])
    return content


def source_prefix(text,target):
    """Display actual received characters only; incomplete output remains untrusted."""
    if '<think>' in text and '</think>' not in text:return ''
    clean=re.sub(r'^\s*<think>[\s\S]*?</think>\s*','',text,count=1)
    if '###' in clean or clean.lstrip().startswith(('```','~~~')):
        try:
            wrapped=clean if '###' in clean else '### FILE: '+target+'\n'+clean
            blocks,_=parse_file_blocks(wrapped,max_files=1)
            if len(blocks)!=1 or blocks[0]['path']!=target:return ''
            code=blocks[0]['content']
            lines=code.splitlines(keepends=True)
            if lines and lines[-1].strip() in {'`','``','~','~~'}:code=''.join(lines[:-1])
            return code
        except ValueError:return ''
    return clean
