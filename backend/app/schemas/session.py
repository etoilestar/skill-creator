from marshmallow import Schema, fields, EXCLUDE
from app.schemas.skill_spec import SkillSpecSchema


class SessionSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Str(dump_only=True)
    model_config_id = fields.Str(required=True)
    user_id = fields.Str(allow_none=True)
    status = fields.Str(dump_only=True)
    context = fields.List(fields.Dict(), dump_default=list)
    current_spec = fields.Nested(SkillSpecSchema, allow_none=True)
    kernel_id = fields.Str(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
