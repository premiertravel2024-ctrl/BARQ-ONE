"""Offline semantic, dialect and real sample-label tests. No provider requests."""
import json
from pathlib import Path
import pytest
from command_network.contracts import Request,TaskProfile
from command_network.triage import Triage
from command_network.verifier import verify
from command_network.semantic_cache import SemanticCache


def profile(kind='qa',language='ar'):
    return TaskProfile(task_type=kind,language=language)

@pytest.mark.asyncio
async def test_private_local_embedding_cache_no_cloud_or_tools(tmp_path):
    async def embed(value):return [1.0,0.0] if 'سلام' in value else [0.0,1.0]
    cache=SemanticCache(path=tmp_path/'cache.sqlite3',embedder=embed)
    request=Request(messages=[{'role':'user','content':'قول سلام'}])
    await cache.put(request,profile(),{'content':'أهلا','model':'ollama/test','task':'qa','offline':True})
    close=Request(messages=[{'role':'user','content':'سلام يا برق'}])
    assert (await cache.get(close,profile()))['content']=='أهلا'
    unrelated=Request(messages=[{'role':'user','content':'ما معنى الدائرة'}])
    assert await cache.get(unrelated,profile()) is None
    private=Request(messages=[{'role':'user','content':'password=very-secret-password123'}])
    assert await cache.put(private,profile(),{'content':'secret'}) is False
    tool=profile('tool')
    assert await cache.get(request,tool) is None


def test_python_syntax_and_egyptian_style_verifier():
    assert not verify('```python\nif True print(5)\n```',profile('coding')).accepted
    assert verify('```python\nprint(5)\n```',profile('coding')).accepted
    assert not verify('شو بدك؟',profile()).accepted
    assert verify('إزيك يا معلم؟',profile()).accepted


def test_heldout_dialect_examples_with_minimum_90_percent():
    samples=Path(__file__).resolve().parents[1]/'examples'/'triage.jsonl'
    assert sum(1 for _ in samples.open(encoding='utf-8'))>=300
    rows=[json.loads(line) for i,line in enumerate(samples.open(encoding='utf-8')) if i%3==0]
    # Test near paraphrases rather than exact training sentences.
    matches=0
    for row in rows:
        question=row['text']+' لو سمحت'
        got=Triage().classify(Request(messages=[{'role':'user','content':question}])).task_type
        matches+=got==row['task_type']
    assert matches/len(rows)>=.90, (matches,len(rows))
