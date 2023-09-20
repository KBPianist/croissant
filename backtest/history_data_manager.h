#ifndef BACKTEST_HISTORY_DATA_MANAGER_H
#define BACKTEST_HISTORY_DATA_MANAGER_H

#include "3rd/json.hpp"
#include "definitions/enums.h"

namespace lavieenbluu::net {
class buffer;
}

namespace robust {
namespace backtest {
using callback = std::function<void(lavieenbluu::net::buffer*)>;
class history_data_manager {
public:
    bool init(const nlohmann::json& json);

    bool load_bars(const char* code, exchange::type exchange, kline_interval::type interval, callback cb);

    bool load_ticks(const char* code, exchange::type exchange, uint32_t date, callback cb);
};
}
}

#endif