#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import collections
import multiprocessing.dummy as threading
import json
import os
import xbmc

from . utils import os_join
from . import constants as const

# https://code.activestate.com/recipes/576694/
class OrderedSet(collections.MutableSet):

    def __init__(self, iterable=None):
        self.end = end = []
        end += [None, end, end]         # sentinel node for doubly linked list
        self.map = {}                   # key --> [key, prev, next]
        if iterable is not None:
            self |= iterable

    def __len__(self):
        return len(self.map)

    def __contains__(self, key):
        return key in self.map

    def add(self, key):
        if key not in self.map:
            end = self.end
            curr = end[1]
            curr[2] = end[1] = self.map[key] = [key, curr, end]

    def discard(self, key):
        if key in self.map:
            key, prev, next = self.map.pop(key)
            prev[2] = next
            next[1] = prev

    def __iter__(self):
        end = self.end
        curr = end[2]
        while curr is not end:
            yield curr[0]
            curr = curr[2]

    def __reversed__(self):
        end = self.end
        curr = end[1]
        while curr is not end:
            yield curr[0]
            curr = curr[1]

    def pop(self, last=True):
        if not self:
            raise KeyError('set is empty')
        key = self.end[1][0] if last else self.end[2][0]
        self.discard(key)
        return key

    def __repr__(self):
        if not self:
            return '%s()' % (self.__class__.__name__,)
        return '%s(%r)' % (self.__class__.__name__, list(self))

    def __eq__(self, other):
        if isinstance(other, OrderedSet):
            return len(self) == len(other) and list(self) == list(other)
        return set(self) == set(other)


class BaseDatabase(object):
    def __init__(self, mediaclass, name):
        self._lock = threading.Lock()
        self.mediaclass = mediaclass
        self.name = name
        self.filepath = os_join(const.userdatafolder, "%s.json" % self.name)
        self.edited = False
        self.load()

    def load(self):
        xbmc.log(self.filepath)
        try:
            with open(self.filepath, 'r') as jf:
                stored = json.load(jf)
                for urlid, title in stored:
                    media_obj = self.mediaclass(urlid, title)
                    self.add(media_obj)
        except IOError:
            pass

    def commit(self):
        if self.edited:
            with open(self.filepath, 'w') as jf:
                json.dump([(item.urlid, item.title) for item in self], jf, indent=2)

    def insert(self, item):
        with self.lock:
            self.add(item)
            self.edited = True

    def delete(self, item):
        with self.lock:
            self.remove(item)
            self.edited = True


class Database(set, BaseDatabase):
    def __init__(self, mediaclass, name):
        set.__init__(self)
        BaseDatabase.__init__(self, mediaclass, name)


class OrderedDatabase(OrderedSet, BaseDatabase):
    def __init__(self, mediaclass, name):
        OrderedSet.__init__(self)
        BaseDatabase.__init__(self, mediaclass, name)

    def upsert(self, item):
        '''update or insert:
        insert if item not in database.
        if item is in database and retain_order == true, move item to end of list'''
        with self.lock:
            self.discard(item)
            self.add(item)
            self.edited = True

