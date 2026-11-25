# M-C: SPI: the read header's ADDR_ERR from a registered copy of eeg_regs' address decode (one MCLK later)
EDITS = [
 ("rtl_r14/eeg_spi_slave.sv",
  "    logic        chk_addr;\n",
  "    logic        chk_addr;\n    logic        chk_q, ok_q;                         // the decode registered (timing)\n"),
 ("rtl_r14/eeg_spi_slave.sv",
  "            addr_err  <= 1'b0;\n        end else begin",
  "            addr_err  <= 1'b0;\n            chk_q     <= 1'b0;\n            ok_q      <= 1'b1;\n        end else begin"),
 ("rtl_r14/eeg_spi_slave.sv",
  "            addr_err  <= chk_addr && !reg_addr_ok;       // the read header's address, one cycle later\n",
  "            chk_q     <= chk_addr;\n            ok_q      <= reg_addr_ok;\n"
  "            addr_err  <= chk_q && !ok_q;                 // the read header's address, two cycles later\n"),
]
