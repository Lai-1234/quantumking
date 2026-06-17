//+------------------------------------------------------------------+
//|                                  CStrategy_MACD_Momentum.mqh     |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.00"

#include "CStrategy.mqh"

class CStrategy_MACD_Momentum : public CStrategy
  {
private:
   // 大级别趋势过滤句柄
   int               m_ema50_h1;
   int               m_ema200_h1;
   int               m_ema50_h4;
   int               m_ema200_h4;

   // 触发级别 MACD 句柄
   int               m_macd_handle;

   // MACD 参数
   int               m_fast_ema;
   int               m_slow_ema;
   int               m_signal_sma;

public:
                     // 严格蓝图：默认使用华尔街标准 MACD 参数 (12, 26, 9)
                     CStrategy_MACD_Momentum(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf,
                                             int fastEMA = 12, int slowEMA = 26, int signalSMA = 9)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_fast_ema = fastEMA;
                        m_slow_ema = slowEMA;
                        m_signal_sma = signalSMA;

                        m_ema50_h1 = iMA(m_symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
                        m_ema200_h1 = iMA(m_symbol, PERIOD_H1, 200, 0, MODE_EMA, PRICE_CLOSE);
                        m_ema50_h4 = iMA(m_symbol, PERIOD_H4, 50, 0, MODE_EMA, PRICE_CLOSE);
                        m_ema200_h4 = iMA(m_symbol, PERIOD_H4, 200, 0, MODE_EMA, PRICE_CLOSE);

                        m_macd_handle = iMACD(m_symbol, m_timeframe, m_fast_ema, m_slow_ema, m_signal_sma, PRICE_CLOSE);

                        Print(m_strategy_name, " 动能伏击部队已就位 (H4/H1 顺势 + MACD 零轴动能爆破)");
                     }

                    ~CStrategy_MACD_Momentum(void)
                     {
                        IndicatorRelease(m_ema50_h1); IndicatorRelease(m_ema200_h1);
                        IndicatorRelease(m_ema50_h4); IndicatorRelease(m_ema200_h4);
                        IndicatorRelease(m_macd_handle);
                     }

   //========================================================================
   // 核心逻辑 2：大趋势护航 + MACD 跌破后翻上零轴 + 动能放大
   //========================================================================
   virtual double    CalculateSignal(void) override
                     {
                        double e50h1[], e200h1[], e50h4[], e200h4[];
                        double macd_main[], macd_signal[];

                        if(CopyBuffer(m_ema50_h1, 0, 1, 1, e50h1) <= 0 || CopyBuffer(m_ema200_h1, 0, 1, 1, e200h1) <= 0 ||
                           CopyBuffer(m_ema50_h4, 0, 1, 1, e50h4) <= 0 || CopyBuffer(m_ema200_h4, 0, 1, 1, e200h4) <= 0 ||
                           CopyBuffer(m_macd_handle, MAIN_LINE, 1, 3, macd_main) <= 0 ||
                           CopyBuffer(m_macd_handle, SIGNAL_LINE, 1, 3, macd_signal) <= 0) return 0;

                        // 【条件 1：大级别趋势向上/向下】用 H4 和 H1 的 EMA 阵型做绝对过滤
                        bool is_Bullish_MTF = (e50h4[0] > e200h4[0]) && (e50h1[0] > e200h1[0]);
                        bool is_Bearish_MTF = (e50h4[0] < e200h4[0]) && (e50h1[0] < e200h1[0]);

                        // 计算动能柱 (Histogram = Main - Signal)
                        double hist_current = macd_main[0] - macd_signal[0];
                        double hist_prev = macd_main[1] - macd_signal[1];

                        // 【做多爆破】：大趋势涨 + MACD 刚从水下翻上零轴 + 动能红柱放大
                        if(is_Bullish_MTF)
                          {
                           // macd_main[1] <= 0 且 macd_main[0] > 0 代表“跌破零轴后再次翻上零轴”
                           // hist_current > hist_prev 且 hist_current > 0 代表“动能放大”
                           if(macd_main[1] <= 0 && macd_main[0] > 0 && hist_current > 0 && hist_current > hist_prev)
                             {
                              Print("🚀 [MACD顺势-多] 大趋势向上，洗盘结束！MACD 翻上零轴且动能放大！");
                              return 100.0;
                             }
                          }

                        // 【做空爆破】：大趋势跌 + MACD 刚从水上跌穿零轴 + 动能绿柱放大
                        if(is_Bearish_MTF)
                          {
                           // macd_main[1] >= 0 且 macd_main[0] < 0 代表“冲上零轴后再次跌破零轴”
                           if(macd_main[1] >= 0 && macd_main[0] < 0 && hist_current < 0 && hist_current < hist_prev)
                             {
                              Print("🚀 [MACD顺势-空] 大趋势向下，反弹结束！MACD 跌穿零轴且动能放大！");
                              return -100.0;
                             }
                          }

                        return 0.0;
                     }

   //========================================================================
   // 进场：结构性防守计算
   //========================================================================
   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, m_timeframe, 0);
                        if(current_bar_time == last_bar_time) return;

                        double signal = CalculateSignal();
                        if(signal == 0.0) return;

                        // 自动扫描近期 50 根 K 线，寻找洗盘期间的波段极值点作为止损点
                        double high_arr[], low_arr[];
                        if(CopyHigh(m_symbol, m_timeframe, 1, 50, high_arr) <= 0 || CopyLow(m_symbol, m_timeframe, 1, 50, low_arr) <= 0) return;

                        double swing_high = high_arr[ArrayMaximum(high_arr)];
                        double swing_low  = low_arr[ArrayMinimum(low_arr)];

                        double current_price = (signal == 100.0) ? SymbolInfoDouble(m_symbol, SYMBOL_ASK) : SymbolInfoDouble(m_symbol, SYMBOL_BID);
                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
                        double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight);
                        bool is_opened = false;

                        if(signal == 100.0)
                          {
                           // 多单结构止损：挂在洗盘形成的最低点下方 150 点 (留出容错空间)
                           double dynamic_sl_pts = (current_price - swing_low) / point + 150;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                          }
                        else if(signal == -100.0)
                          {
                           // 空单结构止损：挂在反弹形成的最高点上方 150 点
                           double dynamic_sl_pts = (swing_high - current_price) / point + 150;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                          }

                        if(is_opened) last_bar_time = current_bar_time;
                     }

   //========================================================================
   // 退出：趋势策略必须让利润狂奔 (已适配三维参数引擎)
   //========================================================================
   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        // 参数 1: 1000点启动 (盈利 10美金开始干活)
                        // 参数 2: 1000点跟随距离 (止损线距离现价 10美金，给波段留下极大的呼吸空间)
                        // 参数 3: 500点步长 (价格每多跑 5美金，更新一次止损)
                        posMgr.ManageTrailingStop(m_symbol, m_magic_number, 1000, 1000, 500);
                     }
  };
//+------------------------------------------------------------------+
