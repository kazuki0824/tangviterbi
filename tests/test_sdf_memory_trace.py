"""Extract current SDF external-delay traffic; retain independent FFT oracle.
The RAM is ideal. No SDRAM cache/service or whole receiver claim is made.
"""
import hashlib,json,os,shutil,subprocess,tempfile,unittest
from pathlib import Path
from fractions import Fraction
from test_shared_sdf_fft import TB,ROOT,ARCHIVE,ORACLE,vectors


def bench():
    s=TB.replace('parameter MODE=2,', 'parameter PACED=0;\nparameter MODE=2,')
    s=s.replace('reg clk=0;', 'localparam PERIOD=40095*(1<<MODE);\ninteger offered=0,within_frame=0;\nreg clk=0;')
    s=s.replace('sent<=sent+1;', '$display("INPUT %0d %0d",cycles,sent);\n   sent<=sent+1;')
    s=s.replace('if(re) ext_q<=mem[ra];', 'if(re)begin ext_q<=mem[ra];$display("READ %0d %0d",cycles,ra);end')
    s=s.replace('if(we) mem[wa]<=wd;', 'if(we)begin mem[wa]<=wd;$display("WRITE %0d %0d",cycles,wa);end')
    s=s.replace('in_valid=sent<FRAMES*N;', '''within_frame=((cycles%PERIOD)*64)/1215;
 if(within_frame>N)within_frame=N;
 offered=(cycles/PERIOD)*N+within_frame;
 in_valid=sent<FRAMES*N && (!PACED || sent<offered);''')
    return s.replace('if(!STALL && (max_input_gap', 'if(!PACED && !STALL && (max_input_gap')


@unittest.skipUnless(shutil.which('iverilog') and shutil.which('vvp'),'Icarus required')
class SDFMemoryTraceTest(unittest.TestCase):
    def test_external_contract_and_complete_frame_oracle(self):
        results=[]
        for mode,paced in ((0,1),(1,1),(2,1),(2,0)):
            n=1<<(11+mode);words=vectors(n,'random')
            expected=sum((ORACLE.reference_fft(words[f*n:(f+1)*n],ORACLE.load_quarter()) for f in range(3)),[])
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp);(p/'tb.sv').write_text(bench())
                (p/'input.hex').write_text(''.join(f'{w:08x}\n' for w in words))
                subprocess.run(['iverilog','-g2012','-s','tb',f'-Ptb.MODE={mode}',f'-Ptb.PACED={paced}',
                    '-o',str(p/'sim'),str(p/'tb.sv'),str(ROOT/'rtl/shared_sdf_fft.sv'),str(ARCHIVE/'rtl/research_sdf_twiddle.sv')],cwd=ARCHIVE,check=True,timeout=30)
                run=subprocess.run(['vvp',str(p/'sim'),f'+INPUT_HEX={p/"input.hex"}'],cwd=ARCHIVE,text=True,capture_output=True,timeout=90)
                self.assertEqual(run.returncode,0,run.stdout[-2000:]+run.stderr)
            parsed={tag:[] for tag in ('INPUT','READ','WRITE','OUT')}
            for line in run.stdout.splitlines():
                fields=line.split()
                if fields and fields[0] in parsed:parsed[fields[0]].append(fields[1:])
            outputs=parsed['OUT'];self.assertEqual(len(outputs),3*n)
            for seq,row in enumerate(outputs):
                self.assertEqual(int(row[1]),ORACLE.bit_reverse(seq%n,11+mode))
                self.assertEqual(int(row[2],16),expected[seq])
            inputs=[(int(t),int(i)) for t,i in parsed['INPUT']]
            reads=[(int(t),int(a)) for t,a in parsed['READ']]
            writes=[(int(t),int(a)) for t,a in parsed['WRITE']]
            if mode!=2:self.assertEqual((reads,writes),([],[]))
            else:
                for events,delay in ((reads,1),(writes,6)):
                    self.assertGreaterEqual(len(events),3*n)
                    for j,(t,a) in enumerate(events):
                        self.assertEqual(t,inputs[j][0]+delay)
                        self.assertEqual(a,j%4096)
            # Analyze only the first 3 complete input frames, excluding tail.
            lines=[reads[j][0] for j in range(min(len(reads),3*n)) if j%8==0]
            gaps=[b-a for a,b in zip(lines,lines[1:])]
            results.append(dict(mode=mode+1,paced=bool(paced),checked_bins=3*n,
                input_count=len(inputs),read_count=len(reads),write_count=len(writes),
                outer_delay_words=4096 if mode==2 else 0,
                external_bytes_per_symbol=8*n if mode==2 else 0,
                ideal_coalesced_BL8_per_symbol=2*n//8 if mode==2 else 0,
                external_MBps=float(Fraction(8*n,1)/Fraction(2079*(1<<mode),8)) if mode==2 else 0,
                read_line_start_min_gap=min(gaps) if gaps else None,
                read_line_start_max_gap=max(gaps) if gaps else None,
                first_events=dict(inputs=inputs[:9],reads=reads[:9],writes=writes[:9]),
                oracle_bit_exact=True))
        if os.environ.get('SDF_MEMORY_TRACE_REPORT'):
            Path(os.environ['SDF_MEMORY_TRACE_REPORT']).write_text(json.dumps(dict(scope=__doc__,results=results,
                source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in
                    (Path(__file__),ROOT/'rtl/shared_sdf_fft.sv',ROOT/'tests/test_shared_sdf_fft.py')},
                actual_cache_implemented=False,SDRAM_deadlines_verified=False),indent=2)+'\n')

if __name__=='__main__':unittest.main()
