yt-dlp -f "bestvideo+bestaudio/best" --merge-output-format mkv --external-downloader aria2c --live-from-start --no-warnings $1 && rm -rf *.aria2
