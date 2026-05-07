/*
 * PluginWrapper.h — High-level wrapper around a loaded VST3 plugin.
 *
 * Provides:
 *   - Parameter get/set by index or name
 *   - Preset loading (.vstpreset or factory presets)
 *   - Audio rendering with optional MIDI input
 *   - Parameter info export (for YAML config generation)
 *   - Parameter automation support (Phase 14)
 *   - MIDI input handling (Phase 14)
 *   - State serialization (Phase 14)
 */
#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include "AudioFileIO.h"
#include <memory>
#include <string>
#include <vector>
#include <map>

struct ParamInfo {
    int index;
    std::string id;         // paramID string (JUCE assigned)
    std::string name;
    std::string category;
    float currentValue;     // normalized [0,1]
    float defaultValue;     // normalized [0,1]
};

struct MidiEvent {
    std::string type;       // "note_on", "note_off", "cc"
    int channel = 0;
    int note = 60;          // for note events
    int velocity = 100;     // for note_on
    int cc = 0;             // for CC events
    int value = 0;          // for CC events
    double timeSeconds = 0.0;
};

struct AutomationPoint {
    double timeSeconds;
    float value;            // normalized [0,1]
};

class PluginWrapper {
public:
    /**
     * Construct wrapper around an existing plugin instance.
     * Takes ownership of the instance.
     */
    PluginWrapper(std::unique_ptr<juce::AudioPluginInstance> plugin,
                  double sampleRate = 44100.0,
                  int blockSize = 512);
    ~PluginWrapper() = default;

    /** Initialize the plugin for processing (prepareToPlay). */
    bool prepare();

    /** Set a parameter by index (0-based), value is normalized [0,1]. */
    void setParamByIndex(int index, float value);

    /** Set a parameter by name match, value is normalized [0,1]. */
    bool setParamByName(const std::string& name, float value);

    /** Get current parameter value by index. */
    float getParamByIndex(int index) const;

    /** Get all parameter info. */
    std::vector<ParamInfo> getParamInfo() const;

    /** Load a .vstpreset file. */
    bool loadPresetFile(const std::string& path);

    /**
     * Render audio from an input WAV file.
     * For effects: input audio is processed through the plugin.
     * For instruments: input may be empty, MIDI events generate audio.
     */
    AudioData renderFromInput(const AudioData& input,
                              const std::vector<MidiEvent>& midiEvents = {});

    /**
     * Render audio for an instrument (no input file).
     * Generates audio purely from MIDI events for the given duration.
     */
    AudioData renderInstrument(double durationSeconds,
                               const std::vector<MidiEvent>& midiEvents);

    /** Check if this is an instrument (synth) plugin. */
    bool isInstrument() const;

    /** Get plugin name. */
    std::string getName() const;

    /** Get the raw JUCE plugin instance (for advanced usage). */
    juce::AudioPluginInstance* getPlugin() const { return plugin.get(); }

    // ── Phase 14 additions ────────────────────────────────────────────────

    /** Set parameter automation for a specific parameter. */
    void setAutomation(int paramIndex, const std::vector<AutomationPoint>& points);

    /** Clear automation for a parameter. */
    void clearAutomation(int paramIndex);

    /** Clear all automation. */
    void clearAllAutomation();

    /** Get plugin state as raw bytes. */
    std::vector<uint8_t> getState() const;

    /** Restore plugin state from raw bytes. */
    bool setState(const uint8_t* data, size_t size);

    /** Get number of parameters. */
    int getNumParameters() const;

    /** Get parameter name by index. */
    std::string getParamName(int index) const;

    /** Process a single block of audio with MIDI. */
    void processBlock(juce::AudioBuffer<float>& buffer,
                      const juce::MidiBuffer& midiBuffer);

private:
    /** Convert MidiEvent list to JUCE MidiBuffer. */
    juce::MidiBuffer buildMidiBuffer(
        const std::vector<MidiEvent>& events,
        double durationSeconds) const;

    /** Apply automation for a given sample position range. */
    void applyAutomation(int startSample, int numSamples);

    std::unique_ptr<juce::AudioPluginInstance> plugin;
    double sampleRate;
    int blockSize;
    bool prepared = false;

    // Automation data: paramIndex -> list of automation points
    std::map<int, std::vector<AutomationPoint>> automationData;
};
