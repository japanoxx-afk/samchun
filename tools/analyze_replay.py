"""Read-only, reproducible replay reconnaissance for the supported Samchun EXE.

No executable bytes, saved games, or process state are changed. Raw immediate
references are candidates, not a claim that every occurrence is executable code.
"""
import argparse
import hashlib
import json
import re
import struct
from pathlib import Path
import capstone
import pefile

SUPPORTED = 'a0ee96931b3b74fce739062d8e58253892510ef863e9127648ac38fd4d515f99'
REGIONS = {
    'rng_seed': (0x671413, 13),
    'rng_next': (0x671420, 34),
    'rng_thread_storage': (0x674743, 103),
    'single_clock': (0x4e2fc0, 97),
    'slot_command_drain': (0x44c200, 66),
    'due_command_dispatch': (0x44c470, 181),
    'command_decode_validation': (0x44c870, 191),
    'network_command_frame': (0x4e3670, 286),
    'network_frame_validation': (0x4e4400, 162),
    'game_context': (0x43a7d0, 6),
    'initialization_seed_paths': (0x444156, 241),
    'save_global_block': (0x4fefb0, 148),
    'load_global_block': (0x4ff050, 64),
    'global_serializers': (0x4feca0, 639),
    'save_object_table': (0x445610, 118),
    'serialize_synchronized_frame': (0x4e23c0, 45),
    'main_loop_dispatch_and_update': (0x40c6e0, 171),
    'simulation_scheduler': (0x502340, 64),
    'object_serialization_table': (0x44568d, 280),
    'fog_grid_sample': (0x42f0c0, 122),
}

def analyze(path):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != SUPPORTED:
        raise ValueError('Unsupported game SHA-256; analysis profile was not applied.')
    pe = pefile.PE(data=data)
    base = pe.OPTIONAL_HEADER.ImageBase
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_32)
    regions = {}
    for name, (address, length) in REGIONS.items():
        code = pe.get_data(address-base, length)
        regions[name] = {
            'address': hex(address), 'bytes': code.hex(),
            'disassembly': [f'{i.address:08x} {i.mnemonic} {i.op_str}'
                            for i in md.disasm(code, address)]}
    refs = {}
    for name, address in [('rng_seed', 0x671413), ('rng_next', 0x671420),
                          ('command_dispatch', 0x44c870), ('slot_drain', 0x44c200)]:
        found = []
        for section in pe.sections:
            if not section.Characteristics & 0x20000000:
                continue
            code = section.get_data()
            start = base + section.VirtualAddress
            for offset in range(len(code)-4):
                if code[offset] == 0xe8 and start+offset+5+struct.unpack_from('<i',code,offset+1)[0] == address:
                    found.append(hex(start+offset))
        refs[name] = found
    imports = {d.dll.decode('ascii'): [i.name.decode('ascii') if i.name else i.ordinal
                                      for i in d.imports] for d in pe.DIRECTORY_ENTRY_IMPORT}
    strings = []
    for match in re.finditer(rb'[ -~]{5,}', data):
        value = match.group().decode('ascii')
        if any(key in value.lower() for key in ['synchframe', 'illegal frame', '*.sav', 'test sav file']):
            strings.append({'address': hex(base+pe.get_rva_from_offset(match.start())), 'text':value})
    return {'schema':1, 'status':'static-analysis-only', 'game_sha256':digest,
            'machine':hex(pe.FILE_HEADER.Machine), 'image_base':hex(base),
            'imports':imports, 'regions':regions, 'candidate_call_sites':refs,
            'diagnostic_strings':strings,
            'limitations':['No runtime determinism or playback verified.',
                          'Call-site scan can include data in executable sections.',
                          'SAV restore and observer independence remain unverified.']}

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = analyze(args.game)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    print('Static analysis written; no game or save files modified.')
