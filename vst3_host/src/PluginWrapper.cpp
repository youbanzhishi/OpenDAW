/*
 * PluginWrapper.cpp — VST3 plugin wrapper implementation (Phase 14 enhanced).
 */
#include "PluginWrapper.h"

#include <juce_core/juce_core.h>
#include <iostream>
#include <cmath>
#include <algorithm>

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
    if (numChannels == 0) numChannels = 2;

    uint64_t totalFrames = input.totalFrames;
    output.channels = static_cast<unsigned int>(numChannels);
    output.sampleRate = static_cast<unsigned int>(sampleRate);
    output.totalFrames = totalFrames;
    output.samples.resize(static_cast<size_t>(totalFrames) * numChannels, 0.0f);

    double durationSeconds = static_cast<double>(totalFrames) / sampleRate;
    juce::MidiBuffer midiBuffer = buildMidiBuffer(midiEvents, durationSeconds);

    juce::AudioBuffer<float> audioBuffer(numChannels, blockSize);

    uint64_t framesProcessed = 0;
    auto midiIt = midiBuffer.begin();

    while (framesProcessed < totalFrames) {
        int framesThisBlock = std::min(
            static_cast<int>(totalFrames - framesProcessed), blockSize);

        audioBuffer.clear();

        // Copy input (de-interleave)
        int inputChannels = static_cast<int>(input.channels);
        for (int ch = 0; ch < numChannels; ++ch) {
            int srcCh = ch < inputChannels ? ch : 0;
            for (int s = 0; s < framesThisBlock; ++s) {
                uint64_t srcIdx = (framesProcessed + s) * input.channels + srcCh;
                if (srcIdx < input.samples.size()) {
                    audioBuffer.setSample(ch, s, input.samples[srcIdx]);
                }
            }
        }

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
                ++midiIt;
            } else {
                break;
            }
        }

        // Apply automation
        applyAutomation(static_cast<int>(framesProcessed), framesThisBlock);

        // Trim buffer for last block
        juce::AudioBuffer<float> processBuffer(
            audioBuffer.getArrayOfWritePointers(),
            numChannels,
            framesThisBlock);

        plugin->processBlock(processBuffer, blockMidi);

        // Copy output (interleave)
        for (int s = 0; s < framesThisBlock; ++s) {
            for (int ch = 0; ch < numChannels; ++ch) {
                uint64_t dstIdx = (framesProcessed + s) * numChannels + ch;
                if (dstIdx < output.samples.size()) {
                    output.samples[dstIdx] = processBuffer.getSample(ch, s);
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
                ++midiIt;
            } else {
                break;
            }
        }

        // Apply automation
        applyAutomation(static_cast<int>(framesProcessed), framesThisBlock);

        juce::AudioBuffer<float> processBuffer(
            audioBuffer.getArrayOfWritePointers(),
            numChannels,
            framesThisBlock);

        plugin->processBlock(processBuffer, blockMidi);

        // Interleave output
        for (int s = 0; s < framesThisBlock; ++s) {
            for (int ch = 0; ch < numChannels; ++ch) {
                uint64_t dstIdx = (framesProcessed + s) * numChannels + ch;
                if (dstIdx < output.samples.size()) {
                    output.samples[dstIdx] = processBuffer.getSample(ch, s);
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

// ── Phase 14 additions ────────────────────────────────────────────────────

void PluginWrapper::setAutomation(int paramIndex,
                                   const std::vector<AutomationPoint>& points) {
    automationData[paramIndex] = points;
    std::sort(automationData[paramIndex].begin(),
              automationData[paramIndex].end(),
              [](const AutomationPoint& a, const AutomationPoint& b) {
                  return a.timeSeconds < b.timeSeconds;
              });
}

void PluginWrapper::clearAutomation(int paramIndex) {
    automationData.erase(paramIndex);
}

void PluginWrapper::clearAllAutomation() {
    automationData.clear();
}

std::vector<uint8_t> PluginWrapper::getState() const {
    std::vector<uint8_t> state;
    if (plugin == nullptr) return state;

    juce::MemoryBlock block;
    plugin->getStateInformation(block);
    state.resize(block.getSize());
    std::memcpy(state.data(), block.getData(), block.getSize());
    return state;
}

bool PluginWrapper::setState(const uint8_t* data, size_t size) {
    if (plugin == nullptr || data == nullptr || size == 0) return false;
    plugin->setStateInformation(data, static_cast<int>(size));
    return true;
}

int PluginWrapper::getNumParameters() const {
    if (plugin == nullptr) return 0;
    return static_cast<int>(plugin->getParameters().size());
}

std::string PluginWrapper::getParamName(int index) const {
    if (plugin == nullptr) return "";
    auto& params = plugin->getParameters();
    if (index < 0 || index >= static_cast<int>(params.size())) return "";
    return params[index]->getName(64).toStdString();
}

void PluginWrapper::processBlock(juce::AudioBuffer<float>& buffer,
                                  const juce::MidiBuffer& midiBuffer) {
    if (plugin == nullptr || !prepared) return;
    plugin->processBlock(buffer, midiBuffer);
}

void PluginWrapper::applyAutomation(int startSample, int numSamples) {
    if (automationData.empty() || plugin == nullptr) return;

    double startTime = startSample / sampleRate;
    double endTime = (startSample + numSamples) / sampleRate;

    for (auto& [paramIndex, points] : automationData) {
        if (points.empty()) continue;

        // Find the automation value at the start of this block
        float value = 0.0f;
        bool found = false;
        for (const auto& point : points) {
            if (point.timeSeconds <= startTime) {
                value = point.value;
                found = true;
            } else {
                break;
            }
        }

        if (found) {
            setParamByIndex(paramIndex, value);
        }
    }
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
                ev.channel + 1,
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
