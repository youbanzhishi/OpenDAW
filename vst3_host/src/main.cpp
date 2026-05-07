/*
 * main.cpp — CLI entry point for VST3 Host.
 *
 * Usage:
 *   vst3_host list                              — List system VST3 plugins
 *   vst3_host params --plugin PATH              — Export parameter list
 *   vst3_host process --plugin PATH             — Process audio
 *     [--input INPUT.wav] [--output OUTPUT.wav]
 *     [--preset NAME|--preset-file FILE]
 *     [--param INDEX=VALUE]...
 *     [--midi-file FILE.json|.mid]
 *     [--bpm N] [--duration SECONDS]
 *     [--sample-rate N] [--block-size N]
 */
#include "VST3Host.h"
#include "PluginWrapper.h"
#include "AudioFileIO.h"

#include <iostream>
#include <string>
#include <vector>
#include <cstdlib>
#include <cstring>

// ── Simple argument parser ─────────────────────────────────────────────────

struct Args {
    std::string command;           // list, params, process
    std::string pluginPath;
    std::string inputPath;
    std::string outputPath;
    std::string presetName;
    std::string presetFile;
    std::string midiFile;
    std::vector<std::pair<int, float>> params;  // index=value
    double bpm = 120.0;
    double duration = 0.0;
    double sampleRate = 44100.0;
    int blockSize = 512;
};

static void printUsage() {
    std::cerr << "VST3 Host — OpenDAW VST3 Plugin Processor\n\n"
              << "Usage:\n"
              << "  vst3_host list\n"
              << "  vst3_host params --plugin PATH\n"
              << "  vst3_host process --plugin PATH [options]\n\n"
              << "Options:\n"
              << "  --input PATH         Input WAV file (for effects)\n"
              << "  --output PATH        Output WAV file (default: output.wav)\n"
              << "  --preset NAME        Load factory preset by name\n"
              << "  --preset-file PATH   Load .vstpreset file\n"
              << "  --param IDX=VAL      Set parameter (0-based index, normalized 0-1)\n"
              << "  --midi-file PATH     MIDI file (.mid or .json)\n"
              << "  --bpm N              Tempo for MIDI timing (default: 120)\n"
              << "  --duration SECS      Render duration for instruments (seconds)\n"
              << "  --sample-rate N      Sample rate (default: 44100)\n"
              << "  --block-size N       Processing block size (default: 512)\n";
}

static Args parseArgs(int argc, char* argv[]) {
    Args args;

    if (argc < 2) {
        printUsage();
        std::exit(1);
    }

    args.command = argv[1];

    for (int i = 2; i < argc; ++i) {
        std::string arg = argv[i];

        if (arg == "--plugin" && i + 1 < argc) {
            args.pluginPath = argv[++i];
        } else if (arg == "--input" && i + 1 < argc) {
            args.inputPath = argv[++i];
        } else if (arg == "--output" && i + 1 < argc) {
            args.outputPath = argv[++i];
        } else if (arg == "--preset" && i + 1 < argc) {
            args.presetName = argv[++i];
        } else if (arg == "--preset-file" && i + 1 < argc) {
            args.presetFile = argv[++i];
        } else if (arg == "--midi-file" && i + 1 < argc) {
            args.midiFile = argv[++i];
        } else if (arg == "--param" && i + 1 < argc) {
            std::string paramStr = argv[++i];
            auto eqPos = paramStr.find('=');
            if (eqPos != std::string::npos) {
                int idx = std::stoi(paramStr.substr(0, eqPos));
                float val = std::stof(paramStr.substr(eqPos + 1));
                args.params.emplace_back(idx, val);
            }
        } else if (arg == "--bpm" && i + 1 < argc) {
            args.bpm = std::stod(argv[++i]);
        } else if (arg == "--duration" && i + 1 < argc) {
            args.duration = std::stod(argv[++i]);
        } else if (arg == "--sample-rate" && i + 1 < argc) {
            args.sampleRate = std::stod(argv[++i]);
        } else if (arg == "--block-size" && i + 1 < argc) {
            args.blockSize = std::stoi(argv[++i]);
        } else if (arg == "--help" || arg == "-h") {
            printUsage();
            std::exit(0);
        }
    }

    return args;
}

// ── Command: list ──────────────────────────────────────────────────────────

static int cmdList() {
    VST3Host host;
    auto plugins = host.scanPlugins();

    if (plugins.empty()) {
        std::cout << "No VST3 plugins found.\n";
        std::cout << "Searched paths:\n";
        for (const auto& p : VST3Host::getDefaultSearchPaths()) {
            std::cout << "  " << p << "\n";
        }
        return 0;
    }

    std::cout << "Found " << plugins.size() << " VST3 plugin(s):\n\n";

    for (const auto& p : plugins) {
        std::cout << "  Name: " << p.name << "\n"
                  << "  Path: " << p.path << "\n"
                  << "  Type: " << (p.isInstrument ? "Instrument" : "Effect") << "\n"
                  << "  Mfr:  " << p.manufacturer << "\n\n";
    }

    return 0;
}

// ── Command: params ────────────────────────────────────────────────────────

static int cmdParams(const Args& args) {
    if (args.pluginPath.empty()) {
        std::cerr << "Error: --plugin required for params command.\n";
        return 1;
    }

    VST3Host host;
    auto instance = host.loadPlugin(args.pluginPath, args.sampleRate, args.blockSize);
    if (!instance) return 1;

    PluginWrapper wrapper(std::move(instance), args.sampleRate, args.blockSize);
    wrapper.prepare();

    auto paramInfo = wrapper.getParamInfo();

    // Output as JSON-like format for easy parsing
    std::cout << "{\n";
    std::cout << "  \"plugin\": \"" << wrapper.getName() << "\",\n";
    std::cout << "  \"is_instrument\": " << (wrapper.isInstrument() ? "true" : "false") << ",\n";
    std::cout << "  \"num_params\": " << paramInfo.size() << ",\n";
    std::cout << "  \"params\": [\n";

    for (size_t i = 0; i < paramInfo.size(); ++i) {
        const auto& p = paramInfo[i];
        std::cout << "    {\"index\": " << p.index
                  << ", \"name\": \"" << p.name << "\""
                  << ", \"current\": " << p.currentValue
                  << ", \"default\": " << p.defaultValue
                  << "}";
        if (i + 1 < paramInfo.size()) std::cout << ",";
        std::cout << "\n";
    }

    std::cout << "  ]\n}\n";

    return 0;
}

// ── Command: process ───────────────────────────────────────────────────────

static int cmdProcess(const Args& args) {
    if (args.pluginPath.empty()) {
        std::cerr << "Error: --plugin required for process command.\n";
        return 1;
    }

    VST3Host host;
    auto instance = host.loadPlugin(args.pluginPath, args.sampleRate, args.blockSize);
    if (!instance) return 1;

    PluginWrapper wrapper(std::move(instance), args.sampleRate, args.blockSize);

    // Load preset if specified
    if (!args.presetFile.empty()) {
        if (!wrapper.loadPresetFile(args.presetFile)) {
            std::cerr << "Warning: Failed to load preset file: "
                      << args.presetFile << "\n";
        }
    }

    // Set parameters
    for (const auto& [idx, val] : args.params) {
        wrapper.setParamByIndex(idx, val);
    }

    // Prepare for processing
    if (!wrapper.prepare()) {
        std::cerr << "Error: Failed to prepare plugin.\n";
        return 1;
    }

    // Parse MIDI events (TODO: .mid file support via JUCE MidiFile)
    std::vector<MidiEvent> midiEvents;
    if (!args.midiFile.empty()) {
        // For now, support JSON MIDI files
        // .mid file parsing will use juce::MidiFile
        std::cerr << "Info: MIDI file support coming soon: "
                  << args.midiFile << "\n";
    }

    AudioData output;
    std::string outputPath = args.outputPath.empty() ? "output.wav" : args.outputPath;

    if (wrapper.isInstrument()) {
        // Instrument mode: render from MIDI
        double duration = args.duration;
        if (duration <= 0.0) {
            duration = 10.0;  // default 10 seconds
            std::cerr << "Info: No duration specified, defaulting to "
                      << duration << " seconds.\n";
        }

        output = wrapper.renderInstrument(duration, midiEvents);
    } else {
        // Effect mode: process input WAV
        if (args.inputPath.empty()) {
            std::cerr << "Error: --input required for effect plugins.\n";
            return 1;
        }

        AudioData input = AudioFileIO::readWav(args.inputPath);
        if (input.samples.empty()) {
            std::cerr << "Error: Failed to read input file: "
                      << args.inputPath << "\n";
            return 1;
        }

        output = wrapper.renderFromInput(input, midiEvents);
    }

    if (output.samples.empty()) {
        std::cerr << "Error: Plugin produced no output.\n";
        return 1;
    }

    // Write output
    if (!AudioFileIO::writeWav(outputPath, output)) {
        std::cerr << "Error: Failed to write output file: " << outputPath << "\n";
        return 1;
    }

    std::cerr << "Success: Wrote " << output.totalFrames << " frames ("
              << output.channels << " ch @ " << output.sampleRate << " Hz) to "
              << outputPath << "\n";

    return 0;
}

// ── Main ───────────────────────────────────────────────────────────────────

int main(int argc, char* argv[]) {
    Args args = parseArgs(argc, argv);

    if (args.command == "list") {
        return cmdList();
    } else if (args.command == "params") {
        return cmdParams(args);
    } else if (args.command == "process") {
        return cmdProcess(args);
    } else {
        std::cerr << "Unknown command: " << args.command << "\n";
        printUsage();
        return 1;
    }
}
