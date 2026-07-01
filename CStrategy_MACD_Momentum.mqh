//+------------------------------------------------------------------+
//|                                  CStrategy_MACD_Momentum.mqh     |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.10"

#include "CStrategy.mqh"

class CStrategy_MACD_Momentum : public CStrategy
  {
private:
   int               m_ema50_h1;
   int               m_ema200_h1;
   int               m_ema50_h4;
   int               m_ema200_h4;
   int               m_macd_handle;

   int               m_fast_ema;
   int               m_slow_ema;
   int               m_signal_sma;
   int               m_sl_buffer_pts;
   int               m_max_sl_pts;

   bool              m_use_session_filter;
   int               m_session1_start, m_session1_end;
   int               m_session2_start, m_session2_end;

   bool              PassSessionFilter(void)
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
                     CStrategy_MACD_Momentum(string name,
                                             int magic,
                                             double weight,
                                             string symbol,
                                             ENUM_TIMEFRAMES tf,
                                             int fastEMA = 12,
                                             int slowEMA = 26,
                                             int signalSMA = 9,
                                             int slBufferPts = 150,
                                             int maxSlPts = 800)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_fast_ema      = fastEMA;
                        m_slow_ema      = slowEMA;
                        m_signal_sma    = signalSMA;
                        m_sl_buffer_pts = slBufferPts;
                        m_max_sl_pts    = maxSlPts;

                        m_ema50_h1  = iMA(m_symbol, PERIOD_H1, 50, 0, MODE_EMA, PRICE_CLOSE);
                        m_ema200_h1 = iMA(m_symbol, PERIOD_H1, 200, 0, MODE_EMA, PRICE_CLOSE);
                        m_ema50_h4  = iMA(m_symbol, PERIOD_H4, 50, 0, MODE_EMA, PRICE_CLOSE);
                        m_ema200_h4 = iMA(m_symbol, PERIOD_H4, 200, 0, MODE_EMA, PRICE_CLOSE);

                        m_macd_handle = iMACD(m_symbol, m_timeframe, m_fast_ema, m_slow_ema, m_signal_sma, PRICE_CLOSE);

                        m_use_session_filter = true;
                        m_session1_start = 9;  m_session1_end = 12;
                        m_session2_start = 14; m_session2_end = 17;

                        Print(m_strategy_name,
                              " v1.10 | MACD(", m_fast_ema, ",", m_slow_ema, ",", m_signal_sma, ")",
                              " | SL buf=", m_sl_buffer_pts, " MaxSL=", m_max_sl_pts,
                              " | H1/H4 EMA 50/200 ON | Session 9-12/14-17 ON | TP=10000 Trail=OFF");
                     }

                    ~CStrategy_MACD_Momentum(void)
                     {
                        if(m_ema50_h1 != INVALID_HANDLE) IndicatorRelease(m_ema50_h1);
                        if(m_ema200_h1 != INVALID_HANDLE) IndicatorRelease(m_ema200_h1);
                        if(m_ema50_h4 != INVALID_HANDLE) IndicatorRelease(m_ema50_h4);
                        if(m_ema200_h4 != INVALID_HANDLE) IndicatorRelease(m_ema200_h4);
                        if(m_macd_handle != INVALID_HANDLE) IndicatorRelease(m_macd_handle);
                     }

   virtual double    CalculateSignal(void) override
                     {
                        double e50h1[], e200h1[], e50h4[], e200h4[];
                        double macd_main[], macd_signal[];

                        if(CopyBuffer(m_ema50_h1, 0, 1, 1, e50h1) <= 0 ||
                           CopyBuffer(m_ema200_h1, 0, 1, 1, e200h1) <= 0 ||
                           CopyBuffer(m_ema50_h4, 0, 1, 1, e50h4) <= 0 ||
                           CopyBuffer(m_ema200_h4, 0, 1, 1, e200h4) <= 0 ||
                           CopyBuffer(m_macd_handle, MAIN_LINE, 1, 3, macd_main) <= 0 ||
                           CopyBuffer(m_macd_handle, SIGNAL_LINE, 1, 3, macd_signal) <= 0) return 0.0;

                        bool is_Bullish_MTF = (e50h4[0] > e200h4[0]) && (e50h1[0] > e200h1[0]);
                        bool is_Bearish_MTF = (e50h4[0] < e200h4[0]) && (e50h1[0] < e200h1[0]);

                        double hist_current = macd_main[0] - macd_signal[0];
                        double hist_prev    = macd_main[1] - macd_signal[1];

                        if(!PassSessionFilter()) return 0.0;

                        if(is_Bullish_MTF)
                          {
                           if(macd_main[1] <= 0 && macd_main[0] > 0 && hist_current > 0 && hist_current > hist_prev)
                             {
                              Print("[MACD Momentum BUY] H1/H4 bullish, MACD crossed above zero with expanding histogram");
                              return 100.0;
                             }
                          }

                        if(is_Bearish_MTF)
                          {
                           if(macd_main[1] >= 0 && macd_main[0] < 0 && hist_current < 0 && hist_current < hist_prev)
                             {
                              Print("[MACD Momentum SELL] H1/H4 bearish, MACD crossed below zero with expanding histogram");
                              return -100.0;
                             }
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
                        double dynamic_sl_pts = 0.0;
                        bool is_opened = false;

                        if(signal == 100.0)
                           dynamic_sl_pts = (current_price - swing_low) / point + m_sl_buffer_pts;
                        else if(signal == -100.0)
                           dynamic_sl_pts = (swing_high - current_price) / point + m_sl_buffer_pts;

                        if(dynamic_sl_pts <= 0.0) return;

                        if(m_max_sl_pts > 0 && dynamic_sl_pts > m_max_sl_pts)
                          {
                           Print(m_strategy_name, " skip: structural SL ", dynamic_sl_pts,
                                 "pts exceeds Max_SL ", m_max_sl_pts, "pts");
                           last_bar_time = current_bar_time;
                           return;
                          }

                        long stop_level_pts = SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
                        long spread_pts      = SymbolInfoInteger(m_symbol, SYMBOL_SPREAD);
                        if(dynamic_sl_pts < stop_level_pts + spread_pts)
                          {
                           Print(m_strategy_name, " skip: SL ", dynamic_sl_pts,
                                 "pts violates broker stop level ", stop_level_pts, " + spread ", spread_pts);
                           last_bar_time = current_bar_time;
                           return;
                          }

                        if(signal == 100.0)
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                        else if(signal == -100.0)
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);

                        if(is_opened) last_bar_time = current_bar_time;
                     }

   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        posMgr.ManageTrailingStop(m_symbol, m_magic_number, 50000, 50000, 1000);
                     }
  };
//+------------------------------------------------------------------+
