"""Conditional event model of native S RF, real four-page RS RPC and credits.

Unlike the old ingress-only model, each RPC phase depends on completion of the
previous phase of the SAME batch. CPU, publication and downstream bounds are
explicit unmeasured contracts. No silicon WCET or connected RTL claim.
Times are microseconds; float comparisons use a 1e-7 us tolerance.
"""
import argparse
import hashlib
import heapq
import json
import math
from pathlib import Path

PAGE = 4096
RATE = 28.86e6 * 2 / (203 * 8)
BATCH = 204
BATCH_US = BATCH * 1e6 / RATE
RF_PAGE_US = PAGE / 100
EPS = 1e-7


def simulate(*, batches=128, window=8, host_pages=16, spi_api_us=20,
             lcd_api_us=8, bm_us=1000, forney_us=1000, phase_us=0,
             reader_us=2054/90, downstream_us=512, raw_slots=512, trace=False):
    events = []
    serial = 0
    now = 0.0
    busy = [False, False]
    ready_pages = set()
    dma_done = set()
    retired = host_retired = claimed = known = 0
    reading = False
    rpc_queue = []
    done_batches = []
    rpclat = []
    records = []
    peak_host = peak_window = peak_raw = 0
    failure = None
    tx_count = [0, 0]
    polls = 0
    rpc_polls = 0
    occupancy = [0.0, 0.0]
    # Generate bounded arrivals, then drain all pending RPCs and RF pages.
    capture_end = (batches + 1) * BATCH_US + phase_us + downstream_us
    total_pages = int(capture_end // RF_PAGE_US)

    def event(time, kind, value=None):
        nonlocal serial
        serial += 1
        heapq.heappush(events, (time, serial, kind, value))

    def start_read():
        nonlocal reading
        if not reading and retired in ready_pages:
            reading = True
            event(now + reader_us, 'retire')

    def record(kind, port, end, batch=None, stage=None, seq=None, count=None):
        if trace:
            records.append(dict(start_us=now, end_us=end, kind=kind,
                                port=port, batch=batch, stage=stage,
                                sequence=seq, pages=count))

    event(RF_PAGE_US, 'capture', 1)
    for batch in range(batches):
        event((batch+1)*BATCH_US + phase_us + downstream_us, 'rpc_ready', (batch, 0))

    while events:
        now, _, kind, value = heapq.heappop(events)
        # Arrival/retirement events at the same timestamp are processed together
        # before new reservations, so ordering never grants unreceived credit.
        pending = [(kind, value)]
        while events and events[0][0] <= now + EPS:
            _, _, kind, value = heapq.heappop(events)
            pending.append((kind, value))
        for kind, value in pending:
            if kind == 'capture':
                if value < total_pages:
                    event((value+1)*RF_PAGE_US, 'capture', value+1)
            elif kind == 'rf_done':
                port, first, count = value
                busy[port] = False
                dma_done.update(range(first, first+count))
                while host_retired in dma_done:
                    dma_done.remove(host_retired)
                    host_retired += 1
                event(now+3, 'publish', (first, count))
            elif kind == 'publish':
                first, count = value
                ready_pages.update(range(first, first+count))
            elif kind == 'retire':
                ready_pages.remove(retired)
                retired += 1
                reading = False
            elif kind == 'snapshot':
                event(value, 'status_done', retired)
            elif kind == 'status_done':
                busy[0] = False
                known = value
            elif kind == 'rpc_ready':
                batch, stage = value
                # Proposed 32-byte reply: ready/epoch/batch/ack + inverse.
                # This FPGA endpoint is not implemented yet. Charge explicit
                # transactions instead of giving the host free ready signals.
                rpc_queue.append((now, batch, stage, 'query' if stage in (0, 2) else 'data'))
            elif kind == 'rpc_done':
                busy[0] = False
                batch, stage, action = value
                if action == 'query':
                    rpc_queue.append((now, batch, stage, 'data'))
                    continue
                if action == 'ack':
                    done_batches.append(batch)
                    rpclat.append(now-((batch+1)*BATCH_US+phase_us+downstream_us))
                    continue
                if stage == 0:
                    event(now+bm_us, 'rpc_ready', (batch, 1))
                elif stage == 1:
                    # Worst observed stalled Chien service, charged for all 204.
                    event(now+BATCH*224/90, 'rpc_ready', (batch, 2))
                elif stage == 2:
                    event(now+forney_us, 'rpc_ready', (batch, 3))
                else:
                    # Keep raw codewords until correction/output completes.
                    end = now+BATCH*268/90
                    event(end, 'batch_done', batch)
            elif kind == 'batch_done':
                rpc_queue.append((now, value, 3, 'ack'))
        start_read()
        captured = min(total_pages, int((now+EPS)//RF_PAGE_US))
        available = captured-claimed
        peak_host = max(peak_host, min(total_pages, math.ceil((now-EPS)/RF_PAGE_US))-host_retired)
        arrived_words = max(0, int((now-phase_us-downstream_us)*RATE/1e6))
        # Capture is stopped after one extra batch. Include a currently filling
        # codeword; never free a batch at its last RPC DMA completion.
        arrived_words = min((batches+1)*BATCH, arrived_words+1)
        peak_raw = max(peak_raw, arrived_words-len(done_batches)*BATCH)
        if peak_raw > raw_slots:
            failure = dict(kind='raw_codeword_ring_overflow', time_us=now, codewords=peak_raw)
            break
        if peak_host > host_pages:
            failure = dict(kind='host_RF_ring_overflow', time_us=now, pages=peak_host)
            break
        if not busy[0]:
            used = claimed-known
            if rpc_queue:
                release, batch, stage, action = rpc_queue.pop(0)
                # Includes 10-byte SPI command/address, no omitted wire header.
                if action == 'data':
                    dummy = 16/80 if stage in (0, 2) else 0
                    end = now+spi_api_us+(PAGE+10)/80+.25+dummy
                else:
                    end = now+spi_api_us+(10+16+32)/80+.25
                    rpc_polls += 1
                busy[0] = True
                occupancy[0] += end-now
                record('RPC' if action == 'data' else 'RPC_'+action, 0, end, batch, stage)
                event(end, 'rpc_done', (batch, stage, action))
            elif used >= min(4, window) or (available and window-used < min(3, window, available)):
                # Poll only when the consumption frontier can grant new credit.
                end = now+spi_api_us+42/80+.25
                busy[0] = True
                polls += 1
                occupancy[0] += end-now
                record('status', 0, end)
                event(now+spi_api_us+10/80, 'snapshot', end)
            elif available >= min(3, window) and window-used >= min(3, window):
                first = claimed
                count = min(3, window)
                claimed += count
                available -= count
                end = now+spi_api_us+count*((PAGE+10)/80+.25)
                busy[0] = True
                tx_count[0] += count
                occupancy[0] += end-now
                record('RF', 0, end, seq=first, count=count)
                event(end, 'rf_done', (0, first, count))
        if not busy[1] and available and claimed-known < window:
            # Do not starve the efficient three-page Octal batch with LCD singles.
            reserve = min(3, window) if not busy[0] and not rpc_queue and claimed-known < min(4, window) else 0
            if available > reserve or captured == total_pages:
                first = claimed
                claimed += 1
                end = now+lcd_api_us+(PAGE+16)/80
                busy[1] = True
                tx_count[1] += 1
                occupancy[1] += end-now
                record('RF', 1, end, seq=first, count=1)
                event(end, 'rf_done', (1, first, 1))
        peak_window = max(peak_window, claimed-known)
        if peak_window > window:
            raise AssertionError('scheduler spent nonexistent FPGA credit')
        # Detect a stall instead of presenting a finite partial run as a pass.
        if not events and (host_retired != total_pages or len(done_batches) != batches):
            failure = dict(kind='drain_deadlock', pages=host_retired, rpc_batches=len(done_batches))
    result = dict(scope='conditional RF+credit+same-batch 4-stage RPC event model',
        RF_MBps=100, RF_page_bytes=PAGE, FPGA_pages=window, host_RF_pages=host_pages,
        RPC_batch_codewords=BATCH, RPC_batch_period_us=BATCH_US,
        CPU_BM_contract_us=bm_us, CPU_Forney_contract_us=forney_us,
        downstream_latency_contract_us=downstream_us,
        SPI_API_contract_us=spi_api_us, LCD_API_contract_us=lcd_api_us,
        page_reader_contract_us=reader_us, RPC_batches=batches,
        RPC_batches_completed=len(done_batches), RF_pages_generated=total_pages,
        RF_pages_DMA_completed=host_retired, RF_pages_consumed=retired,
        peak_host_RF_pages=peak_host, peak_reserved_FPGA_pages=peak_window,
        peak_raw_codewords_held=peak_raw, raw_codeword_storage_bytes=peak_raw*204,
        raw_PSram_slots=raw_slots, raw_PSram_slot_bytes=256,
        raw_PSram_reserved_bytes=raw_slots*256,
        maximum_RPC_batch_completion_us=max(rpclat, default=0),
        RF_pages_by_port=tx_count, status_transactions=polls,
        RPC_ready_and_ack_transactions=rpc_polls,
        RPC_status_reply_bytes=32, RPC_upstream_dummy_SCK=16,
        RPC_ready_ack_endpoint_implemented=False,
        port_occupied_us=occupancy, drain_finish_us=now, failure=failure,
        conditional_schedule_pass=failure is None and len(done_batches)==batches and retired==total_pages,
        CPU_WCET_verified=False, connected_receiver_verified=False,
        physical_IO_verified=False, receiver_adopted=False)
    if trace:
        result['transactions'] = records
    return result


def report():
    positive = [simulate(phase_us=i*BATCH_US/16) for i in range(16)]
    return dict(scope=__doc__, cases=positive,
                long_run=simulate(batches=4096),
                negative_controls=dict(slow_API=simulate(spi_api_us=40, lcd_api_us=40, batches=32),
                                       two_page_window=simulate(window=2, batches=32),
                                       old_single_batch_storage=simulate(raw_slots=204, batches=32)),
                source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(report(), indent=2)+'\n')
