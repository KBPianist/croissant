import akshare as ak
import numpy as np
import pandas as pd
import torch
import torch.nn as nn

print(torch.version.cuda)
print(torch.cuda.current_device())
print(torch.cuda.get_device_name(0))

def load_data(symbols, start='20200101', end='20250101'):
    data = {}
    for symbol in symbols:
        df = ak.stock_zh_a_hist(symbol, 'daily', start, end, 'hfq')
        df['return'] = df['收盘'].pct_change()  # 计算日收益率
        df = df[['return']].dropna()  # 只保留收益率
        data[symbol] = df
    return data


# 构造时间序列数据集
class TimeSeriesDataset(torch.utils.data.Dataset):
    def __init__(self, data, seq_len=20):
        self.data = data
        self.seq_len = seq_len
        self.assets = list(data.keys())

    def __len__(self):
        return len(next(iter(self.data.values()))) - self.seq_len

    def __getitem__(self, idx):
        x = []
        y = []
        for asset in self.assets:
            asset_data = self.data[asset]
            x.append(asset_data.iloc[idx:idx + self.seq_len].values)
            y.append(asset_data.iloc[idx + self.seq_len].values)

        # x: [N_assets, T, 1]
        x = pd.array(x)
        # y: [N_assets, 1]
        y = pd.array(y)
        return torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)


class TemporalEncoder(nn.Module):
    def __init__(self, n_factors, d_model=64):
        super().__init__()
        self.embed = nn.Linear(n_factors, d_model)
        layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=4, batch_first=True)
        self.encoder = nn.TransformerEncoder(layer, num_layers=2)

    def forward(self, x):
        # x: [B, T, F]
        x = self.embed(x)  # embedding [B, T, F] -> [B, T, D]
        x = self.encoder(x)  # self-attention
        return x[:, -1, :]  # 取最后时间步的输出


# 截面 Transformer 编码器
class CrossSectionEncoder(nn.Module):
    def __init__(self, d_model=64):
        super().__init__()
        layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=4, batch_first=True)
        self.encoder = nn.TransformerEncoder(layer, num_layers=2)
        self.fc = nn.Linear(d_model, 1)

    def forward(self, x):
        # x: [B, N_assets, D]
        x = self.encoder(x)  # self-attention across assets
        return self.fc(x).squeeze(-1)  # output alpha score for each asset


# 2D Attention 模型（时间 + 截面）
class SpatioTemporalTransformer(nn.Module):
    def __init__(self, n_assets, n_factors, d_model=64):
        super().__init__()
        self.temporal = TemporalEncoder(n_factors, d_model)
        self.cross = CrossSectionEncoder(d_model)

    def forward(self, x):
        # x: [B, N_assets, T, F]
        B, N, T, F = x.shape
        x = x.permute(0, 2, 1, 3)  # [B, T, N, F] -> [B, N, T, F]
        x = x.reshape(B * N, T, F)  # [B*N, T, F]

        h = self.temporal(x)  # [B*N, D]
        h = h.view(B, N, -1)  # [B, N, D]

        score = self.cross(h)  # [B, N]
        return score

def ic_loss(pred, target):
    pred = pred - pred.mean(dim=1, keepdim=True)
    target = target - target.mean(dim=1, keepdim=True)
    cov = (pred * target).mean(dim=1)
    std = pred.std(dim=1) * target.std(dim=1)
    ic = cov / (std + 1e-8)
    return -ic.mean()  # 返回负的 IC（优化目标是最大化 IC）

def train(model, train_loader, epochs=10):
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)

    for epoch in range(epochs):
        total_loss = 0
        for x, y in train_loader:
            optimizer.zero_grad()
            pred = model(x)  # 预测 alpha 排名
            loss = ic_loss(pred, y)  # 使用 IC loss
            loss.backward()
            optimizer.step()
            total_loss += loss.item()

        print(f"Epoch {epoch + 1}, Loss: {total_loss / len(train_loader)}")

def backtest(model, dataset):
    model.eval()
    pnl = 0.0

    with torch.no_grad():
        for i in range(len(dataset)):
            x, y = dataset[i]
            x = x.unsqueeze(0)  # [1, N_assets, T, F]
            pred = model(x).squeeze(0).numpy()  # [N_assets]

            # 根据预测的 alpha 排名进行多空
            signal = np.argsort(pred)  # 排名从小到大
            # 做多前五，空仓后五
            pnl += np.sum(np.sign(signal[:5]) * y.numpy()[signal[:5]])

    return pnl

if __name__ == "__main__":
    # 1. 获取数据
    symbols = ['000001', '601512', '600187', '603499', '605178']
    data = load_data(symbols)

    # 2. 准备数据集
    dataset = TimeSeriesDataset(data)
    train_loader = torch.utils.data.DataLoader(dataset, batch_size=32, shuffle=True)

    # 3. 初始化模型
    model = SpatioTemporalTransformer(n_assets=len(symbols), n_factors=1)  # 这里只用日收益率作为因子
    train(model, train_loader, epochs=10)

    # 4. 回测
    pnl = backtest(model, dataset)
    print(f"Total PnL: {pnl}")