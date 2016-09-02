#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import re
import json
from bs4 import BeautifulSoup
import pickle
import requests
from types import MethodType
from HTMLParser import HTMLParser
from collections import namedtuple

from . utils import os_join
from . import constants as const
from . xbmcwrappers import (log, settings)
from . mediatypes import (KoalaMovie, Show, KoalaEpisode)


Mediatuple = namedtuple("Media", "urlid title")


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
        try:
            with open(os_join(const.userdatafolder, "cookies"), 'rb') as f:
                self.session.cookies = pickle.load(f)
        except IOError:
            pass

    def save_cookies(self):
        with open(os_join(const.userdatafolder, "cookies"), 'wb') as f:
            pickle.dump(self.session.cookies, f)

    def soup(self, resp):
        return BeautifulSoup(resp.text)

    def get(self, url, **kwargs):
        log.info("LOADING: %s" % url)
        req = self.session.get(url, timeout=30, **kwargs)
        req.soup = MethodType(self.soup, req)
        return req

    def post(self, url, hidden=False, **kwargs):
        log.info("LOADING: %s" % url)
        if kwargs and not hidden:
            log.info("Payload: %s" % kwargs)
        req = self.session.post(url, timeout=30, **kwargs)
        req.soup = MethodType(self.soup, req)
        return req

    def login(self, loginpage):
        log.info("logging in")
        username = settings["username"]
        passw = settings["password"]
        if not username or not passw:
            raise Exception('Username or password not specified')
        scriptsection = loginpage.soup().find(id="modelJson")
        unescaped_json = HTMLParser().unescape(scriptsection.text.strip())
        scrdata = json.loads(unescaped_json)
        payload = {
            scrdata["antiForgery"]["name"]: scrdata["antiForgery"]["value"],
            scrdata["apiAntiForgery"]["name"]: scrdata["apiAntiForgery"]["value"],
            "userName": username,
            "password": passw,
        }
        loginpage2 = self.post(loginpage.url, data=payload, allow_redirects=True, hidden=True)
        return loginpage2

    def setup(self):
        loginpage = self.get("https://tv.nrk.no/logginn", verify=False)
        if loginpage.soup().find('title').text == "Innlogging":
            loginpage = self.login(loginpage)
        url = loginpage.soup().find("form")["action"]
        payload = {t['name']: t.get('value') for t in loginpage.soup().find_all('input', attrs={'type': 'hidden'})}
        self.post(url, data=payload)

    def getwatchlist(self):
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
                available_movies.add(KoalaMovie(urlid, title))
            elif mediatype == "show":
                urlid = media["program"]["seriesId"]
                title = media["program"]["seriesTitle"]
                available_shows.add(Show(urlid, title))

        if not (available_movies or available_shows):
            raise Exception("No media found in watchlist")

        return available_movies, available_shows

    def getepisodes(self, show):
        episodes = set()
        showdata = self.get("http://tvapi.nrk.no/v1/series/%s/" % show.urlid).json()
        date_for_episodenr = ":" not in showdata["programs"][0]["episodeNumberOrDate"]
        if not date_for_episodenr:
            seasons = {season["id"]: int(season["name"].split()[-1]) for season in showdata["seasonIds"]}
            for episode in showdata["programs"]:
                if not episode["isAvailable"]:
                    continue
                episodenr = int(episode["episodeNumberOrDate"].split(":")[0])
                seasonnr = seasons[episode["seasonId"]]
                urlid = episode["programId"]
                episodes.add(KoalaEpisode(showtitle=show.title, seasonnr=seasonnr, episodenr=episodenr, urlid=urlid, plot=episode["description"],
                                          runtime=int(episode["duration"]/1000), art=episode["imageId"], title=episode["title"]))

        else:
            seasons = {season["id"]: i for i, season in enumerate(reversed(showdata["seasonIds"]), start=1)}
            prevseasonid = None
            for i, episode in enumerate(reversed(showdata["programs"]), start=1):
                if not episode["isAvailable"]:
                    continue
                seasonid = episode["seasonId"]
                seasonnr = seasons[seasonid]
                episodenr = episodenr + 1 if seasonid == prevseasonid else 1
                prevseasonid = seasonid

                urlid = episode["programId"]
                episodes.add(KoalaEpisode(showtitle=show.title, seasonnr=seasonnr, episodenr=episodenr, urlid=urlid, plot=episode["description"],
                                          runtime=int(episode["duration"]/1000), art=episode["imageId"], title=episode["title"]))
        return episodes

    def get_movie_metadata(self, urlid):
        raw_infodict = self.get("http://v8.psapi.nrk.no/mediaelement/%s" % urlid).json()
        infodict = {
            "title": raw_infodict["fullTitle"],
            "plot": raw_infodict["description"],
            "art": raw_infodict['images']["webImages"][-1]["imageUrl"],
            "runtime": re.sub(r"PT(\d+)M.*", r"\1", raw_infodict["duration"]),
            }
        return infodict

    def get_show_metadata(self, showid):
        showpage = self.get("http://tv.nrk.no/serie/%s/" % showid).soup()
        plot_heading = showpage.find("h3", text="Seriebeskrivelse")
        infodict = {
            "year": showpage.find("dt", text="Produksjonsår:").next_sibling.next_sibling.text,
            "in_superuniverse": "isInSuperUniverse: true" in showpage.text,
            "plot": plot_heading.next_sibling.next_sibling.text if plot_heading else ""
        }
        try:
            infodict["art"] = showpage.find(class_="play-icon-action").img["src"]
        except KeyError:
            log.info("Note: New nfo image location invalid")
            infodict["art"] = showpage.find(id="playerelement")["data-posterimage"]

        return infodict
