"""Completion-edge turnover and late response stalls through the pin model."""
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch
import test_dual_sdram as baseline


class CompletionEdge(baseline.SDRAMTest):
    def test_protocol_data_masks_refresh_and_backpressure(self):
        bench=baseline.BENCH.replace(
            'wire rsp_ready=!(cycle>=1000 && cycle<4000);',
            'reg rsp_ready=0;\n'
            'always @(negedge clk)rsp_ready=!(cycle>=1000 && cycle<4000) && cycle%97>=7;\n'
            'integer turnover=0,completion_stalls=0;')
        bench=bench.replace('  if(valid && ready)begin',
            '  if(dut.completing && !rsp_ready)completion_stalls=completion_stalls+1;\n'
            '  if(dut.completing && valid && ready && rv && rsp_ready)turnover=turnover+1;\n'
            '  if(valid && ready)begin')
        bench=bench.replace('   $display("PASS requests=',
            '   if(OPEN_PAGE && (turnover==0 || completion_stalls==0))'
            '$fatal(1,"completion edge not covered");\n'
            '   $display("PASS turnover=%0d completion_stalls=%0d requests=')
        bench=bench.replace('",received,refs,max_ref_gap',
                            '",turnover,completion_stalls,received,refs,max_ref_gap')
        report=os.environ.get('DUAL_SDRAM_PIPELINE_REPORT')
        with patch.object(baseline,'BENCH',bench), patch.dict(os.environ,
                {'DUAL_SDRAM_REPORT':report or ''}):
            super().test_protocol_data_masks_refresh_and_backpressure()
        if report:
            p=Path(report);data=json.loads(p.read_text())
            data['source_sha256']['tests/test_dual_sdram_pipeline.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            data['scope']='Independent SDRAM pins, completion-edge acceptance and late/long response stalls. No physical timing qualification.'
            p.write_text(json.dumps(data,indent=2)+'\n')
