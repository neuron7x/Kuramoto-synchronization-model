"""
Performance profiling for HPC-AI v4.

Profiles:
- Forward pass latency
- Training step latency
- FLOPs estimation
- Memory usage
- Component-wise breakdown (GRU, TransformerEncoder, etc.)

Uses torch.profiler for detailed analysis.
"""

import time

import numpy as np
import torch
from torch.profiler import ProfilerActivity, profile, record_function

from neuropro.hpc_active_inference_v4 import HPCActiveInferenceModuleV4
from neuropro.hpc_validation import generate_synthetic_data


def count_parameters(model):
    """Count total and trainable parameters."""
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return total, trainable


def estimate_flops_forward(model, input_size=(1, 10)):
    """Estimate FLOPs for forward pass (rough approximation)."""
    # For Transformer: ~4 * d_model^2 * seq_len per layer
    # For GRU: ~3 * hidden_dim^2 * seq_len per layer

    state_dim = model.state_dim
    hidden_dim = 256  # From model architecture
    seq_len = 10  # Mock sequence length used in HPC forward

    # Input embedding
    flops_embed = input_size[1] * state_dim

    # Transformer encoder (3 layers, 8 heads)
    flops_transformer = 3 * (4 * state_dim**2 * seq_len)

    # HPC GRU layers (3 levels, bidirectional)
    flops_gru = 3 * (3 * (hidden_dim * 2) ** 2 * seq_len)

    # Residual skips
    flops_residual = 3 * (state_dim * hidden_dim * 2)

    # Error layers
    flops_error = 3 * ((hidden_dim * 2 + state_dim) * state_dim)

    total_flops = (
        flops_embed + flops_transformer + flops_gru + flops_residual + flops_error
    )
    return total_flops


def profile_forward_pass(model, data, num_runs=100):
    """Profile forward pass latency."""
    model.eval()

    # Warmup
    with torch.no_grad():
        for _ in range(10):
            _ = model.afferent_synthesis(data)

    # Measure
    latencies = []
    with torch.no_grad():
        for _ in range(num_runs):
            start = time.perf_counter()
            state = model.afferent_synthesis(data)
            pred, pwpe = model.hpc_forward(state)
            end = time.perf_counter()
            latencies.append((end - start) * 1000)  # Convert to ms

    return {
        "mean_ms": np.mean(latencies),
        "std_ms": np.std(latencies),
        "min_ms": np.min(latencies),
        "max_ms": np.max(latencies),
        "p50_ms": np.percentile(latencies, 50),
        "p95_ms": np.percentile(latencies, 95),
        "p99_ms": np.percentile(latencies, 99),
    }


def profile_training_step(model, data, num_runs=50):
    """Profile training step latency."""
    model.train()

    # Warmup
    for _ in range(5):
        state = model.afferent_synthesis(data)
        action = torch.tensor([1])
        reward = 1.0
        model.sr_drl_step(state, action, reward, state, 0.15)

    # Measure
    latencies = []
    for _ in range(num_runs):
        state = model.afferent_synthesis(data)
        action = torch.tensor([np.random.randint(0, 3)])
        reward = np.random.uniform(-1, 1)

        start = time.perf_counter()
        model.sr_drl_step(state, action, reward, state, 0.15)
        end = time.perf_counter()
        latencies.append((end - start) * 1000)

    return {
        "mean_ms": np.mean(latencies),
        "std_ms": np.std(latencies),
        "min_ms": np.min(latencies),
        "max_ms": np.max(latencies),
        "p50_ms": np.percentile(latencies, 50),
        "p95_ms": np.percentile(latencies, 95),
        "p99_ms": np.percentile(latencies, 99),
    }


def profile_components(model, data):
    """Profile individual components using torch.profiler."""
    model.eval()

    with profile(
        activities=[ProfilerActivity.CPU],
        record_shapes=True,
        with_stack=True,
    ) as prof:
        with record_function("full_forward"):
            with torch.no_grad():
                with record_function("afferent_synthesis"):
                    state = model.afferent_synthesis(data)

                with record_function("hpc_forward"):
                    pred, pwpe = model.hpc_forward(state)

                with record_function("actor"):
                    _ = model.actor(state)

                with record_function("critic"):
                    _ = model.critic(state)

    # Print profiling results
    print("\n" + "=" * 80)
    print("Component-wise Profiling (CPU)")
    print("=" * 80)
    print(prof.key_averages().table(sort_by="cpu_time_total", row_limit=20))
    return prof


def profile_memory(model, data):
    """Profile memory usage."""
    if torch.cuda.is_available():
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.empty_cache()

        # Run forward and backward
        state = model.afferent_synthesis(data)
        pred, pwpe = model.hpc_forward(state)
        loss = pwpe
        loss.backward()

        memory_allocated = torch.cuda.max_memory_allocated() / 1024**2  # MB
        memory_reserved = torch.cuda.max_memory_reserved() / 1024**2

        return {
            "allocated_mb": memory_allocated,
            "reserved_mb": memory_reserved,
        }
    else:
        # CPU memory estimation (rough)
        total_params = sum(p.numel() for p in model.parameters())
        # Assume float32 (4 bytes per param)
        param_memory = total_params * 4 / 1024**2

        # Estimate activations (very rough)
        activation_memory = param_memory * 2  # Rule of thumb

        return {
            "param_mb": param_memory,
            "estimated_total_mb": param_memory + activation_memory,
        }


def run_comprehensive_profile():
    """Run comprehensive performance profiling."""
    print("=" * 80)
    print("HPC-AI v4 Performance Profiling")
    print("=" * 80)

    # Create model
    model = HPCActiveInferenceModuleV4(
        input_dim=10,
        state_dim=128,
        action_dim=3,
        hidden_dim=256,
        hpc_levels=3,
    )

    # Generate data
    data = generate_synthetic_data(n_days=100, seed=42)

    # 1. Model size
    print("\n1. Model Size")
    print("-" * 80)
    total_params, trainable_params = count_parameters(model)
    print(f"Total parameters: {total_params:,}")
    print(f"Trainable parameters: {trainable_params:,}")
    print(f"Model size (MB): {total_params * 4 / 1024**2:.2f}")

    # 2. FLOPs estimation
    print("\n2. FLOPs Estimation")
    print("-" * 80)
    estimated_flops = estimate_flops_forward(model, input_size=(1, 10))
    print(f"Estimated FLOPs per forward pass: {estimated_flops:,}")
    print(f"Estimated GFLOPs: {estimated_flops / 1e9:.4f}")

    # 3. Forward pass profiling
    print("\n3. Forward Pass Latency")
    print("-" * 80)
    forward_stats = profile_forward_pass(model, data, num_runs=100)
    print(f"Mean: {forward_stats['mean_ms']:.2f} ms")
    print(f"Std:  {forward_stats['std_ms']:.2f} ms")
    print(f"Min:  {forward_stats['min_ms']:.2f} ms")
    print(f"Max:  {forward_stats['max_ms']:.2f} ms")
    print(f"P50:  {forward_stats['p50_ms']:.2f} ms")
    print(f"P95:  {forward_stats['p95_ms']:.2f} ms")
    print(f"P99:  {forward_stats['p99_ms']:.2f} ms")

    # Check if meets <1ms target
    if forward_stats["mean_ms"] < 1.0:
        print("✓ Meets <1ms target for forward pass")
    else:
        print(f"⚠ Forward pass ({forward_stats['mean_ms']:.2f}ms) exceeds 1ms target")
        print("  Consider: FlashAttention, quantization, or model pruning")

    # 4. Training step profiling
    print("\n4. Training Step Latency")
    print("-" * 80)
    train_stats = profile_training_step(model, data, num_runs=50)
    print(f"Mean: {train_stats['mean_ms']:.2f} ms")
    print(f"Std:  {train_stats['std_ms']:.2f} ms")
    print(f"Min:  {train_stats['min_ms']:.2f} ms")
    print(f"Max:  {train_stats['max_ms']:.2f} ms")
    print(f"P50:  {train_stats['p50_ms']:.2f} ms")
    print(f"P95:  {train_stats['p95_ms']:.2f} ms")
    print(f"P99:  {train_stats['p99_ms']:.2f} ms")

    # 5. Component-wise profiling
    print("\n5. Component-wise Profiling")
    print("-" * 80)
    _ = profile_components(model, data)

    # 6. Memory profiling
    print("\n6. Memory Usage")
    print("-" * 80)
    mem_stats = profile_memory(model, data)
    for key, value in mem_stats.items():
        print(f"{key}: {value:.2f} MB")

    # 7. Throughput estimation
    print("\n7. Throughput Estimation")
    print("-" * 80)
    throughput_forward = 1000.0 / forward_stats["mean_ms"]  # decisions/second
    throughput_train = 1000.0 / train_stats["mean_ms"]  # training steps/second
    print(f"Forward pass throughput: {throughput_forward:.2f} decisions/second")
    print(f"Training throughput: {throughput_train:.2f} steps/second")

    # 8. Optimization recommendations
    print("\n8. Optimization Recommendations")
    print("-" * 80)
    if forward_stats["mean_ms"] > 1.0:
        print("⚠ Forward latency > 1ms:")
        print("  - Consider FlashAttention for TransformerEncoder")
        print("  - Try int8 quantization for inference")
        print("  - Profile with CUDA/GPU for better performance")

    if train_stats["mean_ms"] > 100.0:
        print("⚠ Training step > 100ms:")
        print("  - Consider gradient accumulation")
        print("  - Use mixed precision training (fp16)")

    if mem_stats.get("estimated_total_mb", 0) > 500:
        print("⚠ High memory usage:")
        print("  - Consider model pruning")
        print("  - Use gradient checkpointing")

    print("\n" + "=" * 80)
    print("Profiling Complete")
    print("=" * 80)

    return {
        "forward": forward_stats,
        "training": train_stats,
        "memory": mem_stats,
        "params": {"total": total_params, "trainable": trainable_params},
        "flops": estimated_flops,
    }


if __name__ == "__main__":
    results = run_comprehensive_profile()
