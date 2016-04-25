#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
from __future__ import absolute_import
import multiprocessing.dummy as threading
import os
import re
from functools import partial
import traceback
import types
import json
import xml.etree.ElementTree as ET
from operator import attrgetter

from . utils import (os_join, uni_join, stringtofile)
from . import scraper
from . import constants as const
from . import database
from .xbmcwrappers import (rpc, log, ScanMonitor, settings, ProgressDialog, dialogs)

###################
class SharedMediaMethods(object):
    def __repr__(self):
        return repr(self.title)

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

    def delete_htm(self):
        os.remove(os_join(self.path, self.htmfilename))
        try:
            os.removedirs(os_join(self.path))
        except OSError:
            pass

    def remove_from_lib(self):
        rpc("VideoLibrary.Remove%s" % self.mediatype.capitalize(), **{"".join([self.mediatype, "id"]): self.kodiid})

    def write_htm(self):
        if not os.path.exists(os_join(self.path)):
            os.makedirs(os_join(self.path))
        with open(os_join(self.path, self.htmfilename), "w") as txt:
            txt.write('<meta http-equiv="REFRESH" content="0;'
                      'url=http://tv.nrk%s.no%s"> <body bgcolor="#ffffff">' %
                      ("super" if self.in_superuniverse else "", self.urlid))

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

    def __init__(self, urlid, title):
        self.mediatype = "movie"
        self.urlid = urlid
        self.title = title
        self.path = uni_join(const.libpath, "%s movies" % const.provider)
        self.htmfilename = "%s.htm" % stringtofile(self.title)
        self.nfofilename = "%s.nfo" % stringtofile(self.title)
        self.jsonfilename = "%s.json" % stringtofile(self.title)
        self.in_superuniverse = False

    def _get_lib_entry(self):
        moviesdict = rpc("VideoLibrary.GetMovies",
                         properties=["file", 'playcount'],
                         multifilter={"and": [
                              ("filename", "is", self.htmfilename),
                              ("path", "startswith", self.path)]})
        if 'movies' not in moviesdict:
            return None
        else:
            return moviesdict['movies'][0]

    def _gen_nfo(self):
        super(Movie, self).delete_htm()
        super(Movie, self).write_htm()
        movsubid = re.findall(r'/program/(.*?)/.*', self.urlid)[0]
        movinfodict = scraper.getinfodict(movsubid)
        root = ET.Element("movie")
        ET.SubElement(root, "title").text = self.title
        ET.SubElement(root, "plot").text = movinfodict["plot"]
        ET.SubElement(root, "thumb", aspect="poster").text = movinfodict["art"]
        fanart = ET.SubElement(root, "fanart")
        ET.SubElement(fanart, "thumb").text = movinfodict["art"]
        ET.SubElement(root, "runtime").text = movinfodict["runtime"]
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
            super(Movie, self).delete_htm()
        Movie.db.remove(self.urlid)
        if settings["added_notifications"]:
            dialogs.notification(heading="%s movie removed:" % const.provider, message=self.title)
        log.info("Finished removing movie: %s" % self.title)

    def update_add(self):
        log.info("Adding movie: %s" % self.title)
        super(Movie, self).write_htm()
        log.info("htm created, waiting for lib update: %s" % self.title)
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
        if settings["added_notifications"]:
            dialogs.notification(heading="%s movie added:" % const.provider, message=self.title)
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

    def __init__(self, urlid, title):
        self.mediatype = "show"
        self.urlid = urlid
        self.title = title
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

    def _write_htms(self, episodes):
        for episode in episodes:
            episode.write_htm()

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
        infodict = scraper.getshowinfo(self.urlid)
        root = ET.Element("tvshow")
        ET.SubElement(root, "title").text = self.title
        ET.SubElement(root, "year").text = infodict["year"]
        ET.SubElement(root, "plot").text = infodict["plot"]
        ET.SubElement(root, "thumb", aspect="poster").text = infodict["art"]
        fanart = ET.SubElement(root, "fanart")
        ET.SubElement(fanart, "thumb").text = infodict["art"]
        if infodict["in_superuniverse"]:
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
            self._write_htms(new_episodes)
            log.info("htms created, waiting for lib update: %s" % self.title)
            yield

            nonadded_episodes = self._check_eps_added(new_episodes)
            if nonadded_episodes:
                self._gen_nfos(nonadded_episodes)
                log.info("NFOs created, waiting for second lib update: %s, %s" %
                         (self.title, sorted(nonadded_episodes, key=attrgetter('code'))))
                yield

            self._load_eps_playcount(new_episodes)
            if settings["added_notifications"]:
                if len(new_episodes) == 1:
                    message = "Added episode: %s" % new_episodes[0].code
                elif len(new_episodes) <= 3:
                    message = "Added episodes: %s" % ", ".join(sorted([ep.code for ep in new_episodes]))
                else:
                    message = "Added %s episodes" % len(new_episodes)
                dialogs.notification(heading="%s updated:" % self.title, message=message)
            log.info("Added episodes: %s, %s" % (self.title, sorted(new_episodes, key=attrgetter('code'))))

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
        self.htmfilename = "%s %s.htm" % (stringtofile(self.showtitle), self.code)
        self.nfofilename = "%s %s.nfo" % (stringtofile(self.showtitle), self.code)
        self.jsonfilename = "%s %s.json" % (stringtofile(self.showtitle), self.code)

    def __repr__(self):
        return self.code

    def remove(self):
        super(Episode, self).save_playcount()
        super(Episode, self).remove_from_lib()
        super(Episode, self).delete_htm()

    def load_playcount(self):
        super(Episode, self).load_playcount()

    def check_added(self, koala_stored_episodes):
        if self.code not in koala_stored_episodes:
            self.nonadded = True
        else:
            self.kodiid = koala_stored_episodes[self.code].kodiid
            self.nonadded = False

    def gen_nfo(self):
        super(Episode, self).delete_htm()
        super(Episode, self).write_htm()
        episodesubid = re.findall(r'/serie/.*?/(.*?)/.*', self.urlid)[0]
        infodict = scraper.getinfodict(episodesubid)
        root = ET.Element("episodedetails")
        ET.SubElement(root, "title").text = infodict["title"]
        ET.SubElement(root, "showtitle").text = self.showtitle
        ET.SubElement(root, "season").text = unicode(self.seasonnr)
        ET.SubElement(root, "episode").text = unicode(self.episodenr)
        ET.SubElement(root, "plot").text = infodict["plot"]
        ET.SubElement(root, "thumb").text = infodict['art']
        ET.SubElement(root, "runtime").text = infodict["runtime"]
        super(Episode, self).write_nfo(root)


###################
def execute(getwatchlist=False, to_remove=None, to_update_add=None):
    '''Executes libary udpates'''
    def mapfuncs(func):
        '''1: execute next step in list of generators sent as arg,
           2: print traceback otherwise swallowed due to multithreading
           3: Indicate whether function is finished (stopiteration), errored (exception), or unfinished
           '''
        try:
            next(func)
        except StopIteration:
            return None
        except Exception as exc:
            log.info(traceback.format_exc())
            return exc
        return func

    if not to_remove:
        to_remove = []
    if not to_update_add:
        to_update_add = []

    pool = None
    progress = ProgressDialog()
    monitor = ScanMonitor()

    try:
        progress.create(heading="Updating %s" % const.provider)
        progress.goto(10)

        if getwatchlist or any(item.mediatype == "show" for item in to_update_add):
            scraper.reqs.load_cookies()

        progress.goto(20)
        if getwatchlist:
            available_movies, available_shows = scraper.getwatchlist()
            unav_movies = [movie for movie in Movie.db.all if movie.urlid not in available_movies]
            log.info("unavailable_movies:\n %s" % unav_movies)
            unav_shows = [show for show in Show.db.all if show.urlid not in available_shows]
            log.info("unavailable_shows:\n %s" % unav_shows)
            to_remove.extend(unav_movies + unav_shows)

            movie_ids = set.union(Movie.db.ids, Movie.db_excluded.ids)
            added_movies = [Movie(urlid, title) for urlid, title in available_movies.items() if urlid not in movie_ids]
            log.info("added_movies:\n %s" % added_movies)
            show_ids = set.union(Show.db.ids, Show.db_excluded.ids)
            added_shows = [Show(urlid, title) for urlid, title in available_shows.items() if urlid not in show_ids]
            log.info("added_shows:\n %s" % added_shows)
            to_update_add.extend(added_movies + added_shows)

        progress.goto(30)
        for item in to_remove:
            item.remove()

        # filter any mediaitem out of to_update that is slated for removal
        to_update_add = [item for item in to_update_add if item not in to_remove]

        errors = []
        progress.goto(40)
        pool = threading.Pool(10 if settings['multithreading'] else 1)
        step1_funcs = [item.update_add() for item in to_update_add]
        # 1 - Create/delete htms
        # All
        # For added movies: generate htms.
        # For shows to update: check ep. availability, delete htms for unavailable episodes generate htms for new episodes
        # For added shows: get available episodes, generate htms for all episodes
        # For movies & shows to remove step 1 is entire process

        step1_results = pool.map(mapfuncs, step1_funcs)
        errors.extend(result for result in step1_results if isinstance(result, Exception))
        step2_funcs = [result for result in step1_results if isinstance(result, types.GeneratorType)]

        if step2_funcs:
            # 2 - Load playcount or generate NFO
            # If any movies in movies_to_add or any shows with new_episodes
            # For movies: check that movie was added to library. if so: load playcount, if not: generate NFO
            # For shows: check that new episodes were added to library. if so: load playcount, if not: generate NFOs
            progress.goto(50)
            monitor.update_video_library()
            progress.goto(60)
            step2_results = pool.map(mapfuncs, step2_funcs)
            errors.extend(result for result in step2_results if isinstance(result, Exception))
            step3_funcs = [result for result in step2_results if isinstance(result, types.GeneratorType)]

            if step3_funcs:
                # 3 - Load playcount 2
                # If any nonadded movies or shows with nonadded_episodes
                # Load playcount for movies/episodes added via NFO
                progress.goto(70)
                monitor.update_video_library()
                progress.goto(80)
                step3_results = pool.map(mapfuncs, step3_funcs)
                errors.extend(result for result in step3_results if isinstance(result, Exception))

        if errors:
            raise Exception("Multithreaded execution finished with %s error(s): \n"
                            "%s. See traceback(s) above." % (len(errors), ", ".join([unicode(error) for error in errors])))

    finally:
        if pool:
            pool.close()
        progress.close()
        scraper.reqs.save_cookies()


def select_mediaitem(mediadb):
    sorted_media = sorted(mediadb.all, key=attrgetter("title"))
    titles = [media.title for media in sorted_media]
    call = dialogs.select(list=titles, heading='Select %s' % mediadb.name[:-1])
    return sorted_media[call] if call != -1 else None


def prioritize():
    sorted_shows = sorted(Show.db.all, key=attrgetter("title"))
    titles = []
    for show in sorted_shows:
        if show.urlid in Show.db_prioritized.ids:
            titles.append("[Prioritized] %s" % show.title)
        else:
            titles.append(show.title)
    while True:
        call = dialogs.select('Select prioritized shows', titles)
        if call == -1:
            break
        show = sorted_shows[call]
        if show.urlid not in Show.db_prioritized.ids:
            Show.db_prioritized.upsert(show.urlid, show.title)
            titles[call] = "[Prioritized] %s" % show.title
        else:
            Show.db_prioritized.remove(show.urlid)
            titles[call] = show.title


def update_all():
    execute(to_update_add=Show.db.all)


def remove_all():
    execute(to_remove=Movie.db.all + Show.db.all)


def update_single():
    show = select_mediaitem(Show.db)
    if show:
        execute(to_update_add=[show])


def exclude_show():
    show = select_mediaitem(Show.db)
    if show:
        execute(to_remove=[show])
        Show.db_excluded.upsert(show.urlid, show.title)


def exclude_movie():
    movie = select_mediaitem(Movie.db)
    if movie:
        execute(to_remove=[movie])
        Movie.db_excluded.upsert(movie.urlid, movie.title)


def readd_show():
    show = select_mediaitem(Show.db_excluded)
    if show:
        execute(to_update_add=[show])
        Show.db_excluded.remove(show.urlid)


def readd_movie():
    movie = select_mediaitem(Movie.db_excluded)
    if movie:
        execute(to_update_add=[movie])
        Movie.db_excluded.remove(movie.urlid)


def watchlist():
    execute(getwatchlist=True)


def startup_and_schedule(action):
    shows_to_update_add = []
    if settings["shows on %s" % action]:
        prioritized = [show for show in Show.db_prioritized.all if show.urlid in Show.db.ids]
        nonprioritized = [show for show in Show.db.all if show.urlid not in Show.db_prioritized.ids]
        if not settings["all shows on %s" % action]:
            n = settings["n shows on %s" % action]
            nonprioritized = nonprioritized[:n]
        shows_to_update_add = prioritized + nonprioritized
    execute(getwatchlist=settings["watchlist on %s" % action], to_update_add=shows_to_update_add)


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

    startup = partial(startup_and_schedule, action="startup")
    schedule = partial(startup_and_schedule, action="schedule")
    library_actions = {
        "prioritize": prioritize,
        "update_all": update_all,
        "remove_all": remove_all,
        "update_single": update_single,
        "exclude_show": exclude_show,
        "exclude_movie": exclude_movie,
        "readd_show": readd_show,
        "readd_movie": readd_movie,
        "watchlist": watchlist,
        "startup": startup,
        "schedule": schedule,
        "startup_debug": startup,
        "schedule_debug": schedule,
        }
    action_func = library_actions[action]
    try:
        action_func()
    except:
        raise
    finally:
        Movie.commit_databases()
        Show.commit_databases()
