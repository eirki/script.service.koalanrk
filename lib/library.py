#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals
import multiprocessing.dummy as threading
import os
import re
from functools import partial
import traceback
import types
import json
from operator import attrgetter
import xbmcgui
import xbmc

from . utils import (os_join, uni_join, stringtofile)
from . import scraper
from . import constants as const
from . import database
from . xbmcwrappers import (rpc, log, settings, dialogs, ProgressDialog, ScanMonitor)
from . mediatypes import (KoalaMovie, Show)


############################
# helper functions
def obj_mapper(obj):
    '''1: execute next step in generator sent as arg,
       2: print traceback otherwise swallowed due to multithreading
       3: Return indication of whether generator is finished (stopiteration), errored (exception), or unfinished
       '''
    try:
        next(obj.task)
        obj.finished = False
    except StopIteration:
        obj.finished = True
    except Exception as exc:
        log.info("Error adding/updating %s:\n%s" % (obj, traceback.format_exc()))
        obj.exception = exc
        obj.finished = True


def select_mediaitem(database):
    if not database:
        dialogs.ok(heading="No media", line1="No relevant media seems to be in library")
        return None
    objects = sorted(database, key=attrgetter("title"))
    titles = [media.title for media in objects]
    selected = dialogs.select(list=titles, heading='Select %s' % database.mediatype)
    return objects[selected] if selected != -1 else None


############################
# main functions
def edit_prioritized_shows(stored_shows, prioritized_shows):
    if not stored_shows:
        dialogs.ok(heading="No media", line1="No TV shows seems to be in library")
        return None
    objects = sorted(stored_shows, key=attrgetter("title"))
    titles = ["[Prioritized] %s" % show.title if show in prioritized_shows else show.title for show in objects]
    while True:
        selected = dialogs.select('Select shows to prioritize', titles)
        if selected == -1:
            break
        show = objects[selected]
        if show not in prioritized_shows:
            prioritized_shows.add(show)
            titles[selected] = "[Prioritized] %s" % show.title
        else:
            prioritized_shows.remove(show)
            titles[selected] = show.title


def fetch_mediaobjects(action, session, stored_movies, stored_shows,
                       excluded_movies, excluded_shows, prioritized_shows):
    update_tasks = []
    removal_tasks = []
    if action == "remove_all":
        if not stored_movies or stored_shows:
            dialogs.ok(heading="No media", line1="No movies or TV shows seems to be in library")
            return
        for movie in stored_movies:
            movie.generate_removal_task(db_stored=stored_movies)
            removal_tasks.append(movie)
        for show in stored_shows:
            show.generate_removal_task(db_stored=stored_shows)
            removal_tasks.append(show)

    elif action == "update_all":
        if not stored_shows:
            dialogs.ok(heading="No media", line1="No TV shows seems to be in library")
            return
        for show in stored_shows:
            show.generate_update_task(db_stored=stored_shows, session=session)
            update_tasks.append(show)

    elif action == "update_single":
        show = select_mediaitem(stored_shows)
        if not show:
            return
        show.generate_update_task(db_stored=stored_shows, session=session)
        update_tasks.append(show)

    elif action == "exclude_show":
        show = select_mediaitem(stored_shows)
        if not show:
            return
        show.generate_removal_task(db_stored=stored_shows, exclude=True, db_excluded=excluded_shows)
        removal_tasks.append(show)

    elif action == "exclude_movie":
        movie = select_mediaitem(stored_movies)
        if not movie:
            return
        movie.generate_removal_task(db_stored=stored_movies, exclude=True, db_excluded=excluded_movies)
        removal_tasks.append(movie)

    elif action == "readd_show":
        show = select_mediaitem(excluded_shows)
        if not show:
            return
        show.generate_update_task(db_stored=stored_shows, session=session, readd=True, db_excluded=excluded_shows)
        update_tasks.append(show)

    elif action == "readd_movie":
        movie = select_mediaitem(excluded_movies)
        if not movie:
            return
        movie.generate_update_task(db_stored=stored_movies, session=session, readd=True, db_excluded=excluded_movies)
        update_tasks.append(movie)

    elif action in ["startup", "schedule", "watchlist"]:
        if action == "watchlist" or (action in ["startup", "schedule"] and settings["watchlist on %s" % action]):
            available_movies, available_shows = session.getwatchlist()

            unav_movies = stored_movies - available_movies
            log.info("unavailable_movies:\n %s" % unav_movies)
            for movie in unav_movies:
                movie.generate_removal_task(db_stored=stored_movies)
                removal_tasks.append(movie)

            unav_shows = stored_shows - available_shows
            log.info("unavailable_shows:\n %s" % unav_shows)
            for show in unav_shows:
                show.generate_removal_task(db_stored=stored_shows)
                removal_tasks.append(show)

            new_movies = available_movies - (stored_movies | excluded_movies)
            log.info("new_movies:\n %s" % new_movies)
            for movie in new_movies:
                movie.generate_add_task(db_stored=stored_movies, session=session)
                update_tasks.append(movie)

            new_shows = available_shows - (stored_shows | excluded_shows)
            log.info("new_shows:\n %s" % new_shows)
            for show in new_shows:
                show.generate_update_task(db_stored=stored_shows, session=session)
                update_tasks.append(show)

        else:
            unav_shows = set()

        if action in ["startup", "schedule"] and settings["shows on %s" % action]:
            prioritized_stored = list((prioritized_shows & stored_shows) - unav_shows)
            nonprioritized_stored = list((stored_shows - prioritized_shows) - unav_shows)
            if not settings["all shows on %s" % action]:
                n = settings["n shows on %s" % action]
                nonprioritized_stored = nonprioritized_stored[:n]
            for show in prioritized_stored + nonprioritized_stored:
                show.generate_update_task(db_stored=stored_shows, session=session)
                update_tasks.append(show)

    return removal_tasks, update_tasks


def main(action):
    stored_movies = database.MediaDatabase(mediaclass=KoalaMovie, name='movies')
    excluded_movies = database.MediaDatabase(mediaclass=KoalaMovie, name='excluded movies')
    stored_shows = database.MediaDatabase(mediaclass=Show, name='shows', retain_order=True)
    excluded_shows = database.MediaDatabase(mediaclass=Show, name='excluded shows')
    prioritized_shows = database.MediaDatabase(mediaclass=Show, name='prioritized shows')

    if action == "prioritize":
        edit_prioritized_shows(stored_shows, prioritized_shows)
        prioritized_shows.commit()
        return
    try:
        pool = None
        progressbar = ProgressDialog()
        requests_session = scraper.RequestsSession() if action in ["update_all", "watchlist", "startup", "schedule",
                                                                   "update_single", "readd_show", "readd_movie"] else None

        if action == "watchlist" or (action in ["startup", "schedule"] and settings["watchlist on %s" % action]):
            progressbar.goto(10)
            requests_session.setup()
            progressbar.goto(20)

        tasks = fetch_mediaobjects(action, session=requests_session, stored_movies=stored_movies,
                                   excluded_movies=excluded_movies, stored_shows=stored_shows,
                                   excluded_shows=excluded_shows, prioritized_shows=prioritized_shows)
        if not tasks:
            return

        removal_tasks, update_tasks = tasks

        if action in ["update_all", "update_single", "readd_show", "readd_movie"]:
            progressbar.goto(30)
            requests_session.setup()

        progressbar.goto(20)
        for obj in removal_tasks:
            try:
                obj.task()
            except Exception as exc:
                log.info("Error removing %s:\n%s" % (obj, traceback.format_exc()))
                obj.exception = exc

        if update_tasks:
            if settings['multithreading'] and len(update_tasks) > 1:
                pool = threading.Pool(5)
                map_ = pool.map
            else:
                map_ = map

            progressbar.goto(30)
            map_(obj_mapper, update_tasks)

            step2 = [obj for obj in update_tasks if not obj.finished]
            if step2:
                progressbar.goto(40)
                monitor = ScanMonitor()
                monitor.update_video_library()
                progressbar.goto(50)
                map_(obj_mapper, step2)

                step3 = [obj for obj in step2 if not obj.finished]
                if step3:
                    progressbar.goto(60)
                    monitor.update_video_library()
                    progressbar.goto(70)
                    map_(obj_mapper, step3)

        progressbar.goto(100)
        errors = [obj for obj in removal_tasks + update_tasks if obj.exception is not None]
        if errors:
            raise Exception("%d library updates finished with %d error(s):\n\n"
                            "%s." % (len(update_tasks), len(errors),
                                     "\n".join(["%s: %s" % (obj, unicode(obj.exception)) for obj in errors])))

    finally:
        if pool is not None:
            pool.close()
        for db in stored_movies, excluded_movies, stored_shows, excluded_shows, prioritized_shows:
            db.commit()
        progressbar.close()
