package goclient

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

type BackoffConfig struct {
	MaxRetries int
	BaseDelay  time.Duration
	Factor     float64
}

func DefaultBackoffConfig() BackoffConfig {
	return BackoffConfig{MaxRetries: 5, BaseDelay: 500 * time.Millisecond, Factor: 2.0}
}

func NewJSONLogger() *slog.Logger {
	return slog.New(slog.NewJSONHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
}

func HealthCheck(ctx context.Context, baseURL string, client *http.Client) error {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, fmt.Sprintf("%s/health", baseURL), nil)
	if err != nil {
		return err
	}
	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("healthcheck status=%d", resp.StatusCode)
	}
	return nil
}

func ConnectWithBackoff(ctx context.Context, target string, cfg BackoffConfig, logger *slog.Logger) (*grpc.ClientConn, error) {
	if cfg.MaxRetries <= 0 {
		cfg = DefaultBackoffConfig()
	}
	var lastErr error
	delay := cfg.BaseDelay
	for attempt := 1; attempt <= cfg.MaxRetries; attempt++ {
		conn, err := grpc.NewClient(target, grpc.WithTransportCredentials(insecure.NewCredentials()))
		if err == nil {
			logger.Info("grpc connected", "attempt", attempt, "target", target)
			return conn, nil
		}
		lastErr = err
		logger.Warn("grpc connect failed", "attempt", attempt, "error", err.Error())
		if attempt == cfg.MaxRetries {
			break
		}
		select {
		case <-ctx.Done():
			return nil, ctx.Err()
		case <-time.After(delay):
		}
		delay = time.Duration(float64(delay) * cfg.Factor)
	}
	return nil, fmt.Errorf("connect failed after %d retries: %w", cfg.MaxRetries, lastErr)
}

func ContextWithSignals(parent context.Context) (context.Context, context.CancelFunc) {
	ctx, cancel := signal.NotifyContext(parent, syscall.SIGINT, syscall.SIGTERM)
	return ctx, cancel
}

func Run(ctx context.Context, grpcTarget string, healthBaseURL string, logger *slog.Logger) error {
	if logger == nil {
		logger = NewJSONLogger()
	}
	if err := HealthCheck(ctx, healthBaseURL, &http.Client{Timeout: 2 * time.Second}); err != nil {
		return fmt.Errorf("health check failed: %w", err)
	}
	conn, err := ConnectWithBackoff(ctx, grpcTarget, DefaultBackoffConfig(), logger)
	if err != nil {
		return err
	}
	defer conn.Close()

	logger.Info("stream start")
	<-ctx.Done()
	if errors.Is(ctx.Err(), context.Canceled) {
		logger.Info("shutdown requested")
	}
	return nil
}
