# core/context.py
from contextvars import ContextVar

current_company: ContextVar[str] = ContextVar("current_company", default="default")


def get_company() -> str:
    try:
        return current_company.get()
    except LookupError:
        return "default"
