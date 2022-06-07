#! /bin/bash

srcs=`find lib include -name '*.c' -o -name '*.h' -o -name '*.cc'`
files=`grep -l 'boost.*shared_ptr' $srcs`

dir=`pwd`

for f in $files; do
	echo editing file $f in $dir
	sed -i 's%boost/shared_ptr.hpp%memory%' $f
	sed -i 's%boost::shared_ptr%std::shared_ptr%' $f
done
