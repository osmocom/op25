cmake_minimum_required(VERSION 2.6)
project(gr-op25 CXX C)

set(CMAKE_BUILD_TYPE Debug)
set(CMAKE_CXX_FLAGS "-std=c++11")

execute_process(COMMAND python3 -c "
import os
import sys
from distutils import sysconfig
pfx = '/usr/local'
m1 = os.path.join('lib', 'python' + sys.version[:3], 'dist-packages')
m2 = sysconfig.get_python_lib(plat_specific=True, prefix='')
f1 = os.path.join(pfx, m1)
f2 = os.path.join(pfx, m2)
ok2 = f2 in sys.path
if ok2:
	print(m2)
else:
	print(m1)
" OUTPUT_VARIABLE OP25_PYTHON_DIR OUTPUT_STRIP_TRAILING_WHITESPACE
)
MESSAGE(STATUS "OP25_PYTHON_DIR has been set to \"${OP25_PYTHON_DIR}\".")

add_subdirectory(op25/gr-op25)
add_subdirectory(op25/gr-op25_repeater)

########################################################################
# Create uninstall target
########################################################################
configure_file(
    ${CMAKE_SOURCE_DIR}/cmake/cmake_uninstall.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/cmake_uninstall.cmake
@ONLY)

add_custom_target(uninstall
    ${CMAKE_COMMAND} -P ${CMAKE_CURRENT_BINARY_DIR}/cmake_uninstall.cmake
)
