"""Prove the extracted RTL comparison for every 13-bit operand pair."""
from pathlib import Path
import re,shutil,subprocess,tempfile,unittest
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(shutil.which('yosys'),'Yosys SAT required')
class GroupedEquivalence(unittest.TestCase):
    def test_all_operand_pairs(self):
        text=(ROOT/'experiments/shared_tc8_k7_grouped.sv').read_text()
        function=re.search(r'    function automatic \[12:0\] grouped_difference;.*?    endfunction',text,re.S).group()
        miter='module k7_grouped_miter(input [12:0] a,b, output equal);\n'+function+'\nwire [12:0] reference_difference=a-b;\nassign equal=reference_difference==grouped_difference(a,b);\nendmodule\n'
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'miter.sv';p.write_text(miter)
            r=subprocess.run(['yosys','-Q','-p',f'read_verilog {p}; prep -top k7_grouped_miter; sat -verify -prove equal 1 -show-inputs'],capture_output=True,text=True,timeout=60)
            self.assertEqual(r.returncode,0,r.stdout+r.stderr)
            self.assertIn('SUCCESS',r.stdout)

if __name__=='__main__':unittest.main()
