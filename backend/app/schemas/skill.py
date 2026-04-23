from marshmallow import Schema, fields, EXCLUDE


class SkillSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Str(dump_only=True)
    session_id = fields.Str(required=True)
    name = fields.Str(required=True)
    description = fields.Str(required=True)
    code = fields.Str(required=True)
    spec = fields.Dict(allow_none=True)
    status = fields.Str(dump_only=True)
    test_result = fields.Dict(allow_none=True)
    created_at = fields.DateTime(dump_only=True)
    updated_at = fields.DateTime(dump_only=True)
