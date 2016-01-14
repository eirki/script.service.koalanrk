#
# Initialization for the win32com package
#

import win32api, sys, os
import pythoncom
print 1
# flag if we are in a "frozen" build.
_frozen = getattr(sys, "frozen", 1==0)
# pythoncom dumbly defaults this to zero - we believe sys.frozen over it.
if _frozen and not getattr(pythoncom, "frozen", 0):
	print 2
	pythoncom.frozen = sys.frozen

# Add support for an external "COM Extensions" path.
#  Concept is that you can register a seperate path to be used for
#  COM extensions, outside of the win32com directory.  These modules, however,
#  look identical to win32com built-in modules.
#  This is the technique that we use for the "standard" COM extensions.
#  eg "win32com.mapi" or "win32com.axscript" both work, even though they do not
#  live under the main win32com directory.
__gen_path__ = ''
__build_path__ = None
### TODO - Load _all_ \\Extensions subkeys - for now, we only read the default
### Modules will work if loaded into "win32comext" path.

def SetupEnvironment():
	print 3
	HKEY_LOCAL_MACHINE = -2147483646 # Avoid pulling in win32con for just these...
	KEY_QUERY_VALUE = 0x1
	# Open the root key once, as this is quite slow on NT.
	try:
		print 4
		keyName = "SOFTWARE\\Python\\PythonCore\\%s\\PythonPath\\win32com" % sys.winver
		print keyName
		print 5
		key = win32api.RegOpenKey(HKEY_LOCAL_MACHINE , keyName, 0, KEY_QUERY_VALUE)
		print 6
		print key
	except (win32api.error, AttributeError):
		print 7
		key = None

	try:
		print 8
		found = 0
		if key is not None:
			try:
				print 9
				__path__.append( win32api.RegQueryValue(key, "Extensions" ))
				found = 1
			except win32api.error:
				print 10
				# Nothing registered
				pass
		if not found:
			try:
				print 11
				__path__.append( win32api.GetFullPathName( __path__[0] + "\\..\\win32comext") )
			except win32api.error:
				print 12
				# Give up in disgust!
				pass

		# For the sake of developers, we also look up a "BuildPath" key
		# If extension modules add support, we can load their .pyd's from a completely
		# different directory (see the comments below)
		try:
			print 13
			if key is not None:
				print 14
				global __build_path__
				print 15
				__build_path__ = win32api.RegQueryValue(key, "BuildPath")
				__path__.append(__build_path__)
		except win32api.error:
			print 16
			# __build_path__ neednt be defined.
			pass
		global __gen_path__
		if key is not None:
			print 17
			try:
				__gen_path__ = win32api.RegQueryValue(key, "GenPath")
			except win32api.error:
				print 18
				pass
	finally:
		print 19
		if key is not None:
			print 20
			key.Close()

# A Helper for developers.  A sub-package's __init__ can call this help function,
# which allows the .pyd files for the extension to live in a special "Build" directory
# (which the win32com developers do!)
def __PackageSupportBuildPath__(package_path):
	# See if we have a special directory for the binaries (for developers)
	print 21
	if not _frozen and __build_path__:
		print 22
		package_path.append(__build_path__)

if not _frozen:
	print 23
	SetupEnvironment()

# If we don't have a special __gen_path__, see if we have a gen_py as a
# normal module and use that (ie, "win32com.gen_py" may already exist as
# a package.
if not __gen_path__:
	print 24
	try:
		print 25
		import win32com.gen_py
		# hrmph - 3.3 throws: TypeError: '_NamespacePath' object does not support indexing
		# attempting to get __path__[0] - but I can't quickly repro this stand-alone.
		# Work around it by using an iterator.
		__gen_path__ = iter(sys.modules["win32com.gen_py"].__path__).next()
	except ImportError:
		print 26
		# If a win32com\gen_py directory already exists, then we use it
		# (gencache doesn't insist it have an __init__, but our __import__
		# above does!
		__gen_path__ = os.path.abspath(os.path.join(__path__[0], "gen_py"))
		if not os.path.isdir(__gen_path__):
			print 27
			# We used to dynamically create a directory under win32com -
			# but this sucks.  If the dir doesn't already exist, we we
			# create a version specific directory under the user temp
			# directory.
			__gen_path__ = os.path.join(
								win32api.GetTempPath(), "gen_py",
								"%d.%d" % (sys.version_info[0], sys.version_info[1]))

# we must have a __gen_path__, but may not have a gen_py module -
# set that up.
if "win32com.gen_py" not in sys.modules:
	print 28
	# Create a "win32com.gen_py", but with a custom __path__
	import imp
	gen_py = imp.new_module("win32com.gen_py")
	gen_py.__path__ = [ __gen_path__ ]
	sys.modules[gen_py.__name__]=gen_py
	del imp
gen_py = sys.modules["win32com.gen_py"]

# get rid of these for module users
del os, sys, win32api, pythoncom
