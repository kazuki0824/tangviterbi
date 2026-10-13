"""Independent conservation / rejection checks for the simultaneous estimate."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from dual_s3_20k_estimate import allocate, candidate_budgets, fft_budget, S_RS, T_RS, rpc_catalog


class EstimateTest(unittest.TestCase):
    def test_half_duplex_cannot_count_both_directions_twice(self):
        p=[dict(name='shared',kind='half',capacity_MBps=80,batch_pages=1)]
        self.assertIsNone(allocate(p,60,30))
        a=allocate(p,60,10)[0]
        self.assertEqual(a['spare_MBps'],10)
        self.assertEqual(a['up_MBps'],60)
        self.assertEqual(a['down_MBps'],10)

    def test_direction_and_exact_capacity(self):
        p=[dict(name='TX',kind='down',capacity_MBps=100,batch_pages=1)]
        self.assertIsNone(allocate(p,99,1))
        self.assertEqual(allocate(p,100,0)[0]['spare_MBps'],0)

    def test_full_frame_conservation_not_peak_confusion(self):
        mean=48*28860000/39936
        self.assertAlmostEqual(mean*188*8,52170000)
        self.assertGreater(S_RS,mean)
        self.assertAlmostEqual(T_RS*188*8,23234699.940582296)

    def test_modes_and_fft_periods(self):
        r=[fft_budget(n) for n in (2048,4096,8192)]
        self.assertEqual([x['period_us'] for x in r],[259.875,519.75,1039.5])
        self.assertTrue(all(x['compute_us']<x['period_us'] for x in r))
        self.assertAlmostEqual(r[0]['SDRAM_MBps'],r[2]['SDRAM_MBps'])
        self.assertGreater(fft_budget(clock=125)['compute_utilization'],1)

    def test_resident_overflows_without_reducing_precision(self):
        rows={r['id']:r for r in candidate_budgets()}
        self.assertGreater(rows['C_resident_shared_RS']['resources']['BSRAM'],46)
        self.assertLess(rows['B_tiled_shared_RS']['resources']['BSRAM'],46)
        self.assertFalse(rows['A_tiled_independent_RS']['resource_budget_pass'])
        self.assertTrue(rows['B_tiled_shared_RS']['tiled_FFT_55percent_schedule_rejected'])
        self.assertTrue(all(not r['performance_verified'] and not r['adopted'] for r in rows.values()))

    def test_rpc_message_overhead_is_not_rf_three_page_overhead(self):
        legacy={'RS_subpartitions':{'solver':{'records':[
            {'name':'syndrome','pages':1,'direction':'FPGA_to_S3'}]}}}
        ports=({"name":"SPI2_Octal80","kind":"half","capacity_MBps":70.32765774788953,
                "capacity_Bps":80000000,"batch_pages":3,"pin_lower_bound":10},
               {"name":"SPI3_Quad80","kind":"half","capacity_MBps":33.3958418263351,
                "capacity_Bps":40000000,"batch_pages":1,"pin_lower_bound":6})
        routes=rpc_catalog(legacy,[ports])['solver']['routes']
        self.assertEqual(len(routes),2)
        octal=next(r for r in routes if r['message_ports']==['SPI2_Octal80'])
        expected_us=4096/80+80/640+.25+20
        self.assertAlmostEqual(octal['RPC_time_fractions'][0],expected_us/(204/S_RS*1e6))
        self.assertAlmostEqual(sum(p['up_MBps'] for p in octal['remaining_RF_control_allocation']),100.01)
        self.assertTrue(all(p['spare_MBps']>=0 for p in octal['remaining_RF_control_allocation']))

    def test_factorized_fft_order_against_independent_dft(self):
        import numpy as np
        rng=np.random.default_rng(2718)
        for a,b in ((32,64),(64,64),(64,128)):
            x=rng.integers(-512,512,a*b)+1j*rng.integers(-512,512,a*b)
            # n=n1+a*n2; k=k2+b*k1. Intermediate row-major transposition
            # permits 8-column (32-byte) bursts, without dropping any sample.
            y=np.fft.fft(x.reshape(b,a),axis=0)
            y*=np.exp(-2j*np.pi*np.arange(b)[:,None]*np.arange(a)[None,:]/(a*b))
            z=np.fft.fft(y,axis=1).T.reshape(-1)
            np.testing.assert_allclose(z,np.fft.fft(x),rtol=1e-11,atol=1e-9)


if __name__=='__main__':unittest.main()
