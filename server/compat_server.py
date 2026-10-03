"""3KD2 1.20g private Internet compatibility service.
Wire layouts are derived from the original client's packet builders/consumers.
No original service, credentials or game files are contacted/distributed.
"""
import argparse
from contextlib import closing
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
    def __init__(self, path):
        self.path = str(path)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS match_results (match_id TEXT NOT NULL, user_id INTEGER NOT NULL, outcome INTEGER NOT NULL, recorded_at INTEGER NOT NULL, PRIMARY KEY(match_id,user_id))')
            db.execute('CREATE TABLE IF NOT EXISTS accounts (id INTEGER PRIMARY KEY, name TEXT UNIQUE COLLATE NOCASE, salt BLOB NOT NULL, digest BLOB NOT NULL)')
    def authenticate(self, name, password, register=False):
        if not 1 <= len(name.encode('cp949', 'replace')) <= 15 or len(password.encode('cp949', 'replace')) > 10:
            return None
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            if register:
                salt = secrets.token_bytes(24)
                digest = hashlib.pbkdf2_hmac('sha256', password.encode('cp949'), salt, 600000)
                try:
                    row = db.execute('INSERT INTO accounts(name,salt,digest) VALUES (?,?,?)', (name, salt, digest))
                    return row.lastrowid, name
                except sqlite3.IntegrityError:
                    return None
            row = db.execute('SELECT id,name,salt,digest FROM accounts WHERE name=?', (name,)).fetchone()
            salt = row[2] if row else bytes(24)
            digest = hashlib.pbkdf2_hmac('sha256', password.encode('cp949'), salt, 600000)
            if row and hmac.compare_digest(row[3], digest):
                return row[0], row[1]
            return None

    def record_result(self, match_id, uid, outcome):
        if not match_id or outcome not in (1, 2, 3, 4):
            return False
        with closing(sqlite3.connect(self.path, timeout=10)) as db, db:
            row = db.execute('INSERT OR IGNORE INTO match_results VALUES (?,?,?,?)',
                             (match_id, uid, outcome, int(time.time())))
            return row.rowcount == 1
    def statistics(self, name):
        with closing(sqlite3.connect(self.path, timeout=10)) as db:
            rows = db.execute('SELECT outcome,COUNT(*) FROM match_results WHERE user_id=(SELECT id FROM accounts WHERE name=?) GROUP BY outcome', (name,)).fetchall()
        counts = dict(rows)
        result = bytearray(80)
        # Original 4f7c40 reads these unsigned 16-bit counters from 0x7a.
        values = [counts.get(1,0), counts.get(2,0), counts.get(3,0)]
        for offset, value in zip((57,59,61,63), values+[sum(values)]):
            struct.pack_into('<H', result, offset, min(value, 65535))
        return result

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
        result = self.world.accounts.authenticate(text(body, 0, 16), text(body, 16, 11), op == 0x30)
        if not result:
            self.send(0x94, b'\x01' if op == 0x30 else b'\x00')
            return
        with self.world.lock:
            if any(c.uid == result[0] for c in self.world.clients):
                self.send(0x94, b'\x03')
                return
            self.uid, self.name = result
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
        elif op == 1 and len(b) == 683:
            # A result often arrives AFTER room-leave; retain the match ticket.
            if self.match_relay and text(b,1,16).casefold() == self.name.casefold():
                stored = self.world.accounts.record_result(self.match_id, self.uid, b[0])
                LOG.info('match result user=%d outcome=%d stored=%s', self.uid, b[0], stored)
            # Native result sender is fire-and-forget; do not enqueue a reply.
        elif op == 2 and len(b) == 17:
            name = text(b,1,16) or self.name
            self.send(0x7a, self.world.accounts.statistics(name))
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
        elif op in (3, 0x0a, 0x0b, 0x2d, 0x2e, 0x2f):
            # Empty search/ranking result, never fabricate account rankings.
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
    """Native Internet game transport (TCP 4901), isolated by lobby membership."""
    def handle(self):
        world = self.server.world
        self.lock = threading.Lock()
        self.uid = self.rid = 0
        self.request.settimeout(60)
        try:
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
                world.relays[rid, uid] = self
            self.send(struct.pack('<IIIII', 1, 0x1f6, 20, 0x130, 0xbe0e33ce))
            self.request.settimeout(None)
            self.request.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            LOG.info('relay connected room=%d user=%d', rid, uid)
            frame_count = 0
            while True:
                raw = read_exact(self.request, 12)
                version, op, size = struct.unpack('<III', raw)
                if version != 1 or not 12 <= size <= 0x840:
                    return
                raw += read_exact(self.request, size-12)
                if op == 0x131:
                    return
                if op == 0x1f5 and size >= 28:
                    with world.lock:
                        room = world.rooms.get(self.rid)
                        if not room or self.uid not in room['members']:
                            return
                        # Sender identity is authoritative, never copied from another client.
                        frame = bytearray(raw)
                        put32(frame, 12, self.rid)
                        put32(frame, 16, self.uid)
                        destination = u32(frame, 24)
                        frame_count += 1
                        if frame_count <= 8:
                            LOG.info('relay frame room=%d user=%d destination=%d size=%d', self.rid, self.uid, destination, size)
                        peers = [r for (group, user), r in world.relays.items()
                                 if group == self.rid and user != self.uid
                                 and (destination in (0, 0xffffffff, self.rid) or destination == user)]
                    for peer in peers:
                        peer.send(frame)
        except (OSError, EOFError, ValueError, struct.error):
            pass
        finally:
            with world.lock:
                if world.relays.get((self.rid, self.uid)) is self:
                    world.relays.pop((self.rid, self.uid), None)
            LOG.info('relay disconnected room=%d user=%d', self.rid, self.uid)
    def send(self, frame):
        try:
            with self.lock:
                self.request.sendall(frame)
        except OSError:
            pass

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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--bind', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=4800)
    parser.add_argument('--relay-port', type=int, default=4901)
    parser.add_argument('--data', type=Path, default=Path(os.environ.get('LOCALAPPDATA', '.'))/'SamchunServer')
    args = parser.parse_args()
    args.data.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s', handlers=[logging.StreamHandler(), RotatingFileHandler(args.data/'server.log', maxBytes=2*1024*1024, backupCount=3, encoding='utf-8')])
    world = World(args.data/'accounts.sqlite3')
    with LobbyServer((args.bind, args.port), world) as server, LobbyServer((args.bind, args.relay_port), world, RelayHandler) as relay:
        threading.Thread(target=relay.serve_forever, daemon=True).start()
        LOG.info('3KD2 compatibility server listening on %s:%d', args.bind, args.port)
        LOG.info('Accounts are local to this server. Native protocol has no TLS; use a private LAN/VPN.')
        LOG.info('Native game relay listening on TCP %d', args.relay_port)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            relay.shutdown()

if __name__ == '__main__':
    main()
