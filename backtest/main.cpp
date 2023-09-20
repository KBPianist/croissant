#include "backtest/quote_replayer.h"

#include <iostream>

int main(int argc, char** argv) {
    if (argc < 2) {
        std::cout << "usage backtest config_file" << std::endl;
        return -1;
    }

    nlohmann::json config = nlohmann::json::parse(argv[1]);

    robust::backtest::quote_replayer replayer;
    replayer.init(config);
    replayer.prepare();
	replayer.run(true);
}