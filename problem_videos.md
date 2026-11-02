# Problem Videos

YouTube videos that exposed a bug in this program, newest first, with what went wrong and the commits that fixed it.

### 2026-11-02 — [ALGS Year 6 Split 2 Playoffs | Grand Finals - Day 4](https://www.youtube.com/watch?v=PhvT9CeyARY)
7-hour stream recording. Clicking 3/4 along the progress bar restarted it from the beginning instead of jumping ahead. Fixed by opening WebM previews with VLC's FFmpeg-based reader, which keeps the separate audio track in step after a seek ([deac1c5](https://github.com/BBC-Esq/Youtube_Player/commit/deac1c5)).

### 2026-11-01 — [Should Food Cost More? | The Onion](https://www.youtube.com/watch?v=LtvPbNf7dPM)
4K. The preview froze after a second or two and reported a restricted stream. Fixed by streaming previews through a local relay that gets around YouTube's throttling ([275f117](https://github.com/BBC-Esq/Youtube_Player/commit/275f117)); previews also start at 1080p now ([7d72dcd](https://github.com/BBC-Esq/Youtube_Player/commit/7d72dcd)).

### 2026-10-25 — [He-Man Official | 3 HOUR COMPILATION](https://www.youtube.com/watch?v=K8t5Uwtyau8)
Made for kids. Downloads failed because YouTube offered only protected streams. Fixed by retrying other YouTube clients when that happens ([2941d36](https://github.com/BBC-Esq/Youtube_Player/commit/2941d36)), plus a pytubefix update those clients rely on ([a952fad](https://github.com/BBC-Esq/Youtube_Player/commit/a952fad)).

### 2026-08-18 — [Icona Pop - I Love It (Feat. Charli XCX) \[Audio\]](https://www.youtube.com/watch?v=W50HtcPAeSs)
Label-uploaded music. YouTube refused it to the default client, and the preview claimed to be playing when it never started. Fixed by falling back to other YouTube clients ([f2369fa](https://github.com/BBC-Esq/Youtube_Player/commit/f2369fa)), checking that a preview really started ([87040a1](https://github.com/BBC-Esq/Youtube_Player/commit/87040a1)), and adding Watch in Browser for videos the program cannot play ([995634e](https://github.com/BBC-Esq/Youtube_Player/commit/995634e)).
