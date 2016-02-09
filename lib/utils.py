#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import division
from __future__ import absolute_import
from functools import wraps
import os

from . import constants as const


def byteify(input):
    if isinstance(input, dict):
        return dict((byteify(key), byteify(value)) for key, value in input.iteritems())
    elif isinstance(input, list):
        return [byteify(element) for element in input]
    elif isinstance(input, tuple):
        return [byteify(element) for element in list(input)]
    elif isinstance(input, unicode):
        return input.encode('utf-8')
    else:
        return input


def debyteify(input):
    if isinstance(input, dict):
        return dict((debyteify(key), debyteify(value)) for key, value in input.iteritems())
    elif isinstance(input, list):
        return [debyteify(element) for element in input]
    elif isinstance(input, tuple):
        return [debyteify(element) for element in list(input)]
    elif isinstance(input, str):
        return input.decode('utf-8')
    else:
        return input


def stringtofile(string):
    string = string.replace('<', '')
    string = string.replace('>', '')
    string = string.replace(':', '')
    string = string.replace('"', '')
    string = string.replace('/', '')
    string = string.replace('\\', '')
    string = string.replace('|', '')
    string = string.replace('?', '')
    string = string.replace('*', '')
    string = string.replace('...', '')
    string = string[:90]
    return string


def wrap_unicode(func):
    '''encodes input from unicode to utf-8, and decodes output from utf-8 to unicode'''
    @wraps(func)
    def wrapper(*args, **kwargs):
        utf_args, utf_kwargs = byteify((args, kwargs))
        output = func(*utf_args, **utf_kwargs)
        unic_output = debyteify(output)
        return unic_output
    return wrapper


def os_join(*args):
    path = os.path.join(*args)
    if const.os == "win":
        return path
    else:
        return path.encode("utf-8")

uni_join = os.path.join


def parameters_string_to_dict(parameters):
    paramDict = {}
    if parameters:
        paramPairs = parameters[1:].split("&")
        for paramsPair in paramPairs:
            paramSplits = paramsPair.split('=')
            if (len(paramSplits)) == 2:
                paramDict[paramSplits[0]] = paramSplits[1]
    return paramDict
