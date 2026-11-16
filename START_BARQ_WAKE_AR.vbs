Option Explicit
Dim shell, fso, root, launcher, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
launcher = root & "\BARQ_Wake.exe"
If fso.FileExists(launcher) Then
    command = Chr(34) & launcher & Chr(34)
Else
    launcher = root & "\scripts\barq_wake_vosk.py"
    command = "py -3.11 " & Chr(34) & launcher & Chr(34)
End If
shell.Run command, 0, False
