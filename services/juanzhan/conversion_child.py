"""One resource-limited parser subprocess. Paths originate only from ConverterStore."""
import hashlib
import json
from pathlib import Path
import resource
import sys
import uuid


def parse(directory, options, limits):
    from .uploads import sniff
    with (directory / 'input').open('rb') as file:
        mime = sniff(file, 'input.txt')
    result = {
        'schema_version': '1.0', 'file_revision_id': options['file_revision_id'],
        'parse_run_id': options['parse_run_id'], 'source_mime': mime,
        'parser': {'name': 'juanzhan-utf8-text', 'version': '1.0.0'},
        'status': 'unsupported', 'language': None, 'page_count': None,
        'extraction': {'text_available': False, 'ocr_used': False, 'ocr_languages': []},
        'blocks': [], 'metadata_candidates': [], 'artifacts': [], 'warnings': [],
    }
    if options['generate_preview']:
        result['warnings'].append('PREVIEW_NOT_AVAILABLE')
    if options['declared_mime'] and options['declared_mime'] != mime:
        result['warnings'].append('DECLARED_MIME_MISMATCH')
    # Only truthful UTF-8 text is enabled in T19; six-format conversion is T20.
    if mime == 'text/plain' and options['declared_mime'] in ('', 'text/plain', 'application/octet-stream'):
        try:
            text = (directory / 'input').read_bytes().decode('utf-8-sig')
        except UnicodeDecodeError:
            return {'error': {'code': 'INVALID_TEXT_ENCODING', 'message': 'UTF-8 decoding failed'}}
        if any(ord(char) < 32 and char not in '\t\n\r\f' for char in text):
            return {'error': {'code': 'INVALID_TEXT_CONTENT', 'message': 'Text contains binary control characters'}}
        # Offset ranges refer to decoded Unicode code points, after any UTF-8 BOM.
        blocks = []
        for start in range(0, len(text), 4096):
            if len(blocks) >= limits['max_blocks']:
                return {'error': {'code': 'RESULT_LIMIT', 'message': 'Block limit exceeded'}}
            end = min(len(text), start + 4096)
            blocks.append({'id': f'b{len(blocks)}', 'index': len(blocks), 'type': 'paragraph',
                           'text': text[start:end], 'locator': {'kind': 'character', 'start': start, 'end': end},
                           'confidence': None})
        content = text.encode('utf-8')
        if len(content) > limits['max_output_bytes']:
            return {'error': {'code': 'RESULT_LIMIT', 'message': 'Artifact limit exceeded'}}
        ref = uuid.uuid4().hex
        (directory / ref).write_bytes(content)
        result['status'] = 'completed'
        result['extraction']['text_available'] = bool(text)
        result['blocks'] = blocks
        result['artifacts'] = [{'kind': 'plain_text', 'media_type': 'text/plain; charset=utf-8',
                                'artifact_ref': ref, 'size_bytes': len(content),
                                'sha256': hashlib.sha256(content).hexdigest()}]
    else:
        result['warnings'].append('UNSUPPORTED_INPUT_TYPE')
    return {'result': result}


def main():
    directory = Path(sys.argv[1])
    options = json.loads((directory / 'options.json').read_bytes())
    limits = json.loads((directory / 'limits.json').read_bytes())
    resource.setrlimit(resource.RLIMIT_AS, (limits['memory_bytes'], limits['memory_bytes']))
    resource.setrlimit(resource.RLIMIT_CPU, (limits['cpu_seconds'], limits['cpu_seconds']))
    resource.setrlimit(resource.RLIMIT_FSIZE, (limits['max_output_bytes'], limits['max_output_bytes']))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    result = parse(directory, options, limits)
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > limits['max_output_bytes']:
        encoded = b'{"error":{"code":"RESULT_LIMIT","message":"Result limit exceeded"}}'
    (directory / 'output.json').write_bytes(encoded)


if __name__ == '__main__':
    main()
