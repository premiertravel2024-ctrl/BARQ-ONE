import os
os.environ['TEST_FREE_KEY']='test-only'
from router.limits import RateLimiter
from router.config import Config
from router.select import Router
from monitor.health import Health

def test_shared_provider_quota():
    clock=[1000.]
    l=RateLimiter(lambda:clock[0]); l.record('groq')
    assert not l.allowed('groq',1,100)
    assert l.remaining('groq',100)==99
    clock[0]+=61
    assert l.allowed('groq',1,100)

def test_no_local_fallback():
    cfg=Config.model_validate({'providers':[{'name':'groq','base_url':'https://example.invalid/v1','api_key_env':'TEST_FREE_KEY','rpm':1,'rpd':2,'models':[{'name':'a'},{'name':'b'}]}]})
    limiter=RateLimiter(); limiter.record('groq')
    assert Router(cfg,limiter,Health()).candidates('simple','easy')==[]
