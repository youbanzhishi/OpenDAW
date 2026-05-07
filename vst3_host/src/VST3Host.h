/*
 * VST3Host.h — JUCE-based VST3 plugin host manager.
 *
 * Manages the AudioPluginFormatManager and provides
 * plugin discovery (scanning) and instantiation.
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
    bool isInstrument;
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

    /** Get the format manager (for advanced usage). */
    juce::AudioPluginFormatManager& getFormatManager() { return formatManager; }

private:
    juce::AudioPluginFormatManager formatManager;
    juce::KnownPluginList knownPluginList;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR(VST3Host)
};
