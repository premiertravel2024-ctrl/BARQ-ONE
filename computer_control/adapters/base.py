"""OSAdapter contract. The fake adapter makes tests independent of the host desktop."""
from abc import ABC,abstractmethod
from dataclasses import dataclass, field
from typing import Any
import hashlib,json

@dataclass
class Perception:
    window:str=''; windows:list[str]=field(default_factory=list)
    elements:list[dict]=field(default_factory=list)
    cursor:tuple[int,int]=(0,0)
    screenshot_png:bytes|None=None
    # x,y,width,height of captured monitor BEFORE resizing to the model preview.
    screenshot_bounds:tuple[int,int,int,int]|None=None
    def safe_data(self)->dict:
        from computer_control.safety.policy import redact
        return {'window':redact(self.window),'windows':[redact(x) for x in self.windows[:15]],
                'elements':[{'id':e.get('id'),'name':redact(str(e.get('name',''))),'role':e.get('role'),
                             'rect':e.get('rect'),'signature':e.get('signature')} for e in self.elements[:120]],'cursor':self.cursor,
                'screenshot_hash':hashlib.sha256(self.screenshot_png).hexdigest() if self.screenshot_png else None}

class OSAdapter(ABC):
    @abstractmethod
    def perceive(self)->Perception:...
    @abstractmethod
    def act(self,tool:str,args:dict[str,Any])->dict[str,Any]:...
    def check_abort(self)->bool:return False
    def check_folder_open(self)->None:pass

class FakeAdapter(OSAdapter):
    def __init__(self):self.calls=[];self.screen=Perception(window='Test Desktop',elements=[{'id':'editor','name':'Editor','role':'text','rect':[0,0,400,200]}]);self.outputs={}
    def perceive(self):return self.screen
    def act(self,tool,args):
        self.calls.append((tool,args.copy()))
        return self.outputs.get(tool,{'ok':True,'tool':tool})
