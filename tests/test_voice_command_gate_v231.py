from voice.command_guard import VoiceCommandGate


def test_direct_command_is_consumed_once():
    gate=VoiceCommandGate();gate.record('يا برق افتح المفكرة',now=100)
    assert gate.check('open_on_computer',{'request':'افتح المفكرة'},now=105)[0]
    assert not gate.check('open_on_computer',{'request':'افتح المفكرة'},now=106)[0]


def test_background_phrase_or_unrelated_tool_is_denied():
    gate=VoiceCommandGate();gate.record('التلفزيون بيقول قصة عن العرب',now=5)
    assert not gate.check('start_computer_task',{'goal':'افتح المفكرة'},now=6)[0]
    gate.record('افتح المفكرة',now=10)
    assert not gate.check('open_on_computer',{'request':'افتح كروم'},now=11)[0]
    assert not gate.check('open_on_computer',{'request':'افتح المفكرة'},now=30)[0]


def test_negated_speech_and_voice_without_transcription():
    gate=VoiceCommandGate()
    assert not gate.check('start_computer_task',{'goal':'اكتب ملف'},now=2)[0]
    gate.record('لا تفتح البرنامج',now=5)
    assert not gate.check('open_on_computer',{'request':'افتح البرنامج'},now=6)[0]


def test_read_only_status_still_works():
    # Stopping a running process changes device state and requires grounded speech.
    assert not VoiceCommandGate().check('stop_computer_task',{},now=1)[0]
    assert VoiceCommandGate().check('computer_task_status',{},now=1)[0]


def test_quick_volume_is_grounded_in_transcript():
    gate=VoiceCommandGate();gate.record('علي الصوت شوية',now=100)
    assert gate.check('control_windows_setting',{'setting':'volume','action':'up'},now=101)[0]
