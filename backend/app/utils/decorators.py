import functools
from flask import g


def require_auth(f):
    # Stub: always passes as 'anonymous'. Replace with real JWT/session validation before production use.
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        g.user_id = 'anonymous'
        return f(*args, **kwargs)
    return decorated_function
