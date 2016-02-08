#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import xbmcaddon
import xbmc

addon = xbmcaddon.Addon()
addonpath = xbmc.translatePath(addon.getAddonInfo('path')).decode("utf-8")
userdatafolder = xbmc.translatePath("special://profile/addon_data/script.service.koalanrk").decode("utf-8")
if addon.getSetting("usecustomLibPath"):
    libpath = xbmc.translatePath(addon.getSetting("LibPath")).decode("utf-8")
else:
    libpath = xbmc.translatePath("special://profile/addon_data/script.service.koalanrk/Library").decode("utf-8")

if xbmc.getCondVisibility("system.platform.linux"):
    os = "linux"
elif xbmc.getCondVisibility("system.platform.windows"):
    os = "win"
elif xbmc.getCondVisibility("system.platform.osx"):
    os = "osx"
elif xbmc.getCondVisibility("system.platform.android"):
    os = "android"
else:
    os = "other"
