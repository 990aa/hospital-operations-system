"""
Shared Flask extensions module.

Declares extension instances at import time so they can be imported by any
module (routes, tasks, tests) without circular imports.  Each extension is
initialised with the Flask app inside ``create_app()`` in app.py.

Using module-level singletons instead of ``current_app.<ext>`` dynamic lookups
gives static type checkers (ty, mypy) a concrete type to work with, eliminating
``unresolved-attribute`` false positives in route modules.
"""

from flask_caching import Cache
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_smorest import Api
from flask_talisman import Talisman

# Cache singleton – initialised with app.init_app() inside create_app()
cache: Cache = Cache()

# JWT singleton for stateless API authentication
jwt: JWTManager = JWTManager()

# API docs singleton (OpenAPI/Swagger UI)
api_docs: Api = Api()

# Security header middleware singleton
talisman: Talisman = Talisman()

# Rate limiting singleton with Redis fallback to in-memory storage in tests/dev.
limiter: Limiter = Limiter(
	key_func=get_remote_address,
	default_limits=[],
)
