import json, os, sys
import numpy as np, pandas as pd
d = sys.argv[1]
meta = json.load(open(os.path.join(d, "meta.json")))
keep = [0, 2 * meta["vectors"].index("qo") + 1]
x = pd.read_csv(os.path.join(d, "tr.csv"), sep=r"\s+", header=None, engine="c", usecols=keep)[keep].to_numpy()
t, qo = x[:, 0], x[:, 1]
t_rel = meta["afe_rst_again"][1]
TCH = 1 / 128e3
s = np.arange(0.0, 13.8e-3, 0.05e-3)
m = (np.interp(t_rel + s + 8 * TCH, t, qo) - np.interp(t_rel + s, t, qo)) / (8 * TCH)   # 8-period means from s
i = np.nonzero((m[:-1] > 0) & (m[1:] <= 0))[0]
print("8-period means change sign (+ to -) at", [f"{s[k]*1e3:.2f} ms (+{(s[k]+8*TCH/2)*1e3:.2f} centre)" for k in i])
print("max 8-period mean", f"{m.max()*1e3:+.1f} mV at {s[m.argmax()]*1e3:.2f} ms;", "last", f"{m[-1]*1e3:+.1f} mV")
