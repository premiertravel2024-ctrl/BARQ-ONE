import pytest
from tools.registry import load_tools,execute,status

def test_registry():
    ids={x.id for x in load_tools()}
    assert {'rea','github_status','github_log'}<=ids
    assert any(x['id']=='rea' and not x['enabled'] for x in status())

@pytest.mark.asyncio
async def test_confirmation_required(tmp_path):
    with pytest.raises(ValueError,match='confirmation'):
        await execute('github_status',str(tmp_path),False)

@pytest.mark.asyncio
async def test_unknown_tool(tmp_path):
    with pytest.raises(ValueError,match='Unknown'):
        await execute('unknown',str(tmp_path),True)
