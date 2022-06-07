#! /bin/bash

me=$0
f=$1

echo "$me processing $f"

sed -i -f - $f << EOF
/Set the version information here/i\
###############################################################\n\
# Determine where to install python libs\n\
###############################################################\n\
execute_process(COMMAND python3 -c "\n\
import os\n\
import sys\n\
pfx = '/usr/local'\n\
path=os.path.join(pfx, 'lib', 'python%d.%d' % sys.version_info[:2], 'dist-packages')\n\
if os.path.isdir(path) and path in sys.path:\n\
	print(path)\n\
	sys.exit(0)\n\
p=[path for path in sys.path if path.startswith(pfx)][0]\n\
print(p)\n\
" OUTPUT_VARIABLE OP25_PYTHON_DIR OUTPUT_STRIP_TRAILING_WHITESPACE\n\
)\n\
MESSAGE(STATUS "OP25_PYTHON_DIR has been set to \\\"\${OP25_PYTHON_DIR}\\\".")\n\

EOF
