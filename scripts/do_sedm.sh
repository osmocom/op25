#! /bin/bash

me=$0
dir=$1
files=`grep -l msg_queue ${dir}/*.h`

echo "$me processing directory $dir, files $files"

for f in $files; do
	echo processing $f
	sed -i -f - $f << EOF
/include.*block.h/a\
#include <gnuradio/msg_queue.h>
EOF
done
