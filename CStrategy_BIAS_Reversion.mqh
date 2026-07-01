//+------------------------------------------------------------------+
//|                                  CStrategy_BIAS_Reversion.mqh    |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.00"

#include "CStrategy.mqh"

// v1.00 — experimental low-vol-range mean-reversion strategy.
// Disabled by default, QK_PRESET_CUSTOM only. No locked strategy affected.
// Structural SL/TP (ADX_Trend template), NOT the grid-reliant pattern used by
// the dropped VWAP_Reversion/Bands_Extreme/Pivot_Divergence strategies.
class CStrategy_BIAS_Reversion : public CStrategy
  {
private:
   int               m_ma_handle;
   int               m_kdj_handle;
   int               m_adx_handle;

   double            m_threshold_pct;
   int               m_sl_buffer_pts;
   int               m_max_sl_pts;
   int               m_tp_pts;
   int               m_swing_lookback;

   bool              m_use_kdj_filter;
   int               m_kdj_lookback_bars;
   int               m_kdj_ob, m_kdj_os;

   bool              m_use_adx_max_filter;
   double            m_adx_max;

   bool              m_use_session_filter;
   int               m_session1_start, m_session1_end;
   int               m_session2_start, m_session2_end;

   // KDJ confirmation: require an OB/OS extreme within the lookback window,
   // not necessarily on the current bar (by the time BIAS crosses back, KDJ
   // may have already left the extreme zone).
   bool              PassKdjFilter(double signal)
                     {
                        double kdj_arr[];
                        if(CopyBuffer(m_kdj_handle, 0, 1, m_kdj_lookback_bars, kdj_arr) <= 0) return true;
                        for(int i = 0; i < ArraySize(kdj_arr); i++)
                          {
                           if(signal == 100.0  && kdj_arr[i] < m_kdj_os) return true;
                           if(signal == -100.0 && kdj_arr[i] > m_kdj_ob) return true;
                          }
                        return false;
                     }

   // Pure toggle — regime gate already restricts to LOW_VOL_RANGE, so this
   // may be redundant/over-filtering. Left to optimization to decide.
   bool              PassAdxMaxFilter(void)
                     {
                        double adx_arr[];
                        if(CopyBuffer(m_adx_handle, 0, 1, 1, adx_arr) <= 0) return true;
                        return (adx_arr[0] < m_adx_max);
                     }

   // Default OFF — the 9-12/14-17 window is proven for trend strategies
   // (SMC/ADX), not for range conditions. Test ON vs OFF before assuming it transfers.
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
                     // IMPORTANT: The substring "回归" in this strategy's name is required by
                     // CStrategyManager's regime router (StringFind(name, "回归")). Do not rename
                     // without also updating CStrategyManager::OnTick's routing logic.
                     CStrategy_BIAS_Reversion(string name,
                                              int magic,
                                              double weight,
                                              string symbol,
                                              ENUM_TIMEFRAMES tf,
                                              int maPeriod = 50,
                                              double thresholdPct = 0.5,
                                              int slBufferPts = 50,
                                              int maxSlPts = 500,
                                              int tpPts = 2000,
                                              int swingLookback = 50,
                                              bool useKdjFilter = false,
                                              int kdjLookbackBars = 3,
                                              bool useAdxMaxFilter = false,
                                              double adxMax = 22.0,
                                              bool useSessionFilter = false)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_threshold_pct      = thresholdPct;
                        m_sl_buffer_pts      = slBufferPts;
                        m_max_sl_pts         = maxSlPts;
                        m_tp_pts             = tpPts;
                        m_swing_lookback     = swingLookback;

                        m_use_kdj_filter     = useKdjFilter;
                        m_kdj_lookback_bars  = kdjLookbackBars;
                        m_kdj_ob             = 70;
                        m_kdj_os             = 30;

                        m_use_adx_max_filter = useAdxMaxFilter;
                        m_adx_max            = adxMax;

                        m_use_session_filter = useSessionFilter;
                        m_session1_start = 9;  m_session1_end = 12;
                        m_session2_start = 14; m_session2_end = 17;

                        m_ma_handle  = iMA(m_symbol, m_timeframe, maPeriod, 0, MODE_EMA, PRICE_CLOSE);
                        m_kdj_handle = iStochastic(m_symbol, m_timeframe, 7, 2, 2, MODE_SMA, STO_LOWHIGH);
                        m_adx_handle = iADX(m_symbol, m_timeframe, 14);

                        Print(m_strategy_name,
                              " v1.00 | BIAS MA(", maPeriod, ") thr=", m_threshold_pct, "%",
                              " | SL buf=", m_sl_buffer_pts, " MaxSL=", m_max_sl_pts, " TP=", m_tp_pts,
                              " | KDJ=", m_use_kdj_filter, " ADXmax=", m_use_adx_max_filter, "(<", m_adx_max, ")",
                              " Session=", m_use_session_filter, " | EXPERIMENTAL, not locked");
                     }

                    ~CStrategy_BIAS_Reversion(void)
                     {
                        if(m_ma_handle != INVALID_HANDLE)  IndicatorRelease(m_ma_handle);
                        if(m_kdj_handle != INVALID_HANDLE) IndicatorRelease(m_kdj_handle);
                        if(m_adx_handle != INVALID_HANDLE) IndicatorRelease(m_adx_handle);
                     }

   virtual double    CalculateSignal(void) override
                     {
                        double ma_arr[];
                        if(CopyBuffer(m_ma_handle, 0, 1, 2, ma_arr) <= 0) return 0.0;

                        double close1 = iClose(m_symbol, m_timeframe, 1); // last closed bar
                        double close2 = iClose(m_symbol, m_timeframe, 2); // second-to-last closed bar
                        if(close1 <= 0 || close2 <= 0 || ma_arr[0] <= 0 || ma_arr[1] <= 0) return 0.0;

                        double bias_curr = (close1 - ma_arr[0]) / ma_arr[0] * 100.0; // bar 1
                        double bias_prev = (close2 - ma_arr[1]) / ma_arr[1] * 100.0; // bar 2

                        double signal = 0.0;
                        if(bias_prev <= -m_threshold_pct && bias_curr > -m_threshold_pct)
                           signal = 100.0;  // was oversold, reverting up
                        else if(bias_prev >= m_threshold_pct && bias_curr < m_threshold_pct)
                           signal = -100.0; // was overbought, reverting down

                        if(signal == 0.0) return 0.0;

                        if(m_use_kdj_filter && !PassKdjFilter(signal)) return 0.0;
                        if(m_use_adx_max_filter && !PassAdxMaxFilter()) return 0.0;
                        if(!PassSessionFilter()) return 0.0;

                        Print("[BIAS Reversion ", (signal > 0 ? "BUY" : "SELL"), "] bias_prev=", bias_prev,
                              " bias_curr=", bias_curr, " threshold=", m_threshold_pct);
                        return signal;
                     }

   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, m_timeframe, 0);
                        if(current_bar_time == last_bar_time) return;

                        double signal = CalculateSignal();
                        if(signal == 0.0) return;

                        double high_arr[], low_arr[];
                        if(CopyHigh(m_symbol, m_timeframe, 1, m_swing_lookback, high_arr) <= 0 ||
                           CopyLow(m_symbol, m_timeframe, 1, m_swing_lookback, low_arr) <= 0) return;

                        double swing_high = high_arr[ArrayMaximum(high_arr)];
                        double swing_low  = low_arr[ArrayMinimum(low_arr)];
                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
                        double current_price = (signal == 100.0) ? SymbolInfoDouble(m_symbol, SYMBOL_ASK) : SymbolInfoDouble(m_symbol, SYMBOL_BID);

                        double sl_distance_pts = (signal == 100.0)
                           ? (current_price - swing_low) / point + m_sl_buffer_pts
                           : (swing_high - current_price) / point + m_sl_buffer_pts;

                        // Tail-risk rule: skip the trade, never clamp the SL inward —
                        // an artificially tightened SL is no longer protected by structure.
                        if(sl_distance_pts > m_max_sl_pts)
                          {
                           Print(m_strategy_name, " skip: structural SL ", sl_distance_pts,
                                 "pts exceeds Max_SL ", m_max_sl_pts, "pts");
                           return;
                          }

                        long stop_level_pts = SymbolInfoInteger(m_symbol, SYMBOL_TRADE_STOPS_LEVEL);
                        long spread_pts      = SymbolInfoInteger(m_symbol, SYMBOL_SPREAD);
                        if(sl_distance_pts < stop_level_pts + spread_pts)
                          {
                           Print(m_strategy_name, " skip: SL ", sl_distance_pts,
                                 "pts violates broker stop level ", stop_level_pts, " + spread ", spread_pts);
                           return;
                          }

                        // Diagnostic logging for future dynamic TP-to-MA research (v2) — not used for logic in v1.
                        double ma_arr[];
                        double dist_to_ma_pts = 0.0;
                        if(CopyBuffer(m_ma_handle, 0, 1, 1, ma_arr) > 0)
                           dist_to_ma_pts = MathAbs(current_price - ma_arr[0]) / point;
                        double rr_ratio = (sl_distance_pts > 0) ? (m_tp_pts / sl_distance_pts) : 0;
                        Print(m_strategy_name, " entry diag | dist_to_MA=", dist_to_ma_pts,
                              "pts TP=", m_tp_pts, "pts SL=", sl_distance_pts, "pts R:R=", rr_ratio);

                        double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight);
                        bool is_opened = false;

                        if(signal == 100.0)
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name, sl_distance_pts, m_tp_pts);
                        else
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name, sl_distance_pts, m_tp_pts);

                        if(is_opened) last_bar_time = current_bar_time;
                     }

   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        // Trail effectively OFF (huge activation) — "simple > complex" lesson from
                        // SMC Phase 9 / ADX. Not exposed as an input in v1; revisit during optimization.
                        posMgr.ManageTrailingStop(m_symbol, m_magic_number, 50000, 50000, 1000);
                     }
  };
//+------------------------------------------------------------------+
