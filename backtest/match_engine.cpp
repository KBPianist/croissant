#include "backtest/match_engine.h"
#include "3rd/json.hpp"
#include "platform/decimal.h"
#include "tools/logger.h"
#include "tools/timestamp.h"

#include <fstream>

using namespace robust;
using namespace robust::backtest;

extern uint32_t make_local_order_id();

void match_engine::init(const std::filesystem::path &cfg_path) {
    std::ifstream conf_stream(cfg_path.filename(), std::ios::in);
    if (!conf_stream.is_open()) {
        std::printf("open configure file:%s failed!", cfg_path.c_str());
        return;
    }
    nlohmann::json conf = nlohmann::json::parse(conf_stream);

    m_cancel_rate = conf.at("cancel_rate").get<double>();
    conf_stream.close();
}

void match_engine::clear() {
    m_orders.clear();
}

void match_engine::delete_orders(const char *code) {
    for (auto &v: m_orders) {
        uint32_t local_id = v.first;
        order_info &info = v.second;

        if (info.m_state == 0) {
            m_sink->handle_entrust(local_id, code, true, "", info.m_time);
            m_sink->handle_order(local_id, code, info.m_buy, info.m_left, info.m_limit, false, info.m_time);
            info.m_state = 1;
        }
    }
}

void match_engine::match_orders(struct tick_data *tick, order_id_list &to_erase) {
    for (auto &v: m_orders) {
        uint32_t local_id = v.first;
        auto &info = (order_info &) v.second;

        if (info.m_state == 9) {
            m_sink->handle_order(local_id, info.m_code, info.m_buy, 0, info.m_limit, true, info.m_time);
            info.m_state = 99;

            to_erase.emplace_back(local_id);

            LOGI << "local order id:" << local_id << " was canceled, left:" << info.m_left * (info.m_buy ? 1 : -1);
            info.m_left = 0;
            continue;
        }

        if (info.m_state != 1 || tick->m_volume == 0)
            continue;

        if (info.m_buy) {
            double price;
            double volume;

            if (info.m_positive) {
                price = tick->m_ask_prices[0];
                volume = tick->m_ask_volumes[0];
            }
            else {
                price = tick->m_last_price;
                volume = tick->m_last_volume;
            }

            if (decimal::less_than(price, info.m_limit)) {
                if (!info.m_positive && decimal::equal(price, info.m_limit)) {
                    double &quepos = info.m_queue;

                    if (volume <= quepos) {
                        quepos -= volume;
                        continue;
                    }
                    else if (quepos != 0) {
                        volume -= quepos;
                        quepos = 0;
                    }
                }
                else if (!info.m_positive) {
                    volume = info.m_left;
                }

                double qty = std::min(volume, info.m_left);
                if (decimal::equal(qty, 0.0))
                    qty = 1;

                m_sink->handle_trade(local_id, info.m_code, info.m_buy, qty, info.m_price, price, info.m_time);

                info.m_traded += qty;
                info.m_left -= qty;

                m_sink->handle_order(local_id, info.m_code, info.m_buy, info.m_left, price, false, info.m_time);

                if (info.m_left == 0)
                    to_erase.emplace_back(local_id);
            }
        }

        if (!info.m_buy) {
            double price;
            double volume;

            if (info.m_positive) {
                price = tick->m_bid_prices[0];
                volume = tick->m_bid_volumes[0];
            }
            else {
                price = tick->m_last_price;
                volume = tick->m_last_volume;
            }

            if (decimal::grate_equal(price, info.m_limit)) {
                if (!info.m_positive && decimal::equal(price, info.m_limit)) {
                    double &quepos = info.m_queue;

                    if (volume <= quepos) {
                        quepos -= volume;
                        continue;
                    }
                    else if (quepos != 0) {
                        volume -= quepos;
                        quepos = 0;
                    }
                }
                else if (!info.m_positive) {
                    volume = info.m_left;
                }

                double qty = std::min(volume, info.m_left);
                if (decimal::equal(qty, 0.0))
                    qty = 1;

                m_sink->handle_trade(local_id, info.m_code, info.m_buy, qty, info.m_price, price, info.m_time);
                info.m_traded += qty;
                info.m_left -= qty;

                m_sink->handle_order(local_id, info.m_code, info.m_buy, info.m_left, price, false, info.m_time);

                if (info.m_left == 0)
                    to_erase.emplace_back(local_id);
            }
        }
    }
}

void match_engine::update_order_book(struct tick_data *tick) {
    order_book &cur_book = m_order_books[tick->m_code];
    cur_book.m_cur_px = std::lround(tick->m_last_price);
    cur_book.m_ask_px = std::lround(tick->m_ask_prices[0]);
    cur_book.m_bid_px = std::lround(tick->m_bid_prices[0]);

    for (uint32_t i = 0; i < 5; i++) {
        if (std::lround(tick->m_ask_prices[i]) == 0 && std::lround(tick->m_bid_prices[i]) == 0)
            break;

        uint32_t px = std::lround(tick->m_ask_prices[i]);
        if (px != 0) {
            double &volume = cur_book.m_items[px];
            volume = tick->m_ask_volumes[i];
        }

        px = std::lround(tick->m_bid_prices[i]);
        if (px != 0) {
            double &volume = cur_book.m_items[px];
            volume = tick->m_ask_volumes[i];
        }
    }

    if (!cur_book.m_items.empty()) {
        auto sit = cur_book.m_items.lower_bound(cur_book.m_bid_px);
        if (sit->first == cur_book.m_bid_px)
            sit++;

        auto eit = cur_book.m_items.lower_bound(cur_book.m_ask_px);

        if (sit->first <= eit->first)
            cur_book.m_items.erase(sit, eit);
    }
}


order_id_list match_engine::buy(const char *code, double price, double qty, uint64_t time) {
    tick_data *last_tick = grab_last_tick(code);
    if (last_tick == nullptr)
        return {};

    uint32_t local_id = make_local_order_id();
    order_info &info = m_orders[local_id];
    strcpy(info.m_code, code);
    info.m_buy = true;
    info.m_limit = price;
    info.m_qty = qty;
    info.m_left = qty;
    info.m_price = last_tick->m_last_price;

    if (decimal::grate_equal(price, last_tick->m_ask_prices[0]))
        info.m_positive = true;
    else if (decimal::equal(price, last_tick->m_bid_prices[0]))
        info.m_queue = last_tick->m_bid_volumes[0];
    if (decimal::equal(price, last_tick->m_last_price))
        info.m_queue = (uint32_t) decimal::round(
                (last_tick->m_ask_volumes[0] * last_tick->m_ask_prices[0] + last_tick->m_bid_volumes[0] * last_tick->m_bid_prices[0]) / (last_tick->m_ask_prices[0] + last_tick->m_bid_prices[0]));

    info.m_queue -= (uint32_t) decimal::round(info.m_queue * m_cancel_rate);
    info.m_time = time;

    delete last_tick;

    order_id_list ret;
    ret.emplace_back(local_id);
    return ret;
}

order_id_list match_engine::sell(const char *code, double price, double qty, uint64_t time) {
    tick_data *last_tick = grab_last_tick(code);
    if (last_tick == nullptr)
        return {};

    uint32_t local_id = make_local_order_id();
    order_info &info = m_orders[local_id];
    strcpy(info.m_code, code);
    info.m_buy = false;
    info.m_limit = price;
    info.m_qty = qty;
    info.m_left = qty;
    info.m_price = last_tick->m_last_price;

    if (decimal::equal(price, last_tick->m_ask_prices[0]))
        info.m_queue = last_tick->m_ask_volumes[0];
    else if (decimal::less_equal(price, last_tick->m_bid_prices[0]))
        info.m_positive = true;
    if (decimal::equal(price, last_tick->m_last_price))
        info.m_queue = (uint32_t) decimal::round(
                (last_tick->m_ask_volumes[0] * last_tick->m_ask_prices[0] + last_tick->m_bid_volumes[0] * last_tick->m_bid_prices[0]) / (last_tick->m_ask_prices[0] + last_tick->m_bid_prices[0]));

    info.m_queue -= (uint32_t) decimal::round(info.m_queue * m_cancel_rate);
    info.m_time = time;

    delete last_tick;

    order_id_list ret;
    ret.emplace_back(local_id);
    return ret;
}

order_id_list match_engine::cancel(const char *code, bool is_buy, double qty, const cancel_callback &cb) {
    order_id_list ret;
    for (auto &v: m_orders) {
        auto &info = (order_info &) v.second;
        if (info.m_state != 1)
            continue;

        double left = qty;
        if (info.m_buy == is_buy) {
            uint32_t local_id = v.first;
            ret.emplace_back(local_id);
            info.m_state = 9;
            cb(info.m_left * (info.m_buy ? 1 : -1));

            if (qty != 0) {
                if ((int32_t) left <= info.m_left)
                    break;

                left -= info.m_left;
            }
        }
    }

    return ret;
}

double match_engine::cancel(uint32_t local_id) {
    auto it = m_orders.find(local_id);
    if (it == m_orders.end())
        return 0.0;

    auto &info = (order_info &) it->second;
    info.m_state = 9;

    return info.m_left * (info.m_buy ? 1 : -1);
}

void match_engine::handle_tick(const char *code, struct tick_data *tick) {
    if (nullptr == tick)
        return;

    if (nullptr == m_tick_cache)
        m_tick_cache = new tick_map();

    m_tick_cache->insert({code, tick});

    update_order_book(tick);

    delete_orders(code);

    order_id_list to_erase;
    match_orders(tick, to_erase);

    for (uint32_t localid: to_erase) {
        auto it = m_orders.find(localid);
        if (it != m_orders.end())
            m_orders.erase(it);
    }
}

struct tick_data *match_engine::grab_last_tick(const char *code) {
    if (nullptr == m_tick_cache)
        return nullptr;

    auto it = m_tick_cache->find(code);
    if (it == m_tick_cache->end()) return nullptr;
    return it->second;
}