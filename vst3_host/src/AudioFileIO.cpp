/*
 * AudioFileIO.cpp — WAV file I/O implementation using dr_wav.
 */
#include "AudioFileIO.h"

#define DR_WAV_IMPLEMENTATION
#include <dr_wav.h>

#include <cstdio>
#include <cstring>

namespace AudioFileIO {

AudioData readWav(const std::string& path) {
    AudioData result;

    drwav wav;
    if (!drwav_init_file(&wav, path.c_str(), nullptr)) {
        std::fprintf(stderr, "AudioFileIO: Failed to open WAV file: %s\n", path.c_str());
        return result;
    }

    result.channels = wav.channels;
    result.sampleRate = wav.sampleRate;
    result.totalFrames = wav.totalPCMFrameCount;

    // Read all frames as interleaved float
    result.samples.resize(static_cast<size_t>(result.totalFrames) * result.channels);
    uint64_t framesRead = drwav_read_pcm_frames_f32(
        &wav, result.totalFrames, result.samples.data());

    if (framesRead != result.totalFrames) {
        std::fprintf(stderr, "AudioFileIO: Read %llu frames, expected %llu\n",
                     (unsigned long long)framesRead,
                     (unsigned long long)result.totalFrames);
        result.totalFrames = framesRead;
        result.samples.resize(static_cast<size_t>(framesRead) * result.channels);
    }

    drwav_uninit(&wav);
    return result;
}

bool writeWav(const std::string& path, const AudioData& audio) {
    return writeWavRaw(path, audio.samples.data(),
                       audio.channels, audio.sampleRate,
                       audio.totalFrames);
}

bool writeWavRaw(const std::string& path,
                 const float* data,
                 unsigned int channels,
                 unsigned int sampleRate,
                 uint64_t totalFrames) {
    drwav wav;
    drwav_data_format format;
    format.container = drwav_container_riff;
    format.format = DR_WAVE_FORMAT_IEEE_FLOAT;
    format.channels = channels;
    format.sampleRate = sampleRate;
    format.bitsPerSample = 32;

    if (!drwav_init_file_write(&wav, path.c_str(), &format, nullptr)) {
        std::fprintf(stderr, "AudioFileIO: Failed to create WAV file: %s\n", path.c_str());
        return false;
    }

    uint64_t framesWritten = drwav_write_pcm_frames(
        &wav, totalFrames, data);

    drwav_uninit(&wav);

    if (framesWritten != totalFrames) {
        std::fprintf(stderr, "AudioFileIO: Wrote %llu frames, expected %llu\n",
                     (unsigned long long)framesWritten,
                     (unsigned long long)totalFrames);
        return false;
    }

    return true;
}

} // namespace AudioFileIO
