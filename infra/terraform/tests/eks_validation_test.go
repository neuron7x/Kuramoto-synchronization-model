package tests

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/gruntwork-io/terratest/modules/test-structure"
	"github.com/stretchr/testify/require"
)

func copyFile(srcPath, dstPath string) error {
	src, err := os.Open(srcPath)
	if err != nil {
		return err
	}
	defer src.Close()

	if err := os.MkdirAll(filepath.Dir(dstPath), 0o755); err != nil {
		return err
	}

	dst, err := os.OpenFile(dstPath, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	defer dst.Close()

	if _, err := io.Copy(dst, src); err != nil {
		return err
	}

	return dst.Sync()
}

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

func TestEKSModuleTerraformValidate(t *testing.T) {
	t.Parallel()

	if _, err := exec.LookPath("terraform"); err != nil {
		t.Skip("terraform binary not available in PATH")
	}

	// Some CI jobs (including our own release workflows) set TF_CLI_ARGS with
	// environment specific -var-file flags to drive terraform plan/apply. The
	// validate subcommand stopped accepting -var-file in Terraform 1.6, so make
	// sure those inherited flags do not bleed into this test run.
	for _, envVar := range []string{"TF_CLI_ARGS", "TF_CLI_ARGS_validate"} {
		t.Setenv(envVar, "")
	}

	terraformDir := test_structure.CopyTerraformFolderToTemp(t, "..", "eks")
	stagingVarsFile := filepath.Join("..", "eks", "environments", "staging.tfvars")
	autoVarsFile := filepath.Join(terraformDir, "staging.auto.tfvars")

	require.NoError(t, copyFile(stagingVarsFile, autoVarsFile))

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
