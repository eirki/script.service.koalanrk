; NRK save ie history
#NoEnv
#ErrorStdOut
#SingleInstance Force
ComObjError(false)
SetTitleMatchMode, 2
historyfile = %1%
WinWait % "Internet Explorer"
WinWait % "NRK"
sleep, 1000

GetExplorer() {
    for win in ComObjCreate("Shell.Application").Windows {
        Sleep, 2000
        If InStr(win.FullName, "iexplore.exe") {
            break
        }
    }
    return win
}

ie := GetExplorer()

while (ie.busy)
	Sleep, 1000

FileAppend, % A_NowUTC . " " . ie.LocationURL . "`n", % historyfile
activeurl := ie.LocationURL

while (WinExist("Internet Explorer")){
	if (activeurl != ie.LocationURL){
		FileAppend, % A_NowUTC . " " . ie.LocationURL . "`n", % historyfile
		activeurl := ie.LocationURL
	}
	sleep, 1000
}
