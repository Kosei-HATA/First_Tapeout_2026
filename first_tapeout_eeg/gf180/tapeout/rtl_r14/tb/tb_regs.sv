// tb_regs - eeg_regs alone: the W1C flags when a set event and the host's clear land in the same cycle (audit round 3,
// 11/20; FLG-02: a flag set in the cycle of its W1C clear survives - the set wins).
//
// For every ERR bit set from outside the register block (FRAME_ERR, CRC_ERR, ADDR_ERR from the SPI; STATE_ERR,
// CFG_ERR from the sequencer) and both DFLAG bits (OVERRUN from the FIFO, OVL from the overload detector): a clear alone
// leaves the bit 0; a set alone leaves it 1; a clear of 0xFF committed in the very cycle of the set leaves it 1 and
// every other bit 0. The flags are read through rdata at their address (the SPI's read path).
//
// cfg_ok and nr_ok (audit round 4, 11/20): every vector of build/ok_vectors.txt (tb/gen_ok_vectors.py, from regmap's
// cfg_ok, nr_ok, field layout and legal values): the active bytes are written and applied (apply), the shadow bytes
// written, and eeg_regs's cfg_ok and nr_ok compared with regmap's. The vectors cover the full 10-bit M (both bytes:
// one step across 255/256 and 511/512, M_H or M_L alone changed), both signs, every range, every other applied field
// and random pairs. Every write must be accepted (no error flag).
//
// The command's acknowledge cycle (audit round 5, 11/20: a command or a guarded write committed in the very cycle the
// tick takes the pending command was never tested; a copy that lost such a command passed every test): a command
// written in the ack cycle becomes the new pending command (no STATE_ERR); a shadow write in the ack cycle is written
// (no STATE_ERR); outside the ack cycle both are refused with STATE_ERR while a command is pending.
`timescale 1ns / 1ps
`default_nettype none

module tb_regs;
    logic       clk = 1'b0, rst_n = 1'b0;
    logic [6:0] addr = 7'h00;
    logic       we = 1'b0;
    logic [7:0] wdata = 8'h00;
    logic       frame_err_set = 1'b0, crc_err_set = 1'b0, addr_err_set = 1'b0;
    logic [3:0] state = 4'd0;
    logic       afe_rst = 1'b1, fifo_nonempty = 1'b0;
    logic [3:0] fifo_level = 4'd0;
    logic       ovl_now = 1'b0, ovr_set = 1'b0, ovl_set = 1'b0, seq_state_err = 1'b0, seq_cfg_err = 1'b0;
    logic       cmd_ack = 1'b0, apply = 1'b0;
    wire  [7:0] rdata, cmd_code, status_byte, t_warm, t_elec, t_rec, t_pre, t_rst;
    wire        addr_ok, cmd_valid, soft_reset, cfg_ok, nr_ok, off_sign, chop_fast, dwa_en, atp_en, chop_stop,
                adc_zero, raw_en, crc_en, drdy_mode, alert, dflag_overrun;
    wire  [9:0] off_mag;
    wire  [3:0] ofen, cpf_trim, blank_len, atp_sel;
    wire  [1:0] afe_ibias, btrim_p, btrim_n, dbg_sel;
    wire  [2:0] chop1_rate;

    eeg_regs #(.FIFO_DEPTH(8)) dut (.*);

    always #15.26 clk = ~clk;

    integer errors = 0, n = 0;
    localparam logic [6:0] A_ERR = 7'h06, A_DFLAG = 7'h07;

    task automatic read_reg(input logic [6:0] a, output logic [7:0] v);
        @(negedge clk);
        addr = a;
        #1 v = rdata;
    endtask

    // one cycle with the set event (bit k of the source vector) and / or the W1C clear of 0xFF at reg_addr
    task automatic cycle(input logic [6:0] reg_addr, input integer src, input logic set, input logic clr);
        @(negedge clk);
        addr = reg_addr;  we = clr;  wdata = 8'hFF;
        case (src)
            0: frame_err_set = set;
            1: crc_err_set   = set;
            2: addr_err_set  = set;
            3: seq_state_err = set;
            4: seq_cfg_err   = set;
            5: ovr_set       = set;
            default: ovl_set = set;
        endcase
        @(negedge clk);
        we = 1'b0;  frame_err_set = 1'b0;  crc_err_set = 1'b0;  addr_err_set = 1'b0;  seq_state_err = 1'b0;
        seq_cfg_err = 1'b0;  ovr_set = 1'b0;  ovl_set = 1'b0;
    endtask

    initial begin
        // bit of each source in its register (regmap: ERR FRAME 1, CRC 2, ADDR 3, STATE 6, CFG 5; DFLAG OVERRUN 0, OVL 1)
        integer bitpos [0:6];
        logic [7:0] v;
        string  nm [0:6];
        bitpos = '{1, 2, 3, 6, 5, 0, 1};
        nm = '{"FRAME_ERR", "CRC_ERR", "ADDR_ERR", "STATE_ERR", "CFG_ERR", "DFLAG.OVERRUN", "DFLAG.OVL"};
        repeat (3) @(negedge clk);
        rst_n = 1'b1;
        for (int s = 0; s < 7; s++) begin
            logic [6:0] a;
            a = (s < 5) ? A_ERR : A_DFLAG;
            cycle(a, s, 1'b0, 1'b1);                    // clear (also RESET_FLAG)
            read_reg(a, v);
            if (v !== 8'h00) begin $display("ERROR: %s: 0x%02h after a clear", nm[s], v); errors++; end
            cycle(a, s, 1'b1, 1'b0);                    // set alone
            read_reg(a, v);
            if (v !== 8'(1 << bitpos[s])) begin $display("ERROR: %s: 0x%02h after a set", nm[s], v); errors++; end
            cycle(a, s, 1'b1, 1'b1);                    // set and clear in the same cycle: the set wins
            read_reg(a, v);
            if (v !== 8'(1 << bitpos[s])) begin
                $display("ERROR: %s: 0x%02h after a set in the cycle of its W1C clear (the set must win)", nm[s], v);
                errors++;
            end
            cycle(a, s, 1'b0, 1'b1);                    // and a clear alone removes it
            read_reg(a, v);
            if (v !== 8'h00) begin $display("ERROR: %s: 0x%02h after the final clear", nm[s], v); errors++; end
            n = n + 4;
        end
        // per bit: two flags set together, a W1C write of one of them leaves the other
        @(negedge clk); frame_err_set = 1'b1; crc_err_set = 1'b1; ovr_set = 1'b1; ovl_set = 1'b1;
        @(negedge clk); frame_err_set = 1'b0; crc_err_set = 1'b0; ovr_set = 1'b0; ovl_set = 1'b0;
        @(negedge clk); addr = A_ERR; we = 1'b1; wdata = 8'h02;          // FRAME_ERR only
        @(negedge clk); we = 1'b0;
        read_reg(A_ERR, v);
        if (v !== 8'h04) begin $display("ERROR: ERR 0x%02h after clearing FRAME_ERR alone, expected 0x04 (CRC_ERR kept)", v); errors++; end
        @(negedge clk); addr = A_DFLAG; we = 1'b1; wdata = 8'h01;        // OVERRUN only
        @(negedge clk); we = 1'b0;
        read_reg(A_DFLAG, v);
        if (v !== 8'h02) begin $display("ERROR: DFLAG 0x%02h after clearing OVERRUN alone, expected 0x02 (OVL kept)", v); errors++; end
        n = n + 2;
        $display("tb_regs: %0d checks of the W1C flags, %0d errors", n, errors);
        // ---------------- cfg_ok and nr_ok against regmap.cfg_ok / regmap.nr_ok
        begin
            integer fd, rc, na, nv, nbad, cexp, nexp, ncfg, nnr;
            integer ad [0:15];
            integer ab [0:15];
            integer sb [0:15];
            logic [7:0] e;
            fd = $fopen("build/ok_vectors.txt", "r");
            if (fd == 0) begin
                $display("FAIL: tb_regs (build/ok_vectors.txt missing: run tb/gen_ok_vectors.py)");
                $finish;
            end
            rc = $fscanf(fd, "%d", na);
            for (int i = 0; i < na; i++) rc = $fscanf(fd, "%h", ad[i]);
            @(negedge clk); addr = 7'h11; we = 1'b1; wdata = 8'h3C;     // TEST_KEY: the test registers are applied too
            @(negedge clk); addr = A_ERR; wdata = 8'hFF;                 // ERR cleared before the vectors
            @(negedge clk); we = 1'b0;
            nv = 0; nbad = 0; ncfg = 0; nnr = 0;
            while (1) begin
                rc = $fscanf(fd, "%h", ab[0]);
                if (rc != 1) break;
                for (int i = 1; i < na; i++) rc = $fscanf(fd, "%h", ab[i]);
                for (int i = 0; i < na; i++) rc = $fscanf(fd, "%h", sb[i]);
                rc = $fscanf(fd, "%d %d", cexp, nexp);
                for (int i = 0; i < na; i++) begin @(negedge clk); addr = 7'(ad[i]); we = 1'b1; wdata = 8'(ab[i]); end
                @(negedge clk); we = 1'b0; apply = 1'b1;                 // shadow -> active
                @(negedge clk); apply = 1'b0;
                for (int i = 0; i < na; i++) begin @(negedge clk); addr = 7'(ad[i]); we = 1'b1; wdata = 8'(sb[i]); end
                @(negedge clk); we = 1'b0;
                #1;
                if (cfg_ok !== 1'(cexp) || nr_ok !== 1'(nexp)) begin
                    nbad = nbad + 1;
                    if (nbad <= 10) $display("ERROR: ok vector %0d: cfg_ok %b nr_ok %b, regmap %0d %0d", nv, cfg_ok, nr_ok,
                                             cexp, nexp);
                end
                ncfg = ncfg + cexp;
                nnr  = nnr + nexp;
                nv = nv + 1;
            end
            $fclose(fd);
            read_reg(A_ERR, v);
            e = v;
            if (e !== 8'h00) begin $display("ERROR: ERR 0x%02h after the vectors' writes (every write must be accepted)", e); nbad = nbad + 1; end
            if (nv < 1000) begin $display("ERROR: only %0d ok vectors read", nv); nbad = nbad + 1; end
            $display("tb_regs: %0d cfg_ok / nr_ok vectors (cfg_ok %0d, nr_ok %0d true) against regmap, %0d mismatches",
                     nv, ncfg, nnr, nbad);
            errors = errors + nbad;
        end
        // ---------------- the command's acknowledge cycle
        begin
            integer nack;
            logic [7:0] e;
            nack = 0;
            @(negedge clk); addr = A_ERR; we = 1'b1; wdata = 8'hFF;      // ERR cleared
            @(negedge clk); addr = 7'h10; wdata = 8'h55;                 // FLUSH: pending
            @(negedge clk); we = 1'b0;
            if (cmd_valid !== 1'b1 || cmd_code !== 8'h55) begin $display("ERROR: FLUSH not pending"); nack++; end
            @(negedge clk); addr = 7'h10; we = 1'b1; wdata = 8'h11; cmd_ack = 1'b1;   // START in the ack cycle
            @(negedge clk); we = 1'b0; cmd_ack = 1'b0;
            if (cmd_valid !== 1'b1 || cmd_code !== 8'h11) begin
                $display("ERROR: a command written in the ack cycle is not the new pending one (valid %b code %02h)", cmd_valid, cmd_code);
                nack++;
            end
            read_reg(A_ERR, e);
            if (e[6] !== 1'b0) begin $display("ERROR: STATE_ERR for a command written in the ack cycle"); nack++; end
            @(negedge clk); addr = 7'h21; we = 1'b1; wdata = 8'h5A;      // a shadow write while START waits: refused
            @(negedge clk); we = 1'b0;
            read_reg(A_ERR, e);
            if (e[6] !== 1'b1) begin $display("ERROR: no STATE_ERR for a shadow write while a command is pending"); nack++; end
            read_reg(7'h21, e);
            if (e === 8'h5A) begin $display("ERROR: a shadow written while a command is pending"); nack++; end
            @(negedge clk); addr = A_ERR; we = 1'b1; wdata = 8'hFF;
            @(negedge clk); addr = 7'h21; we = 1'b1; wdata = 8'h5A; cmd_ack = 1'b1;  // the same write in the ack cycle
            @(negedge clk); we = 1'b0; cmd_ack = 1'b0;
            read_reg(7'h21, e);
            if (e !== 8'h5A) begin $display("ERROR: a shadow write in the ack cycle not written (0x%02h)", e); nack++; end
            read_reg(A_ERR, e);
            if (e[6] !== 1'b0) begin $display("ERROR: STATE_ERR for a shadow write in the ack cycle"); nack++; end
            if (cmd_valid !== 1'b0) begin $display("ERROR: the acknowledged command still pending"); nack++; end
            @(negedge clk); addr = 7'h21; we = 1'b1; wdata = 8'h00;
            @(negedge clk); addr = A_ERR; wdata = 8'hFF;
            @(negedge clk); we = 1'b0;
            $display("tb_regs: the command's acknowledge cycle: 8 checks, %0d errors", nack);
            errors = errors + nack;
        end
        if (errors == 0) $display("PASS: tb_regs (a set in the cycle of its W1C clear wins; cfg_ok and nr_ok == regmap; the ack cycle)");
        else             $display("FAIL: tb_regs");
        $finish;
    end
endmodule

`default_nettype wire
