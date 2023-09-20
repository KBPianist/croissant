#ifndef ROBUST_QUOTERS_CTP_QUOTER_H
#define ROBUST_QUOTERS_CTP_QUOTER_H

#include "access/quoter.h"
#include "libs/ctp/ThostFtdcMdApi.h"

class ctp_quoter : public robust::quoter, public CThostFtdcMdSpi {
public:
    bool connect() override;
    void disconnect() override;
    bool process() override;
    bool load(const robust::variant* config) override;

protected:
    bool subscribe() override;

private:
    void OnFrontConnected() override;
    void OnFrontDisconnected(int Reason) override;
    void OnRspUserLogin(CThostFtdcRspUserLoginField *pRspUserLogin, CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast) override;
    void OnRspError(CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast) override;
    void OnHeartBeatWarning(int nTimeLapse) override;
    void OnRspSubMarketData(CThostFtdcSpecificInstrumentField *pSpecificInstrument, CThostFtdcRspInfoField *pRspInfo, int nRequestID, bool bIsLast) override;
    void OnRtnDepthMarketData(CThostFtdcDepthMarketDataField *pDepthMarketData) override;

private:
    CThostFtdcMdApi *m_api;
    std::string m_broker_id;
    uint32_t m_sub_count;
    char* m_subs[100];
    std::unordered_map<std::string, std::string> m_exchange_mapping;
};

#endif