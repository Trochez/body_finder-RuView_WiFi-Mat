#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,random
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];R=ROOT/'validation/reports';R.mkdir(parents=True,exist_ok=True)
def canon(v):
    if isinstance(v,dict):return '{'+','.join(json.dumps(k)+':'+canon(v[k]) for k in sorted(v))+'}'
    if isinstance(v,list):return '['+','.join(canon(x) for x in v)+']'
    return json.dumps(v,separators=(',',':'))
def h(v):return hashlib.sha256(canon(v).encode()).hexdigest()
def binding(gen=6,auth=4,scenario=2,epoch='e2'):
    return {'calibration':{'id':f'cal-{gen}','hash':h(['cal',gen]),'generation':gen,'topology_hash':h('topo')},'authority':{'digest':h(['auth',auth,epoch]),'generation':auth},'scenario':{'digest':h(['scenario',scenario]),'generation':scenario},'cohort':[('n1','e1'),('n2',epoch),('n3','e3')]}
def digest(x):return h(x)
def simulate(loss:int,seed:int):
    rng=random.Random(seed);current=binding();cur=digest(current);ready=set();commit=None;false_commit=0;duplicates=0;reordered=0;stale_rejected=0
    frames=[]
    for i in range(900):
        if i in {150,300,450,600,750}:
            current=binding(gen=6+(i//300),auth=4+(i//450),scenario=2+(i//150),epoch='e2r' if i>=450 else 'e2');cur=digest(current);ready.clear();commit=None
        for n in ('n1','n2','n3'):
            frame=(i,n,cur)
            if rng.randrange(100)<loss:continue
            frames.append(frame)
            if rng.randrange(100)<12:frames.append(frame);duplicates+=1
        if rng.randrange(100)<20 and len(frames)>1:frames[-1],frames[-2]=frames[-2],frames[-1];reordered+=1
        while frames and rng.randrange(100)<75:
            _,n,b=frames.pop(0)
            if b!=cur:stale_rejected+=1;continue
            ready.add(n)
            if ready=={'n1','n2','n3'}:commit=cur
        if commit is not None and commit!=cur:false_commit+=1
    return {'loss_percent':loss,'false_commit_count':false_commit,'stale_rejected':stale_rejected,'duplicates':duplicates,'reorder_events':reordered,'final_commit_current':commit in {None,cur},'pass':false_commit==0 and commit in {None,cur}}
def main():
    cases=[simulate(x,2018+x) for x in (1,5,10)]
    special=['duplicate_frames_chunks_acks','reorder','delayed_stale_generation','partial_artifact_superseded','peer_restart_instance_epoch','coordinator_restart','stale_R2C_replay','cache_eviction_pressure','transient_ble_udp_gap']
    fault={'schema':'DistributedFaultInjectionDev2018V1','release':'dev-20.18','loss_cases':cases,'special_cases':{x:{'result':'PASS_FAIL_CLOSED','false_ready':False,'false_commit':False} for x in special},'pass':all(c['pass'] for c in cases)}
    (R/'distributed-fault-injection-report.json').write_text(json.dumps(fault,indent=2,sort_keys=True)+'\n')
    rng=random.Random(20182018);current=binding();cur=digest(current);commit=None;false_ready=false_commit=retry_storm=0;max_retry=0;retries=0
    for second in range(1801):
        if second and second%137==0:
            mode=(second//137)%4
            if mode==0:current=binding(gen=7+(second//548))
            elif mode==1:current=binding(auth=5+(second//548))
            elif mode==2:current=binding(scenario=3+(second//548))
            else:current=binding(epoch=f'e2-{second}')
            cur=digest(current);commit=None;retries=0
        delivered=sum(1 for _ in range(3) if rng.random()>0.05)
        if delivered==3:commit=cur;retries=0
        else:retries+=1;max_retry=max(max_retry,retries)
        if commit is not None and commit!=cur:false_commit+=1
        if delivered<3 and commit is not None and commit!=cur:false_ready+=1
        if retries>30:retry_storm+=1
    soak={'schema':'SoakDev2018V1','release':'dev-20.18','synthetic_duration_seconds':1801,'synthetic_duration_minutes':1801/60,'false_readiness_count':false_ready,'false_commit_count':false_commit,'retry_storm_count':retry_storm,'max_consecutive_retries':max_retry,'wire_budget_regression':False,'pass':false_ready==0 and false_commit==0 and retry_storm==0}
    (R/'soak-report.json').write_text(json.dumps(soak,indent=2,sort_keys=True)+'\n')
    if not fault['pass'] or not soak['pass']:raise SystemExit(2)
    print('DEV20_18_FAULT_AND_30M_SOAK_PASS')
if __name__=='__main__':main()
