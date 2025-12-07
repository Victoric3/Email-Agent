@echo off
REM Download English auto-subtitles only (no video) for top 10 leads
yt-dlp --write-auto-subs --sub-lang en --skip-download "https://youtu.be/4SWEpdg81y0?si=f4f-Myy7oUDwNui-"
yt-dlp --write-auto-subs --sub-lang en --skip-download "https://youtu.be/9xzxc-8rFno?si=aV8-r0TLmeqITiyg"
yt-dlp --write-auto-subs --sub-lang en --skip-download "https://youtu.be/Awoaxic8t2M?si=Tp2b7a6lZjxPpOoS"
yt-dlp --write-auto-subs --sub-lang en --skip-download "https://youtu.be/MyHnIREZg4k?si=mRLj0CA2wd1TkL2S"
yt-dlp --write-auto-subs --sub-lang en --skip-download "https://youtu.be/n-DUKAXq3tg?si=ovbYdgpx0qfNCpZ3"
yt-dlp --write-auto-subs --sub-lang en --skip-download "https://youtu.be/edTFSnznfoA?si=YPgib7oFZUBIx6-Q"
yt-dlp --write-auto-subs --sub-lang en --skip-download "https://youtu.be/a7vTTbREb3A?si=4MzZmJFFrx8yK5k3"
yt-dlp --write-auto-subs --sub-lang en --skip-download "https://youtu.be/4XF_mOxCN3k?si=qYQSIUx-Bc10W2it"
yt-dlp --write-auto-subs --sub-lang en --skip-download "https://youtu.be/2KtWzHtbinc?si=sC_pFbvvq8hI9sEu"
yt-dlp --write-auto-subs --sub-lang en --skip-download "https://youtu.be/Y6BnbEFnPuQ?si=MzJ__1ClCnhAKD_I"

echo Done. Subtitles will be saved in the current folder alongside the metadata saved by yt-dlp.
pause
