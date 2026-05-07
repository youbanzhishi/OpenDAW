/*
 * PluginWrapper.cpp — VST3 plugin wrapper implementation.
 */
#include "PluginWrapper.h"

#include <juce_core/juce_core.h>
#include <iostream>
#include <cmath>

PluginWrapper::PluginWrapper(
    std::unique_ptr<juce::AudioPluginInstance> instance,
    double sr,
    int bs)
    : plugin(std::move(instance))
    , sampleRate(sr)
    , blockSize(bs) {
}

bool PluginWrapper::prepare() {
    if (plugin == nullptr) return false;

    plugin->prepareToPlay(sampleRate, blockSize);
    prepared = true;

    std::cerr << "PluginWrapper: Prepared \"" << getName()
              << "\" at " << sampleRate << " Hz, block size " << blockSize << "\n";
    return true;
}

void PluginWrapper::setParamByIndex(int index, float value) {
    if (plugin == nullptr) return;

    auto& params = plugin->getParameters();
    if (index < 0 || index >= static_cast<int>(params.size())) {
        std::cerr << "PluginWrapper: Parameter index out of range: "
                  << index << " (max " << params.size() - 1 << ")\n";
        return;
    }

    // Clamp to [0,1]
    value = std::max(0.0f, std::min(1.0f, value));
    params[index]->setValue(value);
}

bool PluginWrapper::setParamByName(const std::string& name, float value) {
    if (plugin == nullptr) return false;

    auto& params = plugin->getParameters();
    for (int i = 0; i < static_cast<int>(params.size()); ++i) {
        if (params[i]->getName(64).toStdString() == name) {
            value = std::max(0.0f, std::min(1.0f, value));
            params[i]->setValue(value);
            return true;
        }
    }

    std::cerr << "PluginWrapper: Parameter not found by name: " << name << "\n";
    return false;
}

float PluginWrapper::getParamByIndex(int index) const {
    if (plugin == nullptr) return 0.0f;

    auto& params = plugin->getParameters();
    if (index < 0 || index >= static_cast<int>(params.size())) return 0.0f;
    return params[index]->getValue();
}

std::vector<ParamInfo> PluginWrapper::getParamInfo() const {
    std::vector<ParamInfo> result;
    if (plugin == nullptr) return result;

    auto& params = plugin->getParameters();
    for (int i = 0; i < static_cast<int>(params.size()); ++i) {
        ParamInfo info;
        info.index = i;
        info.name = params[i]->getName(64).toStdString();
        info.currentValue = params[i]->getValue();
        info.defaultValue = params[i]->getDefaultValue();
        result.push_back(std::move(info));
    }

    return result;
}

bool PluginWrapper::loadPresetFile(const std::string& path) {
    if (plugin == nullptr) return false;

    juce::File presetFile(path);
    if (!presetFile.exists()) {
        std::cerr << "PluginWrapper: Preset file not found: " << path << "\n";
        return false;
    }

    auto data = presetFile.loadFileAsData();
    plugin->setStateInformation(data.getData(),
                                static_cast<int>(data.getSize()));
    std::cerr << "PluginWrapper: Loaded preset from " << path << "\n";
    return true;
}

AudioData PluginWrapper::renderFromInput(
    const AudioData& input,
    const std::vector<MidiEvent>& midiEvents) {
    AudioData output;
    if (plugin == nullptr || !prepared) {
        std::cerr << "PluginWrapper: Not prepared or no plugin loaded.\n";
        return output;
    }

    int numChannels = static_cast<int>(
        std::max(plugin->getTotalNumInputChannels(),
                 plugin->getTotalNumOutputChannels()));
    if (numChannels == 0) numChannels = 2;  // fallback

    uint64_t totalFrames = input.totalFrames;
    output.channels = static_cast<unsigned int>(numChannels);
    output.sampleRate = static_cast<unsigned int>(sampleRate);
    output.totalFrames = totalFrames;
    output.samples.resize(static_cast<size_t>(totalFrames) * numChannels, 0.0f);

    // Build MIDI buffer
    double durationSeconds = static_cast<double>(totalFrames) / sampleRate;
    juce::MidiBuffer midiBuffer = buildMidiBuffer(midiEvents, durationSeconds);

    // Process in blocks
    juce::AudioBuffer<float> audioBuffer(numChannels, blockSize);

    uint64_t framesProcessed = 0;
    int midiSampleOffset = 0;

    while (framesProcessed < totalFrames) {
        int framesThisBlock = std::min(
            static_cast<int>(totalFrames - framesProcessed), blockSize);

        // Clear buffer
        audioBuffer.clear();

        // Copy input to buffer (de-interleave)
        int inputChannels = static_cast<int>(input.channels);
        for (int ch = 0; ch < numChannels; ++ch) {
            int srcCh = ch < inputChannels ? ch : 0;  // channel fold
            for (int s = 0; s < framesThisBlock; ++s) {
                uint64_t srcIdx = (framesProcessed + s) * input.channels + srcCh;
                if (srcIdx < input.samples.size()) {
                    audioBuffer.setSample(ch, s, input.samples[srcIdx]);
                }
            }
        }

        // Trim buffer to actual frame count for last block
        if (framesThisBlock < blockSize) {
            audioBuffer = juce::AudioBuffer<float>(
                audioBuffer.getArrayOfWritePointers(),
                numChannels,
                framesThisBlock);
        }

        // Process
        juce::MidiBuffer blockMidi;
        // TODO: Extract MIDI events for this block's time range
        // For now, pass all MIDI on first block
        if (framesProcessed == 0) {
            blockMidi = midiBuffer;
        }

        plugin->processBlock(audioBuffer, blockMidi);

        // Copy output (interleave)
        for (int s = 0; s < framesThisBlock; ++s) {
            for (int ch = 0; ch < numChannels; ++ch) {
                uint64_t dstIdx = (framesProcessed + s) * numChannels + ch;
                if (dstIdx < output.samples.size()) {
                    output.samples[dstIdx] = audioBuffer.getSample(ch, s);
                }
            }
        }

        framesProcessed += framesThisBlock;
    }

    return output;
}

AudioData PluginWrapper::renderInstrument(
    double durationSeconds,
    const std::vector<MidiEvent>& midiEvents) {
    AudioData output;

    if (plugin == nullptr || !prepared) {
        std::cerr << "PluginWrapper: Not prepared or no plugin loaded.\n";
        return output;
    }

    int numChannels = static_cast<int>(plugin->getTotalNumOutputChannels());
    if (numChannels == 0) numChannels = 2;

    uint64_t totalFrames = static_cast<uint64_t>(
        durationSeconds * sampleRate);
    output.channels = static_cast<unsigned int>(numChannels);
    output.sampleRate = static_cast<unsigned int>(sampleRate);
    output.totalFrames = totalFrames;
    output.samples.resize(static_cast<size_t>(totalFrames) * numChannels, 0.0f);

    juce::MidiBuffer midiBuffer = buildMidiBuffer(midiEvents, durationSeconds);

    // Process in blocks
    juce::AudioBuffer<float> audioBuffer(numChannels, blockSize);

    uint64_t framesProcessed = 0;
    auto midiIt = midiBuffer.begin();

    while (framesProcessed < totalFrames) {
        int framesThisBlock = std::min(
            static_cast<int>(totalFrames - framesProcessed), blockSize);

        audioBuffer.clear();

        // Build block MIDI
        juce::MidiBuffer blockMidi;
        while (midiIt != midiBuffer.end()) {
            auto metadata = *midiIt;
            if (metadata.samplePosition >= static_cast<int>(framesProcessed) &&
                metadata.samplePosition < static_cast<int>(framesProcessed + framesThisBlock)) {
                blockMidi.addEvent(metadata.getMessage(),
                                   metadata.samplePosition -
                                   static_cast<int>(framesProcessed));
                ++midiIt;
            } else if (metadata.samplePosition < static_cast<int>(framesProcessed)) {
                ++midiIt;  // skip past events
            } else {
                break;  // future event
            }
        }

        if (framesThisBlock < blockSize) {
            audioBuffer = juce::AudioBuffer<float>(
                audioBuffer.getArrayOfWritePointers(),
                numChannels,
                framesThisBlock);
        }

        plugin->processBlock(audioBuffer, blockMidi);

        // Interleave output
        for (int s = 0; s < framesThisBlock; ++s) {
            for (int ch = 0; ch < numChannels; ++ch) {
                uint64_t dstIdx = (framesProcessed + s) * numChannels + ch;
                if (dstIdx < output.samples.size()) {
                    output.samples[dstIdx] = audioBuffer.getSample(ch, s);
                }
            }
        }

        framesProcessed += framesThisBlock;
    }

    return output;
}

bool PluginWrapper::isInstrument() const {
    if (plugin == nullptr) return false;
    return plugin->getPluginDescription().isInstrument;
}

std::string PluginWrapper::getName() const {
    if (plugin == nullptr) return "(null)";
    return plugin->getName().toStdString();
}

juce::MidiBuffer PluginWrapper::buildMidiBuffer(
    const std::vector<MidiEvent>& events,
    double durationSeconds) const {
    juce::MidiBuffer buffer;

    for (const auto& ev : events) {
        int samplePosition = static_cast<int>(ev.timeSeconds * sampleRate);
        juce::MidiMessage msg;

        if (ev.type == "note_on") {
            msg = juce::MidiMessage::noteOn(
                ev.channel + 1,   // JUCE uses 1-based channels
                ev.note,
                static_cast<uint8>(ev.velocity));
        } else if (ev.type == "note_off") {
            msg = juce::MidiMessage::noteOff(
                ev.channel + 1,
                ev.note,
                static_cast<uint8>(ev.velocity));
        } else if (ev.type == "cc") {
            msg = juce::MidiMessage::controllerEvent(
                ev.channel + 1,
                ev.cc,
                ev.value);
        } else {
            continue;
        }

        msg.setTimeStamp(samplePosition);
        buffer.addEvent(msg, samplePosition);
    }

    return buffer;
}
