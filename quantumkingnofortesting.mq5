//+------------------------------------------------------------------+
//|                                                  quantumking.mq5 |
//|                                      Copyright 2026, Lai Si Xiang|
//|                                             https://www.mql5.com |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property link      "https://www.mql5.com"
#property version   "1.20" // 终极升级：一键物理断电开关

// 引入大脑管理器
#include "CStrategyManager.mqh"
// 引入我们的实战部队
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

// 声明全局三大件指针
CStrategyManager *StrategyMgr;
CRiskManager     *RiskMgr;
CPositionManager *PosMgr;

//+------------------------------------------------------------------+
//| EA 初始化函数                                                      |
//+------------------------------------------------------------------+
int OnInit()
  {
   // 1. 打造“盾牌”
   RiskMgr = new CRiskManager(false, 400, 0.02);
   
   // 2. 打造“双手” (使用我们在底层设定好的智能默认参数)
   PosMgr = new CPositionManager();
   
   // 3. 激活“大脑”
   StrategyMgr = new CStrategyManager(RiskMgr, PosMgr);
   
   // --- 正式入编 ---
   //StrategyMgr.AddStrategy(new CStrategy_Bands_Extreme("布林带回归", 10001, 0.3, _Symbol, PERIOD_M15));
   StrategyMgr.AddStrategy(new CStrategy_MA_Trend("均线顺势", 10002, 1.0, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_Asian_Breakout("亚盘顺势", 10003, 1.0, _Symbol, PERIOD_M15));
   StrategyMgr.AddStrategy(new CStrategy_MACD_Momentum("MACD顺势", 10004, 1.0, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_ADX_Trend("ADX顺势", 10005, 1.0, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_Pivot_Divergence("枢轴点回归", 10006, 0.3, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_VWAP_Reversion("VWAP回归", 10007, 0.3, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_Fractal_Breakout("碎形顺势", 10008, 1.0, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_Pulse_Momentum("脉冲顺势", 10009, 1.0, _Symbol, PERIOD_M15));
   //StrategyMgr.AddStrategy(new CStrategy_SMC_OrderBlock("SMC顺势", 10010, 1.0, _Symbol, PERIOD_M15));

   // ======================================================================
   // 🚨 【计划 4 核心】：在图表左上角画出“一键物理断电开关”
   // ======================================================================
   string btnName = "BtnKillSwitch";
   ObjectCreate(0, btnName, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, btnName, OBJPROP_XDISTANCE, 20);         // 距离左边20像素
   ObjectSetInteger(0, btnName, OBJPROP_YDISTANCE, 20);         // 距离上边20像素
   ObjectSetInteger(0, btnName, OBJPROP_XSIZE, 180);            // 按钮宽度
   ObjectSetInteger(0, btnName, OBJPROP_YSIZE, 40);             // 按钮高度
   ObjectSetInteger(0, btnName, OBJPROP_BGCOLOR, clrSeaGreen);  // 默认运行状态为绿色
   ObjectSetInteger(0, btnName, OBJPROP_COLOR, clrWhite);       // 字体白色
   ObjectSetString(0, btnName, OBJPROP_TEXT, "▶️ SYSTEM RUNNING");
   ObjectSetInteger(0, btnName, OBJPROP_FONTSIZE, 10);
   ObjectSetInteger(0, btnName, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, btnName, OBJPROP_STATE, false);          // 默认弹起状态 (未按下)
   ObjectSetInteger(0, btnName, OBJPROP_SELECTABLE, false);     // 禁止鼠标拖动

   Print("Quantum King 核心引擎组装完毕！物理断电开关已部署！");
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| EA 卸载函数                                                        |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
  {
   if(CheckPointer(StrategyMgr) == POINTER_DYNAMIC) delete StrategyMgr;
   if(CheckPointer(RiskMgr) == POINTER_DYNAMIC) delete RiskMgr;
   if(CheckPointer(PosMgr) == POINTER_DYNAMIC) delete PosMgr;
   
   // 清理战场：移除按钮
   ObjectDelete(0, "BtnKillSwitch");
   
   Print("引擎已安全卸载。");
  }

//+------------------------------------------------------------------+
//| EA Tick 循环                                                       |
//+------------------------------------------------------------------+
void OnTick()
  {
   if(CheckPointer(StrategyMgr) != POINTER_INVALID)
     {
      StrategyMgr.OnTick();
     }
  }

//+------------------------------------------------------------------+
//| 🚨 【新增引擎】：监听图表事件 (捕获鼠标点击)                         |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
  {
   // 捕获鼠标点击按钮的动作
   if(id == CHARTEVENT_OBJECT_CLICK && sparam == "BtnKillSwitch")
     {
      // 获取按钮被点击后的状态 (true: 凹下去被按下; false: 弹起来)
      bool state = (bool)ObjectGetInteger(0, "BtnKillSwitch", OBJPROP_STATE);
      
      if(state == true) 
        {
         // 动作 1：变红，警报UI
         ObjectSetInteger(0, "BtnKillSwitch", OBJPROP_BGCOLOR, clrCrimson); 
         ObjectSetString(0, "BtnKillSwitch", OBJPROP_TEXT, "🚨 SYSTEM PAUSED");
         
         // 动作 2：通知大脑中枢断开一切开仓信号
         if(CheckPointer(StrategyMgr) != POINTER_INVALID)
            StrategyMgr.SetManualPause(true); 
            
         Print("🚨 [总指挥指令] 物理断电开关已按下！停止一切新单开仓！");
        }
      else 
        {
         // 动作 1：恢复绿色，安全UI
         ObjectSetInteger(0, "BtnKillSwitch", OBJPROP_BGCOLOR, clrSeaGreen); 
         ObjectSetString(0, "BtnKillSwitch", OBJPROP_TEXT, "▶️ SYSTEM RUNNING");
         
         // 动作 2：通知大脑中枢恢复供电
         if(CheckPointer(StrategyMgr) != POINTER_INVALID)
            StrategyMgr.SetManualPause(false); 
            
         Print("▶️ [总指挥指令] 警报解除，电源恢复！系统恢复全自动侦测！");
        }
        
      // 强制刷新图表，让颜色瞬间改变
      ChartRedraw(); 
     }
  }
//+------------------------------------------------------------------+