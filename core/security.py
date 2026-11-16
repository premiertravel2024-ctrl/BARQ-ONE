"""Child subprocesses must never receive LLM API keys from the router process."""
import os

def child_env(extra=None):
    env={key:value for key,value in os.environ.items() if not (
        key.endswith('_API_KEY') or key.endswith('_TOKEN') or key in {
            'GROQ_API_KEY','GEMINI_API_KEY','OPENROUTER_API_KEY',
            'GITHUB_TOKEN','GH_TOKEN','HF_TOKEN','MISTRAL_API_KEY',
            'CEREBRAS_API_KEY','CLOUDFLARE_API_KEY'})}
    if extra:
        for key,value in extra.items():
            if not key.isidentifier() or len(key)>80 or len(str(value))>8192:raise ValueError('Invalid subprocess environment override')
            if key.endswith('_API_KEY') or key.endswith('_TOKEN'):raise ValueError('Cannot forward cloud API credentials to tools')
            env[key]=str(value)
    return env
