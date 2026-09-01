#!/usr/bin/env python3
import random,hashlib,json
PAYLOAD=(json.dumps({'calibration':'x'*7000},sort_keys=True)).encode();CH=420;parts=[PAYLOAD[i:i+CH] for i in range(0,len(PAYLOAD),CH)];digest=hashlib.sha256(PAYLOAD).hexdigest()
def run(loss,seed,drop_final=False,corrupt=False):
 r=random.Random(seed);have={};rounds=0
 while len(have)<len(parts) and rounds<120:
  missing=[i for i in range(len(parts)) if i not in have]
  for i in missing[:12]:
   if drop_final and rounds<2 and i==len(parts)-1:continue
   if r.random()<loss:continue
   b=parts[i]
   if corrupt and rounds==0 and i==1:b=b+b'bad'
   if hashlib.sha256(b).digest()!=hashlib.sha256(parts[i]).digest():continue
   have[i]=b
  rounds+=1
 rebuilt=b''.join(have[i] for i in range(len(parts))) if len(have)==len(parts) else b''
 return hashlib.sha256(rebuilt).hexdigest()==digest
for loss in (0,.05,.10): assert all(run(loss,s) for s in range(100))
assert run(.05,7,drop_final=True);assert run(.05,8,corrupt=True)
print(json.dumps({'schema':'dev20.13-artifact-transport-report-v1','status':'PASS','loss_levels':[0,5,10],'trials_each':100,'missing_final_chunk':'PASS','corrupt_chunk':'PASS'}))
