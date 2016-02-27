#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from datetime import datetime
import sys
import os
from operator import attrgetter
import xbmc
import xbmcgui

from lib import constants as const
from lib import library
from lib.utils import (os_join, uni_join)
from lib.xbmcwrappers import (settings, rpc, log, dialogs)
if const.os == "win":
    from lib import win32hack
    win32hack.run()
from lib import playback
from lib.remote import Remote


def koalasetup():
    if not os.path.exists(const.userdatafolder):
        os.makedirs(const.userdatafolder)
    if not os.path.exists(os_join(const.libpath, "%s shows" % const.provider)):
        os.makedirs(os_join(const.libpath, "%s shows" % const.provider))
    if not os.path.exists(os_join(const.libpath, "%s movies" % const.provider)):
        os.makedirs(os_join(const.libpath, "%s movies" % const.provider))


def is_libpath_added():
    sources = rpc("Files.GetSources", media="video")
    for source in sources.get('sources', []):
        if source['file'].startswith(const.libpath):
            return True
    return False


def refresh_settings():
    xbmc.executebuiltin('Dialog.Close(dialog)')
    xbmc.executebuiltin('ReloadSkin')
    xbmc.executebuiltin('Addon.OpenSettings(%s)' % const.addonid)


def prioritize_shows():
    library.Show.init_databases()
    sorted_shows = sorted(library.Show.db.all, key=attrgetter("title"))
    titles = [media.title for media in sorted_shows]
    for i, show in enumerate(sorted_shows):
        if show.urlid in library.Show.db_prioritized.ids:
            titles[i] = "[Prioritized] %s" % show.title
    while True:
        call = dialogs.select('Select prioritized shows', titles)
        if call == -1:
            break
        show = sorted_shows[call]
        if show.urlid not in library.Show.db_prioritized.ids:
            library.Show.db_prioritized.upsert(show.urlid, show.title)
            titles[call] = "[Prioritized] %s" % show.title
        else:
            library.Show.db_prioritized.remove(show.urlid)
            titles[call] = show.title.replace("[Prioritized] ", "")
    library.Show.db_prioritized.savetofile()
    # open_addonsettings(id1=2, id2=4)


def deletecookies():
    cookiefile = os_join(const.userdatafolder, "cookies")
    if os.path.isfile(cookiefile):
        os.remove(cookiefile)


def test():
    print const.addonid


def get_params(argv):
    if argv in ([''], ["main.py"]):
        params = {"mode": "library", "action": "startup"}
    else:
        params = {}
        if argv[0] == "main.py":
            arg_pairs = argv[1:]
        elif argv[0] == "plugin://%s/" % const.addonid:
            arg_pairs = argv[2][1:].split("&")
        for arg_pair in arg_pairs:
            arg, val = arg_pair.split('=')
            params[arg] = val
    return params


# Execution
def main():
    log.info("Starting %s" % const.addonname)
    log.info(sys.argv)
    params = get_params(sys.argv)
    log.info(params)
    mode = params.get('mode', None)
    action = params.get('action', None)
    log.info(action)

    if mode == "play":
        urlid = params['urlid']
        playback.play(urlid)
        return

    if mode == "live":
        playback.playlive()
        return

    # not implemented:
    # if mode == "browse":
        # playback.browse()
        # return

    if action == "startup" and not settings["watchlist on startup"]:
        return

    if action == "configureremote":
        remote = Remote()
        remote.configure()
        return

    elif mode == "setting":
        settingsactions = {
            "refreshsettings": refresh_settings,
            "deletecookies": deletecookies,
            "test": test,
            "prioritize": prioritize_shows
        }
        settingsactions[action]()
        return

    elif mode == "library":
        run = True
        if xbmcgui.Window(10000).getProperty("%s running" % const.addonname) == "true":
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
                       line2=uni_join(const.libpath, "%s shows" % const.provider),
                       line3=uni_join(const.libpath, "%s movies" % const.provider))
            return
        library.main(action)

if __name__ == '__main__':
    try:
        starttime = datetime.now()
        main()
    finally:
        log.info("%s finished (in %s)" % (const.addonname, str(datetime.now() - starttime)))
