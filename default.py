#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import json
import subprocess
import sys
import os
from operator import itemgetter
import pickle
import xbmc
import xbmcgui
from collections import OrderedDict

from lib.utils import (settings, log, progress, dialogs, mkpath, monitor, const, wrap_unicode)

from lib import library
from lib import internet as nrk


class LastUpdatedOrderedDict(OrderedDict):
    '''Store items in the order the keys were last added
    from https://docs.python.org/2/library/collections.html#collections.OrderedDict'''

    def __setitem__(self, key, value):
        if key in self:
            del self[key]
        OrderedDict.__setitem__(self, key, value)


class MediaLists(object):
    instances = []

    def __init__(self, mediatype):
        self.mediatype = mediatype
        try:
            with open(mkpath(const.userdatafolder, "%slist" % self.mediatype), 'rb') as p:
                self.__dict__.update(pickle.load(p))
        except IOError:
            self.stored = LastUpdatedOrderedDict({})
            self.excluded = {}
            self.prioritized = set()
        MediaLists.instances.append(self)

    @classmethod
    def savetofile(cls):
        for inst in cls.instances:
            with open(mkpath(const.userdatafolder, "%slist" % inst.mediatype), 'wb') as p:
                pickle.dump(inst.__dict__, p)


class KoalaGlobals():
    @wrap_unicode
    def setglobal(self, id, value):
        if isinstance(value, (bool, int)):
            value = str(value).lower()
        xbmcgui.Window(10000).setProperty(id, value)

    @wrap_unicode
    def getglobal(self, id):
        value = xbmcgui.Window(10000).getProperty(id)
        if value in ["true", "false"]:
            value = value == "true"
        return value
koalaglobals = KoalaGlobals()


# Update actions
def check_watchlist(shows_stored, movies_stored, shows_excluded, movies_excluded):
    stored_show_ids = set(shows_stored)
    stored_movie_ids = set(movies_stored)
    excluded_ids = set(shows_excluded) | set(movies_excluded)
    results = nrk.get_watchlist(stored_show_ids, stored_movie_ids, excluded_ids)
    added_shows, unav_shows, added_movies, unav_movies = results

    progress.addsteps(2 * len(added_shows))
    progress.addsteps(2 * len(unav_shows))
    progress.addsteps(len(added_movies))
    progress.addsteps(len(unav_movies))

    for movieid in unav_movies:
        movietitle = movies_stored[movieid]
        library.delete_movie(movieid, movietitle)
        del movies_stored[movieid]

    library.create_movies(added_movies)
    monitor.update_video_library()
    for movieid, movietitle in added_movies:
        library.add_movie_to_kodi(movieid, movietitle)
        movies_stored.update({movieid: movietitle})

    for showid in unav_shows:
        showtitle = shows_stored[showid]
        library.delete_show(showid, showtitle)
        del shows_stored[showid]

    for showid, showtitle in added_shows:
        library.update_show(showid, showtitle)
        shows_stored.update({showid: showtitle})


def update_mult_shows(shows_stored, shows_prioritized, all=False):
    pri_and_stored = []
    n_shows = list(shows_stored)
    for showid in shows_stored:
        if showid in shows_prioritized:
            n_shows.remove(showid)
            pri_and_stored.append(showid)
    if not all and not settings["update_all_shows"]:
        n = settings["n_shows_to_update"]
        n_shows = n_shows[:n]

    progress.addsteps(2 * len(pri_and_stored + n_shows))
    for showid in pri_and_stored + n_shows:
        showtitle = shows_stored[showid]
        library.update_show(showid, showtitle)
        shows_stored.update({showid: showtitle})


def modify_single_medialement(Mediaobj, mediaid, mediatitle, mediatype, action):
    if mediatype == "show" and action == "update":
        progress.addsteps(1)
        library.update_show(mediaid, mediatitle)
    elif mediatype == "show" and action == "exclude":
        library.delete_show(mediaid, mediatitle)
    elif mediatype == "movie" and action == "exclude":
        library.delete_movie(mediaid, mediatitle)
    elif mediatype == "show" and action == "readd":
        progress.addsteps(1)
        library.update_show(mediaid, mediatitle)
    elif mediatype == "movie" and action == "readd":
        library.create_movies([(mediaid, mediatitle)], add=True)

    if action == "readd":
        del Mediaobj.excluded[mediaid]
    if action in ["update", "readd"]:
        Mediaobj.stored.update({mediaid: mediatitle})
    if action == "exclude":
        del Mediaobj.stored[mediaid]
        Mediaobj.excluded.update({mediaid: mediatitle})


def remove_readd_all(shows_stored, movies_stored):
    progress.addsteps(3 * (len(shows_stored)))
    progress.addsteps(2 * (len(movies_stored)))

    movies_stored_copy = movies_stored.items()
    shows_stored_copy = shows_stored.items()

    for movieid, movietitle in movies_stored.items():
        library.delete_movie(movieid, movietitle)
        del movies_stored[movieid]

    library.create_movies(movies_stored_copy)
    monitor.update_video_library()
    for movieid, movietitle in movies_stored_copy:
        library.add_movie_to_kodi(movieid, movietitle)
        movies_stored.update({movieid: movietitle})

    for showid, showtitle in shows_stored.items():
        library.delete_show(showid, showtitle)
        del shows_stored[showid]

    for showid, showtitle in shows_stored_copy:
        library.update_show(showid, showtitle)
        shows_stored.update({showid: showtitle})


# Settings actions
def refresh_settings():
    xbmc.executebuiltin('Dialog.Close(dialog)')
    xbmc.executebuiltin('ReloadSkin')
    xbmc.executebuiltin('Addon.OpenSettings(script.service.koalanrk)')


def prioritize_shows(shows_stored, shows_prioritized):
    sorted_shows = sorted(shows_stored.items(), key=itemgetter(1))
    showids, showtitles = zip(*sorted_shows)
    showtitles = list(showtitles)
    for i, showtitle in enumerate(showtitles):
        if showids[i] in shows_prioritized:
            showtitles[i] = "[Prioritized] "+showtitle

    while True:
        call = dialogs.select('Select prioritized shows', showtitles)
        if call == -1:
            break
        showid = showids[call]
        showtitle = showtitles[call]
        if showid not in shows_prioritized:
            showtitles[call] = "[Prioritized] "+showtitle
            shows_prioritized.add(showid)
        else:
            showtitles[call] = showtitle.replace("[Prioritized] ", "")
            shows_prioritized.remove(showid)
    xbmc.executebuiltin('Addon.OpenSettings(script.service.koalanrk)')
    id1 = 2
    xbmc.executebuiltin('SetFocus(%i)' % (id1 + 100))
    id2 = 4
    xbmc.executebuiltin('SetFocus(%i)' % (id2 + 200))


def configure_remote():
    try:
        with open(mkpath(const.userdatafolder, "remotemapping.json"), "r") as j:
            remotemapping = json.load(j)
    except IOError:
        remotemapping = {}
    buttonlist = ["Play", "Pause", "Stop", "Forward", "Rewind"]
    returnkeyscript = mkpath(const.ahkfolder, "return key.ahk")
    while True:
        optionlist = ["%s: %s" % (button, remotemapping.get(button)) for button in buttonlist]
        call = dialogs.select('Select function to edit', optionlist)
        if call == -1:
            break
        p = subprocess.Popen([const.ahkexe, returnkeyscript], stdout=subprocess.PIPE)
        dialogs.ok(heading="Input", line1="Please press intended %s button" % buttonlist[call])
        key = p.stdout.read()
        p.stdout.close()
        pressed = key.split("EndKey:")[-1] if "EndKey" in key else key.split(",")[0]
        remotemapping[buttonlist[call]] = pressed
    with open(mkpath(const.userdatafolder, "remotemapping.json"), "w") as j:
        json.dump(remotemapping, j)
    xbmc.executebuiltin('Addon.OpenSettings(script.service.koalanrk)')
    id1 = 1
    xbmc.executebuiltin('SetFocus(%i)' % (id1 + 100))
    id2 = 1
    xbmc.executebuiltin('SetFocus(%i)' % (id2 + 200))


def deletecookies():
    cookiefile = mkpath(const.userdatafolder, "cookies")
    if os.path.isfile(cookiefile):
        os.remove(cookiefile)


def test():
    pass


def select_mediaitem(mediatype, mediadict):
    sorted_media = sorted(mediadict.items(), key=itemgetter(1))
    mediaids, mediatitles = zip(*sorted_media)
    call = dialogs.select('Select %s' % mediatype, mediatitles)
    if call == -1:
        return None, None
    mediaid = mediaids[call]
    mediatitle = mediatitles[call]
    return mediaid, mediatitle


# Execution
def start(action):
    koalaglobals.setglobal("Koala NRK running", True)
    force = False if action == "startup" else True
    progress.create(heading="Updating NRK", force=force)


def stop():
    progress.close()
    koalaglobals.setglobal("Koala NRK running", False)


def execution(argv):
    log.info("Starting Koala NRK")
    log.info(argv)
    run = True
    if koalaglobals.getglobal("Koala NRK running"):
        run = dialogs.yesno(heading="Running",
                           line1="Koala is running. ",
                           line2="Running multiple instances cause instablity.",
                           line3="Continue?")
    if not run:
        return

    if  argv == [''] or argv == ["default.py"]:
        action = "startup"
        mediatype = "both"
        number = "all"
    else:
        _script, action, mediatype, number = argv
    # ["configureremote", "settingsaction", "none"]
    # ["refreshsettings", "settingsaction", "none"]
    # ["deletecookies", "settingsaction", "none"]
    # ["test", "settingsaction", "none"]
    # ["checknonaddedepisodes", "show", "all"]
    # ["prioritize", "show", "single"]
    # ["update", "show", "single"]
    # ["exclude", "show", "single"]
    # ["exclude", "movie", "single"]
    # ["readd", "show", "single"]
    # ["readd", "movie", "single"]
    # ["update", "show", "all"]
    # ["removereadd", "both", "all"]
    # ["watchlist", "both", "all"]
    # ["startup", "both", "all"]
    # ["startup", "both", "all"]

    # settingsaction
    if mediatype == "settingsaction":
        if action == "configureremote":
            configure_remote()

        elif action == "refreshsettings":
            refresh_settings()

        elif action == "deletecookies":
            deletecookies()

        elif action == "test":
            test()
        return

    # initialize mediaobjects
    if mediatype == "show":
        Media = MediaLists("shows")
    elif mediatype == "movie":
        Media = MediaLists("movies")
    elif mediatype == "both":
        Media = {"Shows": MediaLists("shows"),
                 "Movies": MediaLists("movies")}

    # cancel if no media
    if action == "removereaddall" and not Media["Shows"].stored and not Media["Movies"].stored:
        dialogs.ok(heading="No media", line1="No media seems to have been added")
        return
    elif action in ["prioritize", "exclude", "readd", "update"] and not Media.stored:
        dialogs.ok(heading="No %ss" % mediatype, line1="No %ss seem to have been added" % mediatype)
        return

    # prioritize
    if action == "prioritize":
        prioritize_shows(Media.stored, Media.prioritized)
        return

    # select mediaitem
    if number == "single":
        mediadict = Media.stored if action != "readd" else Media.excluded
        mediaid, mediatitle = select_mediaitem(mediatype, mediadict)
        if not any([mediaid, mediatitle]):
            return

    start(action)

    if number == "single" and action in ["exclude", "readd", "update"]:
        modify_single_medialement(Media, mediaid, mediatitle, mediatype, action)

    elif action == "update" and mediatype == "show" and number == "all":
        update_mult_shows(Media.stored, Media.prioritized, all=True)

    elif action == "removereadd":
        remove_readd_all(Media["Shows"].stored, Media["Movies"].stored)

    elif action == "watchlist":
        check_watchlist(Media["Shows"].stored, Media["Movies"].stored, Media["Shows"].excluded, Media["Movies"].excluded)

    elif action == "startup":
        if settings["check watchlist on startup"]:
            check_watchlist(Media["Shows"].stored, Media["Movies"].stored, Media["Shows"].excluded, Media["Movies"].excluded)
            if settings["check shows on startup"]:
                update_mult_shows(Media["Shows"].stored, Media["Shows"].prioritized)

if __name__ == '__main__':
    try:
        execution(sys.argv)
    finally:
        if progress.active:
            stop()
        MediaLists.savetofile()
        log.info("Koala NRK finished")
