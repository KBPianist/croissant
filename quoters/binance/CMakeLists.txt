set(target binance)
project(${target})

set(${target}_src "binance_plugin.cpp" "binance_quoter.cpp")
add_library(${target} SHARED ${${target}_src})
target_link_libraries(${target} platform access Gyuyoung fmt pthread)
install(TARGETS ${target} 
        LIBRARY DESTINATION plugins
        ARCHIVE DESTINATION plugins)