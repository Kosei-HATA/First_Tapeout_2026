// spi_bfm.svh - SPI mode-0 master bus functional model and SPI timing monitors.
//
// Included inside a testbench module that declares:
//   logic SCLK, CS_N, MOSI;  wire MISO, MISO_OE;  localparam real TMCLK
// The master runs on its own time base (asynchronous to MCLK).
//
// Tasks:
//   spi_xfer(nbytes, extra_bits)      raw transfer of spi_tx[0..nbytes-1]
//   spi_read_reg(addr, val)
//   spi_write_reg(addr, val)
//   spi_read_sample(nbytes, status, seq, data, crc_ok)
// Monitors (errors counted in spi_errors):
//   * MISO changes only while SCLK is low, and within 4 MCLK periods after
//     the SCLK falling edge (reports the maximum latency)
//   * MISO_OE is 0 whenever CS_N is 1 (checked 1 ps after CS_N rises) and is
//     never raised while CS_N is 1; it rises within 4 MCLK after CS_N falls
//   * MISO_OE is on at every SCLK rising edge (no 'z' sampled)

logic [7:0] spi_tx [0:15];
logic [7:0] spi_rx [0:15];
real        spi_half  = 250.0;      // SCLK half period [ns] (250 -> 2 MHz)
real        spi_tcss  = 300.0;      // CS_N fall -> first SCLK rise [ns]
real        spi_tcsh  = 200.0;      // last SCLK fall -> CS_N rise [ns]
real        spi_tidle = 600.0;      // CS_N high time after a transfer [ns]
integer     spi_errors = 0;
integer     spi_xfers = 0;
integer     spi_sample_frames = 0;      // READ_SAMPLE transfers (complete or not)
bit         spi_cs_hold = 1'b0;     // when set, CS_N stays low after the last bit until cleared
bit         spi_cs_waiting = 1'b0;  // spi_xfer is waiting for spi_cs_hold to clear
real        spi_miso_lat_max = 0.0;
real        spi_oe_lat_max = 0.0;

wire        miso_pad = MISO_OE ? MISO : 1'bz;

task automatic spi_err(input string msg);
    spi_errors = spi_errors + 1;
    if (spi_errors <= 10) $display("SPI ERROR @%0t: %s", $time, msg);
endtask

// bit n of the transfer (MSB of spi_tx[0] first); extra bits are 0
function automatic logic spi_bit(input integer n, input integer nbytes);
    if (n < 8 * nbytes) return spi_tx[n / 8][7 - (n % 8)];
    else                return 1'b0;
endfunction

// Mode 0: MOSI changes after SCLK falls, both sides sample on SCLK rising.
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
        #(spi_half);
        SCLK = 1'b0;
        MOSI = (n + 1 < total) ? spi_bit(n + 1, nbytes) : 1'b0;
        if (n + 1 < total) #(spi_half);
    end
    #(spi_tcsh);
    spi_cs_waiting = 1'b1;
    while (spi_cs_hold) #1.0;
    spi_cs_waiting = 1'b0;
    CS_N = 1'b1;
    #(spi_tidle);
    spi_xfers = spi_xfers + 1;
endtask

task automatic spi_read_reg(input logic [7:0] addr, output logic [7:0] val);
    spi_tx[0] = 8'h10;
    spi_tx[1] = addr;
    spi_tx[2] = 8'h00;
    spi_xfer(3, 0);
    if (spi_rx[0] !== 8'h00 || spi_rx[1] !== 8'h00) spi_err("READ_REG: MISO bytes 0/1 not zero");
    val = spi_rx[2];
endtask

task automatic spi_write_reg(input logic [7:0] addr, input logic [7:0] val);
    spi_tx[0] = 8'h20;
    spi_tx[1] = addr;
    spi_tx[2] = val;
    spi_xfer(3, 0);
endtask

// CRC-8/SMBUS, bytewise (independent of the RTL bit-serial implementation)
function automatic logic [7:0] tb_crc8_update(input logic [7:0] crc, input logic [7:0] data);
    logic [7:0] c;
    c = crc ^ data;
    for (int i = 0; i < 8; i++) c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
    return c;
endfunction

// READ_SAMPLE with nbytes bytes (8 = complete frame) and extra clock bits
task automatic spi_read_sample_n(input integer nbytes, input integer extra_bits,
                                 output logic [7:0] status, output logic [15:0] seq,
                                 output logic [23:0] data, output bit crc_ok);
    logic [7:0] crc;
    spi_tx[0] = 8'h30;
    for (int i = 1; i < 16; i++) spi_tx[i] = 8'h00;
    spi_xfer(nbytes, extra_bits);
    spi_sample_frames = spi_sample_frames + 1;
    if (spi_rx[0] !== 8'h00) spi_err("READ_SAMPLE: MISO byte 0 not zero");
    status = spi_rx[1];
    seq    = {spi_rx[2], spi_rx[3]};
    data   = {spi_rx[4], spi_rx[5], spi_rx[6]};
    crc    = 8'h00;
    for (int i = 1; i <= 6; i++) crc = tb_crc8_update(crc, spi_rx[i]);
    crc_ok = (nbytes >= 8) && (crc === spi_rx[7]);
    for (int i = 8; i < nbytes; i++)
        if (spi_rx[i] !== 8'h00) spi_err("READ_SAMPLE: MISO after the CRC byte not zero");
endtask

task automatic spi_read_sample(output logic [7:0] status, output logic [15:0] seq,
                               output logic [23:0] data, output bit crc_ok);
    spi_read_sample_n(8, 0, status, seq, data, crc_ok);
endtask

// ---------------------------------------------------------------------
// Timing monitors
// ---------------------------------------------------------------------
real spi_t_fall = 0.0;
real spi_t_csfall = 0.0;

always @(negedge SCLK) spi_t_fall = $realtime;

always @(MISO) begin
    if (MISO_OE === 1'b1 && CS_N === 1'b0) begin
        if (SCLK === 1'b1) spi_err("MISO changed while SCLK is high");
        if ($realtime - spi_t_fall > spi_miso_lat_max) spi_miso_lat_max = $realtime - spi_t_fall;
        if ($realtime - spi_t_fall > 4.0 * TMCLK) spi_err($sformatf("MISO latency %0.1f ns > 4 MCLK", $realtime - spi_t_fall));
    end
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
