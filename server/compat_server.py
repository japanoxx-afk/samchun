"""3KD2 1.20g private Internet compatibility service.
Wire layouts are derived from the original client's packet builders/consumers.
No original service, credentials or game files are contacted/distributed.
"""
import argparse
from contextlib import contextmanager
import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import queue
import hashlib
import hmac
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import secrets
import socket
import socketserver
import sqlite3
import struct
import threading
import time

LOG = logging.getLogger('samchun')
HEADER = struct.Struct('<IBH')
MAX_PACKET = 1024
SERVER_VERSION = '1.3.60'

# Ladder (same rule as the RhakMu lobby server / RTS ARENA site):
# score = 1000 + 10*win - 10*loss, never below 0; order score desc, wins desc,
# losses asc, name. Outcome 4 (native "too short / no contest") never counts.
POINTS_BASE, POINTS_WIN, POINTS_LOSE = 1000, 10, 10
# Native ranking page (4b9770) asks for 7 ranks; a 0x78 reply holds at most
# (1024-7-8)//101 = 9 personal records.
RANK_RECORD = 101
RANK_PAGE_MAX = (MAX_PACKET - 7 - 8) // RANK_RECORD
OUTCOME_CODES = {1: 'win', 2: 'lose', 3: 'draw'}
OUTCOME_NAMES = {1: 'win', 2: 'lose', 3: 'draw', 4: 'no-contest(short game or abort, not counted)'}
DB_OPS = (1, 2, 3, 0x0a, 0x0b)
RELAY_BACKLOG_LIMIT = 8*1024*1024   # bytes queued for one slow receiver before it is dropped

def transport_id(account_id):
    # Native 42ACA0 treats 0 as broadcast and 1 as the room-host alias.
    # A host silently skips unicast destination 1 (42AD06..42AD4B).
    # Database identity must never be used directly as a peer destination.
    if not 1 <= account_id <= 0xfffffffc:
        raise ValueError('account identity outside native transport range')
    return account_id + 1

def u32(b, offset=0):
    return struct.unpack_from('<I', b, offset)[0]

def put32(b, offset, value):
    struct.pack_into('<I', b, offset, value)

def text(b, offset, length):
    return bytes(b[offset:offset+length]).split(b'\0', 1)[0].decode('cp949', 'replace')

def puttext(b, offset, length, value):
    encoded = value.encode('cp949', 'replace')[:length-1]
    b[offset:offset+length] = encoded.ljust(length, b'\0')

def packet(op, body=b''):
    if len(body)+7 > MAX_PACKET:
        raise ValueError('packet too large')
    return HEADER.pack(0xffffffff, op, len(body)+7)+body

def read_exact(stream, length):
    data = bytearray()
    while len(data) < length:
        block = stream.recv(length-len(data))
        if not block:
            raise EOFError()
        data.extend(block)
    return bytes(data)

class Accounts:
    """Account/result store. One process owns the file; every access is serialized
    by a process lock so the database also works on network volumes (NAS/VM
    shares) whose file locking is unreliable ("database is locked")."""
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.RLock()
        # 1.3.60: SQLite file locking is OFF by default. This process is the only user of
        # the file and serializes every access with self.lock; on the NAS share the file
        # locks got stuck ("database is locked" on every write after a game, so results
        # were lost and re-login timed out with "network error"). SAMCHUN_SQLITE_LOCKING=1
        # turns file locking back on for local disks.
        self.nolock = os.environ.get('SAMCHUN_SQLITE_LOCKING') != '1'
        self.pending = []        # results that could not be written yet (retried in the background)
        self.rank_cache = None   # ranking() result until the next stored result/participant
        try:
            self.create()
        except sqlite3.OperationalError as e:
            if self.nolock or 'locked' not in str(e):
                raise
            LOG.warning('database file locking unavailable (%s); using process lock only', e)
            self.nolock = True
            self.create()
    def create(self):
        with self.db() as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS match_results (match_id TEXT NOT NULL, user_id INTEGER NOT NULL, outcome INTEGER NOT NULL, recorded_at INTEGER NOT NULL, PRIMARY KEY(match_id,user_id))')
            db.execute('CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE, salt BLOB NOT NULL, digest BLOB NOT NULL)')
            # 1.3.58: match metadata for the ranking site (RTS ARENA). Results
            # recorded before this version have no row here and still count.
            db.execute('CREATE TABLE IF NOT EXISTS matches (match_id TEXT PRIMARY KEY, room_id INTEGER, title TEXT, map TEXT, started_at INTEGER NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS match_players (match_id TEXT NOT NULL, user_id INTEGER NOT NULL, joined_at INTEGER NOT NULL, PRIMARY KEY(match_id,user_id))')
    @contextmanager
    def db(self):
        with self.lock:
            if self.nolock:
                connection = sqlite3.connect(Path(self.path).resolve().as_uri()+'?nolock=1', uri=True, timeout=2)
            else:
                connection = sqlite3.connect(self.path, timeout=2)
            try:
                yield connection
            finally:
                connection.close()
    def authenticate(self, name, password, register=False):
        if not 1 <= len(name.encode('cp949', 'replace')) <= 15 or len(password.encode('cp949', 'replace')) > 10:
            return None
        if register:
            salt = secrets.token_bytes(24)
            digest = hashlib.pbkdf2_hmac('sha256', password.encode('cp949'), salt, 600000)
            with self.db() as db, db:
                try:
                    row = db.execute('INSERT INTO accounts(name,salt,digest) VALUES (?,?,?)', (name, salt, digest))
                    return row.lastrowid, name
                except sqlite3.IntegrityError:
                    return None
        with self.db() as db:
            row = db.execute('SELECT id,name,salt,digest FROM accounts WHERE name=?', (name,)).fetchone()
        # Key stretching runs outside the database lock (and also for unknown names).
        salt = row[2] if row else bytes(24)
        digest = hashlib.pbkdf2_hmac('sha256', password.encode('cp949'), salt, 600000)
        if row and hmac.compare_digest(row[3], digest):
            return row[0], row[1]
        return None

    def record_result(self, match_id, uid, outcome):
        if not match_id or outcome not in (1, 2, 3, 4):
            return False
        try:
            return self.write_result(match_id, uid, outcome)
        except sqlite3.Error as e:
            # Never lose a finished game's result because the disk is busy: keep it and retry.
            LOG.warning('result kept for retry (%s): match=%s user=%d outcome=%d', e, match_id, uid, outcome)
            with self.lock:
                self.pending.append((match_id, uid, outcome, int(time.time())))
            return False
    def retry_pending(self):
        with self.lock:
            todo, self.pending = self.pending, []
        for match_id, uid, outcome, at in todo:
            try:
                with self.db() as db, db:
                    if db.execute('INSERT OR IGNORE INTO match_results VALUES (?,?,?,?)', (match_id, uid, outcome, at)).rowcount:
                        self.rank_cache = None
                LOG.info('kept result stored: match=%s user=%d outcome=%d', match_id, uid, outcome)
            except sqlite3.Error:
                with self.lock:
                    self.pending.append((match_id, uid, outcome, at))
        return not self.pending
    def write_result(self, match_id, uid, outcome):
        with self.db() as db, db:
            row = db.execute('INSERT OR IGNORE INTO match_results VALUES (?,?,?,?)',
                             (match_id, uid, outcome, int(time.time())))
            if row.rowcount == 1:
                self.rank_cache = None
            return row.rowcount == 1
    def forfeit(self, match_id, winner):
        """1:1 match: the opponent of a reported win who left without any result loses.
        Returns the opponent's account name when a loss was recorded."""
        with self.db() as db, db:
            ids = [r[0] for r in db.execute('SELECT user_id FROM match_players WHERE match_id=?', (match_id,))]
            if len(ids) != 2 or winner not in ids:
                return None
            other = ids[0] if ids[1] == winner else ids[1]
            row = db.execute('INSERT OR IGNORE INTO match_results VALUES (?,?,?,?)', (match_id, other, 2, int(time.time())))
            if row.rowcount != 1:
                return None
            self.rank_cache = None
            name = db.execute('SELECT name FROM accounts WHERE id=?', (other,)).fetchone()
            return name[0] if name else str(other)
    def record_match(self, match_id, room_id, title, map_name, user_id):
        """Remember that an account entered the native game transport of a match."""
        now = int(time.time())
        with self.db() as db, db:
            db.execute('INSERT OR IGNORE INTO matches VALUES (?,?,?,?,?)', (match_id, room_id, title, map_name, now))
            db.execute('INSERT OR IGNORE INTO match_players VALUES (?,?,?)', (match_id, user_id, now))
            self.rank_cache = None

    # A result counts when its match had two or more accounts in the game
    # transport (no single-player games), or when it predates match tracking.
    COUNTED = ('r.outcome IN (1,2,3) AND (NOT EXISTS (SELECT 1 FROM matches m WHERE m.match_id=r.match_id)'
               ' OR (SELECT COUNT(*) FROM match_players p WHERE p.match_id=r.match_id) >= 2)')

    def ranking(self):
        """Every account with a counted result, best first. Rank starts at 1."""
        cached = self.rank_cache
        if cached is not None:
            return cached
        with self.db() as db:
            rows = db.execute(
                'SELECT a.name, SUM(r.outcome=1), SUM(r.outcome=2), SUM(r.outcome=3), MAX(r.recorded_at)'
                ' FROM match_results r JOIN accounts a ON a.id=r.user_id WHERE ' + self.COUNTED +
                ' GROUP BY a.id').fetchall()
        out = []
        for name, w, l, d, last in rows:
            out.append({'name': name, 'win': w, 'lose': l, 'draw': d, 'games': w + l + d, 'last': last,
                        'score': max(0, POINTS_BASE + POINTS_WIN * w - POINTS_LOSE * l)})
        out.sort(key=lambda r: (-r['score'], -r['win'], r['lose'], r['name']))
        for i, r in enumerate(out, 1):
            r['rank'] = i
        self.rank_cache = out
        return out

    def player(self, name):
        """(ranking row or None, account name or None) for a case-insensitive name."""
        with self.db() as db:
            row = db.execute('SELECT name FROM accounts WHERE name=?', (name,)).fetchone()
        if not row:
            return None, None
        return next((r for r in self.ranking() if r['name'] == row[0]), None), row[0]

    @staticmethod
    def native_record(row, name=''):
        """101-byte personal ranking record (native 4b9770 / 4f7cc9 layout).

        0 name[16] · 16 guild text (unused) · 57 win · 59 lose · 61 draw ·
        63 games · 65 score · 67 Tr · 69 HF (u16) · 71 rank (u32) · 75 u32.
        The 0x7a statistics reply is the first 80 bytes of the same record.
        """
        b = bytearray(RANK_RECORD)
        puttext(b, 0, 16, row['name'] if row else name)
        if row:
            for offset, key in ((57, 'win'), (59, 'lose'), (61, 'draw'), (63, 'games'), (65, 'score')):
                struct.pack_into('<H', b, offset, min(row[key], 65535))
            put32(b, 71, row['rank'])
        else:
            struct.pack_into('<H', b, 65, POINTS_BASE)
        return b

    def statistics(self, name):
        row, account = self.player(name)
        return bytes(self.native_record(row, account or name)[:80])

    def ranking_page(self, first, last):
        """(first, last, records) clamped to existing ranks, or None when nobody is ranked."""
        rows = self.ranking()
        if not rows:
            return None
        first = max(1, first)
        if first > len(rows):  # paging past the end shows the last page
            first = max(1, len(rows) - 6)
        last = min(max(first, last), len(rows), first + RANK_PAGE_MAX - 1)
        return first, last, [self.native_record(r) for r in rows[first-1:last]]

    def export_matches(self):
        """Lobby match history in the RhakMu matches.json shape used by RTS ARENA."""
        with self.db() as db:
            matches = db.execute('SELECT match_id, room_id, title, map, started_at FROM matches ORDER BY started_at, rowid').fetchall()
            players = db.execute('SELECT p.match_id, a.name FROM match_players p JOIN accounts a ON a.id=p.user_id ORDER BY p.joined_at, a.name').fetchall()
            results = db.execute('SELECT r.match_id, a.name, r.outcome, r.recorded_at FROM match_results r JOIN accounts a ON a.id=r.user_id').fetchall()
        names, outcome = {}, {}
        for mid, name in players:
            names.setdefault(mid, []).append(name)
        for mid, name, code, at in results:
            if code in OUTCOME_CODES:
                outcome.setdefault(mid, {})[name] = {'code': code, 'at': local_time(at)}
        out = []
        for mid, rid, title, map_name, started in matches:
            out.append({'id': mid, 'time': local_time(started), 'room': title or '', 'map': map_name or '',
                        'players': names.get(mid, []), 'results': outcome.get(mid, {})})
        return out

def local_time(epoch):
    return datetime.datetime.fromtimestamp(epoch).strftime('%Y-%m-%d %H:%M:%S')

def room_map(record):
    """Best-effort map file name inside an opaque 207-byte native room record."""
    for chunk in bytes(record[36:]).split(b'\0'):
        name = chunk.decode('cp949', 'replace').strip()
        if name.lower().endswith('.map') and 4 < len(name) < 64 and name.isprintable():
            return name.replace('\\', '/').rsplit('/', 1)[-1][:-4]
    return ''

class World:
    def __init__(self, database):
        self.accounts = Accounts(database)
        self.lock = threading.RLock()
        self.clients = set()
        self.rooms = {}
        self.channels = {1: self.channel_record(1, 'Lobby')}
        self.next_room = 100
        self.next_channel = 2
        self.auth_attempts = {}
        self.relays = {}
        self.export_path = None  # matches.json for the ranking site (optional)
        self.export_lock = threading.Lock()
    def forfeit_leavers(self, match_id, winner_account):
        """A 1:1 winner reported; the opponent who dropped out without a result gets a loss
        (otherwise leaving a lost game would erase the loss). Skipped while the opponent is
        still in the game transport: their own result will arrive."""
        with self.lock:
            if any(r.match_id == match_id and r.account_id != winner_account for r in self.relays.values()):
                return
        try:
            name = self.accounts.forfeit(match_id, winner_account)
        except sqlite3.Error:
            LOG.exception('forfeit not stored')
            return
        if name:
            LOG.info('forfeit loss recorded for %s (left 1:1 match without a result)', name)
    def export(self):
        if not self.export_path:
            return
        try:
            with self.export_lock:
                data = json.dumps(self.accounts.export_matches(), ensure_ascii=False, indent=1)
                temp = self.export_path.with_name(self.export_path.name+'.tmp')
                temp.write_text(data, encoding='utf-8')
                os.replace(temp, self.export_path)
        except (OSError, sqlite3.Error):
            LOG.exception('matches.json export failed')
    @staticmethod
    def channel_record(cid, name):
        b = bytearray(119)
        put32(b, 0, cid)
        puttext(b, 4, 32, name)
        return b
    def broadcast(self, op, body, channel=None):
        for client in tuple(self.clients):
            if client.uid and (channel is None or client.channel == channel):
                client.send(op, body)
    def room_list(self, client):
        # 0x7f: count followed by action + 207-byte native room records.
        rooms = list(self.rooms.values())
        if not rooms:
            client.send(0x7f, struct.pack('<I', 0))
        for room in rooms:
            client.send(0x7f, struct.pack('<I', 1)+b'\x01'+room['record'])
    def users(self, client):
        peers = [c for c in self.clients if c.uid and c.channel == client.channel]
        if not peers:
            client.send(0x79, struct.pack('<I', 0))
        for peer in peers:
            b = bytearray(38)
            put32(b, 0, peer.uid)
            b[5] = 1
            put32(b, 6, peer.uid)
            put32(b, 10, client.uid)
            puttext(b, 14, 16, peer.name)
            client.send(0x79, struct.pack('<I', 1)+b)
    def channel_list(self, client):
        for record in self.channels.values():
            client.send(0x8d, struct.pack('<I', 1)+b'\x01'+record)
    def remove_room(self, room_id):
        room = self.rooms.pop(room_id, None)
        if room:
            self.broadcast(0x7f, struct.pack('<I', 1)+b'\x02'+room['record'])
    def disconnect(self, client):
        with self.lock:
            self.clients.discard(client)
            for rid, room in list(self.rooms.items()):
                if room['owner'] is client:
                    self.remove_room(rid)
                else:
                    room['members'].discard(client.uid)
            if client.uid:
                b = bytearray(38)
                put32(b, 0, client.uid)
                b[5] = 3
                self.broadcast(0x79, struct.pack('<I', 1)+b, client.channel)

class LobbyHandler(socketserver.BaseRequestHandler):
    def setup(self):
        self.world = self.server.world
        self.uid = 0
        self.account_id = 0
        self.name = ''
        self.channel = 1
        self.room = 0
        self.match_id = None
        self.match_relay = False
        self.send_lock = threading.Lock()
        self.request.settimeout(30)
        self.request.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        self.record = bytearray(485)
        self.last_message = 0
        with self.world.lock:
            self.world.clients.add(self)
    def send(self, op, body=b''):
        try:
            with self.send_lock:
                self.request.sendall(packet(op, body))
        except (OSError, ValueError):
            pass
    def handle(self):
        LOG.info('client connected: %s', self.client_address[0])
        try:
            while True:
                marker, op, size = HEADER.unpack(read_exact(self.request, 7))
                if marker != 0xffffffff or not 7 <= size <= MAX_PACKET:
                    raise ValueError('invalid frame')
                body = read_exact(self.request, size-7)
                # Intentionally never log account/password payloads.
                LOG.info('request op=%02x size=%d authenticated=%s', op, size, bool(self.uid))
                if op in (0x0c, 0x30):
                    self.login(op, body)
                elif op in DB_OPS and self.uid:
                    # Database work (results, statistics, ranking) never holds the
                    # world lock: game relay forwarding takes that lock per frame,
                    # so a slow disk (NAS share) must not stall running matches.
                    self.dispatch_db(op, body)
                else:
                    with self.world.lock:
                        self.dispatch(op, body)
        except (OSError, EOFError, ValueError, struct.error):
            pass
        except Exception:
            LOG.exception('request failed (payload omitted)')
    def finish(self):
        self.world.disconnect(self)
        LOG.info('client disconnected: %s', self.client_address[0])
    def login(self, op, body):
        if self.uid or len(body) != 145:
            self.send(0x94, b'\x00')
            return
        now = time.monotonic()
        with self.world.lock:
            key = self.client_address[0]
            attempts = [t for t in self.world.auth_attempts.get(key, []) if now-t < 60]
            if len(attempts) >= 12:
                self.send(0x94, b'\x00')
                return
            attempts.append(now)
            self.world.auth_attempts[key] = attempts
            if len(self.world.auth_attempts) > 2048:
                self.world.auth_attempts = {k:v for k,v in self.world.auth_attempts.items() if v and now-v[-1] < 60}
        try:
            result = self.world.accounts.authenticate(text(body, 0, 16), text(body, 16, 11), op == 0x30)
        except sqlite3.Error as e:
            LOG.warning('login database unavailable: %s', e)
            result = None
        if not result:
            self.send(0x94, b'\x01' if op == 0x30 else b'\x00')
            return
        with self.world.lock:
            if any(c.account_id == result[0] for c in self.world.clients):
                self.send(0x94, b'\x03')
                return
            self.account_id, self.name = result
            self.uid = transport_id(self.account_id)
            LOG.info('authenticated account=%d peer=%d identity-policy=reserved-0-1', self.account_id, self.uid)
            # Authenticated players may remain in a match without lobby requests.
            self.request.settimeout(None)
            put32(self.record, 0, self.uid)
            puttext(self.record, 4, 16, self.name)
            self.send(0x94, b'\x02'+self.record+b'\x07')  # trailing faction mask: three pairs
    def dispatch(self, op, b):
        if op == 0x13:  # Start/stop asynchronous native receive workers.
            return
        if op == 9:
            raise EOFError()
        if not self.uid:
            self.send(0x93, bytes(4))
            return
        if op == 0x0d:  # lobby entered after authentication
            self.world.users(self)
        elif op == 0x10:
            self.world.room_list(self)
        elif op == 0x21:
            # user/profile list; single 485-byte record fits native receive buffer
            peers = [c for c in self.world.clients if c.uid]
            if not peers:
                self.send(0x83, struct.pack('<I', 0))
            for peer in peers:
                self.send(0x83, struct.pack('<I', 1)+b'\x01'+peer.record)
            self.world.users(self)
        elif op == 0x2b:
            self.world.channel_list(self)
        elif op == 0x28 and len(b) == 119:
            name = text(b, 4, 32).strip()
            if not name or len(self.world.channels) >= 100:
                self.send(0x8c, b'\x07'+struct.pack('<I', 0)+bytes(119))
                return
            cid = self.world.next_channel
            self.world.next_channel += 1
            record = self.world.channel_record(cid, name)
            self.world.channels[cid] = record
            self.channel = cid
            self.send(0x8c, b'\x01'+bytes(4)+record)
            self.world.broadcast(0x8d, struct.pack('<I', 1)+b'\x01'+record)
            self.world.users(self)
        elif op == 0x29 and len(b) == 4:
            cid = u32(b)
            if cid not in self.world.channels:
                self.send(0x8c, bytes(124))
                return
            self.channel = cid
            self.send(0x8c, b'\x01'+bytes(4)+self.world.channels[cid])
            self.world.users(self)
        elif op == 0x2a:
            self.channel = 1
            self.send(0x8c, b'\x01'+bytes(4)+self.world.channels[1])
        elif op == 0x1e and len(b) == 485:
            self.send(0x82, b'\x01'+self.record)
        elif op == 0x1f:
            self.send(0x82, b'\x01'+self.record)
        elif op in (0x2d, 0x2e, 0x2f, 0x31, 5):
            # Guild ranking/search/lookup: guilds are not implemented. 0x93 is
            # the native "no rows" reply (4f7fa0 sets count 0, 4f7df0 fails).
            self.send(0x93, bytes(4))
        elif op == 7 and 30 <= len(b) <= 230:
            now = time.monotonic()
            if now-self.last_message < .3:
                return
            self.last_message = now
            clean = bytearray(b)
            puttext(clean, 5, 16, self.name)
            clean[-1] = 0
            self.world.broadcast(7, clean, self.channel)
        elif op == 0x0e and len(b) == 207:
            # Native game-room setup also needs its separate TCP 4901 transport.
            if any(r['owner'] is self for r in self.world.rooms.values()):
                self.send(0x7e, bytes(350))
                return
            rid = self.world.next_room
            self.world.next_room += 1
            record = bytearray(b)
            put32(record, 0, rid)
            # A zero relay IP makes the client use the lobby peer address.
            put32(record, 0xb7, 0)
            put32(record, 195, rid)
            put32(record, 203, self.uid)
            self.world.rooms[rid] = dict(record=record, owner=self, members={self.uid}, match_id=secrets.token_hex(16))
            self.room = rid
            self.send_room(rid)
            self.world.broadcast(0x7f, struct.pack('<I', 1)+b'\x01'+record)
        elif op == 0x0f and len(b) == 4:
            rid = u32(b)
            room = self.world.rooms.get(rid)
            if not room or len(room['members']) >= 8:
                self.send(0x7e, b'\x06'+bytes(349))
                return
            room['members'].add(self.uid)
            self.room = rid
            self.send_room(rid)
        elif op == 0x11:
            room = self.world.rooms.get(self.room)
            if room and room['owner'] is self:
                self.world.remove_room(self.room)
            elif room:
                room['members'].discard(self.uid)
            self.room = 0
            # Native 42cf80 never consumes a leave response. Sending 0x7e here
            # poisons the next create/join response queue with an empty session.
        elif op == 0x12 and len(b) == 150:
            # Session status is opaque until native transport validation completes.
            return
        else:
            LOG.info('unimplemented request op=%02x size=%d', op, len(b)+7)
            self.send(0x93, bytes(4))
    def dispatch_db(self, op, b):
        try:
            self.dispatch_db_checked(op, b)
        except sqlite3.Error as e:
            # A busy/broken disk must never drop the player (1.3.59 disconnected them and the
            # client then showed "network error"): answer with what the game can always use.
            LOG.warning('database unavailable for op=%02x: %s', op, e)
            if op == 2 and len(b) == 17:
                self.send(0x7a, bytes(Accounts.native_record(None, text(b,1,16) or self.name)[:80]))
            elif op in (3, 0x0a, 0x0b):
                self.send(0x93, bytes(4))
    def dispatch_db_checked(self, op, b):
        if op == 1 and len(b) == 683:
            # A result often arrives AFTER room-leave; retain the match ticket.
            if self.match_relay and text(b,1,16).casefold() == self.name.casefold():
                stored = self.world.accounts.record_result(self.match_id, self.account_id, b[0])
                LOG.info('match result user=%d outcome=%d %s stored=%s', self.uid, b[0], OUTCOME_NAMES.get(b[0], '?'), stored)
                if stored and b[0] == 1:
                    self.world.forfeit_leavers(self.match_id, self.account_id)
                if stored:
                    threading.Thread(target=self.world.export, daemon=True).start()
            # Native result sender is fire-and-forget; do not enqueue a reply.
        elif op == 2 and len(b) == 17:
            name = text(b,1,16) or self.name
            self.send(0x7a, self.world.accounts.statistics(name))
        elif op in (3, 0x0a, 0x0b) and len(b) == 8:
            # Personal ranking page (native 4f7eb0): first/last rank inclusive.
            # The three tabs share one ladder: results carry no ladder kind.
            page = self.world.accounts.ranking_page(u32(b, 0), u32(b, 4))
            if page is None:
                self.send(0x93, bytes(4))
            else:
                first, last, records = page
                self.send(0x78, struct.pack('<II', first, last)+b''.join(records))
        else:
            LOG.info('unimplemented request op=%02x size=%d', op, len(b)+7)
            self.send(0x93, bytes(4))
    def send_room(self, rid):
        room = self.world.rooms[rid]
        self.match_id = room['match_id']
        self.match_relay = False
        # 0x7e payload: status, 14-byte native session address, 207-byte room,
        # then transport initialization fields and 130 bytes of session metadata.
        body = bytearray(360)
        body[0] = 1
        put32(body, 1, rid)
        body[15:222] = room['record']
        put32(body, 222, self.uid)
        self.send(0x7e, body)

class RelayHandler(socketserver.BaseRequestHandler):
    """Native Internet game transport (TCP 4901), isolated by lobby membership.

    1.3.59 latency work: TCP_NODELAY on the server side of every relay socket (small
    lockstep frames are sent at once instead of waiting for the previous ACK, which
    with Windows delayed ACK cost up to ~200 ms per frame), one writer thread per
    receiver so a slow player never blocks the sender's reads, and a summary line per
    connection (frames, largest gap, send backlog) to diagnose lag afterwards.
    """
    NODELAY = True
    def handle(self):
        world = self.server.world
        self.uid = self.rid = 0
        self.match_id = None
        self.account_id = 0
        self.outbox = queue.Queue()
        self.backlog = 0
        self.max_backlog = 0
        self.backlog_lock = threading.Lock()
        self.dead = False
        self.request.settimeout(60)
        started = time.monotonic()
        frames_in = bytes_in = frames_out = 0
        max_gap = 0.0
        writer = None
        try:
            if self.NODELAY:
                self.request.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            raw = read_exact(self.request, 12)
            version, op, size = struct.unpack('<III', raw)
            if (version, op, size) != (1, 0x130, 36):
                return
            body = read_exact(self.request, 24)
            rid, uid = struct.unpack_from('<II', body)
            with world.lock:
                room = world.rooms.get(rid)
                owner = next((c for c in world.clients if c.uid == uid and c.room == rid), None)
                if not room or uid not in room['members'] or owner is None or owner.client_address[0] != self.client_address[0] or text(body, 8, 16) != owner.name:
                    return
                if (rid, uid) in world.relays:
                    return
                owner.match_relay = True
                self.uid, self.rid = uid, rid
                self.match_id, self.account_id = room['match_id'], owner.account_id
                world.relays[rid, uid] = self
                match = (room['match_id'], rid, text(room['record'], 4, 32), room_map(room['record']), owner.account_id)
            # Database write in the background: the game waits for the 0x1f6 reply below.
            threading.Thread(target=self.store_participant, args=(world, match), daemon=True).start()
            writer = threading.Thread(target=self.write_loop, daemon=True)
            writer.start()
            self.send(struct.pack('<IIIII', 1, 0x1f6, 20, 0x130, 0xbe0e33ce))
            self.request.settimeout(None)
            self.request.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            LOG.info('relay connected room=%d user=%d nodelay=%s', rid, uid, self.NODELAY)
            last = time.monotonic()
            while True:
                raw = read_exact(self.request, 12)
                version, op, size = struct.unpack('<III', raw)
                if version != 1 or not 12 <= size <= 0x840:
                    LOG.info('relay closed room=%d user=%d: invalid frame version=%d size=%d', self.rid, self.uid, version, size)
                    return
                raw += read_exact(self.request, size-12)
                now = time.monotonic()
                max_gap = max(max_gap, now-last)
                last = now
                if op == 0x131:
                    return
                if op == 0x1f5 and size >= 28:
                    frames_in += 1
                    bytes_in += size
                    with world.lock:
                        room = world.rooms.get(self.rid)
                        if not room or self.uid not in room['members']:
                            LOG.info('relay closed room=%d user=%d: room gone or member left', self.rid, self.uid)
                            return
                        # Sender identity is authoritative, never copied from another client.
                        frame = bytearray(raw)
                        put32(frame, 12, self.rid)
                        put32(frame, 16, self.uid)
                        destination = u32(frame, 24)
                        if frames_in <= 8:
                            LOG.info('relay frame room=%d user=%d destination=%d size=%d', self.rid, self.uid, destination, size)
                        peers = [r for (group, user), r in world.relays.items()
                                 if group == self.rid and user != self.uid
                                 and (destination in (0, 0xffffffff) or destination == user)]
                    frame = bytes(frame)
                    for peer in peers:
                        peer.send(frame)
                        frames_out += 1
        except (OSError, EOFError, ValueError, struct.error) as e:
            if self.uid:
                LOG.info('relay closed room=%d user=%d: %s', self.rid, self.uid, type(e).__name__)
        finally:
            with world.lock:
                if world.relays.get((self.rid, self.uid)) is self:
                    world.relays.pop((self.rid, self.uid), None)
            self.dead = True
            self.outbox.put(None)
            if self.uid:
                LOG.info('relay disconnected room=%d user=%d after %.0fs: in %d frames/%d bytes, forwarded %d, '
                         'largest gap %.1fs, largest send backlog %d bytes',
                         self.rid, self.uid, time.monotonic()-started, frames_in, bytes_in, frames_out,
                         max_gap, self.max_backlog)
    @staticmethod
    def store_participant(world, match):
        for attempt in range(10):
            try:
                world.accounts.record_match(*match)
                world.export()
                return
            except sqlite3.Error as e:
                if attempt == 9:
                    LOG.warning('match participant not stored: %s', e)
                time.sleep(3)
    def send(self, frame):
        """Queue a frame for this receiver (never blocks the sending player)."""
        if self.dead:
            return
        with self.backlog_lock:
            self.backlog += len(frame)
            self.max_backlog = max(self.max_backlog, self.backlog)
            backlog = self.backlog
        if backlog > RELAY_BACKLOG_LIMIT:
            LOG.warning('relay room=%d user=%d cannot keep up (%d bytes queued); closing', self.rid, self.uid, backlog)
            self.dead = True
            try:
                self.request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            return
        self.outbox.put(frame)
    def write_loop(self):
        while True:
            frame = self.outbox.get()
            if frame is None:
                return
            # Coalesce what is already queued into one send (fewer syscalls, same order).
            chunks = [frame]
            while True:
                try:
                    more = self.outbox.get_nowait()
                except queue.Empty:
                    break
                if more is None:
                    self.outbox.put(None)
                    break
                chunks.append(more)
            data = b''.join(chunks)
            try:
                self.request.sendall(data)
            except OSError:
                self.dead = True
                return
            finally:
                with self.backlog_lock:
                    self.backlog -= len(data)

class LobbyServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 16
    def __init__(self, address, world, handler=LobbyHandler):
        self.world = world
        self.slots = threading.BoundedSemaphore(64)
        super().__init__(address, handler)
    def process_request(self, request, address):
        if not self.slots.acquire(False):
            request.close()
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.slots.release()
            raise
    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.slots.release()

class StatusHandler(BaseHTTPRequestHandler):
    """Read-only JSON for the RTS ARENA site and health checks (no account data beyond names)."""
    server_version = 'SamchunStatus/'+SERVER_VERSION
    def log_message(self, fmt, *args):
        pass
    def do_GET(self):
        world = self.server.world
        path = self.path.split('?', 1)[0]
        try:
            if path == '/healthz':
                with world.lock:
                    online = sum(1 for c in world.clients if c.uid)
                    rooms = len(world.rooms)
                body = {'ok': True, 'version': SERVER_VERSION, 'online': online, 'rooms': rooms}
            elif path == '/matches.json':
                body = world.accounts.export_matches()
            elif path == '/ranking.json':
                body = world.accounts.ranking()
            else:
                return self.reply(404, {'error': 'not found'})
        except sqlite3.Error as e:
            return self.reply(503, {'ok': False, 'error': str(e)})
        self.reply(200, body)
    def reply(self, code, obj):
        data = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=4800)
    parser.add_argument('--relay-port', type=int, default=4901)
    parser.add_argument('--http-port', type=int, default=0, help='JSON status/ranking port for RTS ARENA (0 = off)')
    parser.add_argument('--no-relay-nodelay', action='store_true', help='keep Nagle on relay sockets (pre-1.3.59 behaviour)')
    parser.add_argument('--data', type=Path, default=Path(os.environ.get('LOCALAPPDATA', '.'))/'SamchunServer')
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', handlers=[logging.StreamHandler(), RotatingFileHandler(args.data/'server.log', maxBytes=2*1024*1024, backupCount=3, encoding='utf-8')])
    world = World(args.data/'accounts.sqlite3')
    RelayHandler.NODELAY = not args.no_relay_nodelay
    world.export_path = args.data/'matches.json'
    world.export()
    def maintenance():
        while True:
            time.sleep(30)
            if world.accounts.pending and world.accounts.retry_pending():
                world.export()
    threading.Thread(target=maintenance, daemon=True).start()
    with LobbyServer((args.bind, args.port), world) as server, LobbyServer((args.bind, args.relay_port), world, RelayHandler) as relay:
        threading.Thread(target=relay.serve_forever, daemon=True).start()
        status = None
        if args.http_port:
            status = ThreadingHTTPServer((args.bind, args.http_port), StatusHandler)
            status.daemon_threads = True
            status.world = world
            threading.Thread(target=status.serve_forever, daemon=True).start()
            LOG.info('Status/ranking JSON on http://%s:%d/ (healthz, matches.json, ranking.json)', args.bind, args.http_port)
        LOG.info('3KD2 compatibility server listening on %s:%d', args.bind, args.port)
        LOG.info('Accounts are local to this server. Native protocol has no TLS; use a private LAN/VPN.')
        LOG.info('Native game relay listening on TCP %d', args.relay_port)
        LOG.info('Server %s: in-game personal ranking, match history export (%s), relay nodelay=%s, sqlite file locking=%s', SERVER_VERSION, world.export_path, RelayHandler.NODELAY, not world.accounts.nolock)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            relay.shutdown()
            if status:
                status.shutdown()

if __name__ == '__main__':
    main()
