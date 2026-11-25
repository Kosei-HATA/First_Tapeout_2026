// gl_shadow_r14 - the r14 macro's final gate-level netlist (LibreLane final/nl, module renamed eeg_digital_top_gl) in
// lockstep with the RTL design under test of an r14 testbench (requirement VER-05; tracker C4).
//
// Compile it as a second root module with +define+TB=<testbench> (tb_top_r14, tb_spi_r14, gl_sdf_r14). The
// testbench's design under test must be `dut` (eeg_digital_top, DAC_LOAD_CYCLE 2, FIFO_DEPTH 8: the macro's
// parameters). The netlist gets the testbench's inputs (MCLK, RESET_N, SCLK, CS_N, MOSI, CODE; with
// +define+GL_CODE_SRC=sys_adc_r14.code_gl its CODE comes from the ADC block's netlist instead, sys_adc_r14.sv) and every one of its 50
// outputs must equal the RTL's (4-state compare, an X in either is a mismatch), and so must the two state registers of
// NFR-05 (the sequencer's state and the SPI's st, kept as named nets through synthesis).
//
// Zero delay (+define+FUNCTIONAL, cell models without specify blocks): compared 1 ps after every MCLK falling edge.
// The testbenches change some RTL registers by hand; the same change goes into the netlist (zero delay only):
//   - tb_top_r14 forces dut.u_spi.st to an illegal value (phase A) and deposits dut.seq_cnt (phase K): when such a
//     register changes away from an MCLK rising edge, its flip-flops' Q nets in the netlist are forced to the new value
//     until 1 ps after the next rising edge, where the flip-flops take their D from it (the RTL's variable keeps the
//     value until its next assignment at that edge, which the release of a forced variable allows: the same cycle);
//   - tb_top_r14 forces dut.soft_req (the register block's SOFT_RESET commit, phase R), a net the netlist does not
//     keep: the register block's write port is forced instead (reg_we 1, reg_addr COMMAND 0x10, reg_wdata 0xA5, which
//     eeg_regs decodes as nothing but soft_reset) for the same time; the SPI flip-flops and the registers that take the
//     forced values at the edge are cleared by the soft reset they start (rst_n falls at that edge).
//   Every such mirrored change is counted and reported.
// With +define+GL_SDF (cell models with their specify paths, iverilog -gspecify, the SDF of one corner annotated):
// compared just before every MCLK rising edge (in the active region of the edge, before the RTL's registers update
// and before any delayed netlist output moves); the latest change of the netlist's outputs after a rising edge is
// reported (MISO_OE, combinational from CS_N, left out of that). Icarus applies the SDF's path and interconnect delays
// but not its timing checks; setup / hold are the STA's. The testbench must then move the asynchronous pins (SPI,
// RESET_N) at MCLK falling edges (gl_sdf_r14.sv does).
`timescale 1ns / 1ps
// The flip-flop Q nets of the registers compared and forced: gl_names.svh, written for the netlist by gl_names.py
// (which name a register's net has, and the flip-flop behind any buffer, differ from run to run).
`include "gl_names.svh"

module gl_shadow_r14;

    wire        mclk    = `TB.MCLK;
    wire        reset_n = `TB.RESET_N;
    wire        sclk    = `TB.SCLK;
    wire        cs_n    = `TB.CS_N;
    wire        mosi    = `TB.MOSI;
`ifdef GL_CODE_SRC
    wire [4:0]  code    = `GL_CODE_SRC;          // the ADC block's netlist (sys_adc_r14.sv): the loop closed at gate level
`else
    wire [4:0]  code    = `TB.CODE;
`endif

    wire        miso, miso_oe, drdy_n, raw_data, raw_clk, adc_rst_n, th_capture, dac_load, dwa_en;
    wire        cmp_strobe, dac_clk, chop, chop_out, chop_blank, afe_rst, chop_en, chop1, ofs;
    wire [7:0]  test_cfg;
    wire [3:0]  cpf_trim, ofen;
    wire [1:0]  afe_ibias, btrim_p, btrim_n;
    wire [9:0]  ofm;

    eeg_digital_top_gl g (
        .MCLK (mclk), .RESET_N (reset_n), .SCLK (sclk), .CS_N (cs_n), .MOSI (mosi), .MISO (miso), .MISO_OE (miso_oe),
        .DRDY_N (drdy_n), .RAW_DATA (raw_data), .RAW_CLK (raw_clk), .ADC_RST_N (adc_rst_n), .TH_CAPTURE (th_capture),
        .DAC_LOAD (dac_load), .DWA_EN (dwa_en), .CODE (code), .CMP_STROBE (cmp_strobe), .DAC_CLK (dac_clk),
        .CHOP (chop), .CHOP_OUT (chop_out), .CHOP_BLANK (chop_blank), .AFE_RST (afe_rst), .CHOP_EN (chop_en),
        .TEST_CFG (test_cfg), .CPF_TRIM (cpf_trim), .AFE_IBIAS (afe_ibias), .BTRIM_P (btrim_p), .BTRIM_N (btrim_n),
        .OFM (ofm), .OFS (ofs), .OFEN (ofen), .CHOP1 (chop1)
    );

    // the 50 outputs, MISO first (bit 49) ... CHOP1 last (bit 0)
    wire [49:0] v_gl = {miso, miso_oe, drdy_n, raw_data, raw_clk, adc_rst_n, th_capture, dac_load, dwa_en,
                        cmp_strobe, dac_clk, chop, chop_out, chop_blank, afe_rst, chop_en,
                        test_cfg, cpf_trim, afe_ibias, btrim_p, btrim_n, ofm, ofs, ofen, chop1};
    wire [49:0] v_rtl = {`TB.dut.MISO, `TB.dut.MISO_OE, `TB.dut.DRDY_N, `TB.dut.RAW_DATA, `TB.dut.RAW_CLK,
                         `TB.dut.ADC_RST_N, `TB.dut.TH_CAPTURE, `TB.dut.DAC_LOAD, `TB.dut.DWA_EN,
                         `TB.dut.CMP_STROBE, `TB.dut.DAC_CLK, `TB.dut.CHOP, `TB.dut.CHOP_OUT, `TB.dut.CHOP_BLANK,
                         `TB.dut.AFE_RST, `TB.dut.CHOP_EN, `TB.dut.TEST_CFG, `TB.dut.CPF_TRIM, `TB.dut.AFE_IBIAS,
                         `TB.dut.BTRIM_P, `TB.dut.BTRIM_N, `TB.dut.OFM, `TB.dut.OFS, `TB.dut.OFEN, `TB.dut.CHOP1};
    // the state registers of NFR-05 (named nets of the netlist)
    wire [3:0]  seq_gl = `GL_SEQ ;
    wire [3:0]  st_gl  = `GL_ST ;
    wire [3:0]  seq_rtl = `TB.dut.seq_state;
    wire [3:0]  st_rtl  = `TB.dut.u_spi.st;

    function automatic string sig_name(input integer b);
        if (b == 0)  return "CHOP1";
        if (b < 5)   return $sformatf("OFEN[%0d]", b - 1);
        if (b == 5)  return "OFS";
        if (b < 16)  return $sformatf("OFM[%0d]", b - 6);
        if (b < 18)  return $sformatf("BTRIM_N[%0d]", b - 16);
        if (b < 20)  return $sformatf("BTRIM_P[%0d]", b - 18);
        if (b < 22)  return $sformatf("AFE_IBIAS[%0d]", b - 20);
        if (b < 26)  return $sformatf("CPF_TRIM[%0d]", b - 22);
        if (b < 34)  return $sformatf("TEST_CFG[%0d]", b - 26);
        case (b)
            34: return "CHOP_EN";    35: return "AFE_RST";    36: return "CHOP_BLANK"; 37: return "CHOP_OUT";
            38: return "CHOP";       39: return "DAC_CLK";    40: return "CMP_STROBE"; 41: return "DWA_EN";
            42: return "DAC_LOAD";   43: return "TH_CAPTURE"; 44: return "ADC_RST_N";  45: return "RAW_CLK";
            46: return "RAW_DATA";   47: return "DRDY_N";     48: return "MISO_OE";    default: return "MISO";
        endcase
    endfunction

    longint cycles = 0;
    longint mismatch_cycles = 0;
    integer reported = 0;
    integer n_mirror_st = 0, n_mirror_seq = 0, n_mirror_soft = 0;

    // ---------------------------------------------------------------- the testbench's register changes, mirrored
    // (with the SDF too: the forces are released REL after the next rising edge, when the flip-flops' clock-to-output
    // delays are over, so that the net then carries what the flip-flop took)
`ifdef GL_SDF
    localparam real REL = 7.0;
`else
    localparam real REL = 0.001;
`endif
    realtime t_pos = -1.0;
    always @(posedge mclk) t_pos = $realtime;
    bit st_hold = 0, cnt_hold = 0, seq_hold = 0;
    integer n_mirror_state = 0;
    // u_seq.state (gl_sdf_r14 forces the illegal values 9..15)
    task automatic force_seq(input logic [3:0] v);
        if (v[0]) force `GL_SEQ_0 = 1'b1; else force `GL_SEQ_0 = 1'b0;
        if (v[1]) force `GL_SEQ_1 = 1'b1; else force `GL_SEQ_1 = 1'b0;
        if (v[2]) force `GL_SEQ_2 = 1'b1; else force `GL_SEQ_2 = 1'b0;
        if (v[3]) force `GL_SEQ_3 = 1'b1; else force `GL_SEQ_3 = 1'b0;
    endtask
    always @(seq_rtl) if ($realtime != t_pos && reset_n === 1'b1 && !seq_hold && seq_rtl !== seq_gl) begin
        seq_hold = 1;
        n_mirror_state = n_mirror_state + 1;
        force_seq(seq_rtl);
        @(posedge mclk); #(REL);
        release `GL_SEQ_0 ; release `GL_SEQ_1 ; release `GL_SEQ_2 ; release `GL_SEQ_3 ;
        seq_hold = 0;
    end
    // u_spi.st: constant forces (Icarus evaluates a forced expression once)
    task automatic force_st(input logic [3:0] v);
        if (v[0]) force `GL_ST_0 = 1'b1; else force `GL_ST_0 = 1'b0;
        if (v[1]) force `GL_ST_1 = 1'b1; else force `GL_ST_1 = 1'b0;
        if (v[2]) force `GL_ST_2 = 1'b1; else force `GL_ST_2 = 1'b0;
        if (v[3]) force `GL_ST_3 = 1'b1; else force `GL_ST_3 = 1'b0;
    endtask
    always @(st_rtl) if ($realtime != t_pos && reset_n === 1'b1 && !st_hold && st_rtl !== st_gl) begin
        st_hold = 1;
        n_mirror_st = n_mirror_st + 1;
        force_st(st_rtl);
        @(posedge mclk); #(REL);
        release `GL_ST_0 ; release `GL_ST_1 ; release `GL_ST_2 ; release `GL_ST_3 ;
        st_hold = 0;
    end
    // seq_cnt (16 bits)
    wire [15:0] cnt_rtl = `TB.dut.seq_cnt;
    task automatic force_cnt(input logic [15:0] v);
        if (v[0]) force `GL_CNT_0 = 1'b1; else force `GL_CNT_0 = 1'b0;
        if (v[1]) force `GL_CNT_1 = 1'b1; else force `GL_CNT_1 = 1'b0;
        if (v[2]) force `GL_CNT_2 = 1'b1; else force `GL_CNT_2 = 1'b0;
        if (v[3]) force `GL_CNT_3 = 1'b1; else force `GL_CNT_3 = 1'b0;
        if (v[4]) force `GL_CNT_4 = 1'b1; else force `GL_CNT_4 = 1'b0;
        if (v[5]) force `GL_CNT_5 = 1'b1; else force `GL_CNT_5 = 1'b0;
        if (v[6]) force `GL_CNT_6 = 1'b1; else force `GL_CNT_6 = 1'b0;
        if (v[7]) force `GL_CNT_7 = 1'b1; else force `GL_CNT_7 = 1'b0;
        if (v[8]) force `GL_CNT_8 = 1'b1; else force `GL_CNT_8 = 1'b0;
        if (v[9]) force `GL_CNT_9 = 1'b1; else force `GL_CNT_9 = 1'b0;
        if (v[10]) force `GL_CNT_10 = 1'b1; else force `GL_CNT_10 = 1'b0;
        if (v[11]) force `GL_CNT_11 = 1'b1; else force `GL_CNT_11 = 1'b0;
        if (v[12]) force `GL_CNT_12 = 1'b1; else force `GL_CNT_12 = 1'b0;
        if (v[13]) force `GL_CNT_13 = 1'b1; else force `GL_CNT_13 = 1'b0;
        if (v[14]) force `GL_CNT_14 = 1'b1; else force `GL_CNT_14 = 1'b0;
        if (v[15]) force `GL_CNT_15 = 1'b1; else force `GL_CNT_15 = 1'b0;
    endtask
    always @(cnt_rtl) if ($realtime != t_pos && reset_n === 1'b1 && !cnt_hold) begin
        cnt_hold = 1;
        n_mirror_seq = n_mirror_seq + 1;
        force_cnt(cnt_rtl);
        @(posedge mclk); #(REL);
        release `GL_CNT_0 ; release `GL_CNT_1 ; release `GL_CNT_2 ; release `GL_CNT_3 ;
        release `GL_CNT_4 ; release `GL_CNT_5 ; release `GL_CNT_6 ; release `GL_CNT_7 ;
        release `GL_CNT_8 ; release `GL_CNT_9 ; release `GL_CNT_10 ; release `GL_CNT_11 ;
        release `GL_CNT_12 ; release `GL_CNT_13 ; release `GL_CNT_14 ; release `GL_CNT_15 ;
        cnt_hold = 0;
    end
    // soft_req: the register block's write port while the RTL's soft_req is forced high (the RTL's own writes of
    // SOFT_RESET come from the SPI, at an MCLK rising edge, and the netlist makes them itself)
    wire soft_rtl = `TB.dut.soft_req;
    bit soft_hold = 0;
    always @(posedge soft_rtl) if ($realtime != t_pos && reset_n === 1'b1) begin
        soft_hold = 1;
        n_mirror_soft = n_mirror_soft + 1;
        force `GL_WE_0 = 1'b1;
        // reg_addr = COMMAND (0x10), reg_wdata = SOFT_RESET (0xA5)
        force `GL_ADDR_6 = 1'b0; force `GL_ADDR_5 = 1'b0; force `GL_ADDR_4 = 1'b1; force `GL_ADDR_3 = 1'b0;
        force `GL_ADDR_2 = 1'b0; force `GL_ADDR_1 = 1'b0; force `GL_ADDR_0 = 1'b0;
        force `GL_WDATA_7 = 1'b1; force `GL_WDATA_6 = 1'b0; force `GL_WDATA_5 = 1'b1; force `GL_WDATA_4 = 1'b0;
        force `GL_WDATA_3 = 1'b0; force `GL_WDATA_2 = 1'b1; force `GL_WDATA_1 = 1'b0; force `GL_WDATA_0 = 1'b1;
        wait (soft_rtl !== 1'b1);
        release `GL_WE_0 ;
        release `GL_ADDR_6 ; release `GL_ADDR_5 ; release `GL_ADDR_4 ; release `GL_ADDR_3 ;
        release `GL_ADDR_2 ; release `GL_ADDR_1 ; release `GL_ADDR_0 ;
        release `GL_WDATA_7 ; release `GL_WDATA_6 ; release `GL_WDATA_5 ; release `GL_WDATA_4 ;
        release `GL_WDATA_3 ; release `GL_WDATA_2 ; release `GL_WDATA_1 ; release `GL_WDATA_0 ;
        soft_hold = 0;
    end

    task automatic compare(input bit skip_first);
        cycles = cycles + 1;
        if (!skip_first && ({v_gl, seq_gl, st_gl} !== {v_rtl, seq_rtl, st_rtl})) begin
            mismatch_cycles = mismatch_cycles + 1;
            if (reported < 20) begin
                for (int b = 49; b >= 0 && reported < 20; b--) begin
                    if (v_gl[b] !== v_rtl[b]) begin
                        reported = reported + 1;
                        $display("GL MISMATCH @%0t: %s gate level %b, RTL %b", $time, sig_name(b), v_gl[b], v_rtl[b]);
                    end
                end
                if (seq_gl !== seq_rtl && reported < 20) begin
                    reported = reported + 1;
                    $display("GL MISMATCH @%0t: seq_state gate level %b, RTL %b", $time, seq_gl, seq_rtl);
                end
                if (st_gl !== st_rtl && reported < 20) begin
                    reported = reported + 1;
                    $display("GL MISMATCH @%0t: u_spi.st gate level %b, RTL %b", $time, st_gl, st_rtl);
                end
            end
        end
    endtask

`ifdef GL_SDF
    initial $sdf_annotate(`GL_SDF_FILE, g);
    // latest change of the netlist's outputs after an MCLK rising edge (MISO_OE left out)
    real t_edge = 0.0, settle_max = 0.0, t_settle_max = 0.0;
    wire [48:0] v_sync = {v_gl[49], v_gl[47:0]};
    always @(v_sync) begin
        if (reset_n === 1'b1 && $realtime - t_edge > settle_max) begin
            settle_max = $realtime - t_edge;
            t_settle_max = $realtime;
        end
    end
    // just before every rising edge: in the edge's active region, before the RTL's registers update; not at the
    // first two edges after a RESET_N release (the RTL takes the release there, after this compare)
    integer since_rel = 0;
    always @(posedge mclk) begin
        t_edge = $realtime;
        since_rel = (reset_n === 1'b1) ? since_rel + 1 : 0;
        compare(since_rel <= 2);
    end
`else
    always @(negedge mclk) begin
        #0.001;
        compare(1'b0);
    end
    // RESET_N's asynchronous reset (tb_top_r14 phase X stops MCLK first): 1 ps after its fall
    always @(negedge reset_n) begin
        #0.001;
        compare(1'b0);
    end
`endif

    final begin
`ifdef GL_SDF
        $display("register changes of the testbench mirrored into the netlist: u_spi.st %0d, u_seq.state %0d, seq_cnt %0d, soft_req %0d",
                 n_mirror_st, n_mirror_state, n_mirror_seq, n_mirror_soft);
        $display("gate level with SDF (%s): latest output change %.3f ns after an MCLK rising edge (at %.3f ns)",
                 `GL_SDF_FILE, settle_max, t_settle_max);
        if (mismatch_cycles == 0)
            $display("PASS: gate level (SDF) == RTL just before every MCLK rising edge (%0d cycles, 50 outputs and the 2 state registers)", cycles);
`else
        $display("register changes of the testbench mirrored into the netlist: u_spi.st %0d, u_seq.state %0d, seq_cnt %0d, soft_req %0d",
                 n_mirror_st, n_mirror_state, n_mirror_seq, n_mirror_soft);
        if (mismatch_cycles == 0)
            $display("PASS: gate level == RTL 1 ps after every MCLK falling edge (%0d cycles, 50 outputs and the 2 state registers)", cycles);
`endif
        else
            $display("FAIL: gate level != RTL in %0d of %0d cycles", mismatch_cycles, cycles);
    end

endmodule
