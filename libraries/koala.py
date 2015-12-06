#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
from os.path import exists
import re
try:
    import simplejson as json
except ImportError:
    import json
import xml.etree.ElementTree as ET

from utils import mkpath
from utils import stringtofile
from utils import kodiRPC
from utils import log
from utils import monitor
from utils import progress
from utils import const

import internet


if not exists(const.userdatafolder):
    os.makedirs(const.userdatafolder)


def create_media_file(location, filename, title, mediaid, episodecode=""):
    if not exists(location):
        os.makedirs(location)
    with open(mkpath(location, filename), "w") as txt:
        txt.write('<meta http-equiv="REFRESH" content="0;'
                  'url=http://tv.nrk.no%s"> <body bgcolor="#ffffff">' % mediaid)
    log.debug("File created: %s %s" % (title, episodecode))


def load_playcount(mediatype, mediafile, mediaid):
    jsonfile = mediafile.replace(".htm", ".json")
    if exists(jsonfile):
        with open(jsonfile, "r") as f:
            playcount = json.load(f)
        kodiRPC("VideoLibrary.Set%sDetails" % mediatype.capitalize(), **{mediatype+"id": mediaid, "playcount": playcount})
        os.remove(jsonfile)


def save_playcount(mediafile, playcount):
    if playcount > 0:
        jsonfile = mediafile.replace(".htm", ".json")
        with open(jsonfile, 'w') as f:
            json.dump(playcount, f)


def create_movies(movies, add=False):
    log.info(movies)
    for movieid, movietitle in movies:
        progress.increment("Adding movie: %s" % movietitle)
        location = mkpath(const.libpath, "NRK movies")
        filename = "%s.htm" % stringtofile(movietitle)
        create_media_file(location, filename, movietitle, movieid)
        if add:
            monitor.update_video_library()
            add_movie_to_kodi(movieid, movietitle)


def add_movie_to_kodi(movieid, movietitle):
    moviedict = kodiRPC("VideoLibrary.GetMovies",
                        properties=["file"],
                        multifilter={"and": [
                              ("filename", "is", "%s.htm" % stringtofile(movietitle)),
                              ("path", "startswith", os.path.join(const.libpath, "NRK movies"))]})
    if 'movies' in moviedict:
        moviefile = moviedict['movies'][0]['file']
        movieid = moviedict['movies'][0]['movieid']
        load_playcount("movie", moviefile, movieid)
        log.info("Movie added: %s" % (movietitle))
    else:
        log.info("Movie added, but not scraped: %s" % (movietitle))


def delete_movie(movieid, movietitle):
    progress.increment("Removing movie: %s" % movietitle)
    moviedict = kodiRPC("VideoLibrary.GetMovies",
                        properties=["file", 'playcount'],
                        multifilter={"and": [
                              ("filename", "is", "%s.htm" % stringtofile(movietitle)),
                              ("path", "startswith", os.path.join(const.libpath, "NRK movies"))]})
    if 'movies' in moviedict:
        movie = moviedict['movies'][0]
        save_playcount(movie["file"], movie['playcount'])
        kodiRPC("VideoLibrary.RemoveMovie", movieid=movie["movieid"])
        os.remove(movie["file"])
        log.info("Removed: %s" % (movietitle))
    else:
        log.info("Couldn't find file: %s" % (movietitle))


def update_show(showid, showtitle):
    progress.increment("Updating TV show: %s" % showtitle)
    log.info("Updating TV show: %s" % showtitle)
    available_episodes = internet.getepisodes(showtitle, showid)
    log.debug("available_episodes:\n %s" % available_episodes)

    stored_episodes = kodiRPC("VideoLibrary.GetEpisodes",
                              properties=["season", "episode", "file", "playcount"],
                              filter={"field": "filename", "operator": "startswith", "value": "%s S" % stringtofile(showtitle)})
    koala_stored_episodes = dict()
    other_stored_episodes = set()
    if 'episodes' in stored_episodes:
        for episode in stored_episodes['episodes']:
            episodecode = "S%02dE%02d" % (int(episode['season']), int(episode['episode']))
            if episode["file"].startswith(os.path.join(const.libpath, "NRK shows")):
                koala_stored_episodes[episodecode] = episode
            else:
                other_stored_episodes.add(episodecode)

    added_epcodes = set(available_episodes) - set(koala_stored_episodes) - other_stored_episodes
    added_episodes = [(epcode, available_episodes[epcode]) for epcode in sorted(added_epcodes)]
    log.debug("added_episodes:\n %s" % added_episodes)
    if added_episodes:
        create_episode_files(added_episodes, showtitle)
        add_episodes_to_kodi(added_episodes, showtitle)

    removed_epcodes = set(koala_stored_episodes) - set(available_episodes)
    removed_episodes = [(epcode, koala_stored_episodes[epcode]) for epcode in sorted(removed_epcodes)]
    log.debug("removed_episodes:\n %s" % removed_episodes)
    if removed_episodes:
        delete_episodes(removed_episodes, showtitle)


def create_episode_files(added_episodes, showtitle):
    progress.increment("Adding episodes: %s" % showtitle)
    for episodecode, episodeid in added_episodes:
        seasonnr = re.sub(r"S(\d\d)E\d\d.*", r"\1", episodecode)
        location = mkpath(const.libpath, "NRK shows", stringtofile(showtitle), "Season %s" % int(seasonnr))
        filename = "%s %s.htm" % (stringtofile(showtitle), episodecode)
        create_media_file(location, filename, showtitle, episodeid, episodecode)


def add_episodes_to_kodi(added_episodes, showtitle, skip_nonadded=False):
    monitor.update_video_library()
    eps_in_kodi = kodiRPC("VideoLibrary.GetEpisodes",
                          properties=["season", "episode", "file"],
                          multifilter={"and": [
                           ("filename", "startswith", "%s S" % stringtofile(showtitle)),
                           ("path", "startswith", os.path.join(const.libpath, "NRK shows"))]})
    eps_in_kodi = dict(("S%02dE%02d" % (int(ep['season']), int(ep['episode'])), ep) for ep in eps_in_kodi.get('episodes', []))

    nonadded_episodes = {}
    for episodecode, episodeid in added_episodes:
        if episodecode in eps_in_kodi:
            episodefile = eps_in_kodi[episodecode]['file']
            load_playcount("episode", episodefile, episodeid)
            log.info("Episoded added: %s %s" % (showtitle, episodecode))
        else:
            log.info("Episoded added, but not scraped: %s %s" % (showtitle, episodecode))
            nonadded_episodes[episodecode] = episodeid
            seasonnr = re.sub(r"S(\d\d)E\d\d.*", r"\1", episodecode)
            location = mkpath(const.libpath, "NRK shows", stringtofile(showtitle), "Season %s" % int(seasonnr))
            episodefile = "%s %s.htm" % (stringtofile(showtitle), episodecode)
            if not skip_nonadded:
                os.remove(mkpath(location, episodefile))
        if exists(episodefile.replace(".htm", ".nfo")):
            os.remove(episodefile.replace(".htm", ".nfo"))

    if nonadded_episodes and not skip_nonadded:
        genepisodenfos(showtitle, nonadded_episodes)


def genepisodenfos(showtitle, nonadded_episodes):
    nonadded_episodes = sorted(nonadded_episodes.items())
    for episodecode, episodeid in nonadded_episodes:
        seasonnr, episodenr = re.findall(r"S(\d\d)E(\d\d)", episodecode)[0]
        epinfodict = internet.getepisodeinfo(episodeid)
        root = ET.Element("episodedetails")
        ET.SubElement(root, "title").text = epinfodict["fullTitle"]
        ET.SubElement(root, "showtitle").text = showtitle
        ET.SubElement(root, "season").text = seasonnr
        ET.SubElement(root, "episode").text = episodenr
        ET.SubElement(root, "plot").text = epinfodict["description"]
        ET.SubElement(root, "thumb").text = epinfodict['images']["webImages"][2]["imageUrl"]
        ET.SubElement(root, "runtime").text = re.sub(r"PT(\d+)M.*", r"\1", epinfodict["duration"])
        tree = ET.ElementTree(root)
        location = mkpath(const.libpath, "NRK shows", stringtofile(showtitle), "Season %s" % int(seasonnr))
        filename = "%s %s.nfo" % (stringtofile(showtitle), episodecode)
        tree.write(mkpath(location, filename), xml_declaration=True, encoding='utf-8', method="xml")

    create_episode_files(nonadded_episodes, showtitle)
    add_episodes_to_kodi(nonadded_episodes, showtitle, skip_nonadded=True)


def delete_show(showid, showtitle):
    eps_in_kodi = kodiRPC("VideoLibrary.GetEpisodes",
                          properties=["season", "episode", "file", "playcount"],
                          multifilter={"and": [
                            ("filename", "startswith", "%s S" % stringtofile(showtitle)),
                            ("path", "startswith", os.path.join(const.libpath, "NRK shows"))]})
    eps_in_kodi = [("S%02dE%02d" % (int(ep['season']), int(ep['episode'])), ep) for ep in eps_in_kodi.get('episodes', [])]
    eps_in_kodi.sort()
    if eps_in_kodi:
        delete_episodes(eps_in_kodi, showtitle)


def delete_episodes(removed_episodes, showtitle):
    progress.increment("Removing episodes: %s" % showtitle)
    for episodecode, episodedict in removed_episodes:
        save_playcount(episodedict['file'], episodedict['playcount'])
        kodiRPC("VideoLibrary.RemoveEpisode", episodeid=episodedict['episodeid'])
        os.remove(episodedict['file'])
        log.info("Removed: %s %s" % (showtitle, episodecode))
