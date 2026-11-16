"""BARQ chat response protocol and SSE stream, independently testable."""
import json
import time
import uuid
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from router.engine import AllModelsFailed
from core.persona import with_identity
from services.public_hub import match_explicit_programming_question, lookup, describe
import asyncio
from services.web_research import public_query, research_async, model_research_context, source_footer

async def complete_chat(req,x_barq_mode,brain):
    if x_barq_mode is not None and x_barq_mode not in ('fast','balanced','best'):
        raise HTTPException(400,'Invalid x-barq-mode header')
    selected_mode=x_barq_mode or req.network_mode
    from launcher.api import local_chat_launch
    launch_reply=local_chat_launch(req.messages) if not req.attachments else None
    identity = launch_reply if launch_reply is not None else brain._local_reply(req.messages)
    # Directly requested OWN-device media inventory is a local read-only action.
    # Never send filenames or paths to cloud providers as part of this lookup.
    if identity is None and not req.attachments and req.messages:
        from services.local_media_intent import local_movie_reply
        user_message=next((m.get('content','') for m in reversed(req.messages) if m.get('role')=='user'),'')
        media_reply=await local_movie_reply(user_message)
        if media_reply is not None:identity=media_reply

    if identity is None and not req.attachments and req.messages:
        from services.local_file_intent import local_file_reply
        user_message=next((m.get('content','') for m in reversed(req.messages) if m.get('role')=='user'),'')
        file_reply=await local_file_reply(user_message)
        if file_reply is not None:identity=file_reply

    # Direct, narrow metadata lookup for text chat: no model hallucinations or arbitrary URLs.
    if identity is None and req.messages and not req.attachments:
        last=req.messages[-1]
        if last.get('role') == 'user' and isinstance(last.get('content'),str):
            found=match_explicit_programming_question(last['content'])
            if found:
                provider,target=found
                identity=describe(await asyncio.to_thread(lookup,provider,target))
    # Search ONLY for short public freshness/search requests. Never send local
    # files, attachments, private-mode messages or a whole conversation out.
    # Search snippets are external data, never permission to run tools.
    model_messages=req.messages
    search_result=None
    if identity is None and not req.attachments and req.messages:
        user_text=next((m.get('content','') for m in reversed(req.messages) if m.get('role')=='user'),'')
        query=public_query(user_text,privacy=req.privacy,local_only=req.model=='local-only')
        if query:
            search_result=await research_async(query)
            context=model_research_context(search_result)
            if search_result.get('status')=='unavailable':
                context={'role':'system','content':'BARQ attempted a live public web search, but external sources were unavailable. Do not invent a latest fact, source or citation. Clearly say fresh data could not be verified; provide general knowledge only if clearly identified as possibly outdated.'}
            if context:
                model_messages=[*req.messages[:-1],context,req.messages[-1]]
    messages = with_identity(model_messages, req.voice_mode)
    rid='chatcmpl-'+uuid.uuid4().hex;now=int(time.time())
    if req.stream:
        async def chunks():
            if identity is not None:
                for delta, reason in (({'role':'assistant'}, None), ({'content':identity}, None), ({}, 'stop')):
                    payload={'id':rid,'object':'chat.completion.chunk','created':now,'model':'BARQ-AI/local',
                             'choices':[{'index':0,'delta':delta,'finish_reason':reason}]}
                    yield 'data: '+json.dumps(payload,ensure_ascii=False)+'\n\n'
                yield 'data: [DONE]\n\n'
                return
            model='auto'
            try:
                async for item in brain.stream(model_messages,model=req.model,conversation_id=req.conversation_id,voice_mode=req.voice_mode,network_mode=selected_mode,privacy=req.privacy):
                    kind=item['type']
                    if kind=='model':
                        model=item['model']
                        delta={'role':'assistant'}
                    elif kind=='token':
                        delta={'content':item['content']}
                    elif kind=='done':
                        footer=source_footer(search_result)
                        if footer:
                            extra={'id':rid,'object':'chat.completion.chunk','created':now,'model':model,
                                   'choices':[{'index':0,'delta':{'content':footer},'finish_reason':None}]}
                            yield 'data: '+json.dumps(extra,ensure_ascii=False)+'\n\n'
                        delta={}
                    elif kind=='error':
                        yield 'data: '+json.dumps({'error':item['message'],'attempts':item.get('attempts',[])},ensure_ascii=False)+'\n\n'
                        yield 'data: [DONE]\n\n'
                        return
                    else:
                        continue
                    payload={'id':rid,'object':'chat.completion.chunk','created':now,'model':model,
                             'choices':[{'index':0,'delta':delta,'finish_reason':'stop' if kind=='done' else None}]}
                    yield 'data: '+json.dumps(payload,ensure_ascii=False)+'\n\n'
            except ValueError as exc:
                yield 'data: '+json.dumps({'error':str(exc)[:300]})+'\n\n'
            yield 'data: [DONE]\n\n'
        return StreamingResponse(chunks(),media_type='text/event-stream',headers={'Cache-Control':'no-cache, no-transform', 'X-Accel-Buffering':'no'})
    if identity is not None:
        return {'id':rid,'object':'chat.completion','created':now,'model':'BARQ-AI/local',
                'choices':[{'index':0,'message':{'role':'assistant','content':identity},'finish_reason':'stop'}],'usage':None}
    try:r=await brain.run(model_messages,model=req.model,conversation_id=req.conversation_id,voice_mode=req.voice_mode,network_mode=selected_mode,privacy=req.privacy)
    except AllModelsFailed as exc:raise HTTPException(503,{'message':str(exc),'attempts':exc.attempts})
    except ValueError as exc:raise HTTPException(400,str(exc))
    return {'id':rid,'object':'chat.completion','created':now,'model':r['model'],
            'choices':[{'index':0,'message':{'role':'assistant','content':r['content']+source_footer(search_result)},'finish_reason':'stop'}],'usage':None,'barq':r.get('barq'),'research_sources':search_result.get('results',[]) if search_result and search_result.get('status')=='ok' else []}
