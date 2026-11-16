"""Safe surgical edits with exact-match guards, preview and explicit approval.

Patch proposals reuse the existing workspace approval token, checks and backups.
"""
from workspace.manager import read_text, propose
from coding.quality import source_check


def propose_replace(workspace, path, before, after):
    if not isinstance(before, str) or not before:
        raise ValueError('The old text must be a non-empty exact match')
    if not isinstance(after, str):
        raise ValueError('New text must be a string')
    original = read_text(workspace, path)
    n = original.count(before)
    if n != 1:
        raise ValueError(f'Expected exactly one matching code block; found {n}. Read the file and use a longer unique block.')
    updated = original.replace(before, after, 1)
    check = source_check(path, updated)
    if not check['valid']:
        raise ValueError('Proposed edit is invalid: ' + '; '.join(check['errors'])[:700])
    proposal = propose(workspace, path, updated)
    proposal['quality'] = check
    proposal['edit_type'] = 'exact-replace'
    return proposal
