Set ws = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)

If fso.FileExists(currentDir & "\dist\FFmpegStudio\FFmpegStudio.exe") Then
    ws.Run """" & currentDir & "\dist\FFmpegStudio\FFmpegStudio.exe""", 0, False
Else
    ws.CurrentDirectory = currentDir
    ws.Run "pythonw gui_main.py", 0, False
End If
