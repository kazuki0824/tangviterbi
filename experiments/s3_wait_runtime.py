"""Hardware-loop iteration sensitivity with identical accounting and schedule fees."""
import hashlib,json
from pathlib import Path
from experiments.s3_joint_runtime import ROOT,run
from experiments.s3_owner_order_estimate import owner_variant

def main():
 p=ROOT/'reports/s3-wait-cost';source=ROOT/'reports/s3-counter-envelope/runtime.json'
 baseline=json.loads(source.read_text());profiles=[]
 for rate,share,order in [(16,8,'PCAB'),(40,5,'PCAB'),(40,5,'BCPA'),(40,6,'PCAB'),(40,6,'BCPA')]:
  base=next(q for q in baseline['profiles'] if q['order']==order and (q['rows'][0]['rate'],q['rows'][0]['share'])==(rate,share))
  for update,ready,snapshot in ((0,0,0),(16,0,0),(0,16,16),(16,16,16)):
   c=dict(base['fixed_cost_cycles']);spi_extra=(3*update*11+9)//10;tick_extra=((3*ready+6*snapshot)*11+9)//10
   for key in ('IRQ_FIRST','IRQ_START'):c[key]+=spi_extra
   for key in ('TICK0','TICK1'):c[key]+=tick_extra
   cases=[(rate,share,512,100,1,0,20000,2048,1024)]
   r=run(cases,c,owner_variant(order))
   if r['rows'][0]['scenario_pass']:r['rows']+=run([(rate,share,512,4000,1,0,20000,2048,1024)],c,owner_variant(order))['rows']
   r.update(order=order,extra_iterations={'spi_update':update,'systimer_ready':ready,'snapshot':snapshot},extra_cycles={'per_spi_start':spi_extra,'per_tick':tick_extra})
   profiles.append(r);print(rate,share,order,update,ready,snapshot,[(x['banks'],x['requested_banks']) for x in r['rows']],flush=True)
 data={'profiles':profiles,'hardware_wcet':False,'all_SoC_costs_finalized':False,'source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [Path(__file__).resolve(),source,p/'instructions.json',ROOT/'experiments/s3_owner_order_estimate.py']}}
 (p/'runtime.json').write_text(json.dumps(data,indent=2)+'\n')
 lines=['# ② ハードウェア待ちの追加反復費用','',
 '保存ELFの全分岐を反復数0/1/2/8/16で展開し、SPI UPDATEは追加1反復3命令、systimer readyは3命令、snapshot再試行は6命令と確認した。待ちなしの18/26命令は既計上で、再加算しない。snapshot再試行時にcapture全体をもう一度課すこともしない。', '',
 '発生頻度：SPI UPDATEは各転送開始に1系列、counter captureとsnapshotは各coreの通常tickに各1系列（100Hz、1tick/IRQという現模型条件）。追加時間は各開始/tickイベントの単価に加えて同じ実行のCPU台帳と時刻へ反映した。', '',
 '追加反復16回は測定値でも上限でもなく、明示した感度点。SPI追加53cycle、ready/snapshot各16回でtick追加159cycle。全0、SPIだけ16、counterだけ16、両方16の4条件を評価。メモリ遅延・window例外・追加IRQは別。', '',
 '|系統|順序|UPDATE/ready/snapshot追加回数|最長到達/要求bank|結果|RF監視最大µs|arena最大byte|', '|---|---|---|---:|---|---:|---:|']
 for q in profiles:
  x=q['rows'][-1];n=q['extra_iterations']
  lines.append(f"|{'T' if x['rate']==16 else 'S'} {x['share']}/16|{q['order']}|{n['spi_update']}/{n['systimer_ready']}/{n['snapshot']}|{x['banks']}/{x['requested_banks']}|{'有限通過' if x['scenario_pass'] else '容量超過' if x['accept_reject_reason']==2 else '準備/期限拒否'}|{x['max_rf_poll_gap']/240:.3f}|{x['peak_arena_bytes']}|")
 lines+=['', 'SDKに反復回数上限はなく、これで実時間上限は確定しない。反復回数の不明と1反復費用の不明を分離した。追加費用で到達bankが増える場合もあるが、処理位相が変わるためであり、性能改善とは認定しない。', '',
 '[命令式の30条件検算](instructions.json)、[イベント費用・回数・期限](runtime.json)。再現：`python -m ci.s3_wait_cost_audit --toolchain ../toolchain/xtensa-esp-elf`、`python -m experiments.s3_wait_runtime`。','']
 (p/'README.md').write_text('\n'.join(lines))
if __name__=='__main__':main()
