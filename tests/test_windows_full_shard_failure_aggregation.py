"""BARQ Windows release gate must gather all failing test shards without bypass."""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path


def test_shard_diagnosis_continues_after_failure_and_blocks_release(tmp_path,monkeypatch):
    from scripts import run_python_build_tests as gate
    root=tmp_path
    tests=root/'tests'
    tests.mkdir()
    modules=[tests/'test_a.py',tests/'test_b.py',tests/'test_c.py']
    for module in modules:
        module.write_text('def test_example(): pass\n',encoding='utf-8')
    basetemp=root/'safe-basetemp'
    basetemp.mkdir()
    monkeypatch.setattr(gate,'create_safe_pytest_basetemp',lambda:basetemp)
    visited=[]
    isolated_states=[]

    def fake_runner(*,command,root,idle_timeout,total_timeout):
        shard=command[-1]
        visited.append(shard)
        from os import environ
        isolated_states.append(environ.get('AI_ROUTER_DATA_DIR'))
        rel=root/'release'
        if shard.endswith('test_a.py'):
            (rel/'python-tests.log').write_text('FAILED tests/test_a.py::test_example - AssertionError\n',encoding='utf-8')
            (rel/'python-tests-failures.txt').write_text('FAILED tests/test_a.py::test_example\n',encoding='utf-8')
            return 1
        if shard.endswith('test_b.py'):
            (rel/'python-tests.log').write_text('Fatal error from native DLL\n',encoding='utf-8')
            return 3221225477  # 0xC0000005: Windows access violation
        (rel/'python-tests.log').write_text('1 passed\n',encoding='utf-8')
        junit=next(value for value in command if value.startswith('--junitxml=')).split('=',1)[1]
        ET.ElementTree(ET.Element('testsuite',tests='1',errors='0',failures='0',skipped='0')).write(
            junit,encoding='utf-8')
        return 0

    monkeypatch.setattr(gate,'run',fake_runner)
    result=gate.run_sharded_suite(root=root,files=modules,shard_size=1,require_timeout_plugin=False)
    assert result!=0
    assert len(visited)==3, 'Failure in shard 1 must not hide failures or passes in later shards'
    assert all(value is not None for value in isolated_states)
    assert len(set(isolated_states)) == 3
    assert all('state-shard-' in value for value in isolated_states)
    assert not (tmp_path/'safe-basetemp').exists(), 'Temporary build state cleaned up'
    report=json.loads((root/'release/python-tests-shards.json').read_text(encoding='utf-8'))
    assert report['success'] is False and report['processed_shards']==3
    assert report['shards'][0]['exit_code']==1
    assert report['shards'][1]['exit_hex']=='0xC0000005'
    assert report['shards'][2]['exit_code']==0
    failures=(root/'release/python-tests-failures.txt').read_text(encoding='utf-8')
    assert 'SHARD 1/3' in failures and 'SHARD 2/3' in failures
    assert 'test_a.py::test_example' in failures
    assert '0xC0000005' in failures
    assert not (root/'release/python-tests.xml').exists(), 'Never claim a merged green JUnit on failed shards'


def test_runner_extracts_pytest_collection_errors_without_failed_names(tmp_path):
    from scripts.run_python_build_tests import _shard_failure_details
    from xml.etree.ElementTree import Element, SubElement, ElementTree
    report=tmp_path/'failing.xml'
    root=Element('testsuite',tests='1',failures='0',errors='1')
    case=SubElement(root,'testcase',classname='tests.test_dashboard',name='import_fixture')
    SubElement(case,'error',message='ImportError: test fixture unavailable').text=(
        'Traceback: import_fixture -> ImportError: test fixture unavailable')
    ElementTree(root).write(report,encoding='utf-8')
    log=tmp_path/'failing.log'
    log.write_text('ERROR collecting tests/test_dashboard.py\\n',encoding='utf-8')
    cases,reason=_shard_failure_details(log,report)
    assert any('test_dashboard' in name for name in cases)
    assert 'ImportError: test fixture unavailable' in reason


def test_runner_captures_native_crash_tail_without_green_status(tmp_path):
    from scripts.run_python_build_tests import _shard_failure_details
    log=tmp_path/'access-violation.log'
    log.write_text('collection started\\nFatal Python error: access violation at memory address\\n',
                   encoding='utf-8')
    cases,reason=_shard_failure_details(log,tmp_path/'missing.xml')
    assert cases==[]
    assert 'access violation' in reason
