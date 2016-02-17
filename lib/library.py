#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import absolute_import
import multiprocessing.dummy as threading
import os
import re
import traceback
import json
import xml.etree.ElementTree as ET
import xbmcgui
from operator import attrgetter

from . utils import (os_join, uni_join, stringtofile)
from . import scraper
from . import constants as const
from . import database
from .xbmcwrappers import (rpc, log, monitor, settings, progress, dialogs)

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
    @classmethod
    def init_databases(cls):
        cls.db = database.MediaDatabase('movies', return_as=cls)
        cls.db_excluded = database.MediaDatabase('excluded movies', return_as=cls)

    @classmethod
    def commit_databases(cls):
        cls.db.savetofile()
        cls.db_excluded.savetofile()

    def __init__(self, movieid, movietitle):
        self.nrkid = movieid
        self.title = movietitle
        self.kodiid = None
        self.path = uni_join(const.libpath, "NRK movies")
        self.filename = "%s.strm" % stringtofile(self.title)
        self.nfofilename = "%s.nfo" % stringtofile(self.title)
        self.jsonfilename = "%s.json" % stringtofile(self.title)

    def remove(self):
        moviedict = rpc("VideoLibrary.GetMovies",
                        properties=["file", 'playcount'],
                        multifilter={"and": [
                              ("filename", "is", self.filename),
                              ("path", "startswith", self.path)]})
        if 'movies' in moviedict:
            self.kodiid = moviedict['movies'][0]['movieid']
            playcount = moviedict['movies'][0]['playcount']
            if playcount > 0:
                jsonfilepath = os_join(self.path, self.jsonfilename)
                save_playcount(jsonfilepath, playcount)
            rpc("VideoLibrary.RemoveMovie", movieid=self.kodiid)
            self.delete_file()
            log.info("Removed: %s" % (self.title))
        else:
            log.info("Couldn't find file: %s" % (self.title))
        Movie.db.remove(self.nrkid)

    def delete_file(self):
        os.remove(os_join(self.path, self.filename))

    def create_file(self):
        with open(os_join(self.path, self.filename), "w") as txt:
            txt.write("plugin://%s/?mode=play&url=tv.nrk.no%s" % (const.addonid, self.nrkid))
        log.debug("File created: %s " % self.title)

    def add_to_lib(self):
        moviedict = rpc("VideoLibrary.GetMovies",
                        properties=["file"],
                        multifilter={"and": [
                              ("filename", "is", self.filename),
                              ("path", "startswith", self.path)]})
        if 'movies' in moviedict:
            self.kodiid = moviedict['movies'][0]['movieid']
            jsonfilepath = os_join(self.path, self.jsonfilename)
            if os.path.exists(jsonfilepath):
                load_playcount("movie", jsonfilepath, self.kodiid)
            self.nonadded = False
            log.info("Movie added: %s" % self.title)
        else:
            self.nonadded = True
            log.info("Movie added, but not scraped: %s" % self.title)
        Movie.db.upsert(self.nrkid, self.title)

    def gen_nfo(self):
        self.delete_file()
        self.create_file()
        movsubid = re.findall(r'/program/(.*?)/.*', self.nrkid)[0]
        movinfodict = scraper.getinfodict(movsubid)
        root = ET.Element("movie")
        ET.SubElement(root, "title").text = movinfodict["fullTitle"]
        ET.SubElement(root, "plot").text = movinfodict["description"]
        ET.SubElement(root, "thumb", aspect="poster").text = movinfodict['images']["webImages"][-1]["imageUrl"]
        fanart = ET.SubElement(root, "fanart")
        ET.SubElement(fanart, "thumb").text = movinfodict['images']["webImages"][-1]["imageUrl"]
        ET.SubElement(root, "runtime").text = re.sub(r"PT(\d+)M.*", r"\1", movinfodict["duration"])
        tree = ET.ElementTree(root)
        tree.write(os_join(self.path, self.nfofilename), xml_declaration=True, encoding='utf-8', method="xml")


class Show(object):
    @classmethod
    def init_databases(cls):
        cls.db = database.MediaDatabase('shows', return_as=cls, store_as=database.LastUpdatedOrderedDict)
        cls.db_excluded = database.MediaDatabase('excluded shows', return_as=cls)
        cls.db_prioritized = database.MediaDatabase('prioritized shows', return_as=cls)

    @classmethod
    def commit_databases(cls):
        cls.db.savetofile()
        cls.db_excluded.savetofile()
        cls.db_prioritized.savetofile()

    def __init__(self, showid, showtitle):
        self.nrkid = showid
        self.title = showtitle
        self.path = uni_join(const.libpath, "NRK shows", stringtofile(self.title))

    def _get_stored_episodes(self):
        stored_episodes = rpc("VideoLibrary.GetEpisodes",
                              properties=["season", "episode", "file", "playcount"],
                              filter={"field": "filename", "operator": "startswith", "value": "%s S" % stringtofile(self.title)})
        self.all_stored_episodes = set()
        self.koala_stored_episodes = dict()
        for epdict in stored_episodes.get('episodes', []):
            episodecode = "S%02dE%02d" % (int(epdict['season']), int(epdict['episode']))
            self.all_stored_episodes.add(episodecode)
            if epdict["file"].startswith(self.path):
                episode = Episode(self.title, epdict["season"], epdict["episode"], kodiid=epdict["episodeid"], playcount=epdict["playcount"])
                self.koala_stored_episodes[episodecode] = episode
        return self.koala_stored_episodes, self.all_stored_episodes

    def _get_new_unav_episodes(self):
        koala_stored_episodes, all_stored_episodes = self._get_stored_episodes()
        available_episodes = scraper.getepisodes(self.nrkid)

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
        Show.db.remove(self.nrkid)

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
        if self.nonadded_episodes:
            Show.db.upsert(self.nrkid, self.title)

    def add_nonadded_eps_to_lib(self, second_attempt=False):
        koala_stored_episodes, all_stored_episodes = self._get_stored_episodes()
        for episode in self.nonadded_episodes:
            episode.add_to_lib(koala_stored_episodes)
        Show.db.upsert(self.nrkid, self.title)

    def _gen_show_nfo(self):
        plot, year, image, in_superuniverse = scraper.getshowinfo(self.nrkid)
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
        tree.write(os_join(self.path, "tvshow.nfo"), xml_declaration=True, encoding='utf-8', method="xml")

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
        self.path = uni_join(const.libpath, "NRK shows", stringtofile(self.showtitle), "Season %s" % self.seasonnr)
        self.filename = "%s %s.strm" % (stringtofile(self.showtitle), self.code)
        self.nfofilename = "%s %s.nfo" % (stringtofile(self.showtitle), self.code)
        self.jsonfilename = "%s %s.json" % (stringtofile(self.showtitle), self.code)

    def remove(self):
        if self.playcount > 0:
            jsonfilepath = os_join(self.path, self.jsonfilename)
            save_playcount(jsonfilepath, self.playcount)
        rpc("VideoLibrary.RemoveEpisode", episodeid=self.kodiid)
        self.delete_file()
        log.info("Removed: %s %s" % (self.showtitle, self.code))

    def delete_file(self):
        os.remove(os_join(self.path, self.filename))

    def create_file(self):
        if not os.path.exists(os_join(self.path)):
            os.makedirs(os_join(self.path))
        with open(os_join(self.path, self.filename), "w") as txt:
            txt.write("plugin://%s/?mode=play&url=tv.nrk%s.no%s" %
                      (const.addonid, "super" if self.in_superuniverse else "", self.nrkid))

    def add_to_lib(self, koala_stored_episodes):
        if self.code in koala_stored_episodes:
            self.kodiid = koala_stored_episodes[self.code].kodiid
            jsonfilepath = os_join(self.path, self.jsonfilename)
            if os.path.exists(jsonfilepath):
                load_playcount("episode", jsonfilepath, self.kodiid)
            self.nonadded = False
            log.info("Episoded added: %s %s" % (self.showtitle, self.code))
        else:
            self.nonadded = True
            log.info("Episoded added, but not scraped: %s %s" % (self.showtitle, self.code))

    def gen_nfo(self):
        episodesubid = re.findall(r'/serie/.*?/(.*?)/.*', self.nrkid)[0]
        epinfodict = scraper.getinfodict(episodesubid)
        root = ET.Element("episodedetails")
        ET.SubElement(root, "title").text = epinfodict["fullTitle"]
        ET.SubElement(root, "showtitle").text = self.showtitle
        ET.SubElement(root, "season").text = str(self.seasonnr)
        ET.SubElement(root, "episode").text = str(self.episodenr)
        ET.SubElement(root, "plot").text = epinfodict["description"]
        ET.SubElement(root, "thumb").text = epinfodict['images']["webImages"][-1]["imageUrl"]
        ET.SubElement(root, "runtime").text = re.sub(r"PT(\d+)M.*", r"\1", epinfodict["duration"])
        tree = ET.ElementTree(root)
        tree.write(os_join(self.path, self.nfofilename), xml_declaration=True, encoding='utf-8', method="xml")


###################
def mapfuncs(func):
    '''1: execute list of functions sent as arg, 2: print traceback otherwise swallowed due to multithreading'''
    try:
        func()
    except:
        log.info(traceback.format_exc())
        raise


def execute(movies_to_remove=(), shows_to_remove=(), movies_to_add=(), shows_to_update=()):
    progress.goto(20)
    for movie in movies_to_remove:
        movie.remove()

    progress.goto(30)
    for show in shows_to_remove:
        show.remove_all_episodes()

    if (movies_to_add or shows_to_update):
        progress.goto(40)
        scraper.setup()
        pool = threading.Pool(10 if settings['multithreading'] else 1)
        create_files = ([movie.create_file for movie in movies_to_add] +
                        [show.update for show in shows_to_update])
        pool.map(mapfuncs, create_files)

        if (movies_to_add or any(show.new_episodes for show in shows_to_update)):
            progress.goto(50)
            monitor.update_video_library()

            progress.goto(60)
            add_to_lib = ([movie.add_to_lib for movie in movies_to_add] +
                          [show.add_eps_to_lib for show in shows_to_update])
            pool.map(mapfuncs, add_to_lib)

            nonadded_movies = [movie for movie in movies_to_add if movie.nonadded]
            shows_w_nonadded = [show for show in shows_to_update if show.nonadded_episodes]

            if (nonadded_movies or shows_w_nonadded):
                progress.goto(70)
                gen_nfos_for_nonadded = ([movie.gen_nfo for movie in nonadded_movies] +
                                         [show.gen_nfos for show in shows_w_nonadded])
                pool.map(mapfuncs, gen_nfos_for_nonadded)

                progress.goto(80)
                monitor.update_video_library()

                progress.goto(90)
                add_nonadded_to_lib = ([movie.add_to_lib for movie in nonadded_movies] +
                                       [show.add_nonadded_eps_to_lib for show in shows_w_nonadded])
                pool.map(mapfuncs, add_nonadded_to_lib)

                progress.goto(100)


def select_mediaitem(mediadb):
    if not mediadb.all:
        dialogs.ok(heading="No %s" % mediadb.name,
                   line1="No %s in database" % (mediadb.name))
        return
    sorted_media = sorted(mediadb.all, key=attrgetter("title"))
    titles = [media.title for media in sorted_media]
    call = dialogs.select(list=titles, heading='Select %s' % mediadb.name[:-1])
    return sorted_media[call] if call != -1 else None


def update_all():
    execute(shows_to_update=Show.db.all)


def remove_all():
    execute(movies_to_remove=Movie.db.all, shows_to_remove=Show.db.all)


def update_single():
    show = select_mediaitem(Show.db)
    if show:
        execute(shows_to_update=[show])


def exclude_show():
    show = select_mediaitem(Show.db)
    if show:
        execute(shows_to_remove=[show])
        Show.db_excluded.upsert(show.nrkid, show.title)


def exclude_movie():
    movie = select_mediaitem(Movie.db)
    if movie:
        execute(movies_to_remove=[movie])
        Movie.db_excluded.upsert(movie.nrkid, movie.title)


def readd_show():
    show = select_mediaitem(Show.db_excluded)
    if show:
        execute(shows_to_update=[show])
        Show.db_excluded.remove(show.nrkid)


def readd_movie():
    movie = select_mediaitem(Movie.db_excluded)
    if movie:
        execute(movies_to_add=movie)
        Movie.db_excluded.remove(movie.nrkid)


def check_watchlist():
    all_ids = set.union(Movie.db.ids, Movie.db_excluded.ids, Show.db.ids, Show.db_excluded.ids)
    progress.goto(10)
    scraper.setup()
    results = scraper.check_watchlist(stored_movies=Movie.db.all, stored_shows=Show.db.all, all_ids=all_ids)
    unav_movies, unav_shows, added_movies, added_shows = results
    unav_movies = [Movie(movie.nrkid, movie.title) for movie in unav_movies]
    unav_shows = [Show(show.nrkid, show.title) for show in unav_shows]
    added_movies = [Movie(movie.nrkid, movie.title) for movie in added_movies]
    added_shows = [Show(show.nrkid, show.title) for show in added_shows]
    return unav_movies, unav_shows, added_movies, added_shows


def only_watchlist():
    unav_movies, unav_shows, added_movies, added_shows = check_watchlist()
    execute(movies_to_remove=unav_movies, shows_to_remove=unav_shows, movies_to_add=added_movies, shows_to_update=added_shows)


def startup():
    unav_movies, unav_shows, added_movies, added_shows = check_watchlist()
    shows_to_update = []
    if settings["check shows on startup"]:
        prioritized = [show for show in Show.db_prioritized.all if show.nrkid in Show.db.ids]
        nonprioritized = [show for show in Show.db.all if show.nrkid not in Show.db_prioritized.ids]
        n = settings["n shows to update"]
        shows_to_update = prioritized + nonprioritized[:n]
    execute(movies_to_remove=unav_movies, shows_to_remove=unav_shows,
            movies_to_add=added_movies, shows_to_update=added_shows+shows_to_update)


def main(action):
    Movie.init_databases()
    Show.init_databases()

    if action == "remove_all" and not (Show.db.all or Movie.db.all):
        dialogs.ok(heading="No media", line1="No media seems to have been added")
        return
    elif action in ["prioritize", "exclude_show", "readd_show", "update_single", "update_all"] and not Show.db.all:
        dialogs.ok(heading="No shows", line1="No shows seem to have been added")
        return
    elif action in ["exclude_movie", "readd_movie"] and not Movie.db.all:
        dialogs.ok(heading="No movies", line1="No movies seem to have been added")
        return

    library_actions = {
        "update_all": update_all,
        "remove_all": remove_all,
        "update_single": update_single,
        "exclude_show": exclude_show,
        "exclude_movie": exclude_movie,
        "readd_show": readd_show,
        "readd_movie": readd_movie,
        "watchlist": only_watchlist,
        "startup": startup
        }
    action_func = library_actions[action]

    try:
        progress.create(heading="Updating NRK", force=False if action == "startup" else True)
        xbmcgui.Window(10000).setProperty("Koala NRK running", "true")
        action_func()
    except:
        raise
    finally:
        progress.close()
        Movie.commit_databases()
        Show.commit_databases()
        xbmcgui.Window(10000).setProperty("Koala NRK running", "false")
