"""System health endpoints. Extracted without changing public URLs."""
from fastapi import APIRouter


def make_system_router(engine):
    router=APIRouter(tags=['system'])

    @router.get('/health')
    def health():
        return {'status':'ok','models':engine.health.snapshot(),
                'requests':len(engine.stats),'routing':engine.connectivity()}

    @router.get('/stats')
    def stats():
        return {'recent':engine.stats[-20:],'health':engine.health.snapshot()}

    return router
