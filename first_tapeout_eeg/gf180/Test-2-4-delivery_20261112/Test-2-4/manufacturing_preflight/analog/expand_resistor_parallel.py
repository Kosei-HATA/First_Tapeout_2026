"""Analysis-only expansion of literal integer m on ppolyf_u_1k wrapper instances.
No PDK modification. Other devices untouched. Unsupported m expressions fail.
"""
import re
def expand(text):
 logical=[]
 for line in text.splitlines():
  if line.lstrip().startswith('+'):
   if not logical:raise ValueError('orphan continuation')
   logical[-1]+=' '+line.lstrip()[1:]
  else:logical.append(line)
 out=[];record=[]
 for line in logical:
  if not re.match(r'^\s*x',line,re.I) or not re.search(r'\bppolyf_u_1k\b',line,re.I):
   out.append(line);continue
  match=re.search(r'\bm\s*=\s*(\S+)',line,re.I)
  if not match:out.append(line);continue
  val=match.group(1)
  if not re.fullmatch(r'[1-9]\d*',val):raise ValueError('unsupported multiplier '+val)
  n=int(val)
  if n>4096:raise ValueError('unbounded expansion')
  base=re.sub(r'\bm\s*=\s*\S+','m=1',line,flags=re.I)
  name=base.split()[0];rest=base[len(name):]
  for k in range(n):out.append(name+'__noise_parallel_'+str(k)+rest)
  record.append({'instance':name,'multiplier':n,'generated':[name+'__noise_parallel_'+str(k) for k in range(n)]})
 return '\n'.join(out)+'\n',record
