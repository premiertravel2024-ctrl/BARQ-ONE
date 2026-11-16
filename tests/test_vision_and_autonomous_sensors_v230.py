"""Evidence that image understanding actually uses a vision model and sensors self-start."""
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from PIL import Image

from services import vision


def picture(fmt='PNG'):
    image=Image.new('RGB',(25,20),'navy')
    buf=io.BytesIO();image.save(buf,format=fmt)
    return buf.getvalue()


def provider(kind='cloud',name='gemini',enabled=True):
    m=SimpleNamespace(name='vision-model',enabled=True,strengths=['vision'],free=True)
    p=SimpleNamespace(name=name,kind=kind,models=[m],priority=90,enabled=enabled)
    return p,m


def test_image_validated_and_reject_corrupt():
    mime,b=vision.validated_image(picture());assert mime=='image/png' and len(b)>10
    for content in (b'',b'HELLO WORLD',b'X'* (vision.MAX_IMAGE_BYTES+1)):
        with pytest.raises(ValueError):vision.validated_image(content)


def test_cloud_and_ollama_real_image_payloads():
    p,m=provider();payload=vision.vision_messages(p,'ماذا بالصورة','image/png',picture())
    assert payload[0]['content'][1]['type']=='image_url'
    assert payload[0]['content'][1]['image_url']['url'].startswith('data:image/png;base64,')
    p.kind='local';payload=vision.vision_messages(p,'حلل','image/png',picture())
    assert 'images' in payload[0] and len(payload[0]['images'][0])>20
    assert 'image_url' not in str(payload)


def test_no_cloud_when_privacy_local(monkeypatch):
    cloud,cloud_model=provider('cloud','gemini')
    local,local_model=provider('local','ollama')
    monkeypatch.setattr(vision,'key_for',lambda p:'local-key' if p.kind=='local' else 'cloud-key')
    monkeypatch.setattr(vision,'blocked',lambda n:False)
    allowed=vision.candidates(SimpleNamespace(providers=[cloud,local]),privacy='local-only')
    assert len(allowed)==1 and allowed[0][0] is local


@pytest.mark.asyncio
async def test_analysis_uses_actual_model_and_fails_honestly(monkeypatch):
    p,m=provider('local','ollama')
    e=SimpleNamespace(local_only=True,config=SimpleNamespace(providers=[p]),refresh_local=AsyncMock())
    monkeypatch.setattr(vision,'key_for',lambda p:'local')
    monkeypatch.setattr(vision,'blocked',lambda _:False)
    fake=AsyncMock(return_value='في الصورة شاشة تعرض نافذة')
    monkeypatch.setattr(vision,'complete',fake)
    response=await vision.analyze(e,data=picture(),prompt='اشرح',model='local-only')
    assert response['image_understood'] and response['local'] and 'شاشة' in response['text']
    assert fake.await_count==1
    p.models=[]
    with pytest.raises(ValueError,match='Ollama'):
        await vision.analyze(e,data=picture(),prompt='اشرح',model='local-only')
    assert fake.await_count==1


def test_read_only_sensor_install_is_not_a_model_shell(monkeypatch,tmp_path):
    from core import hardware_sensors as sensors
    fake=tmp_path/'install_hardware_monitor.ps1';fake.write_text('Write-Output ok')
    monkeypatch.setattr(sensors,'_is_windows',lambda:True)
    monkeypatch.setattr(sensors,'_monitor_executable',lambda:None)
    monkeypatch.setattr(sensors,'_sensor_install_script',lambda:fake)
    monkeypatch.setattr(sensors.shutil,'which',lambda cmd:'powershell.exe')
    monkeypatch.setattr('core.paths.state_file',lambda name:tmp_path/name)
    monkeypatch.setattr(sensors,'_auto_setup_process',None)
    monkeypatch.setattr(sensors,'_auto_setup_at',0)
    history=[]
    class Process:
        def poll(self):return None
    def launch(argv,**kwargs):
        history.append(argv)
        assert '-File' in argv and str(fake) in argv
        return Process()
    monkeypatch.setattr(sensors.subprocess,'Popen',launch)
    assert sensors.auto_setup_sensors()=='started'
    assert sensors.auto_setup_sensors()=='running'
    assert len(history)==1


def test_chat_frontend_passes_uploaded_image_to_real_vision_service():
    from pathlib import Path
    s=(Path(__file__).resolve().parents[1]/'frontend/src/lib/backend.ts').read_text()
    assert 'Image understanding is not available' not in s
    assert "'/v1/vision/analyze'" in s
    assert 'image_understood' in s
    chat=(Path(__file__).resolve().parents[1]/'frontend/src/lib/chat.ts').read_text()
    assert "!last?.attachments?.length" in chat
