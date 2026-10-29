"""Report completion blockers; --claim-complete rejects an unsupported claim.
This checks a stored declaration, not the assistant's ability to end a turn.
"""
import argparse,json
from experiments.s3_joint_runtime import ROOT

def validate(plan):
 ids=[x['id'] for x in plan['items']]
 assert len(ids)==len(set(ids)) and ids
 for item in plan['items']:
  assert item['status'] in ('ready','in_progress','blocked','done')
  assert item['criterion'] and item['next_action']
  assert item['evidence'] and all((ROOT/p).is_file() for p in item['evidence'])
  if item['status']=='blocked':assert item.get('dependency') and item.get('blocking_evidence')
 complete=all(x['status']=='done' for x in plan['items'])
 assert plan['completion_claim_allowed']==complete
 return {'complete':complete,'ready':[x['id'] for x in plan['items'] if x['status'] in ('ready','in_progress')], 'blocked':[x['id'] for x in plan['items'] if x['status']=='blocked']}
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--claim-complete',action='store_true');a=ap.parse_args()
 result=validate(json.loads((ROOT/'reports/recovery-20261029/plan.json').read_text()))
 print(json.dumps(result,ensure_ascii=False,indent=2))
 if a.claim_complete and not result['complete']:raise SystemExit(2)
