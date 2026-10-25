"""只读操作记录查询与云端核验；不重放写请求，不以未观察到变化推断可重试。"""

import json
import os
import re
from pathlib import Path

from mubu.config import MubuError
from mubu.media import MediaService, download_digest
from mubu.node_service import NodeEditor, NodeWriteError
from mubu.nodes import equivalent, indexed

COMMANDS = {'operations', 'operation-status'}


def add_commands(subparsers):
    parser = subparsers.add_parser('operations', help='只读列出本地操作摘要，不输出文档正文')
    parser.add_argument('--doc-id', help='仅列出指定文档的操作')
    parser.add_argument('--limit', type=int, default=20, help='返回数量，1–100，默认 20')
    parser = subparsers.add_parser('operation-status', help='读取操作状态，可只读核验云端结果')
    parser.add_argument('operation_id')
    parser.add_argument('--verify', action='store_true', help='读取云端核验；不重新上传或写入')


def state_dir():
    return Path(os.getenv('MUBU_STATE_DIR', str(Path.home() / '.local/state/mubu-cli')))


def load(operation_id):
    if not re.fullmatch(r'[0-9a-f]{32}', operation_id):
        raise MubuError('无效 operation_id；应为操作返回的 32 位十六进制 ID')
    path = state_dir() / 'operations' / (operation_id + '.json')
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise MubuError('操作记录不存在、无法读取或已损坏') from None
    if not isinstance(record, dict) or record.get('operation_id') != operation_id:
        raise MubuError('操作记录格式无效')
    return record


def summary(record):
    result = record.get('result') or {}
    return {'operation_id': record['operation_id'],
            'doc_id': record.get('before', {}).get('doc_id'),
            'kind': record.get('kind', 'node'),
            'action': record.get('action', result.get('action')),
            'node_id': record.get('node_id', result.get('node_id')),
            'record_status': result.get('status', record.get('status', record.get('stage'))),
            'stage': record.get('stage'), 'retryable': False}


def list_operations(doc_id=None, limit=20):
    if not 1 <= limit <= 100:
        raise MubuError('--limit 必须在 1–100 之间')
    paths = sorted((state_dir() / 'operations').glob('*.json'),
                   key=lambda p: (p.stat().st_mtime_ns, p.name), reverse=True)
    items, invalid = [], 0
    for path in paths:
        try:
            item = summary(load(path.stem))
        except (MubuError, TypeError, AttributeError):
            invalid += 1
            continue
        if doc_id is None or item['doc_id'] == doc_id:
            items.append(item)
        if len(items) > limit:
            break
    return {'operations': items[:limit], 'truncated': len(items) > limit,
            'invalid_records': invalid}


def verify(record, client):
    result = {**summary(record), 'status': 'uncertain', 'executed': False,
              'verification_scope': None,
              'message': '现有证据不足以确认；没有发送写请求，不要直接重试原操作'}
    before = record.get('before', {})
    doc_id = before.get('doc_id')
    if not doc_id:
        raise MubuError('操作记录缺少文档 ID')
    kind = record.get('kind', 'node')
    if kind == 'node':
        if 'expected' not in record or 'changed_ids' not in record:
            result['message'] = '旧记录缺少完整预期结果；请读取目标文档核对，不要直接重试'
            return result
        after = NodeEditor(client).snapshot(doc_id)
        if (after['version'] == before['version'] + 1 and
                equivalent(after['definition'], record['expected'], set(record['changed_ids']))):
            result.update(status='verified', verification_scope='whole_document',
                          version=after['version'], message='当前整篇文档和版本符合原操作预期')
    elif kind == 'image':
        image, node_id = record.get('image'), record.get('node_id')
        if image and node_id:
            after = NodeEditor(client).snapshot(doc_id)
            entry = indexed(after['definition']).get(node_id)
            if entry and image in entry[0].get('images', []):
                result.update(status='observed', verification_scope='image_binding',
                              message='目标节点存在该图片引用；仅核对绑定，不代表整篇文档未变化')
    elif kind == 'attachment':
        attachment_id = record.get('attachment_id')
        if attachment_id:
            service = MediaService(client)
            items = service.attachments(doc_id)
            ids = {item['uuid'] for item in items}
            prior_ids = {item['uuid'] for item in record.get('prior_attachments', [])}
            if attachment_id in ids and prior_ids <= ids:
                data = client._request('GET', '/document/attachment/download', _api_version=4,
                    max_retries=0, params={'doc_id': doc_id, 'attachment_uuid': attachment_id})
                metadata = record['file']
                url = data.get('file_url') if isinstance(data, dict) else None
                if isinstance(url, str) and download_digest(url, metadata['size']) == metadata['sha256']:
                    result.update(status='verified', verification_scope='attachment_content',
                                  message='附件列表及下载内容 SHA-256 符合记录')
    return result


def run(args, client=None):
    if args.command == 'operations':
        return list_operations(args.doc_id, args.limit)
    record = load(args.operation_id)
    if not args.verify:
        return {'status': 'recorded', **summary(record)}
    result = verify(record, client)
    if result['status'] == 'uncertain':
        raise NodeWriteError(result)
    return result
