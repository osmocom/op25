#ifndef INCLUDED_CRYPTO_H
#define INCLUDED_CRYPTO_H

#include <stdint.h>
#include <vector>
#include <map>
#include <boost/shared_ptr.hpp>

static const int MESSAGE_INDICATOR_LENGTH = 9;

class CryptoState
{
public:
	CryptoState() :
	kid(0), algid(0), mi(MESSAGE_INDICATOR_LENGTH)
	{ }
public:
	std::vector<uint8_t> mi;
    uint16_t kid;
	uint8_t algid;
};

class crypto_state_provider
{
public:
	virtual struct CryptoState crypto_state() const=0;
};

class crypto_algorithm
{
public:
	typedef boost::shared_ptr<class crypto_algorithm> sptr;
	typedef std::vector<uint8_t> key_type;
	typedef std::map<uint16_t, key_type > key_map_type;
	typedef uint8_t type_id;
	enum
	{
		NONE	= 0x80,
		DES_OFB	= 0x81,
	};
public:
	virtual const type_id id() const=0;
	virtual bool set_key(const key_type& key)=0;
	virtual void set_key_map(const key_map_type& key_map)=0;
	virtual bool update(const struct CryptoState& state)=0;
	virtual uint64_t generate(size_t n_bits)=0;	// Can request up to 64 bits of key stream at one time
	virtual void set_logging(bool on)=0;
};

class crypto_module
{
public:
	typedef boost::shared_ptr<class crypto_module> sptr;
public:
	crypto_module(bool verbose = false);
public:
	virtual crypto_algorithm::sptr algorithm(crypto_algorithm::type_id algid);
	virtual void set_key(const crypto_algorithm::key_type& key);
	virtual void set_key_map(const crypto_algorithm::key_map_type& keys);
	virtual void set_logging(bool on = true);
protected:
	crypto_algorithm::sptr d_current_algorithm;
	crypto_algorithm::key_type d_persistent_key;
	crypto_algorithm::key_map_type d_persistent_key_map;
	bool d_verbose;
public:
	virtual crypto_algorithm::sptr current_algorithm() const
	{ return d_current_algorithm; }
	virtual bool logging_enabled() const
	{ return d_verbose; }
};

#endif // INCLUDED_CRYPTO_H
