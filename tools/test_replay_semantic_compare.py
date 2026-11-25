"""Legacy sprite pointer exclusion must not hide real unit desynchronization."""
from copy import deepcopy
from compare_replay_traces import compare
row=dict(sequence=0,native_frame=1,phase=0,valid=True,checksum=1,objects=1,unit_resource_checksum=1,player_resource_checksum=1,player_slots=1,snapshot_flags=0,entities=[dict(id=12,type=1026,position=[10,20,0],owner=1,hp=43210,mana=1200,command=0,target=0x8000003f)])
ref=dict(states=[row],rng_records=[],records=[])
play=deepcopy(ref);play['states'][0]['unit_resource_checksum']=2;play['states'][0]['entities'][0].update(extended_fields_valid=False,owner=0,hp=0,mana=0,command=0,target=0)
assert compare(ref,play)['first_unit_resource_mismatch'] is None
play['states'][0]['entities'][0]['position'][0]+=1
assert compare(ref,play)['first_unit_resource_mismatch']['native_frame']==1
play=deepcopy(ref);play['states'][0]['entities'][0].update(extended_fields_valid=True,hp=150)
assert compare(ref,play)['first_unit_resource_mismatch']['entity_changes'][0]['id']==12
ref['states'][0]['entities'][0]['extended_fields_valid']=False
assert compare(ref,play)['first_unit_resource_mismatch'] is not None
print('PASS legacy display fields excluded only by native layout proof; position, real HP and class transitions still fail.')
