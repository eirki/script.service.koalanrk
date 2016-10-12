#! /usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division)

import unittest
import os
from os.path import isfile
import shutil

from lib import constants as const
from lib import utils
from lib import library
from tests import mock_constants
from tests import mock_kodi
from tests import mock_scraper
import main

# ## in mock watchlist:
# Beatles - to be added
# Sangfoni - musikkvideo S01E01, S01E02 - to be added
# Folkeopplysningen S01E02, S01E03  - already added
# Fantorangen - to remain excluded
# Wolf Children - to remain excluded

# ##  in mock shows:
# I Mummidalen, S02E01, S02E02 - to be removed
# Folkeopplysningen S01E01, S01E02 - to be updated

# ## in mock movies:
# Thank you for smoking - to be removed

# ## in mock excluded shows:
# Fantorangen - to remain excluded

# ## in mock excluded movies:
# Wolf Children - to remain excluded


# Testing get_watchlist with mutiple results:
# Remove movie: "Thank you for smoking", playcount 1
# Remove show: "I Mummidalen", remove S02E01 and S02E02 (playcount 2),
# Add movie: "Beatles"
# Add show: "Sangfoni - musikkvideo", add 2 episodes, S01E01 (needs nfo), S01E02 (with json)
# Update show: "Folkeopplysningen", remove 1 episode, add 1 episode, 1 episode remains


def setUpModule():
    library.databases.stored_movies.filepath = utils.os_join(mock_constants.userdatafolder, "%s.json" %
                                                             library.databases.stored_movies.name)
    library.databases.excluded_movies.filepath = utils.os_join(mock_constants.userdatafolder, "%s.json" %
                                                               library.databases.excluded_movies.name)
    library.databases.stored_shows.filepath = utils.os_join(mock_constants.userdatafolder, "%s.json" %
                                                            library.databases.stored_shows.name)
    library.databases.excluded_shows.filepath = utils.os_join(mock_constants.userdatafolder, "%s.json" %
                                                              library.databases.excluded_shows.name)
    library.databases.prioritized_shows.filepath = utils.os_join(mock_constants.userdatafolder, "%s.json" %
                                                                 library.databases.prioritized_shows.name)
    library.databases.mediatypes.const = mock_constants
    library.databases.mediatypes.kodi = mock_kodi
    library.kodi = mock_kodi
    library.scraper = mock_scraper

    if os.path.exists(mock_constants.userdatafolder):
        # delete mock userdata folder
        shutil.rmtree(mock_constants.userdatafolder)
    # copy mock userdata folder to userdata so it can be modified
    shutil.copytree(utils.os_join(const.addonpath, "tests", "mock userdata"), mock_constants.userdatafolder)
    main.main(argv={"mode": "library", "action": "startup"})


def check_movie(name, ext, season=None, episode=None):
    path = utils.os_join(mock_constants.libpath, "%s movies" % const.provider, "%s.%s" % (utils.stringtofile(name), ext))
    return path


def check_episode(name, ext, season=None, episode=None):
    path = utils.os_join(mock_constants.libpath, "%s shows" % const.provider, utils.stringtofile(name), "Season %s" % season,
                         "%s S%02dE%02d.%s" % (utils.stringtofile(name), season, episode, ext))
    return path


class AddMovie(unittest.TestCase):
    def test_add_movie_htm(self):
        """Was movie (Beatles) added, with HTM created?"""
        path = check_movie(name="Beatles", ext="htm")
        self.assertTrue(isfile(path), msg="File not created:\n%s" % path)

    def test_add_movie_nfo(self):
        """Was movie (Beatles) added, with NFO created?"""
        path = check_movie(name="Beatles", ext="nfo")
        self.assertTrue(isfile(path), msg="File not created:\n%s" % path)

    def test_add_movie_json(self):
        """Was movie (Beatles) added, with JSON deleted?"""
        path = check_movie(name="Beatles", ext="json")
        self.assertFalse(isfile(path), msg="File not removed:\n%s" % path)


class RemoveMovie(unittest.TestCase):
    def test_remove_movie_htm(self):
        """Was movie (Thank you for smoking) removed, with HTM deleted?"""
        path = check_movie(name="Thank you for smoking", ext="htm")
        self.assertFalse(isfile(path), msg="File not removed:\n%s" % path)

    def test_remove_movie_json(self):
        """Was movie (Thank you for smoking) removed, with JSON created?"""
        path = check_movie(name="Thank you for smoking", ext="json")
        self.assertTrue(isfile(path), msg="File not created:\n%s" % path)


class RemoveShow(unittest.TestCase):
    def test_remove_show_S02E01_htm(self):
        """Was show (I Mummidalen) removed, with S02E01 htm deleted?"""
        path = check_episode(name="I Mummidalen", ext="htm", season=2, episode=1)
        self.assertFalse(isfile(path), msg="File not removed:\n%s" % path)

    def test_remove_show_S02E01_json(self):
        """Was show (I Mummidalen) removed, with S02E01 json not created?"""
        path = check_episode(name="I Mummidalen", ext="json", season=2, episode=1)
        self.assertFalse(isfile(path), msg="File created:\n%s" % path)

    def test_remove_show_S02E02_htm(self):
        """Was show (I Mummidalen) removed, with S02E02 htm deleted?"""
        path = check_episode(name="I Mummidalen", ext="htm", season=2, episode=2)
        self.assertFalse(isfile(path), msg="File not removed:\n%s" % path)

    def test_remove_show_S02E02_json(self):
        """Was show (I Mummidalen) removed, with S02E02 json created?"""
        path = check_episode(name="I Mummidalen", ext="json", season=2, episode=2)
        self.assertTrue(isfile(path), msg="File not created:\n%s" % path)


class AddShow(unittest.TestCase):
    def test_add_show_S01E01_htm(self):
        """Was show (Sangfoni - musikkvideo) added, with S01E01 htm created?"""
        path = check_episode(name="Sangfoni - musikkvideo", ext="htm", season=1, episode=1)
        self.assertTrue(isfile(path), msg="File not created:\n%s" % path)

    def test_add_show_S01E01_nfo(self):
        """Was show (Sangfoni - musikkvideo) added, with S01E01 nfo created?"""
        path = check_episode(name="Sangfoni - musikkvideo", ext="nfo", season=1, episode=1)
        self.assertTrue(isfile(path), msg="File not created:\n%s" % path)

    def test_add_show_S01E01_json(self):
        """Was show (Sangfoni - musikkvideo) added, with S01E02 json deleted?"""
        path = check_episode(name="Sangfoni - musikkvideo", ext="json", season=1, episode=2)
        self.assertFalse(isfile(path), msg="File not removed:\n%s" % path)

    def test_add_show_S01E02_htm(self):
        """Was show (Sangfoni - musikkvideo) added, with S01E02 htm created?"""
        path = check_episode(name="Sangfoni - musikkvideo", ext="htm", season=1, episode=2)
        self.assertTrue(isfile(path), msg="File not created:\n%s" % path)


class UpdateShow(unittest.TestCase):
    def test_update_show_S01E01_htm(self):
        """Was show (Folkeopplysningen) updated, with S01E01 htm deleted?"""
        path = check_episode(name="Folkeopplysningen", ext="htm", season=1, episode=1)
        self.assertFalse(isfile(path), msg="File not removed:\n%s" % path)

    def test_update_show_S01E01_json(self):
        """Was show (Folkeopplysningen) updated, with S01E01 json created?"""
        path = check_episode(name="Folkeopplysningen", ext="json", season=1, episode=1)
        self.assertTrue(isfile(path), msg="File not created:\n%s" % path)

    def test_update_show_S01E02_htm(self):
        """Was show (Folkeopplysningen) updated, with S01E02 htm retained?"""
        path = check_episode(name="Folkeopplysningen", ext="htm", season=1, episode=2)
        self.assertTrue(isfile(path), msg="File not retained:\n%s" % path)

    def test_update_show_S01E03_htm(self):
        """Was show (Folkeopplysningen) updated, with S01E03 htm created?"""
        path = check_episode(name="Folkeopplysningen", ext="htm", season=1, episode=3)
        self.assertTrue(isfile(path), msg="File not created:\n%s" % path)

    def test_update_show_S01E03_json(self):
        """Was show (Folkeopplysningen) updated, with S01E03 json deleted?"""
        path = check_episode(name="Folkeopplysningen", ext="json", season=1, episode=3)
        self.assertFalse(isfile(path), msg="File not removed:\n%s" % path)


class MovieExcluded(unittest.TestCase):
    def test_movie_excluded(self):
        """Was movie (Wolf Children) still excluded?"""
        path = utils.os_join(mock_constants.libpath, "%s movies" % const.provider,
                             "Wolf Children.htm")
        self.assertFalse(isfile(path), msg="File created:\n%s" % path)


class ShowExcluded(unittest.TestCase):
    def test_show_excluded(self):
        """Was show (Fantorangen) still excluded?"""
        path = utils.os_join(mock_constants.libpath, "%s shows" % const.provider, "Fantorangen")
        self.assertFalse(isfile(path), msg="File created:\n%s" % path)

