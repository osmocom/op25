#!/usr/bin/liquidsoap

# Example liquidsoap hls streaming from op25 to nginx 
# (c) 2019, 2020 gnorbury@bondcar.com, wllmbecks@gmail.com
# (c)  2020 KA1RBI

set("log.stdout", true)
set("log.file", false)
set("log.level", 1)

set("frame.audio.samplerate", 8000)

input = mksafe(input.external(buffer=0.02, channels=2, samplerate=8000, restart_on_error=false, "./audio.py -x 2 -s -S"))

output.external(%wav(stereo=false, channels=1, samplesize=16, header=false, samplerate=8000), fallible=false, flush=true, "./ffmpeg.sh", mean(input))
