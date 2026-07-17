# Part 4 — Technical Appendix and Sources

Exact formulas for whoever builds a specific phase from
`READINESS_3_PLAN.md`, and the source of every research claim in the
previous parts.

## Formulas

### WAPE — Weighted Absolute Percentage Error

```
WAPE = Σ|actual - predicted| / Σ|actual|
```

The difference from MAPE: the denominator is a sum, not an average of
individual ratios — so a product with a small actual value does not blow up
the metric the way it does in MAPE (which is precisely why the
divide-by-zero protection exists in `evaluation.py` today). Computed at the
whole-catalogue level, not per product — this is what makes it an
understandable "practical accuracy": "we were off by X% of total demand",
not an average of scattered relative errors.

### FVA — Forecast Value Added

```
FVA(model) = Error(naive_baseline) - Error(model)
```

Positive = the model added real value over the naive forecast. Negative or
zero = the complexity bought nothing, and the recommendation there is to use
the naive one itself — cheaper and faster. Always measured against a fixed
baseline (Naive, not "the latest best model") so the comparison stays fair
over time.

### Safety stock — variable demand and lead time

```
SS = z × √(σ²_d × L + μ²_d × σ²_L)
```

where `z` is the service-level factor (1.65 for 95%, 2.33 for 99%), `σ_d`
the daily demand standard deviation, `L` the mean lead time, `μ_d` the mean
daily demand, `σ_L` the lead-time standard deviation. **Needs actual
lead-time data from a stock file — not estimated without it.**

### Reorder Point

```
ROP = (μ_d × L) + SS
```

### Level alignment — Bottom-Up (the first, simplest step)

Category forecast = sum of its products' forecasts directly. No statistical
adjustment, no matrices. Sufficient as a first step and arithmetically
coherent by definition. **MinT** (Minimum Trace, Wickramasuriya et al. 2019)
is the more accurate standard when an optimal error distribution across all
levels (both up and down together) is needed — deferred until a real need
for accuracy beyond Bottom-Up is proven.

## Research sources

### Market and competitors
- [Best Demand Planning Software in 2026](https://www.mainconverter.com/list-of-demand-planning-softwares/)
- [Best SCM Software 2026: Kinaxis vs SAP IBP vs o9 vs Blue Yonder](https://www.demystifyingplm.com/best-scm-software-2026)
- [Netstock Integrations](https://www.netstock.com/integrations/)
- [Netstock vs Streamline (GMDH)](https://gmdhsoftware.com/netstock-vs-streamline/)
- [frePPLe — open source supply chain planning](https://github.com/frePPLe/frepple)
- [OSI: frePPLe + Odoo integration](https://www.opensourceintegrators.com/publications/build-supply-chain-resiliency-odoo-erp-and-frepple)

### The M5 competition and statistical lessons
- [M5 accuracy competition: Results, findings, and conclusions (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0169207021001874)
- [The M5 uncertainty competition (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0169207021001722)

### Metrics
- [WAPE: Weighted Absolute Percentage Error — Rob J Hyndman](https://robjhyndman.com/hyndsight/wape.html)
- [Forecast Accuracy Metrics: MAPE, WAPE, Bias Explained](https://www.demandplan.io/insights/forecast-accuracy-metrics)
- [Measuring forecast model accuracy — AWS](https://aws.amazon.com/blogs/machine-learning/measuring-forecast-model-accuracy-to-optimize-your-business-objectives-with-amazon-forecast/)

### Forecast Value Added
- [Forecast value added in demand planning (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S0169207024000736)
- [How To Use Forecast Value Added Analysis](https://demand-planning.com/2018/02/12/what-is-forecast-value-added-analysis/)

### Level alignment
- [Forecast reconciliation: A review — Athanasopoulos/Hyndman](https://robjhyndman.com/papers/hf_review.pdf)
- [How to Forecast Hierarchical Time Series — Towards Data Science](https://towardsdatascience.com/how-to-forecast-hierarchical-time-series-75f223f79793/)

### Safety stock and MEIO
- [Reorder Point vs. Safety Stock — GAINS](https://gainsystems.com/blog/reorder-point-vs-safety-stock-balancing-inventory-in-retail/)
- [A guide to echelon inventory: multi-echelon optimization](https://www.cleverence.com/articles/for-business/echelon-inventory-4726/)

### The new product (Cold Start)
- [New Product Demand Forecasting Without History](https://www.fygurs.com/use-cases/new-product-demand-forecasting-cold-start)
- [Generate cold start forecasts — Amazon Forecast](https://aws.amazon.com/blogs/machine-learning/generate-cold-start-forecasts-for-products-with-no-historical-data-using-amazon-forecast-now-up-to-45-more-accurate/)

### Time-series foundation models (context, not immediate recommendation)
- [Benchmarking a time-series foundation model (TimeGPT)](https://www.sciencedirect.com/science/article/pii/S2666827025001847)
- [Time Series Foundation Models: Benchmarking Challenges](https://arxiv.org/html/2510.13654v1)

### Accounts and collaboration
- [Streamlit: User authentication and information](https://docs.streamlit.io/develop/concepts/connections/authentication)
- [st.login — Streamlit Docs](https://docs.streamlit.io/develop/api-reference/user/st.login)

### Amazon Forecast's fate (competitive context)
- [AWS Lifecycle Changes](https://aws.amazon.com/products/lifecycle/)

## Methodological note

These sources are web-search results dated 2026-07-17, and some (such as the
exact Netstock/GMDH pricing) are not fully published — this is stated
explicitly where relevant instead of inventing a number. Any pricing or
commercial-positioning decision needs direct verification from the source at
execution time, not reliance on this research snapshot alone.
