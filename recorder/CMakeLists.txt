set(target recorder)
project(${target})

include_directories(${CMAKE_SOURCE_DIR}/include)
include_directories(${CMAKE_SOURCE_DIR}/lavieenbluu/include)
include_directories(${CMAKE_SOURCE_DIR}/lavieenbluu)

aux_source_directory(${CMAKE_CURRENT_SOURCE_DIR} ${target}_src)
add_executable(${target} ${${target}_src})
target_link_libraries(${target} platform access Gyuyoung fmt pthread)
install(TARGETS ${target} RUNTIME DESTINATION bin)