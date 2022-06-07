#! /bin/bash

me=$0
dir=$1
files=`grep -lr GR_PYTHON_DIR ${dir}`

echo "$me processing directory $dir, files $files"

for f in $files; do
	echo editing $f
	sed -i '/GR_PYTHON_DIR/s%GR_PYTHON_DIR}/gnuradio%OP25_PYTHON_DIR}%' $f
done

