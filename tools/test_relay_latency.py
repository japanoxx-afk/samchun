"""Server 1.3.59: relay latency/robustness and 1:1 leaver loss.

- relay sockets use TCP_NODELAY; 300 frames each way keep order and content
- a receiver that does not read never blocks the sender (per-receiver writer queue)
- statistics/ranking requests answer while the world lock is held (DB work is outside it)
- 1:1 winner reports, opponent dropped without a result -> opponent gets a loss;
  opponent still in the game transport -> no inferred loss
"""
import socket, struct, sys, tempfile, threading, time, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'server'))
from compat_server import World, LobbyServer, RelayHandler, read_exact, puttext, u32
from test_compat_server import Client
from test_stats_native import result_packet, parse_statistics


class RelayLatencyTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.world = World(Path(self.temp.name)/'accounts.sqlite3')
        self.lobby = LobbyServer(('127.0.0.1', 0), self.world); self.relay = LobbyServer(('127.0.0.1', 0), self.world, RelayHandler)
        for s in (self.lobby, self.relay): threading.Thread(target=s.serve_forever, daemon=True).start()
        self.closing = []
    def tearDown(self):
        for c in self.closing: c.close()
        for s in (self.lobby, self.relay): s.shutdown(); s.server_close()
        self.temp.cleanup()
    def client(self, name):
        c = Client(self.lobby.server_address[1]); self.closing.append(c); self.assertEqual(c.auth(name)[0], 2); c.name = name; return c
    def room(self, host, guest):
        record = bytearray(207); puttext(record, 4, 32, 'latency'); host.send(0xe, record); rid = u32(host.receive(0x7e), 15)
        guest.send(0xf, struct.pack('<I', rid)); self.assertEqual(guest.receive(0x7e)[0], 1)
        socks = []
        for c in (host, guest):
            s = socket.create_connection(self.relay.server_address); s.settimeout(5); socks.append(s); self.closing.append(s)
            s.sendall(struct.pack('<IIIII', 1, 0x130, 36, rid, c.uid)+c.name.encode().ljust(16, b'\0'))
            self.assertEqual(len(read_exact(s, 20)), 20)
        return rid, socks

    def test_nodelay_order_and_slow_receiver(self):
        a, b = self.client('LagA'), self.client('LagB')
        rid, (sa, sb) = self.room(a, b)
        relays = [r for r in self.world.relays.values()]
        self.assertTrue(all(r.request.getsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY) for r in relays))
        def frame(src, dst, n):
            payload = struct.pack('<I', n) + bytes(20)
            return struct.pack('<IIIIIII', 1, 0x1f5, 28+len(payload), rid, 0, rid, dst) + payload
        for n in range(300):
            sa.sendall(frame(a.uid, b.uid, n)); sb.sendall(frame(b.uid, a.uid, n))
        for sock, src in ((sb, a.uid), (sa, b.uid)):
            for n in range(300):
                got = read_exact(sock, 52)
                self.assertEqual((u32(got, 16), u32(got, 28)), (src, n))
        # B stops reading; A keeps sending 3 MB. A's sends must not stall on B.
        t0 = time.monotonic()
        big = struct.pack('<IIIIIII', 1, 0x1f5, 28+2000, rid, 0, rid, b.uid) + bytes(2000)
        for _ in range(1500):
            sa.sendall(big)
        self.assertLess(time.monotonic()-t0, 5)
        # statistics answer even while another thread holds the world lock
        with self.world.lock:
            a.send(2, b'\x03'+b'LagA'.ljust(16, b'\0'))
            self.assertEqual(parse_statistics(a.receive(0x7a)), (0, 0, 0, 0))

    def test_leaver_gets_loss_only_after_leaving(self):
        a, b = self.client('StayA'), self.client('LeaveB')
        rid, (sa, sb) = self.room(a, b)
        time.sleep(0.3)   # participants are stored in the background
        # B still in the game transport: A's win does not infer B's loss
        a.send(0x11, struct.pack('<I', rid)); a.send(1, result_packet(1, 'StayA')[7:])
        a.send(2, b'\x03'+b'LeaveB'.ljust(16, b'\0')); self.assertEqual(parse_statistics(a.receive(0x7a)), (0, 0, 0, 0))
        # second match: B drops out (relay closed) without any result, then A reports a win
        rid2, (sa2, sb2) = self.room(a, b)
        time.sleep(0.3)
        sb2.close()
        for _ in range(50):
            if not any(r.uid == b.uid and r.rid == rid2 for r in self.world.relays.values()): break
            time.sleep(0.05)
        a.send(0x11, struct.pack('<I', rid2)); a.send(1, result_packet(1, 'StayA')[7:])
        a.send(2, b'\x03'+b'LeaveB'.ljust(16, b'\0')); self.assertEqual(parse_statistics(a.receive(0x7a)), (0, 1, 0, 1))
        a.send(2, b'\x03'+b'StayA'.ljust(16, b'\0')); self.assertEqual(parse_statistics(a.receive(0x7a)), (2, 0, 0, 2))
        # B's own later loss report does not double count
        b.send(1, result_packet(2, 'LeaveB')[7:])
        a.send(2, b'\x03'+b'LeaveB'.ljust(16, b'\0')); self.assertEqual(parse_statistics(a.receive(0x7a)), (0, 1, 0, 1))


if __name__ == '__main__':
    unittest.main(verbosity=2)
