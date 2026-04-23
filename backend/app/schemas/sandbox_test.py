from marshmallow import Schema, fields, EXCLUDE


class SandboxRunSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    id = fields.Str(dump_only=True)
    skill_id = fields.Str(required=True)
    container_id = fields.Str(allow_none=True)
    input_data = fields.Dict(required=True)
    output_data = fields.Dict(allow_none=True)
    stdout = fields.Str(allow_none=True)
    stderr = fields.Str(allow_none=True)
    exit_code = fields.Int(allow_none=True)
    status = fields.Str(dump_only=True)
    started_at = fields.DateTime(allow_none=True)
    finished_at = fields.DateTime(allow_none=True)
    created_at = fields.DateTime(dump_only=True)


class SandboxRunRequestSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    skill_id = fields.Str(required=True)
    input_data = fields.Dict(load_default=dict)
