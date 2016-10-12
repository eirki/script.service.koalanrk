#! /usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division)

import json
import datetime as dt

from lib import constants as const
from lib import utils
from lib import mediatypes


def mock_watchlistpage():
    with open(utils.os_join(const.addonpath, "tests", "mock_watchlistpage.json"), "r") as js:
        page = json.load(js)
    return page


class RequestsSession(object):
    def setup(self):
        pass

    def get_watchlist(self):
        watchlistpage = mock_watchlistpage()
        mediaitems = watchlistpage
        available_movies = set()
        available_shows = set()
        for media in mediaitems['favorites']:
            # media["isAvailable"] True (mostly) for shows currently airing with no available episodes
            # media["program"]["usageRights"]["hasRightsNow"] false for some airing with no available episodes (bug?)
            mediatype = "show" if media["program"]["seriesId"] else "movie"
            if mediatype == "movie":
                if not media["isAvailable"]:
                    continue
                urlid = "/program/%s/%s" % (media["program"]["myContentId"], media["program"]["programUrlMetadata"])
                title = media["program"]["mainTitle"]
                available_movies.add(mediatypes.ScrapedMovie(urlid, title))
            elif mediatype == "show":
                urlid = media["program"]["seriesId"]
                title = media["program"]["seriesTitle"]
                available_shows.add(mediatypes.ScrapedShow(urlid, title))

        if not (available_movies or available_shows):
            raise Exception("No media found in watchlist")

        return available_movies, available_shows


def get_showdata_episodes(show):
    show_metadata = get_show_metadata(show)

    if show.title == "Sangfoni - musikkvideo":
        episodes = set([
            mediatypes.ScrapedEpisode(show=show, seasonnr=1, episodenr=1, urlid="1234",
                                      metadata=get_episode_metadata(epinfo=None)),
            mediatypes.ScrapedEpisode(show=show, seasonnr=1, episodenr=2, urlid="2345",
                                      metadata=get_episode_metadata(epinfo=None)),
        ])

    elif show.title == "Folkeopplysningen":
        episodes = set([
            mediatypes.ScrapedEpisode(show=show, seasonnr=1, episodenr=2, urlid="2345",
                                      metadata=get_episode_metadata(epinfo=None)),
            mediatypes.ScrapedEpisode(show=show, seasonnr=1, episodenr=3, urlid="1234",
                                      metadata=get_episode_metadata(epinfo=None)),
        ])
    return show_metadata, episodes


def get_movie_metadata(movie):
    metadata = {
        "plot": "Test Movie plot",
        "art": "Test Movie art - url",
        "runtime": dt.timedelta(seconds=600),
    }
    return metadata


def get_show_metadata(show):
    metadata = {
        "plot": "Test Show plot",
        "art": "Test Show art - url",
        "genre": "Test Show genre",
    }
    return metadata


def get_episode_metadata(epinfo):
    metadata = {
        "title": "Test Episode title",
        "plot": "Test Episode plot",
        "runtime": dt.timedelta(seconds=600),
        "thumb": "Test Episode thumb - url",
    }
    return metadata
