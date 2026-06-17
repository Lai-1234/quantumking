//+------------------------------------------------------------------+
//|                                                    CStrategy.mqh |
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.00"

// 引入风控和订单模块，让策略类可以使用它们
#include "CRiskManager.mqh"
#include "CPositionManager.mqh"

class CStrategy
  {
protected:
   int               m_magic_number;   
   string            m_strategy_name;  
   double            m_weight;         
   string            m_symbol;         
   ENUM_TIMEFRAMES   m_timeframe;      

public:
                     CStrategy(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf)
                     {
                        m_strategy_name = name;
                        m_magic_number = magic;
                        m_weight = weight;
                        m_symbol = symbol;
                        m_timeframe = tf;
                     }
                    ~CStrategy(void) {}

   string            GetName(void) const { return m_strategy_name; }

   virtual double    CalculateSignal(void) { return 0.0; } 
   
   // 【修改点】：将双手(posMgr)和盾牌(riskMgr)递给具体的策略去用
   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) {}                   
   virtual void      CheckExit(CPositionManager *posMgr) {}    
  
  
   int GetMagicNumber(void) const { return m_magic_number; }                
  };
//+------------------------------------------------------------------+