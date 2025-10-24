package tests

import (
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/gruntwork-io/terratest/modules/terraform"
	"github.com/stretchr/testify/require"
)

func isTerraformRegistryConnectivityError(err error) bool {
	if err == nil {
		return false
	}

	message := strings.ToLower(err.Error())
	if message == "" {
		return false
	}

	if !strings.Contains(message, "failed to query available provider packages") {
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

	for _, indicator := range networkIndicators {
		if strings.Contains(message, indicator) {
			return true
		}
	}

	return false
}

func TestEKSModuleTerraformValidate(t *testing.T) {
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

	_, err := terraform.InitAndValidateE(t, options)
	if isTerraformRegistryConnectivityError(err) {
		t.Skipf("skipping terraform validation because provider registry is unavailable: %v", err)
	}
	require.NoError(t, err)
}
