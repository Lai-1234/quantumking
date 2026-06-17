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

public:
                     CStrategyManager(CRiskManager *riskMgr, CPositionManager *posMgr) 
                     { 
                        m_strategy_count = 0; 
                        m_risk_mgr = riskMgr;
                        m_pos_mgr = posMgr;
                        
                        m_is_manual_paused = false; 

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