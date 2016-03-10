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
from operator import attrgetter

from . utils import (os_join, uni_join, stringtofile)
from . import scraper
from . import constants as const
from . import database
from .xbmcwrappers import (rpc, log, monitor, settings, progress, dialogs)

###################
class SharedMediaMethods(object):
    def load_playcount(self):
        jsonfilepath = os_join(self.path, self.jsonfilename)
        if os.path.exists(jsonfilepath):
            with open(jsonfilepath, "r") as f:
                playcount = json.load(f)
            rpc("VideoLibrary.Set%sDetails" % self.mediatype.capitalize(),
                **{"".join([self.mediatype, "id"]): self.kodiid, "playcount": playcount})
            os.remove(jsonfilepath)

    def save_playcount(self):
        if self.playcount > 0:
            jsonfilepath = os_join(self.path, self.jsonfilename)
            with open(jsonfilepath, "w") as f:
                json.dump(self.playcount, f)

    def delete_strm(self):
        os.remove(os_join(self.path, self.strmfilename))
        try:
            os.removedirs(os_join(self.path))
        except OSError:
            pass

    def remove_from_lib(self):
        rpc("VideoLibrary.Remove%s" % self.mediatype.capitalize(), **{"".join([self.mediatype, "id"]): self.kodiid})

    def write_strm(self):
        if not os.path.exists(os_join(self.path)):
            os.makedirs(os_join(self.path))
        with open(os_join(self.path, self.strmfilename), "w") as txt:
            txt.write("plugin://%s/?mode=play&url=tv.nrk%s.no%s" %
                      (const.addonid, "super" if self.in_superuniverse else "", self.urlid))

    def write_nfo(self, root):
        tree = ET.ElementTree(root)
        tree.write(os_join(self.path, self.nfofilename), xml_declaration=True, encoding='utf-8', method="xml")


class Movie(SharedMediaMethods):
    @classmethod
    def init_databases(cls):
        cls.db = database.MediaDatabase('movies', return_as=cls)
        cls.db_excluded = database.MediaDatabase('excluded movies', return_as=cls)

    @classmethod
    def commit_databases(cls):
        cls.db.savetofile()
        cls.db_excluded.savetofile()

    def __init__(self, movieid, movietitle):
        self.mediatype = "movie"
        self.urlid = movieid
        self.title = movietitle
        self.path = uni_join(const.libpath, "%s movies" % const.provider)
        self.strmfilename = "%s.strm" % stringtofile(self.title)
        self.nfofilename = "%s.nfo" % stringtofile(self.title)
        self.jsonfilename = "%s.json" % stringtofile(self.title)
        self.in_superuniverse = False

    def _get_lib_entry(self):
        moviesdict = rpc("VideoLibrary.GetMovies",
                         properties=["file", 'playcount'],
                         multifilter={"and": [
                              ("filename", "is", self.strmfilename),
                              ("path", "startswith", self.path)]})
        if 'movies' not in moviesdict:
            return None
        else:
            return moviesdict['movies'][0]

    def _gen_nfo(self):
        super(Movie, self).delete_strm()
        super(Movie, self).write_strm()
        movsubid = re.findall(r'/program/(.*?)/.*', self.urlid)[0]
        movinfodict = scraper.getinfodict(movsubid)
        root = ET.Element("movie")
        ET.SubElement(root, "title").text = movinfodict["fullTitle"]
        ET.SubElement(root, "plot").text = movinfodict["description"]
        ET.SubElement(root, "thumb", aspect="poster").text = movinfodict['images']["webImages"][-1]["imageUrl"]
        fanart = ET.SubElement(root, "fanart")
        ET.SubElement(fanart, "thumb").text = movinfodict['images']["webImages"][-1]["imageUrl"]
        ET.SubElement(root, "runtime").text = re.sub(r"PT(\d+)M.*", r"\1", movinfodict["duration"])
        super(Movie, self).write_nfo(root)

    def remove(self):
        log.info("Removing movie: %s" % self.title)
        dbinfo = self._get_lib_entry()
        if not dbinfo:
            log.info("Couldn't find in library: %s" % (self.title))
        else:
            self.kodiid = dbinfo['movieid']
            self.playcount = dbinfo['playcount']
            super(Movie, self).save_playcount()
            super(Movie, self).remove_from_lib()
            super(Movie, self).delete_strm()
        Movie.db.remove(self.urlid)
        log.info("Finished removing movie: %s" % self.title)

    def add(self):
        log.info("Adding movie: %s" % self.title)
        super(Movie, self).write_strm()
        log.info("STRM created, waiting for lib update: %s" % self.title)
        yield

        dbinfo = self._get_lib_entry()
        if not dbinfo:
            self._gen_nfo()
            log.info("NFO created, waiting for second lib update: %s" % self.title)
            yield

            dbinfo = self._get_lib_entry()
            if not dbinfo:
                log.info("failed to add movie")
                return
        self.kodiid = dbinfo['movieid']
        super(Movie, self).load_playcount()
        log.info("Finished adding movie: %s" % self.title)
        Movie.db.upsert(self.urlid, self.title)


class Show(SharedMediaMethods):
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
        self.mediatype = "show"
        self.urlid = showid
        self.title = showtitle
        self.path = uni_join(const.libpath, "%s shows" % const.provider, stringtofile(self.title))
        self.nfofilename = "tvshow.nfo"

    def _get_stored_episodes(self):
        stored_episodes = rpc("VideoLibrary.GetEpisodes",
                              properties=["season", "episode", "file", "playcount"],
                              filter={"field": "filename", "operator": "startswith", "value": "%s S" % stringtofile(self.title)})
        all_stored_episodes = set()
        koala_stored_episodes = dict()
        for epdict in stored_episodes.get('episodes', []):
            episodecode = "S%02dE%02d" % (int(epdict['season']), int(epdict['episode']))
            all_stored_episodes.add(episodecode)
            if epdict["file"].startswith(self.path):
                episode = Episode(self.title, epdict["season"], epdict["episode"],
                                  kodiid=epdict["episodeid"], playcount=epdict["playcount"])
                koala_stored_episodes[episodecode] = episode
        return koala_stored_episodes, all_stored_episodes

    def _get_new_unav_episodes(self):
        koala_stored_episodes, all_stored_episodes = self._get_stored_episodes()
        available_episodes = scraper.getepisodes(self.urlid)

        unav_episodes = [episode for episode in koala_stored_episodes.values()
                         if episode.code not in available_episodes]

        new_episodes = [Episode(self.title, episode['seasonnr'], episode['episodenr'],
                                urlid=episode['urlid'], in_superuniverse=episode['in_superuniverse'])
                        for episodecode, episode in available_episodes.items()
                        if episodecode not in all_stored_episodes]

        return unav_episodes, new_episodes

    def _remove_episodes(self, episodes):
        for episode in episodes:
            episode.remove()

    def _write_strms(self, episodes):
        for episode in episodes:
            episode.write_strm()

    def _check_eps_added(self, episodes):
        koala_stored_episodes, _ = self._get_stored_episodes()
        nonadded_episodes = []
        for episode in episodes:
            episode.check_added(koala_stored_episodes)
            if episode.nonadded:
                nonadded_episodes.append(episode)
        return nonadded_episodes

    def _gen_nfos(self, nonadded_episodes):
        koala_stored_episodes, _ = self._get_stored_episodes()
        if not koala_stored_episodes:
            self._gen_show_nfo()
        for episode in nonadded_episodes:
            episode.gen_nfo()

    def _gen_show_nfo(self):
        plot, year, image, in_superuniverse = scraper.getshowinfo(self.urlid)
        root = ET.Element("tvshow")
        ET.SubElement(root, "title").text = self.title
        ET.SubElement(root, "year").text = year
        ET.SubElement(root, "plot").text = plot
        ET.SubElement(root, "thumb", aspect="poster").text = image
        fanart = ET.SubElement(root, "fanart")
        ET.SubElement(fanart, "thumb").text = image
        if in_superuniverse:
            ET.SubElement(root, "genre").text = "Children"
        super(Show, self).write_nfo(root)

    def _load_eps_playcount(self, episodes):
        for episode in episodes:
            episode.load_playcount()

    def remove(self):
        log.info("Removing show: %s" % self.title)
        koala_stored_episodes, _ = self._get_stored_episodes()
        for episode in koala_stored_episodes.values():
            episode.remove()
        Show.db.remove(self.urlid)
        log.info("Finished removing show: %s" % self.title)

    def update_add(self):
        log.info("Updating show: %s" % self.title)
        unav_episodes, new_episodes = self._get_new_unav_episodes()
        if unav_episodes:
            self._remove_episodes(unav_episodes)
        if new_episodes:
            self._write_strms(new_episodes)
            log.info("STRMs created, waiting for lib update: %s" % self.title)
            yield

            nonadded_episodes = self._check_eps_added(new_episodes)
            if nonadded_episodes:
                self._gen_nfos(nonadded_episodes)
                log.info("NFOs created, waiting for second lib update: %s" % self.title)
                yield

            self._load_eps_playcount(new_episodes)
        Show.db.upsert(self.urlid, self.title)
        log.info("Finished updating show: %s" % self.title)


class Episode(SharedMediaMethods):
    def __init__(self, showtitle, seasonnr, episodenr, in_superuniverse=None, urlid=None, kodiid=None, playcount=0):
        self.mediatype = "episode"
        self.showtitle = showtitle
        self.seasonnr = int(seasonnr)
        self.episodenr = int(episodenr)
        self.urlid = urlid
        self.kodiid = kodiid
        self.code = "S%02dE%02d" % (seasonnr, episodenr)
        self.in_superuniverse = in_superuniverse
        self.playcount = int(playcount)
        self.path = uni_join(const.libpath, "%s shows" % const.provider, stringtofile(self.showtitle), "Season %s" % self.seasonnr)
        self.strmfilename = "%s %s.strm" % (stringtofile(self.showtitle), self.code)
        self.nfofilename = "%s %s.nfo" % (stringtofile(self.showtitle), self.code)
        self.jsonfilename = "%s %s.json" % (stringtofile(self.showtitle), self.code)

    def remove(self):
        super(Episode, self).save_playcount()
        super(Episode, self).remove_from_lib()
        super(Episode, self).delete_strm()

    def load_playcount(self):
        super(Episode, self).load_playcount()

    def check_added(self, koala_stored_episodes):
        if self.code not in koala_stored_episodes:
            self.nonadded = True
        else:
            self.kodiid = koala_stored_episodes[self.code].kodiid
            self.nonadded = False
            log.info("Episode added: %s %s" % (self.showtitle, self.code))

    def gen_nfo(self):
        super(Episode, self).delete_strm()
        super(Episode, self).write_strm()
        episodesubid = re.findall(r'/serie/.*?/(.*?)/.*', self.urlid)[0]
        epinfodict = scraper.getinfodict(episodesubid)
        root = ET.Element("episodedetails")
        ET.SubElement(root, "title").text = epinfodict["fullTitle"]
        ET.SubElement(root, "showtitle").text = self.showtitle
        ET.SubElement(root, "season").text = str(self.seasonnr)
        ET.SubElement(root, "episode").text = str(self.episodenr)
        ET.SubElement(root, "plot").text = epinfodict["description"]
        ET.SubElement(root, "thumb").text = epinfodict['images']["webImages"][-1]["imageUrl"]
        ET.SubElement(root, "runtime").text = re.sub(r"PT(\d+)M.*", r"\1", epinfodict["duration"])
        super(Episode, self).write_nfo(root)


###################
def mapfuncs(func):
    '''1: execute list of functions sent as arg, 2: print traceback otherwise swallowed due to multithreading'''
    try:
        next(func)
    except StopIteration:
        return False
    except:
        log.info(traceback.format_exc())
        raise
    return True


def execute(movies_to_remove=(), shows_to_remove=(), movies_to_add=(), shows_to_update_add=()):
    progress.goto(20)
    for movie in movies_to_remove:
        movie.remove()

    progress.goto(30)
    for show in shows_to_remove:
        show.remove()

    if (movies_to_add or shows_to_update_add):
        progress.goto(40)

        pool = threading.Pool(10 if settings['multithreading'] else 1)

        # 1 - Create/delete STRMs
        # All
        # For added movies: generate STRMs.
        # For shows to update: check ep. availability, delete STRMs for unavailable episodes generate STRMs for new episodes
        # For added shows: get available episodes, generate STRMs for all episodes
        step1 = ([movie.add() for movie in movies_to_add] +
                 [show.update_add() for show in shows_to_update_add])
        progress.goto(50)
        results = pool.map(mapfuncs, step1)

        # 2 - Load playcount or generate NFO
        # If any movies in movies_to_add or any shows with new_episodes in shows_to_update_add
        # For movies: check that movie was added to library. if so: load playcount, if not: generate NFO
        # For shows: check that new episodes were added to library. if so: load playcount, if not: generate NFOs
        step2 = [func for (func, generator_active) in zip(step1, results) if generator_active]
        if any(step2):
            progress.goto(60)
            monitor.update_video_library()
            progress.goto(70)
            results = pool.map(mapfuncs, step2)

            # 3 - Load playcount 2
            # If any nonadded movies or shows with nonadded_episodes
            # Load playcount for movies/episodes added via NFO
            step3 = [func for (func, generator_active) in zip(step2, results) if generator_active]
            if any(step3):
                progress.goto(80)
                monitor.update_video_library()
                progress.goto(90)
                pool.map(mapfuncs, step3)

    progress.goto(99)


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
    execute(shows_to_update_add=Show.db.all)


def remove_all():
    execute(movies_to_remove=Movie.db.all, shows_to_remove=Show.db.all)


def update_single():
    show = select_mediaitem(Show.db)
    if show:
        execute(shows_to_update_add=[show])


def exclude_show():
    show = select_mediaitem(Show.db)
    if show:
        execute(shows_to_remove=[show])
        Show.db_excluded.upsert(show.urlid, show.title)


def exclude_movie():
    movie = select_mediaitem(Movie.db)
    if movie:
        execute(movies_to_remove=[movie])
        Movie.db_excluded.upsert(movie.urlid, movie.title)


def readd_show():
    show = select_mediaitem(Show.db_excluded)
    if show:
        execute(shows_to_update_add=[show])
        Show.db_excluded.remove(show.urlid)


def readd_movie():
    movie = select_mediaitem(Movie.db_excluded)
    if movie:
        execute(movies_to_add=[movie])
        Movie.db_excluded.remove(movie.urlid)


def check_watchlist():
    all_ids = set.union(Movie.db.ids, Movie.db_excluded.ids, Show.db.ids, Show.db_excluded.ids)
    progress.goto(10)
    scraper.setup()
    results = scraper.check_watchlist(stored_movies=Movie.db.all, stored_shows=Show.db.all, all_ids=all_ids)
    unav_movies, unav_shows, added_movies, added_shows = results
    unav_movies = [Movie(movie.urlid, movie.title) for movie in unav_movies]
    unav_shows = [Show(show.urlid, show.title) for show in unav_shows]
    added_movies = [Movie(movie.urlid, movie.title) for movie in added_movies]
    added_shows = [Show(show.urlid, show.title) for show in added_shows]
    return unav_movies, unav_shows, added_movies, added_shows


def only_watchlist():
    unav_movies, unav_shows, added_movies, added_shows = check_watchlist()
    execute(movies_to_remove=unav_movies, shows_to_remove=unav_shows, movies_to_add=added_movies, shows_to_update_add=added_shows)


def startup():
    unav_movies, unav_shows, added_movies, added_shows = check_watchlist()
    shows_to_update_add = []
    if settings["shows on startup"]:
        prioritized = [show for show in Show.db_prioritized.all if show.urlid in Show.db.ids]
        nonprioritized = [show for show in Show.db.all if show.urlid not in Show.db_prioritized.ids]
        n = settings["n shows to update"]
        shows_to_update_add = prioritized + nonprioritized[:n]
    execute(movies_to_remove=unav_movies, shows_to_remove=unav_shows,
            movies_to_add=added_movies, shows_to_update_add=added_shows+shows_to_update_add)


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
        progress.create(heading="Updating %s" % const.provider, force=False if action == "startup" else True)
        action_func()
    except:
        raise
    finally:
        progress.close()
        Movie.commit_databases()
        Show.commit_databases()
