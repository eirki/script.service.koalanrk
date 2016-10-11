#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import abc
import os
import json
import xml.etree.ElementTree as ET
import xml.dom.minidom

from . import constants as const
from . import utils
from . import kodi


class BaseLibEntry(object):
    __metaclass__ = abc.ABCMeta

    @abc.abstractmethod
    def __init__(self, kodiid, playcount):
        self.kodiid = kodiid
        self.playcount = playcount

    @abc.abstractmethod
    def load_playcount(self):
        jsonfilepath = utils.os_join(self.path, self.jsonfilename)
        if os.path.exists(jsonfilepath):
            with open(jsonfilepath, "r") as f:
                playcount = json.load(f)
            kodi.rpc("VideoLibrary.Set%sDetails" % self.mediatype.capitalize(), playcount=playcount,
                     **{self.mediatype + "id": self.kodiid})
            os.remove(jsonfilepath)

    @abc.abstractmethod
    def save_playcount(self):
        if self.playcount > 0:
            jsonfilepath = utils.os_join(self.path, self.jsonfilename)
            with open(jsonfilepath, "w") as f:
                json.dump(self.playcount, f)

    @abc.abstractmethod
    def remove_from_lib(self):
        kodi.rpc("VideoLibrary.Remove%s" % self.mediatype.capitalize(),
                 **{self.mediatype + "id": self.kodiid})

    @abc.abstractmethod
    def delete_htm(self):
        os.remove(utils.os_join(self.path, self.htmfilename))
        try:
            os.removedirs(utils.os_join(self.path))
        except OSError:
            pass
###########################


class BaseMovie(object):
    mediatype = "movie"

    def __init__(self, title):
        self.title = title
        self.path = utils.uni_join(const.libpath, "%s movies" % const.provider)
        self.htmfilename = "%s.htm" % utils.stringtofile(self.title)
        self.nfofilename = "%s.nfo" % utils.stringtofile(self.title)
        self.jsonfilename = "%s.json" % utils.stringtofile(self.title)

    def __repr__(self):
        return repr(self.title)

    def __hash__(self):
        return hash(self.title)

    def __eq__(self, other):
        return self.title == other.title

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        return self.title < other.title


class ScrapedMovie(BaseMovie):
    def __init__(self, urlid, title):
        BaseMovie.__init__(self, title)
        self.urlid = urlid
        self.url = "http://tv.nrk.no%s?autostart=true" % self.urlid

    def write_htm(self):
        with open(utils.os_join(self.path, self.htmfilename), "w") as txt:
            txt.write('<meta http-equiv="REFRESH" content="0;'
                      'url=%s"> <body bgcolor="#ffffff">' % self.url)

    def write_nfo(self, metadata):
        root = ET.Element("movie")
        ET.SubElement(root, "title").text = self.title
        ET.SubElement(root, "runtime").text = unicode(metadata["runtime"].seconds/60)
        ET.SubElement(root, "plot").text = metadata["plot"]
        ET.SubElement(root, "thumb", aspect="poster").text = metadata["art"]
        fanart = ET.SubElement(root, "fanart")
        ET.SubElement(fanart, "thumb").text = metadata["art"]

        as_string = ET.tostring(root, method='xml')
        pretty_xml_as_string = xml.dom.minidom.parseString(as_string).toprettyxml()
        with open(os.path.join(self.path, self.nfofilename), "w") as nfo:
            nfo.write(pretty_xml_as_string.encode("utf-8"))

    def get_lib_entry(self):
        moviesdict = kodi.rpc("VideoLibrary.GetMovies",
                              properties=["file", 'playcount'],
                              multifilter={"and":
                                           [("filename", "is", self.htmfilename),
                                            ("path", "startswith", self.path)]})
        try:
            movie_dict = moviesdict['movies'][0]
        except (KeyError, IndexError):
            return None
        return MovieLibEntry(self.title, movie_dict["movieid"], movie_dict["playcount"])


class MovieLibEntry(BaseMovie, BaseLibEntry):
    def __init__(self, title, kodiid, playcount):
        BaseMovie.__init__(self, title)
        BaseLibEntry.__init__(self, kodiid, playcount)

    def load_playcount(self):
        BaseLibEntry.load_playcount(self)

    def save_playcount(self):
        BaseLibEntry.save_playcount(self)

    def remove_from_lib(self):
        BaseLibEntry.remove_from_lib(self)

    def delete_htm(self):
        BaseLibEntry.delete_htm(self)
###########################


class ScrapedShow(object):
    mediatype = "show"

    def __init__(self, urlid, title):
        self.urlid = urlid
        self.title = title
        self.path = utils.uni_join(const.libpath, "%s shows" % const.provider, utils.stringtofile(self.title))
        self.nfofilename = "tvshow.nfo"

    def __repr__(self):
        return repr(self.title)

    def __hash__(self):
        return hash(self.title)

    def __eq__(self, other):
        return self.title == other.title

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        return self.title < other.title

    def get_episode_availability(self, available_episodes):
        koala_stored_episodes, all_stored_episodes = self.get_stored_episodes()
        unav_episodes = koala_stored_episodes - available_episodes
        new_episodes = available_episodes - all_stored_episodes
        return unav_episodes, new_episodes

    def write_nfo(self, metadata):
        root = ET.Element("tvshow")
        ET.SubElement(root, "title").text = self.title
        ET.SubElement(root, "plot").text = metadata["plot"]
        ET.SubElement(root, "thumb", aspect="poster").text = metadata["art"]
        fanart = ET.SubElement(root, "fanart")
        ET.SubElement(fanart, "thumb").text = metadata["art"]
        ET.SubElement(root, "genre").text = metadata["genre"]

        as_string = ET.tostring(root, method='xml')
        pretty_xml_as_string = xml.dom.minidom.parseString(as_string).toprettyxml()
        with open(os.path.join(self.path, self.nfofilename), "w") as nfo:
            nfo.write(pretty_xml_as_string.encode("utf-8"))

    def get_koala_stored_eps(self):
        # get any stored koala episodes
        episodes = kodi.rpc("VideoLibrary.GetEpisodes", properties=["season", "episode", "playcount"],
                            filter={"field": "path", "operator": "startswith", "value": self.path})
        koala_stored_episodes = set()
        for epdict in episodes.get('episodes', []):
            episode = EpisodeLibEntry(self, epdict["season"], epdict["episode"],
                                      kodiid=epdict["episodeid"], playcount=epdict["playcount"])
            koala_stored_episodes.add(episode)

        return koala_stored_episodes

    def get_stored_episodes(self):
        koala_stored_episodes = self.get_koala_stored_eps()
        if koala_stored_episodes:
            any_ep_kodiid = next(iter(koala_stored_episodes)).kodiid
        else:
            # no stored koala episode, get any stored episode
            episodes = kodi.rpc("VideoLibrary.GetEpisodes", limits={"start": 0, "end": 1},
                                filter={"field": "filename", "operator": "startswith", "value": "%s S" % utils.stringtofile(self.title)},
                                ).get('episodes', [])
            if not episodes:
                # no stored episodes detectable
                return set(), set()
            any_ep_kodiid = episodes[0]['episodeid']
        any_episode = kodi.rpc("VideoLibrary.GetEpisodeDetails", episodeid=any_ep_kodiid, properties=["showtitle"])
        scraped_title = any_episode['episodedetails']['showtitle']

        all_stored_episodes_dict = kodi.rpc("VideoLibrary.GetEpisodes",
                                            properties=["season", "episode"],
                                            filter={"field": "tvshow", "operator": "is", "value": scraped_title})
        all_stored_episodes_set = set(BaseEpisode(show=self, seasonnr=epdict['season'], episodenr=epdict['episode'])
                                      for epdict in all_stored_episodes_dict.get('episodes', []))
        return koala_stored_episodes, all_stored_episodes_set
###########################


class BaseEpisode(object):
    mediatype = "episode"

    def __init__(self, show, seasonnr, episodenr):
        self.showtitle = show.title
        self.seasonnr = int(seasonnr)
        self.episodenr = int(episodenr)
        self.code = "S%02dE%02d" % (seasonnr, episodenr)
        self.path = utils.uni_join(const.libpath, "%s shows" % const.provider,
                                   utils.stringtofile(self.showtitle), "Season %s" % self.seasonnr)
        self.htmfilename = "%s %s.htm" % (utils.stringtofile(self.showtitle), self.code)
        self.nfofilename = "%s %s.nfo" % (utils.stringtofile(self.showtitle), self.code)
        self.jsonfilename = "%s %s.json" % (utils.stringtofile(self.showtitle), self.code)

    def __repr__(self):
        return self.code

    def __hash__(self):
        return hash(self.code)

    def __eq__(self, other):
        return self.code == other.code

    def __ne__(self, other):
        return not self.__eq__(other)

    def __lt__(self, other):
        return self.code < other.code


class ScrapedEpisode(BaseEpisode):
    def __init__(self, show, seasonnr, episodenr, urlid, plot, runtime, thumb, title):
        BaseEpisode.__init__(self, show=show, seasonnr=seasonnr, episodenr=episodenr)
        self.urlid = urlid
        self.url = "http://tv.nrk.no/serie/%s/%s?autostart=true" % (show.urlid, urlid)
        self.title = title
        self.plot = plot
        self.runtime = runtime
        self.thumb = "http://gfx.nrk.no/%s" % thumb

    def write_htm(self):
        if not os.path.exists(utils.os_join(self.path)):
            os.makedirs(utils.os_join(self.path))
        with open(utils.os_join(self.path, self.htmfilename), "w") as txt:
            txt.write('<meta http-equiv="REFRESH" content="0;'
                      'url=%s"> <body bgcolor="#ffffff">' % self.url)

    def write_nfo(self):
        root = ET.Element("episodedetails")
        ET.SubElement(root, "title").text = self.title
        ET.SubElement(root, "showtitle").text = self.showtitle
        ET.SubElement(root, "season").text = unicode(self.seasonnr)
        ET.SubElement(root, "episode").text = unicode(self.episodenr)
        ET.SubElement(root, "plot").text = self.plot
        ET.SubElement(root, "runtime").text = unicode(self.runtime.seconds/60)
        ET.SubElement(root, "thumb").text = self.thumb

        as_string = ET.tostring(root, method='xml')
        pretty_xml_as_string = xml.dom.minidom.parseString(as_string).toprettyxml()
        with open(os.path.join(self.path, self.nfofilename), "w") as nfo:
            nfo.write(pretty_xml_as_string.encode("utf-8"))


class EpisodeLibEntry(BaseEpisode, BaseLibEntry):
    def __init__(self, show, seasonnr, episodenr, kodiid, playcount):
        BaseEpisode.__init__(self, show=show, seasonnr=seasonnr, episodenr=episodenr)
        BaseLibEntry.__init__(self, kodiid=kodiid, playcount=playcount)

    def load_playcount(self):
        BaseLibEntry.load_playcount(self)

    def save_playcount(self):
        BaseLibEntry.save_playcount(self)

    def remove_from_lib(self):
        BaseLibEntry.remove_from_lib(self)

    def delete_htm(self):
        BaseLibEntry.delete_htm(self)
