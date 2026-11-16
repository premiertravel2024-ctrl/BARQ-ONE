"""Compatibility wrapper over one quota manager; no second independent counter."""
from router.quota import QuotaManager
class RateLimiter(QuotaManager):
    def __init__(self,clock=None,db_path=None,margin=0):
        super().__init__(clock=clock,db_path=db_path,margin=margin)
