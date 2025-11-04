package tests

import (
	"context"
	"errors"
	"fmt"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
)

func errorMessages(err error) []string {
	type singleUnwrapper interface {
		Unwrap() error
	}

	type multiUnwrapper interface {
		Unwrap() []error
	}

	if err == nil {
		return nil
	}

	stack := []error{err}
	visited := make(map[error]struct{})
	var messages []string

	for len(stack) > 0 {
		current := stack[len(stack)-1]
		stack = stack[:len(stack)-1]

		if current == nil {
			continue
		}

		if _, seen := visited[current]; seen {
			continue
		}
		visited[current] = struct{}{}

		if message := strings.ToLower(current.Error()); message != "" {
			messages = append(messages, message)
		}

		switch unwrapper := any(current).(type) {
		case multiUnwrapper:
			stack = append(stack, unwrapper.Unwrap()...)
		case singleUnwrapper:
			stack = append(stack, unwrapper.Unwrap())
		}
	}

	return messages
}

func isTerraformRegistryConnectivityError(err error) bool {
	if err == nil {
		return false
	}

	networkIndicators := []string{
		"could not connect to registry.terraform.io",
		"registry.terraform.io/.well-known/terraform.json",
		"lookup registry.terraform.io",
		"dial tcp",
		"timeout",
		"context deadline exceeded",
		"connection reset",
		"connection refused",
		"no such host",
		"tls",
		"x509:",
		"forbidden",
		"too many requests",
		"service unavailable",
	}

	for _, message := range errorMessages(err) {
		if !strings.Contains(message, "failed to query available provider packages") {
			continue
		}

		for _, indicator := range networkIndicators {
			if strings.Contains(message, indicator) {
				return true
			}
		}
	}

	return false
}

func runTerraformValidationWithContext(ctx context.Context, t *testing.T, options *terraform.Options) error {
	t.Helper()

	if ctx == nil {
		return errors.New("context must not be nil")
	}

	resultCh := make(chan error, 1)
	go func() {
		_, err := terraform.InitAndValidateE(t, options)
		resultCh <- err
	}()

	select {
	case err := <-resultCh:
		if err != nil {
			return fmt.Errorf("terraform validation failed: %w", err)
		}
		return nil
	case <-ctx.Done():
		terraformErr := <-resultCh
		if terraformErr != nil {
			return fmt.Errorf("terraform validation failed after context cancellation (context error: %w): %w", ctx.Err(), terraformErr)
		}
		return fmt.Errorf("terraform validation canceled or timed out: %w", ctx.Err())
	}
}

func TestL6EKSModuleTerraformValidate(t *testing.T) {
	t.Parallel()

	if _, err := exec.LookPath("terraform"); err != nil {
		t.Skip("terraform binary not available in PATH")
	}

	terraformDir := filepath.Join("..", "eks")
	options := &terraform.Options{
		TerraformDir: terraformDir,
		EnvVars: map[string]string{
			"TF_IN_AUTOMATION": "true",
			"TF_CLI_ARGS_init": "-backend=false",
		},
		NoColor:     true,
		Reconfigure: true,
	}

	baseCtx := context.Background()
	if deadline, ok := t.Deadline(); ok {
		var cancel context.CancelFunc
		baseCtx, cancel = context.WithDeadline(baseCtx, deadline)
		t.Cleanup(cancel)
	} else {
		const defaultTimeout = 5 * time.Minute
		var cancel context.CancelFunc
		baseCtx, cancel = context.WithTimeout(baseCtx, defaultTimeout)
		t.Cleanup(cancel)
	}

	err := runTerraformValidationWithContext(baseCtx, t, options)
	if isTerraformRegistryConnectivityError(err) {
		t.Skipf("skipping terraform validation because provider registry is unavailable: %v", err)
	}

	require.NoError(t, err)
}
