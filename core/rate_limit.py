"""Per-peer monotonic sliding-window limiter; never trusts X-Forwarded-For."""
from collections import defaultdict,deque
from threading import Lock
import time

class SlidingWindowLimiter:
    def __init__(self,limit=30,window=60.0,clock=None):
        self.limit=limit;self.window=window;self.clock=clock or time.monotonic
        self.requests=defaultdict(deque);self.lock=Lock()
    def check(self,identity):
        with self.lock:
            now=self.clock();q=self.requests[identity]
            while q and now-q[0]>=self.window:q.popleft()
            if len(q)>=self.limit:return max(1,int(self.window-(now-q[0])+0.999))
            q.append(now)
            if len(self.requests)>3000:
                for key in list(self.requests):
                    if not self.requests[key] or now-self.requests[key][-1]>=self.window:self.requests.pop(key,None)
            return 0
