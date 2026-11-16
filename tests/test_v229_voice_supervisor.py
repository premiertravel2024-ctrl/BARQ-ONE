"""Safety and bounded recovery regressions for the in-process audio watcher."""
from voice.supervisor import WakeSupervisor


def make_monitor(enabled=True, state='error', detail='temporary device busy'):
    now=[1000.0]
    calls=[]
    info={'running':False,'state':state,'detail':detail}
    m=WakeSupervisor(lambda:enabled, lambda:dict(info),
                     lambda:calls.append(now[0]) or (True,'starting'),
                     lambda:False,clock=lambda:now[0])
    return m,now,calls,info


def test_watcher_retries_with_circuit_breaker_not_infinite_loop():
    monitor,now,calls,_=make_monitor()
    assert monitor.check_once() == 'recovering'
    assert monitor.check_once() == 'cooldown'
    now[0]+=5
    assert monitor.check_once() == 'recovering'
    now[0]+=10
    assert monitor.check_once() == 'recovering'
    now[0]+=30
    assert monitor.check_once() == 'needs_attention'
    assert len(calls)==3
    assert monitor.snapshot()['restart_attempts']==3


def test_watcher_does_not_enable_microphone_without_optin():
    monitor,_,calls,_=make_monitor(enabled=False)
    assert monitor.check_once()=='disabled'
    assert calls==[]


def test_watcher_does_not_interrupt_live_call():
    monitor,_,calls,_=make_monitor()
    monitor.live_active=lambda:True
    assert monitor.check_once()=='in_call'
    assert calls==[]


def test_watcher_does_not_spin_on_missing_runtime_or_permissions():
    monitor,_,calls,_=make_monitor(detail='permission denied')
    assert monitor.check_once()=='needs_attention'
    assert calls==[]


def test_watcher_resets_after_stable_two_minutes():
    monitor,now,calls,info=make_monitor()
    monitor.check_once()
    info.update(running=True,state='listening')
    now[0]+=6
    assert monitor.check_once()=='healthy'
    now[0]+=120
    assert monitor.check_once()=='healthy'
    assert monitor.snapshot()['restart_attempts']==0


def test_wake_endpoint_exposes_supervisor_without_audio_or_secrets():
    from voice.wake import wake_status
    result=wake_status()
    assert result['supervisor']['state']
    assert 'token' not in str(result['supervisor'])
