ENGLISH = "en"


def track_key(stream):
    if not stream.includes_multiple_audio_tracks:
        return ""
    return stream.audio_track_name_regionalized or stream.audio_track_language_id_regionalized or ""


def track_label(stream):
    name = track_key(stream) or "Default"
    return f"{name} (original)" if stream.is_default_audio_track else name


def available_tracks(streams):
    first_by_key = {}
    for stream in streams:
        key = track_key(stream)
        if key:
            first_by_key.setdefault(key, stream)
    ordered = sorted(
        first_by_key.values(),
        key=lambda s: (not s.is_default_audio_track, track_key(s).lower()),
    )
    return [(track_key(s), track_label(s)) for s in ordered]


def default_track(streams):
    tracks = [s for s in streams if track_key(s)]
    english = [s for s in tracks if (s.audio_track_language_id or "").lower() == ENGLISH]
    for group in (
        [s for s in english if s.is_default_audio_track],
        english,
        [s for s in tracks if s.is_default_audio_track],
        tracks,
    ):
        if group:
            return track_key(group[0])
    return ""


def streams_for_track(streams, key):
    return [s for s in streams if track_key(s) == key]
