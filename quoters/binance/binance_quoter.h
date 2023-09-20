#ifndef ROBUST_QUOTERS_BINANCE_QUOTER_H
#define ROBUST_QUOTERS_BINANCE_QUOTER_H

#include "access/quoter.h"

class binance_quoter : public robust::quoter {
public:
    bool connect() override { return true; }
    void disconnect() override {}
    bool process() override { return true; }
    bool subscribe() override { return true; }
};

#endif