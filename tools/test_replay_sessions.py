"""Session orchestration test; native transition still needs real-game testing."""
import json,tempfile
from pathlib import Path
from unittest.mock import patch
import replay_engine as engine
with tempfile.TemporaryDirectory() as d:
 root=Path(d);game=root/'game';game.mkdir();(game/'SAVE').mkdir()
 work=root/'work';profile_base={'output_sha256':'test'}
 names=iter(['RPLA0001','RPLA0002','RPLA0003','RPLA0004']);generations=[];armed=[];archived=[]
 class Process:
  pid=123
  def poll(self):return 0 if len(generations)==3 else None
 def build(*args,**kwargs):args[2].write_text(json.dumps(profile_base))
 def capture(pid,profile,report,seconds,**kwargs):
  p=json.loads(profile.read_text());g=p['expected_generation'];generations.append(g)
  result=dict(capture_error=None,initial_checkpoint=None,end_reason='process-unreadable-or-exited',process_exit_code=0)
  if g<2:
   (game/'SAVE'/p['initial_save_name']).write_bytes(bytes([g]))
   kwargs['on_checkpoint']({})
   result.update(initial_checkpoint={},end_reason='native-cleanup-transition',process_exit_code=None)
  report.write_text(json.dumps(result))
 def create(journal,checkpoint,folder,**kwargs):
  archived.append(checkpoint.read_bytes());return folder/(checkpoint.parent.name+'.screplay')
 with patch.object(engine,'prepare',return_value=game),patch.object(engine,'unique_save',side_effect=lambda *a:next(names)),patch.object(engine,'build',side_effect=build),patch.object(engine,'add_save'),patch.object(engine,'capture_order'),patch.object(engine,'add_end'),patch.object(engine,'add_session'),patch.object(engine,'data_hashes',return_value={}),patch.object(engine.subprocess,'Popen',return_value=Process()),patch.object(engine,'capture',side_effect=capture),patch.object(engine,'arm',side_effect=lambda pid,profile,name=None,acknowledge=False:armed.append(name) if not acknowledge else None),patch.object(engine,'recover_stopped',side_effect=lambda path,dest:path),patch.object(engine,'create',side_effect=create):
  engine.record(game/'3kd2.exe',game/'baseline.exe',work)
 assert generations==[0,1,2] and armed==['RPLA0002','RPLA0003']
 assert archived==[b'\0',b'\1']
 assert len(json.loads((work/'saved.json').read_text())['files'])==2
print('PASS two independent consecutive match archives; main-menu exit creates no empty replay')
