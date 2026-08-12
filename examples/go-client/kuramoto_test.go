package goclient

import (
	"math"
	"testing"
)

func TestOrderParameterRange(t *testing.T) {
	phases := []float64{0, math.Pi / 2, math.Pi, 3 * math.Pi / 2}
	r := OrderParameter(phases)
	if r < 0 || r > 1 {
		t.Fatalf("R out of range: %v", r)
	}
}

func TestOrderParameterAllocs(t *testing.T) {
	phases := make([]float64, 1024)
	allocs := testing.AllocsPerRun(1000, func() {
		_ = OrderParameter(phases)
	})
	if allocs != 0 {
		t.Fatalf("expected 0 allocs/op, got %v", allocs)
	}
}

func TestLUTApproximation(t *testing.T) {
	phases := []float64{0.1, 0.2, 1.4, 2.8, 3.2, 5.9}
	exact := OrderParameter(phases)
	lut := NewLUTKuramoto(4096)
	approx := lut.OrderParameterLUT(phases)
	if math.Abs(exact-approx) > 0.01 {
		t.Fatalf("LUT approximation too coarse: exact=%v approx=%v", exact, approx)
	}
}

func TestLUTAllocs(t *testing.T) {
	phases := make([]float64, 1024)
	lut := NewLUTKuramoto(4096)
	allocs := testing.AllocsPerRun(1000, func() {
		_ = lut.OrderParameterLUT(phases)
	})
	if allocs != 0 {
		t.Fatalf("expected 0 allocs/op for LUT, got %v", allocs)
	}
}

func BenchmarkOrderParameter(b *testing.B) {
	phases := make([]float64, 4096)
	for i := range phases {
		phases[i] = float64(i) * 0.001
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = OrderParameter(phases)
	}
}

func BenchmarkOrderParameterLUT(b *testing.B) {
	phases := make([]float64, 4096)
	for i := range phases {
		phases[i] = float64(i) * 0.001
	}
	lut := NewLUTKuramoto(4096)
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = lut.OrderParameterLUT(phases)
	}
}
