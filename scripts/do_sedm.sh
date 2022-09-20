#! /bin/bash

me=$0
srcs=`find lib include -name '*.c' -o -name '*.h' -o -name '*.cc'`
dir=`pwd`

files=`grep -l -e 'gr::message' -e 'gr::msg_queue' $srcs`
for f in $files; do
	echo $me editing file $f in $dir
	sed -i 's%gr::msg_queue%gr::op25::msg_queue%g' $f
	sed -i 's%gr::message%gr::op25::message%g' $f
done

files=`grep -l -e 'include.*gnuradio/message' -e 'include.*gnuradio/msg_queue' $srcs`
for f in $files; do
	echo $me editing file $f in $dir
	sed -i 's%gnuradio/msg_queue%op25/msg_queue%g' $f
	sed -i 's%gnuradio/message%op25/message%g' $f
done
