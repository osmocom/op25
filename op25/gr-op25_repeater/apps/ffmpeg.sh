#! /bin/sh

# Copyright (c) 2020 OP25
# 
# This file is part of OP25 and part of GNU Radio
# 
# OP25 is free software; you can redistribute it and/or modify it
# under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
# 
# OP25 is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
# or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
# License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with OP25; see the file COPYING. If not, write to the Free
# Software Foundation, Inc., 51 Franklin Street, Boston, MA
# 02110-1301, USA.

#
# this script should not be run directly - run ffmpeg.liq instead
#
# requires ffmpeg configured with --enable-libx264
#

ffmpeg		\
	-ar 8000		\
	-ac 1			\
	-acodec pcm_s16le	\
	-f s16le	\
	-i pipe:0		\
	-f image2		\
	-loop 1			\
	-i ../www/images/status.png	\
	-vcodec libx264		\
	-pix_fmt yuv420p	\
	-f flv		\
	-acodec aac	\
	-b:a 48k	\
	rtmp://localhost/live/stream
