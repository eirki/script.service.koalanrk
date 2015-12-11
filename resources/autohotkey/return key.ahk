; NRK return key
; Wait for the user to press any key.  Keys that produce no visible character -- such as
; the modifier keys, function keys, and arrow keys -- are listed as end keys so that they
; will be detected too.
Input, SingleKey, L1, {Enter}.{Esc}{Media_Play_Pause}{Media_Stop}{Media_prev}{Media_next}{AppsKey}{F1}{F2}{F3}{F4}{F5}{F6}{F7}{F8}{F9}{F10}{F11}{F12}{Left}{Right}{Up}{Down}{Home}{End}{PgUp}{PgDn}{Del}{Ins}{BS}{Capslock}{Numlock}{PrintScreen}{Pause}{Space}
FileAppend, % SingleKey ", " ErrorLevel, *
Send, {Enter}
ExitApp
