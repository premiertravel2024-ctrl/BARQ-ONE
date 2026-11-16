"""Curated no-key, locally executable coding models for Ollama.

This is a discovery/install GUIDE, not a provider registry. Models are usable
only after the user downloads them with Ollama. Never contact model cloud APIs.
"""
from __future__ import annotations

LOCAL_CODERS = (
    {"name": "qwen2.5-coder:7b", "size_gb": 4.7, "license": "Apache-2.0", "role": "coding", "priority": 100,
     "description_ar": "الاختيار الأساسي لكتابة الكود وإصلاحه على 8GB VRAM"},
    {"name": "deepseek-coder:6.7b", "size_gb": 3.8, "license": "DeepSeek Model License", "role": "coding", "priority": 85,
     "description_ar": "بديل محلي للبرمجة عند تعثر النموذج الأول"},
    {"name": "qwen3:4b", "size_gb": 2.5, "license": "Apache-2.0", "role": "general", "priority": 68,
     "description_ar": "خفيف لفهم الأوامر والتوجيه والمهام البرمجية البسيطة"},
    {"name": "qwen2.5-coder:1.5b", "size_gb": 1.0, "license": "Apache-2.0", "role": "light_coding", "priority": 35,
     "description_ar": "بديل خفيف جدًا، لكن مش مناسب لبناء برامج كبيرة وحده"},
)


def coding_rank(name: str) -> int:
    """Ranking only: never make a model available if not downloaded."""
    tag = name.strip().lower()
    for model in LOCAL_CODERS:
        if tag == model['name']:
            return model['priority']
    if tag in ('qwen2.5-coder:latest', 'qwen2.5-coder'):
        return 100  # Ollama latest tag is currently 7b
    if tag.startswith('qwen2.5-coder:'):
        return 45
    if 'coder' in tag or 'code' in tag:
        return 40
    return 10


def catalog(installed_names=()):
    installed = {str(name).lower() for name in installed_names}
    if 'qwen2.5-coder:latest' in installed:
        installed.add('qwen2.5-coder:7b')
    return [{**model, "installed": model['name'] in installed,
             "install_command": 'ollama pull ' + model['name'], "requires_api_key": False,
             "local_only": True} for model in LOCAL_CODERS]
