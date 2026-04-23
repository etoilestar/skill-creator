from flask import Blueprint, request
from app.utils.response import success, error
from app.services.skill_service import SkillService
from app.schemas.skill import SkillSchema

skills_bp = Blueprint('skills', __name__, url_prefix='/api/skills')

_schema = SkillSchema()
_schema_many = SkillSchema(many=True)


@skills_bp.route('/', methods=['GET'])
def list_skills():
    status_filter = request.args.get('status')
    skills = SkillService.list_skills(status=status_filter)
    return success(_schema_many.dump(skills))


@skills_bp.route('/<string:skill_id>', methods=['GET'])
def get_skill(skill_id):
    skill = SkillService.get_skill(skill_id)
    if not skill:
        return error('Skill not found', 404)
    return success(_schema.dump(skill))


@skills_bp.route('/<string:skill_id>', methods=['PUT'])
def update_skill(skill_id):
    json_data = request.get_json()
    if not json_data:
        return error('Request body is required', 400)
    skill = SkillService.update_skill(skill_id, json_data)
    if not skill:
        return error('Skill not found', 404)
    return success(_schema.dump(skill))


@skills_bp.route('/<string:skill_id>', methods=['DELETE'])
def delete_skill(skill_id):
    result = SkillService.delete_skill(skill_id)
    if not result:
        return error('Skill not found', 404)
    return success({'message': 'Skill deleted'})


@skills_bp.route('/<string:skill_id>/publish', methods=['POST'])
def publish_skill(skill_id):
    skill = SkillService.publish_skill(skill_id)
    if not skill:
        return error('Skill not found', 404)
    return success(_schema.dump(skill))
