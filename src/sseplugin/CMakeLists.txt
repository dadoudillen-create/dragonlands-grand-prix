cmake_minimum_required(VERSION 3.24)
project(DragonlandsGP VERSION 0.2.0 LANGUAGES CXX RC)
set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")

# CommonLibSSE NG (alandtse/CommonLibVR ng 11.0.0, GPL-3.0-or-later) from tools/, built as part of this project
set(BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(ENABLE_SKYRIM_VR OFF CACHE BOOL "" FORCE)
add_subdirectory(${CMAKE_SOURCE_DIR}/../../extern/CommonLibVR ${CMAKE_BINARY_DIR}/CommonLibSSE EXCLUDE_FROM_ALL)

add_library(DragonlandsGP SHARED src/main.cpp src/car.cpp src/version.rc)
target_link_libraries(DragonlandsGP PRIVATE CommonLibSSE::CommonLibSSE xinput)
# runtime selection comes from CommonLibSSE options (SE+AE on, VR off)
target_precompile_headers(DragonlandsGP PRIVATE src/pch.h)
# loaded by Ultimate ASI Loader (Melty installs it): ship as DragonlandsGP.asi next to SkyrimSE.exe
set_target_properties(DragonlandsGP PROPERTIES SUFFIX ".asi")
