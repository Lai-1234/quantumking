//+------------------------------------------------------------------+
//|                                     CStrategy_ADX_Trend.mqh      |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.00"

#include "CStrategy.mqh"

class CStrategy_ADX_Trend : public CStrategy
  {
private:
   int               m_adx_handle;
   int               m_adx_period;
   double            m_adx_threshold; // 强趋势分水岭 (蓝图要求: 25)

public:
                     // 严格蓝图：默认 14 周期，ADX 强趋势阈值锁定 25
                     CStrategy_ADX_Trend(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf,
                                         int adxPeriod = 14, double adxThreshold = 25.0)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_adx_period = adxPeriod;
                        m_adx_threshold = adxThreshold;

                        m_adx_handle = iADX(m_symbol, m_timeframe, m_adx_period);

                        Print(m_strategy_name, " 狂暴追击部队已就位 (ADX > ", m_adx_threshold, " + DI 交叉引爆)");
                     }

                    ~CStrategy_ADX_Trend(void)
                     {
                        IndicatorRelease(m_adx_handle);
                     }

   //========================================================================
   // 核心逻辑 3：ADX > 25 确认单边 + DMI (+DI/-DI) 交叉引爆
   //========================================================================
   virtual double    CalculateSignal(void) override
                     {
                        double adx_main[], plus_di[], minus_di[];

                        // 拷贝 ADX 的三根线：0 = MAIN(主线), 1 = PLUSDI(+DI), 2 = MINUSDI(-DI)
                        if(CopyBuffer(m_adx_handle, 0, 1, 2, adx_main) <= 0 ||
                           CopyBuffer(m_adx_handle, 1, 1, 2, plus_di) <= 0 ||
                           CopyBuffer(m_adx_handle, 2, 1, 2, minus_di) <= 0) return 0;

                        // 【核心过滤】：如果 ADX 主线没有超过 25，说明市场毫无波澜，直接拒绝交易
                        if(adx_main[0] < m_adx_threshold) return 0.0;

                        // 【做多追击】：ADX 强劲，且 +DI 刚刚从下方上穿 -DI (多头瞬间夺取控制权)
                        if(plus_di[0] > minus_di[0] && plus_di[1] <= minus_di[1])
                          {
                           Print("🚀 [ADX顺势-多] 波动率爆表(ADX=", adx_main[0], ")！+DI 上穿 -DI，执行激进追多！");
                           return 100.0;
                          }

                        // 【做空追击】：ADX 强劲，且 -DI 刚刚从下方上穿 +DI (空头瞬间夺取控制权)
                        if(minus_di[0] > plus_di[0] && minus_di[1] <= plus_di[1])
                          {
                           Print("🚀 [ADX顺势-空] 波动率爆表(ADX=", adx_main[0], ")！-DI 上穿 +DI，执行激进追空！");
                           return -100.0;
                          }

                        return 0.0;
                     }

   //========================================================================
   // 进场：结构性防守计算
   //========================================================================
   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, m_timeframe, 0);
                        if(current_bar_time == last_bar_time) return;

                        double signal = CalculateSignal();
                        if(signal == 0.0) return;

                        // 自动扫描近期 50 根 K 线，寻找波段极值点作为防守底线
                        double high_arr[], low_arr[];
                        if(CopyHigh(m_symbol, m_timeframe, 1, 50, high_arr) <= 0 || CopyLow(m_symbol, m_timeframe, 1, 50, low_arr) <= 0) return;

                        double swing_high = high_arr[ArrayMaximum(high_arr)];
                        double swing_low  = low_arr[ArrayMinimum(low_arr)];

                        double current_price = (signal == 100.0) ? SymbolInfoDouble(m_symbol, SYMBOL_ASK) : SymbolInfoDouble(m_symbol, SYMBOL_BID);
                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
                        double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight);
                        bool is_opened = false;

                        if(signal == 100.0)
                          {
                           // 多单结构止损：挂在近期低点下方 150 点
                           double dynamic_sl_pts = (current_price - swing_low) / point + 150;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                          }
                        else if(signal == -100.0)
                          {
                           // 空单结构止损：挂在近期高点上方 150 点
                           double dynamic_sl_pts = (swing_high - current_price) / point + 150;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, 10000);
                          }

                        if(is_opened) last_bar_time = current_bar_time;
                     }

   //========================================================================
   // 退出：趋势策略必须让利润狂奔
   //========================================================================
   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        // 既然是第一类顺势策略，共享大格局追踪止损 (1000启动, 500步长)
                        posMgr.ManageTrailingStop(m_symbol, m_magic_number, 1000, 1000, 500);
                     }
  };
//+------------------------------------------------------------------+
