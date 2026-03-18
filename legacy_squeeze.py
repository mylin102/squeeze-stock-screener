import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from datetime import datetime, timedelta
import yfinance as yf
from matplotlib.patches import Rectangle
import os

# 設定中文顯示
def get_chinese_font():
    # 優先嘗試尋找 Mac 內建字體
    mac_fonts = [
        '/System/Library/Fonts/PingFang.ttc',
        '/System/Library/Fonts/STHeiti Light.ttc',
        '/System/Library/Fonts/STHeiti Medium.ttc',
        '/Library/Fonts/Arial Unicode.ttf'
    ]
    
    # 檢查本地目錄是否有 NotoSansTC
    local_font = 'NotoSansTC-VariableFont_wght.ttf'
    if os.path.exists(local_font):
        return fm.FontProperties(fname=local_font, size=10)
    
    # 搜尋 Mac 系統字體
    for font_path in mac_fonts:
        if os.path.exists(font_path):
            try:
                return fm.FontProperties(fname=font_path, size=10)
            except:
                continue
    
    # 如果都找不到，嘗試讓 matplotlib 自動搜尋系統字體
    try:
        # 在某些系統上 'Arial Unicode MS' 或 'Microsoft JhengHei' 是可用的
        for f in fm.findSystemFonts():
            if 'PingFang' in f or 'STHeiti' in f or 'JhengHei' in f:
                return fm.FontProperties(fname=f, size=10)
    except:
        pass
        
    print("提示：找不到適合的中文字體，圖表可能無法顯示中文。請下載 NotoSansTC 字體。")
    return fm.FontProperties(size=10)

zhfont = get_chinese_font()

class PowerSqueezeIndicator:
    """
    PowerSqueeze指標計算類別
    基於John Carter的Squeeze概念改良，結合能量累積與爆發方向
    """
    
    def __init__(self, df, bb_period=20, bb_std=2.0, kc_period=20, kc_atr_mult=1.5):
        """
        初始化PowerSqueeze指標
        
        Parameters:
        -----------
        df : DataFrame
            包含OHLC資料的DataFrame
        bb_period : int
            Bollinger Bands的週期
        bb_std : float
            Bollinger Bands的標準差倍數
        kc_period : int
            Keltner Channels的週期
        kc_atr_mult : float
            Keltner Channels的ATR倍數
        """
        self.df = df.copy()
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.kc_period = kc_period
        self.kc_atr_mult = kc_atr_mult
        
    def calculate_atr(self, period=14):
        """計算平均真實區間(ATR)"""
        high = self.df['High']
        low = self.df['Low']
        close = self.df['Close']
        
        # 計算TR
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # 計算ATR
        atr = tr.rolling(window=period).mean()
        return atr
    
    def calculate_keltner_channels(self):
        """計算Keltner Channels"""
        # 典型價格 = (高+低+收)/3
        tp = (self.df['High'] + self.df['Low'] + self.df['Close']) / 3
        
        # EMA of typical price
        ema_tp = tp.ewm(span=self.kc_period, adjust=False).mean()
        
        # ATR for channel width
        atr = self.calculate_atr(period=self.kc_period)
        
        # Keltner Channels
        kc_upper = ema_tp + (self.kc_atr_mult * atr)
        kc_lower = ema_tp - (self.kc_atr_mult * atr)
        
        return kc_upper, kc_lower, ema_tp
    
    def calculate_bollinger_bands(self):
        """計算Bollinger Bands"""
        # 計算移動平均和標準差
        sma = self.df['Close'].rolling(window=self.bb_period).mean()
        std = self.df['Close'].rolling(window=self.bb_period).std()
        
        # Bollinger Bands
        bb_upper = sma + (std * self.bb_std)
        bb_lower = sma - (std * self.bb_std)
        
        return bb_upper, bb_lower, sma
    
    def calculate_momentum(self, period=12):
        """計算動能指標（柱狀圖）"""
        # 使用價格動能
        momentum = self.df['Close'] - self.df['Close'].shift(period)
        
        # 標準化處理
        momentum_norm = (momentum - momentum.rolling(window=100).min()) / \
                       (momentum.rolling(window=100).max() - momentum.rolling(window=100).min()) * 2 - 1
        momentum_norm = momentum_norm.fillna(0)
        
        return momentum_norm
    
    def calculate_squeeze(self):
        """
        計算Squeeze狀態與能量累積程度
        
        Returns:
        --------
        squeeze_on : 是否處於擠壓狀態
        energy_level : 能量累積程度 (0-3, 0:無, 1:一般, 2:中等, 3:高度)
        """
        bb_upper, bb_lower, bb_sma = self.calculate_bollinger_bands()
        kc_upper, kc_lower, kc_ema = self.calculate_keltner_channels()
        
        # 判斷是否在擠壓狀態（BB在KC內部）
        squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)
        
        # 計算擠壓程度（能量累積）
        bb_width = bb_upper - bb_lower
        kc_width = kc_upper - kc_lower
        
        # 能量累積程度：BB寬度相對KC寬度的壓縮比例
        squeeze_ratio = (kc_width - bb_width) / kc_width
        squeeze_ratio = squeeze_ratio.clip(lower=0, upper=1)
        
        # 轉換為能量等級 (0-3)
        energy_level = pd.cut(squeeze_ratio, 
                             bins=[-np.inf, 0.3, 0.5, 0.7, np.inf], 
                             labels=[0, 1, 2, 3]).fillna(0).astype(int)
        
        return squeeze_on, energy_level
    
    def get_power_squeeze_signals(self):
        """
        獲取完整的PowerSqueeze信號
        
        Returns:
        --------
        DataFrame: 包含所有指標的DataFrame
        """
        # 計算擠壓狀態和能量等級
        squeeze_on, energy_level = self.calculate_squeeze()
        
        # 計算動能（柱狀圖方向）
        momentum = self.calculate_momentum()
        
        # 能量顏色定義
        # 0:灰色(無累積), 1:粉紅(一般), 2:橘色(中等), 3:紅色(高度)
        colors = {
            0: '#808080',  # 灰色
            1: '#FF69B4',  # 粉紅色
            2: '#FFA500',  # 橘色
            3: '#FF0000'   # 紅色
        }
        
        # 建立結果DataFrame
        result = self.df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        result['Squeeze_On'] = squeeze_on
        result['Energy_Level'] = energy_level
        result['Momentum'] = momentum
        result['Color'] = result['Energy_Level'].map(colors)
        
        # 標記爆發狀態 (Squeeze Fired)
        result['Fired'] = (~squeeze_on) & (squeeze_on.shift(1) == True)
        
        return result


class TaiwanIndexAnalyzer:
    """
    台灣指數分析與視覺化類別
    """
    
    def __init__(self, ticker='^TWII', period='6mo'):
        """
        初始化分析器
        
        Parameters:
        -----------
        ticker : str
            股票代號，預設'^TWII'為台灣加權指數
        period : str
            資料期間 (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max)
        """
        self.ticker = ticker
        self.period = period
        self.data = None
        self.signals = None
        
    def fetch_data(self):
        """從yfinance獲取指數資料"""
        try:
            print(f"正在抓取 {self.ticker} 資料...")
            self.data = yf.download(self.ticker, period=self.period, progress=False)
            
            if self.data.empty:
                raise ValueError("無法獲取資料，請檢查網路連線或股票代號")
            
            # 標準化欄位名稱
            self.data.columns = ['Close', 'High', 'Low', 'Open', 'Volume']
            print(f"成功抓取 {len(self.data)} 筆資料")
            print(f"資料區間: {self.data.index[0].strftime('%Y-%m-%d')} 至 {self.data.index[-1].strftime('%Y-%m-%d')}")
            
            return True
            
        except Exception as e:
            print(f"資料抓取失敗: {e}")
            return False
    
    def calculate_power_squeeze(self):
        """計算PowerSqueeze指標"""
        if self.data is None:
            print("請先抓取資料")
            return None
        
        ps = PowerSqueezeIndicator(self.data)
        self.signals = ps.get_power_squeeze_signals()
        return self.signals
    
    def plot_power_squeeze(self, days_to_show=120, conclusion_text=""):
        """
        繪製PowerSqueeze視覺化圖表
        
        Parameters:
        -----------
        days_to_show : int
            要顯示的天數（避免圖表過於擁擠）
        conclusion_text : str
            顯示在圖表下方的判斷結論
        """
        if self.signals is None:
            print("請先計算指標")
            return
        
        # 只顯示最近N天的資料
        plot_data = self.signals.iloc[-days_to_show:].copy()
        
        # 建立圖表 (增加高度以容納文字)
        fig = plt.figure(figsize=(16, 12))
        
        # 設定圖表佈局 (調整比例留出底部空間)
        gs = fig.add_gridspec(4, 1, height_ratios=[3, 1, 1, 0.8], hspace=0.2)
        
        # 主圖：K線圖
        ax1 = fig.add_subplot(gs[0])
        self._plot_candlestick(ax1, plot_data)
        ax1.set_ylabel('指數點數', fontproperties=zhfont)
        ax1.set_title(f'台灣加權指數 PowerSqueeze 分析 ({self.ticker})', 
                     fontproperties=zhfont, fontsize=14, fontweight='bold')
        ax1.legend(prop=zhfont, loc='upper left')
        ax1.grid(True, alpha=0.3)
        
        # 中圖：能量累積狀態（彩色圓點）
        ax2 = fig.add_subplot(gs[1], sharex=ax1)
        self._plot_energy_dots(ax2, plot_data)
        ax2.set_ylabel('能量累積', fontproperties=zhfont)
        ax2.legend(prop=zhfont, loc='upper left')
        ax2.grid(True, alpha=0.3)
        
        # 下圖：動能柱狀圖
        ax3 = fig.add_subplot(gs[2], sharex=ax1)
        self._plot_momentum_bars(ax3, plot_data)
        ax3.set_ylabel('動能方向', fontproperties=zhfont)
        ax3.legend(prop=zhfont, loc='upper left')
        ax3.grid(True, alpha=0.3)
        
        # 底部：文字結論區
        if conclusion_text:
            ax4 = fig.add_subplot(gs[3])
            ax4.axis('off')
            # 使用矩形框包裹文字
            rect = Rectangle((0, 0), 1, 1, fill=True, color='#f0f0f0', alpha=0.5, transform=ax4.transAxes)
            ax4.add_patch(rect)
            ax4.text(0.02, 0.8, "🎯 綜合投資判斷結論", fontproperties=zhfont, fontsize=12, fontweight='bold', transform=ax4.transAxes)
            ax4.text(0.02, 0.1, conclusion_text, fontproperties=zhfont, fontsize=11, transform=ax4.transAxes, verticalalignment='bottom')

        # 調整x軸日期顯示
        for ax in [ax1, ax2, ax3]:
            ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y-%m-%d'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, fontsize=8)
        
        # plt.tight_layout() # 因為手動調整了佈局，先註解掉避免警告
        plt.savefig('power_squeeze_analysis.png', bbox_inches='tight', dpi=150)
        print("圖表已儲存為 power_squeeze_analysis.png")
        # plt.show()
        
        # 顯示最近的信號統計
        self._show_signal_summary(plot_data)
    
    def _plot_candlestick(self, ax, data):
        """繪製K線圖"""
        # 繪製K線
        width = 0.6
        width2 = 0.05
        
        # 計算漲跌顏色
        up = data[data['Close'] >= data['Open']]
        down = data[data['Close'] < data['Open']]
        
        # 繪製上漲K線
        ax.bar(up.index, up['Close'] - up['Open'], width, 
               bottom=up['Open'], color='red', edgecolor='black', alpha=0.8, label='上漲')
        ax.bar(up.index, up['High'] - up['Close'], width2, 
               bottom=up['Close'], color='red', alpha=0.8)
        ax.bar(up.index, up['Low'] - up['Open'], width2, 
               bottom=up['Open'], color='red', alpha=0.8)
        
        # 繪製下跌K線
        ax.bar(down.index, down['Close'] - down['Open'], width, 
               bottom=down['Open'], color='green', edgecolor='black', alpha=0.8, label='下跌')
        ax.bar(down.index, down['High'] - down['Open'], width2, 
               bottom=down['Open'], color='green', alpha=0.8)
        ax.bar(down.index, down['Low'] - down['Close'], width2, 
               bottom=down['Close'], color='green', alpha=0.8)
        
        # 添加20日均線
        sma20 = data['Close'].rolling(window=20).mean()
        ax.plot(data.index, sma20, color='blue', linewidth=1.5, label='20日均線')
    
    def _plot_energy_dots(self, ax, data):
        """繪製能量累積圓點"""
        # 能量等級對應的標籤
        energy_labels = {0: '無累積', 1: '一般', 2: '中等', 3: '高度'}
        
        # 為每個能量等級繪製圓點
        for energy_level in [3, 2, 1, 0]:
            mask = data['Energy_Level'] == energy_level
            if mask.any():
                color = data.loc[mask, 'Color'].iloc[0]
                label = energy_labels[energy_level]
                ax.scatter(data.index[mask], [1] * mask.sum(), 
                          c=color, s=100, label=label, alpha=0.7, edgecolors='black', linewidth=0.5)
        
        ax.set_ylim(0.5, 1.5)
        ax.set_yticks([])
        
        # 標記爆發點
        fired_dates = data[data['Fired']].index
        if len(fired_dates) > 0:
            for date in fired_dates:
                ax.axvline(x=date, color='purple', linestyle='--', alpha=0.5, linewidth=1)
            ax.scatter(fired_dates, [1.2] * len(fired_dates), 
                      c='purple', s=50, marker='^', label='能量爆發', alpha=0.8)
    
    def _plot_momentum_bars(self, ax, data):
        """繪製動能柱狀圖"""
        # 多頭動能（零軸以上）
        positive_mask = data['Momentum'] > 0
        # 空頭動能（零軸以下）
        negative_mask = data['Momentum'] < 0
        
        if positive_mask.any():
            ax.bar(data.index[positive_mask], data['Momentum'][positive_mask], 
                  color='red', alpha=0.6, label='多頭動能', width=0.8)
        
        if negative_mask.any():
            ax.bar(data.index[negative_mask], data['Momentum'][negative_mask], 
                  color='green', alpha=0.6, label='空頭動能', width=0.8)
        
        ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        
    def _show_signal_summary(self, data):
        """顯示信號統計摘要"""
        print("\n" + "="*50)
        print("📊 PowerSqueeze 信號統計摘要")
        print("="*50)
        
        # 能量等級統計
        energy_counts = data['Energy_Level'].value_counts().sort_index()
        energy_pcts = (energy_counts / len(data) * 100).round(1)
        
        energy_labels = {0: '無累積', 1: '一般', 2: '中等', 3: '高度'}
        for level in [3, 2, 1, 0]:
            if level in energy_counts.index:
                count = energy_counts[level]
                pct = energy_pcts[level]
                print(f"{energy_labels[level]}: {count}天 ({pct}%)")
        
        # 爆發信號統計
        fired_count = data['Fired'].sum()
        print(f"\n💥 近期爆發信號次數: {fired_count}次")
        
        # 最近的信號
        recent_fired = data[data['Fired']].index[-3:] if fired_count > 0 else []
        if len(recent_fired) > 0:
            print("\n🔔 最近爆發日期:")
            for date in recent_fired:
                print(f"   {date.strftime('%Y-%m-%d')}")
        
        # 目前狀態
        latest = data.iloc[-1]
        print(f"\n📈 最新狀態 ({data.index[-1].strftime('%Y-%m-%d')}):")
        print(f"   能量等級: {energy_labels[latest['Energy_Level']]}")
        print(f"   動能方向: {'多頭' if latest['Momentum'] > 0 else '空頭' if latest['Momentum'] < 0 else '中性'}")
        print(f"   擠壓狀態: {'是' if latest['Squeeze_On'] else '否'}")
        print("="*50)


class SMABacktestAnalyzer:
    """
    簡單移動平均線 (SMA) 交叉策略回測類別
    @quant-analyst 擴充
    """
    
    def __init__(self, df, short_window=50, long_window=200, initial_capital=100000.0):
        self.df = df.copy()
        self.short_window = short_window
        self.long_window = long_window
        self.initial_capital = initial_capital
        
    def run_backtest(self):
        """執行回測並計算指標"""
        # 1. 計算 SMA
        self.df['SMA_Short'] = self.df['Close'].rolling(window=self.short_window).mean()
        self.df['SMA_Long'] = self.df['Close'].rolling(window=self.long_window).mean()
        
        # 2. 生成信號
        self.df['Signal'] = 0.0
        # 當快線 > 慢線時持倉 (1.0)
        self.df.loc[self.df.index[self.short_window:], 'Signal'] = \
            np.where(self.df['SMA_Short'][self.short_window:] > self.df['SMA_Long'][self.short_window:], 1.0, 0.0)
        
        # 3. 計算收益
        self.df['Market_Returns'] = self.df['Close'].pct_change()
        self.df['Strategy_Returns'] = self.df['Market_Returns'] * self.df['Signal'].shift(1)
        
        # 4. 計算累積收益與資金曲線
        self.df['Cumulative_Market'] = (1 + self.df['Market_Returns']).cumprod()
        self.df['Cumulative_Strategy'] = (1 + self.df['Strategy_Returns']).cumprod()
        self.df['Portfolio_Value'] = self.initial_capital * self.df['Cumulative_Strategy']
        
        # 5. 計算績效指標
        total_return = self.df['Cumulative_Strategy'].iloc[-1] - 1
        annual_return = (1 + total_return) ** (252 / len(self.df)) - 1
        
        # 夏普比率 (假設無風險利率為 1%)
        risk_free_rate = 0.01
        daily_rf = (1 + risk_free_rate) ** (1/252) - 1
        excess_returns = self.df['Strategy_Returns'].dropna() - daily_rf
        sharpe_ratio = np.sqrt(252) * excess_returns.mean() / excess_returns.std() if excess_returns.std() != 0 else 0
        
        # 最大回撤
        rolling_max = self.df['Cumulative_Strategy'].cummax()
        drawdown = self.df['Cumulative_Strategy'] / rolling_max - 1
        max_drawdown = drawdown.min()
        
        metrics = {
            'Total Return': total_return,
            'Annual Return': annual_return,
            'Sharpe Ratio': sharpe_ratio,
            'Max Drawdown': max_drawdown,
            'Final Value': self.df['Portfolio_Value'].iloc[-1]
        }
        
        return metrics, self.df

    def plot_performance(self, ticker):
        """繪製回測績效圖"""
        metrics, data = self.run_backtest()
        
        plt.figure(figsize=(12, 6))
        plt.plot(data['Cumulative_Market'], label='基準 (買入持有)', color='gray', alpha=0.6)
        plt.plot(data['Cumulative_Strategy'], label=f'SMA {self.short_window}/{self.long_window} 策略', color='blue', linewidth=2)
        
        plt.title(f'{ticker} SMA 策略回測績效對比', fontproperties=zhfont, fontsize=14)
        plt.xlabel('日期', fontproperties=zhfont)
        plt.ylabel('累積收益率', fontproperties=zhfont)
        plt.legend(prop=zhfont)
        plt.grid(True, alpha=0.3)
        
        # 顯示指標文字
        stats_text = (f"總收益率: {metrics['Total Return']:.2%}\n"
                     f"年化收益: {metrics['Annual Return']:.2%}\n"
                     f"夏普比率: {metrics['Sharpe Ratio']:.2f}\n"
                     f"最大回撤: {metrics['Max Drawdown']:.2%}")
        
        plt.text(0.02, 0.95, stats_text, transform=plt.gca().transAxes, 
                 fontproperties=zhfont, verticalalignment='top', 
                 bbox=dict(boxstyle='round', facecolor='white', alpha=0.8))
        
        plt.savefig('sma_backtest_performance.png', bbox_inches='tight', dpi=150)
        print(f"回測圖表已儲存為 sma_backtest_performance.png")


def scan_multi_timeframe(ticker='^TWII'):
    """
    多時間框架掃描：同時分析日線和週線
    """
    print("\n" + "="*60)
    print("🌊 巨鯨交易機會掃描（多時間框架確認）")
    print("="*60)
    
    # 分析日線
    print("\n📅 日線分析:")
    daily = TaiwanIndexAnalyzer(ticker, period='3mo')
    if daily.fetch_data():
        daily_signals = daily.calculate_power_squeeze()
        daily_latest = daily_signals.iloc[-1]
        
        print(f"最新日期: {daily_signals.index[-1].strftime('%Y-%m-%d')}")
        print(f"能量等級: {daily_latest['Energy_Level']}")
        print(f"動能方向: {'多頭' if daily_latest['Momentum'] > 0 else '空頭' if daily_latest['Momentum'] < 0 else '中性'}")
        print(f"擠壓狀態: {'是' if daily_latest['Squeeze_On'] else '否'}")
    
    # 分析週線
    print("\n📆 週線分析:")
    weekly = TaiwanIndexAnalyzer(ticker, period='1y')
    if weekly.fetch_data():
        # 轉換為週線資料
        weekly_data = weekly.data.resample('W').agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()
        
        weekly.data = weekly_data
        weekly_signals = weekly.calculate_power_squeeze()
        weekly_latest = weekly_signals.iloc[-1]
        
        print(f"最新日期: {weekly_signals.index[-1].strftime('%Y-%m-%d')}")
        print(f"能量等級: {weekly_latest['Energy_Level']}")
        print(f"動能方向: {'多頭' if weekly_latest['Momentum'] > 0 else '空頭' if weekly_latest['Momentum'] < 0 else '中性'}")
        print(f"擠壓狀態: {'是' if weekly_latest['Squeeze_On'] else '否'}")
        
        # 巨鯨信號判斷
        if (daily_latest['Energy_Level'] >= 2 and weekly_latest['Energy_Level'] >= 2 and
            daily_latest['Momentum'] > 0 and weekly_latest['Momentum'] > 0):
            print("\n🐋 發現巨鯨交易機會！")
            print("   日線與週線同時顯示高度能量累積且動能向上")
        elif (daily_latest['Energy_Level'] >= 2 and weekly_latest['Energy_Level'] >= 2 and
              daily_latest['Momentum'] < 0 and weekly_latest['Momentum'] < 0):
            print("\n⚠️  注意空頭巨鯨信號")
            print("   日線與週線同時顯示高度能量累積且動能向下")
    
    print("="*60)


def generate_final_conclusion(ticker, daily_data, weekly_data):
    """
    根據日線與週線資料生成綜合判斷結論
    """
    d_latest = daily_data.iloc[-1]
    w_latest = weekly_data.iloc[-1]
    
    # 趨勢判定
    trend = "中性"
    if d_latest['Momentum'] > 0 and w_latest['Momentum'] > 0:
        trend = "強勢多頭 (日/週同步向上)"
    elif d_latest['Momentum'] > 0:
        trend = "短期偏多 (週線仍壓抑)"
    elif w_latest['Momentum'] > 0:
        trend = "中期偏多 (短期震盪拉回)"
    elif d_latest['Momentum'] < 0 and w_latest['Momentum'] < 0:
        trend = "強勢空頭 (日/週同步向下)"
    
    # 能量判定
    energy_status = "動能釋放中"
    if d_latest['Energy_Level'] >= 2:
        energy_status = "高度能量壓縮 (即將爆發)"
    elif d_latest['Energy_Level'] == 1:
        energy_status = "能量累積中"
    
    # 操作建議
    action = "觀望等待"
    if d_latest['Squeeze_On'] and d_latest['Energy_Level'] >= 2:
        action = "密切關注：目前處於高壓擠壓狀態，等待動能方向確認（柱狀圖轉向）後進場。"
    elif d_latest['Fired']:
        action = f"動能爆發：目前能量已釋放，{'多頭' if d_latest['Momentum'] > 0 else '空頭'}方向確立，可順勢操作。"
    elif d_latest['Momentum'] > 0 and not d_latest['Squeeze_On']:
        action = "多頭趨勢：目前無擠壓，動能向上，建議持股或尋找回檔買點。"
    elif d_latest['Momentum'] < 0 and not d_latest['Squeeze_On']:
        action = "空頭趨勢：目前無擠壓，動能向下，建議避開或反向操作。"

    conclusion = (f"📍 分析標的: {ticker}\n"
                 f"📈 當前趨勢: {trend}\n"
                 f"🔋 能量狀態: {energy_status}\n"
                 f"💡 操作建議: {action}")
    
    print("\n" + "🎯" + " " + "綜合投資判斷結論")
    print("="*60)
    print(conclusion)
    print("="*60)
    
    return conclusion


def main():
    """
    主程式：執行台灣加權指數PowerSqueeze分析
    """
    print("🚀 PowerSqueeze 台灣加權指數分析工具")
    print("="*50)
    
    ticker = '^TWII'
    
    # 1. 建立分析器並抓取日線資料
    analyzer = TaiwanIndexAnalyzer(ticker=ticker, period='2y')  # 增加期間至2年以便回測
    if not analyzer.fetch_data():
        print("程式執行失敗")
        return
    
    # 2. 計算日線指標
    print("\n正在計算PowerSqueeze指標...")
    daily_signals = analyzer.calculate_power_squeeze()
    
    # 3. 抓取並計算週線資料供綜合判斷
    print("\n正在計算多時間框架數據...")
    # 這裡可以直接使用已經抓取的 2y 資料
    weekly_data = analyzer.data.resample('W').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    }).dropna()
    
    # 為了計算週線的 Squeeze，我們需要另一個實例或直接計算
    ws_indicator = PowerSqueezeIndicator(weekly_data)
    weekly_signals = ws_indicator.get_power_squeeze_signals()
    
    # 4. 生成綜合結論
    conclusion_text = generate_final_conclusion(ticker, daily_signals, weekly_signals)
    
    # 5. 繪製圖表 (傳入結論文字)
    print("正在繪製視覺化圖表...")
    analyzer.signals = daily_signals # 確保繪圖使用日線資料
    analyzer.plot_power_squeeze(days_to_show=120, conclusion_text=conclusion_text)
    
    # 6. 執行 SMA 回測 (@quant-analyst 擴充)
    print("\n正在執行 SMA 策略回測分析...")
    backtest = SMABacktestAnalyzer(analyzer.data, short_window=50, long_window=200)
    backtest.plot_performance(ticker)
    
    print("\n✨ 分析與回測完成！")


if __name__ == "__main__":
    main()
