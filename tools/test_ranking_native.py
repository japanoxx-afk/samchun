"""In-game ranking: original client ranking page/search code against real server replies.

Runs the native x86 code of 3kd2.exe (unicorn) for
  4b9770  ranking page request (op 3/0x0a/0x0b) + 0x78 reply parser + row formatter
  4f7c40  statistics request (op 2) + 0x7a parser (rank used by the ranking search box)
with replies produced by a real compat_server over sockets.
Set SAMCHUN_GAME_EXE to the game executable when it is not in the default path.
"""
import socket, struct, sys, tempfile, threading, unittest
from pathlib import Path
import pefile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import UC_X86_REG_ESP, UC_X86_REG_EAX, UC_X86_REG_EIP
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'server'))
from compat_server import World, LobbyServer, RelayHandler, packet, read_exact, puttext, u32, RANK_PAGE_MAX
from test_compat_native import GAME
from test_compat_server import Client
from test_stats_native import result_packet, parse_statistics

ROWS = 0x84a828     # native row table: 10 rows x 0xa0e bytes, columns 0x101 apart
COLUMNS = {'rank': -0x100, 'name': 1, 'score': 0x102, 'guild': 0x203, 'rate': 0x304,
           'win': 0x405, 'lose': 0x506, 'draw': 0x607, 'tr': 0x708, 'hf': 0x809}

def emulate(entry, reply, setup=lambda u: None, args=()):
    """Run native code; network send captured, network receive answered with `reply` frames."""
    pe = pefile.PE(str(GAME)); u = Uc(UC_ARCH_X86, UC_MODE_32)
    u.mem_map(0x400000, 0x800000); u.mem_write(0x400000, pe.get_memory_mapped_image())
    u.mem_write(0xb00000, struct.pack('<%dI' % (1+len(args)), 0xb70000, *args)); u.reg_write(UC_X86_REG_ESP, 0xb00000)
    setup(u); sent = []; replies = list(reply)
    def ret(value=1):
        sp = u.reg_read(UC_X86_REG_ESP); back = struct.unpack('<I', u.mem_read(sp, 4))[0]
        u.reg_write(UC_X86_REG_EAX, value); u.reg_write(UC_X86_REG_ESP, sp+4); u.reg_write(UC_X86_REG_EIP, back)
    def hook(uc, a, size, data):
        if a == 0x42c050:
            sp = u.reg_read(UC_X86_REG_ESP); ptr, n = struct.unpack('<II', u.mem_read(sp+4, 8))
            sent.append(bytes(u.mem_read(ptr, n))); ret()
        elif a == 0x42c140:
            if not replies: return ret(0)
            u.mem_write(0x8aff20, replies.pop(0)); ret()
        elif a in (0x42c100, 0x42dca0):
            ret()
    u.hook_add(UC_HOOK_CODE, hook); u.emu_start(entry, 0xb70000, count=200000)
    return u, sent, u.reg_read(UC_X86_REG_EAX)

def native_page(reply_frame, start=1, tab=0):
    def setup(u):
        u.mem_write(0x6c78e4, struct.pack('<I', start)); u.mem_write(0x85ac00, struct.pack('<I', 0))
        u.mem_write(0x85ac04, struct.pack('<I', tab))
    u, sent, ok = emulate(0x4b9770, [reply_frame], setup)
    rows = []
    for i in range(7):
        base = ROWS + i*0xa0e
        cell = lambda off: bytes(u.mem_read(base+off, 0x100)).split(b'\0')[0].decode('cp949')
        row = {k: cell(off) for k, off in COLUMNS.items()}
        if row['name']: rows.append(row)
    return sent, rows, struct.unpack('<I', u.mem_read(0x6c78e4, 4))[0]

class RankingNativeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.world = World(Path(self.temp.name)/'accounts.sqlite3')
        self.lobby = LobbyServer(('127.0.0.1', 0), self.world); self.relay = LobbyServer(('127.0.0.1', 0), self.world, RelayHandler)
        for s in (self.lobby, self.relay): threading.Thread(target=s.serve_forever, daemon=True).start()
        self.clients = []
    def tearDown(self):
        for c in self.clients: c.close()
        for s in (self.lobby, self.relay): s.shutdown(); s.server_close()
        self.temp.cleanup()
    def client(self, name):
        c = Client(self.lobby.server_address[1]); self.clients.append(c); self.assertEqual(c.auth(name)[0], 2); c.name = name; return c
    def play(self, host, guest, host_outcome, guest_outcome, title='Rank game'):
        record = bytearray(207); puttext(record, 4, 32, title); puttext(record, 80, 32, r'MAP\Duel.map')
        host.send(0xe, record); rid = u32(host.receive(0x7e), 15)
        guest.send(0xf, struct.pack('<I', rid)); self.assertEqual(guest.receive(0x7e)[0], 1)
        socks = []
        for c in (host, guest):
            s = socket.create_connection(self.relay.server_address); s.settimeout(3); socks.append(s)
            s.sendall(struct.pack('<IIIII', 1, 0x130, 36, rid, c.uid)+c.name.encode().ljust(16, b'\0'))
            self.assertEqual(len(read_exact(s, 20)), 20)
        for s in socks: s.close()
        for c, outcome in ((host, host_outcome), (guest, guest_outcome)):
            c.send(0x11, struct.pack('<I', rid)); c.send(1, result_packet(outcome, c.name)[7:])
        host.send(2, b'\x03'+host.name.encode().ljust(16, b'\0')); host.receive(0x7a)  # results stored
    def request(self, c, op, body, reply):
        c.send(op, body); return c.receive(reply)

    def test_ranking_page_search_and_export(self):
        a, b, d = self.client('Alpha'), self.client('Bravo'), self.client('Delta')
        self.play(a, b, 1, 2); self.play(a, b, 1, 2); self.play(b, d, 1, 2); self.play(d, a, 3, 3)
        # Alpha 2W 0L 1D = 1020, Bravo 1W 2L = 990, Delta 0W 1L 1D = 990 (Bravo ahead on wins)
        # Native request bytes for ranks 1..7 on each of the three tabs.
        for tab, op in enumerate((3, 0x0a, 0x0b)):
            sent, _, _ = native_page(packet(0x93, bytes(4)), 1, tab)
            self.assertEqual(sent[0][4], op); self.assertEqual(struct.unpack('<II', sent[0][7:15]), (1, 7))
            reply = self.request(a, op, sent[0][7:15], 0x78)
            _, rows, start = native_page(packet(0x78, reply), 1, tab)
            self.assertEqual([r['name'] for r in rows], ['Alpha', 'Bravo', 'Delta']); self.assertEqual(start, 1)
            self.assertEqual(rows[0], {'rank': '1', 'name': 'Alpha', 'score': '1020', 'guild': '', 'rate': '66 %',
                                       'win': '2', 'lose': '0', 'draw': '1', 'tr': '0', 'hf': '0'})
            self.assertEqual((rows[1]['rank'], rows[1]['score'], rows[1]['win'], rows[1]['lose']), ('2', '990', '1', '2'))
            self.assertEqual((rows[2]['rank'], rows[2]['score'], rows[2]['draw']), ('3', '990', '1'))
        # Paging past the end shows the last page instead of an empty table.
        reply = self.request(a, 3, struct.pack('<II', 8, 14), 0x78)
        self.assertEqual(struct.unpack_from('<II', reply), (1, 3))
        # Oversized requests are clamped to what fits in one native frame.
        self.assertLessEqual(struct.unpack_from('<II', self.request(a, 3, struct.pack('<II', 1, 500), 0x78))[1], RANK_PAGE_MAX)
        # Ranking search box: original 4f7c40 reads the rank from the 0x7a statistics reply.
        stats = self.request(a, 2, b'\x03'+b'delta'.ljust(16, b'\0'), 0x7a)
        self.assertEqual(parse_statistics(stats), (0, 1, 1, 2))
        name = 0xb10000
        u, sent, ok = emulate(0x4f7c40, [packet(0x7a, stats)], lambda u: (u.mem_write(name, b'Delta\0'), u.mem_write(0x8b0320, b'Alpha\0')), (0, name))
        self.assertEqual(ok, 1); self.assertEqual(sent[0][4], 2); self.assertEqual(sent[0][7], 3)
        self.assertEqual(struct.unpack('<I', u.mem_read(0x8b0367, 4))[0], 3)
        self.assertEqual(struct.unpack('<H', u.mem_read(0x8b0361, 2))[0], 990)
        # Guild ranking and guild search answer "no rows" (guilds are not implemented).
        self.assertEqual(self.request(a, 0x2d, struct.pack('<II', 1, 7), 0x93), bytes(4))
        self.assertEqual(self.request(a, 0x31, b'\x2d'+bytes(48), 0x93), bytes(4))
        # Export for RTS ARENA: four matches, two players each, codes 1/2/3, map from the room record.
        exported = self.world.accounts.export_matches()
        self.assertEqual(len(exported), 4)
        self.assertEqual(exported[0]['players'], ['Alpha', 'Bravo']); self.assertEqual(exported[0]['map'], 'Duel')
        self.assertEqual({k: v['code'] for k, v in exported[0]['results'].items()}, {'Alpha': 1, 'Bravo': 2})
        self.assertEqual({k: v['code'] for k, v in exported[3]['results'].items()}, {'Delta': 3, 'Alpha': 3})

    def test_empty_and_single_player_games_do_not_rank(self):
        a = self.client('Solo')
        self.assertEqual(self.request(a, 3, struct.pack('<II', 1, 7), 0x93), bytes(4))
        _, rows, start = native_page(packet(0x93, bytes(4)))
        self.assertEqual(rows, []); self.assertEqual(start, 1)
        record = bytearray(207); puttext(record, 4, 32, 'alone'); a.send(0xe, record); rid = u32(a.receive(0x7e), 15)
        s = socket.create_connection(self.relay.server_address); s.settimeout(3)
        s.sendall(struct.pack('<IIIII', 1, 0x130, 36, rid, a.uid)+b'Solo'.ljust(16, b'\0')); read_exact(s, 20); s.close()
        a.send(0x11, struct.pack('<I', rid)); a.send(1, result_packet(1, 'Solo')[7:])
        self.assertEqual(parse_statistics(self.request(a, 2, b'\x03'+b'Solo'.ljust(16, b'\0'), 0x7a)), (0, 0, 0, 0))
        self.assertEqual(self.world.accounts.ranking(), [])

if __name__ == '__main__':
    unittest.main(verbosity=2)
