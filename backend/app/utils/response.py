from flask import jsonify


def success(data, status_code=200):
    return jsonify({'success': True, 'data': data}), status_code


def error(message, status_code=400, details=None):
    return jsonify({'success': False, 'error': message, 'details': details}), status_code
