SEQ_NAMES = [s[0] for s in F.SEQ_STATES]
SPI_NAMES = [s[0] for s in F.SPI_STATES]

def seq_sig():
    out = {}
    timed = {x[0] for x in F.SEQ_STATES if x[4]}
    for s in SEQ_NAMES:
        cases = F.seq_tick_cases(s, timed) if s != "RESET" else []
        cases = cases + [["RST"], ["RST", "OUT"], ["OUT"], ["REL"]] + [[c] for c in F.SEQ_COMMANDS]
        for present in cases:
            if not all(F.seq_possible(s, e) for e in present):
                continue
            for vals in itertools.product((0, 1), repeat=len(F.SEQ_CONDS)):
                env = dict(zip(F.SEQ_CONDS, vals))
                try:
                    nxt, acts = F.seq_tick(s, list(present), env)
                except Exception as ex:
                    nxt, acts = "EXC", [repr(ex)]
                out[(s, tuple(present), vals)] = (nxt, tuple(sorted(acts)))
    return out

def spi_sig():
    out = {}
    for kind, crc_en, env, nbytes, extra in F.spi_frame_cases():
        tr = []
        try:
            r = F.spi_walk(nbytes, extra, env, trace=tr)
        except Exception as ex:
            r = ("EXC", repr(ex))
        key = (kind, crc_en, tuple(sorted(env.items())), nbytes, extra)
        out[key] = (None if r is None else r[1], tuple((e, tuple(sorted(a))) for e, a in tr))
    return out

