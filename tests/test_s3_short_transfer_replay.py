from pathlib import Path
import subprocess,tempfile,unittest
from experiments.s3_short_transfer import simulate
ROOT=Path(__file__).resolve().parents[1]
class ReplayTest(unittest.TestCase):
    def test_phase_changes_capacity_in_actual_C(self):
        for chunk,phase,scan in ((16384,0,40),(16384,2400,40),(32768,0,40),(16384,2400,30)):
            with self.subTest(chunk=chunk,phase=phase,scan=scan),tempfile.TemporaryDirectory() as tmp:
                counts=[12289,14352]*64
                r=simulate(chunk,320,scan,counts,scan_phase_cycles=phase)
                events=[];switch=0;total=0;fail=r['first_capacity_failure']
                for k,n in enumerate(counts):
                    events.append((switch+96,0,k%3,n,int(fail is not None and switch+96==fail['at_cycles']),total))
                    events.append((switch+76800,1,k%3,0,0,0));switch+=n*6;total+=n
                for seq,port,start,end in r['schedule']:
                    reap=phase+((end-phase+scan*240-1)//(scan*240))*scan*240
                    events.append((reap,2,0,0,0,seq));events.append((start,3,0,0,0,seq))
                events.sort()
                header='static const struct event events[]={\n'+''.join('{%d,%d,%d,%d,%dULL,%dULL},\n'%(kind,bank,count,busy,seq,t) for t,kind,bank,count,busy,seq in events)+'};\n'
                (Path(tmp)/'events.h').write_text(header)
                exe=str(Path(tmp)/'replay')
                subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments','-I'+tmp,f'-DS3_RAW_TRANSFER_BYTES={chunk}','-DS3_PP_CORE0_SIXTEENTHS=5','experiments/s3_parallel_pack.c','tests/s3_short_transfer_replay_host.c','-o',exe],cwd=ROOT,check=True)
                done=subprocess.run([exe],capture_output=True,text=True)
                self.assertEqual(done.returncode,0,done.stdout+done.stderr)
                print(chunk,phase,scan,done.stdout.strip())
