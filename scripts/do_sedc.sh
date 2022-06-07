#! /bin/bash

me=$0
f=$1
echo "$me editing file $f"
sed -i '/^find_package(Gnuradio .*REQUIRED)/s/)/ COMPONENTS blocks fft filter)/' $f
