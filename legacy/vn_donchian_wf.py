"""
vn_donchian_wf.py
Donchian breakout long-only + bộ lọc xu hướng VN-Index + lọc khối lượng + trailing stop ATR,
tối ưu tham số bằng walk-forward có làm mượt "plateau" và Deflated Sharpe Ratio.

DỮ LIỆU ĐẦU VÀO (định dạng long, CSV hoặc parquet):
  prices : date, symbol, open, high, low, close, volume   -> GIÁ PHẢI ĐIỀU CHỈNH cổ tức tiền/cổ phiếu/phát hành thêm
  index  : date, close                                    -> VN-Index
Nên gồm cả mã đã hủy niêm yết (tránh survivorship bias). Chỉ nên dùng mã HOSE (biên độ +-7%).

QUY ƯỚC THỰC THI (cố ý bảo thủ):
  - Tín hiệu tại giá đóng cửa ngày t, khớp tại giá mở cửa ngày t+1 (không look-ahead).
  - Không mua được nếu giá mở cửa >= trần; không bán được nếu giá mở cửa <= sàn (lệnh chờ sang phiên sau).
  - Giữ tối thiểu `min_hold` phiên (T+2 hàng về) trước khi bán.
  - Chi phí: mua 0.30% (phí + trượt giá), bán 0.40% (phí + trượt giá + thuế 0.1%). Hãy thay bằng biểu phí thực tế của bạn.
"""
import argparse
import itertools
import numpy as np
import pandas as pd
from scipy.stats import norm, skew, kurtosis

CFG = dict(
    buy_cost=0.0030, sell_cost=0.0040, rf=0.05, init_cash=1e9,
    risk_pct=0.01,      # rủi ro mỗi lệnh / vốn (dựa trên khoảng cách stop)
    max_pos=10, max_w=0.15, adtv_frac=0.03,
    min_adtv=1e10,      # GTGD trung vị 60 phiên tối thiểu (VND) ~ 10 tỷ
    min_hold=3, limit=0.07, lot=100, min_trades=20,
)


# ----------------------------------------------------------------------------- dữ liệu
def load_wide(path, price_scale=1.0):
    df = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    W = {c: df.pivot(index="date", columns="symbol", values=c).sort_index()
         for c in ["open", "high", "low", "close", "volume"]}
    for c in ["open", "high", "low", "close"]:
        W[c] = W[c] * price_scale
    return W


def load_index(path, dates):
    d = pd.read_parquet(path) if path.endswith(".parquet") else pd.read_csv(path)
    d["date"] = pd.to_datetime(d["date"])
    return d.set_index("date")["close"].sort_index().reindex(dates).ffill()


def synthetic(n_sym=60, n_days=3600, seed=7):
    """Dữ liệu mô phỏng chỉ để kiểm tra mã chạy được (KHÔNG dùng để rút ra kết luận)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2012-01-02", periods=n_days)
    drift = np.zeros(n_days)
    for t in range(1, n_days):                       # chế độ xu hướng AR(1)
        drift[t] = 0.98 * drift[t - 1] + rng.normal(0, 0.0004)
    mkt = drift + rng.normal(0, 0.009, n_days)
    out = []
    for s in range(n_sym):
        beta = rng.uniform(0.6, 1.4)
        idio = rng.normal(0, 0.016, n_days)
        r = np.clip(beta * mkt + idio, -0.069, 0.069)
        c = 25000 * np.exp(np.cumsum(r))
        o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.004, n_days))
        h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.006, n_days)))
        l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.006, n_days)))
        v = rng.lognormal(13.5, 0.5, n_days) * (1 + 3 * np.abs(r) / 0.05)
        out.append(pd.DataFrame(dict(date=dates, symbol=f"S{s:03d}", open=o, high=h, low=l, close=c, volume=v)))
    df = pd.concat(out)
    idx = pd.DataFrame(dict(date=dates, close=1000 * np.exp(np.cumsum(mkt))))
    return df, idx


class Feat:
    def __init__(self, W, idx_close):
        self.dates = W["open"].index
        self.O, self.H, self.L, self.C, self.V = (W[k].values for k in ["open", "high", "low", "close", "volume"])
        Cdf, Vdf = W["close"], W["volume"]
        self.adtv = (Cdf * Vdf).rolling(60, min_periods=40).median().shift(1).values
        cp = np.vstack([np.full((1, self.C.shape[1]), np.nan), self.C[:-1]])
        tr = np.maximum(self.H - self.L, np.maximum(np.abs(self.H - cp), np.abs(self.L - cp)))
        self.atr = pd.DataFrame(tr).rolling(14, min_periods=10).mean().values
        self.volavg = Vdf.rolling(20, min_periods=15).mean().shift(1).values
        self.idx = idx_close
        self._hh, self._ll, self._reg, self._sig = {}, {}, {}, {}
        self.Hdf, self.Ldf, self.Cdf = W["high"], W["low"], W["close"]
        self._ema, self._sma, self._rsr = {}, {}, {}
        rng = self.H - self.L
        with np.errstate(invalid="ignore", divide="ignore"):
            self.clv = np.where(rng > 0, (self.C - self.L) / rng, 0.5)   # vị trí đóng cửa trong biên độ phiên

    def sma(self, n):
        if n not in self._sma:
            self._sma[n] = self.Cdf.rolling(n, min_periods=n).mean().values
        return self._sma[n]

    def ema(self, n):
        if n not in self._ema:
            self._ema[n] = self.Cdf.ewm(span=n, adjust=False, min_periods=n).mean().values
        return self._ema[n]

    def rs_rank(self, cfg, lb=126):
        """Phân vị sức mạnh tương đối (lợi suất lb phiên) trong nhóm cổ phiếu đủ thanh khoản, tính theo từng ngày."""
        if lb not in self._rsr:
            roc = self.Cdf / self.Cdf.shift(lb) - 1
            elig = pd.DataFrame(self.adtv >= cfg["min_adtv"], index=roc.index, columns=roc.columns)
            self._rsr[lb] = roc.where(elig).rank(axis=1, pct=True).values
        return self._rsr[lb]

    def exit_line(self, mode, n_out):
        return self.ll(n_out) if mode == "brk" else self.sma(n_out)

    def hh(self, n):
        if n not in self._hh:
            self._hh[n] = self.Hdf.rolling(n, min_periods=n).max().shift(1).values
        return self._hh[n]

    def ll(self, n):
        if n not in self._ll:
            self._ll[n] = self.Ldf.rolling(n, min_periods=n).min().shift(1).values
        return self._ll[n]

    def regime(self, m):
        if m not in self._reg:
            if m == 0:
                self._reg[m] = np.ones(len(self.dates), bool)
            else:
                self._reg[m] = (self.idx > self.idx.rolling(m, min_periods=m).mean()).fillna(False).values
        return self._reg[m]

    def signals(self, mode, n_in, m, vm, clv, rs, cfg):
        """mode='brk': phá đỉnh n_in phiên.  mode='pb': pullback về EMA(n_in) trong xu hướng tăng (SMA20>SMA50, giá>SMA50)."""
        key = (mode, n_in, m, vm, clv, rs)
        if key not in self._sig:
            with np.errstate(invalid="ignore"):
                if mode == "brk":
                    hh = self.hh(n_in)
                    sig = self.C > hh
                    strength = (self.C - hh) / self.atr
                else:
                    e, s20, s50 = self.ema(n_in), self.sma(20), self.sma(50)
                    up = (self.C > s50) & (s20 > s50) & (s20 > np.vstack([np.full((5, s20.shape[1]), np.nan), s20[:-5]]))
                    sig = up & (self.L <= e) & (self.C > e) & (self.C > self.O)
                    strength = (self.C - e) / self.atr
                sig = sig & self.regime(m)[:, None] & (self.adtv >= cfg["min_adtv"])
                if vm > 0:
                    sig &= self.V >= vm * self.volavg
                if clv > 0:
                    sig &= self.clv >= clv
                if rs > 0:
                    sig &= self.rs_rank(cfg) >= (1 - rs)
            self._sig[key] = (sig & ~np.isnan(strength), np.nan_to_num(strength, nan=-1))
        return self._sig[key]


# ----------------------------------------------------------------------------- backtest
def backtest(F, p, cfg, i0, i1):
    n_in, n_out, m, vm, k, clv, rs = p
    sig, strength = F.signals(cfg["mode"], n_in, m, vm, clv, rs, cfg)
    ll = F.exit_line(cfg["mode"], n_out)
    T = F.C.shape[0]
    i0 = max(i0, 1)
    i1 = min(i1, T)
    cash = cfg["init_cash"]
    pos, pend_exit, pend_entry, trades = {}, set(), [], []
    eq = np.full(T, np.nan)
    eq[i0 - 1] = cash
    ks = k if k < 50 else 3.0
    for t in range(i0, i1):
        o, cprev = F.O[t], F.C[t - 1]
        # 1) khớp lệnh thoát tại giá mở cửa
        for j in list(pend_exit):
            P = pos[j]
            if t - P["ei"] < cfg["min_hold"] or np.isnan(o[j]) or np.isnan(cprev[j]):
                continue
            if o[j] <= cprev[j] * (1 - cfg["limit"] + 0.002):      # sàn -> không bán được
                continue
            px = o[j] * (1 - cfg["sell_cost"])
            cash += P["sh"] * px
            trades.append((t - P["ei"], px / P["px0"] - 1))
            del pos[j]
            pend_exit.discard(j)
        # 2) khớp lệnh mua tại giá mở cửa
        if pend_entry:
            eqv = cash + sum(P["sh"] * P["last"] for P in pos.values())
            for j in pend_entry:
                if len(pos) >= cfg["max_pos"]:
                    break
                if j in pos or np.isnan(o[j]) or np.isnan(cprev[j]) or np.isnan(F.atr[t - 1][j]):
                    continue
                if o[j] >= cprev[j] * (1 + cfg["limit"] - 0.002):  # trần -> không mua được
                    continue
                risk_ps = ks * F.atr[t - 1][j]
                sh = cfg["risk_pct"] * eqv / risk_ps if risk_ps > 0 else 0
                cap = min(cfg["max_w"] * eqv, cfg["adtv_frac"] * F.adtv[t - 1][j])
                sh = min(sh, cap / o[j], cash / (o[j] * (1 + cfg["buy_cost"])))
                sh = np.floor(sh / cfg["lot"]) * cfg["lot"]
                if sh < cfg["lot"]:
                    continue
                cash -= sh * o[j] * (1 + cfg["buy_cost"])
                pos[j] = dict(sh=sh, ei=t, px0=o[j] * (1 + cfg["buy_cost"]), hc=o[j], last=o[j])
        pend_entry = []
        # 3) cuối phiên: cập nhật, sinh tín hiệu thoát / vào lệnh cho phiên sau
        c = F.C[t]
        for j, P in pos.items():
            if np.isnan(c[j]):
                continue
            P["last"] = c[j]
            P["hc"] = max(P["hc"], c[j])
            if j in pend_exit:
                continue
            if c[j] < ll[t][j] or (k < 50 and c[j] < P["hc"] - k * F.atr[t][j]):
                pend_exit.add(j)
        eq[t] = cash + sum(P["sh"] * P["last"] for P in pos.values())
        if len(pos) < cfg["max_pos"]:
            cand = np.where(sig[t])[0]
            cand = [j for j in cand[np.argsort(-strength[t][cand])] if j not in pos]
            pend_entry = cand[: cfg["max_pos"] * 2]
    ret = eq[i0:i1] / np.r_[eq[i0 - 1], eq[i0:i1 - 1]] - 1
    return ret, trades


def perf(ret, rf):
    r = np.asarray(ret, float)
    r = r[~np.isnan(r)]
    if len(r) < 20 or r.std() == 0:
        return dict(sharpe=0.0, cagr=0.0, vol=0.0, mdd=0.0)
    eqc = np.cumprod(1 + r)
    return dict(sharpe=(r.mean() - rf / 252) / r.std() * np.sqrt(252),
                cagr=eqc[-1] ** (252 / len(r)) - 1, vol=r.std() * np.sqrt(252),
                mdd=(eqc / np.maximum.accumulate(eqc) - 1).min())


def trade_stats(trades):
    if not trades:
        return dict(n=0, win=np.nan, payoff=np.nan, hold=np.nan)
    h = np.array([a for a, _ in trades]); r = np.array([b for _, b in trades])
    w, l = r[r > 0], r[r <= 0]
    return dict(n=len(r), win=len(w) / len(r),
                payoff=(w.mean() / abs(l.mean())) if len(w) and len(l) and l.mean() != 0 else np.nan,
                hold=h.mean())


# ----------------------------------------------------------------------------- tối ưu / walk-forward
def smooth_scores(axes, scores):
    """Điểm = trung bình Sharpe của tham số và các láng giềng 1 bước -> ưu tiên 'cao nguyên', tránh đỉnh nhọn."""
    out = {}
    for p, s in scores.items():
        vals = [s]
        for d, ax in enumerate(axes):
            i = ax.index(p[d])
            for di in (-1, 1):
                if 0 <= i + di < len(ax):
                    q = list(p); q[d] = ax[i + di]
                    vals.append(scores[tuple(q)])
        out[p] = float(np.mean(vals))
    return out


def deflated_sharpe(r, n_trials, var_sr_daily):
    r = np.asarray(r, float); r = r[~np.isnan(r)]
    T, sr = len(r), r.mean() / r.std()
    g = 0.5772156649
    sr0 = np.sqrt(var_sr_daily) * ((1 - g) * norm.ppf(1 - 1 / n_trials) + g * norm.ppf(1 - 1 / (n_trials * np.e)))
    sk, ku = skew(r), kurtosis(r, fisher=False)
    return norm.cdf((sr - sr0) * np.sqrt(T - 1) / np.sqrt(1 - sk * sr + (ku - 1) / 4 * sr ** 2))


def run_grid(F, grid, cfg, i0, i1, n_jobs):
    def one(p):
        ret, tr = backtest(F, p, cfg, i0, i1)
        s = perf(ret, cfg["rf"])["sharpe"] if len(tr) >= cfg["min_trades"] else -5.0
        return p, s
    if n_jobs > 1:
        from joblib import Parallel, delayed
        res = Parallel(n_jobs=n_jobs)(delayed(one)(p) for p in grid)
    else:
        res = [one(p) for p in grid]
    return dict(res)


def walk_forward(F, axes, cfg, train_years, test_years, n_jobs):
    grid = list(itertools.product(*axes))
    yrs = F.dates.year.values
    uy = sorted(set(yrs))
    first = lambda y: int(np.argmax(yrs >= y)) if (yrs >= y).any() else len(yrs)
    oos_ret, picks, last_scores = [], [], None
    ty = uy[0] + train_years
    while ty <= uy[-1]:
        i_tr0, i_tr1, i_te1 = first(ty - train_years), first(ty), first(ty + test_years)
        scores = run_grid(F, grid, cfg, i_tr0, i_tr1, n_jobs)
        sm = smooth_scores(axes, scores)
        best = max(sm, key=sm.get)
        ret, tr = backtest(F, best, cfg, i_tr1, i_te1)
        oos_ret.append(pd.Series(ret, index=F.dates[max(i_tr1, 1):min(i_te1, len(F.dates))]))
        picks.append((ty, best, scores[best], sm[best], perf(ret, cfg["rf"])["sharpe"], len(tr)))
        last_scores = scores
        ty += test_years
    return pd.concat(oos_ret), picks, last_scores, len(grid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data"); ap.add_argument("--index")
    ap.add_argument("--price-scale", type=float, default=1.0, help="1000 nếu giá tính theo nghìn đồng")
    ap.add_argument("--train", type=int, default=3); ap.add_argument("--test", type=int, default=1)
    ap.add_argument("--jobs", type=int, default=1); ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--fast", action="store_true", help="lưới nhỏ để kiểm tra mã")
    ap.add_argument("--mode", default="brk", choices=["brk", "pb"], help="brk = Donchian breakout; pb = pullback EMA trong xu hướng")
    a = ap.parse_args()

    if a.synthetic:
        df, idx = synthetic()
        df.to_csv("/tmp/syn_px.csv", index=False); idx.to_csv("/tmp/syn_idx.csv", index=False)
        a.data, a.index = "/tmp/syn_px.csv", "/tmp/syn_idx.csv"
    W = load_wide(a.data, a.price_scale)
    F = Feat(W, load_index(a.index, W["close"].index) * 1.0)

    CFG["mode"] = a.mode
    # THỨ TỰ TRỤC: n_in, n_out, regime_ma (0=tắt), vol_mult (0=tắt), atr_k (99=tắt), clv_min (0=tắt), rs_top (0=tắt)
    # brk: n_in = cửa sổ đỉnh, n_out = cửa sổ đáy thoát.  pb: n_in = EMA pullback, n_out = SMA thoát.
    if a.fast:
        axes = ([[20, 40], [10, 20], [0, 100], [0, 1.5], [3.0, 99], [0, 0.65], [0, 0.5]] if a.mode == "brk"
                else [[10, 20], [20, 50], [0, 100], [0, 1.5], [3.0, 99], [0, 0.65], [0, 0.5]])
    elif a.mode == "brk":
        axes = [[20, 30, 40, 55], [10, 20], [0, 100, 150], [0, 1.3], [3.0, 99], [0, 0.65], [0, 0.5]]
    else:
        axes = [[10, 15, 20], [20, 50], [0, 100], [0, 1.5], [2.0, 3.0], [0, 0.65], [0, 0.5]]

    oos, picks, last_scores, n_trials = walk_forward(F, axes, CFG, a.train, a.test, a.jobs)
    print("\nTham số chọn theo từng cửa sổ (năm test | n_in,n_out,MA,vol,atr_k,clv,rs | Sharpe train | điểm làm mượt | Sharpe OOS | số lệnh OOS)")
    for y, p, s, sm, so, n in picks:
        print(f"  {y} | {p} | {s:5.2f} | {sm:5.2f} | {so:5.2f} | {n}")

    sh = np.array([x[4] for x in picks])
    print(f"\nPhân phối Sharpe OOS theo năm: trung vị {np.median(sh):.2f} | tứ phân vị {np.percentile(sh,25):.2f}..{np.percentile(sh,75):.2f}"
          f" | tỷ lệ năm dương {np.mean(sh > 0):.0%} | số năm {len(sh)}")
    st = perf(oos.values, CFG["rf"])
    ix = F.idx.pct_change().reindex(oos.index)
    sb = perf(ix.values, CFG["rf"])
    var_sr = np.var([v / np.sqrt(252) for v in last_scores.values() if v > -5])
    dsr = deflated_sharpe(oos.values, n_trials, var_sr)
    print(f"\nOOS gộp: CAGR {st['cagr']:.1%} | Sharpe {st['sharpe']:.2f} | Vol {st['vol']:.1%} | MaxDD {st['mdd']:.1%}")
    print(f"VN-Index buy&hold cùng kỳ: CAGR {sb['cagr']:.1%} | Sharpe {sb['sharpe']:.2f} | MaxDD {sb['mdd']:.1%}")
    print(f"Deflated Sharpe Ratio (xác suất Sharpe thật > 0 sau khi trừ selection bias, N={n_trials}): {dsr:.2f}")
    oos.to_csv("oos_returns.csv")


if __name__ == "__main__":
    main()
