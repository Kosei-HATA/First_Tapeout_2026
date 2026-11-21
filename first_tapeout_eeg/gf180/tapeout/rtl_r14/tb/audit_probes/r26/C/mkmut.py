#!/usr/bin/env python3
"""Make a mutant copy of the audit copy: mkmut.py <name>. The edits are in MUTANTS below; each text must occur exactly
once. The copy is scratchpad/mut_<name> (from audit26_C_pristine)."""
import os
import shutil
import sys

SP = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(SP, "audit26_C_pristine")
R14 = "gf180/tapeout/rtl_r14"
OLD = "gf180/tapeout/rtl"

MUTANTS = {
    # the SPI slave reset by RESET_N only (not by SOFT_RESET's control reset)
    "spi_tmrst": [(f"{R14}/eeg_digital_top.sv",
                   "        .clk(MCLK), .rst_n(rst_n), .sclk(SCLK), .cs_n(CS_N), .mosi(MOSI), .miso(MISO), .miso_oe(MISO_OE),",
                   "        .clk(MCLK), .rst_n(tm_rst_n), .sclk(SCLK), .cs_n(CS_N), .mosi(MOSI), .miso(MISO), .miso_oe(MISO_OE),")],
    # a write to STATUS (0x03) taken silently (STATUS left out of the read-only list, put with the plain registers)
    "status_wr": [(f"{R14}/eeg_regs.sv",
                   "            A_ID, A_VERSION, A_CAPS, A_STATUS, A_STATE, A_FIFO_LEVEL, A_ODR_H, A_ODR_L, A_FORMAT, A_SAMPLE,",
                   "            A_ID, A_VERSION, A_CAPS, A_STATE, A_FIFO_LEVEL, A_ODR_H, A_ODR_L, A_FORMAT, A_SAMPLE,"),
                  (f"{R14}/eeg_regs.sv",
                   "            A_ERR, A_DFLAG, A_ALERT_MASK, A_ALERT_MASK_D, A_COMMAND, A_TEST_KEY, A_OFF_M_H, A_OFF_M_L, A_AFE_IBIAS,",
                   "            A_STATUS, A_ERR, A_DFLAG, A_ALERT_MASK, A_ALERT_MASK_D, A_COMMAND, A_TEST_KEY, A_OFF_M_H, A_OFF_M_L, A_AFE_IBIAS,")],
    # the sample copy kept as an unreset byte array (written at the snap, read by byte index): storage without a reset
    # outside the FIFO (RST-01, spec 7.9)
    "shadow_mem": [(f"{R14}/eeg_spi_slave.sv",
                    "    logic [47:0] shadow;\n",
                    "    logic [7:0]  shadow_b [0:5];                  // (mutant) no reset\n"),
                   (f"{R14}/eeg_spi_slave.sv",
                    """                case (k)
                    3'd0:    tx_next = shadow[47:40];
                    3'd1:    tx_next = shadow[39:32];
                    3'd2:    tx_next = shadow[31:24];
                    3'd3:    tx_next = shadow[23:16];
                    3'd4:    tx_next = shadow[15:8];
                    3'd5:    tx_next = shadow[7:0];
                    default: tx_next = crc8_48(CRC_SMP_HDR, shadow);
                endcase""",
                    """                if (k < 3'd6) tx_next = shadow_b[k];
                else          tx_next = crc8_48(CRC_SMP_HDR, {shadow_b[0], shadow_b[1], shadow_b[2], shadow_b[3],
                                                              shadow_b[4], shadow_b[5]});"""),
                   (f"{R14}/eeg_spi_slave.sv",
                    "            shadow    <= 48'h0;\n",
                    ""),
                   (f"{R14}/eeg_spi_slave.sv",
                    "                                        shadow <= smp_word;\n",
                    ""),
                   (f"{R14}/eeg_spi_slave.sv",
                    "    always_ff @(posedge clk or negedge rst_n) begin\n        if (!rst_n) begin\n            st        <= S_IDLE;",
                    """    always_ff @(posedge clk)                      // (mutant) the copy without a reset
        if (smp_snap) for (int i = 0; i < 6; i++) shadow_b[i] <= smp_word[8 * (5 - i) +: 8];
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            st        <= S_IDLE;""")],
    # a 2-word buffer of CIC outputs without a reset outside the FIFO (storage without a reset; RST-01, spec 7.9)
    "dbuf": [(f"{R14}/eeg_digital_top.sv",
              ".seq_in(seq_cnt), .data_in(cic_data),",
              ".seq_in(seq_cnt), .data_in(cic_stb ? cic_data : dbuf[seq_cnt[0]]),"),
             (f"{R14}/eeg_digital_top.sv",
              "    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (",
              """    logic [23:0] dbuf [0:1];                     // (mutant) a 2-word buffer of CIC outputs, no reset
    always_ff @(posedge MCLK) if (cic_stb) dbuf[seq_cnt[0]] <= cic_data;
    eeg_fifo #(.DEPTH(FIFO_DEPTH)) u_fifo (""")],
    # CAPS always reports the 8-deep FIFO (the register block's depth parameter not passed on)
    "caps8": [(f"{R14}/eeg_digital_top.sv",
               "    eeg_regs #(.FIFO_DEPTH(FIFO_DEPTH)) u_regs (",
               "    eeg_regs #(.FIFO_DEPTH(8)) u_regs (")],
}


def main():
    name = sys.argv[1]
    dst = os.path.join(SP, f"mut_{name}")
    if os.path.exists(dst):
        shutil.rmtree(dst)
    shutil.copytree(SRC, dst, symlinks=True)
    for f, old, new in MUTANTS[name]:
        p = os.path.join(dst, f)
        t = open(p, encoding="utf-8").read()
        if t.count(old) != 1:
            sys.exit(f"{name}: text occurs {t.count(old)} times in {f}")
        open(p, "w", encoding="utf-8").write(t.replace(old, new))
    print(dst)


if __name__ == "__main__":
    main()
