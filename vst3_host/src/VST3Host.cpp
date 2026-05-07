/*
 * VST3Host.cpp — VST3 plugin host implementation (Phase 14 enhanced).
 */
#include "VST3Host.h"

#include <juce_core/juce_core.h>
#include <iostream>
#include <cstring>

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
            auto& plugDesc = instance->getPluginDescription();
            info.manufacturer = plugDesc.manufacturerName.toStdString();
            info.category = plugDesc.category.toStdString();
            info.version = plugDesc.version.toStdString();
            info.isInstrument = plugDesc.isInstrument;
            info.numParams = instance->getParameters().size();
            info.numInputChannels = instance->getTotalNumInputChannels();
            info.numOutputChannels = instance->getTotalNumOutputChannels();
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
    if (!juce::File(pluginPath).exists()) {
        std::cerr << "VST3Host: Plugin file not found: " << pluginPath << "\n";
        return nullptr;
    }

    juce::PluginDescription desc;
    desc.fileOrIdentifier = juce::String(pluginPath);
    desc.pluginFormatName = "VST3";
    desc.uniqueId = 0;

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

juce::AudioProcessor* VST3Host::createProcessor(
    const std::string& pluginPath,
    double sampleRate,
    int blockSize) {
    auto instance = loadPlugin(pluginPath, sampleRate, blockSize);
    if (instance == nullptr) return nullptr;

    setupProcessing(*instance, sampleRate, blockSize);
    loadedPlugins.push_back(std::move(instance));
    return loadedPlugins.back().get();
}

void VST3Host::setupProcessing(
    juce::AudioPluginInstance& plugin,
    double sampleRate,
    int blockSize) {
    plugin.prepareToPlay(sampleRate, blockSize);
}

void VST3Host::processAudio(
    juce::AudioPluginInstance& plugin,
    const float* input,
    float* output,
    int numSamples,
    int numInputChannels,
    int numOutputChannels) {
    int numChannels = std::max(numInputChannels, numOutputChannels);
    if (numChannels == 0) numChannels = 2;

    juce::AudioBuffer<float> buffer(numChannels, numSamples);

    // Copy input (de-interleave)
    buffer.clear();
    for (int s = 0; s < numSamples; ++s) {
        for (int ch = 0; ch < numInputChannels && ch < numChannels; ++ch) {
            buffer.setSample(ch, s, input[s * numInputChannels + ch]);
        }
    }

    // Process
    juce::MidiBuffer midiBuffer;
    plugin.processBlock(buffer, midiBuffer);

    // Copy output (interleave)
    for (int s = 0; s < numSamples; ++s) {
        for (int ch = 0; ch < numOutputChannels && ch < numChannels; ++ch) {
            output[s * numOutputChannels + ch] = buffer.getSample(ch, s);
        }
    }
}

void VST3Host::setParameter(
    juce::AudioPluginInstance& plugin,
    int index,
    float value) {
    auto& params = plugin.getParameters();
    if (index < 0 || index >= static_cast<int>(params.size())) return;
    value = std::max(0.0f, std::min(1.0f, value));
    params[index]->setValue(value);
}

float VST3Host::getParameter(
    juce::AudioPluginInstance& plugin,
    int index) {
    auto& params = plugin.getParameters();
    if (index < 0 || index >= static_cast<int>(params.size())) return 0.0f;
    return params[index]->getValue();
}

std::string VST3Host::getParameterName(
    juce::AudioPluginInstance& plugin,
    int index) {
    auto& params = plugin.getParameters();
    if (index < 0 || index >= static_cast<int>(params.size())) return "";
    return params[index]->getName(64).toStdString();
}

std::vector<uint8_t> VST3Host::getState(
    juce::AudioPluginInstance& plugin) {
    std::vector<uint8_t> state;
    juce::MemoryBlock block;
    plugin.getStateInformation(block);
    state.resize(block.getSize());
    std::memcpy(state.data(), block.getData(), block.getSize());
    return state;
}

bool VST3Host::setState(
    juce::AudioPluginInstance& plugin,
    const uint8_t* data,
    size_t size) {
    if (data == nullptr || size == 0) return false;
    plugin.setStateInformation(data, static_cast<int>(size));
    return true;
}
