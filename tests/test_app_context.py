import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_routes import app_context
from voice.app_tools import app_voice_intent, inspect_app
from voice.command_guard import VoiceCommandGate


def test_ui_context_keeps_only_declared_summary_fields(monkeypatch):
    monkeypatch.setattr(app_context, '_snapshot', None)
    monkeypatch.setattr(app_context, '_snapshot_at', 0)
    app = FastAPI()
    app.include_router(app_context.router)
    client = TestClient(app)
    assert client.get('/v1/app-context/state').json()['status'] == 'unavailable'
    response = client.put('/v1/app-context/state', json={
        'section': 'chat', 'previous': 'music',
        'previous_view': {'mode': 'anghami', 'item': 'تملى معاك', 'invite_code': 'secret'},
        'books': [{'title': 'ما وراء الطبيعة', 'label': 'أحمد خالد توفيق'}],
    })
    assert response.status_code == 200
    current = client.get('/v1/app-context/state').json()
    assert current['previous_view'] == {'mode': 'anghami', 'item': 'تملى معاك'}
    assert 'books' not in current
    assert client.get('/v1/app-context/search', params={'catalogue': 'books', 'q': 'احمد توفيق'}).json() == {
        'status': 'ok', 'items': [{'title': 'ما وراء الطبيعة', 'label': 'أحمد خالد توفيق'}],
    }


def test_in_app_navigation_and_search_do_not_claim_desktop_intents():
    assert app_context.section_command('يا برق افتح أنغامي') == {'section': 'music', 'mode': 'anghami'}
    assert app_context.section_command('افتح مكتبة القراءة') == {'section': 'stories', 'mode': None}
    assert app_context.section_command('افتح كروم') is None
    assert app_context.section_command('لو قلت افتح الموسيقى') is None
    assert app_context.find_request('دور على أغنية تملى معاك في Spotify') == ('spotify', 'تملي معاك')
    assert app_context.find_request('دور على فيلم ماتريكس على الجهاز') is None


def test_voice_routes_the_transcribed_app_target_only_once():
    gate = VoiceCommandGate()
    gate.record('يا برق افتح السينما')
    assert app_voice_intent(gate)
    outcome = asyncio.run(inspect_app(gate))
    assert outcome['status'] == 'requested'
    assert outcome['_ui']['app_action']['section'] == 'watch'
    assert asyncio.run(inspect_app(gate))['status'] == 'needs_clarification'
    gate.record('لو قلت افتح الموسيقى')
    assert not app_voice_intent(gate)


def test_cinema_availability_results_use_selected_region_and_official_link(monkeypatch):
    from services import cinema_catalog

    def fetch(path, params):
        assert path == 'movie/550/watch/providers'
        return {'results': {
            'SA': {'link': 'https://www.themoviedb.org/movie/550-fight-club/watch?locale=SA',
                   'rent': [{'provider_name': 'Example TV'}]},
            'EG': {'link': 'https://example.com/movie/550/watch', 'rent': []},
        }}

    monkeypatch.setattr(cinema_catalog, '_fetch', fetch)
    result = cinema_catalog.watch_providers('movie', 550, 'SA')
    assert result['groups']['rent'] == ['Example TV']
    assert result['link'].startswith('https://www.themoviedb.org/')
    assert cinema_catalog.watch_providers('movie', 550, 'EG')['link'] == ''
