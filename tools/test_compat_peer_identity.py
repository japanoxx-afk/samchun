"""Original native host send -> real relay -> first-account room joiner.

Reproduces the lost packet when account #1 is used as a peer destination.
No game binaries or account databases are changed by this test.
"""
import struct,sys,socket,tempfile,threading,unittest
from pathlib import Path
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'server'))
from compat_server import World,LobbyServer,RelayHandler,read_exact,puttext,u32,transport_id
from test_compat_server import Client

def native_send(sender,destination,rid=100,host=True):
    pe=pefile.PE(r'C:\Users\seo\Downloads\DGGL\Games\3KD2120g_Win\3kd2.exe')
    u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x400000,0x800000);u.mem_write(0x400000,pe.get_memory_mapped_image())
    def put(a,v):u.mem_write(a,struct.pack('<I',v))
    put(0xb20000+0x9d,1 if host else 2)
    put(0x8b104c+0x28,1);put(0x8b104c+0x18,rid);put(0x8b104c+0x1c,sender);put(0x8b106c,destination)
    u.mem_write(0xb10000,b'JOIN');u.mem_write(0xb00000,struct.pack('<5I',0xb70000,sender,destination,0xb10000,4))
    u.reg_write(UC_X86_REG_ECX,0xb20000);u.reg_write(UC_X86_REG_ESP,0xb00000);frames=[]
    def hook(uc,a,n,unused):
        if a!=0x4f9490:return
        sp=u.reg_read(UC_X86_REG_ESP);back,ptr,size=struct.unpack('<III',u.mem_read(sp,12))
        frames.append(bytes(u.mem_read(ptr,size)));u.reg_write(UC_X86_REG_EAX,size);u.reg_write(UC_X86_REG_ESP,sp+12);u.reg_write(UC_X86_REG_EIP,back)
    u.hook_add(UC_HOOK_CODE,hook);u.emu_start(0x42aca0,0xb70000,count=3000)
    assert u.reg_read(UC_X86_REG_ESP)==0xb00014
    return frames

class PeerIdentityTest(unittest.TestCase):
    def test_existing_account_history_and_duplicate_login(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'accounts.sqlite3';old=World(path)
            account_id,_=old.accounts.authenticate('Existing','Pass123',True)
            self.assertEqual(account_id,1)
            self.assertTrue(old.accounts.record_result('before-upgrade',account_id,1))
            world=World(path);lobby=LobbyServer(('127.0.0.1',0),world)
            threading.Thread(target=lobby.serve_forever,daemon=True).start()
            a=Client(lobby.server_address[1]);b=Client(lobby.server_address[1])
            try:
                self.assertEqual(a.auth('Existing',False,'Pass123')[0],2);self.assertEqual(a.uid,2)
                self.assertEqual(b.auth('Existing',False,'Pass123')[0],3)
                from test_stats_native import parse_statistics
                self.assertEqual(parse_statistics(world.accounts.statistics('Existing')),(1,0,0,1))
            finally:a.close();b.close();lobby.shutdown();lobby.server_close()

    def test_original_reserved_host_alias(self):
        self.assertEqual(native_send(2,1),[], 'old account #1 silently loses host replies')
        frame=native_send(3,transport_id(1))[0]
        self.assertEqual(u32(frame,24),2)
        self.assertEqual(frame[-4:],b'JOIN')

    def test_reverse_host_and_first_account_with_real_relay(self):
        with tempfile.TemporaryDirectory() as d:
            world=World(Path(d)/'accounts.sqlite3')
            # Bind all loopback interfaces: mimic server-PC and guest-PC sources.
            lobby=LobbyServer(('0.0.0.0',0),world);relay=LobbyServer(('0.0.0.0',0),world,RelayHandler)
            for s in (lobby,relay):threading.Thread(target=s.serve_forever,daemon=True).start()
            clients=[];peers=[]
            try:
                first=Client(lobby.server_address[1]);clients.append(first)
                guest=Client.__new__(Client);guest.s=socket.create_connection(('127.0.0.1',lobby.server_address[1]),source_address=('127.0.0.2',0));guest.s.settimeout(3);clients.append(guest)
                self.assertEqual(first.auth('FirstAccount')[0],2);self.assertEqual(guest.auth('GuestCreator')[0],2)
                self.assertEqual(first.uid,2);self.assertEqual(guest.uid,3)
                third=Client(lobby.server_address[1]);clients.append(third);self.assertEqual(third.auth('ThirdPeer')[0],2)
                world.next_room=first.uid # Deliberate room/recipient ID collision.
                for creator,joiner in ((guest,first),(first,guest)):
                    record=bytearray(207);puttext(record,4,32,'Native reverse-host regression')
                    creator.send(0xe,record);created=creator.receive(0x7e);rid=u32(created,15)
                    joiner.send(0xf,struct.pack('<I',rid));joined=joiner.receive(0x7e)
                    self.assertEqual(u32(joined,218),creator.uid);self.assertEqual(u32(joined,222),joiner.uid)
                    third.send(0xf,struct.pack('<I',rid));self.assertEqual(third.receive(0x7e)[0],1)
                    sockets={}
                    for c in (creator,joiner,third):
                        src='127.0.0.2' if c is guest else '127.0.0.1'
                        s=socket.create_connection(('127.0.0.1',relay.server_address[1]),source_address=(src,0));s.settimeout(3);peers.append(s);sockets[c.uid]=s
                        name='FirstAccount' if c is first else ('GuestCreator' if c is guest else 'ThirdPeer')
                        s.sendall(struct.pack('<IIIII',1,0x130,36,rid,c.uid)+name.encode().ljust(16,b'\0'))
                        self.assertEqual(len(read_exact(s,20)),20)
                    # Native high-level join reply (not a fabricated relay frame).
                    frame=native_send(creator.uid,joiner.uid,rid)[0]
                    sockets[creator.uid].sendall(frame)
                    received=read_exact(sockets[joiner.uid],len(frame))
                    self.assertEqual(received,frame)
                    sockets[third.uid].settimeout(.15)
                    with self.assertRaises(socket.timeout):sockets[third.uid].recv(1)
                    for s in peers:s.close()
                    peers.clear()
                    creator.send(0x11,struct.pack('<I',rid));joiner.send(0x11,struct.pack('<I',rid))
                    third.send(0x11,struct.pack('<I',rid))
                    joiner.send(0x10);joiner.receive(0x7f)
            finally:
                for s in peers:s.close()
                for c in clients:c.close()
                for s in (lobby,relay):s.shutdown();s.server_close()

if __name__=='__main__':unittest.main(verbosity=2)
