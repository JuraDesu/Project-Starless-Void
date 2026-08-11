$r p_music {
    c_audio_source {
        audio_music,
        audio_playback::playing,
        true,
        0.35f
    };
};

$r g_start {
    world.spawn<p_music>();
};
