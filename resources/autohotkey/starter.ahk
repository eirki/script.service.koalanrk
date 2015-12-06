#NoEnv
#ErrorStdOut
#SingleInstance Force
SendMode Input ; Forces Send and SendRaw to use SendInput buffering for speed.
SetTitleMatchMode, 2 ; A window's title must exactly match WinTitle to be a match.

ComObjError(false)

WinWait, NRK TV, , 60
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

while WinExist("NRK TV") and not WinActive("Adobe Flash Player"){
    MouseClick, left, %left%, %top%, 2, 100
    Sleep, 2000
}
