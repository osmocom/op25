/* -*- c++ -*- */
/*
 * Copyright 2005,2013 Free Software Foundation, Inc.
 *
 * This file is part of GNU Radio
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 */

#ifndef INCLUDED_OP25_MSG_HANDLER_H
#define INCLUDED_OP25_MSG_HANDLER_H

#include <op25/api.h>
#include <op25/message.h>

namespace gr {
namespace op25 {

class msg_handler;
typedef std::shared_ptr<msg_handler> msg_handler_sptr;

/*!
 * \brief abstract class of message handlers
 * \ingroup base
 */
class OP25_API msg_handler
{
public:
    virtual ~msg_handler();

    //! handle \p msg
    virtual void handle(message::sptr msg) = 0;
};

} /* namespace op25 */
} /* namespace gr */

#endif /* INCLUDED_OP25_MSG_HANDLER_H */
