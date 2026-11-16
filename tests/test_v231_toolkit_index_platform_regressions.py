"""Regression coverage for live index state and Windows PATH discovery."""
from __future__ import annotations

from unittest.mock import patch
from pathlib import Path

import pytest

from services.local_media import discover_movies
from core import tool_locator


@pytest.mark.parametrize('status', ['indexing','idle','failed','index_unavailable','ok'])
def test_empty_or_unready_index_falls_back_to_consented_video_folder(tmp_path, status):
    root = tmp_path / 'Movies'
    root.mkdir()
    (root / 'Only.Movie.1080p.mp4').write_bytes(b'x' * 2_100_000)
    with patch('services.device_index.settings', return_value={'enabled':True}), \
         patch('services.device_index.browse_movies', return_value={'status':status,'movies':[]}) as index, \
         patch('services.local_media._roots', return_value=[root]):
        response = discover_movies([str(root)])
    assert index.call_count == 1
    assert response['status'] == 'ok'
    assert response['movies'][0]['name'] == 'Only Movie'
    assert response['searched_folders'] == ['Movies']


def test_ready_index_with_movies_is_preferred_to_scanning(tmp_path):
    indexed = {'status':'ok','engine':'local-index','movies':[{'name':'Verified Index Hit'}],
               'searched_folders':['فهرس الملفات المحلي']}
    with patch('services.device_index.settings', return_value={'enabled':True}), \
         patch('services.device_index.browse_movies', return_value=indexed), \
         patch('services.local_media._roots', side_effect=AssertionError('Must not scan')):
        assert discover_movies([str(tmp_path)]) is indexed


def test_windows_fixed_tool_locator_used_when_process_path_is_stale(tmp_path):
    pf, local, home = (tmp_path / 'ProgramFiles', tmp_path / 'Local', tmp_path / 'Home')
    git = pf / 'Git' / 'cmd' / 'git.exe'
    git.parent.mkdir(parents=True)
    git.write_bytes(b'test executable placeholder')
    with patch.object(tool_locator.sys, 'platform', 'win32'), \
         patch.object(tool_locator.shutil, 'which', return_value=None), \
         patch.object(tool_locator, '_roots', return_value=(pf, local, home)):
        assert tool_locator.find_tool('git') == str(git.resolve())
