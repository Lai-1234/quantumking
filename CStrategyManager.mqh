//+------------------------------------------------------------------+
//|                                             CStrategyManager.mqh |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.30" // 终极进化：智能分级锁 (隔离网格风险，释放优质信号)

#include "CStrategy.mqh"

enum ENUM_MARKET_REGIME
  {
   REGIME_LOW_VOL_RANGE,    // 低波动震荡 (适合均值回归)
   REGIME_HIGH_VOL_TREND,   // 高波动趋势 (适合顺势/突破)
   REGIME_DANGER_ZONE       // 危险期 (物理断电)
  };

class CStrategyManager
  {
private:
   CStrategy         *m_strategies[50]; 
   int               m_strategy_count;  
   CRiskManager      *m_risk_mgr;      
   CPositionManager  *m_pos_mgr;       
   int               m_atr_fast_handle;     
   int               m_atr_slow_handle; 

   bool              m_is_manual_paused; 
   bool              m_use_commercial_time_filter;
   bool              m_block_monday_entries;
   bool              m_block_friday_late_entries;
   int               m_friday_block_hour;
   bool              m_use_global_session_filter;
   int               m_session1_start;
   int               m_session1_end;
   int               m_session2_start;
   int               m_session2_end;
   bool              m_use_premium_window_filter;
   int               m_premium_window_start;
   int               m_premium_window_end;

   // --- 内部辅助：识别哪些是需要靠网格自救的“重装步兵” ---
   bool IsGridStrategy(int magicNumber)
   {
      // 10001: 布林带极值, 10006: 枢轴点背离, 10007: VWAP回归
      if(magicNumber == 10001 || magicNumber == 10006 || magicNumber == 10007) 
         return true;
      return false;
   }

   // --- 内部辅助：侦测场上是否已经有【网格部队】的阵地 ---
   bool HasActiveGridPosition(ENUM_POSITION_TYPE posType)
   {
      for(int i = PositionsTotal() - 1; i >= 0; i--)
      {
         ulong ticket = PositionGetTicket(i);
         if(ticket > 0)
         {
            if(PositionGetString(POSITION_SYMBOL) == _Symbol && 
               (ENUM_POSITION_TYPE)PositionGetInteger(POSITION_TYPE) == posType)
            {
               int magic = (int)PositionGetInteger(POSITION_MAGIC);
               if(IsGridStrategy(magic)) return true; // 发现同向的网格订单！
            }
         }
      }
      return false;
   }

   bool IsHourInRange(int hour, int startHour, int endHour)
   {
      if(startHour == endHour) return true;
      if(startHour < endHour)
         return (hour >= startHour && hour < endHour);
      return (hour >= startHour || hour < endHour);
   }

   bool IsCommercialEntryTimeAllowed(void)
   {
      if(!m_use_commercial_time_filter) return true;

      MqlDateTime time;
      TimeToStruct(TimeCurrent(), time);

      if(m_block_monday_entries && time.day_of_week == 1)
         return false;

      if(m_block_friday_late_entries && time.day_of_week == 5 && time.hour >= m_friday_block_hour)
         return false;

      if(m_use_premium_window_filter)
         return IsHourInRange(time.hour, m_premium_window_start, m_premium_window_end);

      if(m_use_global_session_filter)
        {
         bool in_session1 = IsHourInRange(time.hour, m_session1_start, m_session1_end);
         bool in_session2 = IsHourInRange(time.hour, m_session2_start, m_session2_end);
         return (in_session1 || in_session2);
        }

      return true;
   }

public:
                     CStrategyManager(CRiskManager *riskMgr,
                                      CPositionManager *posMgr,
                                      bool useCommercialTimeFilter = false,
                                      bool blockMondayEntries = true,
                                      bool blockFridayLateEntries = true,
                                      int fridayBlockHour = 14,
                                      bool useGlobalSessionFilter = false,
                                      int session1Start = 9,
                                      int session1End = 12,
                                      int session2Start = 14,
                                      int session2End = 17,
                                      bool usePremiumWindowFilter = false,
                                      int premiumWindowStart = 15,
                                      int premiumWindowEnd = 16) 
                     { 
                        m_strategy_count = 0; 
                        m_risk_mgr = riskMgr;
                        m_pos_mgr = posMgr;
                        
                        m_is_manual_paused = false; 
                        m_use_commercial_time_filter = useCommercialTimeFilter;
                        m_block_monday_entries = blockMondayEntries;
                        m_block_friday_late_entries = blockFridayLateEntries;
                        m_friday_block_hour = fridayBlockHour;
                        m_use_global_session_filter = useGlobalSessionFilter;
                        m_session1_start = session1Start;
                        m_session1_end = session1End;
                        m_session2_start = session2Start;
                        m_session2_end = session2End;
                        m_use_premium_window_filter = usePremiumWindowFilter;
                        m_premium_window_start = premiumWindowStart;
                        m_premium_window_end = premiumWindowEnd;

                        m_atr_fast_handle = iATR(_Symbol, PERIOD_M15, 7);
                        m_atr_slow_handle = iATR(_Symbol, PERIOD_M15, 50);
                     }

                    ~CStrategyManager(void) { Release(); }

   void              SetManualPause(bool isPaused) { m_is_manual_paused = isPaused; }

   void              AddStrategy(CStrategy *strategy)
                     {
                        if(m_strategy_count < 50)
                          {
                           m_strategies[m_strategy_count] = strategy;
                           m_strategy_count++;
                          }
                     }

   ENUM_MARKET_REGIME GetCurrentMarketRegime(void)
                     {
                        if(m_is_manual_paused) return REGIME_DANGER_ZONE;

                        MqlDateTime time;
                        TimeToStruct(TimeCurrent(), time);
                        
                        // 黄金在凌晨收盘前后的流动性极差，点差巨大，强行休息
                        if(time.hour == 23 || time.hour == 0) return REGIME_DANGER_ZONE;

                        double atr_fast[], atr_slow[];
                        if(CopyBuffer(m_atr_fast_handle, 0, 0, 1, atr_fast) <= 0) return REGIME_LOW_VOL_RANGE;
                        if(CopyBuffer(m_atr_slow_handle, 0, 0, 1, atr_slow) <= 0) return REGIME_LOW_VOL_RANGE;
                        
                        if(atr_fast[0] > atr_slow[0] * 1.2)
                           return REGIME_HIGH_VOL_TREND;
                           
                        return REGIME_LOW_VOL_RANGE;
                     }

   void              Release(void) 
                     { 
                        for(int i = 0; i < m_strategy_count; i++)
                          {
                           if(CheckPointer(m_strategies[i]) == POINTER_DYNAMIC)
                              delete m_strategies[i];
                          }
                        m_strategy_count = 0;
                     }

   //========================================================================
   // 🧠 大脑中枢主循环：【智能分级锁】核心实现
   //========================================================================
   void              OnTick(void)
                     {
                        ENUM_MARKET_REGIME currentRegime = GetCurrentMarketRegime();
                        
                        // 1. 全局风控自检：净值回撤 20% 红线检测
                        m_risk_mgr.CheckEmergencyStop(m_pos_mgr);
                        bool commercial_risk_ok = m_risk_mgr.CheckCommercialRiskGuards(m_pos_mgr);

                        // 2. 全局限流令：控制总持仓单量 (上限 6 单)
                        bool is_global_full = (PositionsTotal() >= 6);

                        // 3. 🚨【新武器：智能分级锁】只针对“网格部队”进行同向拦截
                        bool has_grid_buy = HasActiveGridPosition(POSITION_TYPE_BUY);
                        bool has_grid_sell = HasActiveGridPosition(POSITION_TYPE_SELL);

                        for(int i = 0; i < m_strategy_count; i++)
                          {
                           if(CheckPointer(m_strategies[i]) == POINTER_INVALID) continue;

                           // --- A. 永远优先执行防守 (退场、追踪止损、网格均价自救) ---
                           m_strategies[i].CheckExit(m_pos_mgr);

                           // --- B. 进攻权限预审 ---
                           if(currentRegime == REGIME_DANGER_ZONE || is_global_full) continue;
                           if(!commercial_risk_ok) continue;
                           if(!m_risk_mgr.IsTradeEnvironmentSafe(_Symbol)) continue;
                           if(!IsCommercialEntryTimeAllowed()) continue;

                           string name = m_strategies[i].GetName();
                           int magic = m_strategies[i].GetMagicNumber(); // 确保 CStrategy.mqh 有此方法
                           bool is_grid_unit = IsGridStrategy(magic);

                           // 波动率雷达：错峰调度顺势与回归策略
                           if(StringFind(name, "顺势") >= 0 && currentRegime != REGIME_HIGH_VOL_TREND) continue;
                           if(StringFind(name, "回归") >= 0 && currentRegime == REGIME_HIGH_VOL_TREND) continue;

                           // --- C. 信号计算与分级过滤 ---
                           double signal = m_strategies[i].CalculateSignal();

                           if(signal == 100.0) // 策略想做多
                             {
                              // 如果是【网格兵种】，且场上已经有【网格多单】，为了防止风险重叠，坚决拦截！
                              if(is_grid_unit && has_grid_buy) continue; 
                              
                              // 只有过了上面那关，或者是【SMC/Fibo/突破】这类非网格兵种，才允许开仓
                              m_strategies[i].CheckEntry(m_pos_mgr, m_risk_mgr);
                              
                              // 如果成功开启的是网格单，立即同步状态位，拦截后面其他的网格兵种
                              if(is_grid_unit) has_grid_buy = true;
                             }
                           else if(signal == -100.0) // 策略想做空
                             {
                              if(is_grid_unit && has_grid_sell) continue;
                              
                              m_strategies[i].CheckEntry(m_pos_mgr, m_risk_mgr);
                              
                              if(is_grid_unit) has_grid_sell = true;
                             }
                          }
                     }
  };
