#!/usr/bin/env python3
import hashlib, random

CHUNK=512

def chunks(payload:bytes): return [payload[i:i+CHUNK] for i in range(0,len(payload),CHUNK)]
def digest(payload:bytes): return hashlib.sha256(payload).hexdigest()

def transfer(payload:bytes,loss:float,primary=True,fallback=True,seed=208):
    rng=random.Random(seed); cs=chunks(payload); have={}; tx=0; retrans=0
    # identical logical frames may travel over multicast primary and broadcast fallback;
    # receiver deduplicates chunk index.
    for idx,c in enumerate(cs):
        for path_enabled in (primary,fallback):
            if not path_enabled: continue
            tx+=1
            if rng.random() >= loss: have.setdefault(idx,c)
    rounds=0
    while len(have)<len(cs) and rounds<20:
        missing=[i for i in range(len(cs)) if i not in have]
        # selective NACK: only missing chunks are resent; either available path can heal.
        for idx in missing:
            delivered=False
            for path_enabled in (primary,fallback):
                if not path_enabled: continue
                tx+=1; retrans+=1
                if rng.random() >= loss:
                    delivered=True; break
            if delivered: have[idx]=cs[idx]
        rounds+=1
    rebuilt=b''.join(have[i] for i in range(len(cs))) if len(have)==len(cs) else b''
    return {'complete':rebuilt==payload and digest(rebuilt)==digest(payload),'tx':tx,'retrans':retrans,'rounds':rounds,'dedup':tx-len(have)-retrans}

def main():
    payload=(b'{"artifact":"dev20.8","data":"'+b'x'*110_000+b'"}')
    for loss in (0.01,0.05,0.15):
        r=transfer(payload,loss,True,True); assert r['complete'],(loss,r)
        assert r['rounds']<20
    # multicast black-hole: broadcast fallback alone converges.
    assert transfer(payload,0.15,False,True,209)['complete']
    # broadcast black-hole: multicast primary alone converges.
    assert transfer(payload,0.15,True,False,210)['complete']
    # both unavailable must fail closed instead of fabricating completion.
    assert not transfer(payload,0.0,False,False,211)['complete']
    # corrupt reconstructed payload fails SHA identity.
    cs=chunks(payload); bad=b''.join(cs[:-1]+[cs[-1]+b'!']); assert digest(bad)!=digest(payload)
    print('dev20.8 transport fault model PASS')

if __name__=='__main__': main()
