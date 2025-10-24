package tests

import (
	"errors"
	"testing"
)

func TestIsTerraformRegistryConnectivityError(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name    string
		message string
		want    bool
	}{
		{
			name:    "forbidden",
			message: "Error: Failed to query available provider packages\n\nCould not retrieve the list of available versions for provider hashicorp/aws: could not connect to registry.terraform.io: failed to request discovery document: Get \"https://registry.terraform.io/.well-known/terraform.json\": Forbidden",
			want:    true,
		},
		{
			name:    "timeout",
			message: "Error: Failed to query available provider packages: Get \"https://registry.terraform.io/.well-known/terraform.json\": context deadline exceeded",
			want:    true,
		},
		{
			name:    "dns",
			message: "Error: Failed to query available provider packages: lookup registry.terraform.io on 127.0.0.53:53: no such host",
			want:    true,
		},
		{
			name:    "non connectivity error",
			message: "Error: Failed to query available provider packages: no available releases match the given constraints",
			want:    false,
		},
		{
			name:    "empty",
			message: "",
			want:    false,
		},
	}

	for _, tc := range testCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			var err error
			if tc.message != "" {
				err = errors.New(tc.message)
			}
			if got := isTerraformRegistryConnectivityError(err); got != tc.want {
				t.Fatalf("isTerraformRegistryConnectivityError(%q) = %t, want %t", tc.message, got, tc.want)
			}
		})
	}
}
