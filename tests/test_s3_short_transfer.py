from pathlib import Path
import subprocess,tempfile,unittest
from experiments.s3_short_transfer import simulate
ROOT=Path(__file__).resolve().parents[1]
class ShortTransferTest(unittest.TestCase):
    def test_real_c_subarena_leases_and_SPI_wire_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name,sources,extra in (
                ('packing',['experiments/s3_parallel_pack.c','tests/s3_parallel_pack_host.c'],[]),
                ('spi',['experiments/'+s for s in ('s3_parallel_pack.c','s3_parallel_spi.c','s3_spi_transport.c','s3_transport.c')]+['tests/s3_parallel_spi_host.c'],['-Itests/s3_sdk_shim','-DS3_RAW_ONLY_SPI=1'])):
                exe=str(Path(tmp)/name)
                subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread','-fsanitize=undefined','-fno-sanitize-recover=all','-Iexperiments','-DS3_RAW_TRANSFER_BYTES=16384','-DS3_PP_CORE0_SIXTEENTHS=5',*extra,*sources,'-o',exe],cwd=ROOT,check=True)
                r=subprocess.run([exe,'2000'] if name=='packing' else [exe],capture_output=True,text=True,timeout=120)
                self.assertEqual(r.returncode,0,r.stdout+r.stderr);print(r.stdout.strip())
    def test_serialization_and_ordered_reclaim(self):
        r=simulate(16384,320,40,[12289,14352]*64)
        self.assertIsNone(r['first_capacity_failure'])
        self.assertEqual(r['free_bytes_at_peak'],93)
        self.assertEqual(r['retired'],r['transfers'])
        free=[0,0]
        for seq,port,start,end in r['schedule']:
            self.assertGreaterEqual(start,free[port])
            self.assertEqual((end-start)*[8,4][port],(16384*8+80)*3)
            free[port]=end
        self.assertIsNotNone(simulate(32768,320,40,[12289,14352]*64)['first_capacity_failure'])
    def test_small_hand_computed_schedule(self):
        r=simulate(16384,100,10,[12288])
        self.assertEqual(r['schedule'],[[0,0,24000,73182]])
        self.assertEqual(r['peak_reserved_unretired_bytes'],30720)
