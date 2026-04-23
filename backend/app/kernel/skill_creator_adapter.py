import json
import uuid
from datetime import datetime


class SkillCreatorAdapter:
    def send_message(self, session, message, kernel_id=None):
        mock_spec = {
            'name': 'generated_skill',
            'description': f'Skill generated from message: {message[:50]}',
            'input_schema': {
                'type': 'object',
                'properties': {
                    'input': {'type': 'string'}
                }
            },
            'output_schema': {
                'type': 'object',
                'properties': {
                    'output': {'type': 'string'}
                }
            },
            'dependencies': [],
            'examples': [
                {'input': {'input': 'hello'}, 'output': {'output': 'world'}}
            ],
            'code': '# Generated skill\ndef run(input):\n    return {"output": str(input)}',
        }
        return {
            'role': 'assistant',
            'content': json.dumps(mock_spec),
            'spec': mock_spec,
            'timestamp': datetime.utcnow().isoformat(),
        }

    def execute_skill(self, skill_code, input_data, kernel_id=None):
        return {
            'status': 'success',
            'output': {},
            'stdout': '',
            'stderr': '',
        }
