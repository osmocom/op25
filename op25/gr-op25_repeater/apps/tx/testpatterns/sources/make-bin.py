#! /usr/bin/env python

"""
utility program to make binary symbol files

reads source file (stdin); writes binary file to stdout

"""

import sys

s = sys.stdin.read()
s= s.replace(' ', '')
s= s.replace('\n', '')
s = s.strip()

dibits = ''

while s:
	s0 = int(s[0], 16)
	s = s[1:]
	dibits += chr(s0>>2)
	dibits += chr(s0&3)

sys.stdout.write(dibits)
