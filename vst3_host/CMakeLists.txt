cmake_minimum_required(VERSION 3.22)
project(vst3_host VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# ── JUCE via FetchContent ──────────────────────────────────────────────────
include(FetchContent)
FetchContent_Declare(JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG        7.0.9
)
FetchContent_MakeAvailable(JUCE)

# ── dr_wav (single-header WAV I/O) ────────────────────────────────────────
FetchContent_Declare(dr_wav
    GIT_REPOSITORY https://github.com/mackron/dr_wav.git
    GIT_TAG        master
)
FetchContent_MakeAvailable(dr_wav)

# ── vst3_host executable ──────────────────────────────────────────────────
add_executable(vst3_host
    src/main.cpp
    src/VST3Host.cpp
    src/PluginWrapper.cpp
    src/AudioFileIO.cpp
)

target_include_directories(vst3_host PRIVATE
    ${CMAKE_CURRENT_SOURCE_DIR}/src
    ${dr_wav_SOURCE_DIR}           # dr_wav.h
)

target_link_libraries(vst3_host PRIVATE
    juce::juce_audio_processors
    juce::juce_audio_utils
    juce::juce_core
    ${CMAKE_DL_LIBS}               # dlopen on Linux
)

target_compile_definitions(vst3_host PRIVATE
    JUCE_VST3_CAN_REPLACE_VST2=0
    JUCE_STANDALONE_APPLICATION=1
    JUCE_DISPLAY_SPLASH_SCREEN=0
)

# ── Install ───────────────────────────────────────────────────────────────
install(TARGETS vst3_host DESTINATION bin)
