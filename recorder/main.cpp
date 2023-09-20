#include "access/quote_reader.h"
#include "tools/logger.h"

using namespace robust;

int main(int argc, char **argv) {
    auto reader = new quote_reader("ctp_test", "test");
    reader->initialize();
    reader->set_quote_callback([](uint8_t type, int64_t ts, const char *data){
        if (type == quote_type::type::TICK) {
            auto p_data = const_cast<char*>(data);
            auto p_tick = reinterpret_cast<struct tick_data*>(p_data);
            LOGI << "on_tick seq:" << p_tick->m_seq << ", code:" << p_tick->m_code
                 << ", exchange:" << p_tick->m_exchange << ", index:" << p_tick->m_index
                 << ", exchange_time:" << p_tick->m_exchange_time << ", local_time:" << p_tick->m_local_time
                 << ", volume:" << p_tick->m_volume << ", turnover:" << p_tick->m_turnover
                 << ", open_interest:" << p_tick->m_open_interest << ", last_price:" << p_tick->m_last_price
                 << ", last_volume:" << p_tick->m_last_volume << ", high_price:" << p_tick->m_high_price
                 << ", low_price:" << p_tick->m_low_price << ", average_price:" << p_tick->m_average_price
                 << ", bid_price1:" << p_tick->m_bid_prices[0] << ", bid_volume1:" << p_tick->m_bid_volumes[0]
                 << ", ask_price1:" << p_tick->m_ask_prices[0] << ", ask_volume1:" << p_tick->m_ask_volumes[0]
                 << ", bid_price2:" << p_tick->m_bid_prices[1] << ", bid_volume2:" << p_tick->m_bid_volumes[1]
                 << ", ask_price2:" << p_tick->m_ask_prices[1] << ", ask_volume2:" << p_tick->m_ask_volumes[1]
                 << ", bid_price3:" << p_tick->m_bid_prices[2] << ", bid_volume3:" << p_tick->m_bid_volumes[2]
                 << ", ask_price3:" << p_tick->m_ask_prices[2] << ", ask_volume3:" << p_tick->m_ask_volumes[2]
                 << ", bid_price4:" << p_tick->m_bid_prices[3] << ", bid_volume4:" << p_tick->m_bid_volumes[3]
                 << ", ask_price4:" << p_tick->m_ask_prices[3] << ", ask_volume4:" << p_tick->m_ask_volumes[3]
                 << ", bid_price5:" << p_tick->m_bid_prices[4] << ", bid_volume5:" << p_tick->m_bid_volumes[4]
                 << ", ask_price5:" << p_tick->m_ask_prices[4] << ", ask_volume5:" << p_tick->m_ask_volumes[4];
        }
        else if (type == quote_type::type::STATIC) {
            auto p_data = const_cast<char*>(data);
            auto p_static = reinterpret_cast<struct static_data*>(p_data);
            LOGI << "on_static seq:" << p_static->m_seq << ", code:" << p_static->m_code
                 << ", exchange:" << p_static->m_exchange << ", index:" << p_static->m_index
                 << ", exchange_time:" << p_static->m_exchange_time << ", local_time:" << p_static->m_local_time
                 << ", up_limit:" << p_static->m_up_limit << ", down_limit:" << p_static->m_down_limit
                 << ", close_price:" << p_static->m_close_price << ", open_price:" << p_static->m_open_price
                 << ", settle_price:" << p_static->m_settle_price << ", pre_close_price:" << p_static->m_pre_close_price
                 << ", pre_settle_price:" << p_static->m_pre_settle_price;
        }
    });

    while (true) {
        reader->on_quote_received();
    }
    return 0;
}