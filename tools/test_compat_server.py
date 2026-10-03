"""Socket-level tests: native frames, persistent accounts, lobby, rooms and relay."""
import socket, struct, tempfile, threading, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from compat_server import World,LobbyServer,RelayHandler,packet,read_exact,puttext,put32,u32
from test_compat_native import account_call
from test_stats_native import result_packet, parse_statistics

class Client:
    def __init__(self,port):self.s=socket.create_connection(('127.0.0.1',port));self.s.settimeout(3)
    def send(self,op,body=b''):self.s.sendall(packet(op,body))
    def receive(self,op):
        for _ in range(30):
            h=read_exact(self.s,7);body=read_exact(self.s,struct.unpack_from('<H',h,5)[0]-7)
            if h[4]==op:return body
        raise AssertionError('response absent')
    def auth(self,name,register=True,password='Test123'):
        native,_,_=account_call(register)
        body=bytearray(native[7:]);puttext(body,0,16,name);puttext(body,16,11,password)
        self.send(0x30 if register else 0xc,body);r=self.receive(0x94)
        self.uid=u32(r,1) if r[0]==2 else 0
        return r
    def close(self):self.s.close()

class CompatibilityTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.db=Path(self.temp.name)/'accounts.sqlite3'
        self.world=World(self.db);self.server=LobbyServer(('127.0.0.1',0),self.world)
        self.relay=LobbyServer(('127.0.0.1',0),self.world,RelayHandler)
        for server in [self.server,self.relay]:threading.Thread(target=server.serve_forever,daemon=True).start()
        self.clients=[]
    def client(self):
        c=Client(self.server.server_address[1]);self.clients.append(c);return c
    def tearDown(self):
        for c in self.clients:c.close()
        for s in [self.server,self.relay]:s.shutdown();s.server_close()
        self.temp.cleanup()
    def test_short_id_and_empty_password(self):
        a = self.client()
        self.assertEqual(a.auth('a', password='')[0], 2)
        self.assertIsNotNone(World(self.db).accounts.authenticate('a', ''))
        self.assertIsNone(World(self.db).accounts.authenticate('a', 'wrong'))
        self.assertIsNone(World(self.db).accounts.authenticate('', '', True))
        self.assertIsNone(World(self.db).accounts.authenticate('b', 'x'*11, True))
    def test_accounts_native_parsers_and_persistence(self):
        a=self.client();response=a.auth('TesterA')
        self.assertEqual(len(response),487);self.assertEqual(response[486],7);self.assertEqual(response[0],2)
        _,result,u=account_call(True,packet(0x94,response));self.assertEqual(result,0)
        self.assertEqual(self.client().auth('TesterA')[0],1)
        self.assertEqual(self.client().auth('TesterA',False,'wrong')[0],0)
        dbbytes=self.db.read_bytes();self.assertNotIn(b'Test123',dbbytes)
        reopened=World(self.db);self.assertEqual(reopened.accounts.authenticate('testera','Test123')[0],a.uid)
    def test_lobby_rooms_chat_and_relay(self):
        a,b=self.client(),self.client();self.assertEqual(a.auth('TesterA')[0],2);self.assertEqual(b.auth('TesterB')[0],2)
        a.send(0x10);self.assertEqual(u32(a.receive(0x7f)),0)
        a.send(0x2b);self.assertEqual(u32(a.receive(0x8d)),1)
        a.send(0x29,struct.pack('<I',1));self.assertEqual(a.receive(0x8c)[0],1)
        message=bytearray(35);puttext(message,5,16,'spoof');message[29:]=b'hello\0'
        a.send(7,message);chat=b.receive(7);self.assertEqual(chat[5:21].split(b'\0')[0],b'TesterA')
        record=bytearray(207);puttext(record,4,32,'Test room')
        a.send(0xe,record);created=a.receive(0x7e);self.assertEqual(created[0],1);rid=u32(created,15)
        b.send(0x10);listed=b.receive(0x7f);self.assertEqual(u32(listed,5),rid)
        b.send(0xf,struct.pack('<I',rid));joined=b.receive(0x7e);self.assertEqual(joined[0],1)
        peers=[]
        try:
            for c,name in [(a,'TesterA'),(b,'TesterB')]:
                sock=socket.create_connection(self.relay.server_address);sock.settimeout(3)
                sock.sendall(struct.pack('<IIIII',1,0x130,36,rid,c.uid)+name.encode().ljust(16,b'\0'))
                self.assertEqual(struct.unpack('<IIIII',read_exact(sock,20)),(1,0x1f6,20,0x130,0xbe0e33ce));peers.append(sock)
            frame=struct.pack('<IIIIIII',1,0x1f5,32,rid,999,rid,b.uid)+b'test'
            peers[0].sendall(frame);received=read_exact(peers[1],32)
            self.assertEqual(u32(received,16),a.uid);self.assertEqual(received[28:],b'test')
        finally:
            for p in peers:p.close()
        a.send(0x11,struct.pack('<I',rid));a.send(2,b'\x03'+b'TesterA'.ljust(16,b'\0'));a.receive(0x7a)
        self.assertNotIn(rid,self.world.rooms)
        # The real client leaves the room before sending opcode 01.
        win = result_packet(1,'TesterA')[7:]
        a.send(1, win);a.send(1, win)
        # A connected account cannot credit a different account.
        a.send(1,result_packet(1,'TesterB')[7:])
        b.send(1,result_packet(2,'TesterB')[7:])
        def query(c,name):
            request=bytearray(17);request[0]=3;puttext(request,1,16,name)
            c.send(2,request);return parse_statistics(c.receive(0x7a))
        self.assertEqual(query(a,'TesterA'),(1,0,0,1))
        self.assertEqual(query(b,'TesterB'),(0,1,0,1))
        self.assertEqual(query(a,'TesterB'),(0,1,0,1))
        reopened=World(self.db)
        self.assertEqual(parse_statistics(reopened.accounts.statistics('TesterA')),(1,0,0,1))
        self.assertFalse(reopened.accounts.record_result(next(c.match_id for c in self.world.clients if c.uid==a.uid),a.uid,1))
        self.assertTrue(reopened.accounts.record_result('second-match',a.uid,2))
        self.assertEqual(parse_statistics(reopened.accounts.statistics('TesterA')),(1,1,0,2))
        # Native result 4 is a non-counting match, not a request to reset history.
        self.assertTrue(reopened.accounts.record_result('no-contest',a.uid,4))
        self.assertEqual(parse_statistics(reopened.accounts.statistics('TesterA')),(1,1,0,2))
    def test_repeated_room_creation_without_login(self):
        a=self.client();self.assertEqual(a.auth('RepeatA')[0],2)
        for _ in range(4):
            record=bytearray(207);puttext(record,4,32,'Repeated room')
            a.send(0xe,record);created=a.receive(0x7e)
            self.assertEqual(len(created),360)
            rid=u32(created,15);self.assertGreaterEqual(rid,100)
            self.assertEqual(u32(created,222),a.uid)
            relay=socket.create_connection(self.relay.server_address);relay.settimeout(3)
            relay.sendall(struct.pack('<IIIII',1,0x130,36,rid,a.uid)+b'RepeatA'.ljust(16,b'\0'))
            self.assertEqual(struct.unpack('<IIIII',read_exact(relay,20))[-1],0xbe0e33ce)
            relay.close()
            a.send(0x11,struct.pack('<I',rid))
            # No receive(0x7e): native leave is fire-and-forget. The next
            # iteration must not consume a stale leave acknowledgement.
    def test_unauthenticated_and_invalid_frames(self):
        a=self.client();a.send(0xe,bytes(207));self.assertEqual(a.receive(0x93),bytes(4));self.assertFalse(self.world.rooms)
        a.s.sendall(struct.pack('<IBH',0xffffffff,0xc,65535));self.assertEqual(a.s.recv(1),b'')
    def test_fragmented_frame(self):
        a=self.client();frame=packet(0x10)
        for byte in frame:a.s.sendall(bytes([byte]))
        self.assertEqual(a.receive(0x93),bytes(4))

if __name__=='__main__':unittest.main(verbosity=2)
