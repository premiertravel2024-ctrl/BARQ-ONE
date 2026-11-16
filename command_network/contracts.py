"""Stable typed DTOs for the BARQ network API."""
from __future__ import annotations
from typing import Literal, Any
from pydantic import BaseModel, Field, model_validator
import uuid

TASKS = ('coding','debugging','reasoning','writing','translation','summarization','extraction','qa','chat','vision','long_document','tool')
class Request(BaseModel):
    request_id: str = Field(default_factory=lambda: uuid.uuid4().hex, min_length=1, max_length=90)
    messages: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    attachments: list[dict[str, Any]] = Field(default_factory=list, max_length=12)
    mode: Literal['fast','balanced','best'] = 'balanced'
    privacy: Literal['normal','local-only'] = 'normal'
    priority: Literal['interactive','background'] = 'interactive'
    deadline_seconds: float = Field(default=45, ge=1, le=300)
    model: str = 'auto'
    conversation_id: str = Field(default='', max_length=80)
    @model_validator(mode='after')
    def check_messages(self):
        for message in self.messages:
            if message.get('role') not in ('system','user','assistant','tool'):
                raise ValueError('Message role is invalid')
            if not isinstance(message.get('content'),(str,list)):
                raise ValueError('Message content must be string or multimodal list')
        if len(str(self.messages))>1_000_000:
            raise ValueError('Request exceeds size budget')
        return self

class TaskProfile(BaseModel):
    task_type: Literal['coding','debugging','reasoning','writing','translation','summarization','extraction','qa','chat','vision','long_document','tool']
    domain: str = 'general'
    difficulty: Literal['easy','medium','hard'] = 'easy'
    language: Literal['ar','en','mixed'] = 'en'
    needs_long_context: bool = False
    needs_tools: bool = False
    requires_native_tool_calls: bool = False
    needs_json: bool = False
    requires_native_json: bool = False
    modality: Literal['text','image','file'] = 'text'
    latency_sensitivity: float = Field(default=.5,ge=0,le=1)
    risk: Literal['low','medium','high'] = 'low'
    confidence: float = Field(default=.5,ge=0,le=1)
    layer: str = 'rules'
    token_estimate: int = Field(default=0,ge=0)

class RoutePlan(BaseModel):
    request_id: str
    chain: list[str] = Field(default_factory=list)
    strategy: Literal['single','cascade','hedged','ensemble','map_reduce','plan_execute'] = 'single'
    smart_path: bool = False
    reason: str
    rejected: dict[str,str] = Field(default_factory=dict)
    scores: dict[str,float] = Field(default_factory=dict)
    timeouts: dict[str,float] = Field(default_factory=dict)
    profile: TaskProfile

class Event(BaseModel):
    type: Literal['routing','step_started','partial','step_done','verified','final','error']
    request_id: str
    data: dict[str,Any] = Field(default_factory=dict)

class TaskNode(BaseModel):
    id: str = Field(pattern=r'^[a-zA-Z][a-zA-Z0-9_-]{0,31}$')
    goal: str = Field(min_length=1,max_length=1000)
    task_type: str
    depends_on: list[str] = Field(default_factory=list)
    inputs: dict[str,Any] = Field(default_factory=dict)
    expected_output_schema: dict[str,Any] = Field(default_factory=dict)
    model_hint: str | None = None

class TaskGraph(BaseModel):
    nodes: list[TaskNode] = Field(min_length=1,max_length=8)
    @model_validator(mode='after')
    def acyclic(self):
        graph={n.id:n.depends_on for n in self.nodes}
        if len(graph)!=len(self.nodes):raise ValueError('Duplicate task node ID')
        depths={}
        def visit(n,active):
            if n in active:raise ValueError('Dependency cycle')
            if n in depths:return depths[n]
            if n not in graph:raise ValueError('Unknown node dependency')
            depths[n]=1+max((visit(k,active|{n}) for k in graph[n]),default=0)
            if depths[n]>4:raise ValueError('Graph depth exceeds 4')
            return depths[n]
        for key in graph:visit(key,set())
        return self
