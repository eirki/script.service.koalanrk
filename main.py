#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from datetime import datetime
from collections import OrderedDict
import json
import sys
import os
from operator import itemgetter
import xbmc
import xbmcgui

from lib import constants as const
from lib import library
from lib import scraper
from lib.utils import (os_join, uni_join, parameters_string_to_dict)
from lib.xbmcwrappers import (settings, rpc, log, progress, dialogs)
from lib import win32hack
win32hack.run()
from lib import playback
from lib.remote import Remote

# from https://docs.python.org/2/library/collections.html#collections.OrderedDict
class LastUpdatedOrderedDict(OrderedDict):
    '''Store items in the order the keys were last added
    from https://docs.python.org/2/library/collections.html#collections.OrderedDict'''

    def __setitem__(self, key, value):
        if key in self:
            del self[key]
        OrderedDict.__setitem__(self, key, value)


class MediaDatabase(object):
    instances = []

    def __init__(self, mediatype):
        self.mediatype = mediatype
        try:
            with open(os_join(const.userdatafolder, "%s database.json" % self.mediatype), 'r') as j:
                database = json.load(j)
            self.stored = LastUpdatedOrderedDict(database["stored"])
            self.excluded = database["excluded"]
            self.prioritized = set(database["prioritized"])
        except IOError:
            self.stored = LastUpdatedOrderedDict({})
            self.excluded = {}
            self.prioritized = set()
        MediaDatabase.instances.append(self)

    def update(self, mediaitems):
        for mediaid, mediatitle in mediaitems:
            self.stored.update({mediaid: mediatitle})

    def remove(self, mediaitems):
        for mediaid, mediatitle in mediaitems:
            del self.stored[mediaid]

    def exclude(self, mediaitems):
        for mediaid, mediatitle in mediaitems:
            del self.stored[mediaid]
            self.excluded.update({mediaid: mediatitle})

    def readd(self, mediaitems):
        for mediaid, mediatitle in mediaitems:
            del self.excluded[mediaid]
            self.stored.update({mediaid: mediatitle})

    @classmethod
    def savetofile(cls):
        for inst in cls.instances:
            database = {
                "stored": inst.stored.items(),
                "excluded": inst.excluded,
                "prioritized": list(inst.prioritized)
            }
            with open(os_join(const.userdatafolder, "%s database.json" % inst.mediatype), 'w') as p:
                json.dump(database, p, indent=2)


def select_channel():
    channels = ["NRK1", "NRK2", "NRK3", "NRKsuper"]
    call = dialogs.select('Select channel', channels)
    if call == -1:
        return None
    channel_name = channels[call]
    channel_id = "tv.nrk.no/direkte/%s" % channel_name.lower()
    return channel_id, channel_name


def get_n_shows_to_update(show_database):
    pri_shows = []
    n_shows = list(show_database.stored)
    for showid in show_database.stored:
        if showid in show_database.prioritized:
            n_shows.remove(showid)
            pri_shows.append(showid)
    if not settings["all_shows_on_startup"]:
        n = settings["n_shows_to_update"]
        n_shows = n_shows[:n]

    shows_to_update = [(showid, show_database.stored[showid]) for showid in pri_shows+n_shows]
    return shows_to_update


def koalasetup():
    if not os.path.exists(const.userdatafolder):
        os.mkdir(const.userdatafolder)
    if not os.path.exists(os_join(const.libpath, "NRK shows")):
        os.mkdir(os_join(const.libpath, "NRK shows"))
    if not os.path.exists(os_join(const.libpath, "NRK movies")):
        os.mkdir(os_join(const.libpath, "NRK movies"))


def is_libpath_added():
    sources = rpc("Files.GetSources", media="video")
    for source in sources.get('sources', []):
        if source['file'].startswith(const.libpath):
            return True
    return False


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


def deletecookies():
    cookiefile = os_join(const.userdatafolder, "cookies")
    if os.path.isfile(cookiefile):
        os.remove(cookiefile)


        del self


def test():
    pass

def select_mediaitem(database, mediatype):
    sorted_media = sorted(database.items(), key=itemgetter(1))
    mediaids, mediatitles = zip(*sorted_media)
    call = dialogs.select('Select %s' % mediatype, mediatitles)
    if call == -1:
        return None, None
    mediaid = mediaids[call]
    mediatitle = mediatitles[call]
    return mediaid, mediatitle


# Execution
def start(action):
    xbmcgui.Window(10000).setProperty("Koala NRK running", "true")
    force = False if action == "startup" else True
    progress.create(heading="Updating NRK", force=force)


def stop():
    progress.close()
    xbmcgui.Window(10000).setProperty("Koala NRK running", "false")


def main():
    log.info("Starting Koala NRK")
    log.info(sys.argv)
    params = parameters_string_to_dict(sys.argv[-1])
    log.info(params)
    mode = params.get('mode', None)
    action = params.get('action', None)
    log.info(action)
    if sys.argv in ([''], ["default.py"]):
        mode = "library"
        action = "startup"

    if mode == "play":
        url = params['url']
        playback.play(url)
        return

    if mode == "live":
        channel_id, channel_name = select_channel()
        if channel_id:
            playback.playlive(channel_id, channel_name)
        return

    if action == "startup" and not settings["check on startup"]:
        return

    run = True
    if xbmcgui.Window(10000).getProperty("Koala NRK running") == "true":
        run = dialogs.yesno(heading="Running",
                            line1="Koala is running. ",
                            line2="Running multiple instances cause instablity.",
                            line3="Continue?")
    if not run:
        return

    koalasetup()

    if not is_libpath_added():
        dialogs.ok(heading="Koala path not in video sources",
                   line1="Koala library paths have not been added to Kodi video sources:",
                   line2=uni_join(const.libpath, "NRK shows"),
                   line3=uni_join(const.libpath, "NRK movies"))
        return


    if action == "configureremote":
        remote = Remote()
        remote.configure()
        return

    settingsactions = {
        "refreshsettings": refresh_settings,
        "deletecookies": deletecookies,
        "test": test
    }
    if mode == "setting":
        settingsactions[action]()
        return

    # initialize mediaobjects
    show_database = None
    movie_database = None
    if action in ["prioritize", "exclude_show", "readd_show", "update_single", "update_all", "remove_all", "watchlist", "startup"]:
        show_database = MediaDatabase("show")
    if action in ["exclude_movie", "readd_movie", "remove_all", "watchlist", "startup"]:
        movie_database = MediaDatabase("movie")


    # cancel if no media
    if action == "remove_all" and not (show_database.stored or movie_database.stored):
        dialogs.ok(heading="No media", line1="No media seems to have been added")
        return
    elif action in ["prioritize", "exclude_show", "readd_show", "update_single", "update_all"] and not show_database.stored:
        dialogs.ok(heading="No shows", line1="No shows seem to have been added")
        return
    elif action in ["exclude_movie", "readd_movie"] and not movie_database.stored:
        dialogs.ok(heading="No movies", line1="No movies seem to have been added")
        return

    # prioritize
    if action == "prioritize":
        prioritize_shows(show_database.stored, show_database.prioritized)
        return

    if action in ("update_single", "exclude_show"):
        show = select_mediaitem(show_database.stored, "show")
    elif action == "readd_show":
        show = select_mediaitem(show_database.excluded, "show")
    elif action == "exclude_movie":
        movie = select_mediaitem(movie_database.stored, "movie")
    elif action == "readd_movie":
        movie = select_mediaitem(movie_database.excluded, "movie")

    if action in ("update_single", "exclude_show", "readd_show") and not any(show):
        return
    if action in ("exclude_movie", "readd_movie") and not any(movie):
        return

    start(action)

    if action == "exclude_show":
        library.remove(shows=[show])
        show_database.exclude([show])
        return
    elif action == "exclude_movie":
        library.remove(movies=[movie])
        movie_database.exclude([movie])
        return

    progress.update(10)

    if action == "update_single":
        library.update_add_create(shows=[show])
        show_database.update([show])
    elif action == "readd_show":
        library.update_add_create(shows=[show])
        show_database.readd([show])
    elif action == "readd_movie":
        library.update_add_create(movies=[movie])
        movie_database.readd([movie])

    elif action == "update_all":
        progress.update(25)
        library.update_add_create(shows=show_database.stored.items())

    elif action == "remove_all":
        progress.update(50)
        library.remove(movies=movie_database.stored.items(), shows=show_database.stored.items())
        movie_database.remove(movie_database.stored.items())
        show_database.remove(show_database.stored.items())

    elif action in ["watchlist", "startup"]:
        progress.update(25)
        results = scraper.check_watchlist(movie_database, show_database)
        unav_movies, unav_shows, added_movies, added_shows = results
        if unav_movies or unav_shows:
            progress.update(50)
            library.remove(movies=unav_movies, shows=unav_shows)
            movie_database.remove(unav_movies)
            show_database.remove(unav_shows)
        if added_movies or added_shows:
            progress.update(60)
            library.update_add_create(movies=added_movies, shows=added_shows)
            movie_database.update(added_movies)
            show_database.update(added_shows)
        if action == "startup":
            progress.update(75)
            shows_to_update = get_n_shows_to_update(show_database)
            library.update_add_create(shows=shows_to_update)
            show_database.update(shows_to_update)

if __name__ == '__main__':
    try:
        starttime = datetime.now()
        main()
    finally:
        if progress.active:
            stop()
        MediaDatabase.savetofile()
        xbmcgui.Window(10000).setProperty("Koala NRK has run", "true")
        log.info("Koala NRK finished (in %s)" % str(datetime.now() - starttime))
