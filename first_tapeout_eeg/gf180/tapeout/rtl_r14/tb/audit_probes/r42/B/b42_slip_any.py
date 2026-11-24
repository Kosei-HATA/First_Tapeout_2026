import sys, importlib.util
spec = importlib.util.spec_from_file_location("regmap", sys.argv[1])
rm = importlib.util.module_from_spec(spec); spec.loader.exec_module(rm)
for key in ("CAPS", "STATE", "FIFO_LEVEL", "DFLAG", "IF_CFG"):
    hz = rm.slip_hazards(key, any_value=True)
    print(key, len(hz), [(('hdr' if v < 0 else hex(v)), hex(x)) for v, x in hz][:40])
