"""Count declared SPI paths in pinned SDK ELFs; instruction counts, not cycles."""
import argparse, gzip, hashlib, io, json, os, re, subprocess
from pathlib import Path
from elftools.elf.elffile import ELFFile
from ci.s3_pack_cfg_audit import ROW

ROOT = Path(__file__).resolve().parents[1]
PREFIX = [0,3,5,7,9,0xb,0xe,0x10,0x13,0x15,0x18,0x1a,0x1c,0x1f,0x22]
WRAPPER = [0,3,6,9,0xc,0xe,0x10,0x12,0x14,0x16,0x19,0x1b,0x40]
SDK_EMPTY = [0,3,5,0x31,0x34,0x36,0x39,0x3c,0x66,0x69,0x6c,0x6f,0x72,0x82]

def audit(profile, tc, temp, current):
    raw = gzip.decompress((profile/'s3_raw_probe.elf.gz').read_bytes())
    record = json.loads((profile/'result.json').read_text())
    assert hashlib.sha256(raw).hexdigest() == record['ELF_sha256']
    assert record['all_static_checks_pass']
    elf = ELFFile(io.BytesIO(raw))
    symbols = {s.name:s for s in elf.get_section_by_name('.symtab').iter_symbols()}
    temp.write_bytes(raw)
    env = dict(os.environ, XTENSA_GNU_CONFIG=str(tc/'lib/xtensa_esp32s3.so'))
    cache = {}
    def trace(name, offsets, calls):
        symbol = symbols[name]; base = symbol['st_value']; nodes = []
        for offset in offsets:
            assert 0 <= offset < symbol['st_size']
            pc = base+offset
            if pc not in cache:
                dis = subprocess.check_output([str(tc/'bin/xtensa-esp-elf-objdump'), '-d',
                    f'--start-address={pc}', f'--stop-address={pc+4}', str(temp)], env=env, text=True)
                m = next(ROW.match(line) for line in dis.splitlines() if ROW.match(line))
                assert int(m[1],16) == pc
                cache[pc] = dict(offset=offset, bytes=m[2], op=m[3], operands=m[4])
            nodes.append(cache[pc])
        for n, nxt in zip(nodes, nodes[1:]):
            fall = n['offset']+len(n['bytes'])//2
            if n['op']=='j' or n['op'].startswith('b'):
                target = int(re.search(r'\b([0-9a-f]+)\s+<',n['operands'])[1],16)-base
                assert nxt['offset'] in ([target] if n['op']=='j' else [target,fall])
            else:
                assert nxt['offset'] == fall
        assert nodes[-1]['op']=='retw.n'
        actual_calls=[re.search(r'<([^>]+)>',n['operands'])[1] for n in nodes if n['op'].startswith('call')]
        assert actual_calls == calls
        return dict(instructions=len(nodes), nodes=nodes, calls=actual_calls)
    traces = dict(wrapper_timeout=trace('s3_pp_spi_reap',WRAPPER,['s3_spi_reap']),
                  sdk_empty_excluding_queue=trace('spi_device_get_trans_result',SDK_EMPTY,['xQueueReceive']))
    if current:
        for host, select in [(1,[0x30,0x32,0x40]),(2,[0x30,0x32,0x35,0x38,0x3b])]:
            prefix = PREFIX+select+[0x43,0x46,0x48,0x4b]
            traces[f'host{host}_running']=trace('s3_spi_reap',prefix+[0x4e,0x51,0x89],[])
            traces[f'host{host}_idle_empty']=trace('s3_spi_reap',prefix+[0x56,0x59,0x5c,0x5f,0x62,0x65,0x4e,0x51,0x89],['spi_device_get_trans_result'])
    else:
        traces['empty']=trace('s3_spi_reap',PREFIX+[0x30,0x33,0x36,0x39,0x3c,0x3f,0x58],['spi_device_get_trans_result'])
    return dict(ELF_sha256=record['ELF_sha256'],traces=traces)

def main():
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);a=p.parse_args()
    out=ROOT/'reports/s3-spi-running-guard/path-cost';out.mkdir(exist_ok=True)
    old=audit(ROOT/'reports/s3-budgeted-fill/sdk-S/image',a.toolchain.resolve(),ROOT/'build/guard-path.elf',False)
    rows=[];images={'old-S':old}
    for standard in ('S','T'):
        new=audit(ROOT/f'reports/s3-spi-running-guard/sdk-{standard}/image',a.toolchain.resolve(),ROOT/'build/guard-path.elf',True)
        images['new-'+standard]=new
        t=old['traces']; baseline=sum(t[k]['instructions'] for k in ('wrapper_timeout','empty','sdk_empty_excluding_queue'))
        t=new['traces']
        for host in (1,2):
            running=t['wrapper_timeout']['instructions']+t[f'host{host}_running']['instructions']
            idle=sum(t[k]['instructions'] for k in ('wrapper_timeout',f'host{host}_idle_empty','sdk_empty_excluding_queue'))
            rows.append(dict(standard=standard,host=host,old_empty_excluding_queue=baseline,
                new_running=running,new_idle_empty_excluding_queue=idle,
                running_instruction_saving_excluding_removed_queue=baseline-running,
                idle_empty_instruction_increase=idle-baseline,
                sufficient_running_fraction_if_queue_cost_zero=(idle-baseline)/(idle-running)))
    result=dict(scope=__doc__,images=images,rows=rows,
        assumptions=['Valid dedicated raw bus and one outstanding transfer; valid descriptors and no fault.',
            'Running path: CMD.USR=1. Idle-empty path: CMD.USR=0 and SDK result queue empty.',
            'SDK empty path uses non-NO_RETURN_RESULT device and xQueueReceive(...,0) returns false.',
            'Old S image is comparison baseline; new T and S independently checked.'],
        limitations=['Queue body excluded, not assigned zero measured cost.',
            'IRQ, window spill/fill, MMIO waits, memory contention and cycles not bounded.',
            'No claim about completion/submit paths, full owner scan cost, or measured throughput.'],
        all_declared_path_edges_and_call_targets_verified=True,CPU_estimate_reduced=False)
    (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(rows,indent=2))
if __name__=='__main__':main()
