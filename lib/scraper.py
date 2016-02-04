#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import absolute_import
from bs4 import BeautifulSoup
import json
import pickle
import requests
from types import MethodType
from HTMLParser import HTMLParser
import re

from .utils import os_join
from . import constants as const
from .xbmcwrappers import (log, settings)


class RequestSession():
    def __init__(self):
        self.session = requests.Session()
        try:
            with open(os_join(const.userdatafolder, "cookies"), 'rb') as f:
                self.session.cookies = pickle.load(f)
        except IOError:
            pass

    def soup(self, resp):
        return BeautifulSoup(resp.text)

    def get(self, url, **kwargs):
        log.info("LOADING: %s" % url)
        req = self.session.get(url, **kwargs)
        req.soup = MethodType(self.soup, req)
        return req

    def post(self, url, **kwargs):
        log.info("LOADING: %s" % url)
        log.debug("Payload: %s" % kwargs)
        req = self.session.post(url, **kwargs)
        req.soup = MethodType(self.soup, req)
        return req

    def save_cookies(self):
        with open(os_join(const.userdatafolder, "cookies"), 'wb') as f:
            pickle.dump(self.session.cookies, f)
reqs = RequestSession()


def login(loginpage):
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
    loginpage2 = reqs.post(loginpage.url, data=payload, allow_redirects=True)
    return loginpage2
    # if loginpage3.find(id="page-LOGIN"):
        # log.debug(loginpage.text)
        # raise Exception("Login attempt failed")


def setup():
    print "checking login status"
    loginpage = reqs.get("https://tv.nrk.no/logginn", verify=False)
    print loginpage.soup().find('title').text
    if loginpage.soup().find('title').text == "Innlogging":
        loginpage = login(loginpage)
    url = loginpage.soup().find("form")["action"]
    payload = {t['name']: t.get('value') for t in loginpage.soup().find_all('input', attrs={'type': 'hidden'})}
    reqs.post(url, data=payload)
    reqs.save_cookies()


def check_watchlist(movie_database, show_database):
    setup()
    stored_show_ids = set(show_database.stored)
    stored_movie_ids = set(movie_database.stored)
    excluded_ids = set(movie_database.excluded) | set(show_database.excluded)
    watchlistpage = reqs.get("https://tv.nrk.no/mycontent")
    mediaitems = json.loads(watchlistpage.text.replace("\r\n", ""))
    present_ids = set()
    added_shows = []
    added_movies = []
    for media in mediaitems['favorites']:
        if not media["isAvailable"]:
            continue
            # media["isAvailable"] True for shows currently airing with no available episodes
            # media["program"]["usageRights"]["hasRightsNow"] false for some airing with no available episodes (bug?)
        mediatype = "show" if media["program"]["seriesId"] else "movie"
        if mediatype == "movie":
            mediaid = "/program/%s/%s" % (media["program"]["myContentId"], media["program"]["programUrlMetadata"])
            # mediaid = media["program"]["programUrlMetadata"]
            # mediaid = media["program"]["myContentId"]
            if mediaid not in (stored_movie_ids | excluded_ids):
                mediatitle = media["program"]["mainTitle"]
                added_movies.append((mediaid, mediatitle))
        elif mediatype == "show":
            mediaid = media["program"]["seriesId"]
            if mediaid not in (stored_show_ids | excluded_ids):
                mediatitle = media["program"]["seriesTitle"]
                added_shows.append((mediaid, mediatitle))
        present_ids.add(mediaid)
    unavailable_shows = []
    for showid, showtitle in show_database.stored.items():
        if showid not in present_ids:
            unavailable_shows.append((showid, showtitle))
    unavailable_movies = []
    for movieid, movietitle in movie_database.stored.items():
        if movieid not in present_ids:
            unavailable_movies.append((movieid, movietitle))
    log.info("added_shows:\n %s" % added_shows)
    log.info("unavailable_shows:\n %s" % unavailable_shows)
    log.info("added_movies:\n %s" % added_movies)
    log.info("unavailable_movies:\n %s" % unavailable_movies)
    return unavailable_movies, unavailable_shows, added_movies, added_shows


def getepisodes(showid):
    episodes = {}
    showpage = reqs.get("http://tv.nrk.no/serie/%s/" % showid).soup()
    date_for_episodenr = showpage.find(attrs={"name": "latestepisodeurls"}) and "/episode-" not in showpage.find(attrs={"name": "latestepisodeurls"})["content"]
    seasons = showpage.find_all(class_="season-menu-item")
    in_superuniverse = "isInSuperUniverse: true" in showpage.text
    for seasonnr, seasondata in enumerate(reversed(seasons), start=1):
        seasonid = seasondata.a["data-season"]
        if not in_superuniverse:
            headers = {'X-Requested-With': 'XMLHttpRequest'}
            episodepage = reqs.get("https://tv.nrk.no/program/Episodes/%s/%s" % (showid, seasonid), headers=headers).soup()
            episodedata = episodepage.find_all(class_="episode-item")
            for episodenr, episode in enumerate(episodedata, start=1):
                if "no-rights" in episode["class"]:
                    continue
                episodeid = episode.find(class_="clearfix")["href"]
                if not date_for_episodenr:
                    seasonnr, episodenr = re.findall(r"sesong-(\d+)/episode-(\d+)", episodeid)[0]
                epcode = "S%02dE%02d" % (int(seasonnr), int(episodenr))
                episodes[epcode] = {"seasonnr": int(seasonnr), "episodenr": int(episodenr),
                                    "nrkid": str(episodeid), "in_superuniverse": False}
        else:
            episodepage = reqs.get("http://tv.nrksuper.no/program/EpisodesSuper/%s/%s" % (showid, seasonid)).json()
            for episodenr, episodeitem in enumerate(episodepage["data"], start=1):
                episodeid = "/serie/%s/%s/%s" % (episodeitem['seriesId'], episodeitem['id'], episodeitem['programUrlMetadata'])
                if not date_for_episodenr:
                    seasonnr, episodenr = re.findall(r"sesong-(\d+)/episode-(\d+)", episodeitem['programUrlMetadata'])[0]
                epcode = "S%02dE%02d" % (int(seasonnr), int(episodenr))
                episodes[epcode] = {"seasonnr": int(seasonnr), "episodenr": int(episodenr),
                                    "nrkid": str(episodeid), "in_superuniverse": True}
    return episodes


def getinfodict(mediaid):
    infodict = reqs.get("http://v8.psapi.nrk.no/mediaelement/%s" % mediaid).json()
    return infodict


def getshowinfo(showid):
    showpage = reqs.get("http://tv.nrk.no/serie/%s/" % showid).soup()
    plot_heading = showpage.find("h3", text="Seriebeskrivelse")
    plot = plot_heading.next_sibling.next_sibling.text if plot_heading else ""
    year = showpage.find("dt", text="Produksjonsår:").next_sibling.next_sibling.text
    image = showpage.find(id="playerelement")["data-posterimage"]
    in_superuniverse = "isInSuperUniverse: true" in showpage.text
    return plot, year, image, in_superuniverse
