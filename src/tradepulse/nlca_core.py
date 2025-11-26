import argparse
import logging
import queue
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import torch
import torch.nn as nn
import torch.optim as optim
import yaml
from scipy import integrate

try:
    from binance.client import Client
    from binance.websockets import BinanceSocketManager
except Exception:
    Client = None
    BinanceSocketManager = None

try:
    import dash
    import plotly.graph_objs as go
    from dash import dcc, html
    from dash.dependencies import Input, Output, State
except Exception:
    dash = None
    dcc = None
    html = None
    Input = Output = State = None
    go = None

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class FiniteStateMachine:
    def __init__(self, refractory_period: float = 1.0):
        self.state = "S0"
        self.last_transition_time = time.time()
        self.refractory_period = refractory_period
        self.log = []

    def transition(self, new_state: str, reason: str, force: bool = False):
        now = time.time()
        if not force and (now - self.last_transition_time < self.refractory_period):
            logging.warning(f"Refractory active: ignoring {new_state}")
            return False

        prev = self.state
        self.state = new_state
        self.last_transition_time = now
        entry = {"from": prev, "to": new_state, "time": now, "reason": reason}
        self.log.append(entry)
        logging.info(f"FSM {prev}->{new_state} : {reason}")
        return True

    def get_state(self) -> str:
        return self.state

    def get_logs(self):
        return self.log


class ThresholdLearner(nn.Module):
    def __init__(self, theta_s=0.5, q_S=0.0001, q_O=10.0, q_B=5.0):
        super().__init__()
        self.theta_s = nn.Parameter(torch.tensor(float(theta_s)))
        self.q_S = nn.Parameter(torch.tensor(float(q_S)))
        self.q_O = nn.Parameter(torch.tensor(float(q_O)))
        self.q_B = nn.Parameter(torch.tensor(float(q_B)))

    def forward(self):
        return self.theta_s, self.q_S, self.q_O, self.q_B


class L2Collector:
    def __init__(self, sync_tolerance: float = 0.001):
        self.last_ts = time.time()
        self.sync_tolerance = sync_tolerance

    def collect(self, data: dict) -> dict:
        now = time.time()
        if abs(now - self.last_ts) > self.sync_tolerance:
            logging.warning("Timestamp desync detected > sync_tolerance")
        self.last_ts = now
        return data


class BinanceFeed:
    def __init__(
        self, api_key, api_secret, symbol="BTCUSDT", tick_queue: queue.Queue = None
    ):
        self.symbol = symbol.lower()
        self.tick_queue = tick_queue if tick_queue is not None else queue.Queue()
        self.running = False
        self.depth_key: str | None = None
        self.trade_key: str | None = None

        if Client is None or BinanceSocketManager is None:
            logging.warning("Binance SDK не доступний у цьому середовищі")
            self.client = None
            self.bm = None
        else:
            self.client = Client(api_key, api_secret)
            self.bm = BinanceSocketManager(self.client)

        self.last_best_ask = None
        self.last_best_bid = None
        self.last_depth_ask = []
        self.last_depth_bid = []
        self.last_volume = 0.0
        self.last_open = None
        self.last_last = None
        self.last_trades = []
        self.last_messages = []

    def _emit_tick(self):
        if self.last_best_ask is None or self.last_best_bid is None:
            return
        tick = {
            "timestamp": time.time(),
            "p_a1": float(self.last_best_ask),
            "p_b1": float(self.last_best_bid),
            "q_a": [float(x) for x in self.last_depth_ask[:5]],
            "q_b": [float(x) for x in self.last_depth_bid[:5]],
            "events": [],
            "messages": self.last_messages[-200:],
            "trades": self.last_trades[-50:],
            "delta_P": (
                0.0
                if (self.last_last is None or self.last_open is None)
                else float(self.last_last - self.last_open)
            ),
            "Q": float(self.last_volume),
        }
        self.tick_queue.put(tick)

    def process_depth_message(self, msg):
        if msg.get("e") == "error":
            logging.error(f"WebSocket depth error: {msg}")
            return
        bids = msg.get("b", [])
        asks = msg.get("a", [])
        if bids:
            self.last_best_bid = float(bids[0][0])
            self.last_depth_bid = [float(x[1]) for x in bids]
        if asks:
            self.last_best_ask = float(asks[0][0])
            self.last_depth_ask = [float(x[1]) for x in asks]
        self.last_messages.append(("depth", time.time(), len(bids), len(asks)))
        self._emit_tick()

    def process_trade_message(self, msg):
        if msg.get("e") == "error":
            logging.error(f"WebSocket trade error: {msg}")
            return
        price = float(msg.get("p", 0.0))
        qty = float(msg.get("q", 0.0))
        is_buyer_maker = bool(msg.get("m", False))
        self.last_trades.append({"price": price, "qty": qty, "maker": is_buyer_maker})
        self.last_last = price
        if self.last_open is None:
            self.last_open = price
        self.last_volume += qty
        self.last_messages.append(("trade", time.time(), qty, is_buyer_maker))
        self._emit_tick()

    def start(self):
        if self.bm is None:
            logging.warning("Binance feed disabled, cannot start WebSocket.")
            return
        self.depth_key = self.bm.start_depth_socket(
            self.symbol, self.process_depth_message, depth=5
        )
        self.trade_key = self.bm.start_trade_socket(
            self.symbol, self.process_trade_message
        )
        self.bm.start()
        self.running = True
        logging.info(f"Binance WebSocket started for {self.symbol}")

    def stop(self):
        if self.bm is not None:
            for key, label in ((self.depth_key, "depth"), (self.trade_key, "trade")):
                if key is None:
                    continue
                try:
                    self.bm.stop_socket(key)
                except Exception:
                    logging.exception(
                        "Failed to stop Binance %s socket for %s", label, self.symbol
                    )
            try:
                self.bm.close()
            except Exception:
                logging.exception(
                    "Failed to close Binance socket manager for %s", self.symbol
                )
        if self.client is not None:
            close_conn = getattr(self.client, "close_connection", None)
            if callable(close_conn):
                try:
                    close_conn()
                except Exception:
                    logging.exception(
                        "Failed to close Binance REST client for %s", self.symbol
                    )
        self.running = False
        self.depth_key = None
        self.trade_key = None
        logging.info("Binance WebSocket stopped")


class MarketRecorder:
    def __init__(
        self,
        dataset_path: str | Path | None = None,
        enabled: bool = False,
        flush_every: int = 1000,
    ):
        self.enabled = enabled
        self.dataset_path = Path(dataset_path) if dataset_path else None
        self.flush_every = flush_every
        self.buffer: list[dict] = []

    def record_tick(self, tick: dict, decision: dict, metrics: dict):
        if not self.enabled:
            return
        row = {
            "ts": tick.get("timestamp", time.time()),
            "state": decision.get("state"),
            "action": decision.get("action"),
            "S": metrics.get("S"),
            "D": metrics.get("D"),
            "OFI": metrics.get("OFI"),
            "lambda": metrics.get("lambda"),
            "SVI": metrics.get("SVI"),
            "BRHL": metrics.get("BRHL"),
            "OTR": metrics.get("OTR"),
            "date": time.strftime(
                "%Y-%m-%d", time.gmtime(tick.get("timestamp", time.time()))
            ),
        }
        self.buffer.append(row)
        if len(self.buffer) >= self.flush_every:
            self.flush()

    def flush(self):
        if not self.enabled or not self.buffer or self.dataset_path is None:
            return
        try:
            self.dataset_path.mkdir(parents=True, exist_ok=True)
        except OSError:
            logging.exception(
                "Failed to prepare dataset directory %s", self.dataset_path
            )
            return

        df = pd.DataFrame(self.buffer)
        try:
            table = pa.Table.from_pandas(df, preserve_index=False)
            pq.write_to_dataset(
                table, root_path=str(self.dataset_path), partition_cols=["date"]
            )
        except Exception:
            logging.exception(
                "Failed to persist market data batch to %s", self.dataset_path
            )
            return
        self.buffer.clear()


class NLCA:
    def __init__(
        self,
        context_profile: dict,
        exposure_limit: float = 100000,
        delay_budget: float = 0.1,
        max_tau: float = 10.0,
        refractory_period: float = 1.0,
        lr: float = 0.01,
        r2_threshold: float = 0.5,
        recorder: MarketRecorder = None,
    ):
        self.S_median = float(context_profile.get("S_median", 0.01))
        self.D_median = float(context_profile.get("D_median", 1000))

        self.fsm = FiniteStateMachine(refractory_period=refractory_period)
        self.learner = ThresholdLearner(
            theta_s=0.5,
            q_S=context_profile.get("SVI_80th", 0.0001),
            q_O=context_profile.get("OTR_80th", 10.0),
            q_B=context_profile.get("BRHL_80th", 5.0),
        )
        self.optimizer = optim.Adam(self.learner.parameters(), lr=lr)

        self.history = {
            "delta_P": [],
            "Q": [],
            "S": [],
            "D": [],
            "OFI": [],
            "lambda": [],
            "OTR": [],
            "BRHL": [],
        }

        self.last_Seff_book = 0.0
        self.last_Seff_tape = 0.0
        self.exposure_limit = float(exposure_limit)
        self.current_exposure = 0.0
        self.delay_budget = float(delay_budget)
        self.max_tau = float(max_tau)
        self.r2_threshold = float(r2_threshold)

        self.action_log = []
        self.pnl_history = []
        self.slippage_history = []
        self.priority_paths = {}

        self.collector = L2Collector()
        self.recorder = recorder
        self.last_ts = None

    def sanitize_input(self, tick: dict):
        required = [
            "p_a1",
            "p_b1",
            "q_a",
            "q_b",
            "events",
            "messages",
            "trades",
            "delta_P",
            "Q",
        ]
        for k in required:
            if k not in tick or tick[k] is None:
                return False, f"Missing or None key: {k}"

        base_numeric = ["p_a1", "p_b1", "delta_P", "Q"]
        vals = [tick[f] for f in base_numeric]
        if np.any(np.isnan(vals)):
            return False, "NaN in numeric fields"

        for depth_key in ("q_a", "q_b"):
            depth_values = tick.get(depth_key)
            if not isinstance(depth_values, (list, tuple, np.ndarray)):
                return False, f"{depth_key} must be a sequence"
            if len(depth_values) == 0:
                return False, f"{depth_key} is empty"
            try:
                depth_array = np.asarray(depth_values, dtype=float)
            except (TypeError, ValueError):
                return False, f"{depth_key} contains non-numeric values"
            if not np.isfinite(depth_array).all():
                return False, f"{depth_key} contains non-finite values"

        ts = tick.get("timestamp", time.time())
        if self.last_ts is not None and ts <= self.last_ts:
            return False, "Non-increasing timestamp"
        self.last_ts = ts

        return True, ""

    def log_action(self, action: str, metrics: dict, reason: str):
        entry = {
            "time": time.time(),
            "state": self.fsm.get_state(),
            "action": action,
            "reason": reason,
            "metrics": metrics,
        }
        self.action_log.append(entry)
        logging.info(
            f"ACTION {action} state={self.fsm.get_state()} reason={reason} metrics={metrics}"
        )

    @staticmethod
    def compute_spread(p_a1, p_b1):
        return float(p_a1 - p_b1)

    @staticmethod
    def compute_depth(q_b, q_a, L=5):
        q_b = np.asarray(q_b[:L], dtype=float)
        q_a = np.asarray(q_a[:L], dtype=float)
        return float(np.sum(q_b + q_a))

    @staticmethod
    def compute_OFI(events: list):
        ofi = 0.0
        for e in events:
            if "type" not in e or "side" not in e or "volume" not in e:
                continue
            side = e["side"]
            vol = float(e["volume"])
            psi = 0.0
            if e["type"] in ["add", "trade"]:
                psi = (1.0 if side == "ask" else -1.0) * vol
            elif e["type"] == "cancel":
                psi = (-1.0 if side == "ask" else 1.0) * vol
            if e.get("price_change", False):
                psi *= 2.0
            ofi += psi
        return float(ofi)

    def compute_lambda_kyle(self, window=100):
        dP = np.array(self.history["delta_P"][-window:], dtype=float)
        Q = np.array(self.history["Q"][-window:], dtype=float)
        if Q.size < 2:
            return 0.0
        den = np.sum(Q**2)
        if den == 0:
            return 0.0
        num = np.sum(dP * Q)
        return float(num / den)

    def compute_beta_OFI(self, window=100):
        dP = np.array(self.history["delta_P"][-window:], dtype=float)
        OFI_hist = np.array(self.history["OFI"][-window:], dtype=float)
        if OFI_hist.size < 2:
            return 0.0, 0.0
        den = np.sum(OFI_hist**2)
        if den == 0:
            return 0.0, 0.0
        num = np.sum(dP * OFI_hist)
        beta = float(num / den)

        pred = beta * OFI_hist
        ss_res = np.sum((dP - pred) ** 2)
        ss_tot = np.sum((dP - np.mean(dP)) ** 2)
        R2 = float(1 - ss_res / ss_tot) if ss_tot != 0 else 0.0
        return beta, R2

    def compute_SVI(self, delta_t=100):
        S_hist = np.array(self.history["S"][-delta_t:], dtype=float)
        if S_hist.size < 2:
            return 0.0
        return float(np.var(S_hist))

    def compute_BRHL(self, shock_time: int, eps_S=0.001, eps_D=100.0):
        S_hist = np.array(self.history["S"][shock_time:], dtype=float)
        D_hist = np.array(self.history["D"][shock_time:], dtype=float)

        S0 = self.S_median
        D0 = self.D_median

        tau = 1
        while tau < len(S_hist):
            if (
                abs(S_hist[tau - 1] - S0) <= eps_S
                and abs(D_hist[tau - 1] - D0) <= eps_D
            ):
                return float(tau)
            tau += 1
        return float(self.max_tau)

    @staticmethod
    def compute_OTR(messages, trades, delta_t=100):
        msg_n = len(messages[-delta_t:]) if len(messages) >= delta_t else len(messages)
        trd_n = len(trades[-delta_t:]) if len(trades) >= delta_t else len(trades)
        trd_n = max(1, trd_n)
        return float(msg_n / trd_n)

    def compute_ECE(self, X=1000, T=3600, sigma=0.01, gamma=1e-6, eta=1e-5):
        v_t = X / T
        temp_impact = eta * integrate.quad(lambda t: v_t**2, 0, T)[0]
        perm_impact = 0.5 * gamma * (X**2)
        var_C = sigma**2 * integrate.quad(lambda t: (X - v_t * t) ** 2, 0, T)[0]
        ECE = temp_impact + perm_impact
        return float(ECE), float(var_C)

    @staticmethod
    def compute_EVC(expected_profit, ECE):
        return float(expected_profit - ECE)

    @staticmethod
    def compute_PW(var_signal):
        return 1.0 / var_signal if var_signal > 0 else 1.0

    @staticmethod
    def compute_Seff(PW, delta_signal):
        return float(PW * abs(delta_signal))

    @staticmethod
    def compute_RPE(expected_vec, actual_vec):
        return float(sum(expected_vec) - sum(actual_vec))

    def update_thresholds_gradient(self, RPE):
        self.optimizer.zero_grad()
        theta_s, q_S, q_O, q_B = self.learner()
        target_caution = torch.tensor(1.0 if RPE > 0 else 0.0)
        pred_caution = torch.sigmoid((theta_s + q_S + q_O + q_B) * 0.01)
        loss = (pred_caution - target_caution) ** 2
        loss.backward()
        self.optimizer.step()

    def compute_IPN_and_switch_LC(self, Seff_book, Seff_tape):
        IPN = abs(Seff_book + Seff_tape)
        cross_consistent = True
        reason = f"IPN={IPN:.6f}, cc={cross_consistent}"
        if IPN > self.learner.theta_s.item() and cross_consistent:
            self.fsm.transition("S1", reason, force=False)
        else:
            self.fsm.transition("S0", reason, force=False)

    def STN_stop_if_needed(self, BRHL, OTR, SVI):
        _, q_S, q_O, q_B = self.learner()
        trigger = (BRHL >= q_B.item()) or (OTR >= q_O.item()) or (SVI >= q_S.item())
        if trigger:
            reason = f"STN stop: BRHL={BRHL}, OTR={OTR}, SVI={SVI}"
            self.fsm.transition("S⊘", reason, force=True)
            return True
        return False

    def BG_go_nogo(self, OFI, lam, SVI, EVC, OTR, BRHL):
        _, q_S, q_O, q_B = self.learner()
        direction_ok = np.sign(OFI) == np.sign(lam)
        cond_risk = (SVI <= q_S.item()) and (OTR <= q_O.item()) and (BRHL <= q_B.item())
        cond_value = EVC > 0
        return bool(direction_ok and cond_risk and cond_value)

    @staticmethod
    def allocate_intensity(delta_EVC):
        return bool(delta_EVC > 0)

    def estimate_path_gain(self, path: str) -> float:
        if path == "book":
            return float(self.last_Seff_book)
        if path == "tape":
            return float(self.last_Seff_tape)
        return 0.0

    def myelinate_paths(self, paths=("book", "tape")):
        self.priority_paths = {}
        for path in paths:
            delay = torch.tensor(0.0, requires_grad=True)
            gain = torch.tensor(self.estimate_path_gain(path))
            ECE_base = torch.tensor(self.compute_ECE()[0])
            alpha = torch.tensor(1.0)
            EVC_path = gain - (ECE_base + alpha * delay)
            EVC_path.backward()
            sens = abs(delay.grad.item()) if delay.grad is not None else 0.0
            self.priority_paths[path] = sens
        return sorted(self.priority_paths, key=self.priority_paths.get, reverse=True)

    def risk_firewall(self, proposed_exposure: float) -> bool:
        new_exp = self.current_exposure + proposed_exposure
        if abs(new_exp) > self.exposure_limit:
            reason = (
                f"EXPOSURE LIMIT: cur={self.current_exposure}, prop={proposed_exposure}"
            )
            logging.error(reason)
            self.fsm.transition("S⊘", reason, force=True)
            return False
        self.current_exposure = new_exp
        return True

    def check_delay_budget(self, start_time: float) -> bool:
        elapsed = time.time() - start_time
        if elapsed > self.delay_budget:
            logging.warning(f"Delay budget exceeded: {elapsed} > {self.delay_budget}")
            self.fsm.transition("S⊘", "latency budget breach", force=True)
            return False
        return True

    def backtest_pnl_slippage(self, trades: list):
        pnl = sum(t.get("profit", 0.0) for t in trades)
        slippage = sum(t.get("slippage", 0.0) for t in trades)
        self.pnl_history.append(pnl)
        self.slippage_history.append(slippage)
        return float(pnl), float(slippage)

    def update_history(self, delta_P, Q, S, D, OFI, lam, OTR, BRHL):
        self.history["delta_P"].append(float(delta_P))
        self.history["Q"].append(float(Q))
        self.history["S"].append(float(S))
        self.history["D"].append(float(D))
        self.history["OFI"].append(float(OFI))
        self.history["lambda"].append(float(lam))
        self.history["OTR"].append(float(OTR))
        self.history["BRHL"].append(float(BRHL))

    def step(self, tick: dict) -> dict:
        start_time = time.time()

        ok, err = self.sanitize_input(tick)
        if not ok:
            self.fsm.transition("S⊘", f"INVALID_DATA: {err}", force=True)
            return {
                "state": self.fsm.get_state(),
                "action": "STOP_INVALID_DATA",
                "metrics": {},
                "priority_paths": {},
            }

        tick_sync = self.collector.collect(tick)

        S_val = self.compute_spread(tick_sync["p_a1"], tick_sync["p_b1"])
        D_val = self.compute_depth(tick_sync["q_b"], tick_sync["q_a"])
        OFI_val = self.compute_OFI(tick_sync["events"])

        lam_val = self.compute_lambda_kyle()
        OTR_val = self.compute_OTR(
            tick_sync["messages"], tick_sync["trades"], delta_t=100
        )
        SVI_val = self.compute_SVI()
        BRHL_val = self.compute_BRHL(0)

        self.update_history(
            tick_sync["delta_P"],
            tick_sync["Q"],
            S_val,
            D_val,
            OFI_val,
            lam_val,
            OTR_val,
            BRHL_val,
        )

        s_arr = np.array(self.history["S"], dtype=float)
        d_arr = np.array(self.history["D"], dtype=float)
        if s_arr.size > 1:
            combo = np.stack([s_arr, d_arr], axis=1)
            var_book = float(np.mean(np.var(combo, axis=0)))
        else:
            var_book = 1.0

        ofi_arr = np.array(self.history["OFI"], dtype=float)
        var_tape = float(np.var(ofi_arr)) if ofi_arr.size > 1 else 1.0

        PW_book = self.compute_PW(var_book)
        PW_tape = self.compute_PW(var_tape)

        Seff_book = self.compute_Seff(PW_book, S_val - self.S_median)
        Seff_tape = self.compute_Seff(PW_tape, OFI_val)
        self.last_Seff_book = Seff_book
        self.last_Seff_tape = Seff_tape

        self.compute_IPN_and_switch_LC(Seff_book, Seff_tape)

        action = "SCAN_PASSIVE"
        reason = "default S0"
        state_before = self.fsm.get_state()

        if state_before == "S1":
            beta_ofi, r2_ofi = self.compute_beta_OFI()
            if r2_ofi < self.r2_threshold:
                self.fsm.transition("S⊘", f"LOW_R2 {r2_ofi:.3f}", force=True)
                action = "STOP_LOW_CONFIDENCE"
                reason = "beta_OFI R2 below threshold"
            else:
                ECE_val, _ = self.compute_ECE()
                expected_profit = beta_ofi * OFI_val
                EVC_val = self.compute_EVC(expected_profit, ECE_val)

                stopped = self.STN_stop_if_needed(BRHL_val, OTR_val, SVI_val)
                if stopped:
                    action = "STOP_RISK"
                    reason = "STN safety trigger"
                else:
                    allowed = self.BG_go_nogo(
                        OFI_val, lam_val, SVI_val, EVC_val, OTR_val, BRHL_val
                    )
                    if not allowed:
                        self.fsm.transition("S⊘", "NO_GO_CONDITIONS", force=True)
                        action = "STOP_NO_GO"
                        reason = "Go/No-Go denied"
                    else:
                        probe_step = 0.01 * max(abs(expected_profit), abs(ECE_val), 1.0)
                        alt_expected = expected_profit - probe_step
                        alt_ECE = ECE_val + probe_step
                        alt_EVC = self.compute_EVC(alt_expected, alt_ECE)
                        delta_EVC = EVC_val - alt_EVC
                        intensify = self.allocate_intensity(delta_EVC)

                        if intensify and self.risk_firewall(proposed_exposure=1000.0):
                            action = "EXECUTE_AGGRESSIVE"
                            reason = "Go + delta_EVC>0 + exposure ok"
                        else:
                            action = "EXECUTE_PASSIVE"
                            reason = "Go but limited intensity/exposure"

        dummy_trades = [
            {
                "profit": np.random.normal(100, 10),
                "slippage": np.random.normal(0.01, 0.001),
            }
        ]
        self.backtest_pnl_slippage(dummy_trades)

        if self.fsm.get_state() == "S1":
            expected_vec = [0.01, 10.0, 0.9]
            actual_vec = [
                0.01 + np.random.normal(0, 0.005),
                10.0 + np.random.normal(0, 1.0),
                0.9 + np.random.normal(0, 0.05),
            ]
            RPE_val = self.compute_RPE(expected_vec, actual_vec)
            self.update_thresholds_gradient(RPE_val)

        self.myelinate_paths()

        if not self.check_delay_budget(start_time):
            action = "STOP_LATENCY"
            reason = "latency budget breach"

        metrics = {
            "S": S_val,
            "D": D_val,
            "OFI": OFI_val,
            "lambda": lam_val,
            "SVI": SVI_val,
            "BRHL": BRHL_val,
            "OTR": OTR_val,
        }

        self.log_action(action, metrics, reason)

        if self.recorder is not None:
            self.recorder.record_tick(
                tick_sync, {"state": self.fsm.get_state(), "action": action}, metrics
            )

        return {
            "state": self.fsm.get_state(),
            "action": action,
            "metrics": metrics,
            "priority_paths": self.priority_paths,
        }


class StateSimulator:
    def __init__(self, nlca: NLCA):
        self.nlca = nlca

    def simulate(self, ticks: list, num_steps: int = 100):
        results = []
        for i in range(num_steps):
            tick = ticks[i % len(ticks)]
            out = self.nlca.step(tick)
            results.append(out)

        states = [r["state"] for r in results]
        transitions = sum(
            1 for i in range(1, len(states)) if states[i] != states[i - 1]
        )
        logging.info(f"Sim states: {states}")
        logging.info(f"Transitions: {transitions}")

        return {
            "transitions": transitions,
            "results": results,
            "final_state": self.nlca.fsm.get_state(),
        }


class MetricsDashboard:
    def __init__(self, tick_queue: queue.Queue):
        if dash is None:
            raise RuntimeError("Dash/Plotly недоступні в середовищі")
        self.tick_queue = tick_queue
        self.app = dash.Dash(__name__)
        self.data_buffer = []

        self.app.layout = html.Div(
            [
                html.H2("TradePulse NLCA Monitor"),
                dcc.Interval(id="update-interval", interval=1000, n_intervals=0),
                dcc.Graph(id="spread_graph"),
                dcc.Graph(id="depth_graph"),
                html.Pre(id="state_text"),
            ]
        )

        @self.app.callback(
            [
                Output("spread_graph", "figure"),
                Output("depth_graph", "figure"),
                Output("state_text", "children"),
            ],
            [Input("update-interval", "n_intervals")],
        )
        def update_graphs(_):
            while True:
                try:
                    item = self.tick_queue.get_nowait()
                    self.data_buffer.append(item)
                except queue.Empty:
                    break

            if len(self.data_buffer) == 0:
                return go.Figure(), go.Figure(), "No data yet"

            ts_arr = [x["timestamp"] for x in self.data_buffer]
            spread_arr = [x["p_a1"] - x["p_b1"] for x in self.data_buffer]
            depth_arr = [
                float(np.sum(x["q_a"][:5]) + np.sum(x["q_b"][:5]))
                for x in self.data_buffer
            ]

            spread_fig = go.Figure(
                data=[go.Scatter(x=ts_arr, y=spread_arr, mode="lines", name="Spread")]
            )
            depth_fig = go.Figure(
                data=[go.Scatter(x=ts_arr, y=depth_arr, mode="lines", name="Depth")]
            )

            last_state = "N/A"
            if hasattr(self, "last_state"):
                last_state = self.last_state

            return spread_fig, depth_fig, f"Last state: {last_state}"

    def serve_forever(self, host: str = "127.0.0.1", port: int = 8050):
        """
        Start the dashboard server.

        Args:
            host: Network interface to bind to. Default '127.0.0.1' (localhost only).
                  Use '0.0.0.0' only in containerized environments with proper firewall rules.
            port: TCP port to listen on.
        """
        # Security: Default to localhost binding unless explicitly overridden
        self.app.run_server(host=host, port=port)


def load_runtime_config(path: str):
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    return cfg


def build_arg_parser():
    parser = argparse.ArgumentParser(description="TradePulse NLCA runtime")
    parser.add_argument(
        "--config", type=str, default="config.yaml", help="Path to YAML config"
    )
    return parser
