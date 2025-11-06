"""Tests for continual learning metrics."""
import numpy as np
import pytest

from core.validation.continual_learning_metrics import (
    ContinualLearningEvaluator,
    ContinualLearningMetrics,
    SelfRewardingRL,
)


def test_continual_learning_evaluator_init():
    """Test evaluator initialization."""
    evaluator = ContinualLearningEvaluator(task_dimension=10)
    assert evaluator.task_dimension == 10
    assert len(evaluator._task_performances) == 0


def test_fid_score_computation():
    """Test FID score computation."""
    evaluator = ContinualLearningEvaluator(task_dimension=5)
    
    np.random.seed(42)
    # Generate embeddings
    real = np.random.randn(100, 5)
    generated_similar = real + np.random.randn(100, 5) * 0.1
    generated_different = np.random.randn(100, 5) * 2
    
    fid_similar = evaluator.compute_fid_score(real.flatten(), generated_similar.flatten())
    fid_different = evaluator.compute_fid_score(real.flatten(), generated_different.flatten())
    
    # Similar should have lower FID
    assert fid_similar < fid_different


def test_task_performance_recording():
    """Test recording task performances."""
    evaluator = ContinualLearningEvaluator()
    
    evaluator.record_task_performance("task1", 0.8)
    evaluator.record_task_performance("task1", 0.85)
    evaluator.record_task_performance("task2", 0.7)
    
    assert "task1" in evaluator._task_performances
    assert len(evaluator._task_performances["task1"]) == 2
    assert len(evaluator._task_performances["task2"]) == 1


def test_retention_rate_perfect():
    """Test perfect retention (no degradation)."""
    evaluator = ContinualLearningEvaluator()
    
    evaluator.record_task_performance("task1", 0.8)
    evaluator.record_task_performance("task1", 0.8)
    
    retention = evaluator.compute_retention_rate("task1")
    assert retention == 1.0


def test_retention_rate_improvement():
    """Test retention with improvement."""
    evaluator = ContinualLearningEvaluator()
    
    evaluator.record_task_performance("task1", 0.7)
    evaluator.record_task_performance("task1", 0.9)
    
    retention = evaluator.compute_retention_rate("task1")
    assert retention > 1.0  # Improved over time


def test_retention_rate_degradation():
    """Test retention with forgetting."""
    evaluator = ContinualLearningEvaluator()
    
    evaluator.record_task_performance("task1", 0.9)
    evaluator.record_task_performance("task1", 0.7)
    
    retention = evaluator.compute_retention_rate("task1")
    assert retention < 1.0  # Degraded


def test_backward_transfer_positive():
    """Test positive backward transfer."""
    evaluator = ContinualLearningEvaluator()
    
    bt = evaluator.compute_backward_transfer("task1", 0.7, 0.85)
    assert bt > 0  # Improved on old task


def test_backward_transfer_negative():
    """Test negative backward transfer (forgetting)."""
    evaluator = ContinualLearningEvaluator()
    
    bt = evaluator.compute_backward_transfer("task1", 0.9, 0.6)
    assert bt < 0  # Forgot old task


def test_forward_transfer():
    """Test forward transfer computation."""
    evaluator = ContinualLearningEvaluator()
    
    ft = evaluator.compute_forward_transfer(0.8, random_baseline=0.5)
    assert abs(ft - 0.3) < 1e-10  # Benefit from prior knowledge (with floating point tolerance)


def test_catastrophic_forgetting_index_no_forgetting():
    """Test CFI with no forgetting."""
    evaluator = ContinualLearningEvaluator()
    
    # Stable performance on all tasks
    evaluator.record_task_performance("task1", 0.8)
    evaluator.record_task_performance("task1", 0.85)
    evaluator.record_task_performance("task2", 0.7)
    evaluator.record_task_performance("task2", 0.75)
    
    cfi = evaluator.compute_catastrophic_forgetting_index()
    assert cfi < 0.3  # Low forgetting


def test_catastrophic_forgetting_index_high():
    """Test CFI with catastrophic forgetting."""
    evaluator = ContinualLearningEvaluator()
    
    # Performance degrades significantly
    evaluator.record_task_performance("task1", 0.9)
    evaluator.record_task_performance("task1", 0.3)
    evaluator.record_task_performance("task2", 0.8)
    evaluator.record_task_performance("task2", 0.2)
    
    cfi = evaluator.compute_catastrophic_forgetting_index()
    assert cfi > 0.5  # High forgetting


def test_continual_learning_metrics_evaluation():
    """Test comprehensive metrics evaluation."""
    evaluator = ContinualLearningEvaluator(task_dimension=5)
    
    # Record multiple tasks
    evaluator.record_task_performance("task1", 0.7)
    evaluator.record_task_performance("task1", 0.85)
    evaluator.record_task_performance("task2", 0.6)
    evaluator.record_task_performance("task2", 0.75)
    evaluator.record_task_performance("task3", 0.8)
    
    # Generate embeddings for FID
    np.random.seed(42)
    real = np.random.randn(50, 5)
    generated = real + np.random.randn(50, 5) * 0.1
    
    metrics = evaluator.evaluate(real.flatten(), generated.flatten())
    
    assert isinstance(metrics, ContinualLearningMetrics)
    assert metrics.fid_score >= 0
    assert 0 <= metrics.retention_rate <= 2.0
    assert metrics.forward_transfer >= 0
    assert 0 <= metrics.catastrophic_forgetting_index <= 1.0


def test_self_rewarding_rl_initialization():
    """Test SelfRewardingRL initialization."""
    srdrl = SelfRewardingRL(
        initial_lr=3e-4,
        lr_min=1e-5,
        lr_max=1e-3,
    )
    assert srdrl.current_lr == 3e-4
    assert srdrl.lr_min == 1e-5
    assert srdrl.lr_max == 1e-3


def test_lr_increase_on_improvement():
    """Test learning rate increases when improving."""
    srdrl = SelfRewardingRL(initial_lr=3e-4)
    
    # Improving rewards, not converging
    for i in range(5):
        new_lr = srdrl.update_lr(reward=0.1 + i * 0.01, convergence_rate=-0.01)
    
    # LR should have increased
    assert srdrl.current_lr > 3e-4


def test_lr_decrease_on_degradation():
    """Test learning rate decreases when degrading."""
    srdrl = SelfRewardingRL(initial_lr=3e-4)
    
    # Populate history with good rewards first
    for _ in range(10):
        srdrl._reward_history.append(0.5)
    
    # Now degrade
    new_lr = srdrl.update_lr(reward=0.2, convergence_rate=0.0)
    
    # LR should decrease
    assert srdrl.current_lr < 3e-4


def test_lr_bounds_respected():
    """Test learning rate respects min/max bounds."""
    srdrl = SelfRewardingRL(initial_lr=3e-4, lr_min=1e-5, lr_max=1e-3)
    
    # Try to increase many times
    for _ in range(100):
        srdrl.update_lr(reward=1.0, convergence_rate=-1.0)
    
    assert srdrl.current_lr <= srdrl.lr_max
    
    # Try to decrease many times
    srdrl2 = SelfRewardingRL(initial_lr=3e-4, lr_min=1e-5, lr_max=1e-3)
    for _ in range(10):
        srdrl2._reward_history.append(1.0)
    for _ in range(100):
        srdrl2.update_lr(reward=-1.0, convergence_rate=0.0)
    
    assert srdrl2.current_lr >= srdrl2.lr_min


def test_lr_schedule_tracking():
    """Test learning rate schedule is tracked."""
    srdrl = SelfRewardingRL(initial_lr=3e-4)
    
    initial_len = len(srdrl._lr_history)
    
    srdrl.update_lr(reward=0.5, convergence_rate=0.0)
    srdrl.update_lr(reward=0.6, convergence_rate=-0.01)
    
    schedule = srdrl.get_lr_schedule()
    
    assert len(schedule) > initial_len
    assert schedule[0] == 3e-4


def test_fid_score_edge_cases():
    """Test FID score with edge cases."""
    evaluator = ContinualLearningEvaluator(task_dimension=5)
    
    # Insufficient data
    small_real = np.random.randn(1, 5)
    small_gen = np.random.randn(1, 5)
    fid = evaluator.compute_fid_score(small_real.flatten(), small_gen.flatten())
    assert fid == 1.0  # Fallback value


def test_retention_rate_edge_cases():
    """Test retention rate with edge cases."""
    evaluator = ContinualLearningEvaluator()
    
    # Task not recorded
    retention = evaluator.compute_retention_rate("nonexistent")
    assert retention == 1.0  # Default
    
    # Single performance
    evaluator.record_task_performance("single", 0.8)
    retention = evaluator.compute_retention_rate("single")
    assert retention == 1.0  # No change to measure


def test_cfi_empty_tasks():
    """Test CFI with no tasks."""
    evaluator = ContinualLearningEvaluator()
    cfi = evaluator.compute_catastrophic_forgetting_index()
    assert cfi == 0.0
