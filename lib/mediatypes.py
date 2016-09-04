#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import os
import json
from bs4 import BeautifulSoup
from operator import attrgetter

from . utils import (os_join, uni_join, stringtofile)
from . import constants as const
from .xbmcwrappers import (rpc, log, settings, dialogs)


class BaseLibEntry(object):
    def load_playcount(self):
        jsonfilepath = os_join(self.path, self.jsonfilename)
        if os.path.exists(jsonfilepath):
            with open(jsonfilepath, "r") as f:
                playcount = json.load(f)
            rpc("VideoLibrary.Set%sDetails" % self.mediatype.capitalize(), playcount=playcount,
                **{self.mediatype + "id": self.kodiid})
            os.remove(jsonfilepath)

    def save_playcount(self):
        if self.playcount > 0:
            jsonfilepath = os_join(self.path, self.jsonfilename)
            with open(jsonfilepath, "w") as f:
                json.dump(self.playcount, f)

    def remove_from_lib(self):
        rpc("VideoLibrary.Remove%s" % self.mediatype.capitalize(),
            **{self.mediatype + "id": self.kodiid})
###########################


class Movie(object):
    mediatype = "movie"

    def __init__(self, title):
        self.title = title
        self.path = uni_join(const.libpath, "%s movies" % const.provider)
        self.htmfilename = "%s.htm" % stringtofile(self.title)
        self.nfofilename = "%s.nfo" % stringtofile(self.title)
        self.jsonfilename = "%s.json" % stringtofile(self.title)

    def __repr__(self):
        return self.title.encode("ascii", "ignore")

    def __hash__(self):
        return hash(self.title)

    def __eq__(self, other):
        return self.title == other.title

    def __ne__(self, other):
        return not self.__eq__(other)

    def delete_htm(self):
        os.remove(os_join(self.path, self.htmfilename))
        try:
            os.removedirs(os_join(self.path))
        except OSError:
            pass


class KoalaMovie(Movie):
    def __init__(self, urlid, title):
        Movie.__init__(self, title)
        self.urlid = urlid
        self.url = "http://tv.nrk.no%s?autostart=true" % self.urlid

    def write_htm(self):
        if not os.path.exists(os_join(self.path)):
            os.makedirs(os_join(self.path))
        with open(os_join(self.path, self.htmfilename), "w") as txt:
            txt.write('<meta http-equiv="REFRESH" content="0;'
                      'url=%s"> <body bgcolor="#ffffff">' % self.url)

    def write_nfo(self, metadata):
        soup = BeautifulSoup(features='xml')
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

    def get_lib_entry(self):
        moviesdict = rpc("VideoLibrary.GetMovies",
                         properties=["file", 'playcount'],
                         multifilter={"and":
                                      [("filename", "is", self.htmfilename),
                                       ("path", "startswith", self.path)]})
        try:
            movie_dict = moviesdict['movies'][0]
        except KeyError:
            return None
        return MovieLibEntry(self.title, movie_dict["movieid"], movie_dict["playcount"])

    def generate_removal_task(self, db_stored, exclude=False, db_excluded=None):
        def remove():
            log.info("Removing movie: %s" % self)
            lib_entry = self.get_lib_entry()
            if lib_entry:
                lib_entry.save_playcount()
                lib_entry.remove_from_lib()
                lib_entry.delete_htm()
            else:
                log.info("Couldn't find in library: %s" % (self))
            if settings["added_notifications"]:
                dialogs.notification(heading="%s movie removed:" % const.provider, message=self.title)
            db_stored.remove(self)
            if exclude:
                db_excluded.add(self)
            log.info("Finished removing movie: %s" % self)
        self.task = remove
        self.finished = False
        self.exception = None

    def generate_add_task(self, db_stored, session, readd=False, db_excluded=None):
        def add():
            log.info("Adding movie: %s" % self)
            self.write_htm()
            yield

            lib_entry = self.get_lib_entry()
            if not lib_entry:
                metadata = session.get_movie_metadata(self.urlid)
                self.write_nfo(metadata)
                self.delete_htm()
                self.write_htm()
                yield

                lib_entry = self.get_lib_entry()
                if not lib_entry:
                    log.info("Failed to add movie: %s" % self)
                    return
            lib_entry.load_playcount()
            if settings["added_notifications"]:
                dialogs.notification(heading="%s movie added:" % const.provider, message=self.title)
            db_stored.add(self)
            if readd:
                db_excluded.remove(self)
            log.info("Finished adding movie: %s" % self)
        self.task = add()
        self.finished = False
        self.exception = None


class MovieLibEntry(Movie, BaseLibEntry):
    def __init__(self, title, kodiid, playcount):
        Movie.__init__(self, title)
        self.kodiid = kodiid
        self.playcount = playcount
###########################


class Show(object):
    mediatype = "show"

    def __init__(self, urlid, title):
        self.urlid = urlid
        self.title = title
        self.path = uni_join(const.libpath, "%s shows" % const.provider, stringtofile(self.title))
        self.nfofilename = "tvshow.nfo"

    def __repr__(self):
        return self.title.encode("ascii", "ignore")

    def __hash__(self):
        return hash(self.title)

    def __eq__(self, other):
        return self.title == other.title

    def __ne__(self, other):
        return not self.__eq__(other)

    def get_episode_availability(self, available_episodes):
        koala_stored_episodes, all_stored_episodes = self.get_stored_episodes()
        unav_episodes = koala_stored_episodes - available_episodes
        new_episodes = available_episodes - all_stored_episodes
        return unav_episodes, new_episodes

    def write_nfo(self, metadata):
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

    def notify(self, new_episodes):
        if len(new_episodes) == 1:
            message = "Added episode: %s" % new_episodes[0].code
        elif len(new_episodes) <= 3:
            message = "Added episodes: %s" % ", ".join(sorted([ep.code for ep in new_episodes]))
        else:
            message = "Added %s episodes" % len(new_episodes)
        dialogs.notification(heading=self.title, message=message)

    def get_koala_stored_eps(self):
        # get any stored koala episodes
        episodes = rpc("VideoLibrary.GetEpisodes", properties=["season", "episode", "playcount"],
                       filter={"field": "path", "operator": "startswith", "value": self.path})
        koala_stored_episodes = set()
        for epdict in episodes.get('episodes', []):
            episode = EpisodeLibEntry(self.title, epdict["season"], epdict["episode"],
                                      kodiid=epdict["episodeid"], playcount=epdict["playcount"])
            koala_stored_episodes.add(episode)

        return koala_stored_episodes

    def get_stored_episodes(self):
        koala_stored_episodes = self.get_koala_stored_eps()
        if koala_stored_episodes:
            any_ep_kodiid = koala_stored_episodes[0].kodiid
        else:
            # no stored koala episode, get any stored episode
            episodes = rpc("VideoLibrary.GetEpisodes", limits={"start": 0, "end": 1},
                           filter={"field": "filename", "operator": "startswith", "value": "%s S" % stringtofile(self.title)},
                           ).get('episodes', [])
            if not episodes:
                # no stored episodes detectable
                return set(), set()
            any_ep_kodiid = episodes[0]['episodeid']
        any_episode = rpc("VideoLibrary.GetEpisodeDetails", episodeid=any_ep_kodiid, properties=["showtitle"])
        scraped_title = any_episode['episodedetails']['showtitle']

        all_stored_episodes_dict = rpc("VideoLibrary.GetEpisodes",
                                       properties=["season", "episode"],
                                       filter={"field": "tvshow", "operator": "is", "value": scraped_title})
        all_stored_episodes_set = set(Episode(showtitle=self.title, seasonnr=epdict['season'], episodenr=epdict['episode'])
                                      for epdict in all_stored_episodes_dict.get('episodes', []))
        return koala_stored_episodes, all_stored_episodes_set

    def generate_removal_task(self, db_stored, exclude=False, db_excluded=None):
        def remove():
            log.info("Removing show: %s" % self.title)
            koala_stored_episodes = self.get_koala_stored_eps()
            for lib_entry in koala_stored_episodes:
                lib_entry.save_playcount()
                lib_entry.delete_htm()
                lib_entry.remove_from_lib()
            db_stored.remove(self)
            if exclude:
                db_excluded.add(self)
            log.info("Removed episodes: %s, %s" % (self.title, sorted(koala_stored_episodes, key=attrgetter('code'))))
            log.info("Finished removing show: %s" % self.title)
        self.task = remove
        self.finished = False
        self.exception = None

    def generate_update_task(self, db_stored, session, readd=False, db_excluded=None):
        def update_add():
            log.info("Updating show: %s" % self)
            available_episodes = session.getepisodes(self)
            unav_episodes, new_episodes = self.get_episode_availability(available_episodes)
            for lib_entry in unav_episodes:
                lib_entry.save_playcount()
                lib_entry.delete_htm()
                lib_entry.remove_from_lib()
            if new_episodes:
                for episode in new_episodes:
                    episode.write_htm()
                log.info("htms created, waiting for lib update: %s %s" %
                         (self, sorted(new_episodes, key=attrgetter('code'))))
                yield

                koala_stored_episodes = self.get_koala_stored_eps()
                nonadded_episodes = new_episodes - koala_stored_episodes
                if nonadded_episodes:
                    if not koala_stored_episodes:
                        metadata = session.get_show_metadata(self.urlid)
                        self.write_nfo(metadata)
                    for episode in nonadded_episodes:
                        episode.write_nfo()
                        episode.delete_htm()
                        episode.write_htm()
                    log.info("NFOs created, waiting for second lib update: %s, %s" %
                             (self, sorted(nonadded_episodes, key=attrgetter('code'))))
                    yield

                    koala_stored_episodes = self.get_koala_stored_eps()
                    nonadded_episodes = new_episodes - koala_stored_episodes
                    if nonadded_episodes:
                        log.info("Failed to add episodes: %s, %s" % (self, sorted(nonadded_episodes, key=attrgetter('code'))))

                added_episodes = koala_stored_episodes - nonadded_episodes
                for lib_entry in added_episodes:
                    lib_entry.load_playcount()

                if settings["added_notifications"]:
                    self.notify(new_episodes)
                log.info("Added episodes: %s, %s" % (self, sorted(added_episodes, key=attrgetter('code'))))
            if unav_episodes:
                log.info("Removed episodes: %s, %s" % (self, sorted(unav_episodes, key=attrgetter('code'))))
            db_stored.upsert(self)
            if readd:
                db_excluded.remove(self)
            log.info("Finished updating show: %s" % self)
        self.task = update_add()
        self.finished = False
        self.exception = None
###########################


class Episode(object):
    mediatype = "episode"

    def __init__(self, showtitle, seasonnr, episodenr):
        self.showtitle = showtitle
        self.seasonnr = int(seasonnr)
        self.episodenr = int(episodenr)
        self.code = "S%02dE%02d" % (seasonnr, episodenr)
        self.path = uni_join(const.libpath, "%s shows" % const.provider,
                             stringtofile(self.showtitle), "Season %s" % self.seasonnr)
        self.htmfilename = "%s %s.htm" % (stringtofile(self.showtitle), self.code)
        self.nfofilename = "%s %s.nfo" % (stringtofile(self.showtitle), self.code)
        self.jsonfilename = "%s %s.json" % (stringtofile(self.showtitle), self.code)

    def __repr__(self):
        return self.code

    def __hash__(self):
        return hash(self.code)

    def __eq__(self, other):
        return self.code == other.code

    def __ne__(self, other):
        return not self.__eq__(other)

    def delete_htm(self):
        os.remove(os_join(self.path, self.htmfilename))
        try:
            os.removedirs(os_join(self.path))
        except OSError:
            pass


class KoalaEpisode(Episode):
    def __init__(self, show, seasonnr, episodenr, urlid, plot, runtime, art, title):
        Episode.__init__(self, show.title, seasonnr, episodenr)
        self.urlid = urlid
        self.url = "http://tv.nrk.no/serie/%s/%s?autostart=true" % (show.urlid, urlid)
        self.title = title
        self.plot = plot
        self.runtime = runtime
        self.art = "https://gfx.nrk.no/%s" % art

    def write_htm(self):
        if not os.path.exists(os_join(self.path)):
            os.makedirs(os_join(self.path))
        with open(os_join(self.path, self.htmfilename), "w") as txt:
            txt.write('<meta http-equiv="REFRESH" content="0;'
                      'url=%s"> <body bgcolor="#ffffff">' % self.url)

    def write_nfo(self):
        soup = BeautifulSoup("<?xml version='1.0' encoding='utf-8'?>")
        root = soup.new_tag("movie")
        soup.append(root)

        root.append(soup.new_tag("title"))
        root.title.string = self.title

        root.append(soup.new_tag("showtitle"))
        root.showtitle.string = self.showtitle

        root.append(soup.new_tag("season"))
        root.season.string = unicode(self.seasonnr)

        root.append(soup.new_tag("episode"))
        root.episode.string = unicode(self.episodenr)

        root.append(soup.new_tag("plot"))
        root.plot.string = self.plot

        root.append(soup.new_tag("runtime"))
        root.runtime.string = unicode(self.runtime)

        root.append(soup.new_tag("thumb", aspect="poster"))
        root.thumb.string = self.art

        with open(os.path.join(self.path, self.nfofilename), "w") as nfo:
            nfo.write(soup.prettify().encode("utf-8"))


class EpisodeLibEntry(Episode, BaseLibEntry):
    def __init__(self, showtitle, seasonnr, episodenr, kodiid, playcount):
        Episode.__init__(self, showtitle, seasonnr, episodenr)
        self.kodiid = kodiid
        self.playcount = playcount
