from marshmallow import Schema, fields, EXCLUDE


class SkillSpecSchema(Schema):
    class Meta:
        unknown = EXCLUDE

    name = fields.Str(required=True)
    description = fields.Str(required=True)
    input_schema = fields.Dict(load_default=dict)
    output_schema = fields.Dict(load_default=dict)
    dependencies = fields.List(fields.Str(), load_default=list)
    examples = fields.List(fields.Dict(), load_default=list)
