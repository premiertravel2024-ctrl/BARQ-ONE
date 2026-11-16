import os
os.environ["TEST_FREE_KEY"]="test-only"
import pytest
from router.config import Config
from router.limits import RateLimiter
from router.select import Router
from monitor.health import Health
from router.engine import Engine,AllModelsFailed
CFG=Config.model_validate({'providers':[{'name':'testcloud','api_key_env':'TEST_FREE_KEY','base_url':'https://example.invalid/v1','priority':50,'rpm':1,'rpd':2,'models':[{'name':'local','strengths':['coding']}]},{'name':'testcloud','api_key_env':'TEST_FREE_KEY','base_url':'https://example.invalid/v1','priority':20,'models':[{'name':'backup','strengths':['simple']}]}]})
def test_route():
 r=Router(CFG,RateLimiter(),Health(),False)
 assert r.candidates('coding','easy')[0][1].name=='local'
def test_rate_limit():
 clock=[100000.]
 l=RateLimiter(lambda:clock[0]);l.record('x');assert not l.allowed('x',1,2)
 clock[0]+=61;assert l.allowed('x',1,2)
 l.record('x');assert not l.allowed('x',1,2)
 clock[0]+=86401;assert l.allowed('x',1,2)
@pytest.mark.asyncio
async def test_fallback(monkeypatch,tmp_path):
 import router.engine as mod
 async def fake(p,m,messages):
  if m.name=='local':raise mod.ProviderError('rate limited',429)
  return 'A valid answer'
 monkeypatch.setattr(mod,'complete',fake)
 e=Engine(CFG,False,str(tmp_path/'test.db'))
 result=await e.run([{'role':'user','content':'write python code'}])
 assert result['model']=='testcloud/backup'
 assert len(result['attempts'])==1
@pytest.mark.asyncio
async def test_all_fail(monkeypatch,tmp_path):
 import router.engine as mod
 async def fake(p,m,messages):raise mod.ProviderError('timeout')
 monkeypatch.setattr(mod,'complete',fake)
 e=Engine(CFG,False,str(tmp_path/'test.db'))
 with pytest.raises(AllModelsFailed):await e.run([{'role':'user','content':'hello'}])
