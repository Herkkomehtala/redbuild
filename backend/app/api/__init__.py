from flask import Blueprint

# All routes defined in this blueprint will be automatically prefixed with /api
bp = Blueprint('api', __name__)

from . import routes
