import random, sys
from crc import crc8
N=72
def skip(x,k):
    hi=(x>>(N-k))<<(N-k) if k else 0
    lo=(x&((1<<(N-1-k))-1))<<1
    return hi|lo
def dup(x,k):
    hi=(x>>(N-1-k))<<(N-1-k)
    lo=(x>>1)&((1<<(N-1-k))-1)
    return hi|lo
random.seed(7)
hits={}
tot=0
for _ in range(20000):
    st=random.randrange(0x80,0xC0)
    w=[random.randrange(256) for _ in range(6)]
    if random.random()<0.5: w[0]=random.choice([0,0x08,0x20,0x28,0x40,0x48,0x60,0x68])  # empty-word-like
    chip=((st<<56)|sum(b<<(48-8*i) for i,b in enumerate(w))|crc8([0xC0]+w))<<(N-64)
    for name,hf in (("dup",dup),("skip",skip)):
        for k in range(0,9):
            hs=hf(chip,k)
            b=[(hs>>(N-8-8*i))&0xFF for i in range(8)]
            tot+=1
            if crc8([0xC0]+b[1:7])==b[7]:
                hits[(name,k)]=hits.get((name,k),0)+1
print(tot,"header-region faults;","hits",hits)
