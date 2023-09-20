#include "backtest/quote_replayer.h"
#include "platform/calendar.h"
#include "tools/logger.h"

using namespace robust::backtest;

quote_replayer::quote_replayer()
    : m_listener(nullptr),
      m_bt_loader(nullptr),
      m_min_period("d"),
      m_tick_enabled(true),
      m_tick_simulated(true),
      m_cur_date(0),
      m_cur_time(0),
      m_cur_secs(0),
      m_cur_tdate(0),
      m_closed_tdate(0),
      m_opened_tdate(0),
      m_begin_time(0),
      m_end_time(0),
      m_running(false) {
}

quote_replayer::~quote_replayer() {}

bool quote_replayer::init(const nlohmann::json& cfg, data_loader* loader) {
    m_bt_loader = loader;

    m_mode = cfg.at("mode").get<std::string>();
    m_base_dir = cfg.at("save_path").get<std::string>();
    m_begin_time = robust::calendar::instance().convert_exchange_time(cfg.at("begin_time").get<std::string>().c_str());
    m_end_time = robust::calendar::instance().convert_exchange_time(cfg.at("end_time").get<std::string>().c_str());

    LOGI << "backtest time range is set to [" << m_begin_time << ", " << m_end_time << "]";

    instrument_manager::instance().load(cfg.at("instrument_file").get<std::string>().c_str());

    load_fees(cfg.at("fees").get<std::string>().c_str());
    return true;
}