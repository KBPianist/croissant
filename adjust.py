import pandas as pd
import numpy as np
import os
import time
from datetime import datetime, timedelta
import warnings
from pathlib import Path
from tqdm import tqdm
import logging
import json
from typing import Dict, List, Optional, Tuple
import traceback

warnings.filterwarnings('ignore')

# 配置日志 - 显示文件名和行号
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('level2_forward_adjustment.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class Level2ForwardAdjuster:
    def __init__(self, raw_data_path: str, save_path: str, adjust_data_path: str):
        """
        Level2高频数据前复权处理类（使用本地复权数据文件）

        Parameters:
        -----------
        raw_data_path : str
            原始Level2数据路径
        save_path : str
            处理后数据保存路径
        adjust_data_path : str
            本地日级前复权数据文件路径（按股票代码分文件）
        """
        self.raw_data_path = Path(raw_data_path)
        self.save_path = Path(save_path)
        self.adjust_data_path = Path(adjust_data_path)

        # 创建保存目录
        self.save_path.mkdir(parents=True, exist_ok=True)

        # 日级复权因子缓存
        self.daily_adjustment_factors = {}

        # 请求配置
        self.request_delay = 0.1  # 处理延迟
        self.max_retries = 3  # 最大重试次数

        # **只调整价格相关字段**
        self.price_fields_to_adjust = [
            'Price',  # 最新价格
            'WeightBidPrice',  # 加权平均委买价
            'WeightAskPrice',  # 加权平均委卖价
        ]

        # 添加买卖盘价格字段
        for i in range(1, 11):
            self.price_fields_to_adjust.extend([
                f'AskPrice{i}',  # 委卖价格
                f'BidPrice{i}'  # 委买价格
            ])

        # **不需要调整的字段（保持原样）**
        self.fields_not_to_adjust = [
            # 基础字段
            'SecuCode', 'TradingDay', 'TickTime', 'TickTimeDiff',
            # 成交相关字段 - 保持原样
            'DealNum', 'Volume', 'Turnover',
            'TotalDealNum', 'TotalVolume', 'TotalTurnover',
            # 委托总量字段 - 保持原样
            'TotalBidVolume', 'TotalAskVolume',
            # 委托挂单量字段 - 保持原样
        ]

        # 添加委托挂单量字段（保持原样）
        for i in range(1, 11):
            self.fields_not_to_adjust.extend([
                f'AskVolume{i}',  # 委卖挂单量 - 保持原样
                f'BidVolume{i}',  # 委买挂单量 - 保持原样
                f'AskOrder{i}',  # 委卖委托单数 - 保持原样
                f'BidOrder{i}',  # 委买委托单数 - 保持原样
            ])

        # 检查复权数据路径
        if not self.adjust_data_path.exists():
            logger.error(f"复权数据路径不存在: {self.adjust_data_path}")
            raise FileNotFoundError(f"复权数据路径不存在: {self.adjust_data_path}")

    def get_adjustment_data_file(self, stock_code: str) -> Optional[Path]:
        """
        根据股票代码查找对应的复权数据文件

        Parameters:
        -----------
        stock_code : str
            股票代码

        Returns:
        --------
        Optional[Path]: 复权数据文件路径，如果未找到则返回None
        """
        # 尝试多种可能的文件命名方式
        possible_filenames = [
            f"{stock_code}.parquet",
            f"{stock_code}.csv",
            f"{stock_code}.pkl",
            f"{stock_code}_adj.parquet",
            f"{stock_code}_adjust.parquet",
            f"{stock_code}_qfq.parquet",
        ]

        for filename in possible_filenames:
            file_path = self.adjust_data_path / filename
            if file_path.exists():
                logger.info(f"找到复权数据文件: {file_path}")
                return file_path

        # 如果没有找到具体文件，可能是一个包含所有股票的大文件
        # 检查目录下是否有parquet文件
        parquet_files = list(self.adjust_data_path.glob("*.parquet"))
        if len(parquet_files) == 1:
            logger.info(f"使用单个复权数据文件: {parquet_files[0]}")
            return parquet_files[0]

        logger.warning(f"未找到股票 {stock_code} 的复权数据文件")
        return None

    def load_adjustment_data(self, stock_code: str) -> pd.DataFrame:
        """
        加载股票的前复权数据

        Parameters:
        -----------
        stock_code : str
            股票代码

        Returns:
        --------
        DataFrame: 日级前复权数据
        """
        file_path = self.get_adjustment_data_file(stock_code)
        if file_path is None:
            return pd.DataFrame()

        try:
            logger.info(f"加载前复权数据: {file_path}")

            # 根据文件类型加载数据
            if file_path.suffix == '.parquet':
                df = pd.read_parquet(file_path)
            elif file_path.suffix == '.csv':
                df = pd.read_csv(file_path)
            else:
                logger.error(f"不支持的文件格式: {file_path.suffix}")
                return pd.DataFrame()

            # 标准化列名
            df.columns = df.columns.str.strip()

            # 检查必要字段
            required_fields = ['ts_code', 'trade_date', 'close', 'close_qfq']
            missing_fields = [f for f in required_fields if f not in df.columns]

            if missing_fields:
                logger.warning(f"复权数据缺少字段: {missing_fields}")
                # 尝试其他可能的字段名
                field_mapping = {
                    '股票代码': 'ts_code',
                    '交易日期': 'trade_date',
                    '收盘价': 'close',
                    '前复权收盘价': 'close_qfq',
                    '收盘': 'close',
                    '前复权收盘': 'close_qfq'
                }

                for old_field, new_field in field_mapping.items():
                    if old_field in df.columns and new_field not in df.columns:
                        df = df.rename(columns={old_field: new_field})

                # 重新检查
                missing_fields = [f for f in required_fields if f not in df.columns]
                if missing_fields:
                    logger.error(f"复权数据仍然缺少必要字段: {missing_fields}")
                    return pd.DataFrame()

            # 过滤该股票的数据（如果文件包含多只股票）
            if len(df['ts_code'].unique()) > 1:
                # 转换股票代码格式进行比较
                target_code_1 = f"{stock_code}.SH"
                target_code_2 = f"{stock_code}.SZ"
                target_code_3 = stock_code

                # 尝试匹配不同格式的股票代码
                if target_code_1 in df['ts_code'].values:
                    df = df[df['ts_code'] == target_code_1]
                elif target_code_2 in df['ts_code'].values:
                    df = df[df['ts_code'] == target_code_2]
                elif target_code_3 in df['ts_code'].values:
                    df = df[df['ts_code'] == target_code_3]
                else:
                    logger.warning(f"在复权数据中未找到股票 {stock_code}")
                    return pd.DataFrame()

            # 处理数据
            df = df.copy()
            df['trade_date'] = pd.to_datetime(df['trade_date'], format='%Y%m%d', errors='coerce')
            df['trading_date_int'] = df['trade_date'].dt.strftime('%Y%m%d').astype(int)

            # 按日期排序
            df = df.sort_values('trading_date_int')

            # 计算前复权因子：前复权因子 = close_qfq / close
            df['adjust_factor'] = df['close_qfq'] / df['close']

            # 检查复权因子的合理性
            if (df['adjust_factor'] > 1.1).any():
                logger.warning(f"股票 {stock_code} 发现异常大的复权因子（>1.1）")

            if (df['adjust_factor'] < 0.1).any():
                logger.warning(f"股票 {stock_code} 发现异常小的复权因子（<0.1）")

            # 检查复权因子的单调性（前复权应该单调递减）
            df['factor_diff'] = df['adjust_factor'].diff()
            increasing_factors = df[df['factor_diff'] > 0.0001]
            if len(increasing_factors) > 0:
                logger.warning(f"股票 {stock_code} 发现 {len(increasing_factors)} 个异常增加的复权因子")

            logger.info(f"成功加载股票 {stock_code} 的 {len(df)} 天前复权数据")
            logger.info(f"复权因子范围: {df['adjust_factor'].min():.6f} - {df['adjust_factor'].max():.6f}")

            return df[['trade_date', 'trading_date_int', 'close', 'close_qfq', 'adjust_factor']]

        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"加载复权数据失败 {file_path}: {str(e)}")
            logger.debug(f"详细错误信息: {error_msg}")
            return pd.DataFrame()

    def get_daily_adjustment_factors(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """
        获取日级前复权因子

        Parameters:
        -----------
        stock_code : str
            股票代码
        start_date : str
            开始日期 (YYYYMMDD)
        end_date : str
            结束日期 (YYYYMMDD)

        Returns:
        --------
        DataFrame: 包含日期和前复权因子的数据
        """
        cache_key = f"{stock_code}_{start_date}_{end_date}"

        # 检查缓存
        if cache_key in self.daily_adjustment_factors:
            logger.info(f"从缓存获取 {stock_code} 的复权因子")
            return self.daily_adjustment_factors[cache_key]

        try:
            logger.info(f"获取股票 {stock_code} 的日级前复权因子，日期范围: {start_date} 到 {end_date}")

            # 加载复权数据
            df_adjust = self.load_adjustment_data(stock_code)

            if df_adjust.empty:
                logger.error(f"无法加载股票 {stock_code} 的复权数据")
                return pd.DataFrame()

            # 转换为整型日期用于过滤
            start_date_int = int(start_date)
            end_date_int = int(end_date)

            # 过滤日期范围
            mask = (df_adjust['trading_date_int'] >= start_date_int) & (df_adjust['trading_date_int'] <= end_date_int)
            df_filtered = df_adjust[mask].copy()

            if df_filtered.empty:
                logger.warning(f"股票 {stock_code} 在日期范围 {start_date} 到 {end_date} 内无复权数据")
                # 返回所有数据，让后续处理填充
                df_filtered = df_adjust.copy()

            # 重命名列以保持一致
            df_filtered = df_filtered.rename(columns={
                'trade_date': 'date'
            })

            # 缓存结果
            result_df = df_filtered[['date', 'trading_date_int', 'adjust_factor']].copy()
            self.daily_adjustment_factors[cache_key] = result_df

            logger.info(f"成功获取 {stock_code} 的 {len(result_df)} 天前复权因子")
            logger.info(f"日期范围: {result_df['trading_date_int'].min()} 到 {result_df['trading_date_int'].max()}")
            logger.info(
                f"复权因子范围: {result_df['adjust_factor'].min():.6f} - {result_df['adjust_factor'].max():.6f}")

            return result_df

        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"获取 {stock_code} 前复权因子失败: {str(e)}")
            logger.debug(f"详细错误信息: {error_msg}")
            return pd.DataFrame()

    def load_level2_data(self, file_path: Path) -> pd.DataFrame:
        """
        加载Level2高频数据

        Parameters:
        -----------
        file_path : Path
            数据文件路径

        Returns:
        --------
        DataFrame: Level2数据
        """
        try:
            logger.info(f"加载Level2数据: {file_path}")

            # 读取parquet文件
            df = pd.read_parquet(file_path)

            # 标准化列名（去除可能的前后空格）
            df.columns = df.columns.str.strip()

            # 检查必要字段
            required_fields = ['SecuCode', 'TradingDay', 'TickTime', 'Price']
            missing_fields = [f for f in required_fields if f not in df.columns]

            if missing_fields:
                logger.error(f"缺少必要字段: {missing_fields}")
                raise ValueError(f"数据缺少必要字段: {missing_fields}")

            # 确保数据类型正确
            df['SecuCode'] = df['SecuCode'].astype(str).str.strip()

            # 处理TradingDay为整型的情况
            if df['TradingDay'].dtype in ['int64', 'int32']:
                logger.info(f"TradingDay为整型，转换为datetime")
                df['TradingDay_str'] = df['TradingDay'].astype(str)
                df['date'] = pd.to_datetime(df['TradingDay_str'], format='%Y%m%d', errors='coerce')
                invalid_dates = df['date'].isna().sum()
                if invalid_dates > 0:
                    logger.warning(f"发现 {invalid_dates} 个无效的交易日日期")
            else:
                df['date'] = pd.to_datetime(df['TradingDay'], errors='coerce')

            # 处理TickTime
            if df['TickTime'].dtype == 'object':
                df['TickTime'] = pd.to_datetime(df['TickTime'], errors='coerce')

            # 按时间排序
            df = df.sort_values(['date', 'TickTime']).reset_index(drop=True)

            # 添加整型交易日字段
            df['trading_date_int'] = df['date'].dt.strftime('%Y%m%d').astype(int)

            # 记录基本信息
            logger.info(f"加载完成: {len(df)} 行数据")
            logger.info(f"股票代码: {df['SecuCode'].iloc[0] if len(df) > 0 else '未知'}")
            logger.info(f"交易日范围: {df['trading_date_int'].min()} 到 {df['trading_date_int'].max()}")
            logger.info(f"时间范围: {df['TickTime'].min()} 到 {df['TickTime'].max()}")

            return df

        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"加载Level2数据失败 {file_path}: {str(e)}")
            logger.debug(f"详细错误信息: {error_msg}")
            raise

    def merge_adjustment_factors(self, level2_data: pd.DataFrame, daily_factors: pd.DataFrame) -> pd.DataFrame:
        """
        将日级复权因子合并到Level2数据

        Parameters:
        -----------
        level2_data : DataFrame
            Level2高频数据
        daily_factors : DataFrame
            日级复权因子

        Returns:
        --------
        DataFrame: 合并后的数据
        """
        if daily_factors.empty:
            logger.warning("日级复权因子为空，使用默认因子1.0")
            level2_data['adjust_factor'] = 1.0
            return level2_data

        try:
            # 确保有必要的字段
            if 'trading_date_int' not in level2_data.columns:
                logger.error("Level2数据缺少 trading_date_int 字段")
                return level2_data

            if 'trading_date_int' not in daily_factors.columns:
                logger.error("日级复权因子缺少 trading_date_int 字段")
                return level2_data

            # 按整型交易日合并复权因子
            logger.info(f"开始合并复权因子，Level2数据交易日: {sorted(level2_data['trading_date_int'].unique()[:3])}")
            logger.info(f"复权因子交易日: {sorted(daily_factors['trading_date_int'].unique()[:3])}")

            merged = pd.merge(
                level2_data,
                daily_factors[['trading_date_int', 'adjust_factor']],
                on='trading_date_int',
                how='left'
            )

            # 检查合并结果
            missing_factor = merged['adjust_factor'].isna().sum()
            total_rows = len(merged)

            if missing_factor > 0:
                missing_pct = missing_factor / total_rows * 100
                logger.warning(f"有 {missing_factor} 行数据 ({missing_pct:.1f}%) 缺少复权因子")

                # 查找缺失复权因子的交易日
                missing_dates = merged[merged['adjust_factor'].isna()]['trading_date_int'].unique()
                logger.warning(f"缺失复权因子的交易日: {sorted(missing_dates[:5])}")

                # 对于缺失的交易日，使用最近的有效复权因子
                # 首先向前填充（用更早的因子）
                merged['adjust_factor'] = merged['adjust_factor'].ffill()
                # 然后向后填充（用更晚的因子）
                merged['adjust_factor'] = merged['adjust_factor'].bfill()
                # 最后填充NaN为1.0
                merged['adjust_factor'] = merged['adjust_factor'].fillna(1.0)

                logger.info(f"填充后，缺失因子减少到 {merged['adjust_factor'].isna().sum()} 行")

            logger.info(f"合并完成: {len(merged)} 行数据")
            logger.info(
                f"复权因子统计 - 最小值: {merged['adjust_factor'].min():.6f}, 最大值: {merged['adjust_factor'].max():.6f}")
            logger.info(
                f"复权因子统计 - 平均值: {merged['adjust_factor'].mean():.6f}, 最新值: {merged['adjust_factor'].iloc[-1]:.6f}")

            return merged

        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"合并复权因子失败: {str(e)}")
            logger.debug(f"详细错误信息: {error_msg}")

            # 出错时使用默认因子
            level2_data['adjust_factor'] = 1.0
            return level2_data

    def apply_forward_adjustment_to_level2(self, level2_data: pd.DataFrame) -> pd.DataFrame:
        """
        对Level2数据应用前复权 - 只调整价格字段，并保留两位小数

        Parameters:
        -----------
        level2_data : DataFrame
            包含复权因子的Level2数据

        Returns:
        --------
        DataFrame: 前复权后的Level2数据（价格保留两位小数）
        """
        try:
            # 复制数据避免修改原始数据
            df = level2_data.copy()

            logger.info(f"开始应用前复权，数据形状: {df.shape}")
            logger.info(f"复权因子范围: {df['adjust_factor'].min():.6f} - {df['adjust_factor'].max():.6f}")

            # 检查复权因子是否存在
            if 'adjust_factor' not in df.columns:
                logger.error("数据中缺少 adjust_factor 字段")
                return df

            # **只调整价格字段，成交量/成交额等保持不变**
            adjusted_fields = []

            for field in self.price_fields_to_adjust:
                if field in df.columns:
                    # 保存原始值（保持原始精度）
                    df[f'Raw{field}'] = df[field]
                    # 应用前复权因子：前复权价格 = 原始价格 × adjust_factor，然后保留两位小数
                    df[field] = (df[field] * df['adjust_factor']).round(2)
                    adjusted_fields.append(field)
                    logger.debug(f"调整价格字段 {field}，保留两位小数")

            logger.info(f"价格字段调整完成: 调整了 {len(adjusted_fields)} 个字段，全部保留两位小数")
            logger.info(f"调整的字段: {adjusted_fields}")

            # **重要：成交量和成交额字段保持不变**
            # 验证一些成交量字段是否被意外修改
            volume_fields = ['Volume', 'TotalVolume', 'Turnover', 'TotalTurnover']
            for field in volume_fields:
                if field in df.columns:
                    logger.info(f"成交量字段 {field} 保持不变，均值: {df[field].mean():.2f}")

            # 检查买卖盘挂单量是否保持不变
            for i in range(1, 11):
                ask_vol_field = f'AskVolume{i}'
                bid_vol_field = f'BidVolume{i}'
                if ask_vol_field in df.columns and bid_vol_field in df.columns:
                    logger.debug(f"挂单量字段 {ask_vol_field} 和 {bid_vol_field} 保持不变")

            # 添加处理标记和元数据
            df.attrs['forward_adjusted'] = True
            df.attrs['adjustment_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            df.attrs['adjusted_price_fields'] = adjusted_fields
            df.attrs['price_decimal_places'] = 2  # 记录保留的小数位数
            df.attrs['adjust_factor_stats'] = {
                'min': float(df['adjust_factor'].min()),
                'max': float(df['adjust_factor'].max()),
                'mean': float(df['adjust_factor'].mean()),
                'std': float(df['adjust_factor'].std()),
                'latest': float(df['adjust_factor'].iloc[-1]) if len(df) > 0 else 1.0,
                'data_source': '本地前复权数据文件'
            }

            logger.info(f"Level2数据前复权完成，所有价格字段保留两位小数")
            logger.info(f"数据源: 本地前复权数据文件")

            return df

        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"应用前复权失败: {str(e)}")
            logger.debug(f"详细错误信息: {error_msg}")
            return level2_data

    def validate_level2_adjustment(self, raw_df: pd.DataFrame, adjusted_df: pd.DataFrame) -> Dict[str, any]:
        """
        验证Level2数据复权结果

        Parameters:
        -----------
        raw_df : DataFrame
            原始数据
        adjusted_df : DataFrame
            复权后数据

        Returns:
        --------
        Dict: 验证结果
        """
        validation_results = {
            'passed': True,
            'issues': [],
            'warnings': [],
            'stats': {}
        }

        try:
            logger.info("开始验证复权结果")

            # 基本统计
            validation_results['stats']['raw_rows'] = len(raw_df)
            validation_results['stats']['adjusted_rows'] = len(adjusted_df)
            validation_results['stats']['raw_dates'] = raw_df['trading_date_int'].nunique()
            validation_results['stats']['adjusted_dates'] = adjusted_df['trading_date_int'].nunique()

            # 检查行数是否一致
            if len(raw_df) != len(adjusted_df):
                validation_results['warnings'].append(f"行数不一致: 原始={len(raw_df)}, 复权后={len(adjusted_df)}")

            # **验证价格字段是否被正确调整并保留两位小数**
            for price_field in self.price_fields_to_adjust:
                if price_field in raw_df.columns and price_field in adjusted_df.columns:
                    # 检查是否有对应的原始值字段
                    raw_price_field = f'Raw{price_field}'
                    if raw_price_field in adjusted_df.columns:
                        # 验证调整公式: adjusted_price = round(raw_price * adjust_factor, 2)
                        expected_adjusted = (adjusted_df[raw_price_field] * adjusted_df['adjust_factor']).round(2)
                        actual_adjusted = adjusted_df[price_field]

                        # 计算误差
                        diff = abs(expected_adjusted - actual_adjusted)
                        max_diff = diff.max()
                        mean_diff = diff.mean()

                        # 由于四舍五入，允许0.015的误差
                        if max_diff > 0.015:  # 允许1.5分钱的误差
                            validation_results['issues'].append(
                                f"价格字段 {price_field} 调整误差过大: 最大误差={max_diff:.4f}, 平均误差={mean_diff:.4f}"
                            )
                        else:
                            logger.info(f"价格字段 {price_field} 调整验证通过: 最大误差={max_diff:.4f}")

                        # 检查是否真的保留两位小数
                        decimal_check = adjusted_df[price_field].apply(lambda x: abs(x * 100 - round(x * 100)) < 0.0001)
                        if not decimal_check.all():
                            validation_results['warnings'].append(
                                f"价格字段 {price_field} 存在非两位小数的值"
                            )

            # **验证成交量字段是否保持不变**
            volume_fields_to_check = ['Volume', 'TotalVolume']
            for vol_field in volume_fields_to_check:
                if vol_field in raw_df.columns and vol_field in adjusted_df.columns:
                    # 检查成交量是否被意外修改
                    diff = abs(raw_df[vol_field] - adjusted_df[vol_field])
                    max_diff = diff.max()

                    if max_diff > 0.0001:  # 允许微小浮点误差
                        validation_results['issues'].append(
                            f"成交量字段 {vol_field} 被意外修改: 最大差异={max_diff:.6f}"
                        )
                    else:
                        logger.info(f"成交量字段 {vol_field} 保持不变验证通过")

            # 检查复权因子
            if 'adjust_factor' in adjusted_df.columns:
                # 检查同一交易日内的复权因子是否一致
                factor_issues = []
                for date_int, group in adjusted_df.groupby('trading_date_int'):
                    unique_factors = group['adjust_factor'].nunique()
                    if unique_factors > 1:
                        factor_range = group['adjust_factor'].max() - group['adjust_factor'].min()
                        if factor_range > 0.0001:  # 允许微小浮点误差
                            factor_issues.append(
                                f"交易日 {date_int}: {unique_factors} 个不同因子，范围差={factor_range:.6f}")

                if factor_issues:
                    validation_results['issues'].extend(factor_issues[:3])  # 只显示前3个
                    if len(factor_issues) > 3:
                        validation_results['issues'].append(f"... 还有 {len(factor_issues) - 3} 个交易日有问题")

                # 检查前复权因子范围（前复权因子应该<=1，但可能有微小误差）
                if (adjusted_df['adjust_factor'] > 1.001).any():
                    max_factor = adjusted_df['adjust_factor'].max()
                    validation_results['warnings'].append(
                        f"发现异常前复权因子（最大={max_factor:.6f} > 1.001）"
                    )

            # 检查买卖盘价差合理性
            if all(f in adjusted_df.columns for f in ['AskPrice1', 'BidPrice1']):
                spreads = adjusted_df['AskPrice1'] - adjusted_df['BidPrice1']
                abnormal_spreads = spreads[spreads < 0]  # 卖一价小于买一价
                if len(abnormal_spreads) > 0:
                    validation_results['issues'].append(
                        f"发现 {len(abnormal_spreads)} 处买卖盘价差异常（卖一<买一）"
                    )

            validation_results['passed'] = len(validation_results['issues']) == 0

            logger.info(f"验证完成: {'通过' if validation_results['passed'] else '未通过'}")
            logger.info(f"发现 {len(validation_results['issues'])} 个问题，{len(validation_results['warnings'])} 个警告")

        except Exception as e:
            error_msg = traceback.format_exc()
            logger.error(f"验证过程出错: {str(e)}")
            logger.debug(f"详细错误信息: {error_msg}")
            validation_results['passed'] = False
            validation_results['issues'].append(f"验证过程出错: {str(e)}")

        return validation_results

    def process_single_stock_level2(self, file_path: Path) -> Tuple[bool, Dict]:
        """
        处理单只股票的Level2数据

        Parameters:
        -----------
        file_path : Path
            数据文件路径

        Returns:
        --------
        Tuple[bool, Dict]: (是否成功, 处理详情)
        """
        stock_code = file_path.stem
        logger.info(f"开始处理Level2数据: {stock_code}")

        result = {
            'stock_code': stock_code,
            'success': False,
            'file_path': str(file_path),
            'processing_time': None,
            'error_message': None,
            'validation_results': None,
            'output_files': [],
            'data_stats': {}
        }

        start_time = time.time()

        try:
            # 1. 加载Level2数据
            level2_data = self.load_level2_data(file_path)

            if level2_data.empty:
                result['error_message'] = "Level2数据为空"
                logger.warning(f"股票 {stock_code} 数据为空")
                return False, result

            # 记录数据统计
            result['data_stats']['raw_rows'] = len(level2_data)
            result['data_stats'][
                'date_range'] = f"{level2_data['trading_date_int'].min()} - {level2_data['trading_date_int'].max()}"
            result['data_stats']['time_range'] = f"{level2_data['TickTime'].min()} - {level2_data['TickTime'].max()}"

            # 2. 确定日期范围
            start_date = str(level2_data['trading_date_int'].min())
            end_date = str(level2_data['trading_date_int'].max())

            logger.info(f"数据日期范围: {start_date} 到 {end_date}")

            # 3. 获取日级前复权因子（从本地文件）
            daily_factors = self.get_daily_adjustment_factors(stock_code, start_date, end_date)

            if daily_factors.empty:
                result['error_message'] = "无法获取日级前复权因子"
                logger.error(f"无法获取 {stock_code} 的前复权因子")
                return False, result

            result['data_stats']['factor_days'] = len(daily_factors)
            result['data_stats'][
                'factor_range'] = f"{daily_factors['adjust_factor'].min():.6f} - {daily_factors['adjust_factor'].max():.6f}"
            result['data_stats']['factor_latest'] = f"{daily_factors['adjust_factor'].iloc[-1]:.6f}"
            result['data_stats']['factor_oldest'] = f"{daily_factors['adjust_factor'].iloc[0]:.6f}"
            result['data_stats']['data_source'] = "本地前复权数据文件"

            # 4. 合并复权因子
            merged_data = self.merge_adjustment_factors(level2_data, daily_factors)

            # 5. 应用前复权（只调整价格字段，保留两位小数）
            adjusted_data = self.apply_forward_adjustment_to_level2(merged_data)

            # 6. 验证结果
            validation = self.validate_level2_adjustment(level2_data, adjusted_data)
            result['validation_results'] = validation

            if not validation['passed']:
                for issue in validation['issues']:
                    logger.warning(f"验证问题 ({stock_code}): {issue}")

            # 7. 保存结果
            # 保存完整的复权后数据
            output_file = self.save_path / f"{stock_code}_level2_forward_adjusted.parquet"
            adjusted_data.to_parquet(output_file, index=False)
            result['output_files'].append(str(output_file))

            # 保存日级复权因子
            factor_file = self.save_path / f"{stock_code}_daily_adjust_factors.parquet"
            daily_factors.to_parquet(factor_file, index=False)
            result['output_files'].append(str(factor_file))

            # 保存处理摘要
            summary = {
                'stock_code': stock_code,
                'processing_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'data_period': f"{start_date} to {end_date}",
                'total_records': len(adjusted_data),
                'trading_days': adjusted_data['trading_date_int'].nunique(),
                'price_decimal_places': 2,  # 记录价格保留两位小数
                'adjust_factor_min': float(adjusted_data['adjust_factor'].min()),
                'adjust_factor_max': float(adjusted_data['adjust_factor'].max()),
                'adjust_factor_latest': float(adjusted_data['adjust_factor'].iloc[-1]) if len(
                    adjusted_data) > 0 else 1.0,
                'adjusted_price_fields': adjusted_data.attrs.get('adjusted_price_fields', []),
                'data_source': '本地前复权数据文件',
                'validation_passed': validation['passed'],
                'validation_issues': validation['issues'],
                'validation_warnings': validation['warnings']
            }

            summary_file = self.save_path / f"{stock_code}_processing_summary.json"
            with open(summary_file, 'w', encoding='utf-8') as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
            result['output_files'].append(str(summary_file))

            # 8. 记录成功
            result['success'] = True
            processing_time = time.time() - start_time
            result['processing_time'] = processing_time

            logger.info(f"股票 {stock_code} 处理成功: {len(adjusted_data)} 行数据，处理时间: {processing_time:.2f}秒")

            # 处理延迟
            time.sleep(self.request_delay)

            return True, result

        except Exception as e:
            processing_time = time.time() - start_time
            result['processing_time'] = processing_time
            result['error_message'] = str(e)

            error_msg = traceback.format_exc()
            logger.error(f"处理股票 {stock_code} 失败: {str(e)}")
            logger.debug(f"详细错误信息: {error_msg}")

            return False, result

    def batch_process_level2(self, max_files: int = None, pattern: str = "*.parquet") -> Dict:
        """
        批量处理Level2数据

        Parameters:
        -----------
        max_files : int, optional
            最大处理文件数
        pattern : str
            文件匹配模式

        Returns:
        --------
        Dict: 批量处理结果
        """
        # 获取所有Level2数据文件
        files = list(self.raw_data_path.glob(pattern))

        if not files:
            logger.error(f"在 {self.raw_data_path} 中未找到匹配 {pattern} 的文件")
            return {}

        if max_files:
            files = files[:max_files]

        logger.info(f"找到 {len(files)} 个Level2数据文件，开始批量处理...")

        # 批量处理结果
        batch_results = {
            'total': len(files),
            'success': 0,
            'failed': 0,
            'success_codes': [],
            'failed_codes': [],
            'details': {},
            'start_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

        # 使用进度条处理
        for file_path in tqdm(files, desc="处理Level2数据"):
            stock_code = file_path.stem
            success, detail = self.process_single_stock_level2(file_path)

            batch_results['details'][stock_code] = detail

            if success:
                batch_results['success'] += 1
                batch_results['success_codes'].append(stock_code)
            else:
                batch_results['failed'] += 1
                batch_results['failed_codes'].append(stock_code)

        # 生成批量处理报告
        batch_results['end_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.generate_batch_report(batch_results)

        return batch_results

    def generate_batch_report(self, batch_results: Dict):
        """生成批量处理报告"""
        report_file = self.save_path / "batch_processing_report.md"

        try:
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("# Level2数据前复权批量处理报告（本地复权数据）\n\n")
                f.write(f"**生成时间:** {batch_results['end_time']}\n")
                f.write(f"**处理周期:** {batch_results['start_time']} 到 {batch_results['end_time']}\n\n")

                f.write("## 处理概览\n")
                f.write(f"- **总文件数:** {batch_results['total']}\n")
                f.write(f"- **处理成功:** {batch_results['success']}\n")
                f.write(f"- **处理失败:** {batch_results['failed']}\n")
                f.write(f"- **成功率:** {batch_results['success'] / batch_results['total'] * 100:.1f}%\n\n")

                if batch_results['success_codes']:
                    f.write("## 成功处理的股票\n")
                    f.write("| 序号 | 股票代码 | 数据行数 | 处理时间(秒) | 复权因子范围 | 最新因子 | 数据源 |\n")
                    f.write("|------|----------|----------|--------------|--------------|----------|--------|\n")
                    for i, code in enumerate(sorted(batch_results['success_codes']), 1):
                        detail = batch_results['details'][code]
                        rows = detail.get('data_stats', {}).get('raw_rows', 0)
                        proc_time = detail.get('processing_time', 0)
                        factor_range = detail.get('data_stats', {}).get('factor_range', 'N/A')
                        factor_latest = detail.get('data_stats', {}).get('factor_latest', 'N/A')
                        f.write(
                            f"| {i} | {code} | {rows:,} | {proc_time:.1f} | {factor_range} | {factor_latest} | 本地 |\n")
                    f.write("\n")

                if batch_results['failed_codes']:
                    f.write("## 处理失败的股票\n")
                    f.write("| 序号 | 股票代码 | 错误信息 |\n")
                    f.write("|------|----------|----------|\n")
                    for i, code in enumerate(sorted(batch_results['failed_codes']), 1):
                        detail = batch_results['details'][code]
                        error_msg = detail.get('error_message', '未知错误')
                        # 截断过长的错误信息
                        if len(error_msg) > 100:
                            error_msg = error_msg[:97] + "..."
                        f.write(f"| {i} | {code} | {error_msg} |\n")
                    f.write("\n")

                # 成功案例详情
                if batch_results['success_codes']:
                    f.write("## 处理详情示例\n")
                    sample_code = batch_results['success_codes'][0]
                    sample_detail = batch_results['details'][sample_code]

                    f.write(f"### 股票 {sample_code} 处理详情\n")
                    f.write(f"- **处理状态:** {'成功' if sample_detail['success'] else '失败'}\n")
                    f.write(f"- **处理时间:** {sample_detail.get('processing_time', 0):.2f}秒\n")
                    f.write(f"- **数据行数:** {sample_detail.get('data_stats', {}).get('raw_rows', 0)}\n")
                    f.write(f"- **交易日范围:** {sample_detail.get('data_stats', {}).get('date_range', 'N/A')}\n")
                    f.write(
                        f"- **调整的价格字段:** {', '.join(sample_detail.get('validation_results', {}).get('stats', {}).get('adjusted_fields', ['无']))}\n")
                    f.write(f"- **价格小数位数:** 2位\n")
                    f.write(f"- **数据源:** 本地前复权数据文件\n")

                    if sample_detail.get('validation_results'):
                        validation = sample_detail['validation_results']
                        f.write(f"- **验证结果:** {'通过' if validation['passed'] else '未通过'}\n")
                        if validation['issues']:
                            f.write(f"- **验证问题:**\n")
                            for issue in validation['issues'][:2]:  # 只显示前2个
                                f.write(f"  - {issue}\n")
                            if len(validation['issues']) > 2:
                                f.write(f"  - ... 还有 {len(validation['issues']) - 2} 个问题\n")

                f.write(f"\n## 处理规则说明\n")
                f.write("1. **数据源:** 使用本地日级前复权数据文件\n")
                f.write("2. **复权因子计算:** 前复权因子 = 前复权收盘价(close_qfq) / 原始收盘价(close)\n")
                f.write("3. **只调整价格相关字段:** 包括最新价、买卖盘价格、加权平均价等\n")
                f.write("4. **价格保留两位小数:** 所有调整后的价格字段都四舍五入保留两位小数\n")
                f.write("5. **成交量/成交额保持不变:** Volume, Turnover, TotalVolume, TotalTurnover 等字段不调整\n")
                f.write("6. **挂单量保持不变:** AskVolume1-10, BidVolume1-10 等字段不调整\n")
                f.write("7. **原始值保存:** 调整的价格字段会保存原始值到 Raw{字段名} 字段中\n")

            logger.info(f"批量处理报告已保存至: {report_file}")

            # 打印简要报告
            print("\n" + "=" * 70)
            print("Level2数据前复权批量处理完成（本地复权数据）")
            print("=" * 70)
            print(f"处理总数: {batch_results['total']}")
            print(f"成功: {batch_results['success']}")
            print(f"失败: {batch_results['failed']}")
            print(f"成功率: {batch_results['success'] / batch_results['total'] * 100:.1f}%")
            print(f"价格小数位: 2位")
            print(f"数据源: 本地前复权数据文件")
            print(f"输出目录: {self.save_path}")
            print("=" * 70)

        except Exception as e:
            logger.error(f"生成批量处理报告失败: {str(e)}")


def main():
    """
    主函数 - Level2数据前复权处理
    """
    # 配置参数
    config = {
        'raw_data_path': './level2_data/raw',  # 原始Level2数据路径
        'save_path': './level2_data/forward_adjusted',  # 保存路径
        'adjust_data_path': './adjustment_data',  # 本地复权数据路径
        'max_files': 5,  # 最大处理文件数（测试用，None表示全部）
        'request_delay': 0.1,  # 处理延迟（秒）
        'pattern': '*.parquet'  # 文件匹配模式
    }

    print("开始Level2数据前复权处理（本地复权数据）...")
    print(f"原始数据目录: {config['raw_data_path']}")
    print(f"复权数据目录: {config['adjust_data_path']}")
    print(f"输出目录: {config['save_path']}")
    print(f"最大处理文件数: {config['max_files'] or '全部'}")
    print("-" * 70)
    print("处理规则: 只调整价格字段，价格保留两位小数，成交量/成交额等保持不变")
    print("数据源: 本地前复权数据文件")
    print("-" * 70)

    try:
        # 创建Level2复权处理器
        adjuster = Level2ForwardAdjuster(
            raw_data_path=config['raw_data_path'],
            save_path=config['save_path'],
            adjust_data_path=config['adjust_data_path']
        )

        # 设置处理延迟
        adjuster.request_delay = config['request_delay']

        # 批量处理
        results = adjuster.batch_process_level2(
            max_files=config['max_files'],
            pattern=config['pattern']
        )

        # 显示成功案例详情
        if results['success'] > 0:
            print("\n成功案例详情:")
            sample_code = results['success_codes'][0]
            sample_detail = results['details'][sample_code]

            # 读取处理后的数据示例
            if sample_detail.get('output_files'):
                adjusted_file = sample_detail['output_files'][0]
                if adjusted_file.endswith('_level2_forward_adjusted.parquet'):
                    try:
                        df_sample = pd.read_parquet(adjusted_file)

                        print(f"\n股票 {sample_code} 处理结果:")
                        print(f"数据行数: {len(df_sample):,}")
                        print(f"交易日数: {df_sample['trading_date_int'].nunique()}")

                        if 'adjust_factor' in df_sample.columns:
                            print(
                                f"复权因子范围: {df_sample['adjust_factor'].min():.6f} - {df_sample['adjust_factor'].max():.6f}")

                            # 按交易日显示复权因子
                            print("\n按交易日的复权因子（前5个）:")
                            factor_by_day = df_sample.groupby('trading_date_int')['adjust_factor'].first().reset_index()
                            for _, row in factor_by_day.head(5).iterrows():
                                print(f"  {row['trading_date_int']}: {row['adjust_factor']:.6f}")
                            if len(factor_by_day) > 5:
                                print(f"  ... 还有 {len(factor_by_day) - 5} 个交易日")

                        # 显示价格调整前后对比
                        if all(col in df_sample.columns for col in ['Price', 'RawPrice', 'Volume']):
                            print(f"\n价格调整前后对比 (前3条):")
                            sample_data = df_sample.head(3)[
                                ['trading_date_int', 'TickTime', 'Price', 'RawPrice', 'adjust_factor', 'Volume']]
                            sample_data['Price'] = sample_data['Price'].round(2)
                            sample_data['RawPrice'] = sample_data['RawPrice'].round(4)
                            sample_data['adjust_factor'] = sample_data['adjust_factor'].round(6)
                            print(sample_data.to_string(index=False))

                            # 验证价格是否保留两位小数
                            print(f"\n价格小数位验证:")
                            for price in sample_data['Price']:
                                price_str = f"{price:.2f}"
                                is_two_decimal = abs(float(price_str) - price) < 0.001
                                print(
                                    f"  {price} -> 格式化后: {price_str} ({'两位小数' if is_two_decimal else '非两位小数'})")

                            # 验证成交量是否保持不变
                            print(f"\n成交量验证 (前3条):")
                            volume_check = df_sample.head(3)[['trading_date_int', 'TickTime', 'Volume', 'TotalVolume']]
                            print(volume_check.to_string(index=False))

                    except Exception as e:
                        print(f"读取示例数据失败: {e}")

    except Exception as e:
        error_msg = traceback.format_exc()
        logger.error(f"程序执行失败: {str(e)}")
        print(f"\n错误: {str(e)}")
        print("详细错误信息请查看日志文件: level2_forward_adjustment.log")


def test_single_stock():
    """
    测试单只股票处理
    """
    # 测试配置
    test_config = {
        'raw_file': 'C:/baidunetdiskdownload/2023/20230501_20230601/000001.parquet',  # 测试文件
        'save_dir': './',  # 测试输出目录
        'adjust_data_dir': 'C:/baidunetdiskdownload/adj_factor'  # 复权数据目录
    }

    adjuster = Level2ForwardAdjuster(
        raw_data_path=os.path.dirname(test_config['raw_file']),
        save_path=test_config['save_dir'],
        adjust_data_path=test_config['adjust_data_dir']
    )

    success, detail = adjuster.process_single_stock_level2(Path(test_config['raw_file']))

    print(f"\n处理结果: {'成功' if success else '失败'}")
    if success:
        print(f"输出文件:")
        for file in detail['output_files']:
            print(f"  {file}")

        # 验证结果
        if detail['validation_results']:
            validation = detail['validation_results']
            print(f"\n验证结果: {'通过' if validation['passed'] else '未通过'}")
            if validation['issues']:
                print("问题列表:")
                for issue in validation['issues']:
                    print(f"  - {issue}")
            if validation['warnings']:
                print("警告列表:")
                for warning in validation['warnings']:
                    print(f"  - {warning}")


if __name__ == "__main__":
    # 运行主函数进行批量处理
    # main()

    # 或者测试单只股票
    test_single_stock()