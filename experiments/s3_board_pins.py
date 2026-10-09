#!/usr/bin/env python3
"""Proposed connector-only data wiring; not an electrical timing certificate.

Sipeed Tang_nano_9K_3674_schematics.pdf sheet GW1NR 9K (downloaded 2026-10-09).
All data/TS pins below are on the board's 3.3 V banks. RECONFIG_N separately
requires a connection at pin9/R18 and a 1.8-V open-drain interface. MODE1/R17
must be changed from pull-down to the 1.8-V MSPI strap; this is NOT stock boot.
No microSD/card/LCD/HDMI load may be attached to these shared nets.
"""
import json
from pathlib import Path
PAIRS=[
('spi2_sclk',12,35,'J5',14),('spi2_cs_n',10,25,'J5',5),
('spi2_d0',11,26,'J5',6),('spi2_d1',13,27,'J5',7),('spi2_d2',14,28,'J5',8),
('spi2_d3',9,29,'J5',9),('spi2_d4',4,30,'J5',10),('spi2_d5',5,33,'J5',11),
('spi2_d6',6,34,'J5',12),('spi2_d7',7,40,'J5',13),
('spi3_sclk',16,36,'J5',3),('spi3_cs_n',15,41,'J5',15),
('spi3_d0',17,42,'J5',16),('spi3_d1',18,51,'J5',17),('spi3_d2',8,53,'J5',18),
('spi3_d3',21,54,'J5',19),('control_sda',38,55,'J5',20),('control_scl',39,56,'J5',21),
('ts_data',None,31,'J6',21),('ts_clk',None,32,'J6',22),
('ts_valid',None,48,'J6',19),('ts_sync',None,49,'J6',20)]

def proposal():
    gpio=[p[1] for p in PAIRS if p[1] is not None]
    fpga=[p[2] for p in PAIRS]
    assert len(gpio)==len(set(gpio)) and len(fpga)==len(set(fpga))
    assert not set(gpio)&{0,3,19,20,26,27,28,29,30,31,32,33,34,35,36,37,43,44,45,46}
    assert not set(fpga)&{3,4,5,6,7,8,9,10,11,12,13,14,15,16,52,59,60,61,62,79,80,81,82,83,84,85,86,87,88}
    return {'scope':__doc__,'board_revision_reference':'Tang_nano_9K_3674_schematics.pdf / 2024-03-11 NO.01',
        'module':'ESP32-S3-WROOM-1U-N16R8','nets':[dict(signal=s,ESP_GPIO=g,FPGA_pin=f,connector=c,connector_pin=p,voltage=3.3) for s,g,f,c,p in PAIRS],
        'reconfig':{'ESP_GPIO':40,'FPGA_pin':9,'board_net':'IOL13B_RECONFIG_N / R18','voltage':1.8,'header_exposed':False,'interface':'open-drain level shift'},
        'boot_strap':{'MODE1_pin':87,'resistor':'R17','stock':'4.7k to GND','required':'MODE1=1 at 1.8 V; keep MODE0=0'},
        'ts_format':'serial data plus clock, valid, sync; sink chosen externally',
        'pin_count_checked':True,'routed_receiver_CST_verified':False,'IO_STA_verified':False,'receiver_adopted':False}
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(proposal(),indent=2)+'\n')
