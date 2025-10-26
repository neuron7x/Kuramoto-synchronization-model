package vpin

import (
	"errors"
	"math"
)

// Config represents runtime parameters controlling the VPIN calculation.
type Config struct {
	// BucketSize defines the rolling window (in trades) over which totals and imbalances
	// are aggregated. It must be strictly positive.
	BucketSize int
	// Threshold represents the VPIN level above which alerts should be emitted.
	// It must be strictly positive.
	Threshold float64
}

// Validate ensures the configuration uses sensible values.
func (c Config) Validate() error {
	if c.BucketSize <= 0 {
		return errors.New("vpin: bucket size must be positive")
	}
	if math.IsNaN(c.Threshold) || math.IsInf(c.Threshold, 0) || c.Threshold <= 0 {
		return errors.New("vpin: threshold must be a positive finite number")
	}
	return nil
}

// VolumeObservation captures the volume totals for a single trade bucket.
type VolumeObservation struct {
	Total float64
	Buy   float64
	Sell  float64
}

// Alert represents a VPIN threshold breach produced during a calculation.
type Alert struct {
	Index int
	Value float64
}

// Calculation encapsulates the VPIN series and accompanying alerts.
type Calculation struct {
	Values []float64
	Alerts []Alert
}

// Calculator executes VPIN computations for the configured parameters.
type Calculator struct {
	config Config
}

// NewCalculator creates a VPIN calculator for the provided configuration.
func NewCalculator(cfg Config) (*Calculator, error) {
	if err := cfg.Validate(); err != nil {
		return nil, err
	}
	return &Calculator{config: cfg}, nil
}

// Calculate computes the VPIN time series for the provided observations.
//
// Observations are sanitised before processing: NaN, +/-Inf, and negative values
// are coerced to zero. Alerts are emitted when the VPIN series breaches the
// configured threshold once at least BucketSize observations have been
// processed.
func (c *Calculator) Calculate(observations []VolumeObservation) Calculation {
	length := len(observations)
	if length == 0 {
		return Calculation{Values: []float64{}, Alerts: []Alert{}}
	}

	totals := make([]float64, length)
	imbalances := make([]float64, length)
	for i, obs := range observations {
		total := sanitise(obs.Total)
		buy := sanitise(obs.Buy)
		sell := sanitise(obs.Sell)
		totals[i] = total
		imbalances[i] = math.Abs(buy - sell)
	}

	totalSums := rollingSum(totals, c.config.BucketSize)
	imbalanceSums := rollingSum(imbalances, c.config.BucketSize)

	values := make([]float64, length)
	alerts := make([]Alert, 0, length)
	for idx := 0; idx < length; idx++ {
		sum := totalSums[idx]
		if sum <= 0 {
			continue
		}
		ratio := imbalanceSums[idx] / sum
		if ratio < 0 {
			ratio = 0
		}
		if ratio > 1 {
			ratio = 1
		}
		values[idx] = ratio
		if idx+1 >= c.config.BucketSize && ratio >= c.config.Threshold {
			alerts = append(alerts, Alert{Index: idx, Value: ratio})
		}
	}

	return Calculation{Values: values, Alerts: alerts}
}

func sanitise(value float64) float64 {
	if math.IsNaN(value) || math.IsInf(value, 0) || value <= 0 {
		return 0
	}
	return value
}

func rollingSum(values []float64, window int) []float64 {
	length := len(values)
	result := make([]float64, length)
	if window <= 0 || length == 0 {
		return result
	}

	var accumulator float64
	for idx, value := range values {
		accumulator += value
		if idx >= window {
			accumulator -= values[idx-window]
		}
		result[idx] = accumulator
	}
	return result
}
