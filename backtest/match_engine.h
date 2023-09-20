#ifndef BACKTEST_MATCH_ENGINE_H
#define BACKTEST_MATCH_ENGINE_H

#include "definitions/types.h"

#include <cstring>
#include <filesystem>
#include <functional>
#include <map>
#include <string>
#include <unordered_map>

namespace robust {
namespace backtest {
typedef std::vector<uint32_t> order_id_list;

typedef std::unordered_map<std::string, struct tick_data *> tick_map;

class match_sink {
public:
    virtual void handle_trade(uint32_t localid, const char *code, bool buy, double vol, double fireprice, double price, uint64_t time) = 0;
    virtual void handle_order(uint32_t localid, const char *code, bool buy, double leftover, double price, bool canceled, uint64_t time) = 0;
    virtual void handle_entrust(uint32_t localid, const char *code, bool success, const char *message, uint64_t time) = 0;
};

typedef std::function<void(double)> cancel_callback;

class match_engine {
public:
    match_engine() : m_sink(nullptr), m_cancel_rate(0), m_tick_cache(nullptr) {}

    void init(const std::filesystem::path &cfg_path);

    void register_sink(match_sink *sink) { m_sink = sink; }

    void clear();

    void handle_tick(const char *code, tick_data *tick);

    order_id_list buy(const char *code, double price, double qty, uint64_t time);
    order_id_list sell(const char *code, double price, double qty, uint64_t time);
    double cancel(uint32_t local_id);
    virtual order_id_list cancel(const char *code, bool is_buy, double qty, const cancel_callback &cb);

private:
    void delete_orders(const char *code);
    void match_orders(struct tick_data *tick, order_id_list &to_erase);
    void update_order_book(struct tick_data *tick);

    struct tick_data *grab_last_tick(const char *code);

private:
    struct order_info {
        char m_code[32];
        bool m_buy;
        double m_qty;
        double m_left;
        double m_traded;
        double m_limit;
        double m_price;
        uint32_t m_state;
        uint64_t m_time;
        double m_queue;
        bool m_positive;

        order_info() {
            std::memset(this, 0, sizeof(order_info));
        }
    };

    typedef std::unordered_map<uint32_t, order_info> orders;
    orders m_orders;

    typedef std::map<uint32_t, double> ob_item;

    struct order_book {
        ob_item m_items;
        uint32_t m_cur_px;
        uint32_t m_ask_px;
        uint32_t m_bid_px;

        void clear() {
            m_items.clear();
            m_cur_px = 0;
            m_ask_px = 0;
            m_bid_px = 0;
        }

        order_book() {
            m_cur_px = 0;
            m_ask_px = 0;
            m_bid_px = 0;
        }
    };
    typedef std::unordered_map<std::string, order_book> order_books;
    order_books m_order_books;

    match_sink *m_sink;

    double m_cancel_rate;
    tick_map *m_tick_cache;
};
}// namespace backtest
}// namespace robust
#endif