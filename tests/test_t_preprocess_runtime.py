"""Same-C semantics and strict evidence gating for the fresh finite model."""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock
from ci import t_preprocess_runtime_audit as audit


class RuntimeModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        # These fees only drive semantic tests. They cannot pass the final gate.
        cls.binary,cls.build=audit.build(Path(cls.tmp.name),audit.PROVISIONAL)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_owner_init_and_fatal_contracts(self):
        result=subprocess.run([str(self.binary),'--selftest'],capture_output=True,text=True)
        detail=json.loads(result.stdout)
        self.assertEqual(result.returncode,0)
        self.assertEqual(detail['executed'],16)
        self.assertEqual(detail['failed'],0)

    def test_source_destruction_and_independent_output(self):
        case={'id':'nominal_finite_8','banks':8}
        row=audit.execute(self.binary,case)
        self.assertEqual(audit.row_errors(row,case),[])
        self.assertTrue(row['candidate_pass'])
        self.assertGreater(row['complex_outputs_checked'],0)
        self.assertGreater(row['destroyed_banks'],0)
        self.assertFalse(row['complete_processing_and_dma_drain'])
        self.assertGreater(row['unconsumed_accepted_words'],0)

    def test_queue_and_publication_faults(self):
        for injection in (1,2,3,4,6,7,8,9):
            case={'id':f'injection_{injection}','inject':injection}
            with self.subTest(injection=injection):
                row=audit.execute(self.binary,case)
                self.assertEqual(audit.row_errors(row,case),[])

    def test_functional_fault_cannot_masquerade_as_capacity_rejection(self):
        case={'id':'nominal_candidate_100','banks':8}
        row=audit.execute(self.binary,case)
        row.update(task_fault=13,native_fault=0,adapter_fault=0,outcome=0)
        self.assertEqual(audit.classify_stop(row)['kind'],'unrecognized_functional_stop')
        self.assertTrue(any('not a recognized' in error for error in audit.row_errors(row,case)))
        row.update(task_fault=5,adapter_fault=6,max_sampled_core0_step=1)
        self.assertFalse(audit.classify_stop(row)['capacity_stop'])

    def test_generated_owner_is_verbatim(self):
        text=audit.generated(audit.PROVISIONAL)['runtime.c']
        self.assertEqual(text,(audit.ROOT/'experiments/t_preprocess_integration_probe/tpre_runtime.c').read_text())

    def test_instrumentation_anchor_drift_rejected(self):
        for text in ('missing','anchor anchor'):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):audit.replace(text,'anchor','replacement')

    def test_every_stale_source_is_reported(self):
        document={'schema_version':2,'status':'PROVISIONAL','fees':copy.deepcopy(audit.PROVISIONAL),
                  'source_sha256':{name:'0'*64 for name in audit.HOST_C_SOURCES}}
        document['source_sha256']['missing-runtime-source.c']='0'*64
        errors=audit.verify_costs(document)
        self.assertEqual(sum(e.startswith('stale source:') for e in errors),len(audit.HOST_C_SOURCES))
        self.assertTrue(any('not READY' in e for e in errors))
        self.assertTrue(any('missing source:' in e for e in errors))

    def test_invalid_evidence_enumerates_all_scenarios(self):
        for document in ({'schema_version':2,'status':'PROVISIONAL','fees':{},'source_sha256':{}},['not an object']):
            with self.subTest(document=document):
                report=audit.run_audit(document)
                statuses={row['id']:row['status'] for row in report['checks']}
                self.assertEqual(report['candidate_status'],'BLOCKED')
                for case in audit.CASES:self.assertEqual(statuses[case['id']],'BLOCKED')
                self.assertIn('diagnostic_prepare_1024',statuses)
                self.assertIn('source_destruction_preserves_complete_trace',statuses)
                self.assertIn('all_model_source_hashes',statuses)

    def test_host_source_subset_cannot_claim_linked_evidence_ready(self):
        document={'schema_version':2,'status':'READY','fees':copy.deepcopy(audit.PROVISIONAL),
                  'source_sha256':{name:audit.sha(audit.ROOT/name) for name in audit.HOST_C_SOURCES}}
        errors=audit.verify_costs(document)
        required=set(audit.TARGET_SOURCES+audit.COST_DEPENDENCIES)-set(audit.HOST_C_SOURCES)
        for name in required:
            with self.subTest(required=name):
                self.assertTrue(any(name in error and error.startswith('unbound') for error in errors))
        for artifact in ('t_preprocess_integration_probe.elf.gz','sdk/audit.json','sdk/provenance.json'):
            self.assertTrue(any(artifact in error and error.startswith('unbound selected artifact:') for error in errors))

    def test_early_scenario_failure_does_not_skip_later_cases(self):
        # No target evidence is asserted here: this tests non-fail-fast control.
        visited=[]
        def execute(binary,case):
            visited.append(case['id'])
            raise RuntimeError('injected independent scenario failure')
        document={'schema_version':2,'status':'PROVISIONAL','fees':audit.PROVISIONAL,'source_sha256':{}}
        with mock.patch.object(audit,'build',return_value=(self.binary,{})), \
             mock.patch.object(audit,'execute',side_effect=execute), \
             mock.patch.object(audit,'model_step_envelope',return_value={'bound':20000}):
            report=audit.run_audit(document,allow_provisional=True)
        self.assertEqual(visited,[case['id'] for case in audit.CASES]+['derived_bound_sensitivity','diagnostic_prepare_1024'])
        self.assertEqual(report['candidate_status'],'BLOCKED')
        self.assertTrue(any(row['id']=='all_model_source_hashes' for row in report['checks']))


if __name__=='__main__':unittest.main()
