//+------------------------------------------------------------------+
//|                          CStrategy_Fractal_Breakout.mqh          |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.00"

#include "CStrategy.mqh"

class CStrategy_Fractal_Breakout : public CStrategy
  {
private:
   int               m_fractal_handle;
   double            m_buffer_pts; // 突破缓冲区 (蓝图：点外 2-3 个点差)

public:
                     // 严格蓝图：默认在碎形极值外加 30 点 (3 Pips) 的防假突破缓冲
                     CStrategy_Fractal_Breakout(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf,
                                                double bufferPts = 30.0)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_buffer_pts = bufferPts;
                        m_fractal_handle = iFractals(m_symbol, m_timeframe);

                        Print(m_strategy_name, " 碎形突破特种部队已就位 (虚拟挂单启动，突破缓冲: ", m_buffer_pts, " 点)");
                     }

                    ~CStrategy_Fractal_Breakout(void)
                     {
                        IndicatorRelease(m_fractal_handle);
                     }

   //========================================================================
   // 核心逻辑 8：扫描最近分形点 + 虚拟挂单突破
   //========================================================================
   virtual double    CalculateSignal(void) override
                     {
                        double upper[], lower[], close[];
                        
                        // 从第 2 根 K 线开始取 50 根 (因为最近的两根 K 线是无法确认分形的)
                        if(CopyBuffer(m_fractal_handle, 0, 2, 50, upper) <= 0 || 
                           CopyBuffer(m_fractal_handle, 1, 2, 50, lower) <= 0 ||
                           CopyClose(m_symbol, m_timeframe, 1, 1, close) <= 0) return 0;

                        double recent_up_fractal = EMPTY_VALUE;
                        double recent_dn_fractal = EMPTY_VALUE;

                        // 倒序扫描寻找最近的有效上分形(波峰)和下分形(波谷)
                        for(int i = 0; i < 50; i++)
                          {
                           if(recent_up_fractal == EMPTY_VALUE && upper[i] != EMPTY_VALUE) 
                              recent_up_fractal = upper[i];
                           if(recent_dn_fractal == EMPTY_VALUE && lower[i] != EMPTY_VALUE) 
                              recent_dn_fractal = lower[i];
                           if(recent_up_fractal != EMPTY_VALUE && recent_dn_fractal != EMPTY_VALUE) 
                              break;
                          }

                        if(recent_up_fractal == EMPTY_VALUE || recent_dn_fractal == EMPTY_VALUE) return 0.0;

                        double ask = SymbolInfoDouble(m_symbol, SYMBOL_ASK);
                        double bid = SymbolInfoDouble(m_symbol, SYMBOL_BID);
                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
                        double buffer = m_buffer_pts * point;

                        // 【虚拟挂单 - 做多】：上一根K线收盘还在波峰下，当前 Ask 价格瞬间突破了 (波峰 + 缓冲区)
                        if(close[0] < recent_up_fractal && ask >= recent_up_fractal + buffer)
                          {
                           Print("🚀 [碎形突破-多] 价格突破最近上分形颈线(", recent_up_fractal, ")！触发虚拟 Buy Stop 挂单！");
                           return 100.0;
                          }

                        // 【虚拟挂单 - 做空】：上一根K线收盘还在波谷上，当前 Bid 价格瞬间砸穿了 (波谷 - 缓冲区)
                        if(close[0] > recent_dn_fractal && bid <= recent_dn_fractal - buffer)
                          {
                           Print("🚀 [碎形突破-空] 价格跌穿最近下分形颈线(", recent_dn_fractal, ")！触发虚拟 Sell Stop 挂单！");
                           return -100.0;
                          }

                        return 0.0;
                     }

   //========================================================================
   // 进场：反向分形防守计算 (经典的 Williams 止损法)
   //========================================================================
   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, m_timeframe, 0);
                        if(current_bar_time == last_bar_time) return;

                        double signal = CalculateSignal();
                        if(signal == 0.0) return; 

                        // 再次获取分形点作为止损基准
                        double upper[], lower[];
                        if(CopyBuffer(m_fractal_handle, 0, 2, 50, upper) <= 0 || CopyBuffer(m_fractal_handle, 1, 2, 50, lower) <= 0) return;
                        
                        double recent_up_fractal = EMPTY_VALUE, recent_dn_fractal = EMPTY_VALUE;
                        for(int i = 0; i < 50; i++) {
                           if(recent_up_fractal == EMPTY_VALUE && upper[i] != EMPTY_VALUE) recent_up_fractal = upper[i];
                           if(recent_dn_fractal == EMPTY_VALUE && lower[i] != EMPTY_VALUE) recent_dn_fractal = lower[i];
                           if(recent_up_fractal != EMPTY_VALUE && recent_dn_fractal != EMPTY_VALUE) break;
                        }

                        double current_price = (signal == 100.0) ? SymbolInfoDouble(m_symbol, SYMBOL_ASK) : SymbolInfoDouble(m_symbol, SYMBOL_BID);
                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
                        double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight); 
                        bool is_opened = false;

                        if(signal == 100.0)
                          {
                           // 多单结构止损：经典法则，止损设在最近的【下分形(波谷)】下方 20 点
                           double dynamic_sl_pts = (current_price - recent_dn_fractal) / point + 20; 
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                          }
                        else if(signal == -100.0)
                          {
                           // 空单结构止损：经典法则，止损设在最近的【上分形(波峰)】上方 20 点
                           double dynamic_sl_pts = (recent_up_fractal - current_price) / point + 20; 
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                          }

                        if(is_opened) last_bar_time = current_bar_time; // 保证同一根K线只触发一次，防止连续扫损
                     }

   //========================================================================
   // 退出：疯狗追踪止损 (吃流动性爆发的肉)
   //========================================================================
   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        // 突破类策略的共性：动能爆发后绝不扛单，用 300 启动 150 步长贴身追踪
                        posMgr.ManageTrailingStop(m_symbol, m_magic_number, 1000, 1000, 500);
                     }
  };
//+------------------------------------------------------------------+