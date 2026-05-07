/*
 * AudioFileIO.h — WAV file I/O using dr_wav for VST3 Host.
 *
 * Provides simple read/write functions for WAV audio files,
 * converting between dr_wav's interleaved PCM format and
 * JUCE's AudioBuffer format.
 */
#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct AudioData {
    std::vector<float> samples;     // interleaved PCM
    unsigned int channels = 0;
    unsigned int sampleRate = 0;
    uint64_t totalFrames = 0;
};

namespace AudioFileIO {

/** Read a WAV file into AudioData (interleaved float PCM). */
AudioData readWav(const std::string& path);

/** Write AudioData to a WAV file (32-bit float). */
bool writeWav(const std::string& path, const AudioData& audio);

/** Write raw float buffer to WAV (interleaved). */
bool writeWavRaw(const std::string& path,
                 const float* data,
                 unsigned int channels,
                 unsigned int sampleRate,
                 uint64_t totalFrames);

} // namespace AudioFileIO
