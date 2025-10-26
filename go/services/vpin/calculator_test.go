package vpin

import (
	"math"
	"testing"
)

func TestNewCalculatorValidation(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		cfg  Config
		ok   bool
	}{
		{name: "valid", cfg: Config{BucketSize: 50, Threshold: 0.3}, ok: true},
		{name: "zero bucket", cfg: Config{BucketSize: 0, Threshold: 0.3}},
		{name: "negative bucket", cfg: Config{BucketSize: -5, Threshold: 0.3}},
		{name: "zero threshold", cfg: Config{BucketSize: 10, Threshold: 0}},
		{name: "negative threshold", cfg: Config{BucketSize: 10, Threshold: -1}},
		{name: "nan threshold", cfg: Config{BucketSize: 10, Threshold: math.NaN()}},
		{name: "inf threshold", cfg: Config{BucketSize: 10, Threshold: math.Inf(1)}},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			calc, err := NewCalculator(tt.cfg)
			if tt.ok {
				if err != nil {
					t.Fatalf("expected success, got error: %v", err)
				}
				if calc == nil {
					t.Fatal("expected calculator instance, got nil")
				}
			} else if err == nil {
				t.Fatalf("expected validation error for cfg=%+v", tt.cfg)
			}
		})
	}
}

func TestCalculatorCalculateDeterministicSeries(t *testing.T) {
	t.Parallel()

	calc, err := NewCalculator(Config{BucketSize: 3, Threshold: 0.3})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	observations := []VolumeObservation{
		{Total: 100, Buy: 60, Sell: 40},
		{Total: 120, Buy: 70, Sell: 50},
		{Total: 80, Buy: 20, Sell: 60},
		{Total: 150, Buy: 100, Sell: 50},
		{Total: 130, Buy: 40, Sell: 90},
	}

	got := calc.Calculate(observations)

	wantValues := []float64{
		0.2,
		0.18181818181818182,
		0.26666666666666666,
		0.3142857142857143,
		0.3888888888888889,
	}

	if len(got.Values) != len(wantValues) {
		t.Fatalf("unexpected values length: got %d want %d", len(got.Values), len(wantValues))
	}

	const tolerance = 1e-9
	for i := range wantValues {
		if diff := math.Abs(got.Values[i] - wantValues[i]); diff > tolerance {
			t.Fatalf("values[%d]=%f, want %f (diff=%f)", i, got.Values[i], wantValues[i], diff)
		}
	}

	wantAlerts := []Alert{{Index: 3, Value: wantValues[3]}, {Index: 4, Value: wantValues[4]}}
	if len(got.Alerts) != len(wantAlerts) {
		t.Fatalf("unexpected alerts length: got %d want %d", len(got.Alerts), len(wantAlerts))
	}
	for i := range wantAlerts {
		if got.Alerts[i].Index != wantAlerts[i].Index {
			t.Fatalf("alert[%d] index=%d want %d", i, got.Alerts[i].Index, wantAlerts[i].Index)
		}
		if diff := math.Abs(got.Alerts[i].Value - wantAlerts[i].Value); diff > tolerance {
			t.Fatalf("alert[%d] value=%f want %f (diff=%f)", i, got.Alerts[i].Value, wantAlerts[i].Value, diff)
		}
	}
}

func TestCalculatorCalculateHandlesEdgeCases(t *testing.T) {
	t.Parallel()

	calc, err := NewCalculator(Config{BucketSize: 4, Threshold: 0.6})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	observations := []VolumeObservation{
		{Total: -10, Buy: -5, Sell: -5},
		{Total: math.NaN(), Buy: 40, Sell: math.Inf(1)},
		{Total: 100, Buy: 55, Sell: 45},
		{Total: 110, Buy: 60, Sell: 50},
		{Total: 90, Buy: -10, Sell: 100},
	}

	got := calc.Calculate(observations)

	wantValues := []float64{0, 0, 0.5, 0.2857142857142857, 0.5333333333333333}
	if len(got.Values) != len(wantValues) {
		t.Fatalf("unexpected length: got %d want %d", len(got.Values), len(wantValues))
	}

	const tolerance = 1e-9
	for i := range wantValues {
		if diff := math.Abs(got.Values[i] - wantValues[i]); diff > tolerance {
			t.Fatalf("values[%d]=%f want %f (diff=%f)", i, got.Values[i], wantValues[i], diff)
		}
	}

	if len(got.Alerts) != 0 {
		t.Fatalf("expected no alerts, got %v", got.Alerts)
	}
}

func TestCalculatorCalculateEmptyInput(t *testing.T) {
	t.Parallel()

	calc, err := NewCalculator(Config{BucketSize: 2, Threshold: 0.2})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	result := calc.Calculate(nil)
	if result.Values == nil || len(result.Values) != 0 {
		t.Fatalf("expected empty values slice, got %#v", result.Values)
	}
	if result.Alerts == nil || len(result.Alerts) != 0 {
		t.Fatalf("expected empty alerts slice, got %#v", result.Alerts)
	}
}

func TestRollingSumWindowGreaterThanLength(t *testing.T) {
	t.Parallel()

	values := []float64{1, 2, 3}
	got := rollingSum(values, 5)
	want := []float64{1, 3, 6}
	for i := range want {
		if got[i] != want[i] {
			t.Fatalf("rollingSum mismatch at %d: got %f want %f", i, got[i], want[i])
		}
	}
}
