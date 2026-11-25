# M-A2: SPI: a write's CRC check and commit pipelined (timing closure of the CRC-8 compare): at the synchronized CS_N
# rise a complete write only arms the check; the commit (or CRC_ERR) follows one MCLK later. FRAME_ERR and the pop
# request keep their cycle.
EDITS = [
 ("rtl_r14/eeg_spi_slave.sv",
  "    logic        chk_addr;\n",
  "    logic        chk_addr;\n    logic        wr_chk;                              // a complete write: CRC check next cycle\n"),
 ("rtl_r14/eeg_spi_slave.sv",
  "            addr_err  <= 1'b0;\n        end else begin",
  "            addr_err  <= 1'b0;\n            wr_chk    <= 1'b0;\n        end else begin"),
 ("rtl_r14/eeg_spi_slave.sv",
  "            chk_addr  <= 1'b0;\n            if (cs_start) begin",
  "            chk_addr  <= 1'b0;\n            wr_chk    <= 1'b0;\n"
  "            if (wr_chk) begin                            // the registered write check: commit or CRC_ERR\n"
  "                if (crc_en && (wcrc != crc8_step(crc8_step(8'h00, hdr), wdat))) crc_err <= 1'b1;\n"
  "                else                                                            reg_we  <= 1'b1;\n"
  "            end\n"
  "            if (cs_start) begin"),
 ("rtl_r14/eeg_spi_slave.sv",
  "                    end else if (st == S_WDONE) begin\n"
  "                        if (crc_en && (wcrc != crc8_step(crc8_step(8'h00, hdr), wdat))) crc_err <= 1'b1;\n"
  "                        else                                                            reg_we  <= 1'b1;\n",
  "                    end else if (st == S_WDONE) begin\n"
  "                        wr_chk <= 1'b1;\n"),
]
