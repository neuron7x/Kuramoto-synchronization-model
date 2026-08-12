package goclient

import "math"

// OrderParameter computes Kuramoto R(t) in one pass and zero allocations.
func OrderParameter(phases []float64) float64 {
	n := len(phases)
	if n == 0 {
		return 0
	}
	var sumCos, sumSin float64
	for _, th := range phases {
		sumCos += math.Cos(th)
		sumSin += math.Sin(th)
	}
	invN := 1.0 / float64(n)
	x := sumCos * invN
	y := sumSin * invN
	return math.Hypot(x, y)
}

// LUTKuramoto precomputes sin/cos tables for low-latency phase streams.
type LUTKuramoto struct {
	bins int
	cos  []float64
	sin  []float64
}

func NewLUTKuramoto(bins int) *LUTKuramoto {
	if bins < 256 {
		bins = 256
	}
	k := &LUTKuramoto{bins: bins, cos: make([]float64, bins), sin: make([]float64, bins)}
	for i := 0; i < bins; i++ {
		th := 2.0 * math.Pi * float64(i) / float64(bins)
		k.cos[i] = math.Cos(th)
		k.sin[i] = math.Sin(th)
	}
	return k
}

// OrderParameterLUT computes R(t) using table lookup, 0 allocs/op.
func (k *LUTKuramoto) OrderParameterLUT(phases []float64) float64 {
	n := len(phases)
	if n == 0 {
		return 0
	}
	var sumCos, sumSin float64
	scale := float64(k.bins) / (2.0 * math.Pi)
	for _, th := range phases {
		idx := int(th*scale) % k.bins
		if idx < 0 {
			idx += k.bins
		}
		sumCos += k.cos[idx]
		sumSin += k.sin[idx]
	}
	invN := 1.0 / float64(n)
	return math.Hypot(sumCos*invN, sumSin*invN)
}
