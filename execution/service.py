"""Shared entry for chat/voice/UI task requests; retained Manager is policy authority.

The model cannot submit arbitrary process args through this interface.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

VALID_SOURCES=frozenset({'chat','voice','launcher','ui'})

@dataclass
class ExecutionService:
    manager:Any

    def submit(self,goal:str,*,source:str,model:str='auto')->dict:
        if source not in VALID_SOURCES:raise ValueError('Unknown execution source')
        if not isinstance(goal,str) or not 2<=len(goal.strip())<=3000:
            raise ValueError('Invalid task goal')
        # All sources are subject to the same Manager master toggle, policy,
        # audit and exact-action on-screen approval. Voice never auto-approves.
        from execution.react_mission import is_react_desktop_goal, mission
        active=mission().public()
        if active and active.get('status') in ('running','planning'):
            raise RuntimeError('Finish or stop current React mission before starting another computer task')
        from computer_control.tools.direct_intent import direct_action
        from computer_control.tools.direct_sequence import direct_sequence
        if not direct_action(goal) and not direct_sequence(goal) and is_react_desktop_goal(goal):
            policy=getattr(self.manager,'policy',None)
            if policy is None:raise RuntimeError('Computer Control policy is unavailable')
            current=getattr(self.manager,'current',None)
            if current is not None and getattr(current,'status',None) in ('planning','running','approval'):
                raise RuntimeError('Finish current desktop task before starting React setup')
            return mission().start(goal,source,bool(policy.enabled),policy.mode)
        legacy_source='voice' if source=='voice' else 'text'
        return self.manager.start(goal.strip(),model,source=legacy_source)

    def current_task(self)->dict|None:
        from execution.react_mission import mission
        project=mission().public()
        desktop=getattr(self.manager,'current',None)
        if not project:
            return desktop.public() if desktop else None
        active=('planning','running','approval')
        if desktop and (desktop.status in active or (
                project['status'] not in active and desktop.started>=project.get('started',0))):
            return desktop.public()
        return project

    def status(self)->dict:
        return self.current_task() or {'status':'idle'}

    def task_by_id(self,task_id:str)->dict|None:
        from execution.react_mission import mission
        desktop=self.manager.current
        if desktop and desktop.id==task_id:
            return desktop.public()
        project=mission().public()
        if project and project['id']==task_id:
            return project
        return self.manager.state_store.get(task_id)

    def cancel(self)->dict:
        return self.manager.stop()

    def approve_on_screen(self,id:str,accepted:bool)->dict:
        return self.manager.approve(id,accepted)

    def continue_confirmed(self,task_id:str,confirmed:bool=False)->dict:
        return self.manager.continue_interrupted(task_id,confirmed=confirmed)
