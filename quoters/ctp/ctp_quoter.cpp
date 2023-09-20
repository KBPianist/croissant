#include "ctp_quoter.h"
#include "platform/instrument_manager.h"
#include "definitions/variant.hpp"

#include <ranges>
#include <fmt/core.h>

using namespace robust;
using namespace lavieenbluu;

extern "C" {
__robust_ex quoter* create_quoter() {
	ctp_quoter *instance = new ctp_quoter();
	return instance;
}

__robust_ex void delete_quoter(quoter* &quoter) {
	if (nullptr != quoter) {
		delete quoter;
		quoter = nullptr;
	}
}
}

namespace details {
double inline correct_double(double d) {
    return (d == std::numeric_limits<double>::max()) ? std::numeric_limits<double>::quiet_NaN() : d;
}
}

bool ctp_quoter::load(const robust::variant* config) {
    m_broker_id = config->at("broker_id")->get_string();
    m_instruments = instrument_manager::instance().get_instruments(m_period_name.c_str());
    return quoter::load(config);
}

bool ctp_quoter::connect() {
    m_api = CThostFtdcMdApi::CreateFtdcMdApi("Md", true, true);
    m_api->RegisterSpi(this);
    std::string addr = fmt::format("tcp://{}:{}", m_addr.get_ip(), m_addr.get_port());
    m_api->RegisterFront(addr.data());
    m_api->Init();
    LOGI << get_name() << " init api done, addr:" << addr;
    return true;
}

void ctp_quoter::disconnect() {
    if (m_api != nullptr) {
        LOGI << get_name() << " release api";
        m_api->RegisterSpi(nullptr);
        m_api->Release();
        m_api = nullptr;
    }
    set_connected(false);
}

bool ctp_quoter::process() {
    return true;
}

void ctp_quoter::OnFrontConnected() {
    LOGI << get_name() << " front connected";
    set_connected(true);
    auto req = new CThostFtdcReqUserLoginField;
    strcpy(req->BrokerID, m_broker_id.c_str());
    strcpy(req->UserID, m_user.c_str());
    strcpy(req->Password, m_password.c_str());

    if (0 != m_api->ReqUserLogin(req, get_next_req_id())) {
        LOGE << get_name() << " request login failed";
    }
    else {
        LOGI << get_name() << " request login success";
    }
    delete req;
}

void ctp_quoter::OnFrontDisconnected(int Reason) {
    set_connected(false);
    LOGI << get_name() << " front disconnected";
}

void ctp_quoter::OnRspUserLogin(CThostFtdcRspUserLoginField *pRspUserLogin, CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast) {
    if (pRspInfo == nullptr || pRspInfo->ErrorID != 0) {
        LOGE << get_name() << " OnRspUserLogin rsp error id:" << pRspInfo->ErrorID << ", error msg:" << pRspInfo->ErrorMsg << ", request id:" << nRequestID;
    }
    else {
        LOGI << get_name() << " user login done, trading day:" << pRspUserLogin->TradingDay << ", user id:" << pRspUserLogin->UserID
             << ", session id:" << pRspUserLogin->SessionID << ", request id:" << nRequestID;
        subscribe();
    }
}

void ctp_quoter::OnRspError(CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast) {
    LOGE << get_name() << " OnRspError rsp error id:" << pRspInfo->ErrorID << ", error msg:" << pRspInfo->ErrorMsg << ", request id:" << nRequestID;
}

void ctp_quoter::OnHeartBeatWarning(int nTimeLapse) {
    LOGW << get_name() << " heart beat warning, time lapse:" << nTimeLapse;
}

void ctp_quoter::OnRspSubMarketData(CThostFtdcSpecificInstrumentField *pSpecificInstrument, CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast) {
    if (pRspInfo == nullptr || pRspInfo->ErrorID != 0 || pSpecificInstrument == nullptr) {
        LOGE << get_name() << " OnRspSubMarketData rsp error id:" << pRspInfo->ErrorID << ", error msg:" << pRspInfo->ErrorMsg << ", request id:" << nRequestID;
    }
    else {
        m_sub_count++;
        LOGI << get_name() << " OnRspSubMarketData rsp success, instrument_id:" << pSpecificInstrument->InstrumentID
             << ", request id:" << nRequestID << ", sub_count:" << m_sub_count;
        if (m_sub_count == instrument_manager::instance().get_instruments(m_period_name.c_str())->size()) {
            LOGI << get_name() << " subscribe done";
            set_ready(true);
        }
    }
}

void ctp_quoter::OnRtnDepthMarketData(CThostFtdcDepthMarketDataField *pDepthMarketData) {
    if (pDepthMarketData == nullptr) {
        LOGE << get_name() << " OnRtnDepthMarketData rsp error";
        return;
    }

    LOGD << get_name() << " OnRtnDepthMarketData rsp success, trading_day:" << pDepthMarketData->TradingDay
         << ", instrument_id:" << pDepthMarketData->InstrumentID << ", exchange_id:" << pDepthMarketData->ExchangeID
         << ", exchange_inst_id:" << pDepthMarketData->ExchangeInstID << ", last_price:" << details::correct_double(pDepthMarketData->LastPrice)
         << ", pre_settlement_price:" << details::correct_double(pDepthMarketData->PreSettlementPrice)
         << ", pre_close_price:" << details::correct_double(pDepthMarketData->PreClosePrice)
         << ", pre_open_interest:" << pDepthMarketData->PreOpenInterest << ", open_price:" << details::correct_double(pDepthMarketData->OpenPrice)
         << ", highest_price:" << details::correct_double(pDepthMarketData->HighestPrice)
         << ", lowest_price:" << details::correct_double(pDepthMarketData->LowestPrice)
         << ", volume:" << pDepthMarketData->Volume << ", turnover:" << details::correct_double(pDepthMarketData->Turnover)
         << ", open_interest:" << details::correct_double(pDepthMarketData->OpenInterest)
         << ", close_price:" << details::correct_double(pDepthMarketData->ClosePrice)
         << ", settlement_price:" << details::correct_double(pDepthMarketData->SettlementPrice)
         << ", upper_limit_price:" << details::correct_double(pDepthMarketData->UpperLimitPrice)
         << ", lower_limit_price:" << details::correct_double(pDepthMarketData->LowerLimitPrice)
         << ", update_time:" << pDepthMarketData->UpdateTime << ", update_millisec:" << pDepthMarketData->UpdateMillisec
         << ", bid_price1:" << details::correct_double(pDepthMarketData->BidPrice1) << ", bid_volume1:" << pDepthMarketData->BidVolume1
         << ", ask_price1:" << details::correct_double(pDepthMarketData->AskPrice1) << ", ask_volume1:" << pDepthMarketData->AskVolume1
         << ", bid_price2:" << details::correct_double(pDepthMarketData->BidPrice2) << ", bid_volume2:" << pDepthMarketData->BidVolume2
         << ", ask_price2:" << details::correct_double(pDepthMarketData->AskPrice2) << ", ask_volume2:" << pDepthMarketData->AskVolume2
         << ", bid_price3:" << details::correct_double(pDepthMarketData->BidPrice3) << ", bid_volume3:" << pDepthMarketData->BidVolume3
         << ", ask_price3:" << details::correct_double(pDepthMarketData->AskPrice3) << ", ask_volume3:" << pDepthMarketData->AskVolume3
         << ", bid_price4:" << details::correct_double(pDepthMarketData->BidPrice4) << ", bid_volume4:" << pDepthMarketData->BidVolume4
         << ", ask_price4:" << details::correct_double(pDepthMarketData->AskPrice4) << ", ask_volume4:" << pDepthMarketData->AskVolume4
         << ", bid_price5:" << details::correct_double(pDepthMarketData->BidPrice5) << ", bid_volume5:" << pDepthMarketData->BidVolume5
         << ", ask_price5:" << details::correct_double(pDepthMarketData->AskPrice5) << ", ask_volume5:" << pDepthMarketData->AskVolume5;

    auto p_type = std::strlen(pDepthMarketData->InstrumentID) > 6 ? instrument_type::type::OPTION : instrument_type::type::FUTURE;
    auto p_code = fmt::format("{}.{}", pDepthMarketData->InstrumentID, m_exchange_mapping[pDepthMarketData->InstrumentID]);
    std::optional<uint32_t> p_index = code_to_index(p_code.c_str(), p_type).value();
    if (p_index == std::nullopt) return;
    auto p_exchange_time = calendar::convert_exchange_time(pDepthMarketData->TradingDay,
                                                             pDepthMarketData->UpdateTime,
                                                             pDepthMarketData->UpdateMillisec);
    write<struct tick_data>([=](struct tick_data& p_data, uint64_t write_pos) -> void {
        p_data.m_seq = write_pos;
        std::strcpy(p_data.m_code.s, p_code.c_str());
        p_data.m_exchange = exchange::from_string(m_exchange_mapping[pDepthMarketData->InstrumentID].c_str());
        p_data.m_index = p_index.value();
        p_data.m_exchange_time = p_exchange_time.get_ticks();
        p_data.m_local_time = timestamp::now().get_ticks();

        p_data.m_last_price = details::correct_double(pDepthMarketData->LastPrice);
        p_data.m_low_price = details::correct_double(pDepthMarketData->LowestPrice);
        p_data.m_high_price = details::correct_double(pDepthMarketData->HighestPrice);
        p_data.m_turnover = details::correct_double(pDepthMarketData->Turnover);
        p_data.m_average_price = details::correct_double(pDepthMarketData->AveragePrice);
        p_data.m_open_interest = details::correct_double(pDepthMarketData->OpenInterest);
        p_data.m_volume = pDepthMarketData->Volume;
    });

    write<struct static_data>([=](struct static_data& p_data, uint64_t write_pos) -> void {
        p_data.m_seq = write_pos;
        std::strcpy(p_data.m_code.s, p_code.c_str());
        p_data.m_exchange = exchange::from_string(m_exchange_mapping[pDepthMarketData->InstrumentID].c_str());
        p_data.m_index = p_index.value();
        p_data.m_exchange_time = p_exchange_time.get_ticks();
        p_data.m_local_time = timestamp::now().get_ticks();

        p_data.m_close_price = details::correct_double(pDepthMarketData->ClosePrice);
        p_data.m_open_price = details::correct_double(pDepthMarketData->OpenPrice);
        p_data.m_up_limit = details::correct_double(pDepthMarketData->UpperLimitPrice);
        p_data.m_down_limit = details::correct_double(pDepthMarketData->LowerLimitPrice);
        p_data.m_pre_settle_price = details::correct_double(pDepthMarketData->PreSettlementPrice);
        p_data.m_pre_close_price = details::correct_double(pDepthMarketData->PreClosePrice);
    });
}

bool ctp_quoter::subscribe() {
    if (m_subscribe_all) {
        LOGE << get_name() << " subscribe all is not supported";
        return false;
    }
    else {
        for (auto & code : m_subscribe_codes) {
            auto slices = split(code, ".");
            m_exchange_mapping[slices[0]] = slices[1];
            m_subs[0] = const_cast<char*>(slices[0].data());
            LOGI << get_name() << " add code: " << m_subs[0];
            if (0 == m_api->SubscribeMarketData(m_subs, 1)) {
                LOGI << get_name() << " subscribe market data success";
            }
            else {
                LOGE << get_name() << " subscribe market data failed";
                return false;
            }
        }
        return true;
    }
}