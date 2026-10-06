"""Compare experimental entity samples and RNG; never claim complete equality."""
import argparse,json
from pathlib import Path

def compare(original,playback):
    def compact(row):return {k:v for k,v in row.items() if k!='entities'}
    reference={(r['native_frame'],r['phase']):r for r in original['states'] if r['valid']}
    actual={(r['native_frame'],r['phase']):r for r in playback['states'] if r['valid']}
    checked=0;first=None
    for key,row in sorted(reference.items()):
        other=actual.get(key)
        if other is None:continue
        checked+=1
        if (row['checksum'],row['objects'])!=(other['checksum'],other['objects']):
            first=dict(native_frame=key[0],phase=key[1],expected=compact(row),actual=compact(other));break
    rng_first=None
    fields=['native_frame','state_before','caller']
    for index,(a,b) in enumerate(zip(original['rng_records'],playback['rng_records'])):
        if any(a[k]!=b[k] for k in fields):
            rng_first=dict(sequence=index,expected={k:a[k] for k in fields},actual={k:b[k] for k in fields});break
    simulation_first=None;simulation_checked=0
    for key,row in sorted(reference.items()):
        other=actual.get(key)
        if other is None or row.get('unit_resource_checksum') is None or other.get('unit_resource_checksum') is None:continue
        simulation_checked+=1
        if row['unit_resource_checksum']!=other['unit_resource_checksum']:
            entity_changes=[]
            a={r['id']:r for r in row.get('entities',[])};b={r['id']:r for r in other.get('entities',[])}
            for entity_id in sorted(a.keys()|b.keys()):
                if a.get(entity_id)!=b.get(entity_id):
                    entity_changes.append(dict(id=entity_id,expected=a.get(entity_id),actual=b.get(entity_id)))
            simulation_first=dict(native_frame=key[0],phase=key[1],expected=compact(row),actual=compact(other),
                                  entity_changes=entity_changes[:20],changed_entities=len(entity_changes));break
    resources_checked=0;resources_first=None
    for key,row in sorted(reference.items()):
        other=actual.get(key)
        if other is None or 'player_resource_checksum' not in row or 'player_resource_checksum' not in other:continue
        resources_checked+=1
        if (row['player_resource_checksum'],row['player_slots'])!=(other['player_resource_checksum'],other['player_slots']):
            resources_first=dict(native_frame=key[0],phase=key[1],expected=compact(row),actual=compact(other));break
    first_tick=min((r['native_frame'] for r in [first,simulation_first] if r is not None),default=None)
    recent=[r for r in original['records'] if first_tick is not None and r['native_frame']<=first_tick][-8:]
    fields_command=['sequence','native_frame','slot','scheduled_frame','command_kind','raw']
    command_pairs=list(zip(original['records'],playback['records']))
    commands_equal=len(command_pairs)==len(original['records']) and all(
        all(a[k]==b[k] for k in fields_command) for a,b in command_pairs)
    return dict(entity_samples_compared=checked,first_entity_mismatch=first,
                unit_resource_samples_compared=simulation_checked,first_unit_resource_mismatch=simulation_first,
                player_resource_samples_compared=resources_checked,first_player_resource_mismatch=resources_first,
                command_attempts_match=commands_equal,recent_commands_at_first_entity_mismatch=recent,
                first_rng_mismatch=rng_first,playback_status=playback.get('playback_status'),
                reference_samples=len(reference),playback_samples=len(actual),
                complete_simulation_equality_verified=False,
                limitations=['Partial fields only; production/AI/scheduled tasks not covered.',
                             'Matching samples alone are insufficient to release a replay.'])

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['original','playback','report']:p.add_argument(name,type=Path)
    a=p.parse_args()
    result=compare(json.loads(a.original.read_text(encoding='utf-8')),
                   json.loads(a.playback.read_text(encoding='utf-8')))
    a.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
