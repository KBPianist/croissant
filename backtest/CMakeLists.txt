set(target backtest)
project(${target})

include_directories(${CMAKE_SOURCE_DIR}/include)

aux_source_directory(${CMAKE_CURRENT_SOURCE_DIR} ${target}_src)
add_executable(${target} ${${target}_src})
target_link_libraries(${ctp_impl} platform Gyuyoung fmt pthread)
install(TARGETS ${ctp_impl} RUNTIME DESTINATION bin)