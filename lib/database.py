#! /usr/bin/env python
# -*- coding: utf-8 -*-
from collections import OrderedDict
import multiprocessing.dummy as threading
import json

from . utils import os_join
from . import constants as const


class LastUpdatedOrderedDict(OrderedDict):
    '''Store items in the order the keys were last added
    from https://docs.python.org/2/library/collections.html#collections.OrderedDict'''
    def __setitem__(self, key, value):
        if key in self:
            del self[key]
        OrderedDict.__setitem__(self, key, value)


class MediaDatabase(object):
    def __init__(self, name, return_as, store_as=dict):
        self.name = name
        self.lock = threading.Lock()
        self.return_as = return_as
        self.filepath = os_join(const.userdatafolder, ".".join([self.name, "json"]))
        try:
            with open(self.filepath, 'r') as jf:
                self.database = store_as(json.load(jf))
        except IOError:
            self.database = store_as()
        self.edited = False
        self.initial_ids = set(self.database)
        self.initial_all = [self.return_as(ntflxid, title) for ntflxid, title in self.database.items()]

    def savetofile(self):
        if self.edited:
            with open(self.filepath, 'w') as jf:
                json.dump(self.database.items(), jf, indent=2)

    def upsert(self, ntflxid, title):
        '''update or insert:
        insert if id not in database.
        if id is in database and store_as=LastUpdatedOrderedDict, put id and title at end of database'''
        with self.lock:
            self.database[ntflxid] = title
            self.edited = True

    def remove(self, ntflxid):
        with self.lock:
            del self.database[ntflxid]
            self.edited = True

    @property
    def all(self):
        if not self.edited:
            return self.initial_all
        else:
            return [self.return_as(ntflxid, title) for ntflxid, title in self.database.items()]

    @property
    def ids(self):
        if not self.edited:
            return self.initial_ids
        else:
            return set(self.database)

