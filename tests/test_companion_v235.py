import asyncio,csv,io,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from computer_control.safety.policy import Policy
from services.desktop_companion import intent,command,first_video,video_url
from services.game_performance import summarize_csv
from voice.brain_bridge import action_route

@pytest.mark.parametrize('text,kind',[
 ('شغلي اغنية عمرو دياب','youtube'),('يا برق شغللي موسيقى على اليوتيوب','youtube'),('play a song on youtube','youtube'),
 ('عاوز اسمع اغنية هادية','youtube'),('شغللي مزيكا','youtube'),('ممكن تقيسلي الفريمات','fps'),
 ('قيسلي الفريمات','fps'),('الفريمات كام','fps'),('ايه رايك في اللعبة','game_advice'),('اديني نصايح في اللعب','game_advice')])
def test_common_voice_text_routes(text,kind):
 assert intent(text)[0]==kind
 assert action_route(text)=='desktop_companion'

@pytest.mark.parametrize('text',['متشغلش اغنية','لو قلت شغلي اغنية','اشرحلي ازاي يقيس الفريمات','ابنيلي لعبة','قيس حرارة المعالج','دور على فيلم','امسح لعبة','لا تشغل موسيقى'])
def test_non_companion_commands_not_hijacked(text):assert intent(text) is None

@pytest.mark.parametrize('url',['http://youtube.com/watch?v=abcdefghijk','https://youtube.com.evil.com/watch?v=abcdefghijk','https://user:pw@youtube.com/watch?v=abcdefghijk','https://youtu.be/invalid','file:///abc'])
def test_only_video_urls(url):assert video_url(url) is None

def test_search_only_organic_video_renderer():
 data={'contents':{'twoColumnSearchResultsRenderer':{'primaryContents':{'sectionListRenderer':{'contents':[{'itemSectionRenderer':{'contents':[{'adSlotRenderer':{'videoId':'badbadbad11'}},{'videoRenderer':{'videoId':'abcdefghijk','title':{'runs':[{'text':'اختبار أغنية'}]}}}]}}]}}}}}
 answer=first_video('var ytInitialData = '+json.dumps(data)+';')
 assert answer['url']=='https://www.youtube.com/watch?v=abcdefghijk&autoplay=1'
 assert answer['title']=='اختبار أغنية'
 assert first_video('consent wall') is None

@pytest.mark.asyncio
async def test_permission_checked_before_search_or_capture():
 def fail(*a,**kw):pytest.fail('must not touch device/network')
 for text in ['شغلي اغنية','قيسلي الفريمات','شوف اللعبة واديني نصايح']:
  result=await command(text,policy=Policy(enabled=False),finder=fail,capture=fail,fps_reader=fail)
  assert result['status']=='disabled'

@pytest.mark.asyncio
async def test_youtube_exact_video_launch_and_honest_playback():
 calls=[]
 class Manager:
  def launch_direct(self,tool,args,**kw):calls.append((tool,args));return {'status':'opened'}
 async def finder(q):return {'url':'https://youtu.be/abcdefghijk','title':'Song'}
 result=await command('شغلي اغنية على يوتيوب',policy=Policy(enabled=True,direct_commands=True),manager_instance=Manager(),finder=finder)
 assert result['status']=='opened' and result['playback_verified'] is False
 assert calls==[('open_url',{'url':'https://www.youtube.com/watch?v=abcdefghijk&autoplay=1'})]

@pytest.mark.asyncio
async def test_search_result_cannot_open_untrusted_host():
 async def finder(q):return {'url':'https://evil.test/video','title':'foo'}
 assert (await command('شغل اغنية',policy=Policy(enabled=True,direct_commands=True),finder=finder))['status']=='invalid'

@pytest.mark.asyncio
async def test_game_advice_uses_real_snapshot_and_privacy():
 from PIL import Image
 async def analyzer(engine,**kwargs):
  assert kwargs['privacy']=='local-only' and kwargs['data'].startswith(b'\x89PNG')
  assert 'لا تخمن' in kwargs['prompt']
  return {'text':'نصيحة من اللقطة','model':'local/vision'}
 result=await command('اديني نصايح في اللعبة',policy=Policy(enabled=True,local_only_vision=True),engine=object(),capture=lambda:Image.new('RGB',(40,40)),analyzer=analyzer)
 assert result['snapshot_only'] and result['message']=='نصيحة من اللقطة'

@pytest.mark.asyncio
async def test_no_vision_returns_no_invented_advice():
 def capture():raise OSError('exclusive screen')
 result=await command('شوف اللعبة',policy=Policy(enabled=True),engine=object(),capture=capture)
 assert result['status']=='unavailable'

def csv_rows(values,second=False):
 out='Application,ProcessID,SwapChainAddress,msBetweenPresents\n'
 out+=''.join(f'game.exe,10,A,{value}\n' for value in values)
 if second:out+=''.join('other.exe,20,B,10\n' for _ in range(30))
 return out

def test_fps_uses_total_intervals_not_mean_instantaneous_fps():
 result=summarize_csv(csv_rows([10,30]*100))
 assert result['average_fps']==50 and result['one_percent_low']==33.3
 assert result['sample_seconds']==4 and result['pid']==10

def test_invalid_fps_never_becomes_refresh_rate_or_zero():
 assert summarize_csv(csv_rows(['NA','0','nan','inf','-1']))['status']=='unavailable'
 assert summarize_csv(csv_rows([16]*5))['status']=='unavailable'

def test_multiple_processes_require_grounded_target():
 assert summarize_csv(csv_rows([16]*100,True))['status']=='choose'
 assert summarize_csv(csv_rows([16]*100,True),pid=10)['application']=='game.exe'

def test_multiple_swapchains_do_not_double_count():
 text=csv_rows([20]*100)+''.join('game.exe,10,B,1\n' for _ in range(30))
 assert summarize_csv(text)['average_fps']==50

def test_native_sample_bounded_and_temp_csv_cleaned(monkeypatch):
 from services import game_performance as perf
 monkeypatch.setattr(perf.sys,'platform','win32');paths=[]
 def runner(argv,**kw):
  assert kw['shell'] is False and kw['timeout']==12 and '--restart_as_admin' not in argv
  assert '--process_id' in argv and argv[-1]=='10'
  p=Path(argv[argv.index('--output_file')+1]);paths.append(p);p.write_text(csv_rows([20]*100))
  return SimpleNamespace(returncode=0)
 result=perf.capture_fps(tool=Path('verified-presentmon.exe'),pid=10,runner=runner)
 assert result['average_fps']==50 and not paths[0].exists()

def test_native_sample_failure_does_not_fabricate_fps(monkeypatch):
 from services import game_performance as perf
 monkeypatch.setattr(perf.sys,'platform','win32')
 result=perf.capture_fps(tool=Path('verified-presentmon.exe'),pid=10,runner=lambda *a,**k:SimpleNamespace(returncode=5))
 assert result['status']=='unavailable' and 'average_fps' not in result

@pytest.mark.parametrize('correct_title,active,expected',[(True,True,True),(False,True,False),(True,False,False)])
def test_youtube_never_clicks_wrong_window_or_after_user_switch(monkeypatch,correct_title,active,expected):
 from services import youtube_playback as player
 monkeypatch.setattr(player.time,'sleep',lambda _:None)
 clicks=[]
 class Button:
  def window_text(self):return 'Pause (k)' if clicks else 'Play (k)'
  def invoke(self):clicks.append('play')
 class Window:
  handle=123
  def window_text(self):return 'Song - YouTube' if correct_title else 'Other page'
  def descendants(self,**kw):return [Button()]
 result=player.verify_playback('Song',policy=Policy(enabled=True,direct_commands=True),window_probe=lambda:(Window(),lambda:active))
 assert result is expected
 assert len(clicks)==(1 if expected else 0)

def test_glow_uses_burgundy_and_separate_monitor_edges():
 root=Path(__file__).resolve().parents[1]
 text=(root/'voice/screen_glow.py').read_text()
 assert '0x002B0D78' in text and 'EnumDisplayMonitors' in text
 assert 'for x,y,width,height in self._monitor_bounds()' in text
