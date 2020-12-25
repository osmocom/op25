#!/usr/bin/env python

#
# (c) Copyright 2020, OP25
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

""" generate named image file consisting of multi-line text """

from PIL  import Image, ImageDraw, ImageFont
import os

_TTF_FILE = '/usr/share/fonts/truetype/freefont/FreeSerif.ttf'

def create_image(textlist=["Blank"], imgfile="test.png", bgcolor='red', fgcolor='black', windowsize=(400,300)):
    global _TTF_FILE
    width=windowsize[0]
    height=windowsize[1]

    margin      = 4
    if not os.access(_TTF_FILE, os.R_OK):
        font        = ImageFont.load_default()
    else:
        font        = ImageFont.truetype(_TTF_FILE, 16)
    img        = Image.new('RGB', (width, height), bgcolor)
    draw        = ImageDraw.Draw(img)
    cursor = 0
    for line in textlist:
        w,h         = draw.textsize(line, font)
        # TODO: overwidth check needed?
        if cursor+h >= height:
            break
        draw.text((margin, cursor), line,'black',font)
        cursor += h + margin // 2

    img.save(imgfile)

if __name__ == '__main__':
    s = []
    s.append('Starting...')

    create_image(textlist=s, bgcolor='#c0c0c0')
