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
	message := err.Error()
	if message == "" {
		return false
	}

	substrings := []string{
		"Failed to query available provider packages",
		"could not connect to registry.terraform.io",
		"Forbidden",
	}
	matches := 0
	for _, part := range substrings {
		if strings.Contains(message, part) {
			matches++
		}
	}

	return matches >= 2
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
