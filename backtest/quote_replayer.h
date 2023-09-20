#ifndef ROBUST_BACKTEST_QUOTE_REPLAYER_H
#define ROBUST_BACKTEST_QUOTE_REPLAYER_H

#include "3rd/json.hpp"
#include "backtest/data_type.h"
#include "backtest/history_data_manager.h"
#include "definitions/types.h"
#include "platform/instrument_manager.h"

#include <functional>
#include <map>
#include <memory>
#include <set>
#include <string>
#include <unordered_map>
#include <vector>

namespace robust {
namespace backtest {
class data_sink {
public:
    virtual void handle_tick(const char *code, tick_data *tick, uint32_t pxType) = 0;
    virtual void handle_order_detail(const char *code, order_detail_data *order){};
    virtual void handle_transaction(const char *code, transaction_data *trade){};
    virtual void handle_bar_close(const char *code, const char *period, uint32_t time, bar_data *bar) = 0;
    virtual void handle_schedule(uint32_t date, uint32_t time) = 0;

    virtual void handle_init() = 0;
    virtual void handle_session_begin(uint32_t date) = 0;
    virtual void handle_session_end(uint32_t date) = 0;
    virtual void handle_replay_done() {}
    virtual void handle_section_end(uint32_t date, uint32_t time) {}
};

using read_bars_callback = std::function<void>(void *obj, bar_data *first_bar, uint32_t count);
using read_factors_callback = std::function<void>(void *obj, const char *code, uint32_t *dates, double *factors, uint32_t count);
using read_ticks_callback = std::function<void>(void *obj, tick_data *first_tick, uint32_t count);

class data_loader {
public:
	virtual bool load_final_history_bars(void *obj, const char *code, kline_interval interval, read_bars_callback cb) = 0;
    virtual bool load_raw_history_bars(void *obj, const char *code, kline_interval interval, read_bars_callback cb) = 0;
    virtual bool load_all_factors(void *obj, read_factors_callback cb) = 0;
    virtual bool load_factor(void *obj, const char *code, read_factors_callback cb) = 0;
    virtual bool load_raw_history_tick(void *obj, const char *code, uint32_t date, read_ticks_callback cb) = 0;
    virtual bool is_auto_trans() { return true; }
};

class quote_replayer {
private:
    template<typename T>
    class data_list {
    public:
        std::string m_code;
        uint32_t m_date;
        std::size_t m_cursor;
        std::size_t m_count;

        std::vector<T> m_items;

        data_list() : m_cursor(UINT64_MAX), m_count(0), m_date(0) {}
    };

    typedef std::unordered_map<std::string, data_list<tick_data>> tick_map;
    typedef std::unordered_map<std::string, data_list<order_detail_data>> order_map;
    typedef std::unordered_map<std::string, data_list<transaction_data>> trade_map;

    struct bars_list {
        std::string m_code;
        kline_interval m_interval;
        uint32_t m_cursor;
        uint32_t m_count;
        uint32_t m_times;
        double m_factor;
        std::vector<bar_data> m_bars;

        bars_list() : m_cursor(UINT32_MAX), m_count(0), m_times(1), m_factor(1) {}
    };

    typedef std::shared_ptr<bars_list> bars_list_ptr;
    typedef std::unordered_map<std::string, bars_list_ptr> bars_map;

    enum task_interval {
        TPT_UNREPEAT,
        TPT_MINUTE = 4,
        TPT_DAILY = 8,
        TPT_WEEKLY,
        TPT_MONTHLY,
        TPT_YEARLY
    };

    struct task_info {
        uint32_t m_id;
        std::string m_name;
        char m_trade_template[16];
        char m_session[16];
        uint32_t m_date;
        uint32_t m_time;
        bool m_strict_time;
        uint64_t m_last_exec_time;
        task_interval m_period;
    };

    typedef std::shared_ptr<task_info> task_info_ptr;

public:
    quote_replayer();
    ~quote_replayer();

public:
    bool init(const nlohmann::json &cfg, data_loader *loader = nullptr);

    bool prepare();

    void run(bool dump = false);

    void stop();

    void clear_cache();

    inline void set_time_range(uint64_t start_time, uint64_t end_time) {
        m_begin_time = start_time;
        m_end_time = end_time;
    }

    inline void enable_tick(bool enabled = true) {
        m_tick_enabled = enabled;
    }

    inline void register_sink(data_sink *sink, const char *sink_name) {
        m_sink = sink;
        m_strategy_name = sink_name;
    }

    void register_task(uint32_t taskid, uint32_t date, uint32_t time);

    kline_slice *get_kline_slice(const char *code, const char *period, uint32_t count, uint32_t times = 1, bool is_main = false);
    tick_slice *get_tick_slice(const char *code, uint32_t count, uint64_t end_time = 0);
    order_detail_slice *get_order_detail_slice(const char *code, uint32_t count, uint64_t end_time = 0);
    transaction_slice *get_transaction_slice(const char *code, uint32_t count, uint64_t end_time = 0);
    tick_data *get_last_tick(const char *code);
    instrument_info *get_commodity_info(const char *code);
    double get_cur_price(const char *code);
    double get_day_price(const char *code, int flag = 0);
    std::string get_rawcode(const char *code);
    uint32_t get_date() const { return m_cur_date; }
    uint32_t get_min_time() const { return m_cur_time; }
    uint32_t get_raw_time() const { return m_cur_time; }
    uint32_t get_secs() const { return m_cur_secs; }
    uint32_t get_trading_date() const { return m_cur_tdate; }

    double calculate_fee(const char *code, double price, double qty, uint32_t offset);

    void sub_tick(uint32_t sid, const char *code);
    void sub_order_queue(uint32_t sid, const char *code);
    void sub_order_detail(uint32_t sid, const char *code);
    void sub_transaction(uint32_t sid, const char *code);

    inline bool is_tick_enabled() const { return m_tick_enabled; }

    inline bool is_tick_simulated() const { return m_tick_simulated; }

    inline void update_price(const char *code, double price) { m_price_map[code] = price; }

private:
    bool load_raw_bars_from_csv(const std::string &key, const char *code, kline_interval interval, bool subbed = true);
    bool load_raw_ticks_from_csv(const std::string &key, const char *code, uint32_t date);
	bool load_raw_ticks_from_loader(const std::string &key, const char *code, kline_interval interval, bool subbed = true);
    bool load_raw_ticks_from_loader(const std::string &key, const char *code, uint32_t date);
    void load_fees(const char *file_name);
	void load_stock_factors(const char *file_name);

    void on_minute_end(uint32_t date, uint32_t time, uint32_t end_date = 0, bool tick_simulated = true);

    bool replay_data(uint64_t start_time, uint64_t end_time);
    uint64_t replay_data(uint32_t date);

    void simulate_tick_with_unsub_bars(uint64_t start_time, uint64_t end_time, uint32_t end_date = 0, int pxType = 0);
    void simulate_ticks(uint32_t date, uint32_t time, uint32_t end_date = 0, int pxType = 0);

    bool check_ticks(const char *code, uint32_t date);
    bool check_order_details(const char *code, uint32_t date);
    bool check_trasactions(const char *code, uint32_t date);
    void check_unsub_bars();
    bool check_all_ticks(uint32_t date);

    uint64_t next_tick_time(uint32_t date, uint64_t time = UINT64_MAX);
    uint64_t next_order_detail_time(uint32_t date, uint64_t time = UINT64_MAX);
    uint64_t next_transaction_time(uint32_t date, uint64_t time = UINT64_MAX);

    void reset();
    void dump_bt_state(const char *code, kline_interval interval, uint32_t time, uint64_t start_time, uint64_t end_time, double progress, int64_t elapse);
    void notify_state(const char *code, kline_interval interval, uint32_t time, uint64_t start_time, uint64_t end_time, double progress);
    uint32_t locate_bar_index(const std::string &key, uint64_t curTime, bool upper_bound = false);

    void run_by_bars(bool dump = false);
    void run_by_tasks(bool dump = false);
    void run_by_ticks(bool dump = false);

private:
    data_sink *m_sink;
    data_loader *m_bt_loader;
    std::string m_strategy_name;

    tick_map m_ticks_cache;
    order_map m_order_detail_cache;
    trade_map m_trans_cache;
    bars_map m_bars_cache;
    bars_map m_unbars_cache;

    task_info_ptr m_task;

    std::string m_main_key;
    std::string m_min_period;
    std::string m_main_period;
    bool m_tick_enabled;
    bool m_tick_simulated;
    std::map<std::string, tick_data> m_day_cache;
    std::map<std::string, std::string> m_ticker_keys;

    std::set<std::string> m_unsubbed_in_need;

    uint32_t m_cur_date;
    uint32_t m_cur_time;
    uint32_t m_cur_secs;
    uint32_t m_cur_tdate;
    uint32_t m_closed_tdate;
    uint32_t m_opened_tdate;

    history_data_manager m_history_data_manager;

    std::string m_base_dir;
    std::string m_mode;
    uint64_t m_begin_time;
    uint64_t m_end_time;

    bool m_running;
    bool m_terminated;

    struct fee {
        double m_open{0};
        double m_close{0};
        double m_close_today{0};
        bool m_by_volume{false};
    };
    typedef std::unordered_map<std::string, struct fee> fee_map;
    fee_map m_fee_map;

    typedef std::unordered_map<std::string, double> price_map;
    price_map m_price_map;

    typedef std::pair<uint32_t, uint32_t> sub_option;
    typedef std::unordered_map<uint32_t, sub_option> sub_list;
    typedef std::unordered_map<std::string, sub_list> sub_map;
    sub_map m_tick_sub_map;
    sub_map m_order_sub_map;
    sub_map m_trade_sub_map;
};
}// namespace backtest
}// namespace robust

#endif