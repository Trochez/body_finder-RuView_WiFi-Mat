#!/usr/bin/env python3
import multiprocessing as mp,queue,random,json

def node(name,rx,tx):
 state={'name':name,'scenario':None,'cal':None,'run':None,'freeze':None}
 while True:
  m=rx.get()
  if m['t']=='STOP':tx.put(state);return
  if m['t']=='SCENARIO':state['scenario']=m['digest'];tx.put(('ACK',name,m['digest']))
  elif m['t']=='CAL':state['cal']=m['id'];tx.put(('CAL_ACK',name,m['id']))
  elif m['t']=='START' and state['scenario'] and state['cal']:state['run']=m['token'];tx.put(('START_READY',name,m['token']))
  elif m['t']=='FREEZE' and state['run']==m['token']:state['freeze']=m['auth'];tx.put(('SNAPSHOT_READY',name,m['auth']))

def main():
 ctx=mp.get_context('spawn');rx=[ctx.Queue() for _ in range(3)];tx=ctx.Queue();ps=[ctx.Process(target=node,args=(f'n{i}',rx[i],tx)) for i in range(3)];[p.start() for p in ps]
 phases=[{'t':'SCENARIO','digest':'s1'},{'t':'CAL','id':'c1'},{'t':'START','token':'r1'},{'t':'FREEZE','token':'r1','auth':'a1'}]
 for m in phases:
  for q in rx:q.put(m)
  got=[tx.get(timeout=5) for _ in range(3)];assert len({x[1] for x in got})==3 and len({x[2] for x in got})==1,got
 for q in rx:q.put({'t':'STOP'})
 states=[tx.get(timeout=5) for _ in range(3)];[p.join(5) for p in ps];assert all(x['scenario']=='s1' and x['cal']=='c1' and x['run']=='r1' and x['freeze']=='a1' for x in states);print(json.dumps({'isolated_runtimes':3,'scenario_ack':3,'calibration_ack':3,'run_start_ready':3,'snapshot_ready':3,'pass':True}))
if __name__=='__main__':main()
