; NRK starter
#NoEnv
#ErrorStdOut
#SingleInstance Force
ComObjError(false)
SetTitleMatchMode, 2
DetectHiddenText, off
SendMode Input


WinWait, NRK, , 60
WinActivate
GetExplorer() {
    for win in ComObjCreate("Shell.Application").Windows {
        If InStr(win.FullName, "iexplore.exe") {
            ie = 1
            break
        }
    }
    return win
}
WaitandExitonQuit() {
    Sleep, 100
    if (A_LastError = -2147023174) {
        ExitApp
    }
}

wb := GetExplorer()
while wb.Busy or wb.ReadyState != 4 or not wb.document.getElementsByClassName("play-icon").length
    WaitandExitonQuit()
play := wb.document.getElementsByClassName("play-icon")[0].getBoundingClientRect()
left := play.left
top := play.top
wb.document.getElementsByClassName("play-icon")[0].Click()

while WinExist("NRK") and !InStr(wb.document.head.innerhtml, "progresstracker"){
    Sleep, 100
}
MouseClick, left, %left%, %top%, 2, 0
