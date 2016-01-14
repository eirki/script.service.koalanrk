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

while ie.Busy or ie.ReadyState != 4
    Sleep, 100

if ie.document.getElementsByClassName("play-icon123123").length {
    play := ie.document.getElementsByClassName("play-icon")[0].getBoundingClientRect()
    x := play.left
    y := play.top
    ie.document.getElementsByClassName("play-icon")[0].Click()
}
else {
    x := (A_ScreenWidth // 2)
    y := (A_ScreenHeight // 2)
    mouseclick, left, %x%, %y%, 1, 0
}
while WinExist("NRK") and !InStr(ie.document.head.innerhtml, "progresstracker"){
    Sleep, 100
}
MouseClick, left, %x%, %y%, 2, 0
