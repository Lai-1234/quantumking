//+------------------------------------------------------------------+
//|                                         CStrategy_MA_Trend.mqh   |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "3.30" // 最优参数版：Fast10 / Slow40 / Trail1400/100
 
#include "CStrategy.mqh"
 
class CStrategy_MA_Trend : public CStrategy
  {
private:
   int    m_stoch_handle;
   int    m_ema50_h4, m_ema200_h4;
   int    m_stoch_ob, m_stoch_os;
 
   double m_fibo_top;
   double m_fibo_bottom;
   int    m_zone_buffer;
   int    m_sl_buffer;
   int    m_max_sl;
   int    m_trail_start;
   int    m_trail_step;
 
public:
   // ======================================================================
   // 默认值 = 优化器最优结果 (Fast10 / Slow40 / Trail1400 / Step100)
   // ⚠️ 不要直接改这里的数字，统一在 quantumking.mq5 的 input 区修改
   // ======================================================================
   CStrategy_MA_Trend(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf,
                      int    stochOB      = 70,
                      int    stochOS      = 40,
                      int    fastEMA      = 20,    // ✅ 优化后：10
                      int    slowEMA      = 70,    // ✅ 优化后：40
                      int    kdj_period   = 7,
                      int    kdj_d        = 2,
                      int    kdj_s        = 2,
                      double fibo_top     = 0.5,
                      double fibo_bottom  = 0.677,
                      int    zone_buf     = 150,
                      int    sl_buf       = 300,
                      int    max_sl       = 800,
                      int    trail_start  = 1400,  // ✅ 优化后：1400
                      int    trail_step   = 100)   // ✅ 优化后：100
   : CStrategy(name, magic, weight, symbol, tf)
     {
      m_stoch_ob     = stochOB;
      m_stoch_os     = stochOS;
      m_fibo_top     = fibo_top;
      m_fibo_bottom  = fibo_bottom;
      m_zone_buffer  = zone_buf;
      m_sl_buffer    = sl_buf;
      m_max_sl       = max_sl;
      m_trail_start  = trail_start;
      m_trail_step   = trail_step;
 
      m_ema50_h4  = iMA(m_symbol, PERIOD_H4, fastEMA, 0, MODE_EMA, PRICE_CLOSE);
      m_ema200_h4 = iMA(m_symbol, PERIOD_H4, slowEMA, 0, MODE_EMA, PRICE_CLOSE);
 
      m_stoch_handle = iStochastic(m_symbol, PERIOD_M15, kdj_period, kdj_d, kdj_s, MODE_SMA, STO_LOWHIGH);
 
      Print(m_strategy_name, " 已加载最优参数 | EMA:", fastEMA, "/", slowEMA,
            " | KDJ:", kdj_period, "(", kdj_d, ",", kdj_s, ")",
            " | OB/OS:", stochOB, "/", stochOS,
            " | Fibo:", fibo_top, "-", fibo_bottom,
            " | Trail:", trail_start, "/", trail_step);
     }
 
  ~CStrategy_MA_Trend(void)
     {
      IndicatorRelease(m_ema50_h4);
      IndicatorRelease(m_ema200_h4);
      IndicatorRelease(m_stoch_handle);
     }
 
   virtual double CalculateSignal(void) override
     {
      double e50h4[], e200h4[], sm[], ss[];
 
      if(CopyBuffer(m_ema50_h4,  0, 1, 1, e50h4)  <= 0 ||
         CopyBuffer(m_ema200_h4, 0, 1, 1, e200h4) <= 0 ||
         CopyBuffer(m_stoch_handle, 0, 1, 3, sm)  <= 0 ||
         CopyBuffer(m_stoch_handle, 1, 1, 3, ss)  <= 0) return 0;
 
      bool bullish = (e50h4[0] > e200h4[0]);
      bool bearish = (e50h4[0] < e200h4[0]);
 
      bool kdj_buy  = (sm[1] < m_stoch_os && sm[1] > ss[1] && sm[2] <= ss[2]);
      bool kdj_sell = (sm[1] > m_stoch_ob && sm[1] < ss[1] && sm[2] >= ss[2]);
 
      if(bullish && kdj_buy)  return  100.0;
      if(bearish && kdj_sell) return -100.0;
 
      return 0.0;
     }
 
   virtual void CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
     {
      static datetime last_bar_time = 0;
      if(iTime(m_symbol, m_timeframe, 0) == last_bar_time) return;
 
      double signal = CalculateSignal();
      if(signal == 0.0) return;
 
      double high_arr[], low_arr[], open_arr[], close_arr[];
      ArraySetAsSeries(high_arr,  true);
      ArraySetAsSeries(low_arr,   true);
      ArraySetAsSeries(open_arr,  true);
      ArraySetAsSeries(close_arr, true);
 
      if(CopyHigh(m_symbol,  m_timeframe, 0, 100, high_arr)  <= 0 ||
         CopyLow(m_symbol,   m_timeframe, 0, 100, low_arr)   <= 0 ||
         CopyOpen(m_symbol,  m_timeframe, 0, 1,   open_arr)  <= 0 ||
         CopyClose(m_symbol, m_timeframe, 0, 1,   close_arr) <= 0) return;
 
      double swH = 0, swL = 0, wave = 0;
      int    idx_H = 0, idx_L = 0;
 
      if(signal == 100.0)
        {
         idx_H = ArrayMaximum(high_arr, 1, 50);
         idx_L = ArrayMinimum(low_arr, idx_H, 100 - idx_H);
         swH = high_arr[idx_H]; swL = low_arr[idx_L];
        }
      else if(signal == -100.0)
        {
         idx_L = ArrayMinimum(low_arr, 1, 50);
         idx_H = ArrayMaximum(high_arr, idx_L, 100 - idx_L);
         swH = high_arr[idx_H]; swL = low_arr[idx_L];
        }
 
      wave = swH - swL;
      if(wave < 1.0) return;
 
      double price = (signal == 100.0)
                     ? SymbolInfoDouble(m_symbol, SYMBOL_ASK)
                     : SymbolInfoDouble(m_symbol, SYMBOL_BID);
      double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
 
      double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight);
      bool   ok       = false;
      bool   touched  = false;
 
      if(signal == 100.0)
        {
         double zone_top    = swH - wave * m_fibo_top    + m_zone_buffer * point;
         double zone_bottom = swH - wave * m_fibo_bottom - m_zone_buffer * point;
 
         for(int i = 0; i <= 3; i++)
           {
            if(low_arr[i] <= zone_top && low_arr[i] >= zone_bottom)
              { touched = true; break; }
           }
 
         if(touched)
           {
            double sl_pts = (price - swL) / point + m_sl_buffer;
            if(sl_pts > m_max_sl) sl_pts = m_max_sl;
            ok = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot,
                                             m_magic_number, m_strategy_name, sl_pts, 10000);
            Print("🎯 [H4多头] Fibo触碰，买入！SL=", sl_pts, "pts");
           }
        }
      else if(signal == -100.0)
        {
         double zone_bottom = swL + wave * m_fibo_top    - m_zone_buffer * point;
         double zone_top    = swL + wave * m_fibo_bottom + m_zone_buffer * point;
 
         for(int i = 0; i <= 3; i++)
           {
            if(high_arr[i] >= zone_bottom && high_arr[i] <= zone_top)
              { touched = true; break; }
           }
 
         if(touched)
           {
            double sl_pts = (swH - price) / point + m_sl_buffer;
            if(sl_pts > m_max_sl) sl_pts = m_max_sl;
            ok = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot,
                                             m_magic_number, m_strategy_name, sl_pts, 10000);
            Print("🎯 [H4空头] Fibo触碰，卖出！SL=", sl_pts, "pts");
           }
        }
 
      if(ok) last_bar_time = iTime(m_symbol, m_timeframe, 0);
     }
 
   virtual void CheckExit(CPositionManager *posMgr) override
     {
      // EMA 是趋势波段，需要极大的呼吸空间，所以启动和距离都是 m_trail_start (1400)
      posMgr.ManageTrailingStop(m_symbol, m_magic_number, m_trail_start, m_trail_start, m_trail_step);
     }
  };
//+------------------------------------------------------------------+