#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import re
import json
from bs4 import BeautifulSoup
import browsercookie
import requests
from types import MethodType
import datetime as dt

from . import kodi
from . import mediatypes


class RequestsSession(object):
    def __init__(self):
        self.session = requests.Session()
        self.session.headers = {
            'User-Agent': 'NRK%20TV/43 CFNetwork/711.5.6 Darwin/14.0.0',
            "accept": '*/*',
            'app-version-ios': '43',
            'Accept-Language': 'en-us',
        }

    def load_cookies(self):
        self.session.cookies = browsercookie.chrome()

    def soup(self, resp):
        return BeautifulSoup(resp.text)

    def get(self, url, **kwargs):
        kodi.log("LOADING: %s" % url)
        req = self.session.get(url, timeout=30, **kwargs)
        req.soup = MethodType(self.soup, req)
        return req

    def post(self, url, hidden=False, **kwargs):
        kodi.log("LOADING: %s" % url)
        if kwargs and not hidden:
            kodi.log("Payload: %s" % kwargs)
        req = self.session.post(url, timeout=30, **kwargs)
        req.soup = MethodType(self.soup, req)
        return req

    def setup(self):
        self.load_cookies()
        loginpage = self.get("https://tv.nrk.no/logginn", verify=False)
        if loginpage.soup().find('title').text == "Innlogging":
            raise Exception('Login failed. Ensure chrome is logged in')
        url = loginpage.soup().find("form")["action"]
        payload = {t['name']: t.get('value') for t in loginpage.soup().find_all('input', attrs={'type': 'hidden'})}
        self.post(url, data=payload)

    def get_watchlist(self):
        watchlistpage = self.get("https://tv.nrk.no/mycontent")
        mediaitems = json.loads(watchlistpage.text.replace("\r\n", ""))
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
    episodes = set()
    reqs = RequestsSession()
    showdata = reqs.get("http://tvapi.nrk.no/v1/series/%s/" % show.urlid).json()
    metadata = get_show_metadata(showdata)
    date_for_episodenr = ":" not in showdata["programs"][0]["episodeNumberOrDate"]
    if not date_for_episodenr:
        seasons = {season["id"]: int(season["name"].split()[-1]) for season in showdata["seasonIds"]}
        for epinfo in showdata["programs"]:
            if not epinfo["isAvailable"]:
                continue
            episodenr = int(epinfo["episodeNumberOrDate"].split(":")[0])
            seasonnr = seasons[epinfo["seasonId"]]
            urlid = epinfo["programId"]
            metadata = get_episode_metadata(epinfo)
            episode = mediatypes.ScrapedEpisode(show=show, seasonnr=seasonnr, episodenr=episodenr, urlid=urlid, metadata=metadata)
            episodes.add(episode)

    else:
        seasons = {season["id"]: i for i, season in enumerate(reversed(showdata["seasonIds"]), start=1)}
        prevseasonid = None
        for i, epinfo in enumerate(reversed(showdata["programs"]), start=1):
            if not epinfo["isAvailable"]:
                continue
            seasonid = epinfo["seasonId"]
            seasonnr = seasons[seasonid]
            episodenr = episodenr + 1 if seasonid == prevseasonid else 1
            prevseasonid = seasonid

            urlid = epinfo["programId"]
            metadata = get_episode_metadata(epinfo)
            episode = mediatypes.ScrapedEpisode(show=show, seasonnr=seasonnr, episodenr=episodenr, urlid=urlid, metadata=metadata)
            episodes.add(episode)
    return metadata, episodes


def get_movie_metadata(movie):
    reqs = RequestsSession()
    _, _, subid, _ = movie.urlid.split("/")
    raw_infodict = reqs.get("http://v8.psapi.nrk.no/mediaelement/%s" % subid).json()
    hours, minutes, seconds = re.match(r"PT(\d+H)?(\d+M)?(\d+S)?", raw_infodict["duration"]).groups()
    runtime = dt.timedelta(
        hours=int(hours[:-1]) if hours is not None else 0,
        minutes=int(minutes[:-1]) if minutes is not None else 0,
        seconds=int(seconds[:-1]) if seconds is not None else 0,
    )
    infodict = {
        "plot": raw_infodict["description"],
        "art": raw_infodict['images']["webImages"][-1]["imageUrl"],
        "runtime": runtime,
        }
    return infodict


def get_show_metadata(showdata):
    metadata = {
        "genre": showdata["category"]["displayValue"],
        "plot": showdata["description"],
        "art": "http://gfx.nrk.no/%s" % showdata["imageId"],
    }
    return metadata


def get_episode_metadata(epinfo):
    metadata = {
        "plot": epinfo["description"],
        "runtime": dt.timedelta(milliseconds=epinfo["duration"]),
        "thumb": epinfo["imageId"],
        "title": epinfo["title"]
    }
    return metadata
