// spi_bfm_r14.svh - SPI mode-0 master for the r14 protocol (gf180/tapeout/rtl/spec, documentation
// gf180_digital_control_spec_20261119.md section 3), with the timing monitors of rtl/tb/spi_bfm.svh.
//
// Included inside a testbench module that declares: logic SCLK, CS_N, MOSI; wire MISO, MISO_OE; logic MCLK;
// localparam real TMCLK. Every transfer checks that MISO's first byte carries STATUS's fixed bits (bit 7 = 1,
// bit 6 = 0) and keeps it in spi_status.
//
// Tasks: spi_xfer(nbytes, extra_bits) raw; r14_write(addr, val); r14_read(addr, val); r14_cmd(code);
//        r14_sample(sstat, seq, data, crc_ok) (8 bytes); bfm_crc_en mirrors IF_CFG.CRC_EN.
// SCLK's high and low times are set apart (spi_high, spi_low); MISO and MISO_OE reach the master through the pad
// delay SPI_TPAD (spec 3.1: about 15 ns), so the specification's minimum low time is checked with it. A write's MISO
// must be 0x00 after the header, also at the CRC position (a write turned into a read by a flipped R/W bit returns
// data and a nonzero CRC).

logic [7:0] spi_tx [0:143];         // up to a burst of the whole map and its wrap (header + 136 bytes)
logic [7:0] spi_rx [0:143];
real        spi_high  = 250.0;      // SCLK high [ns] (>= 4 MCLK = 122 ns)
real        spi_low   = 250.0;      // SCLK low [ns] (>= 5 MCLK = 153 ns); 2 MHz at most
localparam real SPI_TPAD = 15.0;    // MISO / MISO_OE pad delay [ns]
real        spi_tcss  = 300.0;      // CS_N fall -> first SCLK rise [ns] (>= 5 MCLK = 153 ns)
real        spi_tcsh  = 200.0;      // last SCLK fall -> CS_N rise [ns]
real        spi_tidle = 600.0;      // CS_N high after a transfer [ns]
integer     spi_errors = 0;
integer     spi_xfers = 0;
logic [7:0] spi_status;
bit         bfm_crc_en = 1'b0;
real        spi_miso_lat_max = 0.0;
real        spi_oe_lat_max = 0.0;

wire        #(SPI_TPAD) miso_pin = MISO;
wire        #(SPI_TPAD) oe_pin   = MISO_OE;
wire        miso_pad = oe_pin ? miso_pin : 1'bz;

task automatic spi_err(input string msg);
    spi_errors = spi_errors + 1;
    if (spi_errors <= 20) $display("SPI ERROR @%0t: %s", $time, msg);
endtask

function automatic logic spi_bit(input integer n, input integer nbytes);
    if (n < 8 * nbytes) return spi_tx[n / 8][7 - (n % 8)];
    else                return 1'b0;
endfunction

function automatic logic [7:0] tb_crc8_update(input logic [7:0] crc, input logic [7:0] data);
    logic [7:0] c;
    c = crc ^ data;
    for (int i = 0; i < 8; i++) c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
    return c;
endfunction

task automatic spi_xfer(input integer nbytes, input integer extra_bits);
    integer total;
    total = 8 * nbytes + extra_bits;
    CS_N = 1'b0;
    MOSI = spi_bit(0, nbytes);
    #(spi_tcss);
    for (int n = 0; n < total; n++) begin
        SCLK = 1'b1;
        if (n < 8 * nbytes) begin
            spi_rx[n / 8][7 - (n % 8)] = miso_pad;
            if (miso_pad === 1'bz || miso_pad === 1'bx) spi_err("MISO not driven at SCLK rising edge");
        end
        #(spi_high);
        SCLK = 1'b0;
        MOSI = (n + 1 < total) ? spi_bit(n + 1, nbytes) : 1'b0;
        if (n + 1 < total) #(spi_low);
    end
    #(spi_tcsh);
    CS_N = 1'b1;
    #(spi_tidle);
    spi_xfers = spi_xfers + 1;
    if (total >= 8) begin
        spi_status = spi_rx[0];
        if (spi_rx[0][7:6] !== 2'b10) spi_err($sformatf("first MISO byte 0x%02h without STATUS's fixed bits", spi_rx[0]));
    end
endtask

task automatic r14_write(input logic [6:0] addr, input logic [7:0] val);
    spi_tx[0] = {1'b0, addr};
    spi_tx[1] = val;
    spi_tx[2] = tb_crc8_update(tb_crc8_update(8'h00, spi_tx[0]), val);
    spi_xfer(bfm_crc_en ? 3 : 2, 0);
    if (spi_rx[1] !== 8'h00) spi_err("write: MISO data byte not 0x00");
    if (bfm_crc_en && spi_rx[2] !== 8'h00) spi_err("write: MISO byte at the CRC position not 0x00");
endtask

task automatic r14_read(input logic [6:0] addr, output logic [7:0] val);
    logic [7:0] c;
    spi_tx[0] = {1'b1, addr};
    spi_tx[1] = 8'h00;
    spi_tx[2] = 8'h00;
    spi_xfer(bfm_crc_en ? 3 : 2, 0);
    val = spi_rx[1];
    if (bfm_crc_en) begin
        c = tb_crc8_update(tb_crc8_update(8'h00, spi_tx[0]), val);
        if (spi_rx[2] !== c) spi_err($sformatf("read 0x%02h: CRC 0x%02h, expected 0x%02h", addr, spi_rx[2], c));
    end
endtask

task automatic r14_cmd(input logic [7:0] code);
    r14_write(7'h10, code);
endtask

task automatic r14_sample(output logic [7:0] sstat, output logic [15:0] seq, output logic [23:0] data,
                          output bit crc_ok);
    logic [7:0] crc;
    spi_tx[0] = 8'hC0;
    for (int i = 1; i < 8; i++) spi_tx[i] = 8'h00;
    spi_xfer(8, 0);
    sstat = spi_rx[1];
    seq   = {spi_rx[2], spi_rx[3]};
    data  = {spi_rx[4], spi_rx[5], spi_rx[6]};
    crc   = 8'h00;
    for (int i = 1; i <= 6; i++) crc = tb_crc8_update(crc, spi_rx[i]);
    crc_ok = (crc === spi_rx[7]);
endtask

// ------------------------------------------------------------------ timing monitors (as rtl/tb/spi_bfm.svh)
real spi_t_fall = 0.0;
real spi_t_csfall = 0.0;
always @(negedge SCLK) spi_t_fall = $realtime;
always @(miso_pin) begin                     // at the pin: a change while SCLK is high came too late
    if (oe_pin === 1'b1 && CS_N === 1'b0 && SCLK === 1'b1 && $realtime - spi_t_csfall > 4.0 * TMCLK)
        spi_err("MISO changed while SCLK is high");
end
always @(negedge CS_N) spi_t_csfall = $realtime;
always @(posedge CS_N) begin
    #0.001;
    if (MISO_OE !== 1'b0) spi_err("MISO_OE still high after CS_N rose");
end
always @(posedge MISO_OE) begin
    if (CS_N !== 1'b0) spi_err("MISO_OE raised while CS_N is high");
    if ($realtime - spi_t_csfall > spi_oe_lat_max) spi_oe_lat_max = $realtime - spi_t_csfall;
    if ($realtime - spi_t_csfall > 4.0 * TMCLK) spi_err("MISO_OE later than 4 MCLK after CS_N fell");
end
