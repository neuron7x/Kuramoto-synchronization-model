package goclient

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestDefaultBackoffConfig(t *testing.T) {
	cfg := DefaultBackoffConfig()
	if cfg.MaxRetries != 5 {
		t.Fatalf("expected retries=5 got %d", cfg.MaxRetries)
	}
	if cfg.BaseDelay != 500*time.Millisecond {
		t.Fatalf("expected base delay 500ms got %v", cfg.BaseDelay)
	}
	if cfg.Factor != 2.0 {
		t.Fatalf("expected factor=2 got %v", cfg.Factor)
	}
}

func TestHealthCheckOK(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/health" {
			t.Fatalf("unexpected path %s", r.URL.Path)
		}
		w.WriteHeader(http.StatusOK)
	}))
	defer ts.Close()

	err := HealthCheck(context.Background(), ts.URL, ts.Client())
	if err != nil {
		t.Fatalf("expected no health error got %v", err)
	}
}

func TestHealthCheckNon200(t *testing.T) {
	ts := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusServiceUnavailable)
	}))
	defer ts.Close()

	err := HealthCheck(context.Background(), ts.URL, ts.Client())
	if err == nil {
		t.Fatal("expected health error")
	}
}
