#include "backtest/history_data_manager.h"

using namespace robust;
using namespace robust::backtest;

bool history_data_manager::init(const nlohmann::json& json) {
    
}

bool history_data_manager::load_bars(const char* code, exchange::type exchange, kline_interval::type interval, callback cb) {

}

bool history_data_manager::load_ticks(const char* code, exchange::type exchange, uint32_t date, callback cb) {

}