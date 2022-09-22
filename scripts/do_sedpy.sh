#! /bin/sh

me=$0

py=`find . -type f -name '*.py' | grep -v doxy`

files=`grep -l 'filter\.firdes\.WIN_' $py`
for f in $files; do
	echo $me editing $f
	sed -i 's/filter\.firdes\.WIN_/fft.window.WIN_/' $f
done

files=`grep -l 'gr\.msg_queue' $py`
for f in $files; do
	echo $me editing $f
	sed -i 's/gr\.msg_queue/op25.msg_queue/' $f
done

files=`grep -l 'gr\.message' $py`
for f in $files; do
	echo $me editing $f
	sed -i 's/gr\.message/op25.message/' $f
done
