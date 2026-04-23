from flask import Blueprint, request
from app.utils.response import success, error
from app.services.model_config_service import ModelConfigService
from app.schemas.model_config import ModelConfigSchema, ModelConfigCreateSchema

model_configs_bp = Blueprint('model_configs', __name__, url_prefix='/api/model-configs')

_schema = ModelConfigSchema()
_schema_many = ModelConfigSchema(many=True)
_create_schema = ModelConfigCreateSchema()


@model_configs_bp.route('/', methods=['GET'])
def list_model_configs():
    configs = ModelConfigService.list_active()
    return success(_schema_many.dump(configs))


@model_configs_bp.route('/', methods=['POST'])
def create_model_config():
    json_data = request.get_json()
    if not json_data:
        return error('Request body is required', 400)
    errors = _create_schema.validate(json_data)
    if errors:
        return error('Validation failed', 400, details=errors)
    data = _create_schema.load(json_data)
    model_config = ModelConfigService.create(data)
    return success(_schema.dump(model_config), 201)


@model_configs_bp.route('/<string:config_id>', methods=['GET'])
def get_model_config(config_id):
    model_config = ModelConfigService.get(config_id)
    if not model_config:
        return error('Model config not found', 404)
    return success(_schema.dump(model_config))


@model_configs_bp.route('/<string:config_id>', methods=['PUT'])
def update_model_config(config_id):
    json_data = request.get_json()
    if not json_data:
        return error('Request body is required', 400)
    model_config = ModelConfigService.update(config_id, json_data)
    if not model_config:
        return error('Model config not found', 404)
    return success(_schema.dump(model_config))


@model_configs_bp.route('/<string:config_id>', methods=['DELETE'])
def delete_model_config(config_id):
    model_config = ModelConfigService.soft_delete(config_id)
    if not model_config:
        return error('Model config not found', 404)
    return success({'message': 'Model config deactivated'})
