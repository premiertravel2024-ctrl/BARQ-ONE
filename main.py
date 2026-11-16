"""BARQ command-line client. Desktop/API entry points remain unchanged."""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
import os

from router.engine import Engine, AllModelsFailed

from core.version import VERSION


def configure_logging():
    level=os.getenv('BARQ_LOG_LEVEL','INFO').upper()
    logging.basicConfig(level=getattr(logging,level,logging.INFO),format='%(levelname)s %(name)s: %(message)s')


async def run_task(args):
    engine=Engine(local_only=args.local_only)
    from brain.coordinator import Brain
    brain=Brain(engine)
    if args.stats:
        print(json.dumps(engine.health.snapshot(),indent=2))
        return 0
    if not args.task:
        return 2
    try:
        answer=await brain.run([{'role':'user','content':args.task}])
        print(answer['content'])
        print('\n[model: '+answer['model']+']')
        return 0
    except AllModelsFailed as exc:
        logging.error('All models failed: %s',exc)
        return 1


def main(argv=None):
    parser=argparse.ArgumentParser(description='BARQ AI')
    parser.add_argument('task',nargs='?')
    parser.add_argument('--local-only',action='store_true')
    parser.add_argument('--stats',action='store_true')
    parser.add_argument('--version',action='version',version=f'BARQ {VERSION}')
    args=parser.parse_args(argv)
    configure_logging()
    if not args.task and not args.stats:
        parser.error('Provide a task or run uvicorn api:app')
    try:
        return asyncio.run(run_task(args))
    except KeyboardInterrupt:
        return 130


if __name__=='__main__':
    raise SystemExit(main())
