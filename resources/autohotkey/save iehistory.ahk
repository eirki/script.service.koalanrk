SetTitleMatchMode, 2
historyfile = %1%
WinWait % "Internet Explorer"
WinWait % "NRK"

for win in ComObjCreate("Shell.Application").Windows
	If InStr(win.FullName, "iexplore.exe")
		break

while (win.busy)
	Sleep, 1000

FileAppend, % A_NowUTC . " " . win.LocationURL . "`n", % historyfile
activeurl := win.LocationURL

while (WinExist("Internet Explorer")){
	if (activeurl != win.LocationURL){
		FileAppend, % A_NowUTC . " " . win.LocationURL . "`n", % historyfile
		activeurl := win.LocationURL
	}
	sleep, 1000
}
