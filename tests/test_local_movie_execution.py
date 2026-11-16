import asyncio
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from services.media_assistant import MediaAssistant
from services.local_media import discover_movies


def setup_assistant(tmp_path,*,direct=True):
 home=tmp_path/'profile';videos=home/'Videos';videos.mkdir(parents=True)
 for name in ('Space.Movie.1080p.mkv','Winter.Film.720p.mp4'):
  with (videos/name).open('wb') as f:f.truncate(2200000)
 policy=NS(enabled=True,direct_commands=direct,allowed_folders=[str(videos)])
 calls=[]
 def launch(tool,args,source):calls.append((tool,args,source));return {'status':'opened'}
 manager=NS(policy=policy,launch_direct=launch)
 def search(folders,**kwargs):return discover_movies(folders,home=home,**kwargs)
 assistant=MediaAssistant(discovery=search,manager_factory=lambda:manager,policy_loader=lambda:policy)
 return assistant,policy,calls,videos

@pytest.mark.asyncio
async def test_recommend_and_play_actual_local_movie_in_one_command(tmp_path):
 assistant,policy,calls,videos=setup_assistant(tmp_path)
 result=await assistant.command('دورلي علي فيلم حلو ع الجهاز',source='voice')
 assert result['matched'] and result['status']=='opened'
 assert result['cards'][0]['label']=='Space Movie'
 assert calls==[('open_file',{'path':str((videos/'Space.Movie.1080p.mkv').resolve())},'voice')]
 assert '_path' not in str(result) and str(tmp_path) not in str(result)
 assert 'مش تقييم فني' in result['message']

@pytest.mark.asyncio
async def test_search_then_ordinal_then_another_movie(tmp_path):
 assistant,policy,calls,videos=setup_assistant(tmp_path)
 first=await assistant.command('دور على افلام عندي')
 assert first['status']=='ok' and not calls
 second=await assistant.command('شغل التاني')
 assert second['status']=='opened' and calls[-1][1]['path'].endswith('Winter.Film.720p.mp4')
 third=await assistant.command('اختار غيره')
 assert third['status']=='opened'  # Direct mode follows the standing choose-and-play preference.
 fourth=await assistant.command('شغل غيره')
 assert fourth['status']=='opened'

@pytest.mark.asyncio
async def test_changed_file_never_plays_a_different_file(tmp_path):
 assistant,policy,calls,videos=setup_assistant(tmp_path)
 await assistant.command('دور على افلام عندي')
 (videos/'Space.Movie.1080p.mkv').write_bytes(b'changed')
 result=await assistant.command('شغل الاول')
 assert result['status']=='changed' and not calls

@pytest.mark.asyncio
async def test_permission_and_no_false_success(tmp_path):
 assistant,policy,calls,videos=setup_assistant(tmp_path)
 policy.enabled=False
 assert (await assistant.command('رشحلي فيلم على الجهاز'))['status']=='disabled'
 assert not calls
 policy.enabled=True;await assistant.command('دور على افلام عندي')
 policy.enabled=False
 assert (await assistant.command('شغله'))['status']=='disabled' and not calls

@pytest.mark.asyncio
async def test_player_failure_is_reported_without_success(tmp_path):
 assistant,policy,calls,videos=setup_assistant(tmp_path)
 assistant.manager_factory=lambda:NS(policy=policy,launch_direct=lambda *args,**kwargs: (_ for _ in ()).throw(OSError('no player')))
 result=await assistant.command('اختارلي فيلم حلو على جهازي وشغله')
 assert result['status']=='failed'

@pytest.mark.asyncio
async def test_questions_and_other_services_do_not_play(tmp_path):
 assistant,policy,calls,videos=setup_assistant(tmp_path)
 for text in ('ازاي اشغل فيلم على الجهاز','رشحلي فيلم على نتفليكس','متشغلش فيلم على جهازي'):
  assert (await assistant.command(text))=={'matched':False}
 assert not calls

@pytest.mark.asyncio
async def test_named_query_does_not_filter_on_good_movie_boilerplate(tmp_path):
 assistant,policy,calls,videos=setup_assistant(tmp_path)
 result=await assistant.command('دور على فيلم اسمه Winter على الجهاز')
 # Quoted whole request is not a path: query extraction is tested independently.
 assert result['matched']
 result=await assistant.command('دورلي على فيلم حلو على الجهاز')
 assert result['status']=='opened'
