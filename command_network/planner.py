"""Validate plans and dispatch independent nodes. No OS actions are executed here."""
from __future__ import annotations
import asyncio
from .contracts import TaskGraph

async def schedule(graph:TaskGraph,runner,concurrency=3):
    semaphore=asyncio.Semaphore(concurrency)
    outputs={};remaining={n.id:n for n in graph.nodes}
    while remaining:
        ready=[node for node in remaining.values() if set(node.depends_on)<=outputs.keys()]
        if not ready:raise ValueError('Graph cannot be scheduled')
        async def one(node):
            async with semaphore:
                # Dependencies are the ONLY intermediate data exposed to this node.
                return await runner(node,{name:outputs[name] for name in node.depends_on})
        batch=await asyncio.gather(*(one(n) for n in ready))
        for node,out in zip(ready,batch):outputs[node.id]=out;remaining.pop(node.id)
    return outputs
