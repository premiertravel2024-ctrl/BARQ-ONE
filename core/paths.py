"""Portable source resources and writable user state, including packaged Windows builds."""
from pathlib import Path
import os, sys

RESOURCE_ROOT = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
SOURCE_ROOT = Path(__file__).resolve().parents[1]

def data_dir() -> Path:
    custom = os.getenv('AI_ROUTER_DATA_DIR')
    if custom:
        folder = Path(custom).expanduser().resolve()
    elif sys.platform == 'win32':
        folder = Path(os.getenv('LOCALAPPDATA', str(Path.home() / 'AppData/Local'))) / 'AI Router Agent'
    else:
        folder = Path.home() / '.local/share/ai-router-agent'
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def resource(*parts):
    return RESOURCE_ROOT.joinpath(*parts)

def state_file(name):
    return data_dir()/name
