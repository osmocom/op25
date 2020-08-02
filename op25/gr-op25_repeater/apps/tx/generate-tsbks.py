#! /usr/bin/python

from p25craft import make_fakecc_tsdu

# should generate file p25.out

if __name__ == '__main__':
	params = {
		'wacn' : 0xbee00,
		'system_id': 0x290,
		'cc_freq': 925000000,
		'vc_freq': 924900000,
		'nac': 0x293,
		'subsystem_id': 1,
		'site_id': 1,
		'iden_up_bw' : 12500,
		'iden_up_tx_offset' : 25,	# MHz
		'iden_up_spacing' : 12500,
		'iden_up_frequency' : 902012500}
	make_fakecc_tsdu(params)
