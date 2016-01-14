; NRK remote
#Persistent
#NoEnv
#ErrorStdOut
#SingleInstance Force
ComObjError(false)
SetTitleMatchMode, 2
CoordMode, Mouse, Screen

SysGet, Mon, Monitor
if (MonRight = 1920 and MonBottom = 1080)
{
	pausex := 1920
	pausey := 870
}
else if (MonRight = 1280 and MonBottom = 720)
{
	pausex := 1920
	pausey := 870
}
browser  = %1%
r_play = %2%
r_pause = %3%
r_stop = %4%
r_fforw = %5%
r_rewnd = %6%

Hotkey, IfWinActive, %browser%
if r_play
	Hotkey, %r_play%  , pauselabel
if r_pause
	Hotkey, %r_pause%  , pauselabel
if r_stop
	Hotkey, %r_stop%  , stoplabel
if r_fforw
	Hotkey, %r_fforw%  , fforwlabel
if r_rewnd
	Hotkey, %r_rewnd%  , rewlabel

Return


pauselabel:
	; MsgBox You pressed playpause %A_ThisHotkey%.
	MouseMove, pausex, pausey
	sleep, 100
	MouseClick
	sleep, 30
	MouseMove, MonRight, MonBottom, 0
Return
stoplabel:
	; MsgBox You pressed stop %A_ThisHotkey%.
	Send !{f4}
Return
fforwlabel:
	send {Right}
	; MsgBox You pressed fastforward %A_ThisHotkey%.
Return
rewlabel:
	send {Left}
	; MsgBox You pressed rewind %A_ThisHotkey%.
Return
