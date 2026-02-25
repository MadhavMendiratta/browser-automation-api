"""Shared rate-limiter instance.

Extracted into its own module so both app.py and auth/routes.py can
import `limiter` without circular dependencies.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request


def get_rate_limit_key(request: Request):
    return get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key)
