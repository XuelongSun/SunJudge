"""Small UTF-8 assignment materials saved with settings, never executed."""
from hashlib import sha256

from .file_validation import FileValidationError

MAX_TEMPLATE_BYTES = 1024 * 1024
MAX_TEMPLATES = 4


def normalize_code_template(filename, content):
    if not isinstance(filename, str) or not filename or len(filename) > 120 or filename.lower() in {'.py', '..py', '.md', '..md'}:
        raise FileValidationError('作业资料文件名无效。')
    if '/' in filename or '\\' in filename or any(ord(char) < 32 or char in ':*?"<>|' for char in filename):
        raise FileValidationError('作业资料文件名不能包含路径或特殊字符。')
    if not filename.lower().endswith(('.py', '.md')):
        raise FileValidationError('作业资料仅支持 .py / .md 文件。')
    if not isinstance(content, str) or not content.lstrip('\ufeff').strip():
        raise FileValidationError('作业资料文件不能为空。')
    try:
        raw = content.encode('utf-8')
        name_bytes = filename.encode('utf-8')
    except UnicodeError:
        raise FileValidationError('作业资料须使用 UTF-8 编码。')
    if len(raw) > MAX_TEMPLATE_BYTES:
        raise FileValidationError('单个作业资料文件不能超过 1 MB。')
    if any(ord(char) < 32 and char not in '\t\n\r\f' for char in content):
        raise FileValidationError('作业资料必须是文本，不能包含二进制字符。')
    return {'id': sha256(name_bytes + b'\0' + raw).hexdigest()[:32],
            'filename': filename, 'content': content, 'file_size': len(raw), 'purpose': ''}


def normalize_code_templates(items):
    if not isinstance(items, list) or len(items) > MAX_TEMPLATES:
        raise FileValidationError('每份作业最多提供 4 个附件，主说明独立编辑。')
    result, names = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise FileValidationError('作业资料数据格式无效。')
        template = normalize_code_template(item.get('filename'), item.get('content'))
        if item.get('is_main', False) is not False:
            raise FileValidationError('作业资料仅包含附件，请在主说明卡片编辑作业说明。')
        purpose = item.get('purpose', '')
        if not isinstance(purpose, str) or len(purpose.strip()) > 120 or any(ord(char) < 32 for char in purpose):
            raise FileValidationError('附件用途须为不超过 120 字的单行文字。')
        template['purpose'] = purpose.strip()
        name = template['filename'].casefold()
        if name in names:
            raise FileValidationError('作业资料文件名不能重复。')
        names.add(name)
        result.append(template)
    return result
