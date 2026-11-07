"""Pinned source-path checks, deliberately not a WCET or binary CFG audit."""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'reports/s3-spi-wait-audit'

def run():
    manifest=json.loads((BASE/'sources.json').read_text())
    checks=[]
    def check(name,ok):
        checks.append(dict(name=name,passed=bool(ok)))
        if not ok:raise AssertionError(name)
    for path,item in manifest['sources'].items():
        check('source hash '+path,hashlib.sha256((BASE/'sources'/Path(path).name).read_bytes()).hexdigest()==item['sha256'])
    previous=json.loads((ROOT/'reports/s3-spi-isr-placement/sources.json').read_text())
    for path in ('esp_driver_spi/src/gpspi/spi_master.c','esp_hw_support/spi_bus_lock.c'):
        check('previous SDK identity '+path,manifest['sources'][path]['sha256']==previous['sources'][path])
    master=(BASE/'sources/spi_master.c').read_text();queue=(BASE/'sources/queue.c').read_text()
    for name,end in [('xQueueGenericSend','xQueueGenericSendFromISR'),('xQueueReceive','xQueueSemaphoreTake')]:
        body=queue[queue.index('BaseType_t '+name+'('):queue.index('BaseType_t '+end+'(')]
        check(name+' critical before zero timeout',body.index('taskENTER_CRITICAL')<body.index('xTicksToWait == ( TickType_t ) 0'))
    q=master[master.index('esp_err_t SPI_MASTER_ATTR spi_device_queue_trans('):master.index('esp_err_t SPI_MASTER_ATTR spi_device_get_trans_result(')]
    check('descriptor setup then queue then background request',q.index('setup_priv_desc(')<q.index('xQueueSend(')<q.index('spi_bus_lock_bg_request('))
    check('normal completion sends descriptor from ISR','xQueueSendFromISR(host->device[cs]->ret_queue, &host->cur_trans_buf, &do_yield)' in master)
    check('ISR repeats if bus lock exit asks retry','while (!spi_bus_lock_bg_exit(lock, trans_found, &do_yield))' in master)
    transport=(ROOT/'experiments/s3_spi_transport.c').read_text()
    check('raw enqueue zero tick','spi_device_queue_trans(p->device, &p->segments[0].base, 0)' in transport)
    check('raw reap zero tick','spi_device_get_trans_result(p->device, &done, 0)' in transport)
    check('manual DMA alignment flag','SPI_TRANS_DMA_BUFFER_ALIGN_MANUAL' in transport)
    check('SDK rejects manual misalignment before allocation',master.index('ESP_RETURN_ON_FALSE(!(trans_desc->flags & SPI_TRANS_DMA_BUFFER_ALIGN_MANUAL)')<master.index('uint32_t *temp = heap_caps_aligned_alloc'))
    return dict(checks=checks,scope=__doc__,elapsed_upper_cycles=None,WCET_proven=False,receiver_adopted=False)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(json.dumps(run(),indent=2)+'\n')
