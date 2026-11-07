"""Same-fee permutations; model experiments, not recompiled Xtensa WCET."""
import hashlib
import itertools
import json
from pathlib import Path
from experiments.s3_joint_runtime import ROOT, run, generated


def owner_variant(order):
    if sorted(order) != ['A', 'B', 'C', 'P']:
        raise ValueError(order)
    source = generated()['joint_owner.inc']
    start = source.index(' if(!poll_rf(r,&prepare_words)||!pack_slice')
    collect_start = source.index(' uint64_t now=', start)
    port_start = source.index(' for(unsigned i=0;i<2;++i)', collect_start)
    end = source.index(' return feed(r,0,false);', port_start)
    port = source[port_start:end]
    assert port.endswith(' }\n')
    body = port[port.index('{')+1:-3]
    blocks = {
        'P': ' if(!pack_slice(r,0)||!poll_rf(r,&prepare_words))return false;\n',
        'C': ' {\n' + source[collect_start:port_start] + ' }\n',
        'A': ' { unsigned i=0;\n' + body + ' }\n',
        'B': ' { unsigned i=1;\n' + body + ' }\n',
    }
    return source[:start] + ' if(!poll_rf(r,&prepare_words))return false;\n' + ''.join(blocks[k] for k in order) + source[end:]


def main():
    folder = ROOT/'reports/s3-owner-order-estimate'
    folder.mkdir(exist_ok=True)
    source = ROOT/'reports/s3-receiver-cost-ledger/runtime.json'
    baseline = json.loads(source.read_text())
    records = []
    for profile in baseline['profiles']:
        rate, share = profile['rows'][0]['rate'], profile['rows'][0]['share']
        for order in itertools.permutations('PCAB'):
            name = ''.join(order)
            costs = profile['fixed_cost_cycles']
            cases = [(rate, share, 512, 100, 1, 0, 20000, prep, 1024) for prep in (1024,2048,3072)]
            result = run(cases, costs, owner_variant(order))
            long_cases = [tuple(list(case[:3])+[4000]+list(case[4:])) for case,row in zip(cases,result['rows']) if row['scenario_pass'] and rate==40]
            if long_cases:
                result['rows'] += run(long_cases,costs,owner_variant(order))['rows']
            result['order'] = name
            records.append(result)
            print(rate,share,name,[(r['prepare_per_iteration'],r['requested_banks'],r['banks'],r['scenario_pass']) for r in result['rows']],flush=True)
    output = {'profiles':records,'hardware_proven':False,'receiver_adopted':False,
              'assumption':'All permutations use the original owner shell instruction fee. Unrolled/reordered Xtensa code is not audited. Seven RF polls, one shared preparation budget, same per-event fees; event counts arise from execution. Each port retains reap-before-submit and collect retains clock-before-collect.',
              'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),source)}}
    (folder/'results.json').write_text(json.dumps(output,indent=2)+'\n')
    lines=['# ② 同じ費用による処理順序24通りの比較','',
           'P=core0 packing、C=collect、A=SPI2 reap/submit、B=SPI3 reap/submit。各portはreap→RF監視→submit→RF監視を維持。P/C後にもRF監視、反復先頭にもRF監視し、計7回を維持する。準備語予算は反復全体で共有。', '',
           '単価は受信費用台帳と同一。順序で変わる実発生回数を課す。ownerの制御費用は現行の190cycleを共通に置いた比較模型であり、並べ替えたXtensaバイナリの計数ではない。実装採用・実時間保証ではない。', '',
           '各条件100bankを要求し、S側で通過した条件だけ4000bankでも評価。T側の並べ替えは100bankの比較に限定し、4000bankは今回未実施。100bank以前の拒否は既に反例なので長期試験を重ねない。全24順序×3分担×3準備予算=216条件。', '',
           '|系統|準備語|100bank通過順序数/24|4000bank通過順序|最長到達bank（上限4000）|',
           '|---|---:|---:|---|---:|']
    for rate,share in ((16,8),(40,5),(40,6)):
        for prep in (1024,2048,3072):
            rows=[(p['order'],r) for p in records for r in p['rows'] if r['rate']==rate and r['share']==share and r['prepare_per_iteration']==prep]
            n=sum(r['scenario_pass'] and r['requested_banks']==100 for _,r in rows)
            passed=[order for order,r in rows if r['scenario_pass'] and r['requested_banks']==4000]
            lines.append(f"|{'T' if rate==16 else 'S'} {share}/16|{prep}|{n}|{', '.join(passed) or ('未実施' if rate==16 else 'なし')}|{max(r['banks'] for _,r in rows)}|")
    lines += ['', '順序の離散比較であり、全スケジュールの探索ではない。slice長、port処理の分割、動的優先順位、費用削減はこの比較で変えていない。有限通過も無期限成立を示さない。RF監視間隔・送信間隔・容量拒否・全費用／頻度は [results.json](results.json) に保存。正式採用0。','']
    (folder/'README.md').write_text('\n'.join(lines))

if __name__=='__main__':main()
