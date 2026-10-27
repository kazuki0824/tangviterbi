import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class IntegratedEstimateTest(unittest.TestCase):
    def test_all_declared_banks_and_payload_conservation(self):
        for name in ('T-8','S-5','S-6'):
            r=json.loads((ROOT/f'reports/receiver-integrated-estimate/paths-{name}.json').read_text())
            self.assertEqual({x['bank_samples'] for x in r['rows']},{11264,12288,12289,14288,14352})
            self.assertEqual(len(r['rows']),40)
            for x in r['rows']:
                self.assertEqual(sum(8*s[1]+2*s[2] for s in x['stats']),x['banks']*x['bank_samples'])
    def test_same_configuration_resource_tradeoff(self):
        r=json.loads((ROOT/'reports/receiver-integrated-estimate/estimate.json').read_text())
        raw=next(x for x in r['FPGA'] if x['kernel']=='slotaddr-154' and not x['T_FIR_on_SoC'])
        moved=next(x for x in r['FPGA'] if x['kernel']=='slotaddr-154' and x['T_FIR_on_SoC'])
        self.assertEqual(raw['whole_ledger']['logic_sites_estimate']-moved['whole_ledger']['logic_sites_estimate'],752)
        self.assertEqual(moved['remaining']['BSRAM'],2)
        s=next(x for x in r['cpu'] if x['standard']=='S' and x['share']==6)
        self.assertGreater(s['additional_scan_cost_sensitivity'][2]['core0_percent'][1],100)
        self.assertLess(s['fill_reduction_25pct_and_scan_1500_cycles_core0'][1],100)
        self.assertFalse(r['receiver_adopted'])
