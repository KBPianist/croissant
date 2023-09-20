//
// Created by jiahao.du on 2023/5/9.
//

#ifndef ROBUST_BACKTEST_DATA_TYPE_H
#define ROBUST_BACKTEST_DATA_TYPE_H

#include "definitions/types.h"

#include <cstring>
#include <cmath>
#include <vector>
#include <map>

namespace robust {
namespace backtest {
template <typename S, typename T>
class slice {
protected:
    code m_code{};
    int32_t m_count{0};
    std::vector<std::pair<T*, int32_t> > m_items;

public:
    static S* create(const char* code, T* items = nullptr, int32_t count = 0) {
        auto result = new S();
        std::strcpy(result->m_code, code);
        result->m_count = count;
        if (items != nullptr) result->m_items.emplace_back(items, count);
        return result;
    }

    bool append(T* bars, int32_t count) {
        if (count == 0 || bars == nullptr) return false;

        m_count += count;
        m_items.emplace_back(bars, count);
        return true;
    }

    T* at(int index) {
        if (m_count == 0 || std::abs(index) > m_count) return nullptr;

        int idx = index > 0 ? index : std::max(0, m_count + index);

        for (auto &bar: m_items) {
            if (idx >= bar.second) idx -= bar.second;
            else return bar.first + idx;
        }
        return nullptr;
    }

    int32_t total_size() const { return m_count; }

    bool is_empty() const { return m_count == 0; }
};

class kline_slice : public slice<kline_slice, struct bar_data> {
private:
    kline_interval::type m_interval;

private:
    kline_slice() : m_interval(kline_interval::MIN_1) {}

public:
    static kline_slice* create(const char* code, kline_interval::type interval, struct bar_data* bars = nullptr, int32_t count = 0) {
        auto result = new kline_slice();
        std::strcpy(result->m_code, code);
        result->m_count = count;
        if (bars != nullptr) result->m_items.emplace_back(bars, count);
        return result;
    }
};

class tick_slice : public slice<tick_slice, struct tick_data> {

};

struct order_detail_slice : public slice<order_detail_slice, struct order_detail_data> {

};

struct transaction_slice : public slice<transaction_slice, struct transaction_data> {

};
}
}

#endif//ROBUST_BACKTEST_DATA_TYPE_H
