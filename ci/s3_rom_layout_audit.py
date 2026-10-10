#!/usr/bin/env python3
"""Audit reservations against the actual ESP32-S3 ROM layout, not heap totals.

The SDK appends the ROM reservation at runtime, hence ld cannot detect this
collision. The supplied ROM ELF is revision-specific; runtime hardware still
must match its layout. No ELF is executed by this tool.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

class ELF32:
    def __init__(self, path):
        self.path=Path(path); self.data=self.path.read_bytes()
        if self.data[:6]!=b'\x7fELF\x01\x01':raise ValueError('ELF32 little endian required')
        e=struct.unpack_from('<16sHHIIIIIHHHHHH',self.data)
        self.sections=[struct.unpack_from('<IIIIIIIIII',self.data,e[6]+i*e[11]) for i in range(e[12])]
        self.symbols={}
        for s in self.sections:
            if s[1]!=2:continue
            strings=self.sections[s[6]]; names=self.data[strings[4]:strings[4]+strings[5]]
            for pos in range(s[4],s[4]+s[5],s[9]):
                name,value,size,info,other,index=struct.unpack_from('<IIIBBH',self.data,pos)
                if name:self.symbols[names[name:names.index(0,name)].decode()]=(value,size,index)
    def address(self,name):return self.symbols[name][0]
    def read(self,addr,size):
        for s in self.sections:
            if s[1]!=8 and s[2]&2 and s[3]<=addr and addr+size<=s[3]+s[5]:
                off=s[4]+addr-s[3];return self.data[off:off+size]
        raise ValueError(f'unbacked ELF address {addr:#x}+{size}')

def overlap(a,b):return max(a[0],b[0])<min(a[1],b[1])

def audit(app,rom):
    layout=rom.address('ets_rom_layout')
    shared,start=struct.unpack('<II',rom.read(layout,8))
    assert start==rom.address('_dram0_rtos_reserved_start')
    reserved=(start,0x3fcf0000)
    begin=app.address('soc_reserved_memory_region_start');end=app.address('soc_reserved_memory_region_end')
    assert (end-begin)%8==0
    regions=list(struct.iter_unpack('<II',app.read(begin,end-begin)))
    conflicts=[dict(start=hex(a),end=hex(b),overlap_bytes=min(b,reserved[1])-max(a,reserved[0]))
               for a,b in regions if overlap((a,b),reserved)]
    return dict(scope=__doc__,ELF_sha256=hashlib.sha256(app.data).hexdigest(),
        ROM_ELF_sha256=hashlib.sha256(rom.data).hexdigest(),
        ROM_shared_buffer_start=hex(shared),ROM_reserved_start=hex(start),ROM_reserved_end=hex(reserved[1]),
        static_reservations=[dict(start=hex(a),end=hex(b)) for a,b in regions],
        conflicts=conflicts,ROM_reservation_nonoverlap_pass=not conflicts,
        SDK_behavior_on_overlap='s_prepare_reserved_regions logs conflict then aborts before app_main',
        hardware_revision_layout_verified=False,receiver_adopted=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--elf',type=Path,required=True)
    p.add_argument('--rom-elf',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();r=audit(ELF32(a.elf),ELF32(a.rom_elf))
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(r,indent=2)+'\n')
    print(json.dumps(r,indent=2))
