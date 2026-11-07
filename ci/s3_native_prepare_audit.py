"""Pinned SDK sentinel fill counts and phase-aware scheduling conditions, not WCET."""
import argparse, gzip, hashlib, json, os, subprocess
from pathlib import Path
from fractions import Fraction
from ci.s3_pack_cfg_audit import ROW
ROOT=Path(__file__).resolve().parents[1]

def budget(rate, cycles_per_word=5):
    cpp=240//rate
    words=3072+4096
    cycles=words*cycles_per_word
    samples=(cycles+cpp-1)//cpp
    return dict(rate_msps=rate, words=words, body_instructions=words*5,
                ideal_body_cycles=cycles, ideal_body_us=cycles/240,
                samples_during_body_rounded_up=samples,
                latest_entry_written_body_only=12288+2000-samples,
                uniform_late_poll_budget_cycles=2000*cpp,
                body_exceeds_uniform_poll_budget=cycles>2000*cpp,
                nominal_banks_per_s=float(Fraction(rate*1000000,12288)),
                nominal_fill_instructions_per_s=float(Fraction(rate*1000000*words*5,12288)))

def main():
    p=argparse.ArgumentParser();p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output;out.mkdir(parents=True,exist_ok=True)
    data=gzip.decompress((ROOT/'reports/s3-pack-span/sdk/n16r8-late-stacks-no-phy-nvs-raw-only-spi/s3_raw_probe.elf.gz').read_bytes())
    expected=json.loads((ROOT/'reports/s3-pack-span/sdk-loop-summary.json').read_text())['ELF_sha256']
    elf=ROOT/'build/native-audit/sdk.elf';elf.parent.mkdir(parents=True,exist_ok=True);elf.write_bytes(data)
    tc=a.toolchain.resolve();env=os.environ.copy();env['XTENSA_GNU_CONFIG']=str(tc/'lib/xtensa_esp32s3.so')
    checks=[dict(name='pinned_ELF',passed=hashlib.sha256(data).hexdigest()==expected)]
    dis=[]
    for lo,hi in [(0x403777c6,0x403777d9),(0x403777ea,0x403777fd)]:
        text=subprocess.check_output([str(tc/'bin/xtensa-esp-elf-objdump'),'-d',f'--start-address={lo}',f'--stop-address={hi}',str(elf)],text=True,env=env)
        dis.append(text)
        ops=[m[3] for line in text.splitlines() if (m:=ROW.match(line))]
        checks.append(dict(name=f'fill_loop_{lo:x}',passed=ops==['loop','extui','addx4','memw','s32i.n','addi.n','memw'],ops=ops))
    cfg=json.loads((ROOT/'reports/s3-pack-span/cfg/results.json').read_text())
    owners=[]
    for standard,rate in [('T',16),('S',40)]:
        row=next(r for r in cfg['rows'] if r['standard']==standard and r['worker']==0 and r['bank_samples']==12288 and r['first']==0 and r['slice_pairs']==512)
        packing=row['ideal_one_cycle_per_instruction_Mcycles_s']
        fill=budget(rate)['nominal_fill_instructions_per_s']/1e6
        api=(rate*2.5+.01)*240*20/32768
        owners.append(dict(standard=standard,packing_ideal_Mcycles_s=packing,fill_ideal_Mcycles_s=fill,old_assumed_API_Mcycles_s=api,conditional_total_Mcycles_s=packing+fill+api,conditional_remaining_Mcycles_s=240-packing-fill-api))
    report=dict(scope=__doc__,conditional_owner_scenario=owners,ELF_sha256=expected,checks=checks,rows=[budget(16),budget(40)],
                instruction_count_includes='Five instructions per word in two hardware loops; no setup or exit',
                excluded=['loop setup','bank callback bodies','all other poll logic','MMIO and memory stalls','interrupts','packing','SPI','clock'],
                schedule_condition='written_at_INDEX_read + ceil((prepare_tail_cycles + external_gap_cycles + next_poll_to_INDEX_cycles)/cpp) <= 14288',
                full_WCET_proven=False,uniform_poll_bound_is_not_necessary_when_preparing_early=True)
    (out/'results.json').write_text(json.dumps(report,indent=2)+'\n');(out/'fill.dis').write_text('\n'.join(dis))
    print(json.dumps(report,indent=2));return any(not x['passed'] for x in checks)
if __name__=='__main__':raise SystemExit(main())
