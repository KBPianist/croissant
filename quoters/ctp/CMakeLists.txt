set(target ctp_quoter)
project(${target})

include_directories(${CMAKE_SOURCE_DIR})

set(${target}_src "ctp_quoter.cpp")
add_library(${target} SHARED ${${target}_src})
target_link_libraries(${target} platform access Gyuyoung fmt pthread)
target_link_libraries(${target} ${libs_src}/ctp/libthostmduserapi_se_6315.so)
install(TARGETS ${target} 
        LIBRARY DESTINATION plugins
        ARCHIVE DESTINATION plugins)