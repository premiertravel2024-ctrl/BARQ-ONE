"""Regression for short, contextual user corrections shown in BARQ chat."""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from brain.coordinator import Brain
from brain.state import TaskStore

@pytest.mark.asyncio
async def test_exact_funny_reply_for_khafif_zi_el_sahm(tmp_path):
    engine=SimpleNamespace(run=AsyncMock())
    b=Brain(engine, TaskStore(tmp_path/'tasks.db'))
    result=await b.run([{'role':'user','content':'خفيف زي السهم'}])
    assert 'راسي زي التريلا' in result['content']
    engine.run.assert_not_called()

@pytest.mark.asyncio
async def test_generic_speed_feedback_still_not_parroted(tmp_path):
    engine=SimpleNamespace(run=AsyncMock())
    b=Brain(engine, TaskStore(tmp_path/'tasks.db'))
    result=await b.run([{'role':'user','content':'عايز ردودك تكون سهلة'},
                        {'role':'assistant','content':'حاضر هرد ببساطة'},
                        {'role':'user','content':'سرّع ردك'}])
    assert 'أنا سريع' not in result['content']
    assert 'أقصر' in result['content']
    engine.run.assert_not_called()

@pytest.mark.asyncio
async def test_funny_reply_stays_local_even_with_history(tmp_path):
    engine=SimpleNamespace(run=AsyncMock())
    b=Brain(engine, TaskStore(tmp_path/'tasks.db'))
    result=await b.run([{'role':'user','content':'عايز الدبلجة المصرية من فيلم برق بنزين'},
                        {'role':'assistant','content':'أي شخصية؟'},
                        {'role':'user','content':'خفيف زي السهم'}])
    assert 'راسي زي التريلا' in result['content']
    engine.run.assert_not_called()
