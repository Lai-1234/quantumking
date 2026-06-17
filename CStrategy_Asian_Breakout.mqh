//+------------------------------------------------------------------+
//|                                 CStrategy_Asian_Breakout.mqh     |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.00"

#include "CStrategy.mqh"

class CStrategy_Asian_Breakout : public CStrategy
  {
private:
   int               m_start_hour;
   int               m_end_hour;
   double            m_box_high;
   double            m_box_low;
   int               m_current_day;
   int               m_traded_day;

public:
                     // 默认 00:00 开始造盒子，08:00 结束造盒子并准备引爆
                     CStrategy_Asian_Breakout(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf,
                                              int startHour = 0, int endHour = 8)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_start_hour = startHour;
                        m_end_hour = endHour;
                        m_box_high = 0.0;
                        m_box_low = 999999.0;
                        m_current_day = -1;
                        m_traded_day = -1;
                        Print(m_strategy_name, " 破城锤已就位 (亚洲盘箱体区间: ", m_start_hour, ":00 - ", m_end_hour, ":00)");
                     }

                    ~CStrategy_Asian_Breakout(void) {}

   //========================================================================
   // 核心逻辑 7：绘制寂静盒子 + 捕捉伦敦盘大实体突破
   //========================================================================
   virtual double    CalculateSignal(void) override
                     {
                        MqlDateTime time;
                        TimeToStruct(TimeCurrent(), time);

                        // 每天跨日时，清空昨天的盒子数据，准备画新盒子
                        if(time.day_of_year != m_current_day)
                          {
                           m_current_day = time.day_of_year;
                           m_box_high = 0.0;
                           m_box_low = 999999.0;
                          }

                        // 【第一阶段：造盒子】服务器时间 00:00 - 07:59
                        // 这个阶段绝对不开火，只默默记录亚洲盘的最高点和最低点
                        if(time.hour >= m_start_hour && time.hour < m_end_hour)
                          {
                           double high[], low[];
                           if(CopyHigh(m_symbol, m_timeframe, 0, 1, high) > 0 && CopyLow(m_symbol, m_timeframe, 0, 1, low) > 0)
                             {
                              if(high[0] > m_box_high) m_box_high = high[0];
                              if(low[0] < m_box_low) m_box_low = low[0];
                             }
                           return 0.0; 
                          }

                        // 【第二阶段：伦敦盘爆破】08:00 之后
                        // 铁律：每天只允许成功突破一次，吃完最肥的肉就收工，严禁一天内来回扫单
                        if(time.day_of_year == m_traded_day) return 0.0;

                        // 突破通常发生在伦敦盘开盘的前 4 个小时内 (08:00 - 11:59)，错过这个爆发期就判定为震荡市
                        if(time.hour >= m_end_hour && time.hour <= m_end_hour + 3)
                          {
                           double close[], open[], high[], low[];
                           if(CopyClose(m_symbol, m_timeframe, 1, 1, close) <= 0) return 0;
                           if(CopyOpen(m_symbol, m_timeframe, 1, 1, open) <= 0) return 0;
                           if(CopyHigh(m_symbol, m_timeframe, 1, 1, high) <= 0) return 0;
                           if(CopyLow(m_symbol, m_timeframe, 1, 1, low) <= 0) return 0;

                           double body = MathAbs(close[0] - open[0]);
                           double candle_size = high[0] - low[0];
                           if(candle_size == 0) candle_size = 0.00001;

                           // 【蓝图严打：必须是大实体 K 线】实体部分至少占整根 K 线的 60%
                           bool is_solid_candle = (body / candle_size) >= 0.60;

                           // 【多头爆破】：收盘价高于箱顶 + 是阳线 + 是大实体坚决突破
                           if(close[0] > m_box_high && close[0] > open[0] && is_solid_candle)
                             {
                              Print("🚀 [亚洲盘突破-多] 伦敦盘主力涌入！大实体收盘价:", close[0], " 彻底击穿箱顶:", m_box_high);
                              m_traded_day = time.day_of_year; // 盖章：今天已引爆
                              return 100.0;
                             }

                           // 【空头爆破】：收盘价低于箱底 + 是阴线 + 是大实体坚决砸穿
                           if(close[0] < m_box_low && close[0] < open[0] && is_solid_candle)
                             {
                              Print("🚀 [亚洲盘突破-空] 伦敦盘主力涌入！大实体收盘价:", close[0], " 彻底砸穿箱底:", m_box_low);
                              m_traded_day = time.day_of_year;
                              return -100.0;
                             }
                          }

                        return 0.0;
                     }

   //========================================================================
   // 进场与极限防守计算
   //========================================================================
   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, m_timeframe, 0);
                        if(current_bar_time == last_bar_time) return;

                        double signal = CalculateSignal();
                        if(signal == 0.0) return; 

                        double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight); 
                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
                        bool is_opened = false;

                        // 读取刚刚突破的那根大实体 K 线的高低点
                        double high[], low[];
                        CopyHigh(m_symbol, m_timeframe, 1, 1, high);
                        CopyLow(m_symbol, m_timeframe, 1, 1, low);

                        if(signal == 100.0)
                          {
                           // 动能策略绝不扛单！止损直接挂在突破大阳线的最低点下方 50 点
                           double sl_pts = (SymbolInfoDouble(m_symbol, SYMBOL_ASK) - low[0]) / point + 50;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name, sl_pts, 10000);
                          }
                        else if(signal == -100.0)
                          {
                           // 止损直接挂在突破大阴线的最高点上方 50 点
                           double sl_pts = (high[0] - SymbolInfoDouble(m_symbol, SYMBOL_BID)) / point + 50;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name, sl_pts, 10000);
                          }

                        if(is_opened) last_bar_time = current_bar_time;
                     }

 //========================================================================
   // 退出：疯狗追踪止损 (已适配三维参数引擎)
   //========================================================================
   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        // 参数 1: 200点启动 (盈利 2美金开始干活)
                        // 参数 2: 150点跟随距离 (止损线距离现价 1.5美金)
                        // 参数 3: 30点步长 (价格每多跑 0.3美金，更新一次止损)
                        posMgr.ManageTrailingStop(m_symbol, m_magic_number, 200, 150, 30);
                     }
  };
//+------------------------------------------------------------------+