"""Low-cost, read-only symbol outline for permitted workspace source files.

Never imports/runs code. This helps the agent choose a smaller relevant file section
before spending cloud quota. All returned text is bounded, with no function bodies.
"""
import ast
import re
from pathlib import Path
from workspace.manager import read_text

_MAX_SYMBOLS = 120
_JS_DECL = re.compile(
    r'^\s*(?:export\s+)?(?:default\s+)?(?:async\s+)?'
    r'(?:(?:function|class|interface|type|enum)\s+([A-Za-z_$][\w$]*)|'
    r'(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=)', re.M
)


def outline(workspace: str, path: str) -> dict:
    """Extract source structure, not source contents, without executing any code."""
    content = read_text(workspace, path)
    ext = Path(path).suffix.lower()
    records = []
    imports = []
    truncated = False
    if ext == '.py':
        try:
            tree = ast.parse(content, filename=path)
        except SyntaxError as exc:
            return {'path':path, 'symbols':[], 'imports':[],
                    'syntax_error':f'{exc.msg} (line {exc.lineno})', 'truncated':False}

        def inspect(body, prefix='', depth=0):
            nonlocal truncated
            for node in body:
                if len(records) >= _MAX_SYMBOLS:
                    truncated = True
                    return
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = ('class' if isinstance(node, ast.ClassDef) else
                            'async function' if isinstance(node, ast.AsyncFunctionDef) else 'function')
                    records.append({'name':prefix+node.name, 'kind':kind,
                                    'line':node.lineno, 'end_line':getattr(node,'end_lineno',node.lineno)})
                    # Only descend into class methods, not nested function closures.
                    if isinstance(node, ast.ClassDef) and depth < 3:
                        inspect(node.body, prefix+node.name+'.', depth+1)
                elif not prefix and isinstance(node, ast.Import):
                    imports.extend(alias.name.split('.')[0] for alias in node.names)
                elif not prefix and isinstance(node, ast.ImportFrom):
                    if node.module:imports.append(node.module.split('.')[0])
        inspect(tree.body)
    elif ext in {'.js','.jsx','.ts','.tsx','.vue','.svelte'}:
        for match in _JS_DECL.finditer(content):
            if len(records) >= _MAX_SYMBOLS:
                truncated = True
                break
            records.append({'name':match.group(1) or match.group(2),
                            'kind':'declaration',
                            'line':content.count('\n',0,match.start())+1})
    else:
        raise ValueError('Symbol outline supports Python, JavaScript and TypeScript sources only')
    return {'path':path, 'symbols':records, 'imports':sorted(set(imports))[:60],
            'syntax_error':None, 'truncated':truncated}
