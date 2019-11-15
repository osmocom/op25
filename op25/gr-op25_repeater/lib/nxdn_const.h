//
// NXDN Encoder (C) Copyright 2019 Max H. Parke KA1RBI
// thx gr-ysf fr_vch_decoder_bb_impl.cc * Copyright 2015 Mathias Weyland *
// 
// This file is part of OP25
// 
// OP25 is free software; you can redistribute it and/or modify it
// under the terms of the GNU General Public License as published by
// the Free Software Foundation; either version 3, or (at your option)
// any later version.
// 
// OP25 is distributed in the hope that it will be useful, but WITHOUT
// ANY WARRANTY; without even the implied warranty of MERCHANTABILITY
// or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public
// License for more details.
// 
// You should have received a copy of the GNU General Public License
// along with OP25; see the file COPYING. If not, write to the Free
// Software Foundation, Inc., 51 Franklin Street, Boston, MA
// 02110-1301, USA.

#ifndef INCLUDED_NXDN_CONST_H
#define INCLUDED_NXDN_CONST_H

#include <stdint.h>

/* postamble + frame sync (FS) */
static const uint64_t NXDN_POSTFS_SYNC_MAGIC = 0x5775fdcdf59LL;
/* frame sync + scrambled rendition of LICH=0x6e (a halfrate voice 4V) */
static const uint64_t NXDN_FS6E_SYNC_MAGIC   = 0xcdf5975d7LL;

#endif /* INCLUDED_NXDN_CONST_H */
