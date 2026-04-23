from app.extensions import db
from app.models.skill import Skill
from app.models.session import SkillSession


class SkillService:
    @staticmethod
    def create_from_session(session_id):
        session = SkillSession.query.filter_by(id=session_id).first()
        if not session or not session.current_spec:
            return None
        spec = session.current_spec
        skill = Skill(
            session_id=session_id,
            name=spec.get('name', 'Unnamed Skill'),
            description=spec.get('description', ''),
            code=spec.get('code', '# TODO: implement'),
            spec=spec,
            status='draft',
        )
        db.session.add(skill)
        db.session.commit()
        return skill

    @staticmethod
    def get_skill(skill_id):
        return Skill.query.filter_by(id=skill_id).first()

    @staticmethod
    def list_skills(status=None):
        query = Skill.query
        if status:
            query = query.filter_by(status=status)
        return query.all()

    @staticmethod
    def update_skill(skill_id, data):
        skill = Skill.query.filter_by(id=skill_id).first()
        if not skill:
            return None
        allowed_fields = ['name', 'description', 'code', 'spec']
        for field in allowed_fields:
            if field in data:
                setattr(skill, field, data[field])
        db.session.commit()
        return skill

    @staticmethod
    def delete_skill(skill_id):
        skill = Skill.query.filter_by(id=skill_id).first()
        if not skill:
            return False
        db.session.delete(skill)
        db.session.commit()
        return True

    @staticmethod
    def publish_skill(skill_id):
        skill = Skill.query.filter_by(id=skill_id).first()
        if not skill:
            return None
        skill.status = 'published'
        db.session.commit()
        return skill
