"""Reproducible finite architecture and transport screening. NOT WCET/STA.
All rates decimal MB/s; native RF preserved. No quality-lowering transport variant.
"""
import json,math,itertools,csv,sys,gzip,argparse,copy,io
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output',type=Path,default=ROOT/'build/s3-partition-audit')
args=parser.parse_args()
R=args.output
R.mkdir(parents=True,exist_ok=True)
fixture=json.loads(gzip.decompress((ROOT/'reports/s3-partition-audit/inputs.json.gz').read_bytes()))
import s3_rs_offload_budget as rs
from s3_sct_schedule import service,terrestrial
from s3_peripheral_resources import pin_count,constraints
P=4096; rate=28.86e6*2/(203*8); interval=204/rate*1e6
inputs=copy.deepcopy(fixture['receiver_inputs'])
ports=inputs['ports']
# Additional slower SPI profiles and documented 4-bit eMMC DDR40 alternative.
for ctl in (2,3):
 for width in (1,2):
  ports.append(dict(name=f'SPI{ctl}_{"Single" if width==1 else "Dual"}80',kind='half',capacity_Bps=80e6*width/8,pin_lower_bound=4,exclusive_group=f'SPI{ctl}'))
ports.append(dict(name='eMMC4_DDR40',kind='half',capacity_Bps=40e6,pin_lower_bound=6,exclusive_group='SDHOST'))
for p in ports:
 if p['name']=='SPI3_Quad80':p['exclusive_group']='SPI3'
 if p['name']=='SDIO8_40':p['name']='eMMC8_SDR40'

def cap(p,gap=0):
 n=p['name']; c=p['capacity_Bps']/1e6
 if 'Octal' in n:return 3*P/service(3)
 if n.startswith('SPI'):
  w=round(c/10);return P/service(1,lanes=w,segment_us=0)
 if n.startswith(('SDIO','eMMC')):
  # Conservative per-4KiB command/response plus nine blocks' CRC allowance;
  # native SDR/DDR data capacity. Protocol not implemented as an FPGA endpoint.
  return P/((P+16)/c+(96+18*9)/40+20)
 return P/((P+16)/c+(gap if n.startswith(('LCD','CAM')) else 0))

sets=[]
for k in range(1,len(ports)+1):
 for ps in itertools.combinations(ports,k):
  groups=[p['exclusive_group'] for p in ps if p['exclusive_group']]
  if len(set(groups))!=len(groups):continue
  pins=pin_count(ps)
  if pins+3>30 or pins+6>35:continue
  if not constraints(ps)['gdma']['selected_driver_capacity_pass']:continue
  sets.append(ps)

def routes(d,u,gap=0):
 out=[]
 for ps in sets:
  cs=[cap(p,gap) for p in ps]
  sums={k:sum(c for p,c in zip(ps,cs) if p['kind']==k) for k in ('half','down','up')}
  h,cd,cu=(sums[k] for k in ('half','down','up'))
  if d>cd+h+1e-9 or u>cu+h+1e-9 or d+u>cd+cu+h+1e-9:continue
  peak=max(d/(cd+h) if d else 0,u/(cu+h) if u else 0,(d+u)/(cd+cu+h))
  # One feasible minimum-peak allocation; no claim it is the only allocation.
  dedicated_d=min(d,cd*peak);dedicated_u=min(u,cu*peak)
  hd=d-dedicated_d;hu=u-dedicated_u
  links=[]
  for p,c in zip(ps,cs):
   if p['kind']=='half':down=hd*c/h if h else 0;up=hu*c/h if h else 0
   elif p['kind']=='down':down=dedicated_d*c/cd if cd else 0;up=0
   else:down=0;up=dedicated_u*c/cu if cu else 0
   load=down+up
   links.append(dict(name=p['name'],capacity_MBps=c,down_MBps=down,up_MBps=up,
                     spare_MBps=c-load,spare_percent=100*(c-load)/c,
                     additional_gap_us=P/load-P/c if load else None))
  out.append(dict(ports=[p['name'] for p in ps],peak_utilization=peak,
                  GPIO_with_control=pin_count(ps)+3,
                  FPGA_header_pins_with_TS=pin_count(ps)+6,
                  peripheral_constraints=constraints(ps),
                  links=links,endpoint_implemented=False,WCET_verified=False))
 names=[set(x['ports']) for x in out]
 for x,n in zip(out,names):x['minimal']=not any(q<n for q in names)
 return out

base=fixture['assignments']
base=[r for r in base if r['SoC']=='S3']
records=[]
for r in base:
 st=r['standard']; own=r['owners'];flows=json.loads(json.dumps(r['crossings']))
 for f in flows:
  if 'after' not in f['format'] and st=='T' and f['source']=='sync' and f['target']=='FFT':
   f['MBps']=8192*4/1039.5;f['format']='8192 complex Q15 after hardware GI removal'
  if st=='S' and f['format']=='RS204 codewords':f['MBps']=rate*204/1e6
  if st=='S' and f['format']=='coded-frame byte stream':f['MBps']=28.86*2/8
  if f['source']=='RF':f['format']='native I10/Q10 lossless20; 5 B per 2 samples'
 d=sum(f['MBps'] for f in flows if f['direction']=='SoC→FPGA')
 u=sum(f['MBps'] for f in flows if f['direction']=='FPGA→SoC')
 # Legacy selected stage profiles, corrected complete RS and all missing stage costs.
 cpu=[]
 for high in (0,1):
  if own['FIR']=='FPGA':total=(153.375+32*high if st=='T' else 368.4375+80*high)
  else:total=(36.54166666666667+20.833333333333334 if st=='T' else 76.35416666666667+52.083333333333336)
  for node,v in r['stage_CPU_models'].items():
   if node=='TS':continue
   if node=='RS':cost=22060*(rate if st=='S' else 2.904337492572787e6/188)/1e6
   elif node=='frame_deinterleave':cost=(14 if not high else 20)*rate*204/1e6
   else:cost=v['known_model_Mcycles_per_s'][high]
   total+=cost
  if own['sync']=='SoC':total+=(16 if high else 8)*(8192/1008 if st=='T' else 28.86)
  if st=='T' and own['FFT']=='SoC':total+=(93583.45358345358 if high else 46791.72679172679)/1000
  nonraw=sum(f['MBps'] for f in flows if f['source']!='RF')
  total+=nonraw*(2 if high else 1)+(d+u)*200/P
  cpu.append(total)
 resources=r['FPGA_selected_stage_budget']
 records.append(dict(id=r['id'],standard=st,owners=own,flows=flows,
  required_down_MBps=d,required_up_MBps=u,CPU_low_high_Mcycles_s=cpu,
  CPU_low_high_percent=[x/480*100 for x in cpu],
  stage_only_resources=resources,resource_basis='Inherited selected kernels; incomplete logic/FF and I/O; NOT whole design occupancy',
  legacy_exclusions=r['stage1_reasons'],
  CPU_average_model_screen_pass=cpu[0]<=480 and not any('ARITHMETIC' in x for x in r['stage1_reasons']),
  all_deadlines_verified=False,whole_FPGA_fit_verified=False,adopted=False))

# Cache identical rate pairs. Only CPU-low profile passing rows reach transport assignment.
cache={}
for r in records:
 if not r['CPU_average_model_screen_pass']:
  r['route_catalog']=None;continue
 key=f"{r['required_down_MBps']:.9f}_{r['required_up_MBps']:.9f}"
 if key not in cache:cache[key]={'gap0':routes(r['required_down_MBps'],r['required_up_MBps']),
                              'gap8':routes(r['required_down_MBps'],r['required_up_MBps'],8)}
 r['route_catalog']=key

special={}
def message_time(p,n,gap):
 name=p['name']
 if 'Octal' in name:return service(n)
 if name.startswith('SPI'):return n*service(1,lanes=round(p['capacity_Bps']/10e6),segment_us=0)
 return n*P/cap(p,gap)

def rpc_routes(profile,counts,gap):
 """Enumerate every unsplit message-to-port assignment; RF can stripe.
 Report exact per-message transaction overhead, plus RF residual capacity.
 No CPU release/same-batch deadline proof is implied.
 """
 out=[]
 for ps in sets:
  choices=[[i for i,p in enumerate(ps) if p['kind'] in ('half','down' if dr=='S3_to_FPGA' else 'up')]
           for _,_,dr in profile]
  if any(not c for c in choices):continue
  winners=[]
  for assignment in itertools.product(*choices):
   used=[0.]*len(ps)
   for i,n in zip(assignment,counts):used[i]+=message_time(ps[i],n,gap)/interval
   if max(used)>1:continue
   remaining=[cap(p,gap)*(1-u) if p['kind'] in ('half','down') else 0 for p,u in zip(ps,used)]
   capacity=sum(remaining)
   if capacity<100:continue
   # Every port used for RPC or RF; no idle input-only supersets.
   if any(p['kind']=='up' and u==0 for p,u in zip(ps,used)):continue
   winners.append(dict(message_ports=[ps[i]['name'] for i in assignment],RPC_time_fractions=used,
                  RF_capacity_MBps=capacity,RF_margin_MBps=capacity-100,
                  RF_allocation_MBps=[c*100/capacity for c in remaining],
                  port_spare_MBps=[cap(p,gap)*(1-u)-r*100/capacity for p,u,r in zip(ps,used,remaining)]))
  if winners:out.append(dict(ports=[p['name'] for p in ps],GPIO_with_control=pin_count(ps)+3,
      peripheral_constraints=constraints(ps),
      assignments=winners,maximum_RF_margin_MBps=max(w['RF_margin_MBps'] for w in winners),
      minimum_RF_margin_MBps=min(w['RF_margin_MBps'] for w in winners),same_batch_deadlines_verified=False))
 names=[set(x['ports']) for x in out]
 for x,n in zip(out,names):x['minimal']=not any(q<n for q in names)
 return out

for name,profile in rs.PROFILES.items():
 pg=[math.ceil(204/((P-16)//s)) for _,s,_ in profile]
 dd=sum(n*P/interval for (_,_,dr),n in zip(profile,pg) if dr=='S3_to_FPGA')
 uu=sum(n*P/interval for (_,_,dr),n in zip(profile,pg) if dr=='FPGA_to_S3')
 special[name]=dict(records=[dict(name=n,bytes=s,direction=dr,pages=k) for (n,s,dr),k in zip(profile,pg)],
  padded_down_MBps=100+dd,padded_up_MBps=uu,CPU_WCET_cycles=None,whole_FPGA_resources=None,
  communication_only_gap0=rpc_routes(profile,pg,0),communication_only_gap8=rpc_routes(profile,pg,8),adopted=False)
exact=rs.report()
(R/'exact-rs.json').write_text(json.dumps(exact,indent=2)+'\n')
report=dict(scope='256 T + 64 S whole-stage assignments, 4 RS subpartitions, 18 explicit peripheral profiles. No universal exhaustive microarchitecture claim.',
 capacities=inputs['capacity'],profiles=[{**p,'effective_gap0_MBps':cap(p),'effective_gap8_MBps':cap(p,8)} for p in ports],
 rates=dict(T_raw_MBps=40,S_raw_MBps=100,T_FFT_each_direction_MBps=8192*4/1039.5,
            RS_codewords_s=rate,RS_deadline_us=1e6/rate,RS_batch_us=interval,
            S_RF_CPU_model_low_high_Mcycles=[368.4375+100*200/P,448.4375+100*200/P],
            S_remaining_aggregate_cycles_per_CW=[(480e6-(368.4375+100*200/P)*1e6)/rate,(480e6-(448.4375+100*200/P)*1e6)/rate]),
 definitions=dict(down='S3 to FPGA',up='FPGA to S3',SPI='80MHz master,20us API; octal3page .25us segment; others onepage',
                  parallel='4096B+16B framing; 0 or 8us gap scenarios, not measured',
                  SD='40MHz host,20us gap; 96+18*9 clocks overhead; FPGA card endpoint unimplemented',
                  pins='Same-controller full-duplex I2S may share BCLK/WS with matching clock/slots; +3 S3 control <=30, +6 FPGA control/TS <=35; counts only, no pin/electrical proof',
                  GDMA='5 TX/RX pairs; SPI reserves whole pair; LCD TX, CAM RX and each I2S direction need a channel; SDMMC separate DMA; no memory contention proof',
                  resource='All inherited partial resource numbers are labelled incomplete; no new P&R performed'),
 assignments=records,route_catalogs=cache,RS_subpartitions=special,receiver_adopted=False)
report['provenance']=fixture['provenance']
report['performance_stage_completed']=False
report['complete_estimate']=False
report['all_receiver_implemented']=False
report['safe_to_flash']=False
report['CPU_WCET_verified']=False
report['whole_FPGA_resources_verified']=False
report['proposed_validation_order']=['T target SIMD FFT, separate from the failed scalar O3 object','S resource redesign, separate from the failed Forney mapped netlist']
report['selected_implementation_observations']={
 'T_scalar_FFT_O3':dict(ideal_two_core_us_lower_bound=3882.6666666666665,
  period_us=1039.5,selected_object_pass=False,evidence='reports/s3-fft-target-bound/results.json'),
 'S_BM_Omega_Forney_FPGA_partial':dict(minimum_required_logic_sites=9426,available_logic_sites=8640,
  selected_mapped_netlist_pass=False,evidence='reports/s3-rs-forney-evidence/results.json')}
report['validation_order_is_feasibility_recommendation']=False
for row in records:
 row['performance_pass']=None
 row['communication_assignment_role']='Exploratory necessary condition; performance gate remains open'
 row['whole_FPGA_resources']=None
 row['CPU_WCET_cycles']=None
encoded=(json.dumps(report,ensure_ascii=False,sort_keys=True,separators=(',',':'))+'\n').encode()
(R/'estimate.json.gz').write_bytes(gzip.compress(encoded,mtime=0))
summary={k:v for k,v in report.items() if k not in ('assignments','route_catalogs','RS_subpartitions')}
summary['whole_stage_assignments']=len(records)
summary['CPU_average_only_screen_pass_count']=sum(x['CPU_average_model_screen_pass'] for x in records)
summary['pin_count_legal_subsets']=len(sets)
summary['RS_route_counts']={n:{g:{'sets':len(v['communication_only_'+g]),'message_assignments':sum(len(x['assignments']) for x in v['communication_only_'+g])} for g in ('gap0','gap8')} for n,v in special.items()}
(R/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
csv_output=io.StringIO(newline='')
writer=csv.writer(csv_output)
writer.writerow(['partition','parallel_gap_us','port_set','minimal_set','message_ports_in_order',
 'RF_capacity_MBps','RF_margin_MBps','RPC_port_time_fractions','RF_port_allocation_MBps','per_port_spare_MBps'])
for name,profile in special.items():
 for gap in (0,8):
  for row in profile[f'communication_only_gap{gap}']:
   for assignment in row['assignments']:
    writer.writerow([name,gap,'+'.join(row['ports']),row['minimal'],'+'.join(assignment['message_ports']),
     assignment['RF_capacity_MBps'],assignment['RF_margin_MBps'],json.dumps(assignment['RPC_time_fractions']),
     json.dumps(assignment['RF_allocation_MBps']),json.dumps(assignment['port_spare_MBps'])])
(R/'message-assignments.csv.gz').write_bytes(gzip.compress(csv_output.getvalue().encode(),mtime=0))
print(json.dumps({'ports':len(ports),'pin_legal_subsets':len(sets),'CPU_average_only_rows':sum(r['CPU_average_model_screen_pass'] for r in records),
                 'unique_rate_catalogs':len(cache),'rates':report['rates'],
                 'special_routes':{n:{k:len(v[k]) for k in ('communication_only_gap0','communication_only_gap8')} for n,v in special.items()}},indent=2))
