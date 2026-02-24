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

# Cache singleton – initialised with app.init_app() inside create_app()
cache: Cache = Cache()
