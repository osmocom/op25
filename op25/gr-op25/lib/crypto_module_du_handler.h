#ifndef INCLUDED_CRYPTO_MODULE_DU_HANDLER_H
#define INCLUDED_CRYPTO_MODULE_DU_HANDLER_H

#include <boost/shared_ptr.hpp>

#include "data_unit_handler.h"
#include "crypto.h"

class crypto_module_du_handler : public data_unit_handler
{
public:
	crypto_module_du_handler(data_unit_handler_sptr next, crypto_module::sptr crypto_mod);
public:
	typedef boost::shared_ptr<class crypto_module_du_handler> sptr;
public:
	virtual void handle(data_unit_sptr du);
private:
	crypto_module::sptr d_crypto_mod;
};

#endif //INCLUDED_CRYPTO_MODULE_HANDLER_H
