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
                available_movies.add(Movie(urlid, title))
            elif mediatype == "show":
                urlid = media["program"]["seriesId"]
                title = media["program"]["seriesTitle"]
                available_shows.add(Show(urlid, title))

        if not (available_movies or available_shows):
            raise Exception("No media found in watchlist")

        return available_movies, available_shows

    def getepisodes(self, show):
        episodes = set()
        showpage = self.get("http://tv.nrk.no/serie/%s/" % show.urlid).soup()
        date_for_episodenr = showpage.find(attrs={"name": "latestepisodeurls"}) and "/episode-" not in showpage.find(attrs={"name": "latestepisodeurls"})["content"]
        seasons = showpage.find_all(class_="season-menu-item")
        in_superuniverse = "isInSuperUniverse: true" in showpage.text
        for seasonnr, seasondata in enumerate(reversed(seasons), start=1):
            seasonid = seasondata.a["data-season"]
            if not in_superuniverse:
                headers = {'X-Requested-With': 'XMLHttpRequest'}
                episodepage = self.get("https://tv.nrk.no/program/Episodes/%s/%s" % (show.urlid, seasonid), headers=headers).soup()
                episodedata = episodepage.find_all(class_="episode-item")
                for episodenr, episode in enumerate(episodedata, start=1):
                    if "no-rights" in episode["class"]:
                        continue
                    episodeid = episode.find(class_="clearfix")["href"]
                    if not date_for_episodenr:
                        seasonnr, episodenr = re.findall(r"sesong-(\d+)/episode-(\d+)", episodeid)[0]
                    episodes.add(KoalaEpisode(showtitle=show.title, seasonnr=int(seasonnr), episodenr=int(episodenr),
                                              urlid=str(episodeid), in_superuniverse=False))
            else:
                episodepage = self.get("http://tv.nrksuper.no/program/EpisodesSuper/%s/%s" % (show.urlid, seasonid)).json()
                for episodenr, episodeitem in enumerate(episodepage["data"], start=1):
                    episodeid = "/serie/%s/%s/%s" % (episodeitem['seriesId'], episodeitem['id'], episodeitem['programUrlMetadata'])
                    if not date_for_episodenr:
                        seasonnr, episodenr = re.findall(r"sesong-(\d+)/episode-(\d+)", episodeitem['programUrlMetadata'])[0]
                    episodes.add(KoalaEpisode(showtitle=show.title, seasonnr=int(seasonnr), episodenr=int(episodenr),
                                              urlid=str(episodeid), in_superuniverse=True))
        return episodes

    def getinfodict(self, urlid):
        raw_infodict = self.get("http://v8.psapi.nrk.no/mediaelement/%s" % urlid).json()
        infodict = {
            "title": raw_infodict["fullTitle"],
            "plot": raw_infodict["description"],
            "art": raw_infodict['images']["webImages"][-1]["imageUrl"],
            "runtime": re.sub(r"PT(\d+)M.*", r"\1", raw_infodict["duration"]),
            }
        return infodict

    def getshowinfo(self, showid):
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
