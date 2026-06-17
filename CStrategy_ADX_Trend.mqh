//+------------------------------------------------------------------+
//|                                     CStrategy_ADX_Trend.mqh      |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.10"

#include "CStrategy.mqh"

class CStrategy_ADX_Trend : public CStrategy
  {
private:
   int               m_adx_handle;
   int               m_adx_period;
   double            m_adx_threshold;
   int               m_sl_buffer_pts;
   int               m_max_sl_pts;
   int               m_tp_pts;
   int               m_trail_activation_pts;
   int               m_trail_distance_pts;
   int               m_trail_step_pts;
   bool              m_use_h1_filter;
   bool              m_use_h4_filter;
   int               m_h1_fast_ema_handle;
   int               m_h1_slow_ema_handle;
   int               m_h4_fast_ema_handle;
   int               m_h4_slow_ema_handle;

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
                        if(m_use_h1_filter && !IsEmaDirectionAligned(m_h1_fast_ema_handle, m_h1_slow_ema_handle, signal))
                           return false;

                        if(m_use_h4_filter && !IsEmaDirectionAligned(m_h4_fast_ema_handle, m_h4_slow_ema_handle, signal))
                           return false;

                        return true;
                     }

public:
                     CStrategy_ADX_Trend(string name,
                                         int magic,
                                         double weight,
                                         string symbol,
                                         ENUM_TIMEFRAMES tf,
                                         int adxPeriod = 14,
                                         double adxThreshold = 25.0,
                                         int slBufferPts = 150,
                                         int maxSlPts = 0,
                                         int tpPts = 10000,
                                         int trailActivationPts = 1000,
                                         int trailDistancePts = 1000,
                                         int trailStepPts = 500,
                                         bool useH1Filter = false,
                                         bool useH4Filter = false,
                                         int h1FastEma = 50,
                                         int h1SlowEma = 200,
                                         int h4FastEma = 50,
                                         int h4SlowEma = 200)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_adx_period = adxPeriod;
                        m_adx_threshold = adxThreshold;
                        m_sl_buffer_pts = slBufferPts;
                        m_max_sl_pts = maxSlPts;
                        m_tp_pts = tpPts;
                        m_trail_activation_pts = trailActivationPts;
                        m_trail_distance_pts = trailDistancePts;
                        m_trail_step_pts = trailStepPts;
                        m_use_h1_filter = useH1Filter;
                        m_use_h4_filter = useH4Filter;

                        m_adx_handle = iADX(m_symbol, m_timeframe, m_adx_period);
                        m_h1_fast_ema_handle = INVALID_HANDLE;
                        m_h1_slow_ema_handle = INVALID_HANDLE;
                        m_h4_fast_ema_handle = INVALID_HANDLE;
                        m_h4_slow_ema_handle = INVALID_HANDLE;

                        if(m_use_h1_filter)
                          {
                           m_h1_fast_ema_handle = iMA(m_symbol, PERIOD_H1, h1FastEma, 0, MODE_EMA, PRICE_CLOSE);
                           m_h1_slow_ema_handle = iMA(m_symbol, PERIOD_H1, h1SlowEma, 0, MODE_EMA, PRICE_CLOSE);
                          }

                        if(m_use_h4_filter)
                          {
                           m_h4_fast_ema_handle = iMA(m_symbol, PERIOD_H4, h4FastEma, 0, MODE_EMA, PRICE_CLOSE);
                           m_h4_slow_ema_handle = iMA(m_symbol, PERIOD_H4, h4SlowEma, 0, MODE_EMA, PRICE_CLOSE);
                          }

                        Print(m_strategy_name,
                              " ADX tunable loaded | ADX>", m_adx_threshold,
                              " | SL buffer=", m_sl_buffer_pts,
                              " | MaxSL=", m_max_sl_pts,
                              " | TP=", m_tp_pts,
                              " | Trail=", m_trail_activation_pts, "/", m_trail_distance_pts, "/", m_trail_step_pts,
                              " | H1/H4=", m_use_h1_filter, "/", m_use_h4_filter);
                     }

                    ~CStrategy_ADX_Trend(void)
                     {
                        if(m_adx_handle != INVALID_HANDLE) IndicatorRelease(m_adx_handle);
                        if(m_h1_fast_ema_handle != INVALID_HANDLE) IndicatorRelease(m_h1_fast_ema_handle);
                        if(m_h1_slow_ema_handle != INVALID_HANDLE) IndicatorRelease(m_h1_slow_ema_handle);
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

                        if(plus_di[0] > minus_di[0] && plus_di[1] <= minus_di[1])
                          {
                           if(!IsMtfAligned(100.0)) return 0.0;
                           Print("[ADX Trend BUY] ADX=", adx_main[0], " +DI crossed above -DI");
                           return 100.0;
                          }

                        if(minus_di[0] > plus_di[0] && minus_di[1] <= plus_di[1])
                          {
                           if(!IsMtfAligned(-100.0)) return 0.0;
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
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, m_tp_pts);
                          }
                        else if(signal == -100.0)
                          {
                           double dynamic_sl_pts = (swing_high - current_price) / point + m_sl_buffer_pts;
                           if(m_max_sl_pts > 0 && dynamic_sl_pts > m_max_sl_pts) dynamic_sl_pts = m_max_sl_pts;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, m_tp_pts);
                          }

                        if(is_opened) last_bar_time = current_bar_time;
                     }

   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        posMgr.ManageTrailingStop(m_symbol, m_magic_number, m_trail_activation_pts, m_trail_distance_pts, m_trail_step_pts);
                     }
  };
//+------------------------------------------------------------------+
