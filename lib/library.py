#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import absolute_import
import multiprocessing.dummy as threading
import os
from os.path import exists
import re
import traceback
import json
import xml.etree.ElementTree as ET

from lib.utils import (mkpath, stringtofile, rpc, log, monitor, const)
import lib.internet as nrk


###################
def load_playcount(mediatype, jsonfile, kodiid):
    with open(jsonfile, "r") as f:
        playcount = json.load(f)
    rpc("VideoLibrary.Set%sDetails" % mediatype.capitalize(), **{mediatype+"id": kodiid, "playcount": playcount})
    os.remove(jsonfile)


def save_playcount(jsonfile, playcount):
    with open(jsonfile, 'w') as f:
        json.dump(playcount, f)


###################
class Movie(object):
    def __init__(self, movieid, movietitle):
        self.nrkid = movieid
        self.title = movietitle
        self.kodiid = None
        self.folderpath = os.path.join(const.libpath, "NRK movies")
        self.filename = "%s.htm" % stringtofile(self.title)
        self.filepath = mkpath(self.folderpath, self.filename)
        self.nfofilepath = self.filepath.replace(".htm", ".nfo")
        self.jsonfilepath = self.filepath.replace(".htm", ".json")

    def remove(self):
        moviedict = rpc("VideoLibrary.GetMovies",
                        properties=["file", 'playcount'],
                        multifilter={"and": [
                              ("filename", "is", self.filename),
                              ("path", "startswith", self.folderpath)]})
        if 'movies' in moviedict:
            self.kodiid = moviedict['movies'][0]['movieid']
            playcount = moviedict['movies'][0]['playcount']
            if playcount > 0:
                save_playcount(self.jsonfilepath, playcount)
            rpc("VideoLibrary.RemoveMovie", movieid=self.kodiid)
            self.delete_file()
            log.info("Removed: %s" % (self.title))
        else:
            log.info("Couldn't find file: %s" % (self.title))

    def delete_file(self):
        os.remove(self.filepath)

    def create_file(self):
        with open(self.filepath, "w") as txt:
            txt.write('<meta http-equiv="REFRESH" content="0;'
                  'url=http://tv.nrk.no%s"> <body bgcolor="#ffffff">' % self.nrkid)
        log.debug("File created: %s " % self.title)

    def add_to_lib(self):
        moviedict = rpc("VideoLibrary.GetMovies",
                        properties=["file"],
                        multifilter={"and": [
                              ("filename", "is", self.filename),
                              ("path", "startswith", self.folderpath)]})
        if 'movies' in moviedict:
            self.kodiid = moviedict['movies'][0]['movieid']
            if exists(self.jsonfilepath):
                load_playcount("movie", self.jsonfilepath, self.kodiid)
            log.info("Movie added: %s" % self.title)
            self.nonadded = False
        else:
            self.nonadded = True
            log.info("Movie added, but not scraped: %s" % self.title)

    def gen_nfo(self):
        self.delete_file()
        self.create_file()
        movsubid = re.findall(r'/program/(.*?)/.*', self.nrkid)[0]
        movinfodict = nrk.getinfodict(movsubid)
        root = ET.Element("movie")
        ET.SubElement(root, "title").text = movinfodict["fullTitle"]
        ET.SubElement(root, "plot").text = movinfodict["description"]
        ET.SubElement(root, "thumb", aspect="poster").text = movinfodict['images']["webImages"][-1]["imageUrl"]
        fanart = ET.SubElement(root, "fanart")
        ET.SubElement(fanart, "thumb").text = movinfodict['images']["webImages"][-1]["imageUrl"]
        ET.SubElement(root, "runtime").text = re.sub(r"PT(\d+)M.*", r"\1", movinfodict["duration"])
        tree = ET.ElementTree(root)
        tree.write(self.nfofilepath, xml_declaration=True, encoding='utf-8', method="xml")


class Show(object):
    def __init__(self, showid, showtitle):
        self.nrkid = showid
        self.title = showtitle
        self.folderpath = mkpath(const.libpath, "NRK shows", stringtofile(self.title))
        self.nfofilepath = mkpath(self.folderpath, "tvshow.nfo")

    def _get_stored_episodes(self):
        stored_episodes = rpc("VideoLibrary.GetEpisodes",
                              properties=["season", "episode", "file", "playcount"],
                              filter={"field": "filename", "operator": "startswith", "value": "%s S" % stringtofile(self.title)})
        self.all_stored_episodes = set()
        self.koala_stored_episodes = dict()
        for epdict in stored_episodes.get('episodes', []):
            episodecode = "S%02dE%02d" % (int(epdict['season']), int(epdict['episode']))
            self.all_stored_episodes.add(episodecode)
            if epdict["file"].startswith(self.folderpath):
                episode = Episode(self.title, epdict["season"], epdict["episode"], kodiid=epdict["episodeid"], playcount=epdict["playcount"])
                self.koala_stored_episodes[episodecode] = episode
        return self.koala_stored_episodes, self.all_stored_episodes

    def _get_new_unav_episodes(self):
        koala_stored_episodes, all_stored_episodes = self._get_stored_episodes()
        available_episodes = nrk.getepisodes(self.nrkid)

        self.new_episodes = []
        for episodecode, epdict in sorted(available_episodes.items()):
            if episodecode not in all_stored_episodes:
                episode = Episode(self.title, epdict['seasonnr'], epdict['episodenr'],
                                  nrkid=epdict['nrkid'], in_superuniverse=epdict['in_superuniverse'])
                self.new_episodes.append(episode)

        self.unav_episodes = []
        for episodecode, episode in sorted(koala_stored_episodes.items()):
            if episodecode not in available_episodes:
                self.unav_episodes.append(episode)

    def remove_all_episodes(self):
        koala_stored_episodes, all_stored_episodes = self._get_stored_episodes()
        for episode in koala_stored_episodes.values():
            episode.remove()

    def update(self):
        log.info("Updating show: %s" % self.title)
        self._get_new_unav_episodes()
        for episode in self.unav_episodes:
            episode.remove()
        for episode in self.new_episodes:
            episode.create_file()

    def add_eps_to_lib(self):
        koala_stored_episodes, all_stored_episodes = self._get_stored_episodes()
        self.nonadded_episodes = []
        for episode in self.new_episodes:
            episode.add_to_lib(koala_stored_episodes)
            if episode.nonadded:
                self.nonadded_episodes.append(episode)

    def add_nonadded_eps_to_lib(self, second_attempt=False):
        koala_stored_episodes, all_stored_episodes = self._get_stored_episodes()
        for episode in self.nonadded_episodes:
            episode.add_to_lib(koala_stored_episodes)

    def _gen_show_nfo(self):
        plot, year, image, in_superuniverse = nrk.getshowinfo(self.nrkid)
        root = ET.Element("tvshow")
        ET.SubElement(root, "title").text = self.title
        ET.SubElement(root, "year").text = year
        ET.SubElement(root, "plot").text = plot
        ET.SubElement(root, "thumb", aspect="poster").text = image
        fanart = ET.SubElement(root, "fanart")
        ET.SubElement(fanart, "thumb").text = image
        if in_superuniverse:
            ET.SubElement(root, "genre").text = "Children"
        tree = ET.ElementTree(root)
        tree.write(self.nfofilepath, xml_declaration=True, encoding='utf-8', method="xml")

    def gen_nfos(self):
        if (self.nonadded_episodes == self.new_episodes) and not self.all_stored_episodes:
            self._gen_show_nfo()
        for episode in self.nonadded_episodes:
            episode.gen_nfo()
            episode.delete_file()
            episode.create_file()


class Episode(object):
    def __init__(self, showtitle, seasonnr, episodenr, in_superuniverse=None, nrkid=None, kodiid=None, playcount=0):
        self.showtitle = showtitle
        self.seasonnr = int(seasonnr)
        self.episodenr = int(episodenr)
        self.code = "S%02dE%02d" % (seasonnr, episodenr)
        self.in_superuniverse = in_superuniverse
        self.nrkid = nrkid
        self.kodiid = kodiid
        self.playcount = int(playcount)
        self.folderpath = mkpath(const.libpath, "NRK shows", stringtofile(self.showtitle), "Season %s" % self.seasonnr)
        self.filename = "%s %s.htm" % (stringtofile(self.showtitle), self.code)
        self.filepath = mkpath(self.folderpath, self.filename)
        self.nfofilepath = self.filepath.replace(".htm", ".nfo")
        self.jsonfilepath = self.filepath.replace(".htm", ".json")
        self.nonadded = False

    def remove(self):
        if self.playcount > 0:
            save_playcount(self.jsonfilepath, self.playcount)
        rpc("VideoLibrary.RemoveEpisode", episodeid=self.kodiid)
        self.delete_file()
        log.info("Removed: %s %s" % (self.showtitle, self.code))

    def delete_file(self):
        os.remove(self.filepath)

    def create_file(self):
        if not exists(self.folderpath):
            os.makedirs(self.folderpath)
        with open(self.filepath, "w") as txt:
            txt.write('<meta http-equiv="REFRESH" content="0;'
                      'url=http://tv.nrk%s.no%s">'
                      '<body bgcolor="#ffffff">' % ("super" if self.in_superuniverse else "", self.nrkid))
        log.debug("File created: %s %s" % (self.showtitle, self.code))

    def add_to_lib(self, koala_stored_episodes):
        if self.code in koala_stored_episodes:
            self.kodiid = koala_stored_episodes[self.code].kodiid
            if exists(self.jsonfilepath):
                load_playcount("episode", self.jsonfilepath, self.kodiid)
            self.nonadded = False
            log.info("Episoded added: %s %s" % (self.showtitle, self.code))
        else:
            self.nonadded = True
            log.info("Episoded added, but not scraped: %s %s" % (self.showtitle, self.code))

    def gen_nfo(self):
        episodesubid = re.findall(r'/serie/.*?/(.*?)/.*', self.nrkid)[0]
        epinfodict = nrk.getinfodict(episodesubid)
        root = ET.Element("episodedetails")
        ET.SubElement(root, "title").text = epinfodict["fullTitle"]
        ET.SubElement(root, "showtitle").text = self.showtitle
        ET.SubElement(root, "season").text = str(self.seasonnr)
        ET.SubElement(root, "episode").text = str(self.episodenr)
        ET.SubElement(root, "plot").text = epinfodict["description"]
        ET.SubElement(root, "thumb").text = epinfodict['images']["webImages"][-1]["imageUrl"]
        ET.SubElement(root, "runtime").text = re.sub(r"PT(\d+)M.*", r"\1", epinfodict["duration"])
        tree = ET.ElementTree(root)
        tree.write(self.nfofilepath, xml_declaration=True, encoding='utf-8', method="xml")


###################
def mapwrapper(func):
    try:
        func()
    except:
        traceback.print_exc()
        raise


def remove(movies=(), shows=()):
    movieobjs = [Movie(movieid, showtitle) for movieid, showtitle in movies]
    showobjs = [Show(showid, showtitle) for showid, showtitle in shows]
    for movie in movieobjs:
        movie.remove()

    for show in showobjs:
        show.remove_all_episodes()


def update_add_create(movies=(), shows=()):
    movieobjs = [Movie(movieid, showtitle) for movieid, showtitle in movies]
    showobjs = [Show(showid, showtitle) for showid, showtitle in shows]
    pool = threading.Pool(len(movieobjs+showobjs))

    pool.map(mapwrapper, [movie.create_file for movie in movieobjs])
    pool.map(mapwrapper, [show.update for show in showobjs])
    if not (movieobjs or any(show.new_episodes for show in showobjs)):
        return

    monitor.update_video_library()
    pool.map(mapwrapper, [movie.add_to_lib for movie in movieobjs])
    pool.map(mapwrapper, [show.add_eps_to_lib for show in showobjs])

    if not (any(movie.nonadded for movie in movieobjs) or any(show.nonadded_episodes for show in showobjs)):
        return

    pool.map(mapwrapper, [movie.gen_nfo for movie in movieobjs if movie.nonadded])
    pool.map(mapwrapper, [show.gen_nfos for show in showobjs if show.nonadded_episodes])
    monitor.update_video_library()
    pool.map(mapwrapper, [movie.add_to_lib for movie in movieobjs if movie.nonadded])
    pool.map(mapwrapper, [show.add_nonadded_eps_to_lib for show in showobjs if show.nonadded_episodes])
