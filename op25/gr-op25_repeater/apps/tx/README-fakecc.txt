
Generating and transmitting a fake trunking control channel
===========================================================

1. After editing, run generate-tsbks.py which should generate
a file named "p25.out".

2. The tool generates the file packed form; it must be unpacked
       ./unpack.py -i p25.out -o sym-cc925.dat

3. The unpacked file must be referenced in the json cfg file:
              .
              .
              .
      "source": "symbols:sym-cc925.dat",
              .
              .
              .

NOTE: in generate_tsbks.py, keys starting with "iden_up"
are used to define a channel band plan with bandwidth(bw),
channel spacing, and starting frequency in Hz; TX offset is in 
MHz.

NOTE: with rx.py and multi_tx.py in tandem using the udp option,
the center frequency must be set in the rx.py trunking TSV
file equal to the device frequency in the multi_tx config.

As always, the control channel and voice channel frequencies
must fall inside the band defined by the center freqency and 
sampling rate.
