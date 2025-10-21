package tests

import (
    "os/exec"
    "path/filepath"
    "testing"

    "github.com/gruntwork-io/terratest/modules/terraform"
    "github.com/stretchr/testify/require"
)

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
    require.NoError(t, err)
}
