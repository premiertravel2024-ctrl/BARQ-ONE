"""Never return secrets to the browser. Prefer OS credential store; .env still supported."""
import os

def get(name):
    from dotenv import load_dotenv
    load_dotenv(override=False)
    try:
        import keyring
        stored=keyring.get_password('AI Router Agent', name)
        if stored:
            return stored
    except Exception:
        pass
    return os.getenv(name,'')

def set_secret(name, value):
    from router.config import bundled_providers
    allowed={p.get('api_key_env') for p in bundled_providers().values() if p.get('api_key_env')}|{'GITHUB_TOKEN'}
    if name not in allowed:raise ValueError('Unsupported key type')
    if not value.strip() or len(value)>512:raise ValueError('Invalid API key length')
    try:
        import keyring
        keyring.set_password('AI Router Agent',name,value.strip())
        if keyring.get_password('AI Router Agent',name)!=value.strip():
            raise RuntimeError('Credential store did not confirm persistence')
    except Exception as exc:
        raise RuntimeError('Could not securely store key using Windows Credential Manager') from exc
