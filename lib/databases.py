#! /usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division)

from collections import MutableSet
import multiprocessing.dummy as threading
import json

from lib import constants as const
from lib import utils
from lib import mediatypes


class MediaDatabase(object):
    def __init__(self, mediaclass, name, retain_order=False):
        self.lock = threading.Lock()
        self.backend = set() if retain_order is False else OrderedSet()
        self.mediaclass = mediaclass
        self.mediatype = mediaclass.mediatype
        self.name = name
        self.filepath = utils.os_join(const.userdatafolder, "%s.json" % self.name)
        self.edited = False
        self.loaded = False

    def load(self):
        try:
            with open(self.filepath, 'r') as jf:
                stored = json.load(jf)
        except IOError:
            stored = []
        for urlid, title in stored:
            media_obj = self.mediaclass(urlid=urlid, title=title)
            self.backend.add(media_obj)
        self.loaded = True

    def commit(self):
        with open(self.filepath, 'w') as jf:
            json.dump([(item.urlid, item.title) for item in self], jf, indent=2)

    def add(self, item):
        with self.lock:
            self.backend.add(item)
            self.edited = True

    def upsert(self, item):
        '''update or insert:
        insert if item not in database.
        if item is in database and retain_order == true, move item to end of list'''
        with self.lock:
            self.backend.discard(item)
            self.backend.add(item)
            self.edited = True

    def remove(self, item):
        with self.lock:
            self.backend.remove(item)
            self.edited = True

    def __repr__(self):
        return repr(self.backend)

    def __contains__(self, key):
        return key in self.backend

    def __iter__(self):
        for item in self.backend:
            yield item

    def __and__(self, other):
        return self.backend.__and__(set(other))

    def __rand__(self, other):
        return self.backend.__rand__(set(other))

    def __or__(self, other):
        return self.backend.__or__(set(other))

    def __ror__(self, other):
        return self.backend.__ror__(set(other))

    def __sub__(self, other):
        return self.backend.__sub__(set(other))

    def __rsub__(self, other):
        return self.backend.__rsub__(set(other))


# https://code.activestate.com/recipes/576694/
class OrderedSet(MutableSet):

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


stored_movies = MediaDatabase(mediaclass=mediatypes.ScrapedMovie, name='movies')
excluded_movies = MediaDatabase(mediaclass=mediatypes.ScrapedMovie, name='excluded movies')
stored_shows = MediaDatabase(mediaclass=mediatypes.ScrapedShow, name='shows', retain_order=True)
excluded_shows = MediaDatabase(mediaclass=mediatypes.ScrapedShow, name='excluded shows')
prioritized_shows = MediaDatabase(mediaclass=mediatypes.ScrapedShow, name='prioritized shows')
