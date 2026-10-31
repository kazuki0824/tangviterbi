"""Pinned source anchors for IRQ refinement obligations, not hardware proof."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'reports/s3-spi-irq-hardware'

def report():
    checks=[]
    def check(name,ok):
        assert ok,name
        checks.append(dict(name=name,passed=True))
    manifest=json.loads((BASE/'sources.json').read_text())
    for path,item in manifest['sources'].items():
        check('hash '+path,hashlib.sha256((BASE/'sources'/Path(path).name).read_bytes()).hexdigest()==item['sha256'])
    prior=json.loads((ROOT/'reports/s3-raw-tasks/sources.json').read_text())
    route=(ROOT/'reports/s3-raw-tasks/sources/intr_alloc.c').read_bytes()
    check('saved allocator hash',hashlib.sha256(route).hexdigest()==prior['intr_alloc.c']['sha256'])
    hal=(BASE/'sources/spi_hal.c').read_text()
    iram=(BASE/'sources/spi_hal_iram.c').read_text()
    ll=(BASE/'sources/spi_ll.h').read_text()
    check('initial software done','spi_ll_enable_int(hw);\n    spi_ll_set_int_stat(hw);' in hal)
    setup=iram[iram.index('void spi_hal_setup_trans('):iram.index('void spi_hal_user_start(')]
    check('setup clears old done','spi_ll_clear_int_stat(hal->hw);' in setup)
    start=iram[iram.index('void spi_hal_user_start('):iram.index('bool spi_hal_usr_is_done(')]
    check('apply before start',start.index('spi_ll_apply_config')<start.index('spi_ll_user_start'))
    check('hardware update wait','while (hw->cmd.update);' in ll)
    check('W1C register write','hw->dma_int_clr.trans_done = 1;' in ll)
    check('user command start','hw->cmd.usr = 1;' in ll)
    check('raw done predicate','return hw->dma_int_raw.trans_done;' in ll)
    return dict(checks=checks,hardware_refinement_proven=False,
                isr_execution_upper_cycles=None,receiver_adopted=False)

if __name__=='__main__':
    (BASE/'audit.json').write_text(json.dumps(report(),indent=2)+'\n')
