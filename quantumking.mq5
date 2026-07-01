//+------------------------------------------------------------------+
//|                                                  quantumking.mq5 |
//|                                      Copyright 2026, Lai Si Xiang|
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property link      "https://www.mql5.com"
#property version   "1.52" // Add MACD_Momentum v1.10 optimization wiring

#include "CStrategyManager.mqh"
#include "CStrategy_MA_Trend.mqh"
#include "CStrategy_Asian_Breakout.mqh"
#include "CStrategy_MACD_Momentum.mqh"
#include "CStrategy_ADX_Trend.mqh"
#include "CStrategy_Pivot_Divergence.mqh"
#include "CStrategy_VWAP_Reversion.mqh"
#include "CStrategy_Fractal_Breakout.mqh"
#include "CStrategy_Pulse_Momentum.mqh"
#include "CStrategy_SMC_OrderBlock.mqh"
#include "CStrategy_BIAS_Reversion.mqh"

enum ENUM_QK_RUNTIME_PRESET
  {
   QK_PRESET_MA_ONLY = 0,
   QK_PRESET_SMC_CHAMPION = 1,
   QK_PRESET_MA_SMC = 2,
   QK_PRESET_MA_SMC_ADX = 3,
   QK_PRESET_ADX_ONLY = 6,
   QK_PRESET_MACD_ONLY = 7,
   QK_PRESET_CUSTOM = 4,
   QK_PRESET_FTMO_CHALLENGE = 5
  };

// ======================================================================
// Commercial runtime preset selector
// ======================================================================
input ENUM_QK_RUNTIME_PRESET Runtime_Preset = QK_PRESET_MA_ONLY; // Default: safest legacy runtime
input bool   Custom_Enable_MA_Trend        = true;  // CUSTOM preset: enable MA_Trend
input bool   Custom_Enable_SMC_OrderBlock  = false; // CUSTOM preset: enable SMC
input bool   Custom_Enable_MACD_Momentum   = false; // CUSTOM preset: enable MACD
input bool   Custom_Enable_ADX_Trend       = false; // CUSTOM preset: enable ADX
input bool   Custom_Enable_BIAS_Reversion  = false; // CUSTOM preset: enable BIAS_Reversion (experimental)
input double MA_Trend_Weight               = 1.0;   // MA strategy weight (1.0 = full)
input double SMC_OrderBlock_Weight         = 1.0;   // SMC strategy weight (1.0 = full)
input double MACD_Momentum_Weight          = 0.3;   // MACD strategy weight
input double ADX_Trend_Weight              = 0.3;   // ADX strategy weight
input double BIAS_Reversion_Weight         = 0.3;   // BIAS_Reversion strategy weight (experimental)
// ======================================================================

// ======================================================================
// 【MA_Trend 优化器参数区】
// ⚠️ 这里的值会覆盖 CStrategy_MA_Trend.mqh 里的默认值
// 单独回测时请确保这里的数值和你要测试的参数一致
// ======================================================================

// --- Trend definition (tuned 2026-06-01: PF 1.82 / DD 4.68% / $1614 / 476 trades) ---
input int    Fast_EMA_Period  = 30;     // MA: H4 fast EMA period (LOCKED: 30, was 20)
input int    Slow_EMA_Period  = 50;     // MA: H4 slow EMA period (LOCKED: 50, was 70)

// --- KDJ momentum (unchanged from original tuning) ---
input int    KDJ_Period       = 7;      // MA: M15 KDJ period
input int    KDJ_Smooth_D     = 2;      // MA: KDJ smooth D
input int    KDJ_Smooth_S     = 2;      // MA: KDJ smooth S
input int    Stoch_OB         = 70;     // MA: Stochastic overbought
input int    Stoch_OS         = 40;     // MA: Stochastic oversold

// --- Fibonacci entry zone (tuned 2026-06-01) ---
input double Fibo_Top         = 0.525;  // MA: Fibonacci upper bound (LOCKED: 0.525, was 0.5)
input double Fibo_Bottom      = 0.675;  // MA: Fibonacci lower bound (LOCKED: 0.675, was 0.677)
input int    Zone_Buffer_Pts  = 80;     // MA: Fib zone buffer pts (LOCKED: 80, was 150)

// --- Risk / stop-loss (unchanged) ---
input int    SL_Buffer_Pts    = 300;    // MA: SL buffer pts
input int    Max_SL_Pts       = 800;    // MA: Max single-trade SL cap

// --- Trailing exit (tuned 2026-06-01) ---
input int    Trail_Start_Pts  = 1400;   // MA: Trail activation pts
input int    Trail_Step_Pts   = 140;    // MA: Trail step pts (LOCKED: 140, was 100)

// ======================================================================
// SMC_OrderBlock — tune these in the Inputs tab (defaults = research pick)
// ======================================================================
input int    SMC_SL_Buffer_Pts = 105;   // SMC champion SL buffer pts
input int    SMC_Fib_Tol_Pts   = 400;   // SMC champion OTE Fib tolerance pts
input int    SMC_Scan_Window    = 80;    // SMC Scan window (inert per research)
input double SMC_SL_Mult        = 0.5;   // SMC SL multiplier (0.5 = half SL)
input bool   SMC_Use_H4_Filter  = false; // SMC champion: H4 EMA filter OFF
input int    SMC_H4_Fast_EMA    = 50;    // SMC H4 fast EMA period
input int    SMC_H4_Slow_EMA    = 200;   // SMC H4 slow EMA period
input int    SMC_Trail_Start    = 50000; // SMC champion: trail effectively OFF
input int    SMC_Trail_Dist     = 50000; // SMC champion: trail effectively OFF
input int    SMC_Trail_Step     = 1000;  // SMC champion trail step
input int    SMC_Max_SL_Pts     = 400;   // SMC champion max single-trade SL pts
// --- v1.13 entry relaxation ---
input double SMC_OTE_Level1     = 0.382; // SMC champion OTE upper fib
input double SMC_OTE_Level2     = 0.886; // SMC champion OTE lower fib
input bool   SMC_Require_FVG    = false; // SMC champion: FVG relaxed
// --- v1.13 KDJ momentum filter ---
input bool   SMC_Use_KDJ_Filter = true;  // SMC champion: KDJ filter ON
input int    SMC_KDJ_Period     = 7;     // SMC KDJ period
input int    SMC_KDJ_Smooth_D   = 2;     // SMC KDJ smooth D
input int    SMC_KDJ_Smooth_S   = 2;     // SMC KDJ smooth S
input int    SMC_KDJ_OB         = 70;    // SMC KDJ overbought (blocks longs)
input int    SMC_KDJ_OS         = 30;    // SMC KDJ oversold (blocks shorts)
// --- v1.13 ADX trend-strength filter ---
input bool   SMC_Use_ADX_Filter = true;  // SMC champion: ADX filter ON
input int    SMC_ADX_Period     = 14;    // SMC ADX period
input double SMC_ADX_Min        = 30.0;  // SMC champion ADX min
// --- v1.14 textbook H4 BOS direction filter ---
input bool   SMC_Use_H4_BOS_Filter = false; // SMC H4 BOS filter (only trade with H4 BOS direction)
input int    SMC_H4_BOS_Lookback   = 50;    // SMC H4 BOS lookback bars (50 ~ 8 days)
// --- v1.15 Kelly Path B cherry-picks: session + fixed R:R + breakeven ---
input bool   SMC_Use_Session_Filter = true;  // SMC champion session filter ON
input int    SMC_Session1_Start    = 9;     // SMC London session start hour (server time)
input int    SMC_Session1_End      = 12;    // SMC London session end hour (exclusive)
input int    SMC_Session2_Start    = 14;    // SMC NY session start hour
input int    SMC_Session2_End      = 17;    // SMC NY session end hour (exclusive)
input bool   SMC_Use_Fixed_RR      = false; // SMC fixed R:R exit (replaces trail)
input double SMC_RR_Ratio          = 5.0;   // SMC R:R ratio (Kelly default 1:5)
input bool   SMC_Use_BreakEven     = false; // SMC break-even ON/OFF
input int    SMC_BE_Trigger_Pts    = 500;   // SMC BE trigger pts (Kelly: ~1:3 risk distance)
// --- v1.16 Trail + Fixed R:R hybrid ---
input bool   SMC_Use_Trail_With_RR = false; // SMC trail+R:R hybrid (captures mid-flight profit when TP too far)
// ======================================================================

// ======================================================================
// ADX_Trend tunable research inputs (strategy disabled by default)
// ======================================================================
input int    ADX_Period             = 12;    // ADX period (locked 2026-06-23)
input double ADX_Threshold          = 45.0;  // ADX strength threshold (locked)
input int    ADX_SL_Buffer_Pts      = 40;    // Structure SL buffer pts (locked)
input int    ADX_Max_SL_Pts         = 500;   // Max SL cap pts (locked)
// ======================================================================

// ======================================================================
// MACD_Momentum tunable research inputs (v1.10, not locked)
// ======================================================================
input int    MACD_Fast_EMA          = 12;    // MACD fast EMA period
input int    MACD_Slow_EMA          = 26;    // MACD slow EMA period
input int    MACD_Signal_SMA        = 9;     // MACD signal SMA period
input int    MACD_SL_Buffer_Pts     = 150;   // Structure SL buffer pts
input int    MACD_Max_SL_Pts        = 800;   // 0=no cap, >0 skips trades above cap
// ======================================================================

// ======================================================================
// BIAS_Reversion tunable research inputs (v1.00, EXPERIMENTAL, disabled by default)
// Fills the empty LOW_VOL_RANGE regime slot (MA/SMC/ADX all require HIGH_VOL_TREND).
// ======================================================================
input int    BIAS_MA_Period            = 50;    // MA period for deviation calc
input double BIAS_Threshold_Pct        = 0.5;    // BIAS %% extreme that triggers reversion (test range 0.3-0.8)
input int    BIAS_SL_Buffer_Pts        = 50;     // Structure SL buffer pts
input int    BIAS_Max_SL_Pts           = 500;    // Max SL cap pts — trade skipped (not clamped) if exceeded
input int    BIAS_TP_Pts               = 2000;   // Fixed TP pts (test range 1000-4000)
input int    BIAS_Swing_Lookback       = 50;     // Bars to scan for swing high/low (test range 20-60)
input bool   BIAS_Use_KDJ_Filter       = false;  // Require KDJ OB/OS within lookback window
input int    BIAS_KDJ_Lookback_Bars    = 3;      // KDJ extreme lookback window (bars)
input bool   BIAS_Use_ADX_Max_Filter   = false;  // Require ADX below max (confirm genuine range)
input double BIAS_ADX_Max              = 22.0;   // ADX ceiling for ADX max filter (test range 18-25)
input bool   BIAS_Use_Session_Filter   = false;  // Test ON vs OFF — trend-session window may not transfer
// ======================================================================

// ======================================================================
// Commercial global entry-time filters (default OFF = current behavior)
// ======================================================================
input bool   Use_Commercial_Time_Filter = false; // Master switch for new-entry time filters
input bool   Block_Monday_New_Entries   = true;  // Block new entries on Monday
input bool   Block_Friday_Late_Entries  = true;  // Block new entries late Friday
input int    Friday_Block_Hour          = 14;    // Server hour to stop Friday entries
input bool   Use_Global_Session_Filter  = false; // Restrict new entries to two sessions
input int    Session1_Start_Hour        = 9;     // London window start
input int    Session1_End_Hour          = 12;    // London window end
input int    Session2_Start_Hour        = 14;    // NY window start
input int    Session2_End_Hour          = 17;    // NY window end
input bool   Use_Premium_Window_Filter  = false; // Restrict new entries to premium window
input int    Premium_Window_Start_Hour  = 15;    // Silver Bullet window start
input int    Premium_Window_End_Hour    = 16;    // Silver Bullet window end
// ======================================================================

// ======================================================================
// Commercial risk and execution controls (default = current behavior)
// ======================================================================
input bool   Is_Cent_Account              = false; // Account type flag
input int    Max_Spread_Pts               = 400;   // Max spread allowed for entries
input double Base_Risk_Pct                = 0.02;  // Base risk percent
input double Max_Floating_Drawdown_Pct    = 0.20;  // Emergency floating DD close
input bool   Use_Commercial_Risk_Guards   = false; // Daily/peak guard master switch
input double Daily_Loss_Guard_Pct         = 0.04;  // Pause after 4% daily equity loss
input double Peak_Equity_DD_Guard_Pct     = 0.10;  // Pause after 10% drop from peak equity
input bool   Persist_Risk_Pause           = true;  // Keep pause after restart
input bool   Reset_Risk_Pause             = false; // One-time reset for persisted pause
input int    Grid_Breakeven_Pts           = 150;   // Grid breakeven exit pts
input int    Grid_Spacing_Pts             = 1000;  // Grid layer spacing pts
input int    Max_Grid_Layers              = 10;    // Set 1 for prop/no-grid mode
// ======================================================================

CStrategyManager *StrategyMgr;
CRiskManager     *RiskMgr;
CPositionManager *PosMgr;

//+------------------------------------------------------------------+
//| EA 初始化函数                                                      |
//+------------------------------------------------------------------+
int OnInit()
  {
   bool is_ftmo_challenge = (Runtime_Preset == QK_PRESET_FTMO_CHALLENGE);
   bool effective_use_commercial_risk_guards = is_ftmo_challenge ? true : Use_Commercial_Risk_Guards;
   double effective_daily_loss_guard_pct = is_ftmo_challenge ? 0.04 : Daily_Loss_Guard_Pct;
   double effective_peak_equity_dd_guard_pct = is_ftmo_challenge ? 0.10 : Peak_Equity_DD_Guard_Pct;
   int effective_max_grid_layers = is_ftmo_challenge ? 1 : Max_Grid_Layers;

   bool effective_use_commercial_time_filter = is_ftmo_challenge ? true : Use_Commercial_Time_Filter;
   bool effective_block_monday_entries = is_ftmo_challenge ? true : Block_Monday_New_Entries;
   bool effective_block_friday_late_entries = is_ftmo_challenge ? true : Block_Friday_Late_Entries;
   int effective_friday_block_hour = is_ftmo_challenge ? 14 : Friday_Block_Hour;
   bool effective_use_global_session_filter = is_ftmo_challenge ? true : Use_Global_Session_Filter;
   int effective_session1_start_hour = is_ftmo_challenge ? 9 : Session1_Start_Hour;
   int effective_session1_end_hour = is_ftmo_challenge ? 12 : Session1_End_Hour;
   int effective_session2_start_hour = is_ftmo_challenge ? 14 : Session2_Start_Hour;
   int effective_session2_end_hour = is_ftmo_challenge ? 17 : Session2_End_Hour;
   bool effective_use_premium_window_filter = is_ftmo_challenge ? false : Use_Premium_Window_Filter;

   RiskMgr = new CRiskManager(
      Is_Cent_Account,
      Max_Spread_Pts,
      Base_Risk_Pct,
      Max_Floating_Drawdown_Pct,
      effective_use_commercial_risk_guards,
      effective_daily_loss_guard_pct,
      effective_peak_equity_dd_guard_pct,
      Persist_Risk_Pause,
      Reset_Risk_Pause
   );
   PosMgr  = new CPositionManager(Grid_Breakeven_Pts, Grid_Spacing_Pts, effective_max_grid_layers);
   StrategyMgr = new CStrategyManager(
      RiskMgr,
      PosMgr,
      effective_use_commercial_time_filter,
      effective_block_monday_entries,
      effective_block_friday_late_entries,
      effective_friday_block_hour,
      effective_use_global_session_filter,
      effective_session1_start_hour,
      effective_session1_end_hour,
      effective_session2_start_hour,
      effective_session2_end_hour,
      effective_use_premium_window_filter,
      Premium_Window_Start_Hour,
      Premium_Window_End_Hour
   );

   bool enable_ma_trend = (Runtime_Preset == QK_PRESET_CUSTOM) ? Custom_Enable_MA_Trend : false;
   bool enable_smc_orderblock = (Runtime_Preset == QK_PRESET_CUSTOM) ? Custom_Enable_SMC_OrderBlock : false;
   bool enable_macd_momentum = (Runtime_Preset == QK_PRESET_CUSTOM) ? Custom_Enable_MACD_Momentum : false;
   bool enable_adx_trend = (Runtime_Preset == QK_PRESET_CUSTOM) ? Custom_Enable_ADX_Trend : false;
   bool enable_bias_reversion = (Runtime_Preset == QK_PRESET_CUSTOM) ? Custom_Enable_BIAS_Reversion : false; // experimental, CUSTOM-only — no preset enables this

   if(Runtime_Preset == QK_PRESET_MA_ONLY)
     {
      enable_ma_trend = true;
     }
   else if(Runtime_Preset == QK_PRESET_SMC_CHAMPION)
     {
      enable_smc_orderblock = true;
     }
   else if(Runtime_Preset == QK_PRESET_MA_SMC)
     {
      enable_ma_trend = true;
      enable_smc_orderblock = true;
     }
   else if(Runtime_Preset == QK_PRESET_MA_SMC_ADX)
     {
      enable_ma_trend = true;
      enable_smc_orderblock = true;
      enable_adx_trend = true;
     }
   else if(Runtime_Preset == QK_PRESET_ADX_ONLY)
     {
      enable_adx_trend = true;
     }
   else if(Runtime_Preset == QK_PRESET_MACD_ONLY)
     {
      enable_macd_momentum = true;
     }
   else if(Runtime_Preset == QK_PRESET_FTMO_CHALLENGE)
     {
      enable_ma_trend = true;
      enable_smc_orderblock = true;
     }

   // ===== Pair test mode: MA_Trend (tuned) + SMC (champion) both active =====
   if(enable_ma_trend)
     {
      StrategyMgr.AddStrategy(new CStrategy_MA_Trend(
      "均线顺势",
      10002,
      MA_Trend_Weight,
      _Symbol,
      PERIOD_M15,
      Stoch_OB,
      Stoch_OS,
      Fast_EMA_Period,
      Slow_EMA_Period,
      KDJ_Period,
      KDJ_Smooth_D,
      KDJ_Smooth_S,
      Fibo_Top,
      Fibo_Bottom,
      Zone_Buffer_Pts,
      SL_Buffer_Pts,
      Max_SL_Pts,
      Trail_Start_Pts,
      Trail_Step_Pts
      ));
     }

   /* ===== SMC disabled (LOCKED, do not change inputs) — re-tuning MA =====
   StrategyMgr.AddStrategy(new CStrategy_SMC_OrderBlock(
      "SMC顺势",
      10010,
      1.0,
      _Symbol,
      PERIOD_M15,
      SMC_SL_Buffer_Pts,
      SMC_Fib_Tol_Pts,
      SMC_Scan_Window,
      SMC_SL_Mult,
      SMC_Use_H4_Filter,
      SMC_H4_Fast_EMA,
      SMC_H4_Slow_EMA,
      SMC_Trail_Start,
      SMC_Trail_Dist,
      SMC_Trail_Step,
      SMC_Max_SL_Pts,
      SMC_Use_KDJ_Filter,
      SMC_KDJ_Period,
      SMC_KDJ_Smooth_D,
      SMC_KDJ_Smooth_S,
      SMC_KDJ_OB,
      SMC_KDJ_OS,
      SMC_Use_ADX_Filter,
      SMC_ADX_Period,
      SMC_ADX_Min,
      SMC_OTE_Level1,
      SMC_OTE_Level2,
      SMC_Require_FVG,
      SMC_Use_H4_BOS_Filter,
      SMC_H4_BOS_Lookback,
      SMC_Use_Session_Filter,
      SMC_Session1_Start,
      SMC_Session1_End,
      SMC_Session2_Start,
      SMC_Session2_End,
      SMC_Use_Fixed_RR,
      SMC_RR_Ratio,
      SMC_Use_BreakEven,
      SMC_BE_Trigger_Pts,
      SMC_Use_Trail_With_RR
   ));
   ===================================================================================== */

   if(enable_smc_orderblock)
     {
      StrategyMgr.AddStrategy(new CStrategy_SMC_OrderBlock(
         "SMC顺势",
         10010,
         SMC_OrderBlock_Weight,
         _Symbol,
         PERIOD_M15,
         SMC_SL_Buffer_Pts,
         SMC_Fib_Tol_Pts,
         SMC_Scan_Window,
         SMC_SL_Mult,
         SMC_Use_H4_Filter,
         SMC_H4_Fast_EMA,
         SMC_H4_Slow_EMA,
         SMC_Trail_Start,
         SMC_Trail_Dist,
         SMC_Trail_Step,
         SMC_Max_SL_Pts,
         SMC_Use_KDJ_Filter,
         SMC_KDJ_Period,
         SMC_KDJ_Smooth_D,
         SMC_KDJ_Smooth_S,
         SMC_KDJ_OB,
         SMC_KDJ_OS,
         SMC_Use_ADX_Filter,
         SMC_ADX_Period,
         SMC_ADX_Min,
         SMC_OTE_Level1,
         SMC_OTE_Level2,
         SMC_Require_FVG,
         SMC_Use_H4_BOS_Filter,
         SMC_H4_BOS_Lookback,
         SMC_Use_Session_Filter,
         SMC_Session1_Start,
         SMC_Session1_End,
         SMC_Session2_Start,
         SMC_Session2_End,
         SMC_Use_Fixed_RR,
         SMC_RR_Ratio,
         SMC_Use_BreakEven,
         SMC_BE_Trigger_Pts,
         SMC_Use_Trail_With_RR
      ));
     }

   //StrategyMgr.AddStrategy(new CStrategy_Asian_Breakout("亚盘顺势", 10003, 1.0, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_MACD_Momentum("MACD顺势", 10004, 1.0, _Symbol, PERIOD_M15));
   if(enable_macd_momentum)
     {
      StrategyMgr.AddStrategy(new CStrategy_MACD_Momentum(
         "MACD顺势",
         10004,
         MACD_Momentum_Weight,
         _Symbol,
         PERIOD_M15,
         MACD_Fast_EMA,
         MACD_Slow_EMA,
         MACD_Signal_SMA,
         MACD_SL_Buffer_Pts,
         MACD_Max_SL_Pts
      ));
     }

   /* ===== ADX tunable disabled; enable for ADX solo/pair testing =====
   StrategyMgr.AddStrategy(new CStrategy_ADX_Trend(
      "ADX顺势",
      10005,
      1.0,
      _Symbol,
      PERIOD_M15,
      ADX_Period,
      ADX_Threshold,
      ADX_SL_Buffer_Pts,
      ADX_Max_SL_Pts
   ));
   ==================================================================== */

   if(enable_adx_trend)
     {
      StrategyMgr.AddStrategy(new CStrategy_ADX_Trend(
         "ADX顺势",
         10005,
         ADX_Trend_Weight,
         _Symbol,
         PERIOD_M15,
         ADX_Period,
         ADX_Threshold,
         ADX_SL_Buffer_Pts,
         ADX_Max_SL_Pts
      ));
     }

   // v1.00 EXPERIMENTAL — not optimized, not locked. CUSTOM preset only.
   if(enable_bias_reversion)
     {
      StrategyMgr.AddStrategy(new CStrategy_BIAS_Reversion(
         "BIAS回归",
         10011,
         BIAS_Reversion_Weight,
         _Symbol,
         PERIOD_M15,
         BIAS_MA_Period,
         BIAS_Threshold_Pct,
         BIAS_SL_Buffer_Pts,
         BIAS_Max_SL_Pts,
         BIAS_TP_Pts,
         BIAS_Swing_Lookback,
         BIAS_Use_KDJ_Filter,
         BIAS_KDJ_Lookback_Bars,
         BIAS_Use_ADX_Max_Filter,
         BIAS_ADX_Max,
         BIAS_Use_Session_Filter
      ));
     }
   //StrategyMgr.AddStrategy(new CStrategy_Pivot_Divergence("枢轴点回归", 10006, 0.3, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_VWAP_Reversion("VWAP回归", 10007, 0.3, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_Fractal_Breakout("碎形顺势", 10008, 1.0, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_Pulse_Momentum("脉冲顺势", 10009, 1.0, _Symbol, PERIOD_M15));

   string btnName = "BtnKillSwitch";
   ObjectCreate(0, btnName, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, btnName, OBJPROP_XDISTANCE, 20);
   ObjectSetInteger(0, btnName, OBJPROP_YDISTANCE, 20);
   ObjectSetInteger(0, btnName, OBJPROP_XSIZE, 180);
   ObjectSetInteger(0, btnName, OBJPROP_YSIZE, 40);
   ObjectSetInteger(0, btnName, OBJPROP_BGCOLOR, clrSeaGreen);
   ObjectSetInteger(0, btnName, OBJPROP_COLOR, clrWhite);
   ObjectSetString(0, btnName, OBJPROP_TEXT, "▶️ SYSTEM RUNNING");
   ObjectSetInteger(0, btnName, OBJPROP_FONTSIZE, 10);
   ObjectSetInteger(0, btnName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, btnName, OBJPROP_STATE, false);
   ObjectSetInteger(0, btnName, OBJPROP_SELECTABLE, false);

   Print("QuantumKing v1.52 启动！Preset: " + EnumToString(Runtime_Preset));
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| EA 卸载函数                                                        |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(CheckPointer(StrategyMgr) == POINTER_DYNAMIC) delete StrategyMgr;
   if(CheckPointer(RiskMgr)     == POINTER_DYNAMIC) delete RiskMgr;
   if(CheckPointer(PosMgr)      == POINTER_DYNAMIC) delete PosMgr;
   ObjectDelete(0, "BtnKillSwitch");
   Print("引擎已安全卸载。");
  }

//+------------------------------------------------------------------+
//| EA Tick 循环                                                       |
//+------------------------------------------------------------------+
void OnTick()
  {
   if(CheckPointer(StrategyMgr) != POINTER_INVALID)
      StrategyMgr.OnTick();
  }

//+------------------------------------------------------------------+
//| 监听图表事件                                                        |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
  {
   if(id == CHARTEVENT_OBJECT_CLICK && sparam == "BtnKillSwitch")
     {
      bool state = (bool)ObjectGetInteger(0, "BtnKillSwitch", OBJPROP_STATE);
      if(state == true)
        {
         ObjectSetInteger(0, "BtnKillSwitch", OBJPROP_BGCOLOR, clrCrimson);
         ObjectSetString(0, "BtnKillSwitch", OBJPROP_TEXT, "🚨 SYSTEM PAUSED");
         if(CheckPointer(StrategyMgr) != POINTER_INVALID)
            StrategyMgr.SetManualPause(true);
         Print("🚨 [总指挥指令] 物理断电开关已按下！停止一切新单开仓！");
        }
      else
        {
         ObjectSetInteger(0, "BtnKillSwitch", OBJPROP_BGCOLOR, clrSeaGreen);
         ObjectSetString(0, "BtnKillSwitch", OBJPROP_TEXT, "▶️ SYSTEM RUNNING");
         if(CheckPointer(StrategyMgr) != POINTER_INVALID)
            StrategyMgr.SetManualPause(false);
         Print("▶️ [总指挥指令] 警报解除，系统恢复全自动侦测！");
        }
      ChartRedraw();
     }
  }

//+------------------------------------------------------------------+
//| MT5 optimization criterion: commercial quality gate               |
//+------------------------------------------------------------------+
double CalculateTesterProfitPips()
  {
   if(!HistorySelect(0, TimeCurrent())) return 0.0;

   long position_ids[];
   double entry_prices[];
   double entry_volumes[];
   int directions[];
   double total_pips = 0.0;
   double point = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   if(point <= 0.0) point = _Point;

   int total_deals = HistoryDealsTotal();
   for(int i = 0; i < total_deals; i++)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;
      if(HistoryDealGetString(ticket, DEAL_SYMBOL) != _Symbol) continue;

      ENUM_DEAL_TYPE deal_type = (ENUM_DEAL_TYPE)HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(deal_type != DEAL_TYPE_BUY && deal_type != DEAL_TYPE_SELL) continue;

      ENUM_DEAL_ENTRY deal_entry = (ENUM_DEAL_ENTRY)HistoryDealGetInteger(ticket, DEAL_ENTRY);
      long position_id = HistoryDealGetInteger(ticket, DEAL_POSITION_ID);
      double price = HistoryDealGetDouble(ticket, DEAL_PRICE);
      double volume = HistoryDealGetDouble(ticket, DEAL_VOLUME);

      int index = -1;
      for(int j = 0; j < ArraySize(position_ids); j++)
        {
         if(position_ids[j] == position_id)
           {
            index = j;
            break;
           }
        }

      if(deal_entry == DEAL_ENTRY_IN)
        {
         int direction = (deal_type == DEAL_TYPE_BUY) ? 1 : -1;
         if(index < 0)
           {
            int size = ArraySize(position_ids);
            ArrayResize(position_ids, size + 1);
            ArrayResize(entry_prices, size + 1);
            ArrayResize(entry_volumes, size + 1);
            ArrayResize(directions, size + 1);
            position_ids[size] = position_id;
            entry_prices[size] = price;
            entry_volumes[size] = volume;
            directions[size] = direction;
           }
         else
           {
            double total_volume = entry_volumes[index] + volume;
            if(total_volume > 0.0)
               entry_prices[index] = (entry_prices[index] * entry_volumes[index] + price * volume) / total_volume;
            entry_volumes[index] = total_volume;
           }
        }
      else if(deal_entry == DEAL_ENTRY_OUT || deal_entry == DEAL_ENTRY_INOUT || deal_entry == DEAL_ENTRY_OUT_BY)
        {
         if(index >= 0 && directions[index] != 0)
           {
            double profit_points = (price - entry_prices[index]) / point * directions[index];
            total_pips += profit_points / 10.0;
           }
        }
     }

   return total_pips;
  }

double OnTester()
  {
   double pf = TesterStatistics(STAT_PROFIT_FACTOR);
   double trades = TesterStatistics(STAT_TRADES);
   double net_profit = TesterStatistics(STAT_PROFIT);
   double balance_dd = TesterStatistics(STAT_BALANCE_DDREL_PERCENT) / 100.0;
   double equity_dd = TesterStatistics(STAT_EQUITY_DDREL_PERCENT) / 100.0;
   double dd = MathMax(balance_dd, equity_dd);
   double profit_pips = CalculateTesterProfitPips();
   double score = 0.0;

   // Returns 0 if DD > 20% (commercial gate fail)
   // Returns 0 if trades < 100 (not enough sample)
   // Otherwise: score = PF x sqrt(trades / 200) x (1 - DD/0.20)
   if(dd <= 0.20 && trades >= 100.0 && pf > 0.0)
      score = pf * MathSqrt(trades / 200.0) * (1.0 - dd / 0.20);

   score = MathMax(score, 0.0);
   PrintFormat("[OnTester] score=%.4f PF=%.2f DD=%.2f%% trades=%.0f net=$%.2f profit_pips=%.1f",
               score, pf, dd * 100.0, trades, net_profit, profit_pips);

   // Higher = better. Use as "Custom max" criterion in MT5.
   return score;
  }
//+------------------------------------------------------------------+
