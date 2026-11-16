"""Read-only project checks. Findings are evidence, never proof of completeness."""
import ast
from pathlib import PurePosixPath
from workspace.manager import read_text


def public_interfaces(source):
    """Small, actual callable contracts, without executing modules or function bodies."""
    try: tree=ast.parse(source)
    except (SyntaxError,ValueError):return []
    result=[]
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            result.append(node.name+'('+ast.unparse(node.args)+')')
        elif isinstance(node,ast.ClassDef):
            for method in node.body:
                if isinstance(method,(ast.FunctionDef,ast.AsyncFunctionDef)) and (not method.name.startswith('_') or method.name=='__init__'):
                    result.append(node.name+'.'+method.name+'('+ast.unparse(method.args)+')')
    return [value[:240] for value in result[:30]]


def _exports(tree):
    names=set()
    for node in tree.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            if node.name=='__getattr__':return None
            names.add(node.name)
        elif isinstance(node,(ast.Import,ast.ImportFrom)):
            for alias in node.names:
                if alias.name=='*':return None
                names.add(alias.asname or alias.name.split('.')[0])
        elif isinstance(node,(ast.Assign,ast.AnnAssign)):
            names.update(n.id for n in ast.walk(node) if isinstance(n,ast.Name) and isinstance(n.ctx,ast.Store))
        elif isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant):pass
        else:return None # Conditional/dynamic exports require a runtime test.
    return names


def review_project(workspace,mission):
    trees={};issues=[];warnings=[]
    def issue(path,line,code,message):
        issues.append({'path':path,'line':line,'code':code,'message':message})
    for row in mission['manifest']:
        path=row['path']
        if not path.endswith('.py'):continue
        try:trees[path]=ast.parse(read_text(workspace,path),filename=path)
        except (OSError,ValueError,SyntaxError) as exc:
            issue(path,getattr(exc,'lineno',1),'unreadable_source',str(exc)[:240])
    for path,tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and node.module and node.level==0:
                relative=node.module.replace('.','/')+'.py'
                candidates=[str(PurePosixPath(path).parent/relative),str(PurePosixPath(path).parts[0]+'/'+relative)]
                target=next((name for name in candidates if name in trees),None)
                exports=_exports(trees[target]) if target else None
                if exports is not None:
                    for alias in node.names:
                        if alias.name!='*' and alias.name not in exports:
                            issue(path,node.lineno,'missing_local_export',f'{target} does not export {alias.name}')
        if PurePosixPath(path).name.startswith('test_') or PurePosixPath(path).name.endswith('_test.py'):
            tests=[n for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')]
            for test in tests:
                body=[n for n in test.body if not (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and isinstance(n.value.value,str))]
                if not body or all(isinstance(n,ast.Pass) or (isinstance(n,ast.Expr) and isinstance(n.value,ast.Constant) and n.value.value is Ellipsis) for n in body):
                    issue(path,test.lineno,'empty_test',f'{test.name} has no executable checks')
                assertions=[n for n in ast.walk(test) if isinstance(n,ast.Assert)]
                calls=[n for n in ast.walk(test) if isinstance(n,ast.Call)]
                if assertions and all(isinstance(n.test,ast.Constant) and bool(n.test.value) for n in assertions) and not calls:
                    issue(path,test.lineno,'vacuous_test',f'{test.name} only asserts constant truth; test real behavior')
        else:
            for node in ast.walk(tree):
                if isinstance(node,ast.Raise) and ((isinstance(node.exc,ast.Name) and node.exc.id=='NotImplementedError') or (isinstance(node.exc,ast.Call) and isinstance(node.exc.func,ast.Name) and node.exc.func.id=='NotImplementedError')):
                    warnings.append({'path':path,'line':node.lineno,'message':'NotImplementedError: confirm this is an intentional abstract interface, not an unfinished feature'})
    from mission.interface import review_interface
    ui=review_interface(workspace,mission)
    issues.extend(ui['issues']);warnings.extend(ui['warnings'])
    return {'passed':not issues,'checked_files':len(trees),'issues':issues[:60],'warnings':warnings[:30],
            'scope':'Static Python integration, obvious placeholder tests and selected UI code checks only; visual/runtime behavior and requirement coverage still need verification'}
