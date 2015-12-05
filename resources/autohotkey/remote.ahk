#Persistent
SetTitleMatchMode, 2
CoordMode, Mouse, Screen

SysGet, Mon, Monitor
if (MonRight = 1920 and MonBottom = 1080)
{
	pausex := 225
	pausey := 976
}
else if (MonRight = 1280 and MonBottom = 720)
{
	pausex := 148
	pausey := 646
}

r_play = %1%
r_pause = %2%
r_stop = %3%
r_fforw = %4%
r_rewnd = %5%
r_contwtch = %6%

Hotkey, IfWinActive, NRK
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
if r_contwtch
	Hotkey, %r_contwtch%  , contwtchlabel

Return


pauselabel:
	; MsgBox You pressed playpause %A_ThisHotkey%.
	MouseMove, pausex, pausey
	sleep, 100
	MouseClick
	sleep, 30
	MouseMove, 1920, 1080, 0
Return
stoplabel:
	; MsgBox You pressed stop %A_ThisHotkey%.
	Send !{f4}
Return
fforwlabel:
	Send, +{Right}
	; MsgBox You pressed fastforward %A_ThisHotkey%.
Return
rewlabel:
	Send, +{Left}
	; MsgBox You pressed rewind %A_ThisHotkey%.
Return
contwtchlabel:
	MouseMove, 947 ,476
	sleep, 100
	MouseClick
	sleep, 30
	MouseMove, 1920, 1080, 0
	; MsgBox You pressed rewind %A_ThisHotkey%.
Return
