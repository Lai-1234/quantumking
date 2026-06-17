//+------------------------------------------------------------------+
//|                                    CStrategy_Bands_Extreme.mqh   |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.10" // 升级为可优化版本

#include "CStrategy.mqh"

class CStrategy_Bands_Extreme : public CStrategy
  {
private:
   int               m_bb_handle;      
   int               m_bb_period;      
   double            m_bb_dev;         
   int               m_rsi_handle;     
   int               m_rsi_period;     // [新增] RSI 周期
   int               m_rsi_ob;         // [新增] RSI 超买线
   int               m_rsi_os;         // [新增] RSI 超卖线
   double            m_shadow_mult;    // [新增] 影线是实体的倍数

public:
                     // 【修改点】：把所有可以优化的参数放进构造函数里
                     CStrategy_Bands_Extreme(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf, 
                                             int bbPeriod = 20, 
                                             double bbDev = 2.5,
                                             int rsiPeriod = 14,
                                             int rsiOB = 80,
                                             int rsiOS = 20,
                                             double shadowMult = 1.5)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_bb_period = bbPeriod;
                        m_bb_dev = bbDev;
                        m_rsi_period = rsiPeriod;
                        m_rsi_ob = rsiOB;
                        m_rsi_os = rsiOS;
                        m_shadow_mult = shadowMult;
                        
                        m_bb_handle = iBands(m_symbol, m_timeframe, m_bb_period, 0, m_bb_dev, PRICE_CLOSE);
                        m_rsi_handle = iRSI(m_symbol, m_timeframe, m_rsi_period, PRICE_CLOSE);
                        
                        Print(m_strategy_name, " 优化模式加载 | BB:", m_bb_period, "(", m_bb_dev, 
                              ") | RSI:", m_rsi_period, "(", m_rsi_ob, "/", m_rsi_os, ") | 影线倍数:", m_shadow_mult);
                     }

                    ~CStrategy_Bands_Extreme(void)
                     {
                        IndicatorRelease(m_bb_handle);
                        IndicatorRelease(m_rsi_handle); 
                     }

   virtual double    CalculateSignal(void) override
                     {
                        double high[], low[], close[], open[], upper[], lower[], rsi[];
                        if(CopyHigh(m_symbol, m_timeframe, 1, 1, high) <= 0 || CopyLow(m_symbol, m_timeframe, 1, 1, low) <= 0 ||
                           CopyClose(m_symbol, m_timeframe, 1, 1, close) <= 0 || CopyOpen(m_symbol, m_timeframe, 1, 1, open) <= 0 ||
                           CopyBuffer(m_bb_handle, 1, 1, 1, upper) <= 0 || CopyBuffer(m_bb_handle, 2, 1, 1, lower) <= 0 ||
                           CopyBuffer(m_rsi_handle, 0, 1, 1, rsi) <= 0) return 0;

                        double body = MathAbs(close[0] - open[0]);
                        if(body == 0) body = 0.00001;
                        double upper_shadow = high[0] - MathMax(close[0], open[0]);
                        double lower_shadow = MathMin(close[0], open[0]) - low[0];

                        // 【修改点】：用变量 m_shadow_mult, m_rsi_ob, m_rsi_os 替代原本写死的 1.5, 80, 20
                        if(high[0] > upper[0] && close[0] < upper[0] && upper_shadow >= body * m_shadow_mult && rsi[0] > m_rsi_ob)
                           return -100.0;

                        if(low[0] < lower[0] && close[0] > lower[0] && lower_shadow >= body * m_shadow_mult && rsi[0] < m_rsi_os)
                           return 100.0;

                        return 0.0;
                     }

   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, m_timeframe, 0);
                        if(current_bar_time == last_bar_time) return;

                        double signal = CalculateSignal();
                        if(signal == 0.0) return; 

                       double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight); 
                        if(signal == 100.0 && posMgr.ExecuteOrder(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name))
                           last_bar_time = current_bar_time;
                        else if(signal == -100.0 && posMgr.ExecuteOrder(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name))
                           last_bar_time = current_bar_time;
                     }

   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        // 启动网格自救系统
                        posMgr.ManagePositions(m_symbol, m_magic_number);
                        //posMgr.ManageTrailingStop(m_symbol, m_magic_number, 300, 150);
                     }
  };