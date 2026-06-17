//+------------------------------------------------------------------+
//|                             CStrategy_Pivot_Divergence.mqh       |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.00"

#include "CStrategy.mqh"

class CStrategy_Pivot_Divergence : public CStrategy
  {
private:
   int               m_rsi_handle;
   int               m_rsi_period;

public:
                     // 严格蓝图：加载 RSI 检测背离
                     CStrategy_Pivot_Divergence(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf,
                                                int rsiPeriod = 14)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_rsi_period = rsiPeriod;
                        m_rsi_handle = iRSI(m_symbol, m_timeframe, m_rsi_period, PRICE_CLOSE);

                        Print(m_strategy_name, " 枢轴点狙击部队已就位 (Daily R2/S2 + RSI 背离检测)");
                     }

                    ~CStrategy_Pivot_Divergence(void)
                     {
                        IndicatorRelease(m_rsi_handle);
                     }

   // 辅助函数：判断是否为波谷 (V型底)
   bool              IsTrough(const double &arr[], int idx)
                     {
                        return (arr[idx] < arr[idx+1] && arr[idx] <= arr[idx-1]);
                     }

   // 辅助函数：判断是否为波峰 (A型顶)
   bool              IsPeak(const double &arr[], int idx)
                     {
                        return (arr[idx] > arr[idx+1] && arr[idx] >= arr[idx-1]);
                     }

   //========================================================================
   // 核心逻辑 5：计算日线枢轴点 + 扫描 RSI 价格背离
   //========================================================================
   virtual double    CalculateSignal(void) override
                     {
                        // 1. 获取昨日日线数据，计算标准枢轴点 (Pivot Points)
                        double d_high[], d_low[], d_close[];
                        if(CopyHigh(m_symbol, PERIOD_D1, 1, 1, d_high) <= 0 ||
                           CopyLow(m_symbol, PERIOD_D1, 1, 1, d_low) <= 0 ||
                           CopyClose(m_symbol, PERIOD_D1, 1, 1, d_close) <= 0) return 0;

                        double P = (d_high[0] + d_low[0] + d_close[0]) / 3.0;
                        double R2 = P + (d_high[0] - d_low[0]);
                        double S2 = P - (d_high[0] - d_low[0]);

                        // 2. 获取近期 50 根 M15 K线数据，倒序排列 (索引 0 为当前未收盘K线)
                        double high[], low[], rsi[];
                        ArrayResize(high, 50); ArraySetAsSeries(high, true);
                        ArrayResize(low, 50);  ArraySetAsSeries(low, true);
                        ArrayResize(rsi, 50);  ArraySetAsSeries(rsi, true);

                        if(CopyHigh(m_symbol, m_timeframe, 0, 50, high) <= 0 ||
                           CopyLow(m_symbol, m_timeframe, 0, 50, low) <= 0 ||
                           CopyBuffer(m_rsi_handle, 0, 0, 50, rsi) <= 0) return 0;

                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

                        // 3. 寻找近期与前期的波段极值点
                        int prev_low_idx = ArrayMinimum(low, 5, 40);   // 过去的波谷区
                        int recent_low_idx = ArrayMinimum(low, 1, 4);  // 近期的波谷区 (刚收盘的这几根)

                        int prev_high_idx = ArrayMaximum(high, 5, 40); // 过去的波峰区
                        int recent_high_idx = ArrayMaximum(high, 1, 4); // 近期的波峰区

                        // 【做多抄底】：价格砸到 S2 支撑位 + 价格创新低 + RSI 没创新低 (底背离)
                        if(IsTrough(low, recent_low_idx) && IsTrough(low, prev_low_idx))
                          {
                           // 检查价格是否触及或跌破 S2 (允许 150 点误差接针)
                           if(low[recent_low_idx] <= S2 + 150 * point)
                             {
                              if(low[recent_low_idx] < low[prev_low_idx] && rsi[recent_low_idx] > rsi[prev_low_idx])
                                {
                                 Print("🔴 [S2枢轴点抄底] 价格跌至S2(", S2, ")。价格创新低，RSI底背离！动能衰竭，接针做多！");
                                 return 100.0;
                                }
                             }
                          }

                        // 【做空摸顶】：价格飙到 R2 阻力位 + 价格创新高 + RSI 没创新高 (顶背离)
                        if(IsPeak(high, recent_high_idx) && IsPeak(high, prev_high_idx))
                          {
                           // 检查价格是否触及或突破 R2
                           if(high[recent_high_idx] >= R2 - 150 * point)
                             {
                              if(high[recent_high_idx] > high[prev_high_idx] && rsi[recent_high_idx] < rsi[prev_high_idx])
                                {
                                 Print("🟢 [R2枢轴点摸顶] 价格飙至R2(", R2, ")。价格创新高，RSI顶背离！买盘衰竭，接针做空！");
                                 return -100.0;
                                }
                             }
                          }

                        return 0.0;
                     }

   //========================================================================
   // 进场：极值接针，无需结构硬止损
   //========================================================================
   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, m_timeframe, 0);
                        if(current_bar_time == last_bar_time) return;

                        double signal = CalculateSignal();
                        if(signal == 0.0) return;

                        double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight);
                        bool is_opened = false;

                        // 第二类回归策略：只下市价单首单，止损和补仓全权交由网格系统接管
                        if(signal == 100.0)
                           is_opened = posMgr.ExecuteOrder(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name + " 首单(多)");
                        else if(signal == -100.0)
                           is_opened = posMgr.ExecuteOrder(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name + " 首单(空)");

                        if(is_opened) last_bar_time = current_bar_time;
                     }

   //========================================================================
   // 退出：调用大脑的网格自救系统
   //========================================================================
   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        // 与布林带部队同等待遇：震荡市网格收割机
                        posMgr.ManagePositions(m_symbol, m_magic_number);
                        //posMgr.ManageTrailingStop(m_symbol, m_magic_number, 300, 150);
                     }
  };
//+------------------------------------------------------------------+
