cmake_minimum_required(VERSION 3.22)
set(CMAKE_MODULE_PATH ${CMAKE_SOURCE_DIR}/cmake)
project(croissant VERSION 1.0 LANGUAGES C CXX)

set(CXX_FLAGS -g
            -Wall
            -Wreorder
            -Wextra
            -Werror
            -Wconversion
            -Wno-unused-parameter
            -Wold-style-cast
            -Woverloaded-virtual
            -Wpointer-arith
            -Wshadow
            -Wwrite-strings
            -march=native
            -rdynamic
)
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED on)
set(CMAKE_CXX_EXTENSIONS off)
set(CMAKE_CXX_FLAGS_DEBUG "-O0")
set(CMAKE_CXX_FLAGS_RELEASE "-O3 -DNDEBUG")

if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release)
endif()

find_package(Boost REQUIRED)
find_package(CURL)
find_library(BOOSTPO_LIBRARY NAMES boost_program_options)
find_library(BOOSTSYSTEM_LIBRARY NAMES boost_system)

if(CURL_FOUND)
    message(STATUS "found curl")
endif()

include_directories($ENV{LAVIEENBLUU_INCLUDE_PATH})
include_directories($ENV{ROBUST_INCLUDE_PATH})
link_directories($ENV{LAVIEENBLUU_LIB_PATH})
link_directories($ENV{ROBUST_LIB_PATH})

add_subdirectory(quoters)
