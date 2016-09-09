#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import multiprocessing.dummy as threading
import traceback
from operator import attrgetter
import sys

from . import scraper
from . import databases
from . xbmcwrappers import (log, settings, dialogs, ProgressDialog, ScanMonitor)
from . import constants as const


# Library tasks
def remove_movie(movie):
    log.info("Removing movie: %s" % movie)
    lib_entry = movie.get_lib_entry()
    if lib_entry:
        lib_entry.save_playcount()
        lib_entry.remove_from_lib()
        lib_entry.delete_htm()
    else:
        log.info("Couldn't find in library: %s" % (movie))
    if settings["added_notifications"]:
        dialogs.notification(heading="%s movie removed:" % const.provider, message=movie.title)
    databases.stored_movies.remove(movie)
    log.info("Finished removing movie: %s" % movie)


def exclude_movie(movie):
    log.info("Excluding movie: %s" % movie.title)
    remove_movie(movie)
    databases.excluded_movies.add(movie)
    log.info("Finished excluding movie: %s" % movie.title)


def add_movie(movie):
    log.info("Adding movie: %s" % movie)
    movie.write_htm()
    yield

    lib_entry = movie.get_lib_entry()
    if not lib_entry:
        metadata = scraper.get_movie_metadata(movie.urlid)
        movie.write_nfo(metadata)
        movie.delete_htm()
        movie.write_htm()
        yield

        lib_entry = movie.get_lib_entry()
        if not lib_entry:
            log.info("Failed to add movie: %s" % movie)
            return
    lib_entry.load_playcount()
    if settings["added_notifications"]:
        dialogs.notification(heading="%s movie added:" % const.provider, message=movie.title)
    databases.stored_movies.add(movie)
    log.info("Finished adding movie: %s" % movie)


def readd_movie(movie):
    log.info("Readding movie: %s" % movie.title)
    for step in add_movie(movie):
        yield step
    databases.excluded_movies.remove(movie)
    log.info("Finished readding movie: %s" % movie.title)


def remove_show(show):
    log.info("Removing show: %s" % show.title)
    koala_stored_episodes = show.get_koala_stored_eps()
    for lib_entry in koala_stored_episodes:
        lib_entry.save_playcount()
        lib_entry.delete_htm()
        lib_entry.remove_from_lib()
    databases.stored_shows.remove(show)
    log.info("Removed episodes: %s, %s" % (show.title, sorted(koala_stored_episodes, key=attrgetter('code'))))
    log.info("Finished removing show: %s" % show.title)


def exclude_show(show):
    log.info("Excluding show: %s" % show.title)
    remove_show(show)
    databases.excluded_shows.add(show)
    log.info("Finished excluding show: %s" % show.title)


def update_add_show(show):
    log.info("Updating show: %s" % show)
    available_episodes = scraper.getepisodes(show)
    unav_episodes, new_episodes = show.get_episode_availability(available_episodes)
    for lib_entry in unav_episodes:
        lib_entry.save_playcount()
        lib_entry.delete_htm()
        lib_entry.remove_from_lib()
    if new_episodes:
        for episode in new_episodes:
            episode.write_htm()
        log.info("htms created, waiting for lib update: %s %s" %
                 (show, sorted(new_episodes, key=attrgetter('code'))))
        yield

        koala_stored_episodes = show.get_koala_stored_eps()
        nonadded_episodes = new_episodes - koala_stored_episodes
        if nonadded_episodes:
            if not koala_stored_episodes:
                metadata = scraper.get_show_metadata(show.urlid)
                show.write_nfo(metadata)
            for episode in nonadded_episodes:
                episode.write_nfo()
                episode.delete_htm()
                episode.write_htm()
            log.info("NFOs created, waiting for second lib update: %s, %s" %
                     (show, sorted(nonadded_episodes, key=attrgetter('code'))))
            yield

            koala_stored_episodes = show.get_koala_stored_eps()
            nonadded_episodes = new_episodes - koala_stored_episodes
            if nonadded_episodes:
                log.info("Failed to add episodes: %s, %s" % (show, sorted(nonadded_episodes, key=attrgetter('code'))))

        added_episodes = koala_stored_episodes - nonadded_episodes
        for lib_entry in added_episodes:
            lib_entry.load_playcount()

        if settings["added_notifications"]:
            show.notify(new_episodes)
        log.info("Added episodes: %s, %s" % (show, sorted(added_episodes, key=attrgetter('code'))))
    if unav_episodes:
        log.info("Removed episodes: %s, %s" % (show, sorted(unav_episodes, key=attrgetter('code'))))
    databases.stored_shows.upsert(show)


def readd_show(show):
    log.info("Readding show: %s" % show.title)
    for step in update_add_show(show):
        yield step
    databases.excluded_shows.remove(show)
    log.info("Finished readding show: %s" % show.title)


############################
class Task(object):
    def __init__(self, obj, func):
        self.obj = obj
        self.func = func
        self.coroutine = None
        self.exception = None
        self.finished = False

    @staticmethod
    def coro_mapper(task):
        '''Executes next step in coroutine sent as arg,
           Prints traceback otherwise swallowed due to multithreading
           Stores indication of whether coroutine is finished (stopiteration), errored (exception), or unfinished
           '''
        try:
            next(task.coroutine)
        except StopIteration:
            task.finished = True
        except Exception as exc:
            log.info("Error adding/updating %s:\n%s" % (task.obj, traceback.format_exc().decode(sys.getfilesystemencoding())))
            task.exception = exc
            task.finished = True

    @staticmethod
    def func_mapper(task):
        '''Stores indication of whether function errored'''
        try:
            task.func(task.obj)
        except Exception as exc:
            log.info("Error removing %s:\n%s" % (task.obj, traceback.format_exc().decode(sys.getfilesystemencoding())))
            task.exception = exc


############################
# helper functions
def select_mediaitem(database):
    if not database:
        dialogs.ok(heading="No media", line1="No relevant media seems to be in library")
        return None
    objects = sorted(database, key=attrgetter("title"))
    titles = [media.title for media in objects]
    selected = dialogs.select(list=titles, heading='Select %s' % database.mediatype)
    return objects[selected] if selected != -1 else None


def edit_prioritized_shows():
    databases.stored_shows.load()
    databases.prioritized_shows.load()
    if not databases.stored_shows:
        dialogs.ok(heading="No media", line1="No TV shows seems to be in library")
        return None
    objects = sorted(databases.stored_shows, key=attrgetter("title"))
    titles = ["[Prioritized] %s" % show.title if show in databases.prioritized_shows else show.title for show in objects]
    while True:
        selected = dialogs.select('Select shows to prioritize', titles)
        if selected == -1:
            break
        show = objects[selected]
        if show not in databases.prioritized_shows:
            databases.prioritized_shows.add(show)
            titles[selected] = "[Prioritized] %s" % show.title
        else:
            databases.prioritized_shows.remove(show)
            titles[selected] = show.title


def get_watchlist_changes(session, tasks):
    available_movies, available_shows = session.getwatchlist()

    unav_movies = databases.stored_movies - available_movies
    log.info("unavailable_movies:\n %s" % unav_movies)
    tasks["removals"].extend([Task(movie, remove_movie) for movie in unav_movies])

    unav_shows = databases.stored_shows - available_shows
    log.info("unavailable_shows:\n %s" % unav_shows)
    tasks["removals"].extend([Task(show, remove_show) for show in unav_shows])

    new_movies = available_movies - (databases.stored_movies | databases.excluded_movies)
    log.info("new_movies:\n %s" % new_movies)
    tasks["updates"].extend([Task(movie, add_movie) for movie in new_movies])

    new_shows = available_shows - (databases.stored_shows | databases.excluded_shows)
    log.info("new_shows:\n %s" % new_shows)
    tasks["updates"].extend([Task(show, update_add_show) for show in new_shows])


def get_n_shows(tasks, all_shows, n_shows):
    prioritized_stored = list(databases.prioritized_shows & databases.stored_shows)
    nonprioritized_stored = list(databases.stored_shows - databases.prioritized_shows)
    if not all_shows:
        nonprioritized_stored = nonprioritized_stored[:n_shows]
    tasks["updates"].extend([Task(show, update_add_show) for show in prioritized_stored + nonprioritized_stored])


############################
# Fetch tasks functions
def remove_all_fetch():
    databases.stored_movies.load()
    databases.stored_shows.load()
    if not (databases.stored_movies or databases.stored_shows):
        dialogs.ok(heading="No media", line1="No movies or TV shows seems to be in library")
        return
    tasks = {"removals": [Task(movie, remove_movie) for movie in databases.stored_movies] +
                         [Task(show, remove_show) for show in databases.stored_shows]}
    return tasks


def update_all_fetch():
    databases.stored_shows.load()
    if not databases.stored_shows:
        dialogs.ok(heading="No media", line1="No TV shows seems to be in library")
        return
    tasks = {"updates": [Task(show, update_add_show) for show in databases.stored_shows]}
    return tasks


def update_single_fetch():
    databases.stored_shows.load()
    show = select_mediaitem(databases.stored_shows)
    if not show:
        return
    tasks = {"updates": [Task(show, update_add_show)]}
    return tasks


def exclude_show_fetch():
    databases.stored_shows.load()
    databases.excluded_shows.load()
    show = select_mediaitem(databases.stored_shows)
    if not show:
        return
    tasks = {"removals": [Task(show, exclude_show)]}
    return tasks


def exclude_movie_fetch():
    databases.stored_movies.load()
    databases.excluded_movies.load()
    movie = select_mediaitem(databases.stored_movies)
    if not movie:
        return
    tasks = {"removals": [Task(movie, exclude_movie)]}
    return tasks


def readd_show_fetch():
    databases.stored_shows.load()
    databases.excluded_shows.load()
    show = select_mediaitem(databases.excluded_shows)
    if not show:
        return
    tasks = {"updates": [Task(show, readd_show)]}
    return tasks


def readd_movie_fetch():
    databases.stored_movies.load()
    databases.excluded_movies.load()
    movie = select_mediaitem(databases.excluded_movies)
    if not movie:
        return
    tasks = {"updates": [Task(movie, readd_movie)]}
    return tasks


def startup_fetch():
    for db in (databases.stored_movies, databases.stored_shows, databases.excluded_movies,
               databases.excluded_shows, databases.prioritized_shows):
        db.load()
    tasks = {"updates": [], "removals": []}
    if settings["shows on startup"]:
        get_n_shows(tasks, all_shows=settings["all shows on startup"], n_shows=settings["n shows on startup"])
    # wathclist tasks fetched after login
    return tasks


def schedule_fetch():
    for db in (databases.stored_movies, databases.stored_shows, databases.excluded_movies,
               databases.excluded_shows, databases.prioritized_shows):
        db.load()
    tasks = {"updates": [], "removals": []}
    if settings["shows on schedule"]:
        get_n_shows(tasks, all_shows=settings["all shows on schedule"], n_shows=settings["n shows on schedule"])
    # wathclist tasks fetched after login
    return tasks


def watchlist_fetch():
    databases.stored_movies.load()
    databases.stored_shows.load()
    databases.excluded_movies.load()
    databases.excluded_shows.load()
    # wathclist tasks fetched after login
    tasks = {"removals": [], "updates": []}
    return tasks


############################
def main(action):
    pool = None
    progressbar = ProgressDialog()
    try:
        if action == "prioritize":
            edit_prioritized_shows()
            return

        switch = {
            "remove_all": remove_all_fetch,
            "update_all": update_all_fetch,
            "update_single": update_single_fetch,
            "exclude_show": exclude_show_fetch,
            "exclude_movie": exclude_movie_fetch,
            "readd_show": readd_show_fetch,
            "readd_movie": readd_movie_fetch,
            "startup": startup_fetch,
            "schedule": schedule_fetch,
            "watchlist": watchlist_fetch,
        }
        tasks = switch[action]()

        if tasks is None:
            return

        if action == "watchlist" or (action in ["startup", "schedule"] and settings["watchlist on %s" % action]):
            progressbar.goto(10)
            session = scraper.RequestsSession()
            session.setup()

            progressbar.goto(20)
            get_watchlist_changes(session, tasks)

            if not (tasks["removals"] or tasks["updates"]):
                return

        removals = tasks.get("removals", [])
        updates = tasks.get("updates", [])

        # step1
        progressbar.goto(30)
        map(Task.func_mapper, removals)

        if updates:

            for task in updates:
                task.coroutine = task.func(task.obj)

            if settings['multithreading'] and len(updates) > 1:
                pool = threading.Pool(5)
                map_ = pool.map
            else:
                map_ = map

            # step2
            progressbar.goto(40)
            map_(Task.coro_mapper, updates)

            step3 = [task for task in updates if not task.finished]
            if step3:
                progressbar.goto(50)
                monitor = ScanMonitor()
                monitor.update_video_library()

                # step3
                progressbar.goto(60)
                map_(Task.coro_mapper, step3)

                step4 = [task for task in step3 if not task.finished]
                if step4:
                    progressbar.goto(70)
                    monitor.update_video_library()

                    # step4
                    progressbar.goto(80)
                    map_(Task.coro_mapper, step4)

        progressbar.goto(100)
        errors = [task for task in removals + updates if task.exception is not None]
        if errors:
            raise Exception("\nAttempted %d updates and %d library removals, with %d error(s):\n"
                            "%s." % (len(removals), len(updates), len(errors),
                                     "\n".join(["%s: %s" % (task.obj, unicode(task.exception)) for task in errors])))

    finally:
        if pool is not None:
            pool.close()
        for db in (databases.stored_movies, databases.stored_shows, databases.excluded_movies,
                   databases.excluded_shows, databases.prioritized_shows):
            if db.loaded and db.edited:
                db.commit()
        progressbar.close()
