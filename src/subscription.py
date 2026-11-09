#!/usr/bin/env python3
"""Private subscription gateway. Run only behind a local HTTPS reverse proxy."""

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import sys
import tempfile
import threading
import time
from urllib.parse import parse_qs, urlsplit


FORMATS = {
    'base64': ('/sub', 'sub.txt', 'text/plain; charset=utf-8'),
    'clash': ('/sub-clash', 'sub-clash.yaml', 'application/yaml; charset=utf-8'),
}
TOKEN_PATTERN = re.compile(r'[A-Za-z0-9_-]{43}\Z')


def validate_origin(value):
    if not isinstance(value, str) or re.search(r'[\s\\?#]', value):
        raise ValueError('订阅地址必须为 HTTPS origin，例如 https://sub.example.com')
    parts = urlsplit(value)
    if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.path not in ('', '/')
            or parts.port == 0):
        raise ValueError('订阅地址必须为 HTTPS origin，不含路径、账号、查询或片段')
    host = parts.hostname
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if len(host) > 253 or not all(
            re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', label)
            for label in host.split('.')
        ):
            raise ValueError('订阅地址的域名无效')
    return value.rstrip('/')


def ttl_seconds(value):
    match = re.fullmatch(r'([1-9][0-9]{0,8})([smhd])', value)
    if not match:
        raise ValueError('有效期格式为正整数加 s/m/h/d，例如 7d')
    seconds = int(match[1]) * {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[match[2]]
    if seconds > 365 * 86400:
        raise ValueError('有效期不能超过 365 天')
    return seconds


def atomic_write(filename, content):
    fd, temporary = tempfile.mkstemp(dir=str(filename.parent), prefix='.config-')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, filename)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).absolute()
        self.database = self.directory / 'tokens.sqlite3'

    def connect(self, readonly=False):
        mode = 'ro' if readonly else 'rw'
        db = sqlite3.connect(self.database.as_uri() + '?mode=' + mode, uri=True, timeout=5)
        db.row_factory = sqlite3.Row
        return db

    def setup(self, origin):
        origin = validate_origin(origin)
        if self.directory.is_symlink():
            raise ValueError('订阅目录不能是符号链接')
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.directory.chmod(0o700)
        if self.database.is_symlink():
            raise ValueError('授权数据库不能是符号链接')
        self.database.touch(mode=0o600, exist_ok=True)
        self.database.chmod(0o600)
        with closing(self.connect()) as db, db:
            db.execute('''CREATE TABLE IF NOT EXISTS grants (
                id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL, format TEXT NOT NULL,
                created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            )''')
        atomic_write(self.directory / 'config.json', json.dumps({'origin': origin}) + '\n')

    def origin(self):
        try:
            config = json.loads((self.directory / 'config.json').read_text(encoding='utf-8'))
            return validate_origin(config['origin'])
        except (KeyError, TypeError, json.JSONDecodeError):
            raise ValueError('订阅配置无效，请重新执行 sub setup') from None

    def validate(self, mode, ttl='7d', name=''):
        if mode not in FORMATS:
            raise ValueError('订阅格式仅支持 base64 / clash')
        seconds = ttl_seconds(ttl)
        if len(name) > 80 or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError('授权名称最多 80 字符，不能含控制字符')
        self.origin()
        with closing(self.connect(readonly=True)) as db:
            db.execute('SELECT id FROM grants LIMIT 1').fetchone()
        return seconds

    def issue(self, mode, ttl='7d', name=''):
        seconds = self.validate(mode, ttl, name)
        content = self.directory / FORMATS[mode][1]
        if not content.is_file() or content.is_symlink() or content.stat().st_size == 0:
            raise ValueError('订阅内容不存在或为空，请先生成订阅')
        token = secrets.token_urlsafe(32)
        created = int(time.time())
        grant = {'id': secrets.token_hex(8), 'name': name, 'format': mode,
                 'created_at': created, 'expires_at': created + seconds}
        with closing(self.connect()) as db, db:
            db.execute('''INSERT INTO grants
                (id, token_hash, name, format, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)''',
                       (grant['id'], hashlib.sha256(token.encode('ascii')).hexdigest(),
                        name, mode, created, grant['expires_at']))
        grant['token'] = token
        grant['url'] = self.origin() + FORMATS[mode][0] + '?token=' + token
        return grant

    def list(self):
        self.origin()
        with closing(self.connect(readonly=True)) as db:
            rows = db.execute('''SELECT id, name, format, created_at, expires_at, revoked
                                 FROM grants ORDER BY created_at, id''').fetchall()
        now = time.time()
        result = []
        for row in rows:
            item = dict(row)
            item['status'] = ('revoked' if item['revoked'] else
                              'expired' if now >= item['expires_at'] else 'active')
            result.append(item)
        return result

    def revoke(self, grant_id):
        with closing(self.connect()) as db, db:
            changed = db.execute('UPDATE grants SET revoked = 1 WHERE id = ?', (grant_id,))
            if changed.rowcount == 0:
                raise ValueError('未找到该授权 ID')

    def authorized(self, token, mode, now=None):
        if not TOKEN_PATTERN.fullmatch(token) or mode not in FORMATS:
            return False
        digest = hashlib.sha256(token.encode('ascii')).hexdigest()
        with closing(self.connect(readonly=True)) as db:
            row = db.execute('''SELECT format, expires_at, revoked FROM grants
                                WHERE token_hash = ?''', (digest,)).fetchone()
        now = time.time() if now is None else now
        return bool(row and row['format'] == mode and row['revoked'] == 0
                    and type(row['expires_at']) is int and now < row['expires_at'])


class SubscriptionHandler(BaseHTTPRequestHandler):
    server_version = 'Subscription'
    sys_version = ''

    def log_message(self, *_args):
        # BaseHTTPRequestHandler logs the full request URL, including credentials.
        pass

    def reply(self, status, body=b'', content_type='text/plain; charset=utf-8'):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Connection', 'close')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)
        self.close_connection = True

    def send_error(self, code, message=None, explain=None):
        self.reply(code, b'Request rejected\n')

    def do_GET(self):
        # Read the original target because the base handler normalizes leading //.
        target = self.raw_requestline.split()[1].decode('iso-8859-1')
        if len(target) > 2048:
            self.reply(414)
            return
        route, separator, query = target.partition('?')
        mode = next((key for key, value in FORMATS.items() if value[0] == route), None)
        if mode is None:
            self.reply(404, b'Not found\n')
            return
        try:
            params = parse_qs(query, keep_blank_values=True, strict_parsing=True,
                              max_num_fields=2)
            tokens = params.get('token', [])
            if set(params) != {'token'} or len(tokens) != 1:
                self.reply(403, b'Forbidden\n')
                return
        except ValueError:
            self.reply(403, b'Forbidden\n')
            return
        try:
            if not self.server.store.authorized(tokens[0], mode):
                self.reply(403, b'Forbidden\n')
                return
            filename = self.server.store.directory / FORMATS[mode][1]
            if filename.is_symlink():
                raise ValueError('invalid content file')
            content = filename.read_bytes()
            if not content:
                raise ValueError('empty content file')
        except (OSError, ValueError, sqlite3.Error):
            self.reply(503, b'Subscription unavailable\n')
            return
        self.reply(200, content, FORMATS[mode][2])

    do_HEAD = do_GET

    def method_not_allowed(self):
        self.reply(405, b'Method not allowed\n')

    do_POST = do_PUT = do_DELETE = do_PATCH = do_OPTIONS = method_not_allowed


class SubscriptionServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, store):
        self.store = store
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, SubscriptionHandler)

    def get_request(self):
        request, address = super().get_request()
        request.settimeout(5)
        return request, address

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def handle_error(self, request, client_address):
        # Avoid tracebacks containing request data; clients receive no content.
        print('订阅请求处理失败', file=sys.stderr)


def make_server(store, port=8787):
    store.origin()
    with closing(store.connect(readonly=True)) as db:
        db.execute('SELECT id FROM grants LIMIT 1').fetchone()
    return SubscriptionServer(('127.0.0.1', port), store)


def timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description='订阅授权管理')
    parser.add_argument('--state-dir', default='/etc/v2ray/subscription')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('setup').add_argument('origin')
    for name in ('issue', 'validate'):
        command = commands.add_parser(name)
        command.add_argument('format', choices=FORMATS)
        command.add_argument('--ttl', default='7d')
        command.add_argument('--name', default='')
    commands.add_parser('list')
    commands.add_parser('revoke').add_argument('id')
    commands.add_parser('serve')
    args = parser.parse_args()
    store = Store(args.state_dir)
    try:
        if args.command == 'setup':
            store.setup(args.origin)
        elif args.command == 'validate':
            store.validate(args.format, args.ttl, args.name)
        elif args.command == 'issue':
            grant = store.issue(args.format, args.ttl, args.name)
            print('授权 ID:', grant['id'])
            print('到期时间 (UTC):', timestamp(grant['expires_at']))
            print('订阅链接 (仅显示一次):', grant['url'])
        elif args.command == 'list':
            print('ID\t名称\t格式\t创建时间 (UTC)\t到期时间 (UTC)\t状态')
            for grant in store.list():
                print('\t'.join([grant['id'], grant['name'], grant['format'],
                                 timestamp(grant['created_at']), timestamp(grant['expires_at']),
                                 grant['status']]))
        elif args.command == 'revoke':
            store.revoke(args.id)
            print('授权已撤销')
        elif args.command == 'serve':
            with make_server(store) as server:
                print('订阅服务监听 127.0.0.1:8787', flush=True)
                server.serve_forever()
    except (OSError, ValueError, sqlite3.Error) as error:
        if isinstance(error, FileNotFoundError):
            message = '订阅尚未配置或文件缺失，请执行 v2ray sub setup https://sub.example.com'
        elif isinstance(error, sqlite3.Error):
            message = '无法读取或写入授权数据库，请检查文件、权限和数据库完整性'
        else:
            message = str(error)
        print('错误: ' + message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == '__main__':
    sys.exit(main())
