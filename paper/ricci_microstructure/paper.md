---
title: "Ricci Curvature on Order-Flow-Imbalance Graphs as a Short-Horizon Return Predictor in Cryptocurrency Perpetual Futures"
author:
  - name: Yaroslav Vasylenko
    affiliation: neuron7xLab
    orcid: TBD
date: \today
classification: q-fin.TR; q-fin.ST
license: CC-BY-4.0 (manuscript); MIT (code)
---

## Abstract

We test whether the minimum Ollivier--Ricci curvature $\kappa_{\min}$ of a
rolling correlation graph on per-symbol order-flow imbalance (OFI) predicts
forward log-returns in cryptocurrency perpetual futures. On a $\sim 5.3$-hour,
10-symbol, 1-second Binance USDT-M book-depth stream ($n = 19{,}081$), we
subject the $\kappa_{\min}$-to-180s-return relationship to eleven mutually
orthogonal validation axes: permutation kill test, block-bootstrap CI,
deflated Sharpe adjustment, purged and embargoed $K$-fold CV, mutual
information, lag attribution, spectral redness, DFA Hurst, pairwise
transfer entropy, conditional transfer entropy (BTC-partialled), and
rolling walk-forward stability. Each axis
falsifies a distinct failure mode (spurious correlation, multiple-testing
inflation, look-ahead leakage, common-factor confounding, single-window
overfitting). All axes concord: IC $= 0.122$ at permutation $p = 0.002$;
95\% block-bootstrap CI $[0.029, 0.210]$ excludes zero; deflated Sharpe
$\mathrm{DSR}_{\mathrm{IC}} = 15.1$
(\textbf{caveat}: this is the deflated Sharpe of the \emph{IC bar series}
on a single 5.3-hour in-sample session, computed per
Bailey \& L\'opez de Prado (2014); it is NOT an annualised trading Sharpe and
should not be compared to one --- the realistic capital-deployable edge
after frictions is characterised by the maker-fill break-even
$f^{\star}\approx 0.232$ in \S\ref{cost-model});
5/5 CV folds positive; $\beta = 1.80$ and $H = 1.01$ agree on
persistence; 45/45 pairs show bidirectional transfer entropy; 33/36 pairs
retain private coupling after BTC-OFI conditioning; 82.1\% of 40-minute
walk-forward windows reproduce the edge at $p<0.05$. Under a realistic
taker/maker cost model, regime-gated diurnally-adjusted execution breaks
even at maker-fill $f^{\star} \approx 0.232$---below the 0.40--0.70
achievable with post-only routing. We disclose explicit limitations
(single session, simulation P\&L, single asset class) and release frozen
gate fixtures and reproducibility tests.

\textbf{Keywords:} Ollivier--Ricci curvature, order-flow imbalance,
transfer entropy, cryptocurrency microstructure, out-of-sample validation,
deflated Sharpe ratio, purged cross-validation.

## 1. Introduction

Cross-sectional regime signals in high-frequency markets are widely studied
but poorly falsified. Practitioner claims often report an information
coefficient (IC) or Sharpe ratio on a single in-sample window without
correcting for look-ahead bias, multiple-testing inflation, time-series
autocorrelation, or common-factor confounding. The question of whether a
reported edge is a real statistical object or a selection artefact is
typically decided by *authority* (who publishes it) rather than by
*orthogonal validation*.

The present paper addresses that gap for one specific candidate edge in one
specific venue. We ask whether the minimum Ollivier--Ricci curvature
$\kappa_{\min}$ of a rolling OFI correlation graph carries genuine
predictive information about forward short-horizon returns in
cryptocurrency perpetual futures. The curvature choice is motivated by
prior work of \citet{sandhu2016marketfragility} and \citet{bai2020networkricci}
who use Ricci curvature as a systemic-fragility indicator on equity and
FX networks; here we apply it not to daily returns but to sub-second
order-flow correlation graphs and treat $\kappa_{\min}$ as a real-time
feature rather than a regime label.

Our contribution is methodological as much as empirical. We do not merely
report that the signal works: we construct eleven falsification axes, each
targeting a distinct plausible failure mode, and show that a single
observation fails to break through any of them. We release the frozen
per-fold and per-session gate fixtures, the full pipeline scripts, and a
CI-level integrity test suite so that the claim is auditable without
privileged access to the substrate.

The design philosophy is deliberately asymmetric: the burden of evidence
sits on the signal, not on the reviewer. A signal that survives eleven
orthogonal falsification attempts is not thereby *true*, but it is now a
hypothesis with respect to which the engineering and statistical apparatus
has been exhausted at this sample size.

## 2. Data and preliminaries

The substrate is a single $\sim 5.3$-hour block of
\texttt{depth5@100ms} WebSocket frames from Binance USDT-M perpetual
futures, covering 10 symbols (BTC, ETH, SOL, XRP, BNB, ADA, DOGE, LINK,
AVAX, LTC paired with USDT). Frames are re-sampled onto a strict 1-second
grid; gaps are forward-filled for at most one bar and dropped otherwise.
Final panel: $n = 19{,}081$ rows by 10 symbols.

For each symbol and each 1-second bar we compute the signed order-flow
imbalance (OFI) following \citet{cont2014ofi} over the five nearest price
levels on both sides of the book. Symbol-wise OFI is then standardised to
unit variance in a 300-bar trailing window. The cross-sectional correlation
matrix on a trailing 120-second window is mapped to a complete weighted
graph on the 10 symbols; Ollivier--Ricci curvature is computed for every
edge as in \citet{ollivier2009ricci}, and $\kappa_{\min}(t)$ is the minimum
over all 45 edges at time $t$.

The forward target is the 180-second log-return of the equal-weight
basket. All seeds are fixed at 42; all windows are strictly backward-
looking; no future-period data enters any feature at time $t$. Raw data
and derived gate fixtures are deposited in \texttt{results/gate\_fixtures/}
and hashed into \texttt{MANIFEST.sha256}.

## 3. Methodology

The empirical core is an eleven-axis falsification battery. For each axis
we state the failure mode it attacks, the test statistic, the decision rule,
and the verdict.

1. **Primary kill test.** IC computed on raw $(\kappa_{\min}, r_{+180})$
   pairs; residual IC after partialling out the contemporaneous mid-price
   return baseline; a 1,000-resample permutation null on the residual IC.
   Decision: proceed iff $\text{IC} > 0.08$ and $p_{null} < 0.05$ and
   $\text{residual IC} \geq 0.8 \cdot \text{raw IC}$.
2. **Stationary block-bootstrap CI** at block length 300 rows
   \citep{politis1994stationary}; edge is significant iff the 95\% CI
   excludes zero.
3. **Deflated Sharpe ratio} \citep{lopezdeprado2014deflated} with
   $n_{\text{trials}} = 15$ (the sum of regime, diurnal, and horizon
   sweeps); corrects for implicit multiple testing from signal search.
4. **Purged and embargoed $K$-fold CV} \citep{lopezdeprado2018afml} at
   $K = 5$, purge horizon 180 rows, embargo 60 rows each side; decision
   rule: all folds must yield positive IC.
5. **Mutual information** with 32-bin histogram estimator; catches
   non-linear dependence invisible to Spearman.
6. **Lag attribution.** IC is computed at lags $\ell \in [-60s, +60s]$;
   if the peak IC occurs at negative lag, the signal leads the return and
   is not a causally-inverted echo of past returns.
7. **Power spectrum.** Welch PSD with 600-second segments, Hann window;
   log-log slope $\beta$ and dominant periods. A white-noise signal yields
   $\beta \approx 0$; a pure oscillation yields a sharp peak at a finite
   frequency; a persistent-memory signal yields $\beta \approx 2$.
8. **Hurst exponent via DFA-1** \citep{peng1994dfa}; scale-free cross-check
   of the spectral result. We require $H$ and $\beta$ to concord on the
   persistence regime.
9. **Pairwise transfer entropy** \citep{schreiber2000te} with a
   100-surrogate time-shuffled null at 1-second lag on all 45 ordered
   symbol pairs; attacks the failure mode that the curvature signal is a
   re-expression of contemporaneous correlation rather than a compression
   of genuine dynamical coupling.
10. **Conditional transfer entropy** with BTCUSDT OFI as the conditioning
    channel $Z$; attacks the orthogonal failure mode that the pairwise
    bidirectional flow of axis 9 could itself be an artefact of every
    symbol responding to a common market-wide factor.
11. **Rolling walk-forward stability**: 56 non-overlapping 40-minute windows
    stepped every 5 minutes; each window independently estimates IC and a
    permutation $p$-value; we report the fraction of positive windows and
    the fraction passing $p < 0.05$.

Economic viability is assessed separately: a symmetric taker/maker cost
model with taker fee $= 4$ bp, maker rebate $= -2$ bp, and the break-even
maker fraction $f^{\star}$ solved such that the measured gross IC
translates to zero net P\&L. A hyperparameter ablation over the
regime-quantile and regime-window axes reports whether $f^{\star}$ survives
natural configuration drift.

## 4. Results

Detailed per-axis results are tabulated in the evidence appendix
(\texttt{research/microstructure/FINDINGS.md}, sections 1--6, with frozen
JSON fixtures referenced by SHA-256 in \texttt{MANIFEST.sha256}). The
consolidated verdict is summarised in Table 1.

\begin{center}
\begin{tabular}{lll}
\hline
Axis & Metric & Verdict \\
\hline
Kill test             & IC = 0.122, $p = 0.002$       & pass \\
Block-bootstrap CI    & $[0.029, 0.210]$ excludes 0   & pass \\
Deflated Sharpe       & DSR = 15.1                    & pass \\
Purged $K$-fold CV    & 5/5 folds positive            & pass \\
Mutual information    & MI = 0.078 nats               & pass \\
Lag attribution       & peak at $-30$s                & pass \\
Power spectrum        & $\beta = 1.80$, persistent    & pass \\
DFA Hurst             & $H = 1.01$, $R^2 = 0.98$      & pass \\
Pairwise TE           & 45/45 bidirectional           & pass \\
Conditional TE (BTC)  & 33/36 private flow            & pass \\
Rolling walk-forward  & 82\% positive at $p < 0.05$   & pass \\
\hline
\end{tabular}
\end{center}

The edge is concordant on every axis on which it can be tested with the
available sample; the null hypothesis that $\kappa_{\min}$ carries no
predictive information is rejected in eleven non-overlapping ways.

## 5. Economic viability

Under the cost model of Section 3, the unconditional strategy (trade on
every $\kappa_{\min}$ signal regardless of regime) is not bracketed by the
sweep: the taker-fee cost exceeds the gross IC at any plausible maker
fill. Regime gating to the top realised-volatility quartile
(\texttt{REGIME\_Q75}) lowers the break-even maker fraction to
$f^{\star} = 0.407$; adding the UTC diurnal sign-flip filter
(\texttt{REGIME\_Q75 + DIURNAL}) lowers it further to $f^{\star} = 0.232$.
Production Binance USDT-M maker-fill rates for post-only orders with
standard smart-routing fall in the 0.40--0.70 band, so the combined
strategy is economically realisable on this substrate.

The $f^{\star}$ value is a *point estimate*, not a robust invariant. A
$3 \times 3$ grid sweep over regime quantile and regime window shows the
break-even fraction drifts by $\pm 60\%$ (range $[0.138, 0.372]$) across
reasonable hyperparameter choices. The strategic claim ("edge is
economically realisable") survives every ablation cell---each cell's
$f^{\star}$ lies below the 0.70 production ceiling---but the precise
value $0.232$ should be read as "likely achievable" rather than
"precisely calibrated".

## 6. Related work

Ollivier's discrete Ricci curvature \citep{ollivier2009ricci} has been
applied to financial networks in the context of systemic fragility. The
closest precedents are \citet{sandhu2016marketfragility} on equity
co-movement graphs and \citet{bai2020networkricci} who link discrete
curvature collapse to market crises. Both treat Ricci curvature as a
slow-moving aggregate stability indicator on daily or weekly windows. The
present work differs on three axes: (i) sub-second temporal resolution on
streaming order-book data rather than close-to-close prices; (ii)
$\kappa_{\min}$ treated as a real-time predictive feature rather than a
regime label; and (iii) exhaustive falsification rather than descriptive
fit.

The methodological apparatus is borrowed rather than novel: the deflated
Sharpe ratio and purged $K$-fold CV come from
\citet{lopezdeprado2014deflated,lopezdeprado2018afml}; the stationary
bootstrap from \citet{politis1994stationary}; transfer entropy from
\citet{schreiber2000te}; the DFA-1 Hurst estimator from
\citet{peng1994dfa}. Our contribution is not in inventing any one of
these but in composing them into a single fail-closed battery applied to
one concrete candidate edge.

OFI as a return predictor is well established
\citep{cont2014ofi}; the novelty here is using the *cross-sectional
correlation structure of OFI* (rather than the per-symbol OFI itself) as
the input to a curvature operator, and treating the result as a regime
feature.

## 7. Limitations (honest)

1. **Single session.** The entire quantitative battery runs on one
   $\sim 5.3$-hour window. A diurnal sign flip observed across three
   non-overlapping sessions confirms the structural finding (the
   polarity is time-varying) but not the quantitative gate values.
   Multi-day substrate activation is flagged as the primary next
   iteration.
2. **Simulation P\&L only.** All profit-and-loss numbers are derived
   from a symmetric taker/maker cost model; no order was actually
   placed. Adverse selection on aggressive taker legs is not modelled.
3. **Single asset class.** USDT-margined crypto perpetuals only. The
   edge may or may not transfer to cash equity, FX, or USD-margined
   futures; no extrapolation is claimed.
4. **Latency assumption.** The 30-second decision horizon assumes
   round-trip decision-to-fill under 100 ms. With $\tau_{\text{decay}}
   \approx 61$ s for the $\kappa_{\min}$ signal, any slippage beyond
   1 s materially erodes the measured IC.
5. **No execution-topology model.** Book skew, cancel--replace dynamics,
   queue-position effects, and rate-limit competition are outside the
   cost model.
6. **Point estimate of $f^{\star}$.** The break-even maker fraction
   varies by $\pm 60\%$ under reasonable hyperparameter perturbation;
   the quantitative gate is not robust, though the strategic verdict
   is.

## 8. Conclusion

The minimum Ollivier--Ricci curvature of a rolling OFI correlation graph
is a statistically well-characterised short-horizon predictor of forward
returns in one cryptocurrency perpetual-futures substrate. Eleven
falsification axes concord; none dominates the result; the edge survives
regime-gated execution with realistic cost assumptions.

The main deliverable is not the numerical result but the falsification
protocol: every published claim is accompanied by the axis that could
have broken it. We release the full pipeline, gate fixtures, and
reproducibility tests under MIT licence, and the manuscript text under
CC-BY-4.0, so that the verdict can be re-derived from first principles
without privileged access.

Next iterations target multi-session substrate activation, live-paper
execution on Binance testnet with a queue-position-aware maker engine,
and cross-asset transfer to USD-margined futures.

## Reproducibility

Full pipeline and invocation instructions are frozen in
\texttt{research/microstructure/FINDINGS.md} section 9. The frozen
verdict JSON files and their SHA-256 hashes are listed in
\texttt{MANIFEST.sha256}. Test-level integrity is gated in CI via the
\texttt{l2-demo-gate.yml} workflow; regression or silent drift trips
the gate.

## References

References are tracked in \texttt{references.bib}; the `\cite{...}`
tokens in this manuscript compile under BibTeX.
