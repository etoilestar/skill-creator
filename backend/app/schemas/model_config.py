from marshmallow import Schema, fields, EXCLUDE


class ModelConfigSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Str(dump_only=True)
    name = fields.Str(required=True)
    provider = fields.Str(required=True)
    model_id = fields.Str(required=True)
    api_base = fields.Str(allow_none=True)
    api_key_env = fields.Str(load_only=True)
    max_tokens = fields.Int(load_default=4096)
    temperature = fields.Float(load_default=0.7)
    is_active = fields.Bool(dump_default=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)


class ModelConfigCreateSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True)
    provider = fields.Str(required=True)
    model_id = fields.Str(required=True)
    api_base = fields.Str(allow_none=True, load_default=None)
    api_key_env = fields.Str(required=True)
    max_tokens = fields.Int(load_default=4096)
    temperature = fields.Float(load_default=0.7)
