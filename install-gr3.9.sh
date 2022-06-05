#! /bin/bash

# op25 install script for debian based systems
# including ubuntu 14/16 and raspbian
#
# *** this script for gnuradio 3.9 and 3.10 ***

TREE_DIR="$PWD/src"	# directory in which our gr3.9 tree will be built

if [ ! -d op25/gr-op25 ]; then
	echo ====== error, op25 top level directories not found
	echo ====== you must change to the op25 top level directory
	echo ====== before running this script
	exit
fi

sudo apt-get update
sudo apt-get build-dep gnuradio
sudo apt-get install gnuradio gnuradio-dev gr-osmosdr librtlsdr-dev libuhd-dev  libhackrf-dev libitpp-dev libpcap-dev cmake git swig build-essential pkg-config doxygen python3-numpy python3-waitress python3-requests python3-pip pybind11-dev clang-format libsndfile1-dev

# setup and populate gr3.9 src tree
echo
echo " = = = = = = = generating source tree for gr3.9, this could take a while = = = = = = ="
echo
python3 add_gr3.9.py $PWD $TREE_DIR
if [ ! -d $TREE_DIR ]; then
	echo ==== Error, directory $TREE_DIR creation failed, exiting
	exit 1
fi

cd $TREE_DIR

mkdir build
cd build
cmake ../op25/gr-op25
make
sudo make install
sudo ldconfig
cd ../

mkdir build_repeater
cd build_repeater
cmake ../op25/gr-op25_repeater
make
sudo make install
sudo ldconfig
cd ../

echo ====== 
echo ====== NOTICE 
echo ====== 
echo ====== The gnuplot package is not installed by default here,
echo ====== as its installation requires numerous prerequisite packages
echo ====== that you may not want to install.
echo ====== 
echo ====== In order to do plotting in rx.py using the \-P option
echo ====== you must install gnuplot, e.g., manually as follows:
echo ====== 
echo ====== sudo apt-get install gnuplot-x11
echo ====== 


