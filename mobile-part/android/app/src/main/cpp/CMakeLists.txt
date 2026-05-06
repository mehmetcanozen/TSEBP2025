cmake_minimum_required(VERSION 3.22.1)

project(suppressionaudio LANGUAGES CXX)

find_package(oboe REQUIRED CONFIG)

add_library(
  suppressionaudio
  SHARED
  native_oboe_audio_engine.cpp
)

target_compile_features(suppressionaudio PRIVATE cxx_std_17)

target_link_libraries(
  suppressionaudio
  oboe::oboe
  android
  log
)
