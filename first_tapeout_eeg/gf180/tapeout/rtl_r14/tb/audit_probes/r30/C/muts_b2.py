R14 = "gf180/tapeout/rtl_r14"
REGS = f"{R14}/eeg_regs.sv"
MUTANTS = {}
# X3: the apply given priority over a write of the same cycle (a designer avoiding the X1 race): a shadow write
# committed in the acknowledge cycle of START / APPLY / APPLY_NR is silently dropped (no flag; the host's write is lost)
MUTANTS["x3_apply_drops_write"] = [(REGS,
    "            if (w_ok) begin\n                case (addr)\n                    A_OFF_M_H:      s_m[9:8] <= wdata[1:0];",
    "            if (w_ok && !apply) begin\n                case (addr)\n                    A_OFF_M_H:      s_m[9:8] <= wdata[1:0];")]
# X14b: the unlock decoded from the data alone (the address test dropped from a separate key-detect term, as round 28's
# data-only SOFT_RESET): a committed write of 0x3C to any writable register unlocks the test registers (REG-08: only a
# write of the key to TEST_KEY unlocks); writes to TEST_KEY lock and unlock as before
MUTANTS["x14b_unlock_any_addr"] = [(REGS,
    "            // command: taken by the sequencer at a tick; a new one only when none is pending (else STATE_ERR)",
    "            if (w_ok && wdata == TEST_KEY_VALUE) unlocked <= 1'b1;\n            // command: taken by the sequencer at a tick; a new one only when none is pending (else STATE_ERR)")]
