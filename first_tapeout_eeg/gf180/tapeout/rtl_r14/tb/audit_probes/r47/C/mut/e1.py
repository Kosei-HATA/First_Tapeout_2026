# SPI: the sample's CRC computed over the FIFO's live head (smp_word) instead of the word copied at the header
EDITS = [("eeg_spi_slave.sv", "default: tx_next = crc8_48(CRC_SMP_HDR, shadow);", "default: tx_next = crc8_48(CRC_SMP_HDR, smp_word);")]
