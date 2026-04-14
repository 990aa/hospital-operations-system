"""Minimal flask-smorest blueprint to expose OpenAPI docs routes."""

from flask.views import MethodView
from flask_smorest import Blueprint
from marshmallow import Schema, fields


docs_blp = Blueprint("docs_meta", __name__, description="Metadata endpoints")


class PingResponseSchema(Schema):
    status = fields.String(required=True)
    service = fields.String(required=True)


@docs_blp.route("/meta/ping")
class MetaPing(MethodView):
    @docs_blp.response(200, PingResponseSchema)
    def get(self):
        return {"status": "ok", "service": "hospital-operations-system"}
