//+------------------------------------------------------------------+
//|                                                 CRiskManager.mqh |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.10" // 核心升级：自适应资金天花板

#include "CPositionManager.mqh"

class CRiskManager
  {
private:
   bool              m_is_cent_account; // 是否为美分账户 (USC)
   int               m_max_spread_pts;  // 黄金允许的最大点差 (Points)
   double            m_max_risk_pct;    // 单次开仓最大风险百分比
   double            m_max_drawdown_pct;// 极限回撤断臂线
   bool              m_use_commercial_guards;
   double            m_daily_loss_guard_pct;
   double            m_peak_drawdown_guard_pct;
   bool              m_persist_risk_pause;
   bool              m_is_risk_paused;
   int               m_day_key;
   double            m_day_start_equity;
   double            m_peak_equity;

   int               CurrentDayKey(void)
                     {
                        MqlDateTime time;
                        TimeToStruct(TimeCurrent(), time);
                        return time.year * 1000 + time.day_of_year;
                     }

   string            PauseGlobalName(void)
                     {
                        return "QuantumKing_RiskPause_" + IntegerToString((long)AccountInfoInteger(ACCOUNT_LOGIN));
                     }

   void              SetRiskPaused(string reason)
                     {
                        m_is_risk_paused = true;
                        if(m_persist_risk_pause)
                           GlobalVariableSet(PauseGlobalName(), 1.0);
                        Print("🚨 [Commercial Guard] Trading paused: ", reason);
                     }

   void              ResetDailyBaselineIfNeeded(void)
                     {
                        int current_day = CurrentDayKey();
                        if(current_day == m_day_key) return;

                        m_day_key = current_day;
                        m_day_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
                        if(!m_persist_risk_pause)
                           m_is_risk_paused = false;
                     }

public:
                     // 默认关闭美分账户(使用标准USD)，黄金点差限制400点，风控红线20%
                     CRiskManager(bool isCentAccount = false,
                                  int maxSpreadPts = 400,
                                  double maxRiskPct = 0.02,
                                  double maxDrawdownPct = 0.20,
                                  bool useCommercialGuards = false,
                                  double dailyLossGuardPct = 0.04,
                                  double peakDrawdownGuardPct = 0.10,
                                  bool persistRiskPause = true,
                                  bool resetRiskPause = false)
                     {
                        m_is_cent_account = isCentAccount;
                        m_max_spread_pts = maxSpreadPts;
                        m_max_risk_pct = maxRiskPct;
                        m_max_drawdown_pct = maxDrawdownPct;
                        m_use_commercial_guards = useCommercialGuards;
                        m_daily_loss_guard_pct = dailyLossGuardPct;
                        m_peak_drawdown_guard_pct = peakDrawdownGuardPct;
                        m_persist_risk_pause = persistRiskPause;
                        m_is_risk_paused = false;
                        m_day_key = CurrentDayKey();
                        m_day_start_equity = AccountInfoDouble(ACCOUNT_EQUITY);
                        m_peak_equity = m_day_start_equity;

                        if(resetRiskPause && GlobalVariableCheck(PauseGlobalName()))
                           GlobalVariableDel(PauseGlobalName());

                        if(m_persist_risk_pause && GlobalVariableCheck(PauseGlobalName()))
                           m_is_risk_paused = (GlobalVariableGet(PauseGlobalName()) > 0.0);
                     }
                    ~CRiskManager(void) {}

   //========================================================================
   // 1. 全局环境过滤器：点差检测
   //========================================================================
   bool              IsTradeEnvironmentSafe(string symbol)
                     {
                        long spread = SymbolInfoInteger(symbol, SYMBOL_SPREAD);
                        if(spread > m_max_spread_pts)
                          {
                           Print("⚠️ [风控拦截] 当前点差 ", spread, " 超过允许上限 ", m_max_spread_pts, "，禁止开仓！");
                           return false;
                          }
                        return true;
                     }

   //========================================================================
   // 2. 自适应仓位计算 (核心升级：净值天花板算法)
   //========================================================================
   double            CalculateSafeLotSize(string symbol, double customRiskPct = 0)
                     {
                        double risk_pct = (customRiskPct > 0) ? customRiskPct : m_max_risk_pct;
                        double equity = AccountInfoDouble(ACCOUNT_EQUITY);
                        
                        double min_lot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MIN);
                        double max_lot = SymbolInfoDouble(symbol, SYMBOL_VOLUME_MAX);
                        double lot_step = SymbolInfoDouble(symbol, SYMBOL_VOLUME_STEP);

                        // 基础风险测算 (假设单兵遇到 1000 点的极限止损)
                        double tick_value = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_VALUE);
                        double tick_size = SymbolInfoDouble(symbol, SYMBOL_TRADE_TICK_SIZE);
                        double point = SymbolInfoDouble(symbol, SYMBOL_POINT);
                        
                        double risk_money = equity * risk_pct;
                        double sl_points = 1000; 
                        double loss_per_lot = (sl_points * point) / tick_size * tick_value;
                        
                        double calculated_lot = risk_money / loss_per_lot;
                        double final_lot = MathFloor(calculated_lot / lot_step) * lot_step;

                        // =========================================================
                        // 🛡️ 机构级护城河：自适应净值天花板 (解决多兵种+网格的乘数效应)
                        // =========================================================
                        
                        // 规则：标准 USD 账户中，每 1000 美金净值，首单极限只允许开 0.01 手
                        double dynamic_max_lot = MathFloor(equity / 1000.0) * 0.01; 
                        
                        // 底线防守：如果你账户只有 400 刀，上面的公式算出是 0，EA会罢工。
                        // 所以这里强行托底，再小的账户，也允许开出券商允许的最低手数 (通常是 0.01)
                        if(dynamic_max_lot < min_lot) dynamic_max_lot = min_lot;
                        
                        // 红线防守：如果账户滚到 20 万美金，单笔首单也不能瞎开，最高锁定 1.0 手。
                        if(dynamic_max_lot > 1.0) dynamic_max_lot = 1.0;

                        // 最终裁决：如果上面风险算出的仓位，超过了净值天花板，强行压扁！
                        if(final_lot > dynamic_max_lot) final_lot = dynamic_max_lot;

                        // 券商极限合规校验
                        if(final_lot < min_lot) final_lot = min_lot;
                        if(final_lot > max_lot) final_lot = max_lot;

                        return final_lot;
                     }
                     
   //========================================================================
   // 3. 终极安全气囊：全局净值回撤监控
   //========================================================================
   void              CheckEmergencyStop(CPositionManager *posMgr)
                     {
                        if(PositionsTotal() == 0) return;

                        double balance = AccountInfoDouble(ACCOUNT_BALANCE);
                        double equity = AccountInfoDouble(ACCOUNT_EQUITY);
                        double floating_loss = balance - equity;

                        if(floating_loss <= 0) return;

                        double drawdown_pct = floating_loss / balance;

                        // 触及 20% 死亡红线，果断断臂求生！
                        if(drawdown_pct >= m_max_drawdown_pct)
                          {
                           Print("🚨🚨🚨 [警报] 触发终极安全气囊！当前浮亏: $", floating_loss, "，占账户 ", drawdown_pct*100, "%！强制执行全仓平仓！");
                           posMgr.EmergencyCloseAll();
                          }
                     }

   //========================================================================
   // 4. Commercial risk guards: daily loss + peak equity protection
   //========================================================================
   bool              CheckCommercialRiskGuards(CPositionManager *posMgr)
                     {
                        if(!m_use_commercial_guards) return true;

                        ResetDailyBaselineIfNeeded();

                        double equity = AccountInfoDouble(ACCOUNT_EQUITY);
                        if(equity > m_peak_equity)
                           m_peak_equity = equity;

                        if(m_is_risk_paused)
                           return false;

                        if(m_day_start_equity > 0.0)
                          {
                           double daily_dd = (m_day_start_equity - equity) / m_day_start_equity;
                           if(daily_dd >= m_daily_loss_guard_pct)
                             {
                              posMgr.EmergencyCloseAll();
                              SetRiskPaused("daily loss guard");
                              return false;
                             }
                          }

                        if(m_peak_equity > 0.0)
                          {
                           double peak_dd = (m_peak_equity - equity) / m_peak_equity;
                           if(peak_dd >= m_peak_drawdown_guard_pct)
                             {
                              posMgr.EmergencyCloseAll();
                              SetRiskPaused("peak equity drawdown guard");
                              return false;
                             }
                          }

                        return true;
                     }
  };
//+------------------------------------------------------------------+
