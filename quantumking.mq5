//+------------------------------------------------------------------+
//|                                                  quantumking.mq5 |
//|                                      Copyright 2026, Lai Si Xiang|
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property link      "https://www.mql5.com"
#property version   "1.40" // 最优参数版：Fast10 / Slow40 / Trail1400/100

#include "CStrategyManager.mqh"
#include "CStrategy_Bands_Extreme.mqh"
#include "CStrategy_MA_Trend.mqh"
#include "CStrategy_Asian_Breakout.mqh"
#include "CStrategy_MACD_Momentum.mqh"
#include "CStrategy_ADX_Trend.mqh"
#include "CStrategy_Pivot_Divergence.mqh"
#include "CStrategy_VWAP_Reversion.mqh"
#include "CStrategy_Fractal_Breakout.mqh"
#include "CStrategy_Pulse_Momentum.mqh"
#include "CStrategy_SMC_OrderBlock.mqh"

// ======================================================================
// 【MA_Trend 优化器参数区】
// ⚠️ 这里的值会覆盖 CStrategy_MA_Trend.mqh 里的默认值
// 单独回测时请确保这里的数值和你要测试的参数一致
// ======================================================================

// --- Trend definition (tuned 2026-06-01: PF 1.82 / DD 4.68% / $1614 / 476 trades) ---
input int    Fast_EMA_Period  = 30;     // tuned from 20
input int    Slow_EMA_Period  = 50;     // tuned from 70

// --- KDJ momentum (unchanged from original tuning) ---
input int    KDJ_Period       = 7;
input int    KDJ_Smooth_D     = 2;
input int    KDJ_Smooth_S     = 2;
input int    Stoch_OB         = 70;
input int    Stoch_OS         = 40;

// --- Fibonacci entry zone (tuned 2026-06-01) ---
input double Fibo_Top         = 0.525;  // tuned from 0.5
input double Fibo_Bottom      = 0.675;  // tuned from 0.677
input int    Zone_Buffer_Pts  = 80;     // tuned from 150 (tighter entry zone)

// --- Risk / stop-loss (unchanged) ---
input int    SL_Buffer_Pts    = 300;
input int    Max_SL_Pts       = 800;

// --- Trailing exit (tuned 2026-06-01) ---
input int    Trail_Start_Pts  = 1400;
input int    Trail_Step_Pts   = 140;    // tuned from 100

// ======================================================================
// ======================================================================
// 【Bands_Extreme 优化器参数区】
// ======================================================================
input int    BB_Period       = 20;     // 布林带周期
input double BB_Dev          = 2.5;    // 布林带偏差
input int    RSI_Period      = 14;     // RSI 周期
input int    RSI_OB          = 80;     // RSI 超买线 (做空条件)
input int    RSI_OS          = 20;     // RSI 超卖线 (做多条件)
input double Shadow_Mult     = 1.5;    // 影线必须大于实体的倍数
// ======================================================================
// ======================================================================
// SMC_OrderBlock — tune these in the Inputs tab (defaults = research pick)
// ======================================================================
input int    SMC_SL_Buffer_Pts = 60;    // SMC SL Buffer pts (below OB)
input int    SMC_Fib_Tol_Pts   = 300;   // SMC OTE Fib tolerance pts
input int    SMC_Scan_Window    = 80;    // SMC Scan window (inert per research)
input double SMC_SL_Mult        = 0.5;   // SMC SL multiplier (0.5 = half SL)
input bool   SMC_Use_H4_Filter  = true;  // SMC H4 EMA trend filter ON/OFF
input int    SMC_H4_Fast_EMA    = 50;    // SMC H4 fast EMA period
input int    SMC_H4_Slow_EMA    = 200;   // SMC H4 slow EMA period
input int    SMC_Trail_Start    = 2000;  // SMC trail activation pts
input int    SMC_Trail_Dist     = 1500;  // SMC trail distance pts
input int    SMC_Trail_Step     = 500;   // SMC trail step pts
input int    SMC_Max_SL_Pts     = 5000;  // SMC max single-trade SL pts (5000=off; recommend 400-1500)
// --- v1.13 entry relaxation ---
input double SMC_OTE_Level1     = 0.705; // SMC OTE upper fib (relax: 0.5)
input double SMC_OTE_Level2     = 0.786; // SMC OTE lower fib (relax: 0.9)
input bool   SMC_Require_FVG    = true;  // SMC require FVG (false=relax)
// --- v1.13 KDJ momentum filter ---
input bool   SMC_Use_KDJ_Filter = false; // SMC KDJ filter ON/OFF
input int    SMC_KDJ_Period     = 7;     // SMC KDJ period
input int    SMC_KDJ_Smooth_D   = 2;     // SMC KDJ smooth D
input int    SMC_KDJ_Smooth_S   = 2;     // SMC KDJ smooth S
input int    SMC_KDJ_OB         = 70;    // SMC KDJ overbought (blocks longs)
input int    SMC_KDJ_OS         = 30;    // SMC KDJ oversold (blocks shorts)
// --- v1.13 ADX trend-strength filter ---
input bool   SMC_Use_ADX_Filter = false; // SMC ADX filter ON/OFF
input int    SMC_ADX_Period     = 14;    // SMC ADX period
input double SMC_ADX_Min        = 20.0;  // SMC ADX min (ADX below this = ranging, block)
// --- v1.14 textbook H4 BOS direction filter ---
input bool   SMC_Use_H4_BOS_Filter = false; // SMC H4 BOS filter (only trade with H4 BOS direction)
input int    SMC_H4_BOS_Lookback   = 50;    // SMC H4 BOS lookback bars (50 ~ 8 days)
// --- v1.15 Kelly Path B cherry-picks: session + fixed R:R + breakeven ---
input bool   SMC_Use_Session_Filter = false; // SMC session filter (London/NY only)
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

CStrategyManager *StrategyMgr;
CRiskManager     *RiskMgr;
CPositionManager *PosMgr;

//+------------------------------------------------------------------+
//| EA 初始化函数                                                      |
//+------------------------------------------------------------------+
int OnInit()
  {
   RiskMgr = new CRiskManager(false, 400, 0.02);
   PosMgr  = new CPositionManager();
   StrategyMgr = new CStrategyManager(RiskMgr, PosMgr);

 /* =================================================================
   StrategyMgr.AddStrategy(new CStrategy_Bands_Extreme(
      "布林带回归",
      10001,
      0.3,
      _Symbol,
      PERIOD_M15,
      BB_Period,    // 传入顶部参数
      BB_Dev,       // 传入顶部参数
      RSI_Period,   // 传入顶部参数
      RSI_OB,       // 传入顶部参数
      RSI_OS,       // 传入顶部参数
      Shadow_Mult   // 传入顶部参数
   ));
   =================================================================*/

   // ===== Pair test mode: MA_Trend (tuned) + SMC (champion) both active =====
   StrategyMgr.AddStrategy(new CStrategy_MA_Trend(
      "均线顺势",
      10002,
      1.0,
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

   //StrategyMgr.AddStrategy(new CStrategy_Asian_Breakout("亚盘顺势", 10003, 1.0, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_MACD_Momentum("MACD顺势", 10004, 1.0, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_ADX_Trend("ADX顺势", 10005, 1.0, _Symbol, PERIOD_M15));
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

   Print("Quantum King v1.40 启动！MA_Trend 最优参数已载入！");
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
