import sys,subprocess,socket,tempfile,time,struct,sqlite3
from pathlib import Path
sys.path.insert(0,str(Path('tools').resolve()))
from test_compat_server import Client
from test_stats_native import result_packet,parse_statistics
from compat_server import puttext,u32,read_exact
exe=str(Path(sys.argv[1] if len(sys.argv)>1 else 'dist/server/samchun-server.exe').resolve())
def port():
 with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
lobby,relay=port(),port()
with tempfile.TemporaryDirectory() as data:
 def start():
  p=subprocess.Popen([exe,'--bind','127.0.0.1','--port',str(lobby),'--relay-port',str(relay),'--data',data],creationflags=subprocess.CREATE_NO_WINDOW)
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',lobby),timeout=.1):return p
   except OSError:time.sleep(.1)
  raise AssertionError('Server startup failed')
 def stop(p):subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True,check=True);p.wait()
 def query(c,name):
  c.send(2,b'\x03'+name.encode().ljust(16,b'\0'));return parse_statistics(c.receive(0x7a))
 p=start();clients=[];peers=[]
 try:
  a,b=Client(lobby),Client(lobby);clients=[a,b]
  assert a.auth('FrozenA')[0]==2 and b.auth('FrozenB')[0]==2
  record=bytearray(207);puttext(record,4,32,'Stats verification');a.send(0xe,record);rid=u32(a.receive(0x7e),15)
  b.send(0xf,struct.pack('<I',rid));assert b.receive(0x7e)[0]==1
  for c,name in ((a,'FrozenA'),(b,'FrozenB')):
   sock=socket.create_connection(('127.0.0.1',relay));sock.settimeout(3);peers.append(sock)
   sock.sendall(struct.pack('<IIIII',1,0x130,36,rid,c.uid)+name.encode().ljust(16,b'\0'));assert len(read_exact(sock,20))==20
  a.send(0x11,struct.pack('<I',rid));a.send(1,result_packet(1,'FrozenA')[7:]);a.send(1,result_packet(1,'FrozenA')[7:])
  b.send(0x11,struct.pack('<I',rid));b.send(1,result_packet(2,'FrozenB')[7:])
  assert query(a,'FrozenA')==(1,0,0,1) and query(b,'FrozenB')==(0,1,0,1)
 finally:
  for s in peers:s.close()
  for c in clients:c.close()
  stop(p)
 p=start();a=Client(lobby);b=Client(lobby)
 try:
  assert a.auth('FrozenA',False)[0]==2 and b.auth('FrozenB',False)[0]==2
  assert query(a,'FrozenA')==(1,0,0,1) and query(b,'FrozenB')==(0,1,0,1)
 finally:a.close();b.close();stop(p)
 print('Packaged server passed native result storage, duplicate suppression, restart/relogin and native statistics parser')

