//+------------------------------------------------------------------+
//|                          CStrategy_Pulse_Momentum.mqh            |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.10" // 核心升级：XAUUSD防秒杀与抗锯齿校准版

#include "CStrategy.mqh"

class CStrategy_Pulse_Momentum : public CStrategy
  {
private:
   int               m_streak_count; // 连续 K 线数量 (蓝图: 5根)
   double            m_pulse_pts;    // 动能爆发最小点数 

public:
                     // 🛠️ 【修复 1】：将触发门槛从 40 点(0.4美金) 大幅提高到 300 点(3美金)！
                     // 只有 5 分钟内出现真正的暴力单边拉升，才会被判定为脉冲，彻底过滤震荡杂波。
                     CStrategy_Pulse_Momentum(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf,
                                              int streakCount = 5, double pulsePts = 300.0)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_streak_count = streakCount;
                        m_pulse_pts = pulsePts;

                        Print(m_strategy_name, " 极限微操刺客(重装版)已就位 (M1级别 ", m_streak_count, " 连击 + ", m_pulse_pts, " 点暴走侦测)");
                     }

                    ~CStrategy_Pulse_Momentum(void) {}

   //========================================================================
   // 核心逻辑 9：M1 降维打击，扫描极速情绪失控
   //========================================================================
   virtual double    CalculateSignal(void) override
                     {
                        // 强制拉取 M1 (1分钟) 级别的微观数据，无视策略挂载的 M15 周期
                        double close[], open[], high[], low[];
                        ArraySetAsSeries(close, true); ArraySetAsSeries(open, true);
                        ArraySetAsSeries(high, true);  ArraySetAsSeries(low, true);

                        // 抓取刚刚收盘的 5 根 M1 K 线 (索引 1 到 5)
                        if(CopyClose(m_symbol, PERIOD_M1, 1, m_streak_count, close) <= 0 || 
                           CopyOpen(m_symbol, PERIOD_M1, 1, m_streak_count, open) <= 0 ||
                           CopyHigh(m_symbol, PERIOD_M1, 1, m_streak_count, high) <= 0 ||
                           CopyLow(m_symbol, PERIOD_M1, 1, m_streak_count, low) <= 0) return 0;

                        bool is_all_bull = true;
                        bool is_all_bear = true;

                        // 检验【连续性】：必须根根都是阳线，或者根根都是阴线，绝不容许夹杂十字星或反向线
                        for(int i = 0; i < m_streak_count; i++)
                          {
                           if(close[i] <= open[i]) is_all_bull = false; 
                           if(close[i] >= open[i]) is_all_bear = false; 
                          }

                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

                        // 【做多极速追击】：5连阳 + 总拉升幅度 > 300点
                        if(is_all_bull)
                          {
                           double total_move = (close[0] - open[m_streak_count - 1]) / point;
                           if(total_move >= m_pulse_pts)
                             {
                              Print("🚀 [M1多头狂飙] 连续 ", m_streak_count, " 根一分钟大阳线！暴涨 ", total_move, " 点！散户踏空，我们追！");
                              return 100.0;
                             }
                          }

                        // 【做空极速追击】：5连阴 + 总暴跌幅度 > 300点
                        if(is_all_bear)
                          {
                           double total_move = (open[m_streak_count - 1] - close[0]) / point;
                           if(total_move >= m_pulse_pts)
                             {
                              Print("🚀 [M1空头狂飙] 连续 ", m_streak_count, " 根一分钟大阴线！暴跌 ", total_move, " 点！散户爆仓，我们追！");
                              return -100.0;
                             }
                          }

                        return 0.0;
                     }

   //========================================================================
   // 进场：动量防守底线
   //========================================================================
   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        // 🛠️ 【修复 2】：单兵阵地物理锁！
                        // 如果场上已经有这支部队的单子，绝对不允许它在一分钟后重复追单！
                        if(posMgr.HasPosition(m_symbol, m_magic_number)) return;

                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, PERIOD_M1, 0); 
                        if(current_bar_time == last_bar_time) return;

                        double signal = CalculateSignal();
                        if(signal == 0.0) return; 

                        // 提取这 5 根 K 线的最高点和最低点，作为起跳点
                        double high[], low[];
                        if(CopyHigh(m_symbol, PERIOD_M1, 1, m_streak_count, high) <= 0 || 
                           CopyLow(m_symbol, PERIOD_M1, 1, m_streak_count, low) <= 0) return;
                           
                        double pulse_origin_low = low[ArrayMinimum(low)];
                        double pulse_origin_high = high[ArrayMaximum(high)];

                        double current_price = (signal == 100.0) ? SymbolInfoDouble(m_symbol, SYMBOL_ASK) : SymbolInfoDouble(m_symbol, SYMBOL_BID);
                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
                        double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight); 
                        bool is_opened = false;

                        if(signal == 100.0)
                          {
                           // 🛠️ 【修复 3】：防秒杀止损！
                           // 将 20 点改为 200 点 (2美金)。即使有30-50点的点差和正常的毛刺回撤，单子也能安然存活！
                           double dynamic_sl_pts = (current_price - pulse_origin_low) / point + 200; 
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                          }
                        else if(signal == -100.0)
                          {
                           // 空单止损同样扩大到 200 点
                           double dynamic_sl_pts = (pulse_origin_high - current_price) / point + 200; 
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                          }

                        if(is_opened) last_bar_time = current_bar_time; 
                     }

//========================================================================
   // 退出：疯狗级微操追踪 (超短线快刀)
   //========================================================================
   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        // 参数 1: 300点启动 (只要赚 300 点就触发)
                        // 参数 2: 150点距离 (止损线死死咬在现价后方 150 点的位置，瞬间锁住 150 点纯利润！)
                        // 参数 3: 50点步长 (只要价格往前挪 50 点，止损就无情跟进)
                        posMgr.ManageTrailingStop(m_symbol, m_magic_number, 300, 150, 50);
                     }
  };
//+------------------------------------------------------------------+