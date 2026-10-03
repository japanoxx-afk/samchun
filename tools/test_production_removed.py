"""Ensure removed production hooks and selection gates retain original bytes."""
from test_selection_patch import IMAGE,P,PAYLOAD
original=P.get_memory_mapped_image()
for address,size in ((0x4127f3,8),(0x40dba7,5),(0x52ce29,2),(0x52ce5c,2),(0x52d0c6,6),(0x52d101,6),(0x529b27,6),(0x529c93,6),(0x529874,2)):
 off=address-0x400000
 assert IMAGE[off:off+size]==original[off:off+size],hex(address)
assert PAYLOAD[0x2800:0x2c00]==bytes(0x400)
print('Removed production hooks/gates match original; unused production payload cleared')
