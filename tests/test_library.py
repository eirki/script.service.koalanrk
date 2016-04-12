from __future__ import unicode_literals
import unittest
from urllib import unquote_plus

from lib import library
from lib.xbmcwrappers import rpc
from lib.utils import (uni_join, stringtofile)
from lib import constants as const

real_getepisodes = library.scraper.getepisodes
real_getinfodict = library.scraper.getinfodict
real_getshowinfo = library.scraper.getshowinfo
real_getwatchlist = library.scraper.getwatchlist


def setUpModule():
    library.Movie.init_databases()
    library.Show.init_databases()


# def tearDownModule():


def fake_getmovieinfo(urlid):
    return fake_movie_data


def fake_getshowinfo(urlid):
    return fake_show_data


def fake_getepinfo(urlid):
    return fake_episode_data


fake_movie_data = {
            "title": "The Fake Koala %s Movie" % const.provider,
            "year": "1337",
            "plot": "Plot of fake movie goes here",
            "genre": "Drama",
            "art": "http://cdn0.nflximg.net/images/8654/9238654.jpg",
            "in_superuniverse": False,
            "runtime": "123"}

fake_show_data = {
            "title": "The Fake Koala %s Show" % const.provider,
            "year": "2000",
            "plot": "Plot of fake show goes here",
            "genre": "Drama",
            "art": "http:/ /cdn1.nflximg.net/images/3089/22243089.jpg",
            "in_superuniverse": False,
            }

fake_episode_data = {
            "title": "The Fake Koala %s Episode" % const.provider,
            "showtitle": "The Fake Koala %s Show" % const.provider,
            "season": "1",
            "episode": "1",
            "plot": "Plot of fake episode goes here",
            "runtime": "20",
            "art": "http://so0.akam.nflximg.com/soa3/189/1425268189.jpg",
            "in_superuniverse": False,
}


def fake_getwatchlist():
    available_movies = {movie.urlid: movie.title for movie in library.Movie.db.all+library.Movie.excluded.all}
    available_shows = {show.urlid: show.title for show in library.Show.db.all+library.Show.excluded.all}
    return available_movies, available_shows


def fake_getepisodes_return_A_B(urlid):
    return {
        "S01E01": {'seasonnr': 1, 'episodenr': 1, 'urlid': "/serie/the-fake-show/KOID25007910/sesong-1/episode-1", "in_superuniverse": False},
        "S01E02": {'seasonnr': 1, 'episodenr': 2, 'urlid': "/serie/the-fake-show/KOID25007910/sesong-1/episode-2", "in_superuniverse": False}
        }


def fake_getepisodes_return_A(urlid):
    return {
        "S01E01": {'seasonnr': 1, 'episodenr': 1, 'urlid': "/serie/the-fake-show/KOID25007910/sesong-1/episode-1", "in_superuniverse": False},
        }


def fake_getepisodes_return_A_B_C(urlid):
    return {
        "S01E01": {'seasonnr': 1, 'episodenr': 1, 'urlid': "/serie/the-fake-show/KOID25007910/sesong-1/episode-1", "in_superuniverse": False},
        "S01E02": {'seasonnr': 1, 'episodenr': 2, 'urlid': "/serie/the-fake-show/KOID25007910/sesong-1/episode-2", "in_superuniverse": False},
        "S02E01": {'seasonnr': 2, 'episodenr': 1, 'urlid': "/serie/the-fake-show/KOID25007910/sesong-2/episode-1", "in_superuniverse": False}
        }


def fake_getepisodes_return_A_C(urlid):
    return {
        "S01E01": {'seasonnr': 1, 'episodenr': 1, 'urlid': "/serie/the-fake-show/KOID25007910/sesong-1/episode-1", "in_superuniverse": False},
        "S02E01": {'seasonnr': 2, 'episodenr': 1, 'urlid': "/serie/the-fake-show/KOID25007910/sesong-2/episode-1", "in_superuniverse": False}
        }


def fake_getepisodes_return_C_D(urlid):
    return {
        "S02E01": {'seasonnr': 2, 'episodenr': 1, 'urlid': "/serie/the-fake-show/KOID25007910/sesong-2/episode-1", "in_superuniverse": False},
        "S02E02": {'seasonnr': 2, 'episodenr': 2, 'urlid': "/serie/the-fake-show/KOID25007910/sesong-2/episode-2", "in_superuniverse": False},
        }


class MovieAdd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.movie = library.Movie(urlid="/program/KOIF10009214/we-dont-live-here-anymore", title="We Don't Live Here Anymore")
        library.execute(to_update_add=[cls.movie])

    @classmethod
    def tearDownClass(cls):
        cls.movie.remove()

    def test_add_movie_to_kodi_lib(self):
        """Does movie.add_update() cause the movie to be added to kodi library?"""
        libfiles = [movie["file"] for movie in rpc("VideoLibrary.GetMovies", properties=["file"])['movies']]
        self.assertIn(uni_join(self.movie.path, self.movie.htmfilename), libfiles)

    def test_add_movie_to_database(self):
        """Does movie.add_update() cause the movie to be added to Movie.database?"""
        self.assertIn(self.movie.urlid, library.Movie.db.ids)


class MovieRemove(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.movie = library.Movie(urlid="/program/KOIF47000608/der-untergang", title="Der Untergang")
        library.execute(to_update_add=[cls.movie])
        libfiles = [movie["file"] for movie in rpc("VideoLibrary.GetMovies", properties=["file"])['movies']]
        assert uni_join(cls.movie.path, cls.movie.htmfilename) in libfiles
        library.execute(to_remove=[cls.movie])

    def test_remove_movie_from_kodi_lib(self):
        """Does movie.remove() cause the movie be removed from kodi library?"""
        libfiles = [movie["file"] for movie in rpc("VideoLibrary.GetMovies", properties=["file"])['movies']]
        self.assertNotIn(self.movie.htmfilename, libfiles)

    def test_remove_movie_to_database(self):
        """Does movie.remove() cause the movie to be removed from Movie.database?"""
        self.assertNotIn(self.movie.urlid, library.Movie.db.ids)


class MovieNFO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library.scraper.getinfodict = fake_getmovieinfo
        cls.movie = library.Movie(urlid="/program/fakemovieurlid/the-fake-movie", title="The Fake Koala %s Movie" % const.provider)
        library.execute(to_update_add=[cls.movie])

    @classmethod
    def tearDownClass(cls):
        cls.movie.remove()
        library.scraper.getinfodict = real_getinfodict

    def test_movie_with_NFO_added_to_kodi_lib(self):
        """Does movie.add_update() cause the movie to be added to kodi library when .nfo created?"""
        libfiles = [movie["file"] for movie in rpc("VideoLibrary.GetMovies", properties=["file"])['movies']]
        self.assertIn(uni_join(self.movie.path, self.movie.htmfilename), libfiles)

    def test_movie_NFO_data_correctly_added(self):
        """Does data stored with fake movie in Kodi library correpond with inputed NFO data?"""
        returned_infodict = rpc("VideoLibrary.GetMovies",
                                properties=["title", "year", "plot", "art", "runtime"],
                                multifilter={"and": [
                                     ("filename", "is", self.movie.htmfilename),
                                     ("path", "startswith", self.movie.path)]})
        returned_infodict = returned_infodict["movies"][0]
        excpected_returned_infodict = {
            "title": returned_infodict["label"],
            "year": str(returned_infodict["year"]),
            "runtime": str(returned_infodict["runtime"]/60),
            "plot": returned_infodict["plot"],
            "art": unquote_plus(returned_infodict["art"]["poster"].replace("image://", "").lower().rstrip("/")),
            "in_superuniverse": False,
        }
        self.assertEqual(excpected_returned_infodict, fake_movie_data, msg="\n%s\n%s" % (excpected_returned_infodict, fake_movie_data))


class ShowAdd(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library.scraper.getepisodes = fake_getepisodes_return_A_B
        cls.show = library.Show(urlid="mr-selfridge", title="Mr. Selfridge")
        library.execute(to_update_add=[cls.show])

    @classmethod
    def tearDownClass(cls):
        cls.show.remove()
        library.scraper.getepisodes = real_getepisodes
        library.scraper.getinfodict = real_getinfodict

    def test_add_show_to_kodi_lib(self):
        """Does show.add_update() cause the show to be added to kodi library?"""
        episodepath = uni_join(const.libpath, "%s shows" % const.provider, "%s\\" % stringtofile(self.show.title))
        libfiles = [show["file"] for show in rpc("VideoLibrary.GetTVShows", properties=["file"])['tvshows']]
        self.assertIn(episodepath, libfiles)

    def test_add_show_to_database(self):
        """Does show.add_update() cause the show to be added to show.database?"""
        self.assertIn(self.show.urlid, library.Show.db.ids)


class ShowUpdate(unittest.TestCase):
    def setUp(self):
        library.scraper.getepisodes = fake_getepisodes_return_A_B
        self.show = library.Show(urlid="fader-brown", title="Father Brown")
        library.execute(to_update_add=[self.show])
        stored_episodes = rpc("VideoLibrary.GetEpisodes",
                              filter={"field": "path", "operator": "startswith", "value": self.show.path}).get('episodes', [])
        assert len(stored_episodes) == 2

    def tearDown(self):
        self.show.remove()
        library.scraper.getepisodes = real_getepisodes

    def test_add_one_episode(self):
        """Does making getepisodes() return 3 episodes cause one episode to be added to the kodi library?"""
        library.scraper.getepisodes = fake_getepisodes_return_A_B_C
        library.execute(to_update_add=[self.show])
        stored_episodes = rpc("VideoLibrary.GetEpisodes",
                              filter={"field": "path", "operator": "startswith", "value": self.show.path}).get('episodes', [])
        self.assertEqual(len(stored_episodes), 3, msg="stored_episodes:\n%s" % stored_episodes)

    def test_remove_one_episode(self):
        """Does making getepisodes() return 1 episode cause one episode to be removed from the kodi library?"""
        library.scraper.getepisodes = fake_getepisodes_return_A
        library.execute(to_update_add=[self.show])
        stored_episodes = rpc("VideoLibrary.GetEpisodes",
                              filter={"field": "path", "operator": "startswith", "value": self.show.path}).get('episodes', [])
        self.assertEqual(len(stored_episodes), 1, msg="stored_episodes:\n%s" % stored_episodes)

    def test_replace_both_added_episodes(self):
        """Does making getepisodes() return 2 episodes different from the ones in the kodi library cause
         the episodes in the library to be replaced?"""
        stored_episodes_A_B = rpc("VideoLibrary.GetEpisodes",
                                  filter={"field": "path", "operator": "startswith", "value": self.show.path}).get('episodes', [])
        stored_episodes_A_B.sort()
        library.scraper.getepisodes = fake_getepisodes_return_C_D
        library.execute(to_update_add=[self.show])
        stored_episodes_C_D = rpc("VideoLibrary.GetEpisodes",
                                  filter={"field": "path", "operator": "startswith", "value": self.show.path}).get('episodes', [])
        stored_episodes_C_D.sort()
        # better assertion: there should be no overlap
        self.assertNotEqual(stored_episodes_A_B, stored_episodes_C_D)

    def test_add_one_episode_remove_one_episode(self):
        """Does making getepisodes() return one different from one in the kodi library cause
        one episode to be added to the library and one removed?"""
        stored_episodes_A_B = rpc("VideoLibrary.GetEpisodes",
                                  filter={"field": "path", "operator": "startswith", "value": self.show.path}).get('episodes', [])
        stored_episodes_A_B.sort()
        library.scraper.getepisodes = fake_getepisodes_return_A_C
        library.execute(to_update_add=[self.show])
        stored_episodes_A_C = rpc("VideoLibrary.GetEpisodes",
                                  filter={"field": "path", "operator": "startswith", "value": self.show.path}).get('episodes', [])
        stored_episodes_A_C.sort()
        self.assertEqual(stored_episodes_A_B[0], stored_episodes_A_C[0])
        self.assertNotEqual(stored_episodes_A_B[1], stored_episodes_A_C[1])


class ShowRemove(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library.scraper.getepisodes = fake_getepisodes_return_A_B
        cls.show = library.Show(urlid="broadchurch", title="Broadchurch")
        library.execute(to_update_add=[cls.show])
        cls.episodepath = uni_join(const.libpath, "%s shows" % const.provider, "%s\\" % stringtofile(cls.show.title))
        libfiles = [show["file"] for show in rpc("VideoLibrary.GetTVShows", properties=["file"])['tvshows']]
        assert cls.episodepath in libfiles
        library.execute(to_remove=[cls.show])

    @classmethod
    def tearDownClass(cls):
        library.scraper.getepisodes = real_getepisodes

    def test_remove_show_from_kodi_lib(self):
        """Does show.remove() cause the show be removed from kodi library?"""
        libfiles = [show["file"] for show in rpc("VideoLibrary.GetTVShows", properties=["file"])['tvshows']]
        self.assertNotIn(self.episodepath, libfiles)

    def test_remove_show_to_database(self):
        """Does show.remove() cause the show to be removed from Show.database?"""
        self.assertNotIn(self.show.urlid, library.Show.db.ids)


class ShowNFOEpisodeNFO(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        library.scraper.getshowinfo = fake_getshowinfo
        library.scraper.getinfodict = fake_getepinfo
        library.scraper.getepisodes = fake_getepisodes_return_A
        cls.show = library.Show(urlid="faketvshowurlid", title="The Fake Koala %s Show" % const.provider)
        cls.episodepath = uni_join(const.libpath, "%s shows" % const.provider, "%s\\" % stringtofile(cls.show.title))
        library.execute(to_update_add=[cls.show])

    @classmethod
    def tearDownClass(cls):
        cls.show.remove()
        library.scraper.getepisodes = real_getepisodes
        library.scraper.getshowinfo = real_getshowinfo

    def test_show_with_NFO_added_to_kodi_lib(self):
        """Does show.add_update() cause the show to be added to kodi library when .nfo created?"""
        libfiles = [show["file"] for show in rpc("VideoLibrary.GetTVShows", properties=["file"])['tvshows']]
        self.assertIn(self.episodepath, libfiles)

    def test_show_NFO_data_correctly_added(self):
        """Does data stored with fake show in Kodi library correpond with inputed NFO data?"""
        returned_infodict = rpc("VideoLibrary.GetTVShows",
                                properties=["year", "plot", "art"],
                                filter={"field": "title", "operator": "is", "value": "The Fake Koala %s Show" % const.provider})
        returned_infodict = returned_infodict["tvshows"][0]
        excpected_returned_infodict = {
            "title": returned_infodict["label"],
            "year": unicode(returned_infodict["year"]),
            "plot": returned_infodict["plot"],
            "art": unquote_plus(returned_infodict["art"]["poster"].replace("image://", "").lower().rstrip("/")),
            "in_superuniverse": False,
        }
        self.assertEqual(excpected_returned_infodict, fake_show_data, msg="\n%s\n%s" % (excpected_returned_infodict, fake_show_data))

    def test_episode_with_NFO_added_to_kodi_lib(self):
        """Is episode added to kodi library when .nfo created?"""
        stored_episodes = rpc("VideoLibrary.GetEpisodes",
                              filter={"field": "tvshow", "operator": "is", "value": "The Fake Koala %s Show" % const.provider}).get('episodes', [])
        self.assertEqual(len(stored_episodes), 1, msg="stored_episodes:\n%s" % stored_episodes)

    def test_episode_NFO_data_correctly_added(self):
        """Does data stored with fake episde in Kodi library correpond with inputed NFO data?"""
        returned_infodict = rpc("VideoLibrary.GetEpisodes",
                                properties=["showtitle", "season", "episode", "plot", "runtime", "art"],
                                filter={"field": "tvshow", "operator": "is", "value": "The Fake Koala %s Show" % const.provider})
        returned_infodict = returned_infodict['episodes'][0]
        excpected_returned_infodict = {
            "title": returned_infodict["label"].replace("%dx%02d. " % (returned_infodict["season"], returned_infodict["episode"]), ""),
            "showtitle": returned_infodict["showtitle"],
            "season": unicode(returned_infodict["season"]),
            "episode": unicode(returned_infodict["episode"]),
            "plot": returned_infodict["plot"],
            "runtime": unicode(returned_infodict["runtime"]/60),
            "art": unquote_plus(returned_infodict["art"]["thumb"].replace("image://", "").lower().rstrip("/")),
            "in_superuniverse": False,
        }
        self.assertEqual(excpected_returned_infodict, fake_episode_data, msg="\n%s\n%s" % (excpected_returned_infodict, fake_episode_data))
