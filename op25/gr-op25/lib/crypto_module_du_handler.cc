#include "crypto_module_du_handler.h"

#include "abstract_data_unit.h"

#include <boost/format.hpp>
#include <sstream>
#include <stdio.h>

crypto_module_du_handler::crypto_module_du_handler(data_unit_handler_sptr next, crypto_module::sptr crypto_mod)
	: data_unit_handler(next)
	, d_crypto_mod(crypto_mod)
{
}

void
crypto_module_du_handler::handle(data_unit_sptr du)
{
	if (!d_crypto_mod)
	{
		data_unit_handler::handle(du);
		return;
	}

	crypto_state_provider* p = dynamic_cast<crypto_state_provider*>(du.get());
	if (p == NULL)
	{
		data_unit_handler::handle(du);
		return;
	}

	CryptoState state = p->crypto_state();

	///////////////////////////////////

	if (d_crypto_mod->logging_enabled())
	{
		std::string duid_str("?");
		abstract_data_unit* adu = dynamic_cast<abstract_data_unit*>(du.get());
		if (adu)
			duid_str = adu->duid_str();

		std::stringstream ss;
		for (size_t n = 0; n < state.mi.size(); ++n)
			ss << (boost::format("%02x") % (int)state.mi[n]);

		fprintf(stderr, "%s:\tAlgID: 0x%02x, KID: 0x%04x, MI: %s\n", duid_str.c_str(), state.algid, state.kid, ss.str().c_str());
	}

	///////////////////////////////////

	crypto_algorithm::sptr algorithm = d_crypto_mod->algorithm(state.algid);
	if (!algorithm)
	{
		data_unit_handler::handle(du);
		return;
	}

	// TODO: Could do key management & selection here with 'state.kid'
	// Assuming we're only using one key (ignoring 'kid')

	algorithm->update(state);

	data_unit_handler::handle(du);
}
