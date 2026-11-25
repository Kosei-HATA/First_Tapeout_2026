# M-A: SPI: the CS_N-rise actions (commit, FRAME_ERR, CRC_ERR, pop request) taken from the synchronized rise registered
# once more (one MCLK later): a designer's pipeline stage after the edge detector
EDITS = [
 ("rtl_r14/eeg_spi_slave.sv",
  "    assign miso_oe   = ~cs_n & cs_act;\n",
  "    assign miso_oe   = ~cs_n & cs_act;\n"
  "    logic cs_end_d;                                  // the synchronized CS_N rise, registered once more\n"
  "    always_ff @(posedge clk or negedge rst_n) begin\n"
  "        if (!rst_n) cs_end_d <= 1'b0;\n"
  "        else        cs_end_d <= cs_end;\n"
  "    end\n"),
 ("rtl_r14/eeg_spi_slave.sv",
  "            end else if (cs_end) begin\n                if (st != S_IDLE) begin",
  "            end else if (cs_end_d) begin\n                if (st != S_IDLE) begin"),
]
