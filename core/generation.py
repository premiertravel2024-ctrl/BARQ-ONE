"""Request-local source-generation settings, separate from chat and JSON plans."""
from contextvars import ContextVar
SOURCE_TARGET=ContextVar('barq_source_target',default=None)
