AUDIO_FORMATS = {
    "MP3": {"codec": "mp3", "extension": "mp3", "container": "mp3", "lossy": True},
    "AAC": {"codec": "aac", "extension": "aac", "container": "adts", "lossy": True},
    "FLAC": {"codec": "flac", "extension": "flac", "container": "flac", "lossy": False},
    "WAV": {"codec": "pcm_s16le", "extension": "wav", "container": "wav", "lossy": False},
    "Opus": {"codec": "libopus", "extension": "opus", "container": "opus", "lossy": True, "sample_rate": 48000},
}

CODEC_SAMPLE_FORMATS = {
    "mp3": "s16p",
    "aac": "fltp",
    "flac": "s16",
    "pcm_s16le": "s16",
    "libopus": "flt",
}

BITRATE_OPTIONS = ["96", "128", "160", "192", "256", "320"]
SAMPLE_RATE_OPTIONS = ["22050", "44100", "48000"]
CHANNEL_OPTIONS = {"Stereo": 2, "Mono": 1}

VIDEO_CODEC_NAMES = {
    "avc1": "H.264",
    "avc3": "H.264",
    "hev1": "H.265",
    "hvc1": "H.265",
    "av01": "AV1",
    "vp8": "VP8",
    "vp9": "VP9",
    "vp09": "VP9",
}

VIDEO_CODEC_TOOLTIPS = {
    "H.264": "Older but most widely compatible video codec. Larger files because it's less efficient at compression, but plays on virtually everything.",
    "H.265": "Successor to H.264 with better compression. Good compatibility on modern devices, but not universally supported on older hardware.",
    "AV1": "Newer codec with much better compression. Smaller files at the same quality, but requires more CPU to decode and isn't supported on older hardware/software.",
    "VP8": "Google's older open video codec. Decent compatibility but largely superseded by VP9.",
    "VP9": "Google's open video codec with good compression. Falls between H.264 and AV1 in efficiency. Widely supported in modern browsers.",
}

AUDIO_CODEC_NAMES = {
    "mp4a": "AAC",
    "aac": "AAC",
    "opus": "Opus",
    "vorbis": "Vorbis",
    "mp3": "MP3",
}

AUDIO_CODEC_TOOLTIPS = {
    "Opus": "Modern, highly efficient codec. Best quality-per-bitrate of all options. Natively in WebM containers. Widely supported in browsers but less so in older media players.",
    "AAC": "Standard audio codec in MP4 containers. Universal compatibility across all devices and players. Slightly less efficient than Opus at the same bitrate.",
    "Vorbis": "Older open-source codec in WebM/OGG containers. Decent quality but largely superseded by Opus.",
    "MP3": "Legacy format with universal compatibility. Least efficient of the group but plays everywhere.",
}

MP4_VIDEO_CODECS = {"avc1", "avc3", "hev1", "hvc1", "av01"}
MP4_AUDIO_CODECS = {"mp4a", "aac", "mp3"}
WEBM_VIDEO_CODECS = {"vp8", "vp9", "vp09", "av01"}
WEBM_AUDIO_CODECS = {"opus", "vorbis"}


def detect_mux_container(video_codec, audio_codec):
    v = video_codec.split(".")[0].lower() if video_codec else ""
    a = audio_codec.split(".")[0].lower() if audio_codec else ""

    v_mp4 = v in MP4_VIDEO_CODECS
    a_mp4 = a in MP4_AUDIO_CODECS
    v_webm = v in WEBM_VIDEO_CODECS
    a_webm = a in WEBM_AUDIO_CODECS

    if v_mp4 and a_mp4:
        return "mp4", ".mp4"
    if v_webm and a_webm:
        return "webm", ".webm"
    return "matroska", ".mkv"
