//+------------------------------------------------------------------+
//|                                     CStrategy_ADX_Trend.mqh      |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.12"

#include "CStrategy.mqh"

class CStrategy_ADX_Trend : public CStrategy
  {
private:
   int               m_adx_handle;
   int               m_adx_period;
   double            m_adx_threshold;
   int               m_sl_buffer_pts;
   int               m_max_sl_pts;
   bool              m_use_h4_filter;
   int               m_h4_fast_ema_handle;
   int               m_h4_slow_ema_handle;
   bool              m_require_rising_adx;
   bool              m_use_session_filter;
   int               m_session1_start, m_session1_end;
   int               m_session2_start, m_session2_end;

   bool              IsEmaDirectionAligned(int fastHandle, int slowHandle, double signal)
                     {
                        double fast[], slow[];
                        if(CopyBuffer(fastHandle, 0, 1, 1, fast) <= 0 ||
                           CopyBuffer(slowHandle, 0, 1, 1, slow) <= 0) return false;

                        if(signal == 100.0) return (fast[0] > slow[0]);
                        if(signal == -100.0) return (fast[0] < slow[0]);
                        return false;
                     }

   bool              IsMtfAligned(double signal)
                     {
                        if(!IsEmaDirectionAligned(m_h4_fast_ema_handle, m_h4_slow_ema_handle, signal))
                           return false;
                        return true;
                     }

   bool              PassSessionFilter()
                     {
                        if(!m_use_session_filter) return true;
                        MqlDateTime t;
                        TimeToStruct(TimeCurrent(), t);
                        int h = t.hour;
                        if(h >= m_session1_start && h < m_session1_end) return true;
                        if(h >= m_session2_start && h < m_session2_end) return true;
                        return false;
                     }

public:
                     CStrategy_ADX_Trend(string name,
                                         int magic,
                                         double weight,
                                         string symbol,
                                         ENUM_TIMEFRAMES tf,
                                         int adxPeriod = 13,
                                         double adxThreshold = 32.5,
                                         int slBufferPts = 50,
                                         int maxSlPts = 1300,
                                         bool requireRising = true)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_adx_period         = adxPeriod;
                        m_adx_threshold      = adxThreshold;
                        m_sl_buffer_pts      = slBufferPts;
                        m_max_sl_pts         = maxSlPts;
                        m_require_rising_adx = requireRising;

                        m_adx_handle = iADX(m_symbol, m_timeframe, m_adx_period);

                        m_use_h4_filter      = true;
                        m_h4_fast_ema_handle = iMA(m_symbol, PERIOD_H4, 50,  0, MODE_EMA, PRICE_CLOSE);
                        m_h4_slow_ema_handle = iMA(m_symbol, PERIOD_H4, 200, 0, MODE_EMA, PRICE_CLOSE);

                        m_use_session_filter = true;
                        m_session1_start = 9;  m_session1_end = 12;
                        m_session2_start = 14; m_session2_end = 17;

                        Print(m_strategy_name,
                              " v1.12 | ADX(", m_adx_period, ")>", m_adx_threshold,
                              " Rising=", m_require_rising_adx,
                              " | SL buf=", m_sl_buffer_pts, " MaxSL=", m_max_sl_pts,
                              " | H4 EMA 50/200 ON | Session 9-12/14-17 ON | TP=10000 Trail=OFF");
                     }

                    ~CStrategy_ADX_Trend(void)
                     {
                        if(m_adx_handle != INVALID_HANDLE) IndicatorRelease(m_adx_handle);
                        if(m_h4_fast_ema_handle != INVALID_HANDLE) IndicatorRelease(m_h4_fast_ema_handle);
                        if(m_h4_slow_ema_handle != INVALID_HANDLE) IndicatorRelease(m_h4_slow_ema_handle);
                     }

   virtual double    CalculateSignal(void) override
                     {
                        double adx_main[], plus_di[], minus_di[];

                        if(CopyBuffer(m_adx_handle, 0, 1, 2, adx_main) <= 0 ||
                           CopyBuffer(m_adx_handle, 1, 1, 2, plus_di) <= 0 ||
                           CopyBuffer(m_adx_handle, 2, 1, 2, minus_di) <= 0) return 0.0;

                        if(adx_main[0] < m_adx_threshold) return 0.0;
                        if(m_require_rising_adx && adx_main[0] <= adx_main[1]) return 0.0;

                        if(plus_di[0] > minus_di[0] && plus_di[1] <= minus_di[1])
                          {
                           if(!IsMtfAligned(100.0)) return 0.0;
                           if(!PassSessionFilter()) return 0.0;
                           Print("[ADX Trend BUY] ADX=", adx_main[0], " +DI crossed above -DI");
                           return 100.0;
                          }

                        if(minus_di[0] > plus_di[0] && minus_di[1] <= plus_di[1])
                          {
                           if(!IsMtfAligned(-100.0)) return 0.0;
                           if(!PassSessionFilter()) return 0.0;
                           Print("[ADX Trend SELL] ADX=", adx_main[0], " -DI crossed above +DI");
                           return -100.0;
                          }

                        return 0.0;
                     }

   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, m_timeframe, 0);
                        if(current_bar_time == last_bar_time) return;

                        double signal = CalculateSignal();
                        if(signal == 0.0) return;

                        double high_arr[], low_arr[];
                        if(CopyHigh(m_symbol, m_timeframe, 1, 50, high_arr) <= 0 ||
                           CopyLow(m_symbol, m_timeframe, 1, 50, low_arr) <= 0) return;

                        double swing_high = high_arr[ArrayMaximum(high_arr)];
                        double swing_low  = low_arr[ArrayMinimum(low_arr)];
                        double current_price = (signal == 100.0) ? SymbolInfoDouble(m_symbol, SYMBOL_ASK) : SymbolInfoDouble(m_symbol, SYMBOL_BID);
                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
                        double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight);
                        bool is_opened = false;

                        if(signal == 100.0)
                          {
                           double dynamic_sl_pts = (current_price - swing_low) / point + m_sl_buffer_pts;
                           if(m_max_sl_pts > 0 && dynamic_sl_pts > m_max_sl_pts) dynamic_sl_pts = m_max_sl_pts;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                          }
                        else if(signal == -100.0)
                          {
                           double dynamic_sl_pts = (swing_high - current_price) / point + m_sl_buffer_pts;
                           if(m_max_sl_pts > 0 && dynamic_sl_pts > m_max_sl_pts) dynamic_sl_pts = m_max_sl_pts;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                          }

                        if(is_opened) last_bar_time = current_bar_time;
                     }

   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        posMgr.ManageTrailingStop(m_symbol, m_magic_number, 50000, 50000, 1000);
                     }
  };
//+------------------------------------------------------------------+
