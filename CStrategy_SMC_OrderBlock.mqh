//+------------------------------------------------------------------+
//|                        CStrategy_SMC_OrderBlock.mqh              |
//|                                      Copyright 2026, Lai Si Xiang|
//+------------------------------------------------------------------+
#property copyright "Copyright 2026, Lai Si Xiang"
#property version   "1.16" // 在 Fixed R:R 上叠加 Trail：捕捉到不了 TP 的中途利润 (修复 1:50 鬼魂利润流失)

#include "CStrategy.mqh"

class CStrategy_SMC_OrderBlock : public CStrategy
  {
private:
   int               m_fractal_handle;

   // --- 可调参数 (默认值 = 原始 v1.00 行为，改这里不会动旧逻辑) ---
   int               m_sl_buffer;     // 订单块外侧止损缓冲点数 (原始: 15)
   int               m_fib_tol;       // OTE 黄金坑容差点数 (原始: 150)
   int               m_scan_window;   // 结构扫描窗口 (原始: 80)
   double            m_sl_mult;       // 止损距离倍率 (原始: 1.0)
   bool              m_use_h4_filter; // 是否启用 H4 趋势顺势过滤 (研究最优: true)
   int               m_trail_start;   // 追踪启动点数 (原始: 1000)
   int               m_trail_dist;    // 追踪距离点数 (原始: 1000)
   int               m_trail_step;    // 追踪步长点数 (原始: 500)
   int               m_max_sl;        // 单笔止损上限点数 (5000 = 默认无限制 / 镜像 MA_Trend Max_SL)

   // --- H4 趋势过滤所需的均线句柄 ---
   int               m_ema_fast_h4;   // H4 EMA(50)
   int               m_ema_slow_h4;   // H4 EMA(200)

   // --- v1.13 KDJ 动能过滤 (M15 Stochastic 共振) ---
   bool              m_use_kdj_filter;
   int               m_kdj_period, m_kdj_d, m_kdj_s;
   int               m_kdj_ob, m_kdj_os;
   int               m_kdj_handle;

   // --- v1.13 ADX 趋势强度过滤 (拒绝盘整市场) ---
   bool              m_use_adx_filter;
   int               m_adx_period;
   double            m_adx_min;
   int               m_adx_handle;

   // --- v1.13 放松入场条件 (配合 KDJ/ADX 加层使用) ---
   double            m_ote_level1;    // OTE 上沿 (默认 0.705，放宽可设 0.50)
   double            m_ote_level2;    // OTE 下沿 (默认 0.786，放宽可设 0.90)
   bool              m_require_fvg;   // 是否强制要求 FVG (默认 true；关闭可显著增加触发频率)

   // --- v1.14 教科书 SMC：H4 BOS 高时间框结构方向过滤 ---
   bool              m_use_h4_bos_filter;
   int               m_h4_bos_lookback;  // 扫描多少根 H4 K 线回看
   int               m_h4_fractal_handle;

   // --- v1.15 Kelly 摘要：会话时段过滤 (伦敦 / 纽约) ---
   bool              m_use_session_filter;
   int               m_session1_start, m_session1_end;  // London window (服务器小时)
   int               m_session2_start, m_session2_end;  // NY window

   // --- v1.15 固定 R:R 出场 + 保本引擎 ---
   bool              m_use_fixed_rr;
   double            m_rr_ratio;          // 1:5 = 5.0
   bool              m_use_breakeven;
   int               m_be_trigger_pts;    // 盈利越过多少点 → SL 拉到入场价

   // --- v1.16 Fixed R:R + Trail 混合模式 (打开后 Trail 与 Fixed R:R 并行运行)
   //         用于捕捉到不了 R:R 高 TP 的中途利润
   bool              m_use_trail_with_rr;

   // 追踪结构破坏 (BMS) 的时间戳，防止重复计算
   datetime          m_last_up_frac_time;
   datetime          m_last_dn_frac_time;

   // 追踪【看涨订单块】的状态
   bool              m_bull_ob_active;
   double            m_bull_ob_high;
   double            m_bull_ob_low;

   // 追踪【看跌订单块】的状态
   bool              m_bear_ob_active;
   double            m_bear_ob_high;
   double            m_bear_ob_low;

   // 信号缓存 (修复双重调用 BUG)：
   // 经理 OnTick 会先调用 CalculateSignal() 取信号，再调用 CheckEntry() 下单；
   // 而 CheckEntry 内部还会再调一次 CalculateSignal。这一次因状态(m_bull_ob_active)
   // 已被清空，会返回 0 → 永远下不了单。改为把 CalculateSignal 算出的信号
   // 先记到 m_pending_signal，CheckEntry 直接读取这里。
   int               m_pending_signal; // +1 多 / -1 空 / 0 无

   // --- 内部辅助：H4 顺势许可 (dir +1 做多, -1 做空) ---
   bool              PassH4Filter(int dir)
                     {
                        if(!m_use_h4_filter) return true;
                        double f[], s[];
                        // 取数失败时不拦截，避免误杀
                        if(CopyBuffer(m_ema_fast_h4, 0, 0, 1, f) <= 0) return true;
                        if(CopyBuffer(m_ema_slow_h4, 0, 0, 1, s) <= 0) return true;
                        if(dir > 0) return (f[0] > s[0]);
                        return (f[0] < s[0]);
                     }

   // --- v1.13 KDJ 动能许可：避免在 KDJ 顶/底背离区入场 ---
   // 多头：拒绝 KDJ 超买区 (main > OB) 的买入；空头：拒绝 KDJ 超卖区 (main < OS) 的卖出
   bool              PassKDJFilter(int dir)
                     {
                        if(!m_use_kdj_filter) return true;
                        double main_arr[];
                        if(CopyBuffer(m_kdj_handle, 0, 1, 1, main_arr) <= 0) return true; // 取上一根已收线
                        if(dir > 0) return (main_arr[0] < m_kdj_ob); // 不在超买区 → 允许买
                        return (main_arr[0] > m_kdj_os);              // 不在超卖区 → 允许卖
                     }

   // --- v1.13 ADX 趋势强度许可：盘整市场 (ADX 低) 不下单 ---
   bool              PassADXFilter()
                     {
                        if(!m_use_adx_filter) return true;
                        double adx_arr[];
                        if(CopyBuffer(m_adx_handle, 0, 1, 1, adx_arr) <= 0) return true;
                        return (adx_arr[0] >= m_adx_min);
                     }

   // --- v1.14 H4 BOS 高时间框结构方向：最近一次 H4 BOS 是看涨还是看跌 ---
   // 返回: +1 看涨 BOS, -1 看跌 BOS, 0 没检测到
   int               GetH4BOSDirection()
                     {
                        double h4_high[], h4_low[], h4_close[], up_frac[], dn_frac[];
                        ArraySetAsSeries(h4_high, true); ArraySetAsSeries(h4_low, true);
                        ArraySetAsSeries(h4_close, true);
                        ArraySetAsSeries(up_frac, true); ArraySetAsSeries(dn_frac, true);

                        int N = m_h4_bos_lookback;
                        if(CopyHigh(m_symbol, PERIOD_H4, 0, N, h4_high) <= 0) return 0;
                        if(CopyLow(m_symbol, PERIOD_H4, 0, N, h4_low) <= 0) return 0;
                        if(CopyClose(m_symbol, PERIOD_H4, 0, N, h4_close) <= 0) return 0;
                        if(CopyBuffer(m_h4_fractal_handle, 0, 0, N, up_frac) <= 0) return 0;
                        if(CopyBuffer(m_h4_fractal_handle, 1, 0, N, dn_frac) <= 0) return 0;

                        // 找最近确认的 H4 上、下分形 (跳过仍在形成的 idx 0..2)
                        int up_idx = -1, dn_idx = -1;
                        for(int i = 3; i < N; i++)
                          {
                           if(up_idx == -1 && up_frac[i] != EMPTY_VALUE) up_idx = i;
                           if(dn_idx == -1 && dn_frac[i] != EMPTY_VALUE) dn_idx = i;
                           if(up_idx != -1 && dn_idx != -1) break;
                          }

                        // 找最近一次「H4 收线突破」事件 (BOS) — 看涨 / 看跌
                        int bull_bos_bar = -1, bear_bos_bar = -1;
                        if(up_idx > 1)
                          {
                           double up_level = h4_high[up_idx];
                           for(int i = up_idx - 1; i >= 1; i--)
                              if(h4_close[i] > up_level) { bull_bos_bar = i; break; }
                          }
                        if(dn_idx > 1)
                          {
                           double dn_level = h4_low[dn_idx];
                           for(int i = dn_idx - 1; i >= 1; i--)
                              if(h4_close[i] < dn_level) { bear_bos_bar = i; break; }
                          }

                        if(bull_bos_bar == -1 && bear_bos_bar == -1) return 0;
                        if(bull_bos_bar != -1 && bear_bos_bar == -1) return  1;
                        if(bear_bos_bar != -1 && bull_bos_bar == -1) return -1;
                        // 两边都有 — 取最近 (bar index 越小越新)
                        return (bull_bos_bar < bear_bos_bar) ? 1 : -1;
                     }

   // --- v1.14 H4 BOS 方向许可：M15 信号必须顺最近一次 H4 BOS 方向 ---
   // 检测不到 H4 BOS 时，宽松处理：不拦截 (避免在盘整 H4 上完全停摆)
   bool              PassH4BOSFilter(int dir)
                     {
                        if(!m_use_h4_bos_filter) return true;
                        int bos = GetH4BOSDirection();
                        if(bos == 0) return true;  // 未识别 → 不拦截
                        if(dir > 0) return (bos ==  1);
                        return            (bos == -1);
                     }

   // --- v1.15 会话时段过滤：只在伦敦 / 纽约 session 下单 (Kelly 教科书规则) ---
   // 输入是服务器小时；用户根据自己的 broker 时区配置
   bool              PassSessionFilter()
                     {
                        if(!m_use_session_filter) return true;
                        MqlDateTime t;
                        TimeToStruct(TimeCurrent(), t);
                        int h = t.hour;
                        if(h >= m_session1_start && h < m_session1_end) return true;
                        if(h >= m_session2_start && h < m_session2_end) return true;
                        return false;
                     }

public:
                     // 严格蓝图：机构订单流战法 + 斐波那契 OTE 共振 (参数化)
                     // ⚠️ 默认值 = 原始 v1.00 行为；研究最优解请在 quantumking.mq5 的 input 区设置
                     CStrategy_SMC_OrderBlock(string name, int magic, double weight, string symbol, ENUM_TIMEFRAMES tf,
                                              int    sl_buffer_pts = 15,
                                              int    fib_tol_pts   = 150,
                                              int    scan_window   = 80,
                                              double sl_mult       = 1.0,
                                              bool   use_h4_filter = false,
                                              int    h4_fast_ema   = 50,
                                              int    h4_slow_ema   = 200,
                                              int    trail_start   = 1000,
                                              int    trail_dist    = 1000,
                                              int    trail_step    = 500,
                                              int    max_sl_pts    = 5000,
                                              bool   use_kdj_filter = false,
                                              int    kdj_period     = 7,
                                              int    kdj_d          = 2,
                                              int    kdj_s          = 2,
                                              int    kdj_ob         = 70,
                                              int    kdj_os         = 30,
                                              bool   use_adx_filter = false,
                                              int    adx_period     = 14,
                                              double adx_min        = 20.0,
                                              double ote_level1     = 0.705,
                                              double ote_level2     = 0.786,
                                              bool   require_fvg    = true,
                                              bool   use_h4_bos_filter = false,
                                              int    h4_bos_lookback   = 50,
                                              bool   use_session_filter = false,
                                              int    session1_start    = 9,
                                              int    session1_end      = 12,
                                              int    session2_start    = 14,
                                              int    session2_end      = 17,
                                              bool   use_fixed_rr      = false,
                                              double rr_ratio          = 5.0,
                                              bool   use_breakeven     = false,
                                              int    be_trigger_pts    = 500,
                                              bool   use_trail_with_rr = false)
                     : CStrategy(name, magic, weight, symbol, tf)
                     {
                        m_fractal_handle = iFractals(m_symbol, m_timeframe);

                        m_sl_buffer     = sl_buffer_pts;
                        m_fib_tol       = fib_tol_pts;
                        m_scan_window   = scan_window;
                        m_sl_mult       = sl_mult;
                        m_use_h4_filter = use_h4_filter;
                        m_trail_start   = trail_start;
                        m_trail_dist    = trail_dist;
                        m_trail_step    = trail_step;
                        m_max_sl        = max_sl_pts;

                        m_use_kdj_filter = use_kdj_filter;
                        m_kdj_period     = kdj_period;
                        m_kdj_d          = kdj_d;
                        m_kdj_s          = kdj_s;
                        m_kdj_ob         = kdj_ob;
                        m_kdj_os         = kdj_os;
                        m_kdj_handle     = iStochastic(m_symbol, PERIOD_M15, m_kdj_period, m_kdj_d, m_kdj_s, MODE_SMA, STO_LOWHIGH);

                        m_use_adx_filter = use_adx_filter;
                        m_adx_period     = adx_period;
                        m_adx_min        = adx_min;
                        m_adx_handle     = iADX(m_symbol, PERIOD_M15, m_adx_period);

                        m_ote_level1     = ote_level1;
                        m_ote_level2     = ote_level2;
                        m_require_fvg    = require_fvg;

                        m_use_h4_bos_filter = use_h4_bos_filter;
                        m_h4_bos_lookback   = (h4_bos_lookback < 10 ? 10 : h4_bos_lookback);
                        m_h4_fractal_handle = iFractals(m_symbol, PERIOD_H4);

                        m_use_session_filter = use_session_filter;
                        m_session1_start     = session1_start;
                        m_session1_end       = session1_end;
                        m_session2_start     = session2_start;
                        m_session2_end       = session2_end;

                        m_use_fixed_rr   = use_fixed_rr;
                        m_rr_ratio       = (rr_ratio > 0 ? rr_ratio : 5.0);
                        m_use_breakeven  = use_breakeven;
                        m_be_trigger_pts = be_trigger_pts;
                        m_use_trail_with_rr = use_trail_with_rr;

                        m_ema_fast_h4 = iMA(m_symbol, PERIOD_H4, h4_fast_ema, 0, MODE_EMA, PRICE_CLOSE);
                        m_ema_slow_h4 = iMA(m_symbol, PERIOD_H4, h4_slow_ema, 0, MODE_EMA, PRICE_CLOSE);

                        m_bull_ob_active = false;
                        m_bear_ob_active = false;
                        m_last_up_frac_time = 0;
                        m_last_dn_frac_time = 0;
                        m_pending_signal = 0;

                        Print(m_strategy_name, " SMC v1.15 已就位 [入场] SLbuf:", m_sl_buffer,
                              " FibTol:", m_fib_tol, " Scan:", m_scan_window,
                              " SLx:", m_sl_mult, " MaxSL:", m_max_sl,
                              " OTE:", m_ote_level1, "-", m_ote_level2, " ReqFVG:", m_require_fvg,
                              " Trail:", m_trail_start, "/", m_trail_dist, "/", m_trail_step);
                        Print(m_strategy_name, " [过滤] H4EMA:", m_use_h4_filter,
                              " KDJ:", m_use_kdj_filter, "(p", m_kdj_period, ",OB", m_kdj_ob, "/OS", m_kdj_os, ")",
                              " ADX:", m_use_adx_filter, "(p", m_adx_period, ",>=", m_adx_min, ")",
                              " H4BOS:", m_use_h4_bos_filter, "(回看", m_h4_bos_lookback, ")",
                              " Session:", m_use_session_filter, "(", m_session1_start, "-", m_session1_end, ",", m_session2_start, "-", m_session2_end, ")",
                              " 固定RR:", m_use_fixed_rr, "(", m_rr_ratio, ")",
                              " 保本:", m_use_breakeven, "(", m_be_trigger_pts, "pts)",
                              " Trail+RR混合:", m_use_trail_with_rr);
                     }

                    ~CStrategy_SMC_OrderBlock(void)
                     {
                        IndicatorRelease(m_fractal_handle);
                        IndicatorRelease(m_ema_fast_h4);
                        IndicatorRelease(m_ema_slow_h4);
                        IndicatorRelease(m_kdj_handle);
                        IndicatorRelease(m_adx_handle);
                        IndicatorRelease(m_h4_fractal_handle);
                     }

   //========================================================================
   // 核心逻辑 11 + 逻辑 10：扫描 BMS -> 标记 OB -> 斐波那契 OTE 共振过滤
   //========================================================================
   virtual double    CalculateSignal(void) override
                     {
                        double high[], low[], close[], open[], up_frac[], dn_frac[];
                        datetime time[];

                        // 每次进入都先清空待执行信号 (经理每 tick 都调用本函数)
                        m_pending_signal = 0;

                        ArraySetAsSeries(high, true); ArraySetAsSeries(low, true);
                        ArraySetAsSeries(close, true); ArraySetAsSeries(open, true);
                        ArraySetAsSeries(up_frac, true); ArraySetAsSeries(dn_frac, true);
                        ArraySetAsSeries(time, true);

                        if(CopyHigh(m_symbol, m_timeframe, 0, 100, high) <= 0 ||
                           CopyLow(m_symbol, m_timeframe, 0, 100, low) <= 0 ||
                           CopyClose(m_symbol, m_timeframe, 0, 100, close) <= 0 ||
                           CopyOpen(m_symbol, m_timeframe, 0, 100, open) <= 0 ||
                           CopyTime(m_symbol, m_timeframe, 0, 100, time) <= 0 ||
                           CopyBuffer(m_fractal_handle, 0, 0, 100, up_frac) <= 0 ||
                           CopyBuffer(m_fractal_handle, 1, 0, 100, dn_frac) <= 0) return 0.0;

                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);

                        // 1. 寻找最近的结构高低点 (Fractals) —— 扫描窗口可调
                        int up_idx = -1, dn_idx = -1;
                        for(int i = 3; i < m_scan_window; i++)
                          {
                           if(up_idx == -1 && up_frac[i] != EMPTY_VALUE) up_idx = i;
                           if(dn_idx == -1 && dn_frac[i] != EMPTY_VALUE) dn_idx = i;
                           if(up_idx != -1 && dn_idx != -1) break;
                          }

                        // ==========================================
                        // [多头剧本]：看涨 BMS -> 找 Bullish OB
                        // ==========================================
                        if(up_idx != -1 && close[1] > high[up_idx])
                          {
                           if(time[up_idx] != m_last_up_frac_time)
                             {
                              m_last_up_frac_time = time[up_idx];

                              int lowest_idx = 1;
                              double min_l = 999999;
                              for(int j = up_idx; j >= 1; j--)
                                {
                                 if(low[j] < min_l) { min_l = low[j]; lowest_idx = j; }
                                }

                              // FVG 缺口验证 (可选 — v1.13 允许放松)
                              if(lowest_idx >= 3)
                                {
                                 bool fvg_ok = !m_require_fvg || (low[lowest_idx - 2] > high[lowest_idx]);
                                 if(fvg_ok)
                                   {
                                    m_bull_ob_high = high[lowest_idx];
                                    m_bull_ob_low = low[lowest_idx];
                                    m_bull_ob_active = true;
                                    m_bear_ob_active = false;
                                    Print("🟩 [SMC-BMS] 发现看涨结构破坏 (FVG要求:", m_require_fvg, ")！锁定订单块(OB): ", m_bull_ob_high, " - ", m_bull_ob_low);
                                   }
                                }
                             }
                          }

                        // ==========================================
                        // [空头剧本]：看跌 BMS -> 找 Bearish OB
                        // ==========================================
                        if(dn_idx != -1 && close[1] < low[dn_idx])
                          {
                           if(time[dn_idx] != m_last_dn_frac_time)
                             {
                              m_last_dn_frac_time = time[dn_idx];

                              int highest_idx = 1;
                              double max_h = 0;
                              for(int j = dn_idx; j >= 1; j--)
                                {
                                 if(high[j] > max_h) { max_h = high[j]; highest_idx = j; }
                                }

                              // FVG 缺口验证 (可选 — v1.13 允许放松)
                              if(highest_idx >= 3)
                                {
                                 bool fvg_ok = !m_require_fvg || (high[highest_idx - 2] < low[highest_idx]);
                                 if(fvg_ok)
                                   {
                                    m_bear_ob_high = high[highest_idx];
                                    m_bear_ob_low = low[highest_idx];
                                    m_bear_ob_active = true;
                                    m_bull_ob_active = false;
                                    Print("🟥 [SMC-BMS] 发现看跌结构破坏 (FVG要求:", m_require_fvg, ")！锁定订单块(OB): ", m_bear_ob_high, " - ", m_bear_ob_low);
                                   }
                                }
                             }
                          }

                        // ==========================================
                        // 2. 狙击触发：回踩订单块 + 斐波那契 OTE 验证 (容差可调, H4 顺势过滤)
                        // ==========================================

                        // 看涨回踩
                        if(m_bull_ob_active)
                          {
                           // 价格回踩碰到订单块上沿，且没有跌穿下沿
                           if(low[0] <= m_bull_ob_high && close[0] > m_bull_ob_low)
                             {
                              // 【内嵌逻辑 10：测算波段，验证 OTE 最优进场区】
                              int highest_since_ob = ArrayMaximum(high, 1, 50); // 找到拉升波段的最高点
                              double wave_high = high[highest_since_ob];
                              double wave_low = m_bull_ob_low; // 波段起点是订单块的底
                              double wave = wave_high - wave_low;

                              // 只有当波段拉出一定空间时，测算才有意义
                              if(wave > 1.0)
                                {
                                 double fib_a = wave_low + wave * m_ote_level1;
                                 double fib_b = wave_high - wave * m_ote_level2;
                                 double zone_lo = MathMin(fib_a, fib_b) - m_fib_tol * point;
                                 double zone_hi = MathMax(fib_a, fib_b) + m_fib_tol * point;

                                 m_bull_ob_active = false; // 触碰即失效，只做最优解

                                 // 检查当前价格是否落入 61.8% ~ 78.6% 黄金坑
                                 if(high[0] >= zone_lo && high[0] <= zone_hi)
                                   {
                                    if(PassH4Filter(1) && PassKDJFilter(1) && PassADXFilter() && PassH4BOSFilter(1) && PassSessionFilter())
                                      {
                                       Print("🎯 [SMC多重共振] OTE+H4EMA+KDJ+ADX+H4BOS+Session 全部通过！执行买入！");
                                       m_pending_signal = 1;
                                       return 100.0;
                                      }
                                    else
                                       Print("⛔ [SMC过滤] OTE满足但任一过滤器未通过 (含会话时段)，放弃做多。");
                                   }
                                 else
                                    Print("⚠️ [SMC过滤] 价格碰到订单块，但未在OTE黄金坑内！放弃接刀。");
                                }
                             }
                          }

                        // 看跌回抽
                        if(m_bear_ob_active)
                          {
                           // 价格回抽碰到订单块下沿，且没有涨穿上沿
                           if(high[0] >= m_bear_ob_low && close[0] < m_bear_ob_high)
                             {
                              // 【内嵌逻辑 10：测算波段，验证 OTE 最优进场区】
                              int lowest_since_ob = ArrayMinimum(low, 1, 50); // 找到砸盘波段的最低点
                              double wave_low = low[lowest_since_ob];
                              double wave_high = m_bear_ob_high; // 波段起点是订单块的顶
                              double wave = wave_high - wave_low;

                              if(wave > 1.0)
                                {
                                 double fib_a = wave_high - wave * m_ote_level1;
                                 double fib_b = wave_low + wave * m_ote_level2;
                                 double zone_lo = MathMin(fib_a, fib_b) - m_fib_tol * point;
                                 double zone_hi = MathMax(fib_a, fib_b) + m_fib_tol * point;

                                 m_bear_ob_active = false;

                                 if(high[0] >= zone_lo && high[0] <= zone_hi)
                                   {
                                    if(PassH4Filter(-1) && PassKDJFilter(-1) && PassADXFilter() && PassH4BOSFilter(-1) && PassSessionFilter())
                                      {
                                       Print("🎯 [SMC多重共振] OTE+H4EMA+KDJ+ADX+H4BOS+Session 全部通过！执行卖出！");
                                       m_pending_signal = -1;
                                       return -100.0;
                                      }
                                    else
                                       Print("⛔ [SMC过滤] OTE满足但任一过滤器未通过 (含会话时段)，放弃做空。");
                                   }
                                 else
                                    Print("⚠️ [SMC过滤] 价格碰到订单块，但未在OTE黄金坑内！放弃接刀。");
                                }
                             }
                          }

                        return 0.0;
                     }

   //========================================================================
   // 进场：纯正的 SMC 结构防守 (止损缓冲 + 倍率可调)
   //========================================================================
   virtual void      CheckEntry(CPositionManager *posMgr, CRiskManager *riskMgr) override
                     {
                        static datetime last_bar_time = 0;
                        datetime current_bar_time = iTime(m_symbol, m_timeframe, 0);
                        if(current_bar_time == last_bar_time) return;

                        // 直接读取上一次 CalculateSignal 缓存的信号 (避免二次调用清空状态)
                        if(m_pending_signal == 0) return;
                        double signal = (m_pending_signal == 1) ? 100.0 : -100.0;
                        m_pending_signal = 0;  // 消费掉

                        double current_price = (signal == 100.0) ? SymbolInfoDouble(m_symbol, SYMBOL_ASK) : SymbolInfoDouble(m_symbol, SYMBOL_BID);
                        double point = SymbolInfoDouble(m_symbol, SYMBOL_POINT);
                        double safe_lot = riskMgr.CalculateSafeLotSize(m_symbol, 0.01 * m_weight);
                        bool is_opened = false;

                        if(signal == 100.0)
                          {
                           // SMC 铁律：止损放在订单块最低点之下 m_sl_buffer 个点，再乘以止损倍率
                           double dynamic_sl_pts = ((current_price - m_bull_ob_low) / point + m_sl_buffer) * m_sl_mult;
                           // 风控天花板：单笔止损不超过 m_max_sl，防止深订单块带来巨亏
                           if(dynamic_sl_pts > m_max_sl) dynamic_sl_pts = m_max_sl;
                           // v1.15 固定 R:R 止盈 (Kelly 教科书规则)：TP = SL × R:R 倍率
                           double tp_pts = (m_use_fixed_rr) ? (dynamic_sl_pts * m_rr_ratio) : 10000.0;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_BUY, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, tp_pts);
                          }
                        else if(signal == -100.0)
                          {
                           // SMC 铁律：止损放在订单块最高点之上 m_sl_buffer 个点，再乘以止损倍率
                           double dynamic_sl_pts = ((m_bear_ob_high - current_price) / point + m_sl_buffer) * m_sl_mult;
                           // 风控天花板：单笔止损不超过 m_max_sl
                           if(dynamic_sl_pts > m_max_sl) dynamic_sl_pts = m_max_sl;
                           // v1.15 固定 R:R 止盈
                           double tp_pts = (m_use_fixed_rr) ? (dynamic_sl_pts * m_rr_ratio) : 10000.0;
                           is_opened = posMgr.ExecuteOrderWithSLTP(m_symbol, ORDER_TYPE_SELL, safe_lot, m_magic_number, m_strategy_name, dynamic_sl_pts, tp_pts);
                          }

                        if(is_opened) last_bar_time = current_bar_time;
                     }

   //========================================================================
   // 退出：吃主升浪的格局 (追踪参数可调)
   //========================================================================
   virtual void      CheckExit(CPositionManager *posMgr) override
                     {
                        // v1.16 退场矩阵：
                        //  - 纯追踪 (Fixed R:R 关闭)  → 只跑 Trail (原 v1.12 行为)
                        //  - Fixed R:R 开启          → 静态 TP 负责巨大利润；
                        //                              BE 保护已起飞的单子；
                        //                              如果 use_trail_with_rr=true，则 Trail 同时启动，
                        //                              捕捉到不了 TP 的中途利润。
                        if(m_use_fixed_rr)
                          {
                           if(m_use_breakeven)
                              posMgr.ManageBreakEven(m_symbol, m_magic_number, (double)m_be_trigger_pts);
                           if(m_use_trail_with_rr)
                              posMgr.ManageTrailingStop(m_symbol, m_magic_number, m_trail_start, m_trail_dist, m_trail_step);
                          }
                        else
                          {
                           posMgr.ManageTrailingStop(m_symbol, m_magic_number, m_trail_start, m_trail_dist, m_trail_step);
                          }
                     }
  };
//+------------------------------------------------------------------+
