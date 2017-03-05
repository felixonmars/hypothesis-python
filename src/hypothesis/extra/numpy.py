# coding=utf-8
#
# This file is part of Hypothesis, which may be found at
# https://github.com/HypothesisWorks/hypothesis-python
#
# Most of this work is copyright (C) 2013-2016 David R. MacIver
# (david@drmaciver.com), but it contains contributions by others. See
# CONTRIBUTING.rst for a full list of people who may hold copyright, and
# consult the git log if you need to determine who owns an individual
# contribution.
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at http://mozilla.org/MPL/2.0/.
#
# END HEADER

from __future__ import division, print_function, absolute_import

import functools

import numpy as np

import hypothesis.strategies as st
from hypothesis.errors import InvalidArgument
from hypothesis.searchstrategy import SearchStrategy
from hypothesis.internal.compat import hrange, text_type, binary_type


def from_dtype(dtype):
    if dtype.kind == u'b':
        result = st.booleans()
    elif dtype.kind == u'f':
        result = st.floats()
    elif dtype.kind == u'c':
        result = st.complex_numbers()
    elif dtype.kind in (u'S', u'a', u'V'):
        result = st.binary()
    elif dtype.kind == u'u':
        result = st.integers(
            min_value=0, max_value=1 << (4 * dtype.itemsize) - 1)
    elif dtype.kind == u'i':
        min_integer = -1 << (4 * dtype.itemsize - 1)
        result = st.integers(min_value=min_integer, max_value=-min_integer - 1)
    elif dtype.kind == u'U':
        result = st.text()
    else:
        raise InvalidArgument(u'No strategy inference for {}'.format(dtype))
    return result.map(dtype.type)


def check_argument(condition, fail_message, *f_args, **f_kwargs):
    if not condition:
        raise InvalidArgument(fail_message.format(*f_args, **f_kwargs))


def order_check(name, floor, small, large):
    if floor is None:
        floor = -np.inf
    if floor > small > large:
        check_argument(u'min_{name} was {}, must be at least {} and not more '
                       u'than max_{name} (was {})', small, floor, large,
                       name=name, condition=False)


class ArrayStrategy(SearchStrategy):

    def __init__(self, element_strategy, shape, dtype):
        self.shape = tuple(shape)
        assert shape
        self.array_size = np.prod(shape)
        self.dtype = dtype
        self.element_strategy = element_strategy

    def do_draw(self, data):
        result = np.empty(dtype=self.dtype, shape=self.array_size)
        for i in hrange(self.array_size):
            result[i] = self.element_strategy.do_draw(data)
        return result.reshape(self.shape)


def is_scalar(spec):
    return spec in (
        int, bool, text_type, binary_type, float, complex
    )


def arrays(dtype, shape, elements=None):
    if not isinstance(dtype, np.dtype):
        dtype = np.dtype(dtype)
    if elements is None:
        elements = from_dtype(dtype)
    if isinstance(shape, int):
        shape = (shape,)
    shape = tuple(shape)
    if not shape:
        if dtype.kind != u'O':
            return elements
    else:
        return ArrayStrategy(
            shape=shape,
            dtype=dtype,
            element_strategy=elements
        )


@st.defines_strategy
def array_shapes(min_dims=1, max_dims=3, min_side=1, max_side=10):
    """Return a strategy for array shapes (tuples of int >= 1)."""
    order_check('dims', 1, min_dims, max_dims)
    order_check('side', 1, min_side, max_side)
    return st.lists(st.integers(min_side, max_side),
                    min_size=min_dims, max_size=max_dims).map(tuple)


@st.defines_strategy
def scalar_dtypes():
    """Return a strategy that can return any non-flexible scalar dtype."""
    return st.one_of(boolean_dtypes(),
                     integer_dtypes(), unsigned_integer_dtypes(),
                     floating_dtypes(), complex_number_dtypes(),
                     )


def defines_dtype_strategy(strat):
    @st.defines_strategy
    @functools.wraps(strat)
    def inner(*args, **kwargs):
        return strat(*args, **kwargs).map(np.dtype)
    return inner


@defines_dtype_strategy
def boolean_dtypes():
    return st.just('?')


def dtype_factory(kind, sizes, valid_sizes, endianness):
    # Utility function, shared logic for most integer and string types
    valid_endian = ('?', '<', '=', '>')
    check_argument(endianness in valid_endian,
                   u'Unknown endianness: was {}, must be in {}', valid_endian)
    if valid_sizes is not None:
        if isinstance(sizes, int):
            sizes = (sizes,)
        check_argument(sizes, 'Dtype must have at least one possible size.')
        check_argument(all(s in valid_sizes for s in sizes),
                       u'Invalid sizes: was {} must be an item or sequence '
                       u'in {}', sizes, valid_sizes)
        if all(isinstance(s, int) for s in sizes):
            sizes = sorted(set(s // 8 for s in sizes))
    strat = st.sampled_from(sizes)
    if '{}' not in kind:
        kind += '{}'
    if endianness == '?':
        return strat.map(('<' + kind).format) | strat.map(('>' + kind).format)
    return strat.map((endianness + kind).format)


@defines_dtype_strategy
def unsigned_integer_dtypes(endianness='?', sizes=(8, 16, 32, 64)):
    """Return a strategy for unsigned integer dtypes.

    endianness may be ``<`` for little-endian, ``>`` for big-endian,
    ``=`` for native byte order, or ``?`` to allow either byte order.
    This argument only applies to dtypes of more than one byte.

    sizes must be a collection of integer sizes in bits.  The default
    (8, 16, 32, 64) covers the full range of sizes.

    """
    return dtype_factory('u', sizes, (8, 16, 32, 64), endianness)


@defines_dtype_strategy
def integer_dtypes(endianness='?', sizes=(8, 16, 32, 64)):
    """Return a strategy for signed integer dtypes.

    endianness and sizes are treated as for `unsigned_integer_dtypes`.

    """
    return dtype_factory('i', sizes, (8, 16, 32, 64), endianness)


@defines_dtype_strategy
def floating_dtypes(endianness='?', sizes=(16, 32, 64)):
    """Return a strategy for floating-point dtypes.

    sizes is the size in bits of floating-point number.  Some machines support
    96- or 128-bit floats, but these are not generated by default.

    Larger floats (96 and 128 bit real parts) are not supported on all
    platforms and therefore disabled by default.  To generate these dtypes,
    include these values in the sizes argument.

    """
    return dtype_factory('f', sizes, (16, 32, 64, 96, 128), endianness)


@defines_dtype_strategy
def complex_number_dtypes(endianness='?', sizes=(64, 128)):
    """Return a strategy complex-number dtypes.

    sizes is the total size in bits of a complex number, which consists
    of two floats.  Complex halfs (a 16-bit real part) are not supported
    by numpy and will not be generated by this strategy.

    """
    return dtype_factory('c', sizes, (64, 128, 192, 256), endianness)
