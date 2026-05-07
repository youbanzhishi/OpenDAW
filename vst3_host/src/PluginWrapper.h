/*
 * PluginWrapper.h — High-level wrapper around a loaded VST3 plugin.
 *
 * Provides:
 *   - Parameter get/set by index or name
 *   - Preset loading (.vstpreset or factory presets)
 *   - Audio rendering with optional MIDI input
 *   - Parameter info export (for YAML config generation)
 */
#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include "AudioFileIO.h"
#include <memory>
#include <string>
#include <vector>

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
     *
     * Returns the rendered audio data.
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

private:
    /** Convert MidiEvent list to JUCE MidiBuffer. */
    juce::MidiBuffer buildMidiBuffer(
        const std::vector<MidiEvent>& events,
        double durationSeconds) const;

    std::unique_ptr<juce::AudioPluginInstance> plugin;
    double sampleRate;
    int blockSize;
    bool prepared = false;
};
