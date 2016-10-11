#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import glob
import re
import os

from lib import constants as const
from lib import utils
from lib import kodi
from tests import mock_constants

playcounts = {
    utils.os_join(mock_constants.libpath, "%s movies" % const.provider, "Thank you for smoking.htm"): 1,
    utils.os_join(mock_constants.libpath, "%s shows" % const.provider, "I Mummidalen",
                  "Season 2", "I Mummidalen S02E02.htm"): 2,
    utils.os_join(mock_constants.libpath, "%s shows" % const.provider, "Folkeopplysningen",
                  "Season 1", "Folkeopplysningen S01E01.htm"): 3,
}

nfo_needed = {
    utils.os_join(mock_constants.libpath, "%s movies" % const.provider, "Beatles.htm"),
    utils.os_join(mock_constants.libpath, "%s shows" % const.provider, "Sangfoni - musikkvideo", "Season 1", "Sangfoni - musikkvideo S01E01.htm")
}


def rpc(method, multifilter=False, **kwargs):
    if method == "VideoLibrary.GetMovies":
        filename = multifilter.values()[0][0][2]
        path = multifilter.values()[0][1][2]
        filepath = utils.os_join(path, filename)
        files = glob.glob(filepath)

        result = {"movies": []}
        for filepath in files:
            if filepath in nfo_needed and not os.path.isfile(filepath.replace(".htm", ".nfo")):
                continue
            result['movies'].append({"movieid": filepath,
                                     "file": filepath,
                                     'playcount': playcounts.get(filepath, 0)})
        return result

    elif method == "VideoLibrary.GetEpisodes":
        # get_koala_stored_eps
        if kwargs["filter"]["field"] == "path":
            showpath = kwargs["filter"]["value"]
            files = glob.glob(utils.os_join(showpath, "*", "*.htm"))

        # no stored koala episode, get any stored episode
        elif kwargs["filter"]["field"] == "filename":
            filename = kwargs["filter"]["value"]
            files = glob.glob(utils.os_join(mock_constants.libpath, "%s shows" % const.provider, "*", "*", filename))

        # all_stored_episodes
        elif kwargs["filter"]["field"] == "tvshow":
            showtitle = kwargs["filter"]["value"]
            files = glob.glob(utils.os_join(mock_constants.libpath, "%s shows" % const.provider, utils.stringtofile(showtitle), "*", "*.htm"))

        result = {"episodes": []}
        for filepath in files:
            seasonnr, episodenr, = re.match(r".*S(\d\d)E(\d\d).htm", filepath).groups()
            if filepath in nfo_needed and not os.path.isfile(filepath.replace(".htm", ".nfo")):
                continue
            result["episodes"].append({"episodeid": filepath,
                                       "file": filepath,
                                       'playcount': playcounts.get(filepath, 0),
                                       "season": int(seasonnr),
                                       'episode': int(episodenr)})
        return result

    # any_episode, episodeid=any_ep_kodiid
    elif method == "VideoLibrary.GetEpisodeDetails":
        filepath = kwargs["episodeid"]
        path, filename = os.path.split(filepath)
        showtitle = re.match(r"(.*) S\d\dE\d\d.htm", filename).groups()[0]
        return {'episodedetails': {"episodeid": filepath, "showtitle": showtitle}}


class ScanMonitor(object):
    def onScanFinished(self, library):
        pass

    def update_video_library(self):
        pass


class Dialog(object):
    @classmethod
    def browse(cls, *args, **kwargs):
        pass

    @classmethod
    def input(cls, *args, **kwargs):
        pass

    @classmethod
    def notification(cls, *args, **kwargs):
        pass

    @classmethod
    def numeric(cls, *args, **kwargs):
        pass

    @classmethod
    def ok(cls, *args, **kwargs):
        pass

    @classmethod
    def select(cls, *args, **kwargs):
        pass

    @classmethod
    def yesno(cls, *args, **kwargs):
        pass


settings = {
    "shows on startup": True,
    "added_notifications": True,
    'watchlist on startup': True,
    "all shows on startup": True,
    "n shows on startup": 10,
    'multithreading': True
}

log = kodi.log
