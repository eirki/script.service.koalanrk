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

from lib.utils import (log, settings, mkpath, const)


class RequestSession():
    def __init__(self):
        self.session = requests.Session()
        try:
            with open(mkpath(const.userdatafolder, "cookies"), 'rb') as f:
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
        with open(mkpath(const.userdatafolder, "cookies"), 'wb') as f:
            pickle.dump(self.session.cookies, f)


def login(loginpage):
    print "logging in"
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


def get_watchlist(stored_show_ids, stored_movie_ids, excluded_ids):
    setup()
    watchlistpage = reqs.get("https://tv.nrk.no/mycontent").soup()
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
    unavailable_shows = stored_show_ids - present_ids
    unavailable_movies = stored_movie_ids - present_ids
    log.info("added_shows:\n %s" % added_shows)
    log.info("unavailable_shows:\n %s" % unavailable_shows)
    log.info("added_movies:\n %s" % added_movies)
    log.info("unavailable_movies:\n %s" % unavailable_movies)
    return added_shows, unavailable_shows, added_movies, unavailable_movies


def getepisodes(showtitle, showid):
    episodes = {}
    showpage = reqs.get("http://tv.nrk.no/serie/%s/" % showid).soup()
    date_for_episodenr = "/episode-" not in showpage.find(attrs={"name": "latestepisodeurls"})["content"]
    seasons = showpage.find_all(class_="season-menu-item")
    for seasonnr, seasondata in enumerate(reversed(seasons), start=1):
        seasonid = seasondata.a["data-season"]
        headers = {'X-Requested-With': 'XMLHttpRequest'}
        episodepage = reqs.get("https://tv.nrk.no/program/Episodes/%s/%s" % (showid, seasonid), headers=headers).soup()
        episodedata = episodepage.find_all(class_="episode-item")
        for episodenr, episode in enumerate(episodedata, start=1):
            if "no-rights" in episode["class"]:
                continue
            episodeid = episode.find(class_="clearfix")["href"]
            if not date_for_episodenr:
                seasonnr, episodenr = re.findall(r"sesong-(\d+)/episode-(\d+)", episodeid)[0]
            episodes["S%02dE%02d" % (int(seasonnr), int(episodenr))] = episodeid
    return episodes


def getepisodeinfo(episodeid):
    episodesubid = re.findall(r'/serie/.*?/(.*?)/.*', episodeid)[0]
    epinfodict = reqs.get("http://v8.psapi.nrk.no/mediaelement/%s" % episodesubid).json()
    return epinfodict

reqs = RequestSession()
