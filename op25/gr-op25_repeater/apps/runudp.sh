#! /bin/sh

t="-T 900.tsv"
sr="-S 120000"
v="-v 255"

python3 rx.py --args "udp:127.0.0.1:25252" -f 924975000 $sr -q 0 -D fsk4 -P "datascope" -V -w -v 255 $t $v 2> stderr.2
