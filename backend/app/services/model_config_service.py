from app.extensions import db
from app.models.model_config import ModelConfig


class ModelConfigService:
    @staticmethod
    def list_active():
        return ModelConfig.query.filter_by(is_active=True).all()

    @staticmethod
    def get(config_id):
        return ModelConfig.query.filter_by(id=config_id, is_active=True).first()

    @staticmethod
    def create(data):
        model_config = ModelConfig(**data)
        db.session.add(model_config)
        db.session.commit()
        return model_config

    @staticmethod
    def update(config_id, data):
        model_config = ModelConfig.query.filter_by(id=config_id, is_active=True).first()
        if not model_config:
            return None
        allowed_fields = ['name', 'provider', 'model_id', 'api_base', 'api_key_env',
                          'max_tokens', 'temperature']
        for field in allowed_fields:
            if field in data:
                setattr(model_config, field, data[field])
        db.session.commit()
        return model_config

    @staticmethod
    def soft_delete(config_id):
        model_config = ModelConfig.query.filter_by(id=config_id, is_active=True).first()
        if not model_config:
            return None
        model_config.is_active = False
        db.session.commit()
        return model_config
