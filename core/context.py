# core/context.py
from contextvars import ContextVar

current_company: ContextVar[str] = ContextVar("current_company", default="default")
