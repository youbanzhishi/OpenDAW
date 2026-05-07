/*
 * VST3Host.cpp — JUCE-based VST3 plugin host implementation.
 */
#include "VST3Host.h"

#include <juce_core/juce_core.h>
#include <iostream>

VST3Host::VST3Host() {
    formatManager.addDefaultFormats();
}

std::vector<PluginInfo> VST3Host::scanPlugins() {
    std::vector<PluginInfo> results;

    auto* vst3Format = formatManager.getFormat(
        juce::AudioPluginFormatManager::VST3);

    if (vst3Format == nullptr) {
        std::cerr << "VST3Host: VST3 format not available. "
                  << "Check JUCE VST3 support.\n";
        return results;
    }

    // Build search paths from OS defaults
    juce::FileSearchPath searchPaths;
    for (const auto& p : getDefaultSearchPaths()) {
        searchPaths.add(juce::File(p));
    }

    // Scan for plugin files
    auto pluginFiles = vst3Format->searchPathsForPlugins(searchPaths, false);

    for (const auto& file : pluginFiles) {
        PluginInfo info;
        info.path = file;
        info.name = juce::File(file).getFileNameWithoutExtension().toStdString();

        // Try to get more info by creating a temporary description
        juce::PluginDescription desc;
        desc.fileOrIdentifier = file;
        desc.pluginFormatName = "VST3";

        juce::String errorMessage;
        auto instance = formatManager.createPluginInstance(
            desc, 44100.0, 512, errorMessage);

        if (instance != nullptr) {
            info.manufacturer = instance->getPluginDescription()
                                    .manufacturerName.toStdString();
            info.category = instance->getPluginDescription()
                                .category.toStdString();
            info.isInstrument = instance->getPluginDescription()
                                    .isInstrument;
        }

        results.push_back(std::move(info));
    }

    return results;
}

std::vector<std::string> VST3Host::getDefaultSearchPaths() {
    std::vector<std::string> paths;

#if JUCE_LINUX
    paths.push_back("/usr/lib/vst3");
    paths.push_back("/usr/local/lib/vst3");
    paths.push_back(std::string(getenv("HOME") ? getenv("HOME") : "/root") +
                    "/.vst3");
#elif JUCE_MAC
    paths.push_back("/Library/Audio/Plug-Ins/VST3");
    paths.push_back(std::string(getenv("HOME") ? getenv("HOME") : "/Users") +
                    "/Library/Audio/Plug-Ins/VST3");
#elif JUCE_WINDOWS
    paths.push_back("C:\\Program Files\\Common Files\\VST3");
    paths.push_back("C:\\Program Files (x86)\\Common Files\\VST3");
    const char* pf = getenv("PROGRAMFILES");
    if (pf) paths.push_back(std::string(pf) + "\\Common Files\\VST3");
#endif

    return paths;
}

std::unique_ptr<juce::AudioPluginInstance> VST3Host::loadPlugin(
    const std::string& pluginPath,
    double sampleRate,
    int blockSize) {
    // First, check if the file exists
    if (!juce::File(pluginPath).exists()) {
        std::cerr << "VST3Host: Plugin file not found: " << pluginPath << "\n";
        return nullptr;
    }

    // Build plugin description
    juce::PluginDescription desc;
    desc.fileOrIdentifier = juce::String(pluginPath);
    desc.pluginFormatName = "VST3";
    desc.uniqueId = 0;

    // Attempt to create the instance
    juce::String errorMessage;
    auto instance = formatManager.createPluginInstance(
        desc, sampleRate, blockSize, errorMessage);

    if (instance == nullptr) {
        std::cerr << "VST3Host: Failed to load plugin: "
                  << pluginPath << "\n"
                  << "  Error: " << errorMessage.toStdString() << "\n";
        return nullptr;
    }

    std::cerr << "VST3Host: Loaded plugin: "
              << instance->getName().toStdString() << "\n"
              << "  Inputs: " << instance->getTotalNumInputChannels() << "\n"
              << "  Outputs: " << instance->getTotalNumOutputChannels() << "\n"
              << "  Parameters: " << instance->getParameters().size() << "\n";

    return instance;
}
