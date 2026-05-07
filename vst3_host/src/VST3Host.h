/*
 * VST3Host.h — VST3 plugin host manager (Phase 14 enhanced).
 *
 * Manages the AudioPluginFormatManager and provides
 * plugin discovery (scanning), instantiation, parameter
 * management, and state serialization.
 *
 * Phase 14 additions:
 *   - createProcessor() — create AudioProcessor from plugin
 *   - setupProcessing() — configure sample rate/block size
 *   - processAudio() — process audio buffers
 *   - setParameter() / getParameter() / getParameterName()
 *   - getState() / setState() — plugin state serialization
 */
#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <memory>
#include <string>
#include <vector>

struct PluginInfo {
    std::string name;
    std::string path;          // fileOrIdentifier
    std::string manufacturer;
    std::string category;
    std::string version;
    bool isInstrument;
    int numParams;
    int numInputChannels;
    int numOutputChannels;
};

class VST3Host {
public:
    VST3Host();
    ~VST3Host() = default;

    /** Scan system VST3 directories and return found plugins. */
    std::vector<PluginInfo> scanPlugins();

    /** Get default VST3 search paths for the current OS. */
    static std::vector<std::string> getDefaultSearchPaths();

    /**
     * Create a plugin instance from a VST3 bundle path.
     * Returns nullptr if loading fails.
     */
    std::unique_ptr<juce::AudioPluginInstance> loadPlugin(
        const std::string& pluginPath,
        double sampleRate = 44100.0,
        int blockSize = 512);

    /**
     * Create an AudioProcessor instance from a loaded plugin.
     * Returns the raw pointer (host retains ownership via unique_ptr).
     */
    juce::AudioProcessor* createProcessor(
        const std::string& pluginPath,
        double sampleRate = 44100.0,
        int blockSize = 512);

    /**
     * Setup processing parameters for a plugin instance.
     * Must be called before processAudio().
     */
    static void setupProcessing(
        juce::AudioPluginInstance& plugin,
        double sampleRate,
        int blockSize);

    /**
     * Process audio through a plugin instance.
     * Input/output are interleaved float buffers.
     */
    static void processAudio(
        juce::AudioPluginInstance& plugin,
        const float* input,
        float* output,
        int numSamples,
        int numInputChannels,
        int numOutputChannels);

    /** Set a parameter by index (0-based), value is normalized [0,1]. */
    static void setParameter(
        juce::AudioPluginInstance& plugin,
        int index,
        float value);

    /** Get a parameter value by index (normalized [0,1]). */
    static float getParameter(
        juce::AudioPluginInstance& plugin,
        int index);

    /** Get parameter name by index. */
    static std::string getParameterName(
        juce::AudioPluginInstance& plugin,
        int index);

    /** Get plugin state as raw bytes. */
    static std::vector<uint8_t> getState(
        juce::AudioPluginInstance& plugin);

    /** Restore plugin state from raw bytes. */
    static bool setState(
        juce::AudioPluginInstance& plugin,
        const uint8_t* data,
        size_t size);

    /** Get the format manager (for advanced usage). */
    juce::AudioPluginFormatManager& getFormatManager() { return formatManager; }

private:
    juce::AudioPluginFormatManager formatManager;
    juce::KnownPluginList knownPluginList;

    // Store loaded plugins
    std::vector<std::unique_ptr<juce::AudioPluginInstance>> loadedPlugins;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(VST3Host)
};
