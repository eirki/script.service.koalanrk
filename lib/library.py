#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import multiprocessing.dummy as threading
import os
import re
from functools import partial
import traceback
import types
import json
from bs4 import BeautifulSoup
from operator import attrgetter

from . utils import (os_join, uni_join, stringtofile)
from . import scraper
from . import constants as const
from . import database
from .xbmcwrappers import (rpc, log, ScanMonitor, settings, ProgressDialog, dialogs)


def select_mediaitem(mediadb):
    sorted_media = sorted(mediadb.all, key=attrgetter("title"))
    titles = [media.title for media in sorted_media]
    call = dialogs.select(list=titles, heading='Select %s' % mediadb.name[:-1])
    return sorted_media[call] if call != -1 else None


def prioritize():
    sorted_shows = sorted(Show.db.all, key=attrgetter("title"))
    titles = []
    for show in sorted_shows:
        if show.urlid in Show.db_prioritized.ids:
            titles.append("[Prioritized] %s" % show.title)
        else:
            titles.append(show.title)
    while True:
        call = dialogs.select('Select prioritized shows', titles)
        if call == -1:
            break
        show = sorted_shows[call]
        if show.urlid not in Show.db_prioritized.ids:
            Show.db_prioritized.upsert(show.urlid, show.title)
            titles[call] = "[Prioritized] %s" % show.title
        else:
            Show.db_prioritized.remove(show.urlid)
            titles[call] = show.title


def main(action):
    stored_movies = database.MediaDatabase('movies', mediatype=Movie)
    excluded_movies = database.MediaDatabase('excluded movies', mediatype=Movie)
    stored_shows = database.MediaDatabase('shows', mediatype=Show, retain_order=True)
    excluded_shows = database.MediaDatabase('excluded shows', mediatype=Show)
    prioritized_shows = database.MediaDatabase('prioritized shows', mediatype=Show)


    try:
        action_func()
    except:
        raise
    finally:
        stored_movies.savetofile()
        excluded_movies.savetofile()
        stored_shows.savetofile()
        excluded_shows.savetofile()
        prioritized_shows.savetofile()
