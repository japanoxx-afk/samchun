"""Bounded, append-only diagnostic journal; never execute bytes from a journal.

This records data outside the game process. An unsealed/crashed recording is
detectable and is not accepted as a completed replay. It does not establish
simulation determinism or classify a native end as a completed match.
"""
import hashlib
import json
import os
import queue
import struct
import threading
import time
import zlib
from pathlib import Path

MAGIC=b'SCRJ1\r\n\x1a'
MAX_BLOCK=4*1024*1024
HEADER=struct.Struct('<II32s')


def encode(kind,payload):
    raw=json.dumps({'kind':kind,'payload':payload},ensure_ascii=False,
                   separators=(',',':'),allow_nan=False).encode('utf-8')
    if len(raw)>MAX_BLOCK:raise ValueError('Journal entry exceeds bounded size')
    return raw


class Writer:
    def __init__(self,path,metadata,capacity=4096,max_pending_bytes=16*1024*1024):
        if capacity<1 or len(encode('metadata',metadata))>max_pending_bytes:
            raise ValueError('Invalid journal queue budget')
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        # Never replace a user's existing recording, including partial files.
        self.file=self.path.open('xb')
        self.file.write(MAGIC);self.file.flush();os.fsync(self.file.fileno())
        self.queue=queue.Queue(maxsize=capacity)
        self.pending_bytes=0;self.max_pending_bytes=max_pending_bytes;self.lock=threading.Lock()
        self.error=None;self.closed=False;self.count=0;self.chain=bytes(32)
        self.worker=threading.Thread(target=self._run,name='replay-journal',daemon=False)
        self.worker.start()
        self.append('metadata',metadata)

    def _run(self):
        last_flush=time.monotonic()
        try:
            while True:
                item=self.queue.get()
                try:
                    if item is None:break
                    raw=item
                    packed=zlib.compress(raw,1)
                    digest=hashlib.sha256(self.chain+raw).digest()
                    self.file.write(HEADER.pack(len(packed),len(raw),digest))
                    self.file.write(packed)
                    self.chain=digest;self.count+=1
                    if time.monotonic()-last_flush>=1:
                        self.file.flush();last_flush=time.monotonic()
                finally:
                    if item is not None:
                        with self.lock:self.pending_bytes-=len(item)
                    self.queue.task_done()
            self.file.flush();os.fsync(self.file.fileno())
        except BaseException as exc:
            self.error=exc
        finally:self.file.close()

    def append(self,kind,payload):
        if self.closed:raise ValueError('Journal is closed')
        if self.error:raise OSError('Replay journal writer failed') from self.error
        raw=encode(kind,payload)
        with self.lock:
            if self.pending_bytes+len(raw)>self.max_pending_bytes:
                raise BufferError('Replay writer byte budget exceeded; recording is incomplete')
            self.pending_bytes+=len(raw)
        try:self.queue.put_nowait(raw)
        except queue.Full:
            with self.lock:self.pending_bytes-=len(raw)
            raise BufferError('Replay disk writer fell behind; recording is incomplete')

    def close(self,summary=None):
        if self.closed:return
        # Failure deliberately leaves an unsealed journal. No oldest replay is
        # removed and no partial recording is promoted to the normal list.
        if summary is not None:
            try:self.append('seal',summary)
            except BaseException:
                self.close();raise
        self.closed=True
        while self.worker.is_alive():
            try:self.queue.put(None,timeout=.1);break
            except queue.Full:continue
        self.worker.join()
        if self.error:raise OSError('Replay journal could not be flushed') from self.error


def read(path,require_seal=True,max_unpacked=256*1024*1024):
    """Yield validated entries with bounded decompression, no arbitrary paths."""
    chain=bytes(32);sealed=False;count=0;total=0
    with Path(path).open('rb') as stream:
        if stream.read(len(MAGIC))!=MAGIC:raise ValueError('Unsupported journal format')
        while True:
            head=stream.read(HEADER.size)
            if not head:break
            if sealed:raise ValueError('Data follows journal seal')
            if len(head)!=HEADER.size:raise ValueError('Truncated journal header')
            size,raw_size,digest=HEADER.unpack(head)
            if not 0<size<=MAX_BLOCK or not 0<raw_size<=MAX_BLOCK:
                raise ValueError('Invalid journal block length')
            total+=raw_size
            if total>max_unpacked:raise ValueError('Journal expands beyond total size limit')
            packed=stream.read(size)
            if len(packed)!=size:raise ValueError('Truncated journal block')
            decoder=zlib.decompressobj()
            raw=decoder.decompress(packed,raw_size+1)
            if (len(raw)!=raw_size or not decoder.eof or decoder.unused_data
                    or decoder.unconsumed_tail):raise ValueError('Invalid compressed journal block')
            expected=hashlib.sha256(chain+raw).digest()
            if digest!=expected:raise ValueError('Journal checksum/order mismatch')
            chain=digest
            entry=json.loads(raw)
            if not isinstance(entry,dict) or set(entry)!={'kind','payload'}:
                raise ValueError('Invalid journal entry')
            if count==0 and entry['kind']!='metadata':raise ValueError('Missing journal metadata')
            count+=1;sealed=entry['kind']=='seal'
            yield entry
    if count==0 or (require_seal and not sealed):raise ValueError('Recording did not finish or was interrupted')
