//+------------------------------------------------------------------+
//|                                             CPositionManager.mqh |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.20" // 核心升级：均价解套与非马丁网格

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

class CPositionManager
  {
private:
   CTrade            m_trade;        
   CPositionInfo     m_position;     

   // --- Quantum King 核心参数 ---
   int               m_breakeven_pts;   // 均价微利解套点数 (抛弃固定美元)
   int               m_grid_spacing;    // 网格加仓物理距离 (点数)
   int               m_max_grids;       // 最大允许加仓次数

public:
                     // 构造函数升级：黄金默认 1000 点间距 (10美金)，反弹 150 点 (1.5美金) 即可解套！
                     CPositionManager(int breakevenPts = 150, int gridSpacing = 1000, int maxGrids = 10) 
                     {
                        m_trade.SetDeviationInPoints(30);
                        m_trade.SetAsyncMode(true); 
                        
                        m_breakeven_pts = breakevenPts;
                        m_grid_spacing = gridSpacing;
                        m_max_grids = maxGrids;
                     }
                    ~CPositionManager(void) {}

   //========================================================================
   // 1. 拦截与开仓执行 (附带首单物理锁)
   //========================================================================
   bool              ExecuteOrder(string symbol, ENUM_ORDER_TYPE orderType, double volume, int magicNumber, string comment="")
                     {
                        if(HasPosition(symbol, magicNumber)) return false; // 物理锁
                        
                        m_trade.SetExpertMagicNumber(magicNumber);
                        if(orderType == ORDER_TYPE_BUY) return m_trade.Buy(volume, symbol, 0, 0, 0, comment);
                        else return m_trade.Sell(volume, symbol, 0, 0, 0, comment);
                     }

   bool              ExecuteOrderWithSLTP(string symbol, ENUM_ORDER_TYPE orderType, double volume, int magicNumber, string comment, double sl_pts, double tp_pts=0)
                     {
                        // 🚀 修复点 1：补齐了这里缺失的右括号 ')'
                        if(HasPosition(symbol, magicNumber)) return false; // 物理锁
                        
                        m_trade.SetExpertMagicNumber(magicNumber);
                        double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
                        double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
                        double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
                        
                        double sl=0, tp=0;
                        if(orderType == ORDER_TYPE_BUY)
                          {
                           sl = ask - sl_pts * point;
                           tp = (tp_pts > 0) ? ask + tp_pts * point : 0;
                           return m_trade.Buy(volume, symbol, ask, sl, tp, comment);
                          }
                        else
                          {
                           sl = bid + sl_pts * point;
                           tp = (tp_pts > 0) ? bid - tp_pts * point : 0;
                           return m_trade.Sell(volume, symbol, bid, sl, tp, comment);
                          }
                     }

   //========================================================================
   // 2. 【核心重构：无马丁均价解套网格系统】
   //========================================================================
   void              ManagePositions(string symbol, int magicNumber)
                     {
                        double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
                        double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
                        double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);

                        int buy_count = 0, sell_count = 0;
                        double buy_total_vol = 0, sell_total_vol = 0;
                        double buy_total_cost = 0, sell_total_cost = 0;
                        double lowest_buy = 999999, highest_sell = 0;

                        // 步骤 A：扫瞄阵地，计算均价与极值
                        for(int i = PositionsTotal() - 1; i >= 0; i--)
                          {
                           if(m_position.SelectByIndex(i) && m_position.Symbol() == symbol && m_position.Magic() == magicNumber)
                             {
                              double vol = m_position.Volume();
                              double price = m_position.PriceOpen();

                              if(m_position.PositionType() == POSITION_TYPE_BUY)
                                {
                                 buy_count++;
                                 buy_total_vol += vol;
                                 buy_total_cost += (price * vol);
                                 if(price < lowest_buy) lowest_buy = price;
                                }
                              else if(m_position.PositionType() == POSITION_TYPE_SELL)
                                {
                                 sell_count++;
                                 sell_total_vol += vol;
                                 sell_total_cost += (price * vol);
                                 if(price > highest_sell) highest_sell = price;
                                }
                             }
                          }

                        // 步骤 B：多头网格处理 (解套与等量加仓)
                        if(buy_count > 0)
                          {
                           double avg_buy_price = buy_total_cost / buy_total_vol; // 动态均价
                           
                           // [微利解套]：价格反弹，越过多头平均成本价
                           if(bid >= avg_buy_price + m_breakeven_pts * point)
                             {
                              CloseAllByMagic(symbol, magicNumber, POSITION_TYPE_BUY);
                              Print("✅ [网格解套] 多头部队越过均价(", avg_buy_price, ")，微利安全撤退！");
                             }
                           // [网格加仓]：跌破间距，执行等量非马丁加仓
                           else if(buy_count <= m_max_grids && ask <= lowest_buy - m_grid_spacing * point)
                             {
                              double base_vol = buy_total_vol / buy_count; // 等量加仓，拒绝翻倍
                              m_trade.SetExpertMagicNumber(magicNumber);
                              m_trade.Buy(base_vol, symbol, ask, 0, 0, "Grid Buy");
                              Print("📉 [网格防御] 部署第 ", buy_count, " 层多头网格！拉低均价！");
                             }
                          }

                        // 步骤 C：空头网格处理
                        if(sell_count > 0)
                          {
                           double avg_sell_price = sell_total_cost / sell_total_vol;
                           
                           if(ask <= avg_sell_price - m_breakeven_pts * point)
                             {
                              CloseAllByMagic(symbol, magicNumber, POSITION_TYPE_SELL);
                              Print("✅ [网格解套] 空头部队越过均价(", avg_sell_price, ")，微利安全撤退！");
                             }
                           else if(sell_count <= m_max_grids && bid >= highest_sell + m_grid_spacing * point)
                             {
                              double base_vol = sell_total_vol / sell_count; 
                              m_trade.SetExpertMagicNumber(magicNumber);
                              m_trade.Sell(base_vol, symbol, bid, 0, 0, "Grid Sell");
                              Print("📈 [网格防御] 部署第 ", sell_count, " 层空头网格！拉高均价！");
                             }
                          }
                     }

   //========================================================================
   // 3. 辅助武器库与系统锁 (三维参数独立版，适配所有 12 种子策略)
   //========================================================================
   void              ManageTrailingStop(string symbol, int magicNumber, double activation_pts, double distance_pts, double step_pts)
                     {
                        double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
                        double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
                        double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);

                        for(int i = PositionsTotal() - 1; i >= 0; i--)
                          {
                           if(m_position.SelectByIndex(i) && m_position.Symbol() == symbol && m_position.Magic() == magicNumber)
                             {
                              if(m_position.PositionType() == POSITION_TYPE_BUY)
                                {
                                 // 1. 启动线：盈利达到 activation_pts 才开启追踪
                                 if(bid - m_position.PriceOpen() >= activation_pts * point)
                                   {
                                    // 2. 风控线：止损永远距离现价 distance_pts
                                    double new_sl = bid - distance_pts * point; 
                                    
                                    // 3. 防刷线：新止损必须比老止损高出 step_pts，才发送指令
                                    if(m_position.StopLoss() == 0 || (new_sl - m_position.StopLoss() >= step_pts * point))
                                      {
                                       m_trade.PositionModify(m_position.Ticket(), new_sl, m_position.TakeProfit());
                                      }
                                   }
                                }
                              else if(m_position.PositionType() == POSITION_TYPE_SELL)
                                {
                                 // 1. 启动线
                                 if(m_position.PriceOpen() - ask >= activation_pts * point)
                                   {
                                    // 2. 风控线
                                    double new_sl = ask + distance_pts * point;
                                    
                                    // 3. 防刷线
                                    if(m_position.StopLoss() == 0 || (m_position.StopLoss() - new_sl >= step_pts * point))
                                      {
                                       m_trade.PositionModify(m_position.Ticket(), new_sl, m_position.TakeProfit());
                                      }
                                   }
                                }
                             }
                          }
                     }

   //========================================================================
   // 【v1.15 教科书 SMC 风控】保本引擎：盈利越过 trigger_pts 后把 SL 拉到入场价
   //========================================================================
   void              ManageBreakEven(string symbol, int magicNumber, double trigger_pts)
                     {
                        double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
                        double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
                        double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
                        for(int i = PositionsTotal() - 1; i >= 0; i--)
                          {
                           if(m_position.SelectByIndex(i) && m_position.Symbol() == symbol && m_position.Magic() == magicNumber)
                             {
                              double entry = m_position.PriceOpen();
                              double cur_sl = m_position.StopLoss();
                              if(m_position.PositionType() == POSITION_TYPE_BUY)
                                {
                                 if(bid - entry >= trigger_pts * point)
                                   {
                                    if(cur_sl < entry) // 只往保本/盈利方向推
                                       m_trade.PositionModify(m_position.Ticket(), entry, m_position.TakeProfit());
                                   }
                                }
                              else if(m_position.PositionType() == POSITION_TYPE_SELL)
                                {
                                 if(entry - ask >= trigger_pts * point)
                                   {
                                    if(cur_sl == 0 || cur_sl > entry)
                                       m_trade.PositionModify(m_position.Ticket(), entry, m_position.TakeProfit());
                                   }
                                }
                             }
                          }
                     }

   // 🚀 修复点 2：帮你把刚才不小心删掉的关单、查询等关键函数补回来了
   void              CloseAllByMagic(string symbol, int magicNumber, ENUM_POSITION_TYPE posType)
                     {
                        for(int i = PositionsTotal() - 1; i >= 0; i--)
                          {
                           if(m_position.SelectByIndex(i) && m_position.Symbol() == symbol && m_position.Magic() == magicNumber && m_position.PositionType() == posType)
                             {
                              m_trade.PositionClose(m_position.Ticket());
                             }
                          }
                     }

   void              EmergencyCloseAll(void)
                     {
                        for(int i = PositionsTotal() - 1; i >= 0; i--)
                          {
                           if(m_position.SelectByIndex(i))
                              m_trade.PositionClose(m_position.Ticket());
                          }
                     }

   bool              HasPosition(string symbol, int magicNumber)
                     {
                        for(int i = PositionsTotal() - 1; i >= 0; i--)
                          {
                           if(m_position.SelectByIndex(i) && m_position.Symbol() == symbol && m_position.Magic() == magicNumber)
                              return true;
                          }
                        return false;
                     }
                     
   // 【为下一步计划 3 准备的底层雷达】：查询全场同向订单 (无视魔术码)
   bool              HasGlobalPosition(string symbol, ENUM_POSITION_TYPE posType)
                     {
                        for(int i = PositionsTotal() - 1; i >= 0; i--)
                          {
                           if(m_position.SelectByIndex(i) && m_position.Symbol() == symbol && m_position.PositionType() == posType)
                              return true;
                          }
                        return false;
                     }
  }; // 🚀 这里补上了类结尾的大括号
//+------------------------------------------------------------------+