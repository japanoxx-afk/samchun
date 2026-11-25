"""Recording storage integrity tests; no claim of actual gameplay verification."""
import tempfile
import zlib
from pathlib import Path
from replay_journal import Writer,read,MAGIC,HEADER,MAX_BLOCK

def invalid(path):
    try:list(read(path))
    except (ValueError,zlib.error):return
    raise AssertionError('Damaged/incomplete journal accepted')

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory);path=root/'valid.scpartial'
    writer=Writer(path,{'format':1,'game_hash':'test'})
    for seq in range(1000):writer.append('command',{'seq':seq,'frame':seq//3})
    writer.close({'end_reason':'diagnostic-only'})
    entries=list(read(path))
    assert len(entries)==1002 and entries[-1]['kind']=='seal'
    assert [x['payload']['seq'] for x in entries[1:-1]]==list(range(1000))
    assert writer.pending_bytes==0 and not writer.worker.is_alive()
    try:Writer(path,{})
    except FileExistsError:pass
    else:raise AssertionError('Existing recording overwritten')
    data=path.read_bytes()
    corrupt=root/'corrupt.scpartial';changed=bytearray(data);changed[-5]^=0x40;corrupt.write_bytes(changed);invalid(corrupt)
    truncated=root/'truncated.scpartial';truncated.write_bytes(data[:-10]);invalid(truncated)
    offsets=[len(MAGIC)]
    for _ in range(2):
        size,_,_=HEADER.unpack_from(data,offsets[-1]);offsets.append(offsets[-1]+HEADER.size+size)
    reordered=root/'reordered.scpartial'
    reordered.write_bytes(MAGIC+data[offsets[1]:offsets[2]]+data[offsets[0]:offsets[1]]+data[offsets[2]:])
    invalid(reordered)
    partial=root/'partial.scpartial';writer=Writer(partial,{})
    writer.append('state',{'frame':0});writer.close();invalid(partial)
    assert len(list(read(partial,require_seal=False)))==2
    limit=root/'limit.scpartial';writer=Writer(limit,{},max_pending_bytes=128)
    try:writer.append('state',{'x':'x'*200})
    except BufferError:pass
    else:raise AssertionError('Byte budget ignored')
    writer.close();invalid(limit)
    try:Writer(root/'never-created.scpartial',{},capacity=0)
    except ValueError:pass
    else:raise AssertionError('Invalid queue accepted')
    assert not (root/'never-created.scpartial').exists()
print('PASS ordered asynchronous flush, bounded memory, no overwrite, checksum, truncation and missing-seal rejection')
