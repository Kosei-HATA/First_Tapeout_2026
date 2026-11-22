R14 = "gf180/tapeout/rtl_r14"
MUTANTS = {
    # the SPI state codes renumbered with a gap: OVF moved from 10 to 11 (10 left unused, e.g. reserved for a state).
    # The RTL's illegal-value test `st > S_OVF` then misses the unused value 10 (NFR-05: FRAME_ERR at CS_N rising),
    # and tb_top_r14 injects the hard-coded values 11..15 (11 is now OVF, a legal state that also gives FRAME_ERR)
    "hc_spi_ovf_code_11": [
        (f"{R14}/eeg_spi_slave.sv", "                           S_OVF = 4'd10;", "                           S_OVF = 4'd11;")],
}
