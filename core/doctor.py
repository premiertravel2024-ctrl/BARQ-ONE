"""Non-secret diagnostics visible inside the Windows desktop application."""
import importlib.util
import os,platform,shutil,sys
from core.secrets import get
from mcp.bridge import describe

PROVIDER_KEYS=('GEMINI_API_KEY','GROQ_API_KEY','OPENROUTER_API_KEY','MISTRAL_API_KEY','CEREBRAS_API_KEY','HF_TOKEN','CLOUDFLARE_API_KEY')

def module_present(name):
    try:return bool(importlib.util.find_spec(name))
    except (ImportError,ModuleNotFoundError,ValueError):return False

def report():
    return {
       'platform':platform.system(),
       'architecture':platform.machine(),
       'python':platform.python_version(),
       'packaged':bool(getattr(sys,'frozen',False)),
       'windows_build_available':sys.platform=='win32',
       'runtimes':{name:bool(shutil.which(name)) for name in ('git','gh','node','npx','npm','rustc','cargo','pyinstaller','ISCC.exe','ollama')},
       'sdk':{name:module_present(name) for name in ('google.genai','webview','keyring','fitz','docx','openpyxl')},
       'providers':{name:bool(get(name)) for name in PROVIDER_KEYS},
       'mcp':describe(),
       'notes':['Credentials are never included in this report',
                'An installed runtime is not proof that a real project will build',
                'Actual provider and MCP connections require live account/system tests']
    }
