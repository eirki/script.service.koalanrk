#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
import re
import json
from bs4 import BeautifulSoup
from operator import attrgetter

from . utils import (os_join, uni_join, stringtofile)
from . import scraper
from . import constants as const
from .xbmcwrappers import (rpc, log, settings, dialogs)


class Base(object):
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

    def write_htm(self):
        if not os.path.exists(os_join(self.path)):
            os.makedirs(os_join(self.path))
        with open(os_join(self.path, self.htmfilename), "w") as txt:
            txt.write('<meta http-equiv="REFRESH" content="0;'
                      'url=%s"> <body bgcolor="#ffffff">' % self.url)


class Movie(Base):
    def __init__(self, urlid, title):
        self.mediatype = "movie"
        self.urlid = urlid
        self.title = title
        self.path = uni_join(const.libpath, "%s movies" % const.provider)
        self.htmfilename = "%s.htm" % stringtofile(self.title)
        self.nfofilename = "%s.nfo" % stringtofile(self.title)
        self.jsonfilename = "%s.json" % stringtofile(self.title)
        self.url = "http://tv.nrk.no%s?autostart=true" % self.urlid

    def __repr__(self):
        return repr(self.title)

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

    def _write_nfo(self):
        super(Movie, self).delete_htm()
        super(Movie, self).write_htm()

        movsubid = re.findall(r'/program/(.*?)/.*', self.urlid)[0]
        metadata = scraper.getinfodict(movsubid)

        soup = BeautifulSoup("<?xml version='1.0' encoding='utf-8'?>")
        root = soup.new_tag("movie")
        soup.append(root)

        root.append(soup.new_tag("title"))
        root.title.string = self.title

        # root.append(soup.new_tag("year"))
        # root.year.string = unicode(self.year)

        root.append(soup.new_tag("runtime"))
        root.runtime.string = unicode(metadata["runtime"])

        root.append(soup.new_tag("plot"))
        root.plot.string = metadata["plot"]

        root.append(soup.new_tag("thumb", aspect="poster"))
        root.thumb.string = metadata["art"]

        root.append(soup.new_tag("fanart"))
        root.fanart.append(soup.new_tag("thumb"))
        root.fanart.thumb.string = metadata["art"]

        with open(os.path.join(self.path, self.nfofilename), "w") as nfo:
            nfo.write(soup.prettify().encode("utf-8"))

    def generate_removal_task(self, db_stored, exclude=False, db_excluded=None):
        def remove(self):
            log.info("Removing movie: %s" % self.title)
            dbinfo = self._get_lib_entry()
            if not dbinfo:
                log.info("Couldn't find in library: %s" % (self.title))
            else:
                self.kodiid = dbinfo['movieid']
                self.playcount = dbinfo['playcount']
                super(Movie, self).save_playcount()
                self.remove_from_lib()
                super(Movie, self).delete_htm()
            db_stored.remove(self.urlid)
            if exclude:
                db_excluded.add(self.urlid)
            log.info("Finished removing movie: %s" % self.title)
        self.task = remove
        self.finished = False
        self.exception = None

    def generate_update_task(self, db_stored, session, readd=False, db_excluded=None):
        def add(self):
            log.info("Adding movie: %s" % self.title)
            super(Movie, self).write_htm()
            log.info("htm created, waiting for lib update: %s" % self.title)
            yield

            dbinfo = self._get_lib_entry()
            if not dbinfo:
                self._write_nfo()
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
            db_stored.add(self.urlid)
            if readd:
                db_excluded.remove(self.urlid)
            log.info("Finished adding movie: %s" % self.title)
        self.task = add()
        self.finished = False
        self.exception = None

    def remove_from_lib(self):
        rpc("VideoLibrary.RemoveMovie", movieid=self.kodiid)


class Show(object):
    def __init__(self, urlid, title):
        self.mediatype = "show"
        self.urlid = urlid
        self.title = title
        self.path = uni_join(const.libpath, "%s shows" % const.provider, stringtofile(self.title))
        self.nfofilename = "tvshow.nfo"

    def __repr__(self):
        return repr(self.title)

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

    def _confirm_added(self, episodes):
        koala_stored_episodes, _ = self._get_stored_episodes()
        show_in_library = True if koala_stored_episodes else False
        nonadded_episodes = []
        for episode in episodes:
            episode.check_added(koala_stored_episodes)
            if episode.nonadded:
                nonadded_episodes.append(episode)
        return show_in_library, nonadded_episodes

    def _write_nfo(self):
        metadata = scraper.getshowinfo(self.urlid)

        soup = BeautifulSoup("<?xml version='1.0' encoding='utf-8'?>")
        root = soup.new_tag("movie")
        soup.append(root)

        root.append(soup.new_tag("title"))
        root.title.string = self.title

        root.append(soup.new_tag("year"))
        root.year.string = unicode(metadata["year"])

        root.append(soup.new_tag("plot"))
        root.plot.string = metadata["plot"]

        if metadata["in_superuniverse"]:
            root.append(soup.new_tag("genre"))
            root.genre.string = "Children"

        root.append(soup.new_tag("thumb", aspect="poster"))
        root.thumb.string = metadata["art"]

        root.append(soup.new_tag("fanart"))
        root.fanart.append(soup.new_tag("thumb"))
        root.fanart.thumb.string = metadata["art"]

        with open(os.path.join(self.path, self.nfofilename), "w") as nfo:
            nfo.write(soup.prettify().encode("utf-8"))

    def _load_eps_playcount(self, episodes):
        for episode in episodes:
            episode.load_playcount()

    def generate_removal_task(self, db_stored, exclude=False, db_excluded=None):
        def remove(self):
            log.info("Removing show: %s" % self.title)
            koala_stored_episodes, _ = self._get_stored_episodes()
            for episode in koala_stored_episodes.values():
                episode.save_playcount()
                episode.delete_htm()
                episode.remove_from_lib()
            db_stored.remove(self.urlid)
            log.info("Finished removing show: %s" % self.title)
            if exclude:
                db_excluded.add(self)
            log.info("Removed episodes: %s, %s" % (self.title, sorted(koala_stored_episodes, key=attrgetter('code'))))
            log.info("Finished removing show: %s" % self.title)
        self.task = remove
        self.finished = False
        self.exception = None

    def generate_update_task(self, db_stored, session, readd=False, db_excluded=None):
        def update_add():
            log.info("Updating show: %s" % self.title)
            unav_episodes, new_episodes = self._get_new_unav_episodes()
            for episode in unav_episodes:
                episode.save_playcount()
                episode.delete_htm()
                episode.remove_from_lib()
            if new_episodes:
                for episode in new_episodes:
                    episode.write_htm()
                log.info("htms created, waiting for lib update: %s" % self.title)
                yield

                show_in_library, nonadded_episodes = self._confirm_added(new_episodes)
                if not show_in_library:
                    self._write_nfo()
                for episode in nonadded_episodes:
                    episode.write_nfo()
                if nonadded_episodes or not show_in_library:
                    log.info("NFOs created, waiting for second lib update: %s, %s" %
                             (self.title, sorted(nonadded_episodes, key=attrgetter('code'))))
                    yield

                for episode in new_episodes:
                    episode.load_playcount()
                if settings["added_notifications"]:
                    if len(new_episodes) == 1:
                        message = "Added episode: %s" % new_episodes[0].code
                    elif len(new_episodes) <= 3:
                        message = "Added episodes: %s" % ", ".join(sorted([ep.code for ep in new_episodes]))
                    else:
                        message = "Added %s episodes" % len(new_episodes)
                    dialogs.notification(heading=self.title, message=message)
                log.info("Added episodes: %s, %s" % (self.title, sorted(new_episodes, key=attrgetter('code'))))

            db_stored.upsert(self.urlid, self.title)
            if readd:
                db_excluded.remove(self)
            log.info("Finished updating show: %s" % self.title)
        self.task = update_add()
        self.finished = False
        self.exception = None


class Episode(Base):
    def __init__(self, showtitle, seasonnr, episodenr, in_superuniverse=None, urlid=None, kodiid=None, playcount=0):
        self.mediatype = "episode"
        self.showtitle = showtitle
        self.seasonnr = int(seasonnr)
        self.episodenr = int(episodenr)
        self.urlid = urlid
        self.kodiid = kodiid
        self.code = "S%02dE%02d" % (seasonnr, episodenr)
        self.playcount = int(playcount)
        self.path = uni_join(const.libpath, "%s shows" % const.provider, stringtofile(self.showtitle), "Season %s" % self.seasonnr)
        self.htmfilename = "%s %s.htm" % (stringtofile(self.showtitle), self.code)
        self.nfofilename = "%s %s.nfo" % (stringtofile(self.showtitle), self.code)
        self.jsonfilename = "%s %s.json" % (stringtofile(self.showtitle), self.code)
        self.url = "http://tv.nrk.no%s?autostart=true" % self.urlid
        # self.url = "http://tv.nrk%s.no%s?autostart=true" % ("super" if in_superuniverse else "", self.urlid)

    def __repr__(self):
        return self.code

    def load_playcount(self):
        super(Episode, self).load_playcount()

    def check_added(self, koala_stored_episodes):
        if self.code not in koala_stored_episodes:
            self.nonadded = True
        else:
            self.kodiid = koala_stored_episodes[self.code].kodiid
            self.nonadded = False

    def write_nfo(self):
        super(Episode, self).delete_htm()
        super(Episode, self).write_htm()
        episodesubid = re.findall(r'/serie/.*?/(.*?)/.*', self.urlid)[0]
        metadata = scraper.getinfodict(episodesubid)

        soup = BeautifulSoup("<?xml version='1.0' encoding='utf-8'?>")
        root = soup.new_tag("movie")
        soup.append(root)

        root.append(soup.new_tag("title"))
        root.title.string = metadata["title"]

        root.append(soup.new_tag("showtitle"))
        root.showtitle.string = self.showtitle

        root.append(soup.new_tag("season"))
        root.season.string = unicode(self.seasonnr)

        root.append(soup.new_tag("episode"))
        root.episode.string = unicode(self.episodenr)

        root.append(soup.new_tag("runtime"))
        root.runtime.string = unicode(metadata["runtime"])

        root.append(soup.new_tag("plot"))
        root.plot.string = metadata["plot"]

        root.append(soup.new_tag("thumb", aspect="poster"))
        root.thumb.string = metadata["art"]

        with open(os.path.join(self.path, self.nfofilename), "w") as nfo:
            nfo.write(soup.prettify().encode("utf-8"))

    def remove_from_lib(self):
        rpc("VideoLibrary.RemoveEpisode", episodeid=self.kodiid)
