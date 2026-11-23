// audit37 C: coverage monitor, a second top module beside tb_top_r14 (reads the DUT only).
`timescale 1ns / 1ps
module mon_cov;
    integer f;
    initial f = $fopen("build/cov_apply.txt", "w");
    // every apply: the command, the state, and which settings differ between shadow and active
    always @(posedge tb_top_r14.MCLK) begin
        if (tb_top_r14.dut.rst_n === 1'b1 && tb_top_r14.dut.u_regs.apply === 1'b1) begin
            $fdisplay(f, "APPLY t=%0t cmd=%02h st=%0d m=%0d sign=%0d range=%0d ibias=%0d cpf=%0d bp=%0d bn=%0d fast=%0d dwa=%0d c1=%0d blank=%0d atpen=%0d atpsel=%0d cstop=%0d azero=%0d",
                $time, tb_top_r14.dut.u_regs.pcode, tb_top_r14.dut.seq_state,
                tb_top_r14.dut.u_regs.s_m != tb_top_r14.dut.u_regs.a_m,
                tb_top_r14.dut.u_regs.s_sign != tb_top_r14.dut.u_regs.a_sign,
                tb_top_r14.dut.u_regs.s_range != tb_top_r14.dut.u_regs.a_range,
                tb_top_r14.dut.u_regs.s_ibias != tb_top_r14.dut.u_regs.a_ibias,
                tb_top_r14.dut.u_regs.s_cpf != tb_top_r14.dut.u_regs.a_cpf,
                tb_top_r14.dut.u_regs.s_bp != tb_top_r14.dut.u_regs.a_bp,
                tb_top_r14.dut.u_regs.s_bn != tb_top_r14.dut.u_regs.a_bn,
                tb_top_r14.dut.u_regs.s_fast != tb_top_r14.dut.u_regs.a_fast,
                tb_top_r14.dut.u_regs.s_dwa != tb_top_r14.dut.u_regs.a_dwa,
                tb_top_r14.dut.u_regs.s_c1 != tb_top_r14.dut.u_regs.a_c1,
                tb_top_r14.dut.u_regs.s_blank != tb_top_r14.dut.u_regs.a_blank,
                tb_top_r14.dut.u_regs.s_atpen != tb_top_r14.dut.u_regs.a_atpen,
                tb_top_r14.dut.u_regs.s_atpsel != tb_top_r14.dut.u_regs.a_atpsel,
                tb_top_r14.dut.u_regs.s_cstop != tb_top_r14.dut.u_regs.a_cstop,
                tb_top_r14.dut.u_regs.s_azero != tb_top_r14.dut.u_regs.a_azero);
        end
        // every committed write: address, data, outcome, the state and whether a command was pending
        if (tb_top_r14.dut.rst_n === 1'b1 && tb_top_r14.dut.u_regs.we === 1'b1) begin
            $fdisplay(f, "WRITE t=%0t a=%02h d=%02h ok=%0d ev=%02h st=%0d pend=%0d ack=%0d crc=%0d",
                $time, tb_top_r14.dut.u_regs.addr, tb_top_r14.dut.u_regs.wdata, tb_top_r14.dut.u_regs.w_ok,
                tb_top_r14.dut.u_regs.ev_err, tb_top_r14.dut.seq_state, tb_top_r14.dut.u_regs.pend,
                tb_top_r14.dut.u_regs.cmd_ack, tb_top_r14.dut.u_regs.r_crc);
        end
        // every acknowledged command: code, state, outcome
        if (tb_top_r14.dut.rst_n === 1'b1 && tb_top_r14.dut.cmd_ack === 1'b1) begin
            $fdisplay(f, "ACK t=%0t cmd=%02h st=%0d apply=%0d flush=%0d serr=%0d cerr=%0d cfg_ok=%0d nr_ok=%0d",
                $time, tb_top_r14.dut.cmd_code, tb_top_r14.dut.seq_state, tb_top_r14.dut.apply,
                tb_top_r14.dut.seq_flush, tb_top_r14.dut.seq_serr, tb_top_r14.dut.seq_cerr,
                tb_top_r14.dut.cfg_ok, tb_top_r14.dut.nr_ok);
        end
        // SPI frames: kind at the end (read/write, address, CRC mode, error flags)
        if (tb_top_r14.dut.rst_n === 1'b1 && (tb_top_r14.dut.frame_err === 1'b1 || tb_top_r14.dut.crc_err === 1'b1 ||
            tb_top_r14.dut.addr_err === 1'b1)) begin
            $fdisplay(f, "FLAG t=%0t fe=%0d ce=%0d ae=%0d st=%0d", $time, tb_top_r14.dut.frame_err,
                tb_top_r14.dut.crc_err, tb_top_r14.dut.addr_err, tb_top_r14.dut.seq_state);
        end
        if (tb_top_r14.dut.rst_n === 1'b1 && tb_top_r14.dut.push_ok === 1'b1) begin
            $fdisplay(f, "STORE t=%0t st=%0d lvl=%0d status=%02h dflag=%0d err=%02h", $time, tb_top_r14.dut.seq_state,
                tb_top_r14.dut.fifo_level, tb_top_r14.dut.smp_status, tb_top_r14.dut.u_regs.dflag, tb_top_r14.dut.u_regs.err);
        end
        if (tb_top_r14.dut.rst_n === 1'b1 && tb_top_r14.dut.smp_pop === 1'b1) begin
            $fdisplay(f, "POP t=%0t held=%0d lvl=%0d", $time, tb_top_r14.dut.u_fifo.held, tb_top_r14.dut.fifo_level);
        end
        if (tb_top_r14.dut.rst_n === 1'b1 && tb_top_r14.dut.smp_snap === 1'b1) begin
            $fdisplay(f, "SNAP t=%0t lvl=%0d word=%012h", $time, tb_top_r14.dut.fifo_level, tb_top_r14.dut.smp_word);
        end
    end
endmodule
