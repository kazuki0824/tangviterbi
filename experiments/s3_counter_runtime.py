"""Re-evaluate all owner orders with the long-counter complete envelope."""
import hashlib,itertools,json
from pathlib import Path
from experiments.s3_joint_runtime import ROOT,run
from experiments.s3_owner_order_estimate import owner_variant

def main():
 p=ROOT/'reports/s3-counter-envelope'
 source=ROOT/'reports/s3-receiver-cost-ledger/runtime.json'
 audit=json.loads((p/'instructions.json').read_text())
 sdk=json.loads((ROOT/'reports/s3-sdk-cost-ledger/results.json').read_text())
 profiles=[]
 for baseline in json.loads(source.read_text())['profiles']:
  rate,share=baseline['rows'][0]['rate'],baseline['rows'][0]['share']
  c=dict(baseline['fixed_cost_cycles']);desc='9' if rate==16 else '5'
  c['REAP_DONE']=((sdk['roots'][desc]['reap_done']['inclusive_instructions']+audit['extra_complete_instructions'])*11+9)//10
  for order in itertools.permutations('PCAB'):
   cases=[(rate,share,512,100,1,0,20000,prep,1024) for prep in (1024,2048,3072)]
   r=run(cases,c,owner_variant(order));r['order']=''.join(order)
   long=[(rate,share,512,4000,1,0,20000,x['prepare_per_iteration'],1024) for x in r['rows'] if x['scenario_pass'] and (rate==40 or r['order']=='PCAB')]
   if long:r['rows']+=run(long,c,owner_variant(order))['rows']
   profiles.append(r)
   print(rate,share,r['order'],[(x['prepare_per_iteration'],x['requested_banks'],x['banks'],x['scenario_pass']) for x in r['rows']],flush=True)
 data={'profiles':profiles,'hardware_proven':False,'all_SoC_costs_finalized':False,'receiver_adopted':False,
       'fee_change':{'REAP_DONE_old':baseline['fixed_cost_cycles']['REAP_DONE'],'REAP_DONE_new':c['REAP_DONE'],'reason':'replace equal-high-word complete path144 with all-branch envelope153; do not add both'},
       'source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),ROOT/'experiments/s3_owner_order_estimate.py',source,p/'instructions.json',ROOT/'reports/s3-sdk-cost-ledger/results.json']}}
 (p/'runtime.json').write_text(json.dumps(data,indent=2)+'\n')
 lines=['# ② 64bitカウンタ比較・桁上がりの費用監査','',
 '保存S ELFのtake/completeを、上位32bit一致という分岐制限を外して監査。take成功包絡55命令、empty30命令は不変。completeは8lease退役を上限に全分岐を展開し、従来144から153命令の包絡へ変更した。最後に不要なslot確認をする実現不能経路も許す保守的包絡で、実測増加9命令の主張ではない。', '',
 '上限8回の根拠は8leaseで各退役時に別slotをFREE化すること。64bit全体のオーバーフローは除外し、下位32bit桁上がりと上位word不一致は許す。実Cの全完了順序を、8種類の開始番号・1〜全leaseで検算。S16KiBは369864例、T32KiBは264例。順序違いの完了、重複完了拒否、prefixだけの退役、payload位置を確認した。実C機能検算とXtensa命令包絡は別々の根拠である。', '',
 'REAP_DONEを469→479cycleへ置換し、同じ費用をCPU台帳と時刻に一度だけ課した。24順序×3分担×3準備予算を100bank評価し、Sで通過した条件とT現行順序は4000bankでも確認。slice512、stall0%、その他の費用は旧台帳と同一。owner並べ替え後の制御命令費用は190cycleという同一模型のまま。', '',
 '|系統|準備語|100bank通過順序/24|4000bank通過/実施|最長到達bank|', '|---|---:|---:|---:|---:|']
 for rate,share in ((16,8),(40,5),(40,6)):
  for prep in (1024,2048,3072):
   rows=[x for q in profiles for x in q['rows'] if (x['rate'],x['share'],x['prepare_per_iteration'])==(rate,share,prep)]
   short=[x for x in rows if x['requested_banks']==100];long=[x for x in rows if x['requested_banks']==4000]
   lines.append(f"|{'T' if rate==16 else 'S'} {share}/16|{prep}|{sum(x['scenario_pass'] for x in short)}|{sum(x['scenario_pass'] for x in long)}/{len(long)}|{max(x['banks'] for x in rows)}|")
 lines+=['','残るwindow例外・追加lock/ハード待ち・メモリ競合・アプリ差分を解消したわけではない。全SoC計上完了・正式採用とは認定しない。結果は [runtime.json](runtime.json)、命令根拠は [instructions.json](instructions.json)。','',
 '再現：`python -m ci.s3_counter_envelope --toolchain ../toolchain/xtensa-esp-elf`、`python -m unittest tests.test_s3_counter_envelope`、`python -m experiments.s3_counter_runtime`。','']
 (p/'README.md').write_text('\n'.join(lines))
if __name__=='__main__':main()
