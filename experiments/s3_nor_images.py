#!/usr/bin/env python3
"""Package already-built .fs images for the BOARD's 4 MiB external SPI NOR.

This is not a programmer and does not create receiver RTL. Header/placement/hash
checks do NOT replace the vendor bitstream CRC verifier or a hardware boot test.
MSPI straps and 1.8-V RECONFIG_N access on the completed board are prerequisites.
Jump address semantics: Gowin UG290 2.9.1E 7.5.4; apicula 5d51fb6565f8 bslib.py.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

CAPACITY=4*1024*1024
SLOT=512*1024
OFFSETS={'T':0,'S':SLOT,'recovery':2*SLOT}
NEXT={'T':'S','S':'recovery','recovery':'T'}


def inspect_fs(text):
    data=bytearray();jump=None;device=None;frame_count=None;rows=0
    for raw in text.splitlines():
        line=raw.strip()
        if not line or line.startswith('//'):continue
        if len(line)%8 or set(line)-{'0','1'}:raise ValueError('non-byte-aligned binary .fs row')
        b=bytes(int(line[i:i+8],2) for i in range(0,len(line),8));data.extend(b)
        if frame_count is None:
            if len(b)!=8:raise ValueError('unsupported header row width')
            if b[0]==0xd2:
                if jump is not None:raise ValueError('duplicate jump')
                jump=int.from_bytes(b[4:],'big')
            if b[0]==0x06:device=int.from_bytes(b[4:],'big')
            if b[0]==0x3b:frame_count=int.from_bytes(b[2:],'big')
        elif rows<frame_count:rows+=1
    if device not in (0x1100481b,0x1100581b):raise ValueError('not a supported GW1N(R)-9 image')
    if frame_count is None or not frame_count or rows!=frame_count:raise ValueError('missing frame rows')
    if jump is None or jump>=1<<24 or jump%4096:raise ValueError('invalid 24-bit, 4-KiB jump address')
    if not data or len(data)>SLOT:raise ValueError('slot overflow')
    return bytes(data),jump,device


def package(files):
    if set(files)!=set(OFFSETS):raise ValueError('T, S and recovery .fs images are all required')
    image=bytearray(b'\xff'*CAPACITY);entries=[]
    for mode,offset in OFFSETS.items():
        content,jump,device=inspect_fs(files[mode])
        if jump!=OFFSETS[NEXT[mode]]:raise ValueError('header does not implement T -> S -> recovery -> T')
        image[offset:offset+len(content)]=content
        entries.append({'mode':mode,'offset':offset,'slot_bytes':SLOT,'bytes':len(content),
                        'next_mode':NEXT[mode],'jump':jump,'device_id':hex(device),
                        'sha256':hashlib.sha256(content).hexdigest()})
    manifest={'target':'Tang Nano 9K onboard external SPI NOR','capacity_bytes':CAPACITY,
              'power_on_mode':'T','images':entries,'image_sha256':hashlib.sha256(image).hexdigest(),
              'bitstream_CRC_verified':False,'hardware_boot_verified':False,
              'all_corruption_recoverable':False,'receiver_adopted':False}
    return bytes(image),manifest


def verify_readback(image,manifest):
    if len(image)!=manifest['capacity_bytes'] or hashlib.sha256(image).hexdigest()!=manifest['image_sha256']:
        raise ValueError('full NOR readback mismatch')
    for e in manifest['images']:
        x=image[e['offset']:e['offset']+e['bytes']]
        if hashlib.sha256(x).hexdigest()!=e['sha256']:raise ValueError('slot readback mismatch')


@dataclass
class Switch:
    """Executable control contract, not an S3 register driver.

    tick() returns an action. Caller MUST actually implement/acknowledge it.
    No RF restart without matching image identity, fresh epoch and RF lock.
    Timeouts latch fault; no endless reconfig or assumed golden recovery.
    """
    current: str='T'
    epoch: int=1
    state: str='running'
    target: str='T'
    expected: str='T'
    expires: int=0
    hops: int=0
    def request(self,target,now):
        if self.state!='running' or target not in ('T','S'):raise ValueError('invalid switch request')
        if target==self.current:return 'none'
        if self.epoch==65535:self.state='fault';return 'stop_RF_mute_TS'
        self.target=target;self.state='quiesce';self.expires=now+100000;self.hops=0
        return 'stop_RF_mute_TS_drain_DMA'
    def tick(self,now,*,quiescent=False,image=None,identity_ok=False,epoch_ack=False,locked=False):
        if self.state in ('running','fault'):return 'none'
        if now>=self.expires:
            self.state='fault';return 'stop_RF_mute_TS'
        if self.state=='quiesce' and quiescent:
            self.expected=NEXT[self.current];self.state='boot';self.expires=now+2000000;self.hops+=1
            return 'pulse_RECONFIG_N' # pulse width is a physical driver contract
        if self.state=='boot' and image is not None:
            if image!=self.expected or not identity_ok or self.hops>2:
                self.state='fault';return 'stop_RF_mute_TS'
            self.current=image
            if image!=self.target:
                self.expected=NEXT[image];self.expires=now+2000000;self.hops+=1
                return 'pulse_RECONFIG_N'
            self.epoch+=1;self.state='epoch';self.expires=now+100000
            return 'reset_streams_set_epoch'
        if self.state=='epoch' and epoch_ack:
            self.state='lock';self.expires=now+5000000;return 'tune_RF'
        if self.state=='lock' and locked:
            self.state='running';return 'enable_RF_TS'
        return 'none'

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--T',type=Path,required=True);p.add_argument('--S',type=Path,required=True)
    p.add_argument('--recovery',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    img,m=package({k:getattr(a,k).read_text() for k in OFFSETS});a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'external-nor.bin').write_bytes(img);(a.output/'manifest.json').write_text(json.dumps(m,indent=2)+'\n')
