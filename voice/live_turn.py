"""Order Live tool calls behind their microphone transcript."""
from __future__ import annotations

import asyncio

from voice.command_guard import VoiceCommandGate

# Some Live models omit the finished flag. Allow their transcript deltas a
# short window to arrive, without waiting indefinitely for a tool response.
TRANSCRIPT_GRACE = 0.65


def merge_transcript(previous: str, chunk: str) -> str:
    if not previous or chunk.startswith(previous):
        return chunk
    if not chunk or previous.endswith(chunk):
        return previous
    for overlap in range(min(len(previous), len(chunk)), 1, -1):
        if previous.endswith(chunk[:overlap]):
            return previous + chunk[overlap:]
    separator = '' if previous[-1:].isspace() or chunk[:1].isspace() or chunk[0] in '،,.!?؟:;' else ' '
    return previous + separator + chunk


async def ordered_responses(session, gate: VoiceCommandGate):
    """Yield server events and deferred tool calls in usable order.

    Only the pending SDK read runs concurrently. Cancelling a grace-period
    wait must not cancel that read and lose the late transcript packet.
    """
    pending = []
    text = ''
    finished = None
    deadline = None
    reader = None
    loop = asyncio.get_running_loop()

    def commit():
        if not gate.last_text and text.strip() and len(text.strip()) <= 420:
            gate.record(text.strip())

    def reset():
        nonlocal text, finished
        text, finished = '', None
        gate.clear()

    async def incoming():
        while True:
            async for response in session.receive():
                yield response

    stream = incoming()
    try:
        while True:
            if reader is None:
                reader = asyncio.create_task(anext(stream))
            delay = None if deadline is None else max(0, deadline - loop.time())
            done, _ = await asyncio.wait({reader}, timeout=delay)
            if not done:
                if finished is not False:
                    commit()
                for response in pending:
                    yield response
                pending.clear()
                deadline = None
                continue

            response = reader.result()
            reader = None
            content = response.server_content
            cancellation = getattr(response, 'tool_call_cancellation', None)
            if cancellation and pending:
                cancelled = set(cancellation.ids or ())
                for deferred in pending:
                    deferred.tool_call.function_calls = [
                        call for call in deferred.tool_call.function_calls or [] if call.id not in cancelled
                    ]
                pending = [deferred for deferred in pending if deferred.tool_call.function_calls]
                if not pending:
                    deadline = None
            if content and content.interrupted:
                reset()
                # A cancelled call must never bind to the next speaker turn.
                pending.clear()
                deadline = None
            if content and content.input_transcription:
                transcript = content.input_transcription
                piece = transcript.text or ''
                if not gate.last_text:
                    text = merge_transcript(text, piece)[:421]
                    finished = getattr(transcript, 'finished', None)
                    if finished is True:
                        commit()

            if getattr(response, 'tool_call', None) and not gate.last_text:
                pending.append(response)
                if deadline is None:
                    deadline = loop.time() + TRANSCRIPT_GRACE
                continue

            boundary = bool(content and content.turn_complete)
            if boundary and not content.interrupted and finished is not False:
                commit()
            if not boundary:
                yield response
            if pending and (gate.last_text or boundary):
                for deferred in pending:
                    yield deferred
                pending.clear()
                deadline = None
            if boundary:
                yield response
            if boundary and not content.interrupted:
                reset()
    finally:
        if reader is not None:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        await stream.aclose()
