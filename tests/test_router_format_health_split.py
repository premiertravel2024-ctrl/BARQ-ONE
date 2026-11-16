from monitor.health import Health

def test_output_quality_does_not_penalize_provider_health(tmp_path):
    health=Health(str(tmp_path/'health.json'))
    health.report_quality('ollama/qwen3',False)
    assert health.available('ollama/qwen3')
    assert health.snapshot()['ollama/qwen3']['fail']==0
    assert health.snapshot()['ollama/qwen3']['output_quality'] < 1
    another=Health(str(tmp_path/'health.json'))
    assert another.snapshot()['ollama/qwen3']['output_quality'] < 1
