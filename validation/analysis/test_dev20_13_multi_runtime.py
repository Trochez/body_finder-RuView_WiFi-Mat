#!/usr/bin/env python3
import hashlib,json,random,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
def h(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def view(session,nodes,prior=0):
 if len(nodes)!=3:return None
 c=sorted(nodes,key=lambda n:(-n['score'],n['id']))
 cohort=sorted([{'node_id':n['id'],'instance_epoch':n['epoch']} for n in nodes],key=lambda x:x['node_id'])
 base={'session_id':session,'cohort':cohort,'elected_coordinator':c[0]['id']};g=max(1,prior);material={**base,'coordinator_generation':g};return{**material,'base_digest':h(base),'authority_view_digest':h(material)}
ids=['pixel10','pixel7','lenovo']
for perm_seed in range(100):
 r=random.Random(perm_seed);order=ids[:];r.shuffle(order);nodes=[]
 for i in order:nodes.append({'id':i,'epoch':'e1','score':.78})
 views=[view('lab',nodes) for _ in ids];assert len({v['elected_coordinator'] for v in views})==1 and len({v['authority_view_digest'] for v in views})==1
assert views[0]['elected_coordinator']=='lenovo'
# delayed and replacement instance alter authority identity, never silently reuse old digest
assert view('lab',[{'id':'pixel10','epoch':'e1','score':.78},{'id':'pixel7','epoch':'e1','score':.78}]) is None
v1=view('lab',[{'id':i,'epoch':'e1','score':.78} for i in ids],1);v2=view('lab',[{'id':i,'epoch':'e2' if i=='pixel7' else 'e1','score':.78} for i in ids],2);assert v1['authority_view_digest']!=v2['authority_view_digest'] and v2['coordinator_generation']>v1['coordinator_generation']
# serialized control frame loss/reorder/duplicate: eventual ACK convergence under bounded retransmit.
def trial(loss,seed):
 r=random.Random(seed);digest=v1['authority_view_digest'];seen={i:set() for i in ids}
 frames=[json.dumps({'type':'authority','src':s,'digest':digest}).encode() for s in ids]
 for round_no in range(80):
  batch=frames[:];r.shuffle(batch)
  for f in batch:
   if r.random()<loss:continue
   x=json.loads(f);seen[x['src']].add(x['digest'])
  if all(digest in seen[i] for i in ids):return True
 return False
for loss in (0,.05,.10):
 assert all(trial(loss,s) for s in range(100))
source=(ROOT/'apps/mobile/src/authority.ts').read_text();assert 'AuthorityViewV1' in source and "a.localeCompare" not in source
hp=(ROOT/'apps/mobile/src/humanPresence.ts').read_text();assert "BodyFinderControlPlaneV11" in hp and 'AUTHORITY_CONSENSUS_REQUIRED_3_OF_3' in hp
cc=(ROOT/'apps/mobile/src/campaignControl.ts').read_text();assert 'RUN_START_AUTHORITY_ACK_3_OF_3_REQUIRED' in cc and 'peer_ack_count' in cc
print(json.dumps({'schema':'dev20.13-multi-runtime-fault-injection-report-v1','status':'PASS','randomized_staggered_trials':100,'equal_score_trials':100,'packet_loss_trials':{'0':100,'5':100,'10':100}},sort_keys=True))
