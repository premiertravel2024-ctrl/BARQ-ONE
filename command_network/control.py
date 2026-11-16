"""Provider circuit breakers and explicit request/token quota tracking."""
import time,random
from collections import defaultdict,deque
class CircuitBreaker:
    def __init__(self,clock=None,threshold=3,cooldown=30):
        self.clock=clock or time.monotonic;self.threshold=threshold;self.cooldown=cooldown;self.states={}
    def peek(self,key):
        """Read-only eligibility: planning/previews must never consume a probe."""
        state=self.states.get(key)
        return not state or not state[1] or (self.clock()>=state[1] and not state[2])
    def release(self,key):
        """A cancelled dispatch must not strand the half-open probe forever."""
        state=self.states.get(key)
        if state and state[2]:self.states[key]=(state[0],state[1],False)
    def allowed(self,key):
        state=self.states.get(key)
        if not state:return True
        errors,until,probe=state
        if until and self.clock()<until:return False
        if until and probe:return False
        if until:self.states[key]=(errors,until,True)
        return True
    def success(self,key):self.states.pop(key,None)
    def failure(self,key,status=None):
        errors,until,_=self.states.get(key,(0,0,False))
        errors+=1
        if status==429 or (status is not None and status>=500) or errors>=self.threshold:
            until=self.clock()+self.cooldown*(.9+.2*random.random())
        self.states[key]=(errors,until,False)
    def status(self,key):
        s=self.states.get(key)
        return 'open' if s and s[1]>self.clock() else 'half-open' if s and s[1] else 'closed'

from router.quota import QuotaManager
class Quota(QuotaManager):
    def __init__(self,clock=None,margin=.1,db_path=None):
        super().__init__(clock=clock,margin=margin,db_path=db_path)
