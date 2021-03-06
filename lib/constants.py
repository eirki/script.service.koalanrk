#! /usr/bin/env python2
# -*- coding: utf-8 -*-
from __future__ import (unicode_literals, absolute_import, division)

import xbmcaddon
import xbmc

addon = xbmcaddon.Addon()
addonid = addon.getAddonInfo("id").decode("utf-8")
provider = "NRK"
addonname = "Koala %s" % provider
addonpath = xbmc.translatePath(addon.getAddonInfo('path')).decode("utf-8")
userdatafolder = xbmc.translatePath("special://profile/addon_data/%s" % addonid).decode("utf-8")
masterprofilefolder = xbmc.translatePath("special://masterprofile").decode("utf-8")
homefolder = xbmc.translatePath("special://home").decode("utf-8")
if addon.getSetting("usecustomLibPath"):
    libpath = xbmc.translatePath(addon.getSetting("LibPath")).decode("utf-8")
else:
    libpath = xbmc.translatePath("special://profile/addon_data/%s/Library" % addonid).decode("utf-8")

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
