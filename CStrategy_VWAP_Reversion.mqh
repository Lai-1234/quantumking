//+------------------------------------------------------------------+
//|                            CStrategy_VWAP_Reversion.mqh          |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.00"

#include "CStrategy.mqh"

class CStrategy_VWAP_Reversion : public CStrategy
  {
private:
   double            m_std_dev_multiplier; // 第三标准差乘数

public:
                     // 严格蓝图：锁定 3.0 倍极值标准差
                     CStrategy_VWAP_Reversion(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf,
                                              double stdDevMultiplier = 3.0)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_std_dev_multiplier = stdDevMultiplier;
                        Print(m_strategy_name, " VWAP 极值反转部队已就位 (锚定每日开盘 + ", m_std_dev_multiplier, " 标准差)");
                     }

                    ~CStrategy_VWAP_Reversion(void) {}

   //========================================================================
   // 核心逻辑 6：日内 VWAP 动态计算引擎 + 第三标准差极值刺破检测
   //========================================================================
   virtual double    CalculateSignal(void) override
                     {
                        // 1. 定位今天的开盘时间，计算今天已经走过了多少根 K 线
                        datetime day_start = iTime(m_symbol, PERIOD_D1, 0); 
                        int bars_today = iBarShift(m_symbol, m_timeframe, day_start);
                        
                        // 刚开盘前几个小时 VWAP 和标准差极度不稳定，给它 1 个小时 (4根M15) 的数据积累期
                        if(bars_today < 4) return 0.0; 

                        // 2. 提取今天所有的价格和成交量数据
                        double high[], low[], close[], open[];
                        long vol[];
                        ArraySetAsSeries(high, true); ArraySetAsSeries(low, true); 
                        ArraySetAsSeries(close, true); ArraySetAsSeries(vol, true);

                        if(CopyHigh(m_symbol, m_timeframe, 1, bars_today, high) <= 0 || 
                           CopyLow(m_symbol, m_timeframe, 1, bars_today, low) <= 0 || 
                           CopyClose(m_symbol, m_timeframe, 1, bars_today, close) <= 0 || 
                           CopyOpen(m_symbol, m_timeframe, 1, 1, open) <= 0 || // 只需要最新一根的开盘价算实体
                           CopyTickVolume(m_symbol, m_timeframe, 1, bars_today, vol) <= 0) return 0;

                        // 3. 计算日内 VWAP (成交量加权平均价)
                        double sum_pv = 0.0;
                        double sum_v = 0.0;
                        double tp_arr[];
                        ArrayResize(tp_arr, bars_today);

                        for(int i = 0; i < bars_today; i++)
                          {
                           tp_arr[i] = (high[i] + low[i] + close[i]) / 3.0; // 典型价格 (Typical Price)
                           sum_pv += tp_arr[i] * (double)vol[i];
                           sum_v += (double)vol[i];
                          }
                        if(sum_v == 0) return 0.0;
                        double vwap = sum_pv / sum_v;

                        // 4. 计算 VWAP 标准差 (Variance & Standard Deviation)
                        double sum_dev = 0.0;
                        for(int i = 0; i < bars_today; i++)
                          {
                           sum_dev += (double)vol[i] * MathPow(tp_arr[i] - vwap, 2);
                          }
                        double variance = sum_dev / sum_v;
                        double std_dev = MathSqrt(variance);

                        // 5. 构筑极限轨道 (第三标准差)
                        double upper_band = vwap + m_std_dev_multiplier * std_dev;
                        double lower_band = vwap - m_std_dev_multiplier * std_dev;

                        // 6. 形态甄别：获取刚刚收盘这根 K 线的实体和影线
                        double body = MathAbs(close[0] - open[0]);
                        if(body == 0) body = 0.00001;
                        double upper_shadow = high[0] - MathMax(close[0], open[0]);
                        double lower_shadow = MathMin(close[0], open[0]) - low[0];

                        // 【做空极值反转】：刺破第三标准差上轨 + 收回轨内 + 上影线是实体的1.5倍
                        if(high[0] > upper_band && close[0] < upper_band && upper_shadow >= body * 1.5)
                          {
                           Print("🟢 [VWAP极值摸顶] 价格刺破 VWAP 第 ", m_std_dev_multiplier, " 标准差上轨(", upper_band, ")！橡皮筋崩紧，执行做空回归！");
                           return -100.0;
                          }

                        // 【做多极值反转】：跌穿第三标准差下轨 + 收回轨内 + 下影线是实体的1.5倍
                        if(low[0] < lower_band && close[0] > lower_band && lower_shadow >= body * 1.5)
                          {
                           Print("🔴 [VWAP极值抄底] 价格跌穿 VWAP 第 ", m_std_dev_multiplier, " 标准差下轨(", lower_band, ")！橡皮筋崩紧，执行做多回归！");
                           return 100.0;
                          }

                        return 0.0;
                     }

   //========================================================================
   // 进场：极值接针，第二类部队的标准免死金牌
   //========================================================================
   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, m_timeframe, 0);
                        if(current_bar_time == last_bar_time) return;

                        double signal = CalculateSignal();
                        if(signal == 0.0) return; 

                        double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight); 
                        bool is_opened = false;

                        if(signal == 100.0)
                           is_opened = posMgr.ExecuteOrder(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name + " 首单(多)");
                        else if(signal == -100.0)
                           is_opened = posMgr.ExecuteOrder(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name + " 首单(空)");

                        if(is_opened) last_bar_time = current_bar_time;
                     }

   //========================================================================
   // 退出：调用大脑的网格自救系统
   //========================================================================
   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        // 均值回归阵营标志：使用网格系统进行兜底与止盈
                        posMgr.ManagePositions(m_symbol, m_magic_number);
                        //posMgr.ManageTrailingStop(m_symbol, m_magic_number, 300, 150);
                     }
  };
//+------------------------------------------------------------------+