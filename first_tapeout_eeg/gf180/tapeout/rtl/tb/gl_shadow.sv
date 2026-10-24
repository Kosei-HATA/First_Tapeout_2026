// gl_shadow - the gate-level netlists of eeg_digital_top and eeg_adc_dig (the LibreLane
// final netlists used on the chip, gf180/tapeout/layout/gds/*.nl.v, with the module
// names suffixed _gl) in lockstep with the RTL design under test of a system
// testbench.
//
// Compile it as a second root module with +define+TB=<testbench> (tb_spi, tb_top or
// tb_e2e) and +define+FUNCTIONAL (cell models without specify blocks, zero delay).
// The testbench's design under test must be `dut` (eeg_digital_sys with
// DAC_LOAD_CYCLE = 2, the value the macros were synthesized with). The netlists get
// the testbench's inputs (MCLK, RESET_N, SCLK, CS_N, MOSI, TH) and are connected to
// each other as in eeg_digital_sys.sv. At every MCLK falling edge all outputs, and
// the wires between the two blocks, must equal those of the RTL (4-state compare,
// so an X in one of them is a mismatch). The result line is printed at the end of
// the simulation (PASS/FAIL, picked up by run_tests.sh and run_e2e.sh).
`timescale 1ns / 1ps

module gl_shadow;

    wire        mclk     = `TB.MCLK;
    wire        reset_n  = `TB.RESET_N;
    wire        sclk     = `TB.SCLK;
    wire        cs_n     = `TB.CS_N;
    wire        mosi     = `TB.MOSI;
    wire [30:0] th       = `TB.TH;

    wire        miso, miso_oe, drdy_n, raw_data, raw_clk;
    wire        adc_rst_n, th_capture, dac_load, dwa_en;
    wire [4:0]  code;
    wire [30:0] sel1, sel2;
    wire        cmp_strobe, dac_clk, chop, chop_out, chop_blank, afe_rst, chop_en, chop1;
    wire [7:0]  test_cfg;
    wire [3:0]  cpf_trim;
    wire [1:0]  afe_ibias, btrim_p, btrim_n;
    wire [9:0]  ofm;
    wire        ofs;
    wire [3:0]  ofen;

    eeg_digital_top_gl g_top (
        .MCLK (mclk), .RESET_N (reset_n),
        .SCLK (sclk), .CS_N (cs_n), .MOSI (mosi), .MISO (miso), .MISO_OE (miso_oe),
        .DRDY_N (drdy_n), .RAW_DATA (raw_data), .RAW_CLK (raw_clk),
        .ADC_RST_N (adc_rst_n), .TH_CAPTURE (th_capture), .DAC_LOAD (dac_load),
        .DWA_EN (dwa_en), .CODE (code),
        .CMP_STROBE (cmp_strobe), .DAC_CLK (dac_clk),
        .CHOP (chop), .CHOP_OUT (chop_out), .CHOP_BLANK (chop_blank),
        .AFE_RST (afe_rst), .CHOP_EN (chop_en),
        .TEST_CFG (test_cfg), .CPF_TRIM (cpf_trim), .AFE_IBIAS (afe_ibias),
        .BTRIM_P (btrim_p), .BTRIM_N (btrim_n), .OFM (ofm), .OFS (ofs), .OFEN (ofen),
        .CHOP1 (chop1)
    );

    eeg_adc_dig_gl g_adc (
        .MCLK (mclk), .RST_N (adc_rst_n),
        .TH_CAPTURE (th_capture), .DAC_LOAD (dac_load), .DWA_EN (dwa_en),
        .TH (th), .CODE (code), .SEL1 (sel1), .SEL2 (sel2)
    );

    // outputs of eeg_digital_sys, then the wires between the blocks
    wire [116:0] v_gl = {miso, miso_oe, drdy_n, raw_data, raw_clk, sel1, sel2,
                         cmp_strobe, dac_clk, chop, chop_out, chop_blank, afe_rst, chop_en,
                         test_cfg, cpf_trim, afe_ibias, btrim_p, btrim_n, ofm, ofs, ofen, chop1,
                         adc_rst_n, th_capture, dac_load, dwa_en, code};
    wire [116:0] v_rtl = {`TB.dut.MISO, `TB.dut.MISO_OE, `TB.dut.DRDY_N, `TB.dut.RAW_DATA,
                          `TB.dut.RAW_CLK, `TB.dut.SEL1, `TB.dut.SEL2,
                          `TB.dut.CMP_STROBE, `TB.dut.DAC_CLK, `TB.dut.CHOP, `TB.dut.CHOP_OUT,
                          `TB.dut.CHOP_BLANK, `TB.dut.AFE_RST, `TB.dut.CHOP_EN,
                          `TB.dut.TEST_CFG, `TB.dut.CPF_TRIM, `TB.dut.AFE_IBIAS,
                          `TB.dut.BTRIM_P, `TB.dut.BTRIM_N, `TB.dut.OFM, `TB.dut.OFS,
                          `TB.dut.OFEN, `TB.dut.CHOP1,
                          `TB.dut.adc_rst_n, `TB.dut.th_capture, `TB.dut.dac_load,
                          `TB.dut.dwa_en, `TB.dut.code};

    function automatic string sig_name(input integer b);
        // bit index (0 = LSB of code) to a signal name
        if (b < 5)   return $sformatf("CODE[%0d]", b);
        if (b == 5)  return "DWA_EN";
        if (b == 6)  return "DAC_LOAD";
        if (b == 7)  return "TH_CAPTURE";
        if (b == 8)  return "ADC_RST_N";
        if (b == 9)  return "CHOP1";
        if (b < 14)  return $sformatf("OFEN[%0d]", b - 10);
        if (b == 14) return "OFS";
        if (b < 25)  return $sformatf("OFM[%0d]", b - 15);
        if (b < 27)  return $sformatf("BTRIM_N[%0d]", b - 25);
        if (b < 29)  return $sformatf("BTRIM_P[%0d]", b - 27);
        if (b < 31)  return $sformatf("AFE_IBIAS[%0d]", b - 29);
        if (b < 35)  return $sformatf("CPF_TRIM[%0d]", b - 31);
        if (b < 43)  return $sformatf("TEST_CFG[%0d]", b - 35);
        if (b == 43) return "CHOP_EN";
        if (b == 44) return "AFE_RST";
        if (b == 45) return "CHOP_BLANK";
        if (b == 46) return "CHOP_OUT";
        if (b == 47) return "CHOP";
        if (b == 48) return "DAC_CLK";
        if (b == 49) return "CMP_STROBE";
        if (b < 81)  return $sformatf("SEL2[%0d]", b - 50);
        if (b < 112) return $sformatf("SEL1[%0d]", b - 81);
        if (b == 112) return "RAW_CLK";
        if (b == 113) return "RAW_DATA";
        if (b == 114) return "DRDY_N";
        if (b == 115) return "MISO_OE";
        return "MISO";
    endfunction

    longint cycles = 0;
    longint mismatch_cycles = 0;
    integer reported = 0;

    always @(negedge mclk) begin
        cycles = cycles + 1;
        if (v_gl !== v_rtl) begin
            mismatch_cycles = mismatch_cycles + 1;
            if (reported < 20) begin
                for (int b = 0; b < 117 && reported < 20; b++) begin
                    if (v_gl[b] !== v_rtl[b]) begin
                        reported = reported + 1;
                        $display("GL MISMATCH @%0t: %s gate level %b, RTL %b", $time, sig_name(b), v_gl[b], v_rtl[b]);
                    end
                end
            end
        end
    end

    final begin
        if (mismatch_cycles == 0)
            $display("PASS: gate level == RTL at every MCLK falling edge (%0d cycles, %0d signals: all outputs of both macros and the wires between them)", cycles, 117);
        else
            $display("FAIL: gate level != RTL in %0d of %0d cycles", mismatch_cycles, cycles);
    end

endmodule
