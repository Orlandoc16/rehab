cmake_minimum_required(VERSION 3.22.1)
project(rehab_whisper C CXX)

# whisper.cpp lo descarga tools/fetch_android_deps.py en android/third_party/whisper.cpp
set(WHISPER_DIR ${CMAKE_CURRENT_SOURCE_DIR}/../../../../third_party/whisper.cpp)
if(NOT EXISTS ${WHISPER_DIR}/CMakeLists.txt)
    message(FATAL_ERROR "Falta whisper.cpp: ejecuta  python tools/fetch_android_deps.py")
endif()

set(BUILD_SHARED_LIBS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(WHISPER_BUILD_SERVER OFF CACHE BOOL "" FORCE)
set(GGML_NATIVE OFF CACHE BOOL "" FORCE)
# Sin OpenMP: ggml usa su propio grupo de hilos (no hay que empaquetar libomp)
set(GGML_OPENMP OFF CACHE BOOL "" FORCE)
# x86_64 (solo el emulador): sin esto ggml usa SSE y Whisper va ~20 veces más lento.
# En arm64 (las tablets) NEON viene activado siempre.
if(ANDROID_ABI STREQUAL "x86_64")
    set(GGML_AVX ON CACHE BOOL "" FORCE)
    set(GGML_AVX2 ON CACHE BOOL "" FORCE)
    set(GGML_FMA ON CACHE BOOL "" FORCE)
    set(GGML_F16C ON CACHE BOOL "" FORCE)
endif()

add_subdirectory(${WHISPER_DIR} whisper EXCLUDE_FROM_ALL)

add_library(rehab_whisper SHARED whisper_jni.c)
target_link_libraries(rehab_whisper PRIVATE whisper log)
# Optimizado también en las compilaciones de depuración (si no, Whisper es muchísimo más lento)
target_compile_options(rehab_whisper PRIVATE -O3)
target_compile_options(whisper PRIVATE -O3)
target_compile_options(ggml-base PRIVATE -O3)
target_compile_options(ggml-cpu PRIVATE -O3)
