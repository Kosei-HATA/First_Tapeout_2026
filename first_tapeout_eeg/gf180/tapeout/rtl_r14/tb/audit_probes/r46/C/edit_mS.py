# M-S: SPI: the sample read's copy of the FIFO head (shadow and the FIFO's smp_snap) taken one MCLK after the header
# byte completes (the header decoded in a registered stage first)
EDITS = [
 ("rtl_r14/eeg_spi_slave.sv",
  "    assign smp_snap = !cs_start && !cs_end && sclk_rise && (st == S_HDR) && (bit_cnt == 3'd7) && rx_byte[7] &&\n"
  "                      (rx_byte[6:0] == A_SAMPLE);\n",
  "    logic snap_now, snap_d;                          // the header decoded, then the copy one MCLK later\n"
  "    assign snap_now = !cs_start && !cs_end && sclk_rise && (st == S_HDR) && (bit_cnt == 3'd7) && rx_byte[7] &&\n"
  "                      (rx_byte[6:0] == A_SAMPLE);\n"
  "    assign smp_snap = snap_d;\n"),
 ("rtl_r14/eeg_spi_slave.sv",
  "            addr_err  <= 1'b0;\n        end else begin",
  "            addr_err  <= 1'b0;\n            snap_d    <= 1'b0;\n        end else begin\n"
  "            snap_d    <= snap_now;\n"
  "            if (snap_d) shadow <= smp_word;"),
 ("rtl_r14/eeg_spi_slave.sv",
  "                                        shadow <= smp_word;\n",
  ""),
]
