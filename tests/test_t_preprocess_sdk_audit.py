import json
from pathlib import Path
import tempfile
import unittest
from ci import t_preprocess_sdk_audit as audit

class SDKEnumerationTests(unittest.TestCase):
    def run_audit(self,folder):
        return audit.audit(folder/'toolchain',folder/'missing.elf',folder/'config.json',folder/'idf',folder/'provenance.json')
    @staticmethod
    def rows(result):return {r['name']:r for r in result['checks']}
    def test_missing_first_inputs_keeps_all_source_and_terminal_checks(self):
        with tempfile.TemporaryDirectory() as directory:r=self.run_audit(Path(directory))
        rows=self.rows(r)
        self.assertEqual(rows['input ELF']['status'],'FAIL')
        for name in audit.SOURCE_INPUTS:self.assertIn('compiled source/header '+name,rows)
        for name in audit.MAIN_UNITS:self.assertIn('SLP disabled '+name,rows)
        self.assertIn('cache enabled receive condition documented',rows)
        self.assertFalse(r['all_static_checks_pass'])
    def test_missing_first_chunk_does_not_hide_later_six_chunks(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);parts=folder/'full-elf.parts';parts.mkdir();manifest=[]
            for i in range(7):
                name=f'full-elf.parts/part-{i:03d}';data=f'chunk{i}'.encode()
                if i:(folder/name).write_bytes(data)
                manifest.append(dict(path=name,bytes=len(data),sha256=audit.sha(data)))
            (folder/'provenance.json').write_text(json.dumps({'full_elf_chunks':manifest}))
            r=self.run_audit(folder)
        rows=self.rows(r)
        self.assertEqual(rows['full ELF chunk full-elf.parts/part-000']['status'],'FAIL')
        for i in range(1,7):self.assertEqual(rows[f'full ELF chunk full-elf.parts/part-{i:03d}']['status'],'PASS')
        self.assertEqual(rows['full ELF chunks and debug stripping preserve all allocated bytes']['status'],'BLOCKED')
    def test_early_source_failure_preserves_later_valid_source(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);hashes={n:audit.sha((audit.ROOT/n).read_bytes()) for n in audit.SOURCE_INPUTS}
            hashes[audit.SOURCE_INPUTS[0]]='0'*64
            (folder/'provenance.json').write_text(json.dumps({'source_sha256':hashes}))
            r=self.run_audit(folder)
        rows=self.rows(r)
        self.assertEqual(rows['compiled source/header '+audit.SOURCE_INPUTS[0]]['status'],'FAIL')
        self.assertEqual(rows['compiled source/header '+audit.SOURCE_INPUTS[-1]]['status'],'PASS')
    def test_malformed_provenance_still_enumerates_fixed_criteria(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);(folder/'provenance.json').write_text('[]');r=self.run_audit(folder)
        rows=self.rows(r)
        self.assertEqual(rows['input provenance']['status'],'FAIL')
        self.assertIn('compiled source/header '+audit.SOURCE_INPUTS[-1],rows)
        self.assertIn('full ELF chunk full-elf.parts/part-006',rows)
        self.assertIn('normal interrupt entry has no CPENABLE writes',rows)

if __name__=='__main__':unittest.main()
