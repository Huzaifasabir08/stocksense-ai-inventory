Dim voice, stream
Set voice = CreateObject("SAPI.SpVoice")
Set stream = CreateObject("SAPI.SpFileStream")
stream.Format.Type = 21
stream.Open WScript.Arguments(0), 3, True
Set voice.AudioOutputStream = stream
voice.Speak WScript.Arguments(1)
stream.Close
